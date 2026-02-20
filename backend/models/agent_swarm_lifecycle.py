"""
Agent Swarm Lifecycle Models

Manages agent provisioning, heartbeat execution, and lifecycle states.
Supports DBOS workflow durability and crash recovery.

Refs #1213
"""

from datetime import datetime
from typing import Optional
from enum import Enum
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
from app.db.base_class import Base
from app.models.base_models import UUIDMixin
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


class AgentSwarmInstance(Base, UUIDMixin):
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
    heartbeat_checklist = Column(ARRAY(String), nullable=True)

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
    heartbeat_executions = relationship(
        "AgentHeartbeatExecution",
        back_populates="agent",
        cascade="all, delete-orphan",
        order_by="desc(AgentHeartbeatExecution.started_at)"
    )

    def __repr__(self):
        return f"<AgentSwarmInstance {self.name} ({self.status})>"


class AgentHeartbeatExecution(Base, UUIDMixin):
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
    checklist_items = Column(ARRAY(String), nullable=True)
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
