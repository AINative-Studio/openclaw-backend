"""
Ralph Loop Models (Issue #143)

Manages Ralph's iterative development loop sessions and individual iterations.
Tracks agent progress through issue resolution cycles with quality metrics,
test results, and self-review capabilities.

Refs #143
"""

from enum import Enum
from uuid import uuid4
from sqlalchemy import (
    Column,
    Integer,
    Text,
    DateTime,
    JSON,
    Boolean,
    ForeignKey,
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from backend.db.base_class import Base


class LoopMode(str, Enum):
    """Ralph loop execution mode enumeration"""
    SINGLE_SHOT = "single_shot"
    FIXED_ITERATIONS = "fixed_iterations"
    UNTIL_DONE = "until_done"


class LoopStatus(str, Enum):
    """Ralph loop session status enumeration"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class RalphLoopSession(Base):
    """
    Ralph Loop Session Model (Issue #143)

    Represents a Ralph agent's iterative development session for a specific issue.
    Manages loop configuration, iteration tracking, token budgets, and overall
    session status.

    Key Features:
    - Supports multiple loop modes (single shot, fixed iterations, until done)
    - Tracks current iteration progress and token usage
    - Links to agent swarm instance for multi-agent coordination
    - Maintains session status lifecycle
    """
    __tablename__ = "ralph_loop_sessions"

    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_swarm_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Issue tracking
    issue_number = Column(Integer, nullable=False, index=True)

    # Loop configuration
    loop_mode = Column(
        SQLEnum(LoopMode, name="loop_mode", native_enum=True, create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        index=True
    )
    max_iterations = Column(Integer, default=20, nullable=False)
    current_iteration = Column(Integer, default=0, nullable=False)

    # Status tracking
    status = Column(
        SQLEnum(LoopStatus, name="loop_status", native_enum=True, create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=LoopStatus.ACTIVE,
        nullable=False,
        index=True
    )

    # Token budget management
    token_budget = Column(Integer, nullable=True)  # Max tokens allowed for session
    tokens_used = Column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    agent = relationship("AgentSwarmInstance", foreign_keys=[agent_id])
    iterations = relationship(
        "RalphIteration",
        back_populates="loop_session",
        cascade="all, delete-orphan",
        order_by="RalphIteration.iteration_number"
    )

    def __repr__(self):
        return f"<RalphLoopSession issue={self.issue_number} status={self.status.value} iteration={self.current_iteration}/{self.max_iterations}>"


class RalphIteration(Base):
    """
    Ralph Iteration Model (Issue #143)

    Represents a single iteration within a Ralph loop session. Captures changes made,
    test results, quality metrics, self-review analysis, and continuation decision.

    Key Features:
    - Tracks code changes with detailed file-level metadata
    - Stores test results with pass/fail metrics
    - Records quality metrics (coverage, complexity, etc.)
    - Contains self-review text for agent reflection
    - Decision flag for whether to continue iterating
    """
    __tablename__ = "ralph_iterations"

    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    loop_session_id = Column(
        UUID(as_uuid=True),
        ForeignKey("ralph_loop_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Iteration tracking
    iteration_number = Column(Integer, nullable=False, index=True)

    # Iteration data (JSON for flexibility)
    changes_made = Column(JSON, nullable=True)  # List of file changes with metadata
    test_results = Column(JSON, nullable=True)  # Test execution results
    quality_metrics = Column(JSON, nullable=True)  # Code quality metrics

    # Self-review and decision
    self_review = Column(Text, nullable=True)  # Agent's reflection on iteration
    should_continue = Column(Boolean, nullable=True)  # Decision to continue iterating

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    loop_session = relationship("RalphLoopSession", back_populates="iterations")

    def __repr__(self):
        return f"<RalphIteration #{self.iteration_number} session={self.loop_session_id} continue={self.should_continue}>"
