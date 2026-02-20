"""
Task Lease Management Models

Models specifically for task lease issuance workflow (E5-S1).
Extends existing task models with lease-specific entities.

Refs #27 (E5-S1: Task Lease Issuance)
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
    Enum as SQLEnum,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from uuid import uuid4
from sqlalchemy.sql import func

from backend.db.base_class import Base


class TaskComplexity(str, Enum):
    """Task complexity enumeration for lease duration calculation"""
    LOW = "low"  # 5 min lease
    MEDIUM = "medium"  # 10 min lease
    HIGH = "high"  # 15 min lease


class TaskLease(Base):
    """
    Task Lease Model

    Represents a time-bound lease granted to a node for task execution.
    Includes signed JWT token for secure lease validation.
    """
    __tablename__ = "task_leases"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    task_id = Column(String(255), nullable=False, index=True)  # References tasks.task_id

    # Node identification (from P2P network)
    peer_id = Column(String(255), nullable=False, index=True)
    node_address = Column(String(255), nullable=True)

    # Lease security
    lease_token = Column(Text, nullable=False, unique=True)  # JWT token

    # Lease timing
    issued_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

    # Lease status
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    revoke_reason = Column(Text, nullable=True)

    # Execution tracking
    heartbeat_count = Column(Integer, default=0, nullable=False)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)

    # Node capabilities snapshot (at time of lease)
    node_capabilities = Column(JSON, default=dict, nullable=True)

    # Task complexity for lease duration tracking
    task_complexity = Column(
        SQLEnum(
            TaskComplexity,
            name="task_complexity_lease",
            native_enum=True,
            create_constraint=True,
            values_callable=lambda x: [e.value for e in x]
        ),
        default=TaskComplexity.MEDIUM,
        nullable=False
    )

    # Lease metadata
    lease_metadata = Column(JSON, default=dict, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self):
        return f"<TaskLease {self.id} (task={self.task_id}, peer={self.peer_id[:12]}...)>"


class NodeCapability(Base):
    """
    Node Capability Model

    Tracks capabilities of nodes in the P2P network for task matching.
    Periodically updated via heartbeat messages.
    """
    __tablename__ = "node_capabilities"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    peer_id = Column(String(255), nullable=False, unique=True, index=True)
    node_address = Column(String(255), nullable=True)

    # Capability information
    capabilities = Column(JSON, default=dict, nullable=False)
    # Format: {
    #   "cpu_cores": 8,
    #   "memory_mb": 16384,
    #   "gpu_available": true,
    #   "gpu_memory_mb": 8192,
    #   "storage_mb": 100000,
    #   "network_bandwidth_mbps": 1000
    # }

    # Availability status
    is_available = Column(Boolean, default=True, nullable=False, index=True)
    current_task_count = Column(Integer, default=0, nullable=False)
    max_concurrent_tasks = Column(Integer, default=5, nullable=False)

    # Health metrics
    cpu_usage_percent = Column(Integer, default=0, nullable=True)
    memory_usage_percent = Column(Integer, default=0, nullable=True)
    last_health_check = Column(DateTime(timezone=True), nullable=True)

    # Reputation and reliability
    success_count = Column(Integer, default=0, nullable=False)
    failure_count = Column(Integer, default=0, nullable=False)
    total_tasks_completed = Column(Integer, default=0, nullable=False)

    # Node metadata
    node_metadata = Column(JSON, default=dict, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    last_seen_at = Column(DateTime(timezone=True), nullable=True)

    def __repr__(self):
        return f"<NodeCapability {self.peer_id[:12]}... (available={self.is_available})>"
