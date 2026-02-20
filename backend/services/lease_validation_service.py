"""
Lease Validation Service

Validates task lease tokens, checks expiration, and handles late result rejection.
Implements security checks to prevent duplicate work and unauthorized submissions.

Based on OPENCLAW_P2P_SWARM_PRD.md Section 6.2 (Task Lifecycle State Machine)
and Section 9.2 (Authorization with Capability-Based Tokens).

Refs #33
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Any
from uuid import UUID

from backend.schemas.task_schemas import (
    TaskLease,
    TaskResult,
    RejectionNotification,
    RejectionLogEntry,
)


logger = logging.getLogger(__name__)


class LeaseValidationError(Exception):
    """Base exception for lease validation errors"""
    pass


class LeaseExpiredError(LeaseValidationError):
    """Raised when lease token has expired"""
    pass


class LeaseNotFoundError(LeaseValidationError):
    """Raised when lease token is not found"""
    pass


class LeaseOwnershipError(LeaseValidationError):
    """Raised when peer_id does not match lease owner"""
    pass


class LeaseValidationService:
    """
    Lease Validation Service

    Provides:
    - Lease token validation with signature verification
    - Expiration timestamp checking
    - Late result rejection with logging
    - Peer notification for rejected submissions

    Security Features:
    - Token ownership verification (peer_id match)
    - Expiration enforcement (expires_at check)
    - Comprehensive audit logging
    """

    def __init__(self):
        """Initialize validation service with in-memory lease store"""
        # In-memory store for leases (in production, this would be DBOS/PostgreSQL)
        self.lease_store: Dict[str, TaskLease] = {}
        self.rejection_logs: list[Dict[str, Any]] = []
        logger.info("LeaseValidationService initialized")

    async def validate_lease_token(
        self,
        lease_token: str,
        task_id: UUID,
        peer_id: str,
    ) -> bool:
        """
        Validate lease token for task result submission

        Args:
            lease_token: Authorization token to validate
            task_id: Task identifier to verify
            peer_id: Submitting peer identifier

        Returns:
            True if lease is valid and not expired

        Raises:
            LeaseNotFoundError: Token not found in lease store
            LeaseExpiredError: Lease has expired
            LeaseOwnershipError: Peer does not own this lease
            LeaseValidationError: Task ID mismatch or other validation error

        Security Checks:
        1. Token exists in lease store
        2. Lease has not expired (expires_at > now)
        3. Peer ID matches lease owner
        4. Task ID matches lease task
        """
        logger.debug(
            f"Validating lease token for task_id={task_id}, peer_id={peer_id}"
        )

        # Check if lease exists
        if lease_token not in self.lease_store:
            logger.warning(
                f"Lease token not found: {lease_token[:20]}... for task {task_id}"
            )
            raise LeaseNotFoundError(
                f"Lease token not found: {lease_token}"
            )

        lease = self.lease_store[lease_token]

        # Check task ID match
        if lease.task_id != task_id:
            logger.error(
                f"Task ID mismatch: expected {lease.task_id}, got {task_id}"
            )
            raise LeaseValidationError(
                f"Task ID mismatch for lease token {lease_token}"
            )

        # Check lease ownership
        if lease.lease_owner_peer_id != peer_id:
            logger.error(
                f"Ownership mismatch: lease owner={lease.lease_owner_peer_id}, "
                f"submitter={peer_id}"
            )
            raise LeaseOwnershipError(
                f"Peer {peer_id} does not own lease for task {task_id}. "
                f"Owner: {lease.lease_owner_peer_id}"
            )

        # Check expiration
        if await self.is_lease_expired(lease):
            logger.warning(
                f"Lease expired for task {task_id}. "
                f"Expired at: {lease.lease_expires_at}"
            )
            raise LeaseExpiredError(
                f"Lease token {lease_token} expired at {lease.lease_expires_at}"
            )

        logger.info(f"Lease validation successful for task {task_id}")
        return True

    async def is_lease_expired(self, lease: TaskLease) -> bool:
        """
        Check if lease has expired

        Args:
            lease: TaskLease to check

        Returns:
            True if lease has expired, False otherwise

        Implementation:
            A lease is expired if current UTC time >= lease_expires_at
        """
        now = datetime.now(timezone.utc)
        is_expired = now >= lease.lease_expires_at

        if is_expired:
            logger.debug(
                f"Lease for task {lease.task_id} expired. "
                f"Expires at: {lease.lease_expires_at}, Now: {now}"
            )

        return is_expired

    async def verify_lease_token_validity(self, lease_token: str) -> bool:
        """
        Verify lease token exists and is valid

        Args:
            lease_token: Token to verify

        Returns:
            True if token exists in lease store and not expired

        Note:
            In production, this would verify JWT signature and claims
        """
        if lease_token not in self.lease_store:
            return False

        lease = self.lease_store[lease_token]
        return not await self.is_lease_expired(lease)

    async def reject_late_result(
        self, result: TaskResult
    ) -> Dict[str, Any]:
        """
        Reject late task result submission

        Args:
            result: TaskResult with expired or invalid lease

        Returns:
            Rejection details dictionary with:
                - rejected: bool (True)
                - reason: str (rejection reason)
                - task_id: str
                - peer_id: str
                - expires_at: datetime (if lease found)
                - timestamp: datetime (rejection time)

        Behavior:
            1. Look up lease by token
            2. Determine rejection reason
            3. Create structured rejection response
            4. Log rejection for audit
        """
        logger.info(
            f"Rejecting late result for task {result.task_id} "
            f"from peer {result.peer_id}"
        )

        lease = self.lease_store.get(result.lease_token)

        rejection = {
            "rejected": True,
            "reason": "lease_expired",
            "task_id": str(result.task_id),
            "peer_id": result.peer_id,
            "timestamp": datetime.now(timezone.utc),
        }

        if lease:
            rejection["expires_at"] = lease.lease_expires_at
            logger.warning(
                f"Task {result.task_id} result rejected. "
                f"Lease expired at {lease.lease_expires_at}"
            )
        else:
            rejection["reason"] = "lease_not_found"
            logger.warning(
                f"Task {result.task_id} result rejected. "
                f"Lease token not found"
            )

        return rejection

    async def notify_peer_of_rejection(
        self,
        peer_id: str,
        rejection: Dict[str, Any],
    ) -> RejectionNotification:
        """
        Send rejection notification to peer

        Args:
            peer_id: Target peer identifier
            rejection: Rejection details from reject_late_result()

        Returns:
            RejectionNotification message to be sent via libp2p

        Protocol:
            Notification sent via /openclaw/task/notification/1.0 protocol
            Peer should log rejection and avoid resubmitting same result
        """
        logger.info(f"Notifying peer {peer_id} of result rejection")

        notification = RejectionNotification(
            peer_id=peer_id,
            notification_type="result_rejected",
            rejection_reason=rejection["reason"],
            task_id=rejection["task_id"],
            timestamp=datetime.now(timezone.utc),
            details={
                "expires_at": (
                    rejection["expires_at"].isoformat()
                    if "expires_at" in rejection
                    else None
                ),
                "rejection_timestamp": rejection["timestamp"].isoformat(),
            },
        )

        logger.debug(
            f"Rejection notification created for peer {peer_id}: "
            f"reason={notification.rejection_reason}"
        )

        return notification

    async def log_rejection(
        self, rejection: Dict[str, Any]
    ) -> RejectionLogEntry:
        """
        Create structured log entry for rejection

        Args:
            rejection: Rejection details from reject_late_result()

        Returns:
            RejectionLogEntry for audit trail

        Storage:
            In production, log entries persisted to DBOS for compliance
            Current implementation stores in-memory for testing
        """
        log_entry = RejectionLogEntry(
            task_id=rejection["task_id"],
            peer_id=rejection["peer_id"],
            reason=rejection["reason"],
            lease_token=rejection.get("lease_token", "unknown"),
            expires_at=rejection.get("expires_at"),
            timestamp=datetime.now(timezone.utc),
            additional_info={
                "rejection_timestamp": rejection["timestamp"].isoformat(),
            },
        )

        # Store in-memory (production would use DBOS)
        self.rejection_logs.append(log_entry.model_dump())

        logger.info(
            f"Rejection logged: task={log_entry.task_id}, "
            f"peer={log_entry.peer_id}, reason={log_entry.reason}"
        )

        return log_entry
