"""
Task Management Schemas

Pydantic schemas for task management API requests and responses.

Refs #27 (E5-S1: Task Lease Issuance)
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class TaskLeaseRequest(BaseModel):
    """Request schema for task lease issuance"""
    task_id: UUID = Field(..., description="Task ID to lease")
    peer_id: str = Field(..., description="Requesting peer ID", min_length=1, max_length=255)
    node_address: Optional[str] = Field(None, description="Node network address")
    node_capabilities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Node capability snapshot"
    )

    @field_validator("peer_id")
    @classmethod
    def validate_peer_id(cls, v: str) -> str:
        """Validate peer_id format"""
        if not v or v.isspace():
            raise ValueError("peer_id cannot be empty or whitespace")
        return v.strip()


class TaskLeaseResponse(BaseModel):
    """Response schema for task lease issuance"""
    lease_id: UUID = Field(..., description="Unique lease identifier")
    task_id: UUID = Field(..., description="Associated task ID")
    peer_id: str = Field(..., description="Peer ID holding the lease")
    lease_token: str = Field(..., description="Signed JWT lease token")
    issued_at: datetime = Field(..., description="Lease issuance timestamp")
    expires_at: datetime = Field(..., description="Lease expiration timestamp")
    task_payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Task execution payload"
    )

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "lease_id": "123e4567-e89b-12d3-a456-426614174000",
                "task_id": "123e4567-e89b-12d3-a456-426614174001",
                "peer_id": "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG",
                "lease_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "issued_at": "2026-02-19T12:00:00Z",
                "expires_at": "2026-02-19T12:10:00Z",
                "task_payload": {"operation": "compute", "data": "..."}
            }
        }


class TaskLeaseErrorResponse(BaseModel):
    """Error response for task lease issuance failures"""
    error: str = Field(..., description="Error type")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional error context")

    class Config:
        json_schema_extra = {
            "example": {
                "error": "CAPABILITY_MISMATCH",
                "message": "Node does not meet task requirements",
                "details": {
                    "required": {"gpu": True, "memory_mb": 8192},
                    "provided": {"gpu": False, "memory_mb": 4096}
                }
            }
        }


class NodeCapabilitySnapshot(BaseModel):
    """Schema for node capability information"""
    cpu_cores: int = Field(default=1, ge=1, description="Number of CPU cores")
    memory_mb: int = Field(default=1024, ge=512, description="Available memory in MB")
    gpu_available: bool = Field(default=False, description="GPU availability")
    gpu_memory_mb: Optional[int] = Field(None, ge=0, description="GPU memory in MB")
    storage_mb: int = Field(default=10000, ge=1000, description="Available storage in MB")
    network_bandwidth_mbps: Optional[int] = Field(None, ge=0, description="Network bandwidth")

    @field_validator("gpu_memory_mb")
    @classmethod
    def validate_gpu_memory(cls, v: Optional[int], info) -> Optional[int]:
        """GPU memory must be provided if GPU is available"""
        if info.data.get("gpu_available") and v is None:
            raise ValueError("gpu_memory_mb required when gpu_available is True")
        return v


class TaskCreateRequest(BaseModel):
    """Request schema for creating a new task"""
    task_type: str = Field(..., description="Task type identifier", min_length=1, max_length=255)
    description: Optional[str] = Field(None, description="Task description")
    complexity: str = Field(default="medium", description="Task complexity: low, medium, high")
    required_capabilities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Required node capabilities"
    )
    payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Task execution payload"
    )
    priority: int = Field(default=0, ge=0, le=100, description="Task priority (0-100)")
    timeout_seconds: int = Field(default=300, ge=60, le=3600, description="Task timeout")

    @field_validator("complexity")
    @classmethod
    def validate_complexity(cls, v: str) -> str:
        """Validate complexity value"""
        allowed = ["low", "medium", "high"]
        if v.lower() not in allowed:
            raise ValueError(f"complexity must be one of {allowed}")
        return v.lower()


class TaskResponse(BaseModel):
    """Response schema for task information"""
    id: UUID
    task_type: str
    description: Optional[str]
    complexity: str
    status: str
    required_capabilities: Dict[str, Any]
    payload: Dict[str, Any]
    priority: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

# Additional schemas for E5-S7: Late Result Rejection

from enum import Enum


class TaskStatus(str, Enum):
    """Task execution status"""
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class TaskLease(BaseModel):
    """
    TaskLease Pydantic schema for validation service

    Authorizes task execution on specific node with time-bound lease.
    """
    task_id: UUID
    lease_owner_peer_id: str = Field(..., min_length=10)
    lease_token: str = Field(..., min_length=10)
    lease_expires_at: datetime
    granted_at: datetime
    heartbeat_interval: int = Field(default=30, ge=1, le=300)

    @field_validator('lease_expires_at', 'granted_at')
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware (UTC)"""
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        return v

    @field_validator('lease_expires_at')
    @classmethod
    def validate_expiration_after_grant(cls, v: datetime, info) -> datetime:
        """Ensure expiration is after grant time"""
        if 'granted_at' in info.data:
            granted_at = info.data['granted_at']
            if v <= granted_at:
                raise ValueError("lease_expires_at must be after granted_at")
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }


class TaskResult(BaseModel):
    """
    TaskResult Pydantic schema

    Contains task execution output and metadata.
    """
    task_id: UUID
    peer_id: str = Field(..., min_length=10)
    lease_token: str = Field(..., min_length=10)
    status: TaskStatus
    output_payload: Dict[str, Any]
    execution_metadata: Dict[str, Any] = Field(default_factory=dict)
    submitted_at: datetime

    @field_validator('submitted_at')
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware (UTC)"""
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v),
        }


class RejectionNotification(BaseModel):
    """
    RejectionNotification Pydantic schema

    Notifies peer of rejected task result submission.
    """
    peer_id: str = Field(..., min_length=10)
    notification_type: str = Field(default="result_rejected")
    rejection_reason: str
    task_id: str
    timestamp: datetime
    details: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_validator('timestamp')
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware (UTC)"""
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }


class RejectionLogEntry(BaseModel):
    """
    RejectionLogEntry Pydantic schema

    Structured log entry for rejected task results.
    """
    task_id: str
    peer_id: str
    reason: str
    lease_token: str
    expires_at: Optional[datetime] = None
    timestamp: datetime
    additional_info: Optional[Dict[str, Any]] = Field(default_factory=dict)

    @field_validator('timestamp')
    @classmethod
    def validate_timezone_aware(cls, v: datetime) -> datetime:
        """Ensure datetime is timezone-aware (UTC)"""
        if v.tzinfo is None:
            raise ValueError("Timestamp must be timezone-aware (UTC)")
        return v

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat(),
        }
