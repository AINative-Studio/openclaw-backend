"""
Pydantic schemas for lease management endpoints.

Provides request/response models for:
- Lease issuance (POST /leases/issue)
- Lease validation (GET /leases/{lease_id}/validate)
- Lease revocation (POST /leases/{lease_id}/revoke)

Refs: Issue #122 - MCP Evaluation (native tools approach)
"""

from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator


class NodeCapabilitiesSnapshot(BaseModel):
    """Snapshot of node capabilities at lease issuance time."""

    cpu_cores: int = Field(..., ge=1, description="Number of CPU cores available")
    memory_mb: int = Field(..., ge=512, description="RAM in megabytes")
    gpu_available: bool = Field(default=False, description="Whether GPU is available")
    gpu_memory_mb: Optional[int] = Field(None, ge=0, description="GPU memory in MB if available")
    storage_mb: int = Field(..., ge=1024, description="Available storage in MB")

    class Config:
        json_schema_extra = {
            "example": {
                "cpu_cores": 8,
                "memory_mb": 16384,
                "gpu_available": True,
                "gpu_memory_mb": 8192,
                "storage_mb": 102400
            }
        }


class LeaseIssueRequest(BaseModel):
    """Request to issue a new task lease."""

    task_id: UUID = Field(..., description="UUID of the task to lease")
    peer_id: str = Field(..., min_length=1, max_length=255, description="Peer ID requesting the lease")
    node_capabilities: Optional[NodeCapabilitiesSnapshot] = Field(
        None,
        description="Optional node capabilities for validation"
    )

    @field_validator("peer_id")
    @classmethod
    def validate_peer_id_format(cls, v: str) -> str:
        """Validate peer ID format (should start with 12D3KooW for libp2p)."""
        if not v.startswith("12D3KooW"):
            raise ValueError("peer_id must be a valid libp2p peer ID starting with 12D3KooW")
        if len(v) < 20:
            raise ValueError("peer_id appears to be too short for a valid libp2p ID")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "node_capabilities": {
                    "cpu_cores": 8,
                    "memory_mb": 16384,
                    "gpu_available": True,
                    "gpu_memory_mb": 8192,
                    "storage_mb": 102400
                }
            }
        }


class LeaseIssueResponse(BaseModel):
    """Response after successfully issuing a lease."""

    lease_id: UUID = Field(..., description="UUID of the created lease")
    lease_token: str = Field(..., description="JWT token for lease authentication")
    task_id: UUID = Field(..., description="UUID of the leased task")
    peer_id: str = Field(..., description="Peer ID that owns the lease")
    expires_at: datetime = Field(..., description="Lease expiration timestamp (UTC)")
    task_complexity: str = Field(..., description="Task complexity level (LOW/MEDIUM/HIGH)")
    lease_duration_seconds: int = Field(..., ge=1, description="Lease duration in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "lease_id": "660e8400-e29b-41d4-a716-446655440000",
                "lease_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "expires_at": "2026-03-08T12:15:00Z",
                "task_complexity": "MEDIUM",
                "lease_duration_seconds": 600
            }
        }


class LeaseValidateRequest(BaseModel):
    """Request to validate a lease token."""

    lease_token: str = Field(..., min_length=10, description="JWT lease token to validate")
    task_id: Optional[UUID] = Field(None, description="Optional task ID to verify ownership")
    peer_id: Optional[str] = Field(None, description="Optional peer ID to verify ownership")

    class Config:
        json_schema_extra = {
            "example": {
                "lease_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI"
            }
        }


class LeaseValidateResponse(BaseModel):
    """Response from lease validation."""

    is_valid: bool = Field(..., description="Whether the lease is valid")
    lease_id: Optional[UUID] = Field(None, description="Lease UUID if valid")
    task_id: Optional[UUID] = Field(None, description="Task UUID if valid")
    peer_id: Optional[str] = Field(None, description="Peer ID if valid")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp if valid")
    is_expired: bool = Field(default=False, description="Whether the lease has expired")
    is_revoked: bool = Field(default=False, description="Whether the lease has been revoked")
    error_message: Optional[str] = Field(None, description="Error description if invalid")

    class Config:
        json_schema_extra = {
            "example": {
                "is_valid": True,
                "lease_id": "660e8400-e29b-41d4-a716-446655440000",
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "expires_at": "2026-03-08T12:15:00Z",
                "is_expired": False,
                "is_revoked": False,
                "error_message": None
            }
        }


class LeaseRevokeRequest(BaseModel):
    """Request to revoke a lease."""

    reason: str = Field(..., min_length=1, max_length=500, description="Reason for revocation")
    requeue_task: bool = Field(default=True, description="Whether to requeue the task after revocation")

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "Node crashed - detected heartbeat timeout",
                "requeue_task": True
            }
        }


class LeaseRevokeResponse(BaseModel):
    """Response after revoking a lease."""

    lease_id: UUID = Field(..., description="UUID of the revoked lease")
    task_id: UUID = Field(..., description="UUID of the associated task")
    peer_id: str = Field(..., description="Peer ID that owned the lease")
    revoked_at: datetime = Field(..., description="Timestamp when lease was revoked")
    reason: str = Field(..., description="Revocation reason")
    task_requeued: bool = Field(..., description="Whether the task was requeued")
    task_status: str = Field(..., description="Current task status after revocation")

    class Config:
        json_schema_extra = {
            "example": {
                "lease_id": "660e8400-e29b-41d4-a716-446655440000",
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "revoked_at": "2026-03-08T12:10:00Z",
                "reason": "Node crashed - detected heartbeat timeout",
                "task_requeued": True,
                "task_status": "queued"
            }
        }


class LeaseStatsResponse(BaseModel):
    """Statistics about lease system."""

    active_leases: int = Field(..., ge=0, description="Number of currently active leases")
    expired_leases: int = Field(..., ge=0, description="Number of expired leases")
    revoked_leases: int = Field(..., ge=0, description="Number of revoked leases")
    total_leases_issued: int = Field(..., ge=0, description="Total leases issued (all time)")
    avg_lease_duration_seconds: Optional[float] = Field(None, description="Average lease duration")

    class Config:
        json_schema_extra = {
            "example": {
                "active_leases": 15,
                "expired_leases": 3,
                "revoked_leases": 2,
                "total_leases_issued": 120,
                "avg_lease_duration_seconds": 580.5
            }
        }
