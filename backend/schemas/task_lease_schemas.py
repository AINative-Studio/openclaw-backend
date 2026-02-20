"""
Task Lease Schemas

Pydantic schemas specific for E5-S1 task lease issuance.

Refs #27 (E5-S1: Task Lease Issuance)
"""

from datetime import datetime
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class TaskLeaseRequest(BaseModel):
    """Request schema for task lease issuance"""
    task_id: str = Field(..., description="Task ID to lease")
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
    lease_id: Any = Field(..., description="Unique lease identifier")
    task_id: str = Field(..., description="Associated task ID")
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
                "lease_id": 1,
                "task_id": "task-123e4567",
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
