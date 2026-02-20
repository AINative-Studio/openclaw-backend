"""
Token Rotation Service (E7-S5)

Manages capability token renewal, revocation, and lifecycle.
Provides automatic renewal, grace periods, and audit logging.

Refs: #47
"""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
import logging

from backend.models.capability_token import CapabilityToken, TokenLimits
from backend.models.token_revocation import TokenRevocation


logger = logging.getLogger(__name__)


class TokenRotationService:
    """
    Service for managing token rotation and revocation

    Handles token renewal with grace periods, revocation tracking,
    and automatic cleanup of old revocations.
    """

    def __init__(self, db: Session):
        """
        Initialize token rotation service

        Args:
            db: Database session for persistence
        """
        self.db = db

    async def renew_token(
        self,
        token: CapabilityToken,
        extends_by_seconds: int = 3600,
        grace_period_seconds: int = 300
    ) -> CapabilityToken:
        """
        Renew a capability token

        Creates a new token with extended expiration and revokes the old token.
        Maintains capability grants and peer_id from original token.

        Args:
            token: Original token to renew
            extends_by_seconds: Extension period (default 1 hour)
            grace_period_seconds: Grace period for old token (default 5 minutes)

        Returns:
            New capability token with extended expiration
        """
        logger.info(f"Renewing token {token.jti} for peer {token.peer_id}")

        # Create new token with same capabilities, limits, and peer_id
        new_token = CapabilityToken.create(
            peer_id=token.peer_id,
            capabilities=token.capabilities.copy(),
            limits=token.limits,
            data_scope=token.data_scope.copy() if token.data_scope else None,
            expires_in_seconds=extends_by_seconds,
            parent_jti=token.jti
        )

        # Revoke old token
        await self.revoke_token(
            jti=token.jti,
            expires_at=datetime.fromtimestamp(token.expires_at),
            reason="rotation",
            replaced_by_jti=new_token.jti
        )

        logger.info(f"Token renewed: {token.jti} -> {new_token.jti}")

        return new_token

    async def revoke_token(
        self,
        jti: str,
        expires_at: datetime,
        reason: str = "manual",
        replaced_by_jti: Optional[str] = None
    ) -> None:
        """
        Revoke a token by adding to revocation list

        Args:
            jti: Token ID to revoke
            expires_at: Original token expiration
            reason: Revocation reason (rotation, compromise, logout, manual)
            replaced_by_jti: New token ID if this was rotated
        """
        logger.info(f"Revoking token {jti}, reason: {reason}")

        revocation = TokenRevocation.create(
            jti=jti,
            expires_at=expires_at,
            reason=reason,
            replaced_by_jti=replaced_by_jti
        )

        self.db.add(revocation)
        self.db.commit()

        logger.debug(f"Token {jti} added to revocation list")

    async def is_token_revoked(self, jti: str) -> bool:
        """
        Check if a token is revoked

        Args:
            jti: Token ID to check

        Returns:
            True if token is revoked
        """
        revocation = self.db.query(TokenRevocation).filter(
            TokenRevocation.jti == jti
        ).first()

        return revocation is not None

    async def should_auto_renew(
        self,
        token: CapabilityToken,
        threshold_seconds: int = 3600
    ) -> bool:
        """
        Check if token should be automatically renewed

        Args:
            token: Token to check
            threshold_seconds: Renew if expiring within this threshold

        Returns:
            True if token should be renewed
        """
        remaining = token.expires_in_seconds()
        should_renew = remaining < threshold_seconds and remaining > 0

        if should_renew:
            logger.debug(
                f"Token {token.jti} should renew: {remaining}s remaining, "
                f"threshold {threshold_seconds}s"
            )

        return should_renew

    async def is_within_grace_period(
        self,
        jti: str,
        grace_period_seconds: int = 300
    ) -> bool:
        """
        Check if revoked token is within grace period

        During grace period, old token is still valid for smooth transition.

        Args:
            jti: Token ID to check
            grace_period_seconds: Grace period duration (default 5 minutes)

        Returns:
            True if within grace period
        """
        revocation = self.db.query(TokenRevocation).filter(
            TokenRevocation.jti == jti
        ).first()

        if not revocation:
            return False

        # Check if revocation is recent enough to be in grace period
        elapsed = (datetime.utcnow() - revocation.revoked_at).total_seconds()
        is_within_grace = elapsed < grace_period_seconds

        if is_within_grace:
            logger.debug(
                f"Token {jti} within grace period: {elapsed:.0f}s of {grace_period_seconds}s"
            )

        return is_within_grace

    async def validate_token(
        self,
        token: CapabilityToken,
        grace_period_seconds: int = 300
    ) -> bool:
        """
        Validate a capability token

        Checks expiration and revocation status with grace period support.

        Args:
            token: Token to validate
            grace_period_seconds: Grace period for revoked tokens

        Returns:
            True if token is valid
        """
        # Check expiration
        if token.is_expired():
            logger.warning(f"Token {token.jti} is expired")
            return False

        # Check revocation
        is_revoked = await self.is_token_revoked(token.jti)

        if not is_revoked:
            return True

        # Check grace period
        within_grace = await self.is_within_grace_period(
            token.jti,
            grace_period_seconds
        )

        if within_grace:
            logger.debug(f"Token {token.jti} revoked but within grace period")
            return True

        logger.warning(f"Token {token.jti} is revoked and outside grace period")
        return False

    async def cleanup_old_revocations(
        self,
        retention_days: int = 30
    ) -> int:
        """
        Clean up old revocation entries

        Removes revocations older than retention period for database hygiene.

        Args:
            retention_days: Days to keep after expiration (default 30)

        Returns:
            Number of entries deleted
        """
        cleanup_threshold = datetime.utcnow() - timedelta(days=retention_days)

        logger.info(f"Cleaning up revocations older than {cleanup_threshold}")

        # Find old revocations
        old_revocations = self.db.query(TokenRevocation).filter(
            TokenRevocation.expires_at < cleanup_threshold
        ).all()

        count = len(old_revocations)

        if count == 0:
            logger.debug("No old revocations to clean up")
            return 0

        # Delete old entries
        for revocation in old_revocations:
            self.db.delete(revocation)

        self.db.commit()

        logger.info(f"Cleaned up {count} old revocation entries")

        return count

    async def get_revocation_audit_trail(
        self,
        jti: str
    ) -> Optional[TokenRevocation]:
        """
        Get audit trail for a revoked token

        Args:
            jti: Token ID to query

        Returns:
            Revocation entry if found
        """
        return self.db.query(TokenRevocation).filter(
            TokenRevocation.jti == jti
        ).first()

    async def renew_if_needed(
        self,
        token: CapabilityToken,
        threshold_seconds: int = 3600,
        extends_by_seconds: int = 3600
    ) -> Optional[CapabilityToken]:
        """
        Automatically renew token if needed

        Convenience method that checks and renews in one call.

        Args:
            token: Token to check
            threshold_seconds: Renew if expiring within this threshold
            extends_by_seconds: Extension period

        Returns:
            New token if renewed, None if renewal not needed
        """
        should_renew = await self.should_auto_renew(token, threshold_seconds)

        if not should_renew:
            return None

        logger.info(f"Auto-renewing token {token.jti}")
        return await self.renew_token(token, extends_by_seconds)
