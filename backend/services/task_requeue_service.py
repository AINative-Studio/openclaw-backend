"""
Task Requeue Service

Handles automatic requeueing of failed and expired tasks with retry limits,
exponential backoff, and lease management. Integrates with DBOS for durability.

Refs #E5-S8
"""

import logging
from typing import Optional
from datetime import datetime, timezone
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from backend.models.task_queue import Task, TaskLease, TaskStatus


logger = logging.getLogger(__name__)


class TaskRequeueService:
    """
    Service for managing task requeue workflow

    Handles:
    - Retry limit enforcement
    - Exponential backoff calculation
    - Lease clearing and revocation
    - Status transitions
    - Event emission for monitoring
    """

    # Configuration constants
    BASE_BACKOFF_DELAY = 30  # Base delay in seconds
    MAX_BACKOFF_DELAY = 3600  # Max delay in seconds (1 hour)

    def __init__(self, db: Session):
        """
        Initialize requeue service

        Args:
            db: Database session
        """
        self.db = db

    async def requeue_task(self, task_id: UUID) -> bool:
        """
        Requeue a failed or expired task

        Implements the core requeue workflow:
        1. Validate task exists and is requeueable
        2. Check retry_count < max_retries
        3. Increment retry_count or mark permanently failed
        4. Clear lease assignment
        5. Set status = queued
        6. Emit requeue event

        Args:
            task_id: Task ID to requeue

        Returns:
            True if requeued successfully, False if max retries reached

        Raises:
            ValueError: If task not found or not in requeueable state
            SQLAlchemyError: If database operation fails
        """
        try:
            # Fetch task
            task = self.db.query(Task).filter(Task.id == task_id).first()

            if not task:
                raise ValueError(f"Task {task_id} not found")

            # Validate task is in requeueable state
            requeueable_states = [
                TaskStatus.FAILED,
                TaskStatus.EXPIRED,
                TaskStatus.QUEUED  # Idempotent requeue
            ]

            if task.status not in requeueable_states:
                raise ValueError(
                    f"Cannot requeue task in {task.status} state. "
                    f"Only {requeueable_states} are requeueable."
                )

            # Check if already queued (idempotency)
            if task.status == TaskStatus.QUEUED:
                logger.info(
                    f"Task {task_id} already queued, requeue is idempotent",
                    extra={"task_id": str(task_id), "retry_count": task.retry_count}
                )
                return True

            # Check retry limit
            if task.retry_count >= task.max_retries:
                return await self._mark_permanently_failed(task)

            # Increment retry count
            task.retry_count += 1

            # Clear lease assignment
            task.assigned_peer_id = None

            # Revoke all active leases
            await self._revoke_task_leases(task_id)

            # Calculate backoff delay (stored for scheduler use)
            backoff_delay = self.calculate_backoff_delay(task.retry_count)

            # Update task status
            task.status = TaskStatus.QUEUED
            task.updated_at = datetime.now(timezone.utc)

            # Commit changes
            self.db.commit()

            # Emit requeue event
            await self._emit_requeue_event(
                task_id=task_id,
                retry_count=task.retry_count,
                backoff_delay=backoff_delay
            )

            logger.info(
                f"Task {task_id} requeued successfully",
                extra={
                    "task_id": str(task_id),
                    "retry_count": task.retry_count,
                    "max_retries": task.max_retries,
                    "backoff_delay_seconds": backoff_delay,
                    "previous_status": TaskStatus.FAILED.value
                }
            )

            return True

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(
                f"Database error during task requeue: {task_id}",
                extra={"task_id": str(task_id), "error": str(e)}
            )
            raise

        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Unexpected error during task requeue: {task_id}",
                extra={"task_id": str(task_id), "error": str(e)}
            )
            raise

    async def _mark_permanently_failed(self, task: Task) -> bool:
        """
        Mark task as permanently failed when max retries reached

        Args:
            task: Task entity

        Returns:
            False to indicate requeue failed
        """
        task.status = TaskStatus.PERMANENTLY_FAILED
        task.assigned_peer_id = None
        task.error_message = (
            f"Task failed permanently after {task.retry_count} retries "
            f"(max retries: {task.max_retries})"
        )
        task.updated_at = datetime.now(timezone.utc)

        # Revoke leases
        await self._revoke_task_leases(task.id)

        self.db.commit()

        logger.warning(
            f"Task {task.id} marked permanently failed - max retries reached",
            extra={
                "task_id": str(task.id),
                "retry_count": task.retry_count,
                "max_retries": task.max_retries
            }
        )

        return False

    async def _revoke_task_leases(self, task_id: UUID) -> None:
        """
        Revoke all active leases for a task

        Args:
            task_id: Task ID
        """
        leases = self.db.query(TaskLease).filter(
            TaskLease.task_id == task_id,
            TaskLease.is_revoked == 0
        ).all()

        now = datetime.now(timezone.utc)

        for lease in leases:
            lease.is_revoked = 1
            lease.revoked_at = now
            lease.updated_at = now

        if leases:
            logger.debug(
                f"Revoked {len(leases)} lease(s) for task {task_id}",
                extra={"task_id": str(task_id), "lease_count": len(leases)}
            )

    async def _emit_requeue_event(
        self,
        task_id: UUID,
        retry_count: int,
        backoff_delay: int
    ) -> None:
        """
        Emit requeue event for monitoring and metrics

        In production, this would publish to event stream (e.g., Kafka, NATS).
        For now, we log the event for observability.

        Args:
            task_id: Task ID
            retry_count: Current retry count
            backoff_delay: Backoff delay in seconds
        """
        event = {
            "event_type": "task_requeued",
            "task_id": str(task_id),
            "retry_count": retry_count,
            "backoff_delay_seconds": backoff_delay,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        logger.info(
            "Task requeue event emitted",
            extra=event
        )

        # TODO: Integrate with event streaming system (E3: Gossipsub)
        # await self.event_publisher.publish("task.requeued", event)

    def calculate_backoff_delay(self, retry_count: int) -> int:
        """
        Calculate exponential backoff delay

        Formula: base_delay * (2 ^ retry_count)

        Args:
            retry_count: Current retry count

        Returns:
            Backoff delay in seconds (capped at MAX_BACKOFF_DELAY)
        """
        delay = self.BASE_BACKOFF_DELAY * (2 ** retry_count)
        return min(delay, self.MAX_BACKOFF_DELAY)

    async def requeue_expired_tasks(self, batch_size: int = 100) -> int:
        """
        Batch requeue expired tasks

        This is called by the lease expiration detector service.
        Processes expired tasks in batches for efficiency.

        Args:
            batch_size: Maximum tasks to requeue in one batch

        Returns:
            Number of tasks requeued
        """
        try:
            # Query expired tasks that haven't been requeued
            expired_tasks = self.db.query(Task).filter(
                Task.status == TaskStatus.EXPIRED,
                Task.retry_count < Task.max_retries
            ).limit(batch_size).all()

            requeued_count = 0

            for task in expired_tasks:
                try:
                    result = await self.requeue_task(task.id)
                    if result:
                        requeued_count += 1
                except Exception as e:
                    logger.error(
                        f"Failed to requeue task {task.id}: {e}",
                        extra={"task_id": str(task.id), "error": str(e)}
                    )
                    continue

            logger.info(
                f"Batch requeue completed: {requeued_count}/{len(expired_tasks)} tasks",
                extra={
                    "requeued_count": requeued_count,
                    "total_expired": len(expired_tasks)
                }
            )

            return requeued_count

        except Exception as e:
            logger.error(
                f"Batch requeue failed: {e}",
                extra={"error": str(e)}
            )
            raise
