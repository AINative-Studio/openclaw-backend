"""
Agent Swarm Lifecycle Models

Manages agent provisioning, heartbeat execution, and lifecycle states.
Supports DBOS workflow durability and crash recovery.

Refs #1213
"""

from datetime import datetime
from typing import Optional
from enum import Enum
from uuid import UUID as UUID_TYPE
from sqlalchemy import (
    Column,
    String,
    Text,
    ForeignKey,
    DateTime,
    JSON,
    Boolean,
    Integer,
    Float,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import relationship
from uuid import uuid4
from backend.db.base_class import Base
from sqlalchemy.sql import func


class AgentSwarmStatus(str, Enum):
    """Agent swarm instance status enumeration"""
    PROVISIONING = "provisioning"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class HeartbeatInterval(str, Enum):
    """Heartbeat interval enumeration"""
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    TWO_HOURS = "2h"


class HeartbeatExecutionStatus(str, Enum):
    """Heartbeat execution status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class AgentSwarmInstance(Base):
    """
    Agent Swarm Instance Model

    Represents a persistent agent instance with lifecycle management,
    heartbeat monitoring, and DBOS workflow integration.
    """
    __tablename__ = "agent_swarm_instances"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, index=True)
    persona = Column(Text, nullable=True)
    model = Column(String(255), nullable=False)
    user_id = Column(UUID(), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    workspace_id = Column(
        UUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,  # Nullable for migration, then make NOT NULL after data migration
        index=True
    )
    # Current active conversation (Issue #104: E9-S2)
    current_conversation_id = Column(
        UUID(),
        ForeignKey("conversations.id", ondelete="SET NULL"),
        nullable=True,  # Optional - agent may not have active conversation
        index=True
    )

    # Status tracking
    status = Column(
        SQLEnum(AgentSwarmStatus, name="agent_swarm_status", native_enum=True, create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=AgentSwarmStatus.PROVISIONING,
        nullable=False,
        index=True
    )

    # OpenClaw integration
    openclaw_session_key = Column(String(255), nullable=True, unique=True, index=True)
    openclaw_agent_id = Column(String(255), nullable=True, index=True)

    # Heartbeat configuration
    heartbeat_enabled = Column(Boolean, default=False, nullable=False)
    heartbeat_interval = Column(
        SQLEnum(HeartbeatInterval, name="heartbeat_interval", native_enum=True, create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        nullable=True
    )
    heartbeat_checklist = Column(ARRAY(String), nullable=True)  # PostgreSQL native array type

    # Heartbeat execution tracking
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    next_heartbeat_at = Column(DateTime(timezone=True), nullable=True)

    # Agent configuration
    configuration = Column(JSON, default=dict, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_count = Column(Integer, default=0, nullable=False)
    last_error_at = Column(DateTime(timezone=True), nullable=True)

    # Lifecycle timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    provisioned_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User", foreign_keys=[user_id])
    # TEMPORARY: workspace relationship commented out - workspace_id column doesn't exist yet
    # workspace = relationship("Workspace", back_populates="agents")
    conversations = relationship("Conversation", back_populates="agent_swarm_instance", cascade="all, delete-orphan", foreign_keys="[Conversation.agent_swarm_instance_id]")
    # Current active conversation relationship (Issue #104: E9-S2)
    current_conversation = relationship(
        "Conversation",
        foreign_keys=[current_conversation_id],
        uselist=False,
        viewonly=True
    )
    heartbeat_executions = relationship(
        "AgentHeartbeatExecution",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="desc(AgentHeartbeatExecution.started_at)"
    )
    skill_installations = relationship(
        "SkillInstallationHistory",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="desc(SkillInstallationHistory.started_at)"
    )
    skill_executions = relationship(
        "SkillExecutionHistory",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="desc(SkillExecutionHistory.started_at)"
    )

    def attach_conversation(self, conversation_id: UUID_TYPE) -> None:
        """
        Attach a conversation to this agent as the current active conversation.

        Validates that the conversation exists and belongs to the same workspace
        as the agent to prevent cross-workspace data access. This ensures proper
        workspace isolation and security.

        Args:
            conversation_id: UUID of the conversation to attach

        Raises:
            ValueError: If agent not attached to session, conversation not found,
                       or conversation belongs to different workspace

        Example:
            ```python
            agent.attach_conversation(conversation.id)
            db.session.commit()  # Persist the attachment
            ```
        """
        from sqlalchemy.orm import object_session
        from backend.models.conversation import Conversation

        session = object_session(self)
        if session is None:
            raise ValueError("Agent instance must be attached to a session")

        # Fetch conversation and validate in single query
        conversation = session.query(Conversation).filter(
            Conversation.id == conversation_id
        ).first()

        if conversation is None:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Validate workspace match (security - prevent cross-workspace access)
        if conversation.workspace_id != self.workspace_id:
            raise ValueError(
                "Conversation must belong to the same workspace as the agent. "
                f"Conversation workspace: {conversation.workspace_id}, "
                f"Agent workspace: {self.workspace_id}"
            )

        # Attach conversation
        self.current_conversation_id = conversation_id

    def detach_conversation(self) -> None:
        """
        Detach the current active conversation from this agent.

        Sets current_conversation_id to None, indicating the agent
        has no active conversation. This is useful when ending a conversation
        or switching contexts.

        Example:
            ```python
            agent.detach_conversation()
            db.session.commit()  # Persist the detachment
            ```
        """
        self.current_conversation_id = None

    def get_active_conversation(self) -> Optional["Conversation"]:
        """
        Get the current active conversation for this agent.

        Returns:
            Conversation object if one is attached, None otherwise

        Note:
            This method uses the current_conversation relationship which
            is lazy-loaded by default. If you need to avoid additional queries,
            use eager loading when querying the agent:

            ```python
            agent = db.query(AgentSwarmInstance)\\
                .options(joinedload(AgentSwarmInstance.current_conversation))\\
                .filter(AgentSwarmInstance.id == agent_id)\\
                .first()
            ```

        Example:
            ```python
            conv = agent.get_active_conversation()
            if conv:
                print(f"Active conversation: {conv.id}")
            else:
                print("No active conversation")
            ```
        """
        return self.current_conversation

    def __repr__(self):
        return f"<AgentSwarmInstance {self.name} ({self.status})>"


class AgentHeartbeatExecution(Base):
    """
    Agent Heartbeat Execution Model

    Tracks individual heartbeat execution with DBOS workflow durability.
    Enables crash recovery and execution history audit.
    """
    __tablename__ = "agent_heartbeat_executions"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    agent_id = Column(
        UUID(),
        ForeignKey("agent_swarm_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Execution status
    status = Column(
        SQLEnum(HeartbeatExecutionStatus, name="heartbeat_execution_status", native_enum=True, create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=HeartbeatExecutionStatus.PENDING,
        nullable=False,
        index=True
    )

    # Execution details
    checklist_items = Column(JSON, nullable=True)  # Changed from ARRAY for SQLite compatibility
    checklist_results = Column(JSON, default=dict, nullable=True)

    # Timing information
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0, nullable=False)

    # DBOS workflow tracking
    workflow_uuid = Column(String(255), nullable=True, unique=True, index=True)
    workflow_metadata = Column(JSON, default=dict, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    agent = relationship("AgentSwarmInstance", back_populates="heartbeat_executions")

    def __repr__(self):
        return f"<AgentHeartbeatExecution {self.id} ({self.status})>"
