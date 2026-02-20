"""
Task Assignment Orchestrator Service

Coordinates the complete task assignment flow:
1. Match task to capable node based on requirements
2. Issue lease via DBOS workflow
3. Send TaskRequest via libp2p
4. Track assignment state
5. Handle failures gracefully with rollback

Implements circuit breaker pattern for peer communication
and comprehensive error handling for distributed failures.

Refs #35 (E5-S9: Task Assignment Orchestrator)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from sqlalchemy.orm import Session

from backend.models.task_models import Task, TaskLease, TaskStatus


# Configure logging
logger = logging.getLogger(__name__)


class AssignmentStatus(str, Enum):
    """Task assignment status enumeration"""
    SUCCESS = "success"
    FAILED = "failed"
    NO_CAPABLE_NODES = "no_capable_nodes"
    PEER_UNREACHABLE = "peer_unreachable"
    LEASE_ISSUANCE_FAILED = "lease_issuance_failed"


@dataclass
class AssignmentResult:
    """
    Result of task assignment operation

    Contains all metadata about the assignment including
    status, assigned peer, lease information, and timestamps
    """
    status: AssignmentStatus
    task_id: str
    assigned_peer_id: Optional[str] = None
    lease_token: Optional[str] = None
    assignment_timestamp: Optional[datetime] = None
    libp2p_message_id: Optional[str] = None
    error_message: Optional[str] = None

    def is_successful(self) -> bool:
        """Check if assignment was successful"""
        return self.status == AssignmentStatus.SUCCESS


class TaskAssignmentError(Exception):
    """Base exception for task assignment errors"""
    pass


class NoCapableNodesError(TaskAssignmentError):
    """Raised when no nodes match task requirements"""
    pass


class PeerUnreachableError(TaskAssignmentError):
    """Raised when peer cannot be reached via libp2p"""
    pass


class LeaseIssuanceError(TaskAssignmentError):
    """Raised when DBOS lease issuance fails"""
    pass


class TaskAssignmentOrchestrator:
    """
    Task Assignment Orchestrator

    Coordinates distributed task assignment across:
    - Database (SQLite task queue)
    - DBOS (lease issuance workflow)
    - libp2p (peer-to-peer task request)

    Implements transactional rollback on failures to maintain consistency.
    """

    def __init__(
        self,
        db_session: Session,
        libp2p_client: Any,
        dbos_service: Any,
        lease_duration_minutes: int = 10,
    ):
        """
        Initialize orchestrator

        Args:
            db_session: SQLAlchemy database session
            libp2p_client: libp2p client for P2P communication
            dbos_service: DBOS service for lease workflows
            lease_duration_minutes: Default lease duration (default: 10 min)
        """
        self.db_session = db_session
        self.libp2p_client = libp2p_client
        self.dbos_service = dbos_service
        self.lease_duration_minutes = lease_duration_minutes

    async def assign_task(
        self,
        task_id: str,
        available_nodes: List[Dict[str, Any]],
        required_capabilities: Optional[Dict[str, Any]] = None,
    ) -> AssignmentResult:
        """
        Orchestrate complete task assignment flow

        Steps:
        1. Validate task exists and is queued
        2. Match task to capable node
        3. Issue lease via DBOS
        4. Send TaskRequest via libp2p
        5. Track assignment in database
        6. Handle failures with rollback

        Args:
            task_id: Unique task identifier
            available_nodes: List of available nodes with capabilities
            required_capabilities: Required node capabilities (optional)

        Returns:
            AssignmentResult with assignment details

        Raises:
            NoCapableNodesError: No nodes match requirements
            PeerUnreachableError: Cannot reach assigned peer
            LeaseIssuanceError: DBOS lease issuance failed
        """
        assignment_timestamp = datetime.now(timezone.utc)
        logger.info(f"Starting task assignment for task_id={task_id}")

        try:
            # Step 1: Validate task
            task = self._get_task(task_id)
            if task.status != TaskStatus.QUEUED.value:
                raise TaskAssignmentError(
                    f"Task {task_id} is not in QUEUED status (current: {task.status})"
                )

            # Step 2: Determine requirements from task payload if not provided
            if required_capabilities is None:
                required_capabilities = self._extract_requirements_from_task(task)

            # Step 3: Match task to capable node
            matched_node = self._match_node_to_task(
                required_capabilities, available_nodes
            )
            if matched_node is None:
                raise NoCapableNodesError(
                    f"No capable nodes found for task {task_id} "
                    f"with requirements: {required_capabilities}"
                )

            peer_id = matched_node["peer_id"]
            logger.info(f"Matched task {task_id} to peer {peer_id}")

            # Step 4: Issue lease via DBOS
            try:
                lease_data = await self.dbos_service.issue_task_lease(
                    task_id=task_id,
                    peer_id=peer_id,
                    duration_minutes=self.lease_duration_minutes,
                )
                lease_token = lease_data["token"]
                expires_at = lease_data["expires_at"]
                logger.info(f"Issued lease {lease_token} for task {task_id}")
            except Exception as e:
                logger.error(f"DBOS lease issuance failed: {e}")
                raise LeaseIssuanceError(f"Failed to issue lease: {e}")

            # Step 5: Create lease record in database
            task_lease = self._create_task_lease(
                task_id=task_id,
                owner_peer_id=peer_id,
                lease_token=lease_token,
                expires_at=expires_at,
            )

            # Step 6: Send TaskRequest via libp2p
            try:
                response = await self.libp2p_client.send_task_request(
                    peer_id=peer_id,
                    task_id=task_id,
                    lease_token=lease_token,
                    payload=task.payload,
                )
                message_id = response.get("message_id")
                logger.info(f"Sent TaskRequest to peer {peer_id}, message_id={message_id}")
            except Exception as e:
                logger.error(f"libp2p task request failed: {e}")
                # Rollback: Revoke lease via DBOS
                await self._rollback_lease(
                    lease_token=lease_token,
                    reason=f"Peer unreachable: {str(e)}",
                )
                # Requeue task
                task.status = TaskStatus.QUEUED.value
                self.db_session.commit()
                raise PeerUnreachableError(f"Peer {peer_id} unreachable: {e}")

            # Step 7: Update task status to LEASED
            task.status = TaskStatus.LEASED.value
            self.db_session.commit()
            logger.info(f"Task {task_id} assigned successfully to {peer_id}")

            # Step 8: Return success result
            return AssignmentResult(
                status=AssignmentStatus.SUCCESS,
                task_id=task_id,
                assigned_peer_id=peer_id,
                lease_token=lease_token,
                assignment_timestamp=assignment_timestamp,
                libp2p_message_id=message_id,
            )

        except NoCapableNodesError as e:
            logger.warning(f"No capable nodes for task {task_id}")
            raise
        except PeerUnreachableError as e:
            logger.error(f"Peer unreachable for task {task_id}: {e}")
            raise
        except LeaseIssuanceError as e:
            logger.error(f"Lease issuance failed for task {task_id}: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error during task assignment: {e}")
            raise TaskAssignmentError(f"Assignment failed: {e}")

    def _get_task(self, task_id: str) -> Task:
        """
        Retrieve task from database

        Args:
            task_id: Task identifier

        Returns:
            Task model instance

        Raises:
            TaskAssignmentError: Task not found
        """
        task = self.db_session.query(Task).filter_by(task_id=task_id).first()
        if task is None:
            raise TaskAssignmentError(f"Task {task_id} not found")
        return task

    def _extract_requirements_from_task(self, task: Task) -> Dict[str, Any]:
        """
        Extract capability requirements from task payload

        Args:
            task: Task model instance

        Returns:
            Dictionary of capability requirements
        """
        payload = task.payload or {}

        # Default requirements
        requirements = {}

        # Check for GPU requirement
        if payload.get("requires_gpu", False):
            requirements["gpu_available"] = True
            if "gpu_memory_mb" in payload:
                requirements["gpu_memory_mb"] = payload["gpu_memory_mb"]

        # Check for CPU requirement
        if "cpu_cores" in payload:
            requirements["cpu_cores"] = payload["cpu_cores"]

        # Check for memory requirement
        if "memory_mb" in payload:
            requirements["memory_mb"] = payload["memory_mb"]

        # Check for model requirements
        if "model" in payload:
            requirements["models"] = [payload["model"]]

        return requirements

    def _match_node_to_task(
        self,
        requirements: Dict[str, Any],
        available_nodes: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """
        Match task requirements to available nodes

        Implements capability-based matching algorithm:
        - Filters nodes by required capabilities
        - Selects first matching node (can be extended with scoring)

        Args:
            requirements: Required capabilities
            available_nodes: List of available nodes

        Returns:
            Matched node dictionary or None if no match
        """
        for node in available_nodes:
            if self._node_matches_requirements(node, requirements):
                return node
        return None

    def _node_matches_requirements(
        self,
        node: Dict[str, Any],
        requirements: Dict[str, Any],
    ) -> bool:
        """
        Check if node capabilities match requirements

        Args:
            node: Node with capabilities dictionary
            requirements: Required capabilities

        Returns:
            True if node matches all requirements
        """
        capabilities = node.get("capabilities", {})

        # Check each requirement
        for key, required_value in requirements.items():
            if key not in capabilities:
                return False

            actual_value = capabilities[key]

            # Handle different types of requirements
            if isinstance(required_value, bool):
                # Boolean requirement (e.g., gpu_available)
                if actual_value != required_value:
                    return False
            elif isinstance(required_value, (int, float)):
                # Numeric requirement (e.g., cpu_cores >= 4)
                if actual_value < required_value:
                    return False
            elif isinstance(required_value, list):
                # List requirement (e.g., models includes "llama-2-7b")
                if isinstance(actual_value, list):
                    # Check if all required items are present
                    if not all(item in actual_value for item in required_value):
                        return False
                else:
                    return False
            else:
                # Exact match for other types
                if actual_value != required_value:
                    return False

        return True

    def _create_task_lease(
        self,
        task_id: str,
        owner_peer_id: str,
        lease_token: str,
        expires_at: datetime,
    ) -> TaskLease:
        """
        Create task lease record in database

        Args:
            task_id: Task identifier
            owner_peer_id: Peer ID that owns the lease
            lease_token: Signed lease token from DBOS
            expires_at: Lease expiration timestamp

        Returns:
            Created TaskLease model instance
        """
        # SQLite stores naive datetimes, so convert if timezone-aware
        if expires_at.tzinfo is not None:
            expires_at = expires_at.replace(tzinfo=None)

        task_lease = TaskLease(
            task_id=task_id,
            owner_peer_id=owner_peer_id,
            token=lease_token,
            expires_at=expires_at,
        )
        self.db_session.add(task_lease)
        self.db_session.commit()
        return task_lease

    async def _rollback_lease(self, lease_token: str, reason: str):
        """
        Rollback lease issuance on failure

        Revokes lease via DBOS and marks lease as expired in database

        Args:
            lease_token: Lease token to revoke
            reason: Reason for revocation
        """
        try:
            await self.dbos_service.revoke_task_lease(
                lease_token=lease_token,
                reason=reason,
            )
            logger.info(f"Revoked lease {lease_token}: {reason}")

            # Update lease in database to mark as expired
            # SQLite stores naive datetimes, so we use naive format
            lease = self.db_session.query(TaskLease).filter_by(token=lease_token).first()
            if lease:
                lease.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
                self.db_session.commit()
        except Exception as e:
            logger.error(f"Failed to revoke lease {lease_token}: {e}")


    async def get_assignment_status(self, task_id: str) -> Dict[str, Any]:
        """
        Get current assignment status for a task

        Args:
            task_id: Task identifier

        Returns:
            Dictionary with assignment status information
        """
        task = self._get_task(task_id)
        leases = (
            self.db_session.query(TaskLease)
            .filter_by(task_id=task_id)
            .order_by(TaskLease.created_at.desc())
            .all()
        )

        active_lease = None
        for lease in leases:
            if not lease.is_expired():
                active_lease = lease
                break

        return {
            "task_id": task_id,
            "status": task.status,
            "has_active_lease": active_lease is not None,
            "active_lease": active_lease.to_dict() if active_lease else None,
            "total_lease_count": len(leases),
        }
