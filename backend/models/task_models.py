"""
Task Management Models

Manages distributed task execution including task entities, leases,
and capability matching for fair work distribution.

Matches existing SQLite schema from openclaw.db

Refs #35 (E5-S9: Task Assignment Orchestrator)
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Any
from enum import Enum
from sqlalchemy import (
    Column,
    String,
    ForeignKey,
    DateTime,
    JSON,
    Integer,
    Index,
)
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func

# Create Base for models
Base = declarative_base()


class TaskStatus(str, Enum):
    """Task status enumeration matching database schema"""
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Task(Base):
    """
    Task Entity Model

    Represents a unit of work to be distributed across the P2P network.
    Matches existing tasks table schema in openclaw.db
    """
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(255), nullable=False, unique=True, index=True)
    status = Column(String(11), nullable=False, index=True, default=TaskStatus.QUEUED.value)
    payload = Column(JSON, nullable=True)
    idempotency_key = Column(String(255), nullable=False, unique=True, index=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp()
    )
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp()
    )

    # Relationships
    leases = relationship(
        "TaskLease",
        back_populates="task",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Task {self.task_id} ({self.status})>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "status": self.status,
            "payload": self.payload,
            "idempotency_key": self.idempotency_key,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class TaskLease(Base):
    """
    Task Lease Model

    Represents a time-bound lease granted to a node for task execution.
    Matches existing task_leases table schema in openclaw.db
    """
    __tablename__ = "task_leases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(
        String(255),
        ForeignKey("tasks.task_id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    owner_peer_id = Column(String(255), nullable=False, index=True)
    token = Column(String(255), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    created_at = Column(
        DateTime,
        nullable=False,
        server_default=func.current_timestamp()
    )

    # Relationships
    task = relationship("Task", back_populates="leases")

    # Composite indexes matching schema
    __table_args__ = (
        Index("ix_task_leases_expires_at_owner", "expires_at", "owner_peer_id"),
    )

    def __repr__(self):
        return f"<TaskLease task={self.task_id} owner={self.owner_peer_id}>"

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            "id": self.id,
            "task_id": self.task_id,
            "owner_peer_id": self.owner_peer_id,
            "token": self.token,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def is_expired(self) -> bool:
        """Check if lease has expired"""
        if not self.expires_at:
            return True
        # Handle both timezone-aware and naive datetimes
        # SQLite stores naive datetimes, so we compare in naive format
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        expires = self.expires_at
        if expires.tzinfo is not None:
            expires = expires.replace(tzinfo=None)
        return now > expires
