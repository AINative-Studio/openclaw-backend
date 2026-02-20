"""
Token Revocation Model (E7-S5)

Manages revoked tokens in persistent database storage.
Revoked tokens are kept for 30 days before automatic cleanup.

Refs: #47
"""

from datetime import datetime, timedelta
from sqlalchemy import Column, String, Integer, DateTime, Index
from backend.db.base_class import Base


class TokenRevocation(Base):
    """
    Token revocation list entry

    Tracks revoked tokens with their expiration and revocation reason.
    Tokens remain in revocation list for 30 days after expiration for audit purposes.

    Attributes:
        jti: JWT ID (unique token identifier) - Primary Key
        revoked_at: Timestamp when token was revoked
        expires_at: Original token expiration timestamp
        reason: Revocation reason (rotation, compromise, logout, etc.)
        replaced_by_jti: Optional new token ID if this was rotated
    """
    __tablename__ = "token_revocations"

    jti = Column(String(64), primary_key=True, nullable=False, index=True)
    revoked_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    reason = Column(String(50), nullable=False)
    replaced_by_jti = Column(String(64), nullable=True)

    # Create composite index for cleanup queries
    __table_args__ = (
        Index('ix_revocation_cleanup', 'expires_at', 'revoked_at'),
    )

    def __repr__(self) -> str:
        return f"<TokenRevocation(jti={self.jti}, reason={self.reason}, revoked_at={self.revoked_at})>"

    @classmethod
    def create(
        cls,
        jti: str,
        expires_at: datetime,
        reason: str = "rotation",
        replaced_by_jti: str = None
    ) -> "TokenRevocation":
        """
        Create a new revocation entry

        Args:
            jti: Token ID to revoke
            expires_at: Original token expiration
            reason: Revocation reason
            replaced_by_jti: New token ID if rotated

        Returns:
            New revocation entry
        """
        return cls(
            jti=jti,
            revoked_at=datetime.utcnow(),  # Explicitly set revoked_at
            expires_at=expires_at,
            reason=reason,
            replaced_by_jti=replaced_by_jti
        )

    def should_cleanup(self, retention_days: int = 30) -> bool:
        """
        Check if revocation entry should be cleaned up

        Args:
            retention_days: Days to keep after expiration (default 30)

        Returns:
            True if entry should be deleted
        """
        cleanup_threshold = datetime.utcnow() - timedelta(days=retention_days)
        return self.expires_at < cleanup_threshold
