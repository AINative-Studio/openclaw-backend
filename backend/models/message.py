"""
Message Model - PostgreSQL storage for chat messages

Simple PostgreSQL-based message storage for conversations.
Provides immediate persistence without requiring ZeroDB setup.
Can be migrated to ZeroDB later as an enhancement.
"""

from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Index
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.sql import func
from uuid import uuid4

from backend.db.base_class import Base


# Use PostgreSQL UUID when available, fallback to String for SQLite
try:
    SQLUUID = PGUUID
except:
    SQLUUID = String


class Message(Base):
    """
    Message model for storing chat messages in PostgreSQL.

    Provides simple, immediate persistence for conversations without
    requiring ZeroDB configuration.
    """
    __tablename__ = "messages"

    id = Column(SQLUUID(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id = Column(
        SQLUUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    message_metadata = Column("metadata", JSON, default=dict)  # Rename to avoid SQLAlchemy reserved word

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Index for efficient conversation message retrieval
    __table_args__ = (
        Index("ix_messages_conversation_created", "conversation_id", "created_at"),
    )

    def __repr__(self):
        return f"<Message(id={self.id}, conversation_id={self.conversation_id}, role={self.role})>"
