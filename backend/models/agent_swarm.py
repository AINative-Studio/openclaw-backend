"""
Agent Swarm ORM Model

Standalone model using backend.db.base_class.Base for the swarm CRUD API.
Stores swarm groups that coordinate multiple agents together.
"""

from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    JSON,
    Enum as SQLEnum,
)
from sqlalchemy.sql import func

from backend.db.base_class import Base


class SwarmStatus(str, Enum):
    """Swarm status enumeration"""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    FAILED = "failed"


class CoordinationStrategy(str, Enum):
    """Coordination strategy enumeration"""
    PARALLEL = "parallel"
    SEQUENTIAL = "sequential"
    HIERARCHICAL = "hierarchical"


class AgentSwarm(Base):
    """
    Agent Swarm Model

    Represents a named group of agents with shared goals,
    coordination strategies, and collective lifecycle management.
    """
    __tablename__ = "agent_swarms"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    strategy = Column(
        SQLEnum(
            CoordinationStrategy,
            name="coordination_strategy",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=CoordinationStrategy.PARALLEL,
        nullable=False,
    )
    goal = Column(Text, nullable=True)
    status = Column(
        SQLEnum(
            SwarmStatus,
            name="swarm_status",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        default=SwarmStatus.IDLE,
        nullable=False,
        index=True,
    )
    agent_ids = Column(JSON, default=list)
    user_id = Column(String(36), nullable=False, index=True)
    configuration = Column(JSON, default=dict, nullable=True)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    started_at = Column(DateTime(timezone=True), nullable=True)
    paused_at = Column(DateTime(timezone=True), nullable=True)
    stopped_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<AgentSwarm {self.name} ({self.status})>"
