"""
Skill History Models

Tracks skill installation and execution history for agent swarms.
Enables audit trail, debugging, and rollback capabilities for skill management.

Phase 4: Skill History & Audit Trail
"""

from datetime import datetime
from sqlalchemy import Column, String, Integer, Text, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB, TIMESTAMP
from sqlalchemy.orm import relationship
from backend.db.base_class import Base
import uuid


class SkillInstallationHistory(Base):
    """
    Skill Installation History Model

    Tracks the complete lifecycle of skill installations including:
    - Installation attempts (started/completed/failed)
    - Installation methods (npm/brew/manual)
    - Package and binary paths
    - Error tracking for failed installations
    - Rollback tracking
    """
    __tablename__ = "skill_installation_history"

    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Skill identification
    skill_name = Column(String(255), nullable=False, index=True)

    # Agent relationship
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_swarm_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Installation status tracking
    status = Column(
        String(50),
        nullable=False,
        index=True
    )  # STARTED, COMPLETED, FAILED, ROLLED_BACK

    # Installation method details
    method = Column(String(50))  # npm, brew, manual
    package_name = Column(String(255))
    binary_path = Column(String(500))

    # Timing information
    started_at = Column(TIMESTAMP(timezone=True), nullable=False)
    completed_at = Column(TIMESTAMP(timezone=True))

    # Error tracking
    error_message = Column(Text)

    # Audit timestamp
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now())

    # Relationship
    agent = relationship("AgentSwarmInstance", back_populates="skill_installations")

    def __repr__(self):
        return f"<SkillInstallationHistory {self.skill_name} ({self.status})>"


class SkillExecutionHistory(Base):
    """
    Skill Execution History Model

    Tracks individual skill executions including:
    - Execution status (running/completed/failed/timeout)
    - Input parameters and output results
    - Execution timing and performance metrics
    - Error tracking for debugging
    """
    __tablename__ = "skill_execution_history"

    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

    # Unique execution identifier (for idempotency and tracking)
    execution_id = Column(UUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)

    # Skill identification
    skill_name = Column(String(255), nullable=False, index=True)

    # Agent relationship
    agent_id = Column(
        UUID(as_uuid=True),
        ForeignKey("agent_swarm_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Execution status tracking
    status = Column(
        String(50),
        nullable=False,
        index=True
    )  # RUNNING, COMPLETED, FAILED, TIMEOUT

    # Execution data
    parameters = Column(JSONB)  # Input parameters as JSON
    output = Column(Text)  # Execution output/results
    error_message = Column(Text)  # Error details if failed

    # Performance metrics
    execution_time_ms = Column(Integer)  # Duration in milliseconds

    # Timing information
    started_at = Column(TIMESTAMP(timezone=True), nullable=False, index=True)
    completed_at = Column(TIMESTAMP(timezone=True))

    # Audit timestamp
    created_at = Column(TIMESTAMP(timezone=True), default=lambda: datetime.now())

    # Relationship
    agent = relationship("AgentSwarmInstance", back_populates="skill_executions")

    def __repr__(self):
        return f"<SkillExecutionHistory {self.skill_name} ({self.status})>"
