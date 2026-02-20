"""
Lease Expiration Detection Service.

Periodically scans for expired task leases and triggers recovery workflows.
Part of E5-S6: Lease Expiration Detection.

The service:
- Scans for expired leases every 10 seconds
- Implements a grace period (2-5s) to avoid race conditions
- Marks expired leases and revokes their tokens
- Triggers task requeue workflow for recoverable tasks
- Emits events for monitoring and observability
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.models.task_models import TaskLease, Task, TaskStatus


logger = logging.getLogger(__name__)


class LeaseExpirationService:
    """
    Service for detecting and processing expired task leases.

    This service runs as a background task, periodically scanning the database
    for expired leases and initiating recovery workflows.
    """

    def __init__(
        self,
        db_session: Session,
        scan_interval: int = 10,
        grace_period: int = 2,
        event_emitter: Optional[object] = None,
        requeue_service: Optional[object] = None
    ):
        """
        Initialize the lease expiration service.

        Args:
            db_session: SQLAlchemy database session
            scan_interval: Seconds between scans (default: 10s)
            grace_period: Seconds of grace period to avoid race conditions (default: 2s)
            event_emitter: Optional event emitter for publishing events
            requeue_service: Optional service for requeueing tasks
        """
        self.db_session = db_session
        self.scan_interval = scan_interval
        self.grace_period = grace_period
        self.event_emitter = event_emitter
        self.requeue_service = requeue_service
        self._running = False
        self._task: Optional[asyncio.Task] = None

        logger.info(
            f"LeaseExpirationService initialized with scan_interval={scan_interval}s, "
            f"grace_period={grace_period}s"
        )

    async def start(self) -> None:
        """
        Start the periodic lease expiration scanner.

        This method runs continuously until stop() is called.
        """
        self._running = True
        logger.info("Starting lease expiration scanner")

        while self._running:
            try:
                # Scan for expired leases
                expired_leases = await self.scan_expired_leases()

                if expired_leases:
                    logger.info(f"Found {len(expired_leases)} expired leases")
                    await self.process_expired_leases(expired_leases)

                # Wait for next scan interval
                await asyncio.sleep(self.scan_interval)

            except asyncio.CancelledError:
                logger.info("Lease expiration scanner cancelled")
                break
            except Exception as e:
                logger.error(f"Error in lease expiration scanner: {e}", exc_info=True)
                # Continue scanning despite errors
                await asyncio.sleep(self.scan_interval)

        logger.info("Lease expiration scanner stopped")

    def stop(self) -> None:
        """Stop the periodic scanner gracefully."""
        logger.info("Stopping lease expiration scanner")
        self._running = False

        if self._task and not self._task.done():
            self._task.cancel()

    async def scan_expired_leases(self) -> List[TaskLease]:
        """
        Scan database for expired leases outside grace period.

        The grace period prevents immediate requeue of leases that just expired,
        which could cause race conditions if the worker is about to submit results.

        Returns:
            List of expired TaskLease objects
        """
        try:
            # Calculate expiration threshold with grace period
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            expiration_threshold = now - timedelta(seconds=self.grace_period)

            # Query for active leases that expired before the threshold
            expired_leases = (
                self.db_session.query(TaskLease)
                .filter(TaskLease.expires_at < expiration_threshold)
                .all()
            )

            return expired_leases

        except Exception as e:
            logger.error(f"Error scanning for expired leases: {e}", exc_info=True)
            return []

    async def process_expired_leases(self, expired_leases: List[TaskLease]) -> None:
        """
        Process a batch of expired leases.

        Args:
            expired_leases: List of expired TaskLease objects
        """
        for lease in expired_leases:
            try:
                await self.handle_expired_lease(lease)
            except Exception as e:
                logger.error(
                    f"Error processing expired lease {lease.id} for task {lease.task_id}: {e}",
                    exc_info=True
                )
                # Continue with remaining leases

    async def handle_expired_lease(self, lease: TaskLease) -> None:
        """
        Handle a single expired lease.

        This method:
        1. Marks the lease as expired
        2. Revokes the lease token
        3. Emits a lease_expired event
        4. Triggers task requeue if applicable

        Args:
            lease: The expired TaskLease object
        """
        logger.info(
            f"Processing expired lease {lease.id} for task {lease.task_id} "
            f"(owner: {lease.owner_peer_id})"
        )

        # Mark lease as expired (delete from active leases)
        await self.mark_lease_expired(lease.id)

        # Emit lease expired event
        if self.event_emitter:
            try:
                await self.event_emitter.emit(
                    "lease_expired",
                    lease_id=lease.id,
                    task_id=lease.task_id,
                    owner_peer_id=lease.owner_peer_id,
                    expired_at=lease.expires_at,
                    detected_at=datetime.now(timezone.utc)
                )
            except Exception as e:
                logger.error(f"Error emitting lease_expired event: {e}")

        # Check if task should be requeued
        task = self.db_session.query(Task).filter(Task.task_id == lease.task_id).first()

        if task:
            # Always attempt to requeue - let the requeue service handle retry logic
            logger.info(f"Requeueing task {task.task_id}")

            if self.requeue_service:
                try:
                    await self.requeue_service.requeue_task(task.task_id)
                except Exception as e:
                    logger.error(f"Error requeueing task {task.task_id}: {e}")
            else:
                # If no requeue service, just update task status
                task.status = TaskStatus.QUEUED.value
                self.db_session.commit()

    async def mark_lease_expired(self, lease_id: int) -> None:
        """
        Mark a lease as expired by removing it from the database.

        Args:
            lease_id: ID of the lease to expire
        """
        try:
            lease = self.db_session.query(TaskLease).filter(TaskLease.id == lease_id).first()

            if lease:
                # Delete the expired lease
                self.db_session.delete(lease)
                self.db_session.commit()

                logger.debug(f"Deleted expired lease {lease_id}")
            else:
                logger.warning(f"Lease {lease_id} not found")

        except Exception as e:
            logger.error(f"Error marking lease {lease_id} as expired: {e}", exc_info=True)
            self.db_session.rollback()
            raise

    def get_expiration_stats(self) -> dict:
        """
        Get statistics about lease expirations.

        Returns:
            Dictionary with expiration statistics
        """
        try:
            active_leases = self.db_session.query(TaskLease).count()

            # Count active leases that will expire soon (within next scan interval)
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            upcoming_expirations = (
                self.db_session.query(TaskLease)
                .filter(TaskLease.expires_at < now + timedelta(seconds=self.scan_interval))
                .count()
            )

            return {
                "active_leases": active_leases,
                "upcoming_expirations": upcoming_expirations,
                "scan_interval": self.scan_interval,
                "grace_period": self.grace_period
            }

        except Exception as e:
            logger.error(f"Error getting expiration stats: {e}", exc_info=True)
            return {}
