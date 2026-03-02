"""
User API Key Model for Workspace-Level Encrypted Storage (Issue #96)

Stores encrypted API keys per workspace for external services (Anthropic, OpenAI, Cohere, HuggingFace).
Uses Fernet symmetric encryption to protect keys at rest.

Security Features:
- Encryption at rest using ENCRYPTION_SECRET from environment
- Key hash for quick lookups without decryption
- Never logs or exposes plaintext keys
- Per-workspace isolation
"""

import uuid
import hashlib
from datetime import datetime, timezone
from sqlalchemy import Column, String, Text, Boolean, DateTime, Index
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base_class import Base


class UserAPIKey(Base):
    """
    Encrypted API key storage per workspace for external services.

    Table: user_api_keys

    Fields:
        id: UUID primary key
        workspace_id: UUID of workspace (string for now, can add FK later when workspaces table exists)
        provider: Service identifier (anthropic, openai, cohere, huggingface, google)
        encrypted_key: Fernet-encrypted API key (text)
        key_hash: SHA-256 hash of the key for quick validation (64 chars hex)
        is_active: Flag to disable key without deleting
        last_validated_at: Timestamp of last successful validation
        created_at: Timestamp when key was first added
        updated_at: Timestamp when key was last updated

    Indexes:
        - workspace_id (for filtering by workspace)
        - provider (for filtering by provider)
        - unique constraint on (workspace_id, provider) to ensure one key per provider per workspace
    """

    __tablename__ = "user_api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Workspace identifier (UUID stored as string for now)
    workspace_id = Column(String(36), nullable=False, index=True)

    # Provider name (anthropic, openai, cohere, huggingface, google)
    provider = Column(String(50), nullable=False, index=True)

    # Encrypted key (Fernet ciphertext)
    encrypted_key = Column(Text, nullable=False)

    # SHA-256 hash of key for validation (64 hex chars)
    key_hash = Column(String(64), nullable=False)

    # Status flags
    is_active = Column(Boolean, default=True, nullable=False)

    # Validation timestamp
    last_validated_at = Column(DateTime(timezone=True), nullable=True)

    # Timestamps
    created_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )

    # Indexes
    __table_args__ = (
        # Unique constraint: one key per provider per workspace
        Index(
            'uq_user_api_keys_workspace_provider',
            'workspace_id',
            'provider',
            unique=True
        ),
    )

    def __repr__(self):
        """String representation (never shows encrypted key or hash)."""
        return (
            f"<UserAPIKey(workspace_id='{self.workspace_id}', "
            f"provider='{self.provider}', is_active={self.is_active})>"
        )

    @staticmethod
    def compute_key_hash(plaintext_key: str) -> str:
        """
        Compute SHA-256 hash of an API key.

        Args:
            plaintext_key: Plaintext API key

        Returns:
            64-character hex string (SHA-256 hash)
        """
        return hashlib.sha256(plaintext_key.encode()).hexdigest()
