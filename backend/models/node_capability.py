"""
Node Capability and Task Complexity Models

These models are NOT part of the Task/TaskLease consolidation (Issue #116).
They remain separate as they serve different purposes:
- NodeCapability: Tracks P2P node capabilities
- TaskComplexity: Enum for lease duration calculation

Safe to import from this file.
"""

from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Column,
    String,
    JSON,
    Boolean,
    Integer,
    DateTime,
)
from sqlalchemy.dialects.postgresql import UUID
from uuid import uuid4
from sqlalchemy.sql import func

from backend.db.base_class import Base


class TaskComplexity(str, Enum):
    """Task complexity enumeration for lease duration calculation"""
    LOW = "low"  # 5 min lease
    MEDIUM = "medium"  # 10 min lease
    HIGH = "high"  # 15 min lease


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
