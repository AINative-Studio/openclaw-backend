"""
Agent Skill Configuration Model

Per-agent skill configuration storage with encrypted credentials.
Supports storing API keys, OAuth tokens, and other sensitive configuration
for skills like Notion, Google Places, etc.
"""

from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
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


class AgentSkillConfiguration(Base):
    """Per-agent skill configuration with encrypted credentials"""

    __tablename__ = "agent_skill_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_swarm_instances.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_name = Column(String(255), nullable=False, index=True)

    # Encrypted JSON blob for sensitive credentials (API keys, tokens, etc.)
    # Encrypted using Fernet (symmetric encryption)
    credentials = Column(Text, nullable=True)

    # Additional non-sensitive configuration (JSON)
    config = Column(Text, nullable=True)  # Stored as JSON string

    # Whether this skill is enabled for the agent
    enabled = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    __table_args__ = (
        UniqueConstraint("agent_id", "skill_name", name="uix_agent_skill"),
        Index("idx_agent_skill_config", "agent_id", "skill_name"),
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
        Encrypt and store credentials

        Args:
            credentials_dict: Dictionary of credentials to encrypt
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
        Decrypt and return credentials

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

    def set_config(self, config_dict: Optional[Dict[str, Any]]) -> None:
        """
        Store non-sensitive configuration as JSON

        Args:
            config_dict: Dictionary of configuration
        """
        if config_dict is None:
            self.config = None
        else:
            self.config = json.dumps(config_dict)

    def get_config(self) -> Optional[Dict[str, Any]]:
        """
        Get configuration dictionary

        Returns:
            Configuration dict or None
        """
        if not self.config:
            return None

        try:
            return json.loads(self.config)
        except Exception as e:
            logger.error(f"Error parsing config JSON: {e}")
            return None

    def __repr__(self) -> str:
        return (
            f"<AgentSkillConfiguration("
            f"id={self.id}, "
            f"agent_id={self.agent_id}, "
            f"skill_name={self.skill_name}, "
            f"enabled={self.enabled}"
            f")>"
        )
