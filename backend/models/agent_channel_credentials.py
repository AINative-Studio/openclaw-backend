"""
Agent Channel Credentials Model

Per-agent OAuth credential storage for communication channels (email, Slack, etc.).
Supports encrypted storage of OAuth access/refresh tokens.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.sql import func
from uuid import uuid4
from datetime import datetime, timezone
from cryptography.fernet import Fernet
import json
import os
import logging
from typing import Dict, Any, Optional, ClassVar

from backend.db.base_class import Base

logger = logging.getLogger(__name__)


class AgentChannelCredentials(Base):
    """Per-agent OAuth credentials for communication channels"""

    __tablename__ = "agent_channel_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_swarm_instances.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Channel type: 'email', 'slack', 'discord', etc.
    channel_type = Column(String(50), nullable=False, index=True)

    # OAuth provider: 'google', 'microsoft', 'slack', etc.
    provider = Column(String(50), nullable=False, index=True)

    # Encrypted JSON blob for OAuth tokens (access_token, refresh_token, etc.)
    # Encrypted using Fernet (symmetric encryption)
    credentials = Column(Text, nullable=True)

    # Non-sensitive metadata (email address, channel name, etc.)
    # Uses JSONB for PostgreSQL
    # Renamed to channel_metadata to avoid conflict with SQLAlchemy's metadata attribute
    channel_metadata = Column(JSONB, nullable=True)

    # Token expiration timestamp
    expires_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "agent_id", "channel_type", "provider",
            name="uix_agent_channel_provider"
        ),
        Index("idx_agent_channel", "agent_id", "channel_type"),
        Index("idx_channel_provider", "channel_type", "provider"),
    )

    # Class-level encryption key (loaded from environment)
    _fernet_key: ClassVar[Optional[Fernet]] = None

    @classmethod
    def _get_fernet(cls) -> Fernet:
        """Get or initialize Fernet encryption instance"""
        if cls._fernet_key is None:
            secret_key = os.getenv("SECRET_KEY")
            if not secret_key:
                raise ValueError(
                    "SECRET_KEY environment variable required for credential encryption"
                )

            # Use first 32 bytes of SECRET_KEY for Fernet
            # Fernet requires a URL-safe base64-encoded 32-byte key
            from base64 import urlsafe_b64encode
            import hashlib

            # Hash the secret key to get consistent 32 bytes
            key_bytes = hashlib.sha256(secret_key.encode()).digest()
            fernet_key = urlsafe_b64encode(key_bytes)

            cls._fernet_key = Fernet(fernet_key)

        return cls._fernet_key

    def set_credentials(self, credentials_dict: Dict[str, Any]) -> None:
        """
        Encrypt and store OAuth credentials

        Args:
            credentials_dict: Dictionary of OAuth credentials to encrypt
                Expected keys: access_token, refresh_token, expires_at, etc.
        """
        if not credentials_dict:
            self.credentials = None
            return

        try:
            # Serialize to JSON
            credentials_json = json.dumps(credentials_dict)

            # Encrypt
            fernet = self._get_fernet()
            encrypted_bytes = fernet.encrypt(credentials_json.encode("utf-8"))

            # Store as base64 string
            self.credentials = encrypted_bytes.decode("ascii")

        except Exception as e:
            logger.error(f"Error encrypting credentials: {e}")
            raise ValueError("Failed to encrypt credentials")

    def get_credentials(self) -> Optional[Dict[str, Any]]:
        """
        Decrypt and return OAuth credentials

        Returns:
            Dictionary of credentials or None
        """
        if not self.credentials:
            return None

        try:
            # Decrypt
            fernet = self._get_fernet()
            decrypted_bytes = fernet.decrypt(self.credentials.encode("ascii"))

            # Deserialize from JSON
            credentials_json = decrypted_bytes.decode("utf-8")
            return json.loads(credentials_json)

        except Exception as e:
            logger.error(f"Error decrypting credentials: {e}")
            return None

    def set_metadata(self, metadata_dict: Optional[Dict[str, Any]]) -> None:
        """
        Store non-sensitive metadata

        Args:
            metadata_dict: Dictionary of metadata (email address, channel name, etc.)
        """
        if metadata_dict is None:
            self.channel_metadata = None
        else:
            # For SQLite compatibility, metadata column might be Text
            # SQLAlchemy will handle JSONB conversion for PostgreSQL
            self.channel_metadata = metadata_dict

    def get_metadata(self) -> Optional[Dict[str, Any]]:
        """
        Get metadata dictionary

        Returns:
            Metadata dict or None
        """
        if not self.channel_metadata:
            return None

        # If metadata is already a dict (JSONB), return it
        if isinstance(self.channel_metadata, dict):
            return self.channel_metadata

        # If it's stored as JSON string (Text fallback), parse it
        try:
            if isinstance(self.channel_metadata, str):
                return json.loads(self.channel_metadata)
            return self.channel_metadata
        except Exception as e:
            logger.error(f"Error parsing metadata: {e}")
            return None

    def is_expired(self) -> bool:
        """
        Check if OAuth credentials have expired

        Returns:
            True if expired, False otherwise
        """
        if not self.expires_at:
            return False

        now = datetime.now(timezone.utc)
        return self.expires_at <= now

    def __repr__(self) -> str:
        return (
            f"<AgentChannelCredentials("
            f"id={self.id}, "
            f"agent_id={self.agent_id}, "
            f"channel_type={self.channel_type}, "
            f"provider={self.provider}, "
            f"expired={self.is_expired()}"
            f")>"
        )
