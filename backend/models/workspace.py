"""
Workspace Model

Represents a workspace that contains users, agents, and conversations.
Provides organizational boundary for multi-tenant architecture with ZeroDB integration.
"""

from sqlalchemy import Column, String, Text, DateTime
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from uuid import uuid4
from backend.db.base_class import Base
from sqlalchemy.sql import func
import sqlalchemy as sa


class Workspace(Base):
    """
    Workspace Model

    Represents a workspace with users, agents, and conversations.
    Supports multi-tenant isolation, organizational structure, and ZeroDB integration.
    """
    __tablename__ = "workspaces"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    name = Column(Text, nullable=True)
    comment = Column(Text, nullable=True)
    meta = Column(sa.JSON, nullable=True)
    config = Column(sa.JSON, nullable=True)

    # ZeroDB integration
    zerodb_project_id = Column(String(255), nullable=True, unique=True, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    users = relationship("User", back_populates="workspace", cascade="all, delete-orphan")
    # TEMPORARY: agents relationship commented out - workspace_id column doesn't exist in agent_swarm_instances yet
    # agents = relationship("AgentSwarmInstance", back_populates="workspace", cascade="all, delete-orphan")
    conversations = relationship("Conversation", back_populates="workspace", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Workspace {self.name} ({self.id})>"
