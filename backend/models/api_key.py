"""
API Key Model for Encrypted Storage (Issue #83)

Stores encrypted API keys for external services (Anthropic, OpenAI, Cohere, HuggingFace).
Uses Fernet symmetric encryption to protect keys at rest.
"""

import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, LargeBinary, Boolean, DateTime
from sqlalchemy.dialects.postgresql import UUID

from backend.db.base_class import Base


class APIKey(Base):
    """
    Encrypted API key storage for external services.

    Table: api_keys

    Fields:
        id: UUID primary key
        service_name: Service identifier (anthropic, openai, cohere, huggingface)
        encrypted_key: Fernet-encrypted API key (bytes)
        created_at: Timestamp when key was first added
        updated_at: Timestamp when key was last updated
        is_active: Flag to disable key without deleting
    """

    __tablename__ = "api_keys"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    service_name = Column(String(50), unique=True, nullable=False, index=True)
    encrypted_key = Column(LargeBinary, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False
    )
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        """String representation (never shows encrypted key)."""
        return f"<APIKey(service_name='{self.service_name}', is_active={self.is_active})>"
