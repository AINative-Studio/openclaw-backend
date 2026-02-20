"""
Agent Lifecycle ORM Model

Standalone model using backend.db.base_class.Base for the agent CRUD API.
Shares the same 'agent_swarm_instances' table as the original model.
"""

from datetime import datetime
from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    JSON,
    Boolean,
    Integer,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.sql import func

from backend.db.base_class import Base


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


class AgentSwarmInstance(Base):
    """
    Agent Swarm Instance Model

    Represents a persistent agent instance with lifecycle management
    and heartbeat monitoring.
    """
    __tablename__ = "agent_swarm_instances"
    __table_args__ = {"extend_existing": True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, index=True)
    persona = Column(Text, nullable=True)
    model = Column(String(255), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    status = Column(
        SQLEnum(
            AgentSwarmStatus,
            name="agent_swarm_status",
            native_enum=True,
            create_constraint=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=AgentSwarmStatus.PROVISIONING,
        nullable=False,
        index=True,
    )

    openclaw_session_key = Column(String(255), nullable=True, unique=True, index=True)
    openclaw_agent_id = Column(String(255), nullable=True, index=True)

    heartbeat_enabled = Column(Boolean, default=False, nullable=False)
    heartbeat_interval = Column(
        SQLEnum(
            HeartbeatInterval,
            name="heartbeat_interval",
            native_enum=True,
            create_constraint=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    heartbeat_checklist = Column(ARRAY(String), nullable=True)

    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)
    next_heartbeat_at = Column(DateTime(timezone=True), nullable=True)

    configuration = Column(JSON, default=dict, nullable=True)

    error_message = Column(Text, nullable=True)
    error_count = Column(Integer, default=0, nullable=False)
    last_error_at = Column(DateTime(timezone=True), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    provisioned_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AgentSwarmInstance {self.name} ({self.status})>"
