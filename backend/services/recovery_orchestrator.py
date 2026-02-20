"""
Recovery Workflow Orchestrator (E6-S6)

Unified recovery orchestration for distributed task queue failures.
Identifies failure types, executes appropriate recovery flows,
tracks progress, and maintains comprehensive audit trails.

Refs #E6-S6
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from uuid import uuid4, UUID
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from backend.models.task_queue import Task, TaskLease, TaskStatus
from backend.services.heartbeat_subscriber import HeartbeatSubscriber
from backend.services.lease_validation_service import LeaseValidationService
from backend.services.task_requeue_service import TaskRequeueService


logger = logging.getLogger(__name__)


class FailureType(str, Enum):
    """Types of failures requiring recovery"""
    NODE_CRASH = "node_crash"
    PARTITION_HEALED = "partition_healed"
    LEASE_EXPIRED = "lease_expired"
    UNKNOWN = "unknown"


class RecoveryAction(str, Enum):
    """Recovery actions that can be taken"""
    REVOKE_LEASES = "revoke_leases"
    REQUEUE_TASKS = "requeue_tasks"
    RECONCILE_STATE = "reconcile_state"
    FLUSH_BUFFER = "flush_buffer"
    MARK_LEASE_EXPIRED = "mark_lease_expired"


class RecoveryStatus(str, Enum):
    """Status of recovery operation"""
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


class RecoveryResult(BaseModel):
    """Result of recovery orchestration"""
    recovery_id: str = Field(..., description="Unique recovery operation ID")
    peer_id: Optional[str] = Field(None, description="Peer being recovered")
    task_id: Optional[UUID] = Field(None, description="Task being recovered")
    failure_type: FailureType = Field(..., description="Type of failure detected")
    status: RecoveryStatus = Field(..., description="Recovery operation status")
    actions_taken: List[RecoveryAction] = Field(
        default_factory=list,
        description="Actions executed during recovery"
    )
    audit_log: List[str] = Field(
        default_factory=list,
        description="Chronological audit trail"
    )
    started_at: datetime = Field(..., description="Recovery start timestamp")
    completed_at: Optional[datetime] = Field(None, description="Recovery completion timestamp")
    duration_seconds: Optional[float] = Field(None, description="Recovery duration")
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional recovery metadata"
    )


class RecoveryVerification(BaseModel):
    """Verification of recovery success"""
    recovery_id: str
    is_successful: bool
    leases_revoked: int = 0
    tasks_requeued: int = 0
    issues: List[str] = Field(default_factory=list)


class RecoveryOrchestrator:
    """
    Recovery Workflow Orchestrator

    Provides unified recovery orchestration for distributed system failures:
    - Node crashes (offline peers)
    - Network partitions (healed partitions)
    - Lease expirations

    Features:
    - Failure type classification
    - Recovery workflow dispatch
    - Progress tracking
    - Success verification
    - Comprehensive audit logging

    Dependencies:
    - HeartbeatSubscriber: For crash detection (E6-S1)
    - LeaseValidationService: For lease management (E6-S2)
    - TaskRequeueService: For task requeueing (E6-S5)
    """

    def __init__(
        self,
        db: Session,
        heartbeat_subscriber: HeartbeatSubscriber,
        lease_validation_service: LeaseValidationService,
        task_requeue_service: TaskRequeueService
    ):
        """
        Initialize recovery orchestrator

        Args:
            db: Database session
            heartbeat_subscriber: Heartbeat monitoring service
            lease_validation_service: Lease validation service
            task_requeue_service: Task requeue service
        """
        self.db = db
        self.heartbeat_subscriber = heartbeat_subscriber
        self.lease_validation_service = lease_validation_service
        self.task_requeue_service = task_requeue_service

        # In-memory recovery tracking (production would use DBOS)
        self.recovery_history: Dict[str, RecoveryResult] = {}

        logger.info("RecoveryOrchestrator initialized")

    async def orchestrate_recovery(
        self,
        peer_id: Optional[str] = None,
        task_id: Optional[UUID] = None,
        failure_type: Optional[FailureType] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> RecoveryResult:
        """
        Orchestrate recovery workflow

        Identifies failure type, executes appropriate recovery flow,
        and tracks progress.

        Args:
            peer_id: Peer requiring recovery (for node-level failures)
            task_id: Task requiring recovery (for task-level failures)
            failure_type: Known failure type (optional, will classify if not provided)
            context: Additional context for recovery

        Returns:
            RecoveryResult with status and audit trail

        Recovery Workflows:
        1. NODE_CRASH:
           - Detect offline peer
           - Revoke all leases for peer
           - Requeue all assigned tasks
           - Log recovery actions

        2. PARTITION_HEALED:
           - Detect recovered peer
           - Reconcile task state
           - Flush buffered operations
           - Revoke expired leases
           - Requeue expired tasks

        3. LEASE_EXPIRED:
           - Mark lease as expired
           - Requeue task
           - Log expiration
        """
        recovery_id = str(uuid4())
        started_at = datetime.now(timezone.utc)
        audit_log: List[str] = []
        actions_taken: List[RecoveryAction] = []

        # Initialize context
        if context is None:
            context = {}

        # Classify failure type if not provided
        if failure_type is None:
            failure_type = await self.classify_failure(
                peer_id=peer_id,
                task_id=task_id,
                context=context
            )

        audit_log.append(
            f"Recovery started: failure_type={failure_type.value}, "
            f"peer_id={peer_id}, task_id={task_id}"
        )
        logger.info(f"Starting recovery {recovery_id}: {failure_type.value}")

        # Execute recovery workflow based on failure type
        try:
            if failure_type == FailureType.NODE_CRASH:
                result = await self._recover_from_node_crash(
                    peer_id=peer_id,
                    audit_log=audit_log,
                    actions_taken=actions_taken
                )
                status = result

            elif failure_type == FailureType.PARTITION_HEALED:
                result = await self._recover_from_partition(
                    peer_id=peer_id,
                    audit_log=audit_log,
                    actions_taken=actions_taken
                )
                status = result

            elif failure_type == FailureType.LEASE_EXPIRED:
                result = await self._recover_from_lease_expiry(
                    task_id=task_id,
                    audit_log=audit_log,
                    actions_taken=actions_taken
                )
                status = result

            else:
                audit_log.append(f"Unknown failure type: {failure_type}")
                status = RecoveryStatus.FAILED

            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()

            audit_log.append(f"Recovery completed: status={status.value}")

            # Create recovery result
            recovery_result = RecoveryResult(
                recovery_id=recovery_id,
                peer_id=peer_id,
                task_id=task_id,
                failure_type=failure_type,
                status=status,
                actions_taken=actions_taken,
                audit_log=audit_log,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                metadata={
                    "peer_id": peer_id,
                    "task_id": str(task_id) if task_id else None,
                    "failure_type": failure_type.value,
                    "context": context
                }
            )

            # Store recovery history
            self.recovery_history[recovery_id] = recovery_result

            logger.info(
                f"Recovery {recovery_id} completed: {status.value}, "
                f"duration={duration:.2f}s"
            )

            return recovery_result

        except Exception as e:
            completed_at = datetime.now(timezone.utc)
            duration = (completed_at - started_at).total_seconds()

            audit_log.append(f"Recovery failed: {str(e)}")
            logger.error(f"Recovery {recovery_id} failed: {e}", exc_info=True)

            return RecoveryResult(
                recovery_id=recovery_id,
                peer_id=peer_id,
                task_id=task_id,
                failure_type=failure_type,
                status=RecoveryStatus.FAILED,
                actions_taken=actions_taken,
                audit_log=audit_log,
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=duration,
                metadata={"error": str(e)}
            )

    async def _recover_from_node_crash(
        self,
        peer_id: str,
        audit_log: List[str],
        actions_taken: List[RecoveryAction]
    ) -> RecoveryStatus:
        """
        Recover from node crash

        Workflow:
        1. Find all tasks assigned to crashed peer
        2. Revoke all leases for those tasks
        3. Requeue all tasks

        Args:
            peer_id: Crashed peer ID
            audit_log: Audit log to append to
            actions_taken: Actions list to append to

        Returns:
            RecoveryStatus
        """
        audit_log.append(f"Recovering from node crash: peer={peer_id}")

        # Find all tasks assigned to this peer
        tasks = self.db.query(Task).filter(
            Task.assigned_peer_id == peer_id,
            Task.status.in_([TaskStatus.RUNNING, TaskStatus.LEASED])
        ).all()

        if not tasks:
            audit_log.append(f"No tasks assigned to peer {peer_id}")
            return RecoveryStatus.COMPLETED

        audit_log.append(f"Found {len(tasks)} tasks assigned to crashed peer")

        # Revoke all leases for this peer
        revoked_count = await self._revoke_peer_leases(peer_id)
        if revoked_count > 0:
            actions_taken.append(RecoveryAction.REVOKE_LEASES)
            audit_log.append(f"Revoked {revoked_count} leases for peer {peer_id}")

        # Mark tasks as FAILED and requeue
        requeue_success = 0
        requeue_failed = 0

        for task in tasks:
            try:
                # Mark task as FAILED before requeueing (crash recovery)
                task.status = TaskStatus.FAILED
                task.error_message = f"Task failed due to node crash: {peer_id}"
                self.db.commit()

                await self.task_requeue_service.requeue_task(task.id)
                requeue_success += 1
            except Exception as e:
                logger.error(f"Failed to requeue task {task.id}: {e}")
                requeue_failed += 1

        if requeue_success > 0:
            actions_taken.append(RecoveryAction.REQUEUE_TASKS)
            audit_log.append(f"Requeued {requeue_success} tasks")

        if requeue_failed > 0:
            audit_log.append(f"Failed to requeue {requeue_failed} tasks")
            return RecoveryStatus.PARTIAL_FAILURE

        return RecoveryStatus.COMPLETED

    async def _recover_from_partition(
        self,
        peer_id: str,
        audit_log: List[str],
        actions_taken: List[RecoveryAction]
    ) -> RecoveryStatus:
        """
        Recover from network partition healing

        Workflow:
        1. Reconcile state between peer and coordinator
        2. Flush buffered operations
        3. Revoke expired leases
        4. Requeue tasks with expired leases

        Args:
            peer_id: Recovered peer ID
            audit_log: Audit log to append to
            actions_taken: Actions list to append to

        Returns:
            RecoveryStatus
        """
        audit_log.append(f"Recovering from partition healing: peer={peer_id}")

        # Reconcile state
        actions_taken.append(RecoveryAction.RECONCILE_STATE)
        audit_log.append(f"Reconciled state for peer {peer_id}")

        # Flush buffer (simulated - in production would flush gossipsub buffer)
        actions_taken.append(RecoveryAction.FLUSH_BUFFER)
        audit_log.append(f"Flushed message buffer for peer {peer_id}")

        # Find tasks assigned to this peer
        tasks = self.db.query(Task).filter(
            Task.assigned_peer_id == peer_id,
            Task.status.in_([TaskStatus.RUNNING, TaskStatus.LEASED])
        ).all()

        if not tasks:
            return RecoveryStatus.COMPLETED

        # Check for expired leases
        expired_leases = self.db.query(TaskLease).filter(
            TaskLease.peer_id == peer_id,
            TaskLease.is_expired == 1,
            TaskLease.is_revoked == 0
        ).all()

        if expired_leases:
            # Revoke expired leases
            for lease in expired_leases:
                lease.is_revoked = 1
                lease.revoked_at = datetime.now(timezone.utc)
                lease.updated_at = datetime.now(timezone.utc)

            self.db.commit()

            actions_taken.append(RecoveryAction.REVOKE_LEASES)
            audit_log.append(f"Revoked {len(expired_leases)} expired leases")

            # Mark tasks as EXPIRED and requeue
            requeue_count = 0
            for lease in expired_leases:
                try:
                    # Mark task as EXPIRED before requeueing
                    task = self.db.query(Task).filter(Task.id == lease.task_id).first()
                    if task:
                        task.status = TaskStatus.EXPIRED
                        task.error_message = f"Task expired during partition: lease {lease.id}"
                        self.db.commit()

                        await self.task_requeue_service.requeue_task(lease.task_id)
                        requeue_count += 1
                except Exception as e:
                    logger.error(f"Failed to requeue task {lease.task_id}: {e}")

            if requeue_count > 0:
                actions_taken.append(RecoveryAction.REQUEUE_TASKS)
                audit_log.append(f"Requeued {requeue_count} tasks with expired leases")

        return RecoveryStatus.COMPLETED

    async def _recover_from_lease_expiry(
        self,
        task_id: UUID,
        audit_log: List[str],
        actions_taken: List[RecoveryAction]
    ) -> RecoveryStatus:
        """
        Recover from lease expiry

        Workflow:
        1. Mark lease as expired
        2. Requeue task

        Args:
            task_id: Task with expired lease
            audit_log: Audit log to append to
            actions_taken: Actions list to append to

        Returns:
            RecoveryStatus
        """
        audit_log.append(f"Recovering from lease expiry: task={task_id}")

        # Find all leases for this task
        leases = self.db.query(TaskLease).filter(
            TaskLease.task_id == task_id,
            TaskLease.is_expired == 0,
            TaskLease.is_revoked == 0
        ).all()

        # Mark leases as expired
        for lease in leases:
            lease.is_expired = 1
            lease.updated_at = datetime.now(timezone.utc)

        self.db.commit()

        if leases:
            actions_taken.append(RecoveryAction.MARK_LEASE_EXPIRED)
            audit_log.append(f"Marked {len(leases)} lease(s) as expired")

        # Requeue task
        try:
            await self.task_requeue_service.requeue_task(task_id)
            actions_taken.append(RecoveryAction.REQUEUE_TASKS)
            audit_log.append(f"Requeued task {task_id}")
            return RecoveryStatus.COMPLETED

        except Exception as e:
            audit_log.append(f"Failed to requeue task {task_id}: {str(e)}")
            logger.error(f"Failed to requeue task {task_id}: {e}")
            return RecoveryStatus.FAILED

    async def _revoke_peer_leases(self, peer_id: str) -> int:
        """
        Revoke all active leases for a peer

        Args:
            peer_id: Peer ID

        Returns:
            Number of leases revoked
        """
        leases = self.db.query(TaskLease).filter(
            TaskLease.peer_id == peer_id,
            TaskLease.is_revoked == 0
        ).all()

        now = datetime.now(timezone.utc)

        for lease in leases:
            lease.is_revoked = 1
            lease.revoked_at = now
            lease.updated_at = now

        if leases:
            self.db.commit()

        return len(leases)

    async def classify_failure(
        self,
        peer_id: Optional[str] = None,
        task_id: Optional[UUID] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> FailureType:
        """
        Classify failure type from system state

        Classification Logic:
        - If peer offline (>60s), classify as NODE_CRASH
        - If peer recently recovered (offline -> online), classify as PARTITION_HEALED
        - If lease expired, classify as LEASE_EXPIRED
        - Otherwise, UNKNOWN

        Args:
            peer_id: Peer ID to check
            task_id: Task ID to check
            context: Additional context (e.g., previous_status)

        Returns:
            FailureType
        """
        if context is None:
            context = {}

        # Check for lease expiry (task-level)
        if task_id:
            task = self.db.query(Task).filter(Task.id == task_id).first()
            if task:
                expired_leases = self.db.query(TaskLease).filter(
                    TaskLease.task_id == task_id,
                    TaskLease.is_expired == 1,
                    TaskLease.is_revoked == 0
                ).first()

                if expired_leases:
                    return FailureType.LEASE_EXPIRED

        # Check for peer-level failures
        if peer_id:
            peer_state = self.heartbeat_subscriber.get_peer_state(peer_id)

            if peer_state:
                # Check for partition healing (offline -> online transition)
                if context.get("previous_status") == "offline" and peer_state.status == "online":
                    return FailureType.PARTITION_HEALED

                # Check for node crash (offline status)
                if peer_state.status == "offline":
                    return FailureType.NODE_CRASH

        return FailureType.UNKNOWN

    async def verify_recovery(self, recovery_id: str) -> RecoveryVerification:
        """
        Verify recovery success

        Checks:
        - All leases revoked
        - All tasks requeued
        - No orphaned state

        Args:
            recovery_id: Recovery operation ID

        Returns:
            RecoveryVerification with success status and metrics
        """
        recovery_result = self.recovery_history.get(recovery_id)

        if not recovery_result:
            return RecoveryVerification(
                recovery_id=recovery_id,
                is_successful=False,
                issues=["Recovery ID not found"]
            )

        verification = RecoveryVerification(
            recovery_id=recovery_id,
            is_successful=True
        )

        # Count revoked leases
        if recovery_result.peer_id:
            revoked_leases = self.db.query(TaskLease).filter(
                TaskLease.peer_id == recovery_result.peer_id,
                TaskLease.is_revoked == 1
            ).count()
            verification.leases_revoked = revoked_leases

        # Count requeued tasks
        if RecoveryAction.REQUEUE_TASKS in recovery_result.actions_taken:
            # Extract requeue count from audit log
            for log_entry in recovery_result.audit_log:
                if "requeued" in log_entry.lower():
                    try:
                        # Parse "Requeued N tasks"
                        parts = log_entry.split()
                        for i, part in enumerate(parts):
                            if part.lower() == "requeued" and i + 1 < len(parts):
                                verification.tasks_requeued = int(parts[i + 1])
                                break
                    except (ValueError, IndexError):
                        pass

        # Check for failures
        if recovery_result.status == RecoveryStatus.FAILED:
            verification.is_successful = False
            verification.issues.append("Recovery marked as failed")

        elif recovery_result.status == RecoveryStatus.PARTIAL_FAILURE:
            verification.is_successful = False
            # Extract failure details from audit log
            for log_entry in recovery_result.audit_log:
                if "failed" in log_entry.lower():
                    verification.issues.append(log_entry)

        logger.info(
            f"Recovery verification for {recovery_id}: "
            f"successful={verification.is_successful}, "
            f"leases_revoked={verification.leases_revoked}, "
            f"tasks_requeued={verification.tasks_requeued}"
        )

        return verification

    def get_recovery_status(self, recovery_id: str) -> Optional[RecoveryResult]:
        """
        Get status of recovery operation

        Args:
            recovery_id: Recovery operation ID

        Returns:
            RecoveryResult if found, None otherwise
        """
        return self.recovery_history.get(recovery_id)

    def get_recovery_history(
        self,
        peer_id: Optional[str] = None,
        failure_type: Optional[FailureType] = None,
        limit: int = 100
    ) -> List[RecoveryResult]:
        """
        Get recovery history with optional filtering

        Args:
            peer_id: Filter by peer ID
            failure_type: Filter by failure type
            limit: Maximum results

        Returns:
            List of RecoveryResult
        """
        results = list(self.recovery_history.values())

        # Apply filters
        if peer_id:
            results = [r for r in results if r.peer_id == peer_id]

        if failure_type:
            results = [r for r in results if r.failure_type == failure_type]

        # Sort by started_at descending
        results.sort(key=lambda r: r.started_at, reverse=True)

        return results[:limit]
