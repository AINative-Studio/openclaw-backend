"""
Task Lease Issuance Service

Manages task lease issuance workflow including capability matching,
JWT token generation, and fair work distribution.

Refs #27 (E5-S1: Task Lease Issuance)
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from uuid import UUID
import jwt
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.models.task import Task, TaskStatus
from backend.models.task_lease import TaskLease
from backend.models.task_lease_models import NodeCapability, TaskComplexity
from backend.schemas.task_lease_schemas import (
    TaskLeaseRequest,
    TaskLeaseResponse
)


logger = logging.getLogger(__name__)


class CapabilityMismatchError(Exception):
    """Raised when node capabilities don't match task requirements"""

    def __init__(
        self,
        message: str,
        required_capabilities: Dict[str, Any],
        provided_capabilities: Dict[str, Any]
    ):
        super().__init__(message)
        self.required_capabilities = required_capabilities
        self.provided_capabilities = provided_capabilities


class TaskNotAvailableError(Exception):
    """Raised when task is not available for leasing"""
    pass


class LeaseIssuanceError(Exception):
    """Raised when lease issuance fails"""
    pass


class TaskLeaseIssuanceService:
    """
    Service for issuing task leases to capable nodes

    Responsibilities:
    - Validate node capabilities against task requirements
    - Generate signed JWT lease tokens
    - Calculate lease expiration based on task complexity
    - Update task status to LEASED
    - Create and persist TaskLease records
    """

    # Lease duration mapping (in minutes)
    LEASE_DURATION_MAP = {
        "low": 5,
        "medium": 10,
        "high": 15
    }

    def __init__(self, db: Session):
        """
        Initialize task lease issuance service

        Args:
            db: Database session
        """
        self.db = db
        self._secret_key = None

    async def issue_lease(
        self,
        lease_request: TaskLeaseRequest
    ) -> TaskLeaseResponse:
        """
        Issue a task lease to a capable node

        Args:
            lease_request: Lease issuance request

        Returns:
            TaskLeaseResponse with signed JWT token

        Raises:
            TaskNotAvailableError: If task doesn't exist or isn't available
            CapabilityMismatchError: If node doesn't meet requirements
            LeaseIssuanceError: If lease creation fails
        """
        # 1. Fetch and validate task
        task = self._get_available_task(lease_request.task_id)

        # 2. Fetch node capability information (optional, may not exist yet)
        node_capability = self._get_node_capability(lease_request.peer_id)

        # 3. Validate capabilities match requirements
        self._validate_capabilities(
            task=task,
            node_capabilities=lease_request.node_capabilities
        )

        # 4. Calculate lease duration and expiration
        issued_at = datetime.now(timezone.utc)
        expires_at = self._calculate_expiration(task.complexity, issued_at)

        # 5. Generate signed JWT token
        lease_token = self._generate_lease_token(
            task_id=task.id,
            peer_id=lease_request.peer_id,
            expires_at=expires_at
        )

        # 6. Create TaskLease record
        task_lease = TaskLease()
        task_lease.task_id = task.id
        task_lease.owner_peer_id = lease_request.peer_id
        task_lease.token = lease_token
        task_lease.expires_at = expires_at

        # 7. Update task status to LEASED
        task.status = TaskStatus.LEASED

        # 8. Persist changes
        try:
            self.db.add(task_lease)
            self.db.commit()
            self.db.refresh(task_lease)

            logger.info(
                f"Lease issued: task={task.id}, peer={lease_request.peer_id[:12]}..., "
                f"expires_at={expires_at}",
                extra={
                    "task_id": str(task.id),
                    "peer_id": lease_request.peer_id,
                    "lease_id": str(task_lease.id),
                    "expires_at": expires_at.isoformat()
                }
            )

        except IntegrityError as e:
            self.db.rollback()
            logger.error(f"Failed to create lease: {e}")
            raise LeaseIssuanceError(f"Failed to create lease: {e}")

        # 9. Return lease response
        return TaskLeaseResponse(
            lease_id=task_lease.id if hasattr(task_lease, 'id') else uuid4(),
            task_id=task.id,
            peer_id=lease_request.peer_id,
            lease_token=lease_token,
            issued_at=issued_at,
            expires_at=expires_at,
            task_payload=task.payload if task.payload else {}
        )

    def _get_available_task(self, task_id: str) -> Task:
        """
        Fetch task and validate it's available for leasing

        Args:
            task_id: Task identifier

        Returns:
            Task entity

        Raises:
            TaskNotAvailableError: If task not found or not available
        """
        task = self.db.query(Task).filter(Task.id == task_id).first()

        if not task:
            raise TaskNotAvailableError(f"Task {task_id} not found")

        if task.status != TaskStatus.QUEUED:
            raise TaskNotAvailableError(
                f"Task {task_id} is not available (status: {task.status})"
            )

        return task

    def _get_node_capability(self, peer_id: str) -> Optional[NodeCapability]:
        """
        Fetch node capability information

        Args:
            peer_id: Peer identifier

        Returns:
            NodeCapability entity or None if not registered
        """
        return self.db.query(NodeCapability).filter(
            NodeCapability.peer_id == peer_id
        ).first()

    def _validate_capabilities(
        self,
        task: Task,
        node_capabilities: Dict[str, Any]
    ) -> None:
        """
        Validate node capabilities match task requirements

        Capability Matching Algorithm:
        - CPU cores: node must have >= required cores
        - Memory: node must have >= required memory (MB)
        - GPU: if task requires GPU, node must have GPU available
        - GPU memory: if GPU required, node must have >= required GPU memory
        - Storage: node must have >= required storage (MB)

        Args:
            task: Task entity with requirements
            node_capabilities: Node capability snapshot

        Raises:
            CapabilityMismatchError: If capabilities don't match
        """
        required = task.required_capabilities
        provided = node_capabilities

        # Validate CPU cores
        required_cpu = required.get("cpu_cores", 1)
        provided_cpu = provided.get("cpu_cores", 0)
        if provided_cpu < required_cpu:
            raise CapabilityMismatchError(
                f"Insufficient CPU cores: required {required_cpu}, provided {provided_cpu}",
                required_capabilities=required,
                provided_capabilities=provided
            )

        # Validate memory
        required_memory = required.get("memory_mb", 0)
        provided_memory = provided.get("memory_mb", 0)
        if provided_memory < required_memory:
            raise CapabilityMismatchError(
                f"Insufficient memory: required {required_memory}MB, provided {provided_memory}MB",
                required_capabilities=required,
                provided_capabilities=provided
            )

        # Validate GPU if required
        required_gpu = required.get("gpu_available", False)
        provided_gpu = provided.get("gpu_available", False)
        if required_gpu and not provided_gpu:
            raise CapabilityMismatchError(
                "GPU required but not available on node",
                required_capabilities=required,
                provided_capabilities=provided
            )

        # Validate GPU memory if GPU is required
        if required_gpu:
            required_gpu_memory = required.get("gpu_memory_mb", 0)
            provided_gpu_memory = provided.get("gpu_memory_mb", 0)
            if provided_gpu_memory < required_gpu_memory:
                raise CapabilityMismatchError(
                    f"Insufficient GPU memory: required {required_gpu_memory}MB, "
                    f"provided {provided_gpu_memory}MB",
                    required_capabilities=required,
                    provided_capabilities=provided
                )

        # Validate storage
        required_storage = required.get("storage_mb", 0)
        provided_storage = provided.get("storage_mb", 0)
        if provided_storage < required_storage:
            raise CapabilityMismatchError(
                f"Insufficient storage: required {required_storage}MB, provided {provided_storage}MB",
                required_capabilities=required,
                provided_capabilities=provided
            )

        logger.debug(
            f"Capability validation passed for task {task.id}",
            extra={
                "task_id": str(task.id),
                "required": required,
                "provided": provided
            }
        )

    def _calculate_expiration(
        self,
        complexity: str,
        issued_at: datetime
    ) -> datetime:
        """
        Calculate lease expiration based on task complexity

        Lease durations:
        - LOW complexity: 5 minutes
        - MEDIUM complexity: 10 minutes
        - HIGH complexity: 15 minutes

        Args:
            complexity: Task complexity level (string: "low", "medium", "high")
            issued_at: Lease issuance timestamp

        Returns:
            Expiration timestamp
        """
        duration_minutes = self.LEASE_DURATION_MAP.get(complexity.lower(), 10)
        return issued_at + timedelta(minutes=duration_minutes)

    def _generate_lease_token(
        self,
        task_id: str,
        peer_id: str,
        expires_at: datetime
    ) -> str:
        """
        Generate signed JWT lease token

        Token claims:
        - task_id: Task identifier (string UUID)
        - peer_id: Peer identifier
        - exp: Expiration timestamp (Unix epoch)
        - iat: Issued at timestamp (Unix epoch)

        Args:
            task_id: Task identifier (string)
            peer_id: Peer identifier
            expires_at: Token expiration timestamp

        Returns:
            Signed JWT token string
        """
        payload = {
            "task_id": task_id,
            "peer_id": peer_id,
            "exp": int(expires_at.timestamp()),
            "iat": int(datetime.now(timezone.utc).timestamp())
        }

        secret_key = self._get_secret_key()

        token = jwt.encode(
            payload,
            secret_key,
            algorithm="HS256"
        )

        return token

    def _get_secret_key(self) -> str:
        """
        Get JWT signing secret key from environment

        Returns:
            Secret key string

        Raises:
            LeaseIssuanceError: If secret key not configured
        """
        if self._secret_key:
            return self._secret_key

        secret_key = os.getenv("SECRET_KEY")
        if not secret_key:
            raise LeaseIssuanceError("SECRET_KEY environment variable not set")

        self._secret_key = secret_key
        return secret_key

    def verify_lease_token(self, token: str) -> Dict[str, Any]:
        """
        Verify and decode JWT lease token

        Args:
            token: JWT token string

        Returns:
            Decoded token payload

        Raises:
            jwt.InvalidTokenError: If token is invalid or expired
        """
        secret_key = self._get_secret_key()

        try:
            payload = jwt.decode(
                token,
                secret_key,
                algorithms=["HS256"]
            )
            return payload

        except jwt.ExpiredSignatureError:
            logger.warning("Lease token expired")
            raise

        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid lease token: {e}")
            raise

    async def revoke_lease(
        self,
        lease_id: int,
        reason: str
    ) -> None:
        """
        Revoke an active lease

        Args:
            lease_id: Lease identifier
            reason: Revocation reason

        Raises:
            LeaseIssuanceError: If lease not found
        """
        lease = self.db.query(TaskLease).filter(
            TaskLease.id == lease_id
        ).first()

        if not lease:
            raise LeaseIssuanceError(f"Lease {lease_id} not found")

        # Mark lease as expired by setting expires_at to now
        lease.expires_at = datetime.now(timezone.utc)

        # Update task status back to QUEUED
        task = self.db.query(Task).filter(Task.id == lease.task_id).first()
        if task:
            task.status = TaskStatus.QUEUED

        self.db.commit()

        logger.info(
            f"Lease revoked: {lease_id}, reason: {reason}",
            extra={"lease_id": str(lease_id), "reason": reason}
        )
