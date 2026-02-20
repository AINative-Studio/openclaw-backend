"""
Lease Revocation Service

Handles automatic revocation of task leases when nodes crash or go offline.
Integrates with crash detection system and task requeue workflows.

Features:
- Batch lease revocation for crashed nodes
- Task status updates (LEASED -> EXPIRED)
- Audit logging with revocation reasons
- Optional automatic requeueing
- Idempotent operations

Refs #E6-S2
"""

import logging
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import and_

from backend.models.task_queue import Task, TaskLease, TaskStatus


logger = logging.getLogger(__name__)


class LeaseRevocationService:
    """
    Service for revoking task leases when nodes crash

    Handles:
    - Querying leases by crashed node peer_id
    - Batch revocation with configurable batch sizes
    - Task status transitions (LEASED -> EXPIRED)
    - Audit logging with structured metadata
    - Integration with task requeue service
    - Idempotent revocation operations
    """

    # Configuration constants
    DEFAULT_BATCH_SIZE = 100

    def __init__(self, db: Session):
        """
        Initialize lease revocation service

        Args:
            db: Database session
        """
        self.db = db

    async def revoke_leases_on_crash(
        self,
        crashed_peer_id: str,
        reason: str,
        requeue: bool = False,
        batch_size: int = DEFAULT_BATCH_SIZE
    ) -> Dict[str, Any]:
        """
        Revoke all active leases for a crashed node

        This is the main entry point called by the crash detection system
        when a node is detected as offline or crashed.

        Workflow:
        1. Validate peer_id
        2. Query all active leases for peer (WHERE owner_peer_id = crashed_node)
        3. Mark leases as revoked (batch processing)
        4. Update tasks to expired status
        5. Optionally trigger requeue workflows
        6. Emit audit log events

        Args:
            crashed_peer_id: Peer ID of crashed node
            reason: Reason for revocation (e.g., "node_offline", "heartbeat_timeout")
            requeue: Whether to automatically requeue tasks (default: False)
            batch_size: Maximum leases to process in one batch

        Returns:
            Dict with revocation results:
            {
                "success": bool,
                "revoked_count": int,
                "requeued_count": int (if requeue=True),
                "peer_id": str,
                "reason": str,
                "timestamp": str
            }

        Raises:
            ValueError: If peer_id is empty or invalid
            SQLAlchemyError: If database operation fails
        """
        # Validate input
        if not crashed_peer_id or not crashed_peer_id.strip():
            raise ValueError("peer_id cannot be empty")

        try:
            # Query active leases for crashed peer
            # Active means: is_revoked = 0 (not yet revoked)
            active_leases = self.db.query(TaskLease).filter(
                and_(
                    TaskLease.peer_id == crashed_peer_id,
                    TaskLease.is_revoked == 0
                )
            ).all()

            revoked_count = 0
            requeued_count = 0
            now = datetime.now(timezone.utc)

            # Process leases in batches for large-scale crashes
            for i in range(0, len(active_leases), batch_size):
                batch = active_leases[i:i + batch_size]

                for lease in batch:
                    # Mark lease as revoked
                    lease.is_revoked = 1
                    lease.revoked_at = now
                    lease.updated_at = now

                    # Update associated task
                    task = self.db.query(Task).filter(
                        Task.id == lease.task_id
                    ).first()

                    if task:
                        # Update task status to EXPIRED
                        task.status = TaskStatus.EXPIRED
                        task.assigned_peer_id = None
                        task.updated_at = now

                        # If requeue enabled, increment retry count
                        if requeue and task.retry_count < task.max_retries:
                            task.retry_count += 1
                            task.status = TaskStatus.QUEUED
                            requeued_count += 1

                    revoked_count += 1

                # Commit batch
                self.db.commit()

                logger.debug(
                    f"Processed batch {i // batch_size + 1}: "
                    f"revoked {len(batch)} leases for peer {crashed_peer_id}"
                )

            # Emit audit log
            result = {
                "success": True,
                "revoked_count": revoked_count,
                "peer_id": crashed_peer_id,
                "reason": reason,
                "timestamp": now.isoformat()
            }

            if requeue:
                result["requeued_count"] = requeued_count

            await self._emit_revocation_audit_log(
                peer_id=crashed_peer_id,
                revoked_count=revoked_count,
                reason=reason,
                requeued_count=requeued_count if requeue else None
            )

            logger.info(
                f"Revoked {revoked_count} lease(s) for crashed peer {crashed_peer_id}",
                extra={
                    "peer_id": crashed_peer_id,
                    "revoked_count": revoked_count,
                    "requeued_count": requeued_count if requeue else 0,
                    "reason": reason
                }
            )

            return result

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(
                f"Database error during lease revocation for peer {crashed_peer_id}",
                extra={"peer_id": crashed_peer_id, "error": str(e)}
            )
            raise

        except Exception as e:
            self.db.rollback()
            logger.error(
                f"Unexpected error during lease revocation for peer {crashed_peer_id}",
                extra={"peer_id": crashed_peer_id, "error": str(e)}
            )
            raise

    async def revoke_lease_by_token(
        self,
        lease_token: str,
        reason: str = "manual_revocation"
    ) -> bool:
        """
        Revoke a specific lease by token

        Useful for manual intervention or targeted revocation.

        Args:
            lease_token: Unique lease token
            reason: Reason for revocation

        Returns:
            True if lease was revoked, False if not found or already revoked

        Raises:
            SQLAlchemyError: If database operation fails
        """
        try:
            lease = self.db.query(TaskLease).filter(
                and_(
                    TaskLease.lease_token == lease_token,
                    TaskLease.is_revoked == 0
                )
            ).first()

            if not lease:
                logger.warning(
                    f"Lease not found or already revoked: {lease_token}",
                    extra={"lease_token": lease_token}
                )
                return False

            now = datetime.now(timezone.utc)

            # Mark lease as revoked
            lease.is_revoked = 1
            lease.revoked_at = now
            lease.updated_at = now

            # Update task status
            task = self.db.query(Task).filter(
                Task.id == lease.task_id
            ).first()

            if task:
                task.status = TaskStatus.EXPIRED
                task.assigned_peer_id = None
                task.updated_at = now

            self.db.commit()

            logger.info(
                f"Revoked lease {lease_token}",
                extra={
                    "lease_token": lease_token,
                    "task_id": str(lease.task_id),
                    "peer_id": lease.peer_id,
                    "reason": reason
                }
            )

            return True

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(
                f"Database error during lease revocation by token: {lease_token}",
                extra={"lease_token": lease_token, "error": str(e)}
            )
            raise

    async def get_active_leases_for_peer(
        self,
        peer_id: str
    ) -> List[TaskLease]:
        """
        Get all active (non-revoked) leases for a peer

        Useful for health checks and monitoring.

        Args:
            peer_id: Peer identifier

        Returns:
            List of active TaskLease objects
        """
        try:
            active_leases = self.db.query(TaskLease).filter(
                and_(
                    TaskLease.peer_id == peer_id,
                    TaskLease.is_revoked == 0
                )
            ).all()

            logger.debug(
                f"Found {len(active_leases)} active lease(s) for peer {peer_id}",
                extra={"peer_id": peer_id, "active_lease_count": len(active_leases)}
            )

            return active_leases

        except SQLAlchemyError as e:
            logger.error(
                f"Database error querying active leases for peer {peer_id}",
                extra={"peer_id": peer_id, "error": str(e)}
            )
            raise

    async def revoke_expired_leases(
        self,
        batch_size: int = DEFAULT_BATCH_SIZE
    ) -> int:
        """
        Revoke leases that have passed their expiration time

        This is called by a background scheduler to clean up expired leases.
        Different from crash revocation - this handles natural expiration.

        Args:
            batch_size: Maximum leases to process in one batch

        Returns:
            Number of leases revoked
        """
        try:
            now = datetime.now(timezone.utc)

            # Query expired but not yet revoked leases
            expired_leases = self.db.query(TaskLease).filter(
                and_(
                    TaskLease.expires_at <= now,
                    TaskLease.is_revoked == 0
                )
            ).limit(batch_size).all()

            revoked_count = 0

            for lease in expired_leases:
                lease.is_revoked = 1
                lease.revoked_at = now
                lease.updated_at = now
                lease.is_expired = 1

                # Update task status
                task = self.db.query(Task).filter(
                    Task.id == lease.task_id
                ).first()

                if task and task.status == TaskStatus.LEASED:
                    task.status = TaskStatus.EXPIRED
                    task.assigned_peer_id = None
                    task.updated_at = now

                revoked_count += 1

            self.db.commit()

            if revoked_count > 0:
                logger.info(
                    f"Revoked {revoked_count} expired lease(s)",
                    extra={"revoked_count": revoked_count}
                )

            return revoked_count

        except SQLAlchemyError as e:
            self.db.rollback()
            logger.error(
                f"Database error during expired lease revocation",
                extra={"error": str(e)}
            )
            raise

    async def _emit_revocation_audit_log(
        self,
        peer_id: str,
        revoked_count: int,
        reason: str,
        requeued_count: Optional[int] = None
    ) -> None:
        """
        Emit audit log event for lease revocation

        In production, this would publish to audit log system (e.g., structured logs,
        event stream, or dedicated audit table).

        Args:
            peer_id: Crashed peer ID
            revoked_count: Number of leases revoked
            reason: Revocation reason
            requeued_count: Number of tasks requeued (optional)
        """
        audit_event = {
            "event_type": "lease_revocation",
            "peer_id": peer_id,
            "revoked_count": revoked_count,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if requeued_count is not None:
            audit_event["requeued_count"] = requeued_count

        logger.info(
            "Lease revocation audit event",
            extra=audit_event
        )

        # TODO: Integrate with audit logging system
        # await self.audit_logger.log_event(audit_event)

    async def get_revocation_stats(self) -> Dict[str, Any]:
        """
        Get statistics about lease revocations

        Useful for monitoring and dashboards.

        Returns:
            Dict with revocation statistics
        """
        try:
            total_leases = self.db.query(TaskLease).count()
            revoked_leases = self.db.query(TaskLease).filter(
                TaskLease.is_revoked == 1
            ).count()
            active_leases = self.db.query(TaskLease).filter(
                TaskLease.is_revoked == 0
            ).count()

            stats = {
                "total_leases": total_leases,
                "revoked_leases": revoked_leases,
                "active_leases": active_leases,
                "revocation_rate": (
                    round(revoked_leases / total_leases * 100, 2)
                    if total_leases > 0 else 0.0
                )
            }

            logger.debug("Revocation stats retrieved", extra=stats)

            return stats

        except SQLAlchemyError as e:
            logger.error(
                "Database error retrieving revocation stats",
                extra={"error": str(e)}
            )
            raise
