"""
Canonical Task Lease Models (Issue #116)

This is the SINGLE source of truth for TaskLease and Task models.
All services MUST import from this file.

Consolidates:
- task_models.py (DEPRECATED)
- task_queue.py (DEPRECATED - merged here)
- task_lease_models.py (DEPRECATED)

Uses PostgreSQL-native schema:
- UUID primary keys
- Native enums (NOT strings)
- peer_id field (NOT owner_peer_id)
- Timezone-aware timestamps
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
    Integer,
    Float,
    Enum as SQLEnum,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4
from sqlalchemy.sql import func
from backend.db.base_class import Base


class TaskStatus(str, Enum):
    """
    Task status enumeration

    7 states for complete task lifecycle:
    - QUEUED: Task created, awaiting lease
    - LEASED: Task leased to a peer
    - RUNNING: Task actively executing
    - COMPLETED: Task finished successfully
    - FAILED: Task failed but may retry
    - EXPIRED: Lease expired without completion
    - PERMANENTLY_FAILED: Max retries exceeded
    """
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"
    PERMANENTLY_FAILED = "permanently_failed"


class TaskPriority(str, Enum):
    """Task priority enumeration"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class Task(Base):
    """
    Task Entity Model

    Represents a work unit in the distributed task queue.
    Tracks status, retries, and execution metadata.
    """
    __tablename__ = "tasks"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    idempotency_key = Column(String(255), nullable=True, unique=True, index=True)

    # Multi-tenant isolation (Issue #120)
    workspace_id = Column(
        UUID(),
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        nullable=True,  # Nullable during migration, enforce NOT NULL after data migration
        index=True
    )

    # Task definition
    task_type = Column(String(100), nullable=False, index=True)
    payload = Column(JSON, nullable=False)
    priority = Column(
        SQLEnum(TaskPriority, name="task_priority", native_enum=True, create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=TaskPriority.NORMAL,
        nullable=False,
        index=True
    )

    # Status tracking
    status = Column(
        SQLEnum(TaskStatus, name="task_status", native_enum=True, create_constraint=True, values_callable=lambda x: [e.value for e in x]),
        default=TaskStatus.QUEUED,
        nullable=False,
        index=True
    )

    # Retry handling
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=3, nullable=False)

    # Capability requirements
    required_capabilities = Column(JSON, default=dict, nullable=True)

    # Result tracking
    result = Column(JSON, nullable=True)
    error_message = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True)

    # Execution metadata
    assigned_peer_id = Column(String(255), nullable=True, index=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    workspace = relationship("Workspace", foreign_keys=[workspace_id])
    leases = relationship(
        "TaskLease",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="desc(TaskLease.created_at)"
    )

    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_task_queue_retrieval', 'status', 'priority', 'created_at'),
        Index('idx_task_retry_eligible', 'status', 'retry_count', 'max_retries'),
    )

    def __repr__(self):
        return f"<Task {self.id} ({self.task_type} - {self.status})>"


class TaskLease(Base):
    """
    Task Lease Model

    Represents exclusive ownership of a task by a peer node.
    Includes expiration tracking and token management.

    CRITICAL: Uses peer_id (NOT owner_peer_id) to match PostgreSQL schema.
    """
    __tablename__ = "task_leases"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    task_id = Column(
        UUID(),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    peer_id = Column(String(255), nullable=False, index=True)

    # Lease management
    lease_token = Column(String(500), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    is_expired = Column(Integer, default=0, nullable=False, index=True)
    is_revoked = Column(Integer, default=0, nullable=False)

    # Metadata
    lease_duration_seconds = Column(Integer, nullable=False)
    lease_metadata = Column(JSON, default=dict, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    task = relationship("Task", back_populates="leases")

    # Indexes for lease expiration detection
    __table_args__ = (
        Index('idx_lease_expiration_scan', 'expires_at', 'is_expired', 'is_revoked'),
        Index('idx_lease_validation', 'lease_token', 'expires_at', 'is_revoked'),
    )

    def __repr__(self):
        return f"<TaskLease {self.id} (task={self.task_id}, peer={self.peer_id})>"
