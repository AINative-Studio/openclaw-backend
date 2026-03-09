"""
User Model

Represents a user within a workspace with access to agents and conversations.
Supports multi-tenant architecture with workspace-level isolation.
"""

from sqlalchemy import Column, String, ForeignKey, DateTime, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4
from backend.db.base_class import Base
from sqlalchemy.sql import func


class User(Base):
    """
    User Model

    Represents a user with email authentication, workspace membership,
    and access to agents and conversations.

    Fields:
        id (UUID): Primary key, auto-generated UUID
        email (str): Unique email address, indexed
        full_name (str, optional): User's full name
        workspace_id (UUID): Foreign key to workspaces table
        created_at (datetime): Auto-generated timestamp on creation
        updated_at (datetime): Auto-updated timestamp on modification
        is_active (bool): User account status, defaults to True
    """
    __tablename__ = "users"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(255), nullable=True)

    # Workspace relationship
    workspace_id = Column(
        UUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    workspace = relationship("Workspace", back_populates="users")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    # NOTE: Agents relationship will be integrated after AgentSwarmInstance relationship is fixed
    # agents = relationship("AgentSwarmInstance", back_populates="user", foreign_keys="[AgentSwarmInstance.user_id]")

    def __repr__(self):
        return f"<User {self.email}>"
