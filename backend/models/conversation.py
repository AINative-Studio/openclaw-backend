"""
Conversation Model (Issue #103)

Represents a conversation between a user and an AI agent within a workspace.
Supports multi-channel conversations (WhatsApp, Telegram, Slack, etc.) with
external channel conversation IDs and proper isolation.

This model aligns with Epic E9 (Chat Persistence) Sprint 2 requirements.
"""

from sqlalchemy import Column, String, DateTime, ForeignKey, Enum as SQLEnum, JSON, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from uuid import uuid4
from enum import Enum
from datetime import datetime, timezone
from backend.db.base_class import Base


class ConversationStatus(str, Enum):
    """Conversation status enumeration"""
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"
    DELETED = "DELETED"


class Conversation(Base):
    """
    Conversation Model (Issue #103)

    Represents a multi-channel conversation with workspace isolation,
    optional agent assignment, user association, and channel-specific metadata.

    Key Features:
    - Multi-channel support (WhatsApp, Telegram, Slack, etc.)
    - Unique constraint on (channel, channel_conversation_id)
    - Nullable agent assignment (conversations can exist without agents)
    - Flexible metadata field for channel-specific data
    - Archival workflow with archived_at timestamp
    """
    __tablename__ = "conversations"

    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys (Issue #103 requirements)
    workspace_id = Column(
        UUID(as_uuid=True),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    agent_swarm_instance_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_swarm_instances.id", ondelete="SET NULL"),
        nullable=True,  # Agent can be assigned later
        index=True
    )

    # Channel identification (Issue #103 requirement)
    channel = Column(String(50), nullable=False)  # e.g., "whatsapp", "telegram", "slack"
    channel_conversation_id = Column(String(255), nullable=False)  # External conversation ID (indexed via composite unique index in __table_args__)

    # Conversation metadata (Issue #103) - renamed to avoid SQLAlchemy reserved name
    title = Column(String(500), nullable=True)  # Auto-generated from first message
    conversation_metadata = Column(JSON, default=dict, nullable=False)  # Channel-specific data

    # Status tracking
    status = Column(
        SQLEnum(ConversationStatus, name="conversation_status", native_enum=True, create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=ConversationStatus.ACTIVE,
        nullable=False,
        index=True
    )

    # Timestamps (Issue #103)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)
    archived_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    workspace = relationship("Workspace", back_populates="conversations")
    user = relationship("User", back_populates="conversations")
    agent_swarm_instance = relationship("AgentSwarmInstance", back_populates="conversations", foreign_keys=[agent_swarm_instance_id])

    # Composite unique constraint on (channel, channel_conversation_id) - Issue #103
    __table_args__ = (
        Index('ix_conversations_channel_conversation_id', 'channel', 'channel_conversation_id', unique=True),
    )

    def archive(self):
        """
        Archive this conversation by setting status to ARCHIVED and recording archived_at timestamp.

        This helper method implements the archival workflow required by Issue #103.
        """
        self.status = ConversationStatus.ARCHIVED
        self.archived_at = datetime.now(timezone.utc)

    def is_active(self) -> bool:
        """
        Check if conversation is currently active.

        Returns:
            bool: True if status is ACTIVE, False otherwise
        """
        return self.status == ConversationStatus.ACTIVE

    def __repr__(self):
        return f"<Conversation {self.id} channel={self.channel} status={self.status.value}>"
