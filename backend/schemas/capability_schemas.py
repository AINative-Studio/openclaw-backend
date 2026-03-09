"""
Pydantic schemas for capability validation and token rotation endpoints.

Provides request/response models for:
- Capability validation (POST /capabilities/validate)
- Token rotation (POST /tokens/rotate)

Refs: Issue #122 - MCP Evaluation (native tools approach)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator


class CapabilityRequirementSchema(BaseModel):
    """A single capability requirement for a task."""

    capability_id: str = Field(..., description="Capability identifier (format: type:value)")
    required: bool = Field(default=True, description="Whether this capability is mandatory")

    @field_validator("capability_id")
    @classmethod
    def validate_capability_format(cls, v: str) -> str:
        """Validate capability ID format (should be type:value)."""
        if ":" not in v:
            raise ValueError("capability_id must be in format 'type:value' (e.g., 'model:claude-3-5-sonnet')")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "capability_id": "model:claude-3-5-sonnet",
                "required": True
            }
        }


class ResourceLimitSchema(BaseModel):
    """Resource limit constraint for a task."""

    resource_type: str = Field(..., description="Resource type (CPU/GPU/MEMORY/STORAGE/NETWORK)")
    min_required: int = Field(..., ge=0, description="Minimum amount required")
    max_allowed: Optional[int] = Field(None, ge=0, description="Maximum amount allowed")
    unit: str = Field(..., description="Unit of measurement (cores, MB, GB, etc.)")

    @field_validator("resource_type")
    @classmethod
    def validate_resource_type(cls, v: str) -> str:
        """Validate resource type is one of known types."""
        allowed = {"CPU", "GPU", "MEMORY", "STORAGE", "NETWORK"}
        if v.upper() not in allowed:
            raise ValueError(f"resource_type must be one of {allowed}")
        return v.upper()

    class Config:
        json_schema_extra = {
            "example": {
                "resource_type": "GPU",
                "min_required": 8192,
                "max_allowed": 16384,
                "unit": "MB"
            }
        }


class CapabilityValidateRequest(BaseModel):
    """Request to validate node capabilities against task requirements."""

    task_id: str = Field(..., description="Task UUID or identifier")
    node_peer_id: str = Field(..., description="Peer ID of the node to validate")
    required_capabilities: List[CapabilityRequirementSchema] = Field(
        default_factory=list,
        description="List of required capabilities"
    )
    resource_limits: List[ResourceLimitSchema] = Field(
        default_factory=list,
        description="List of resource constraints"
    )
    node_usage: Optional[Dict[str, Any]] = Field(
        None,
        description="Current resource usage by the node (for concurrent task checks)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "node_peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "required_capabilities": [
                    {
                        "capability_id": "model:claude-3-5-sonnet",
                        "required": True
                    },
                    {
                        "capability_id": "feature:code-execution",
                        "required": False
                    }
                ],
                "resource_limits": [
                    {
                        "resource_type": "GPU",
                        "min_required": 8192,
                        "max_allowed": 16384,
                        "unit": "MB"
                    },
                    {
                        "resource_type": "MEMORY",
                        "min_required": 16384,
                        "max_allowed": None,
                        "unit": "MB"
                    }
                ],
                "node_usage": {
                    "current_tasks": 2,
                    "gpu_minutes_used": 450
                }
            }
        }


class CapabilityValidateResponse(BaseModel):
    """Response from capability validation."""

    is_valid: bool = Field(..., description="Whether node meets all requirements")
    task_id: str = Field(..., description="Task UUID that was validated")
    node_peer_id: str = Field(..., description="Peer ID of the validated node")
    missing_capabilities: List[str] = Field(
        default_factory=list,
        description="List of required capabilities that are missing"
    )
    resource_violations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of resource constraints that are violated"
    )
    error_message: Optional[str] = Field(None, description="Error description if validation failed")

    class Config:
        json_schema_extra = {
            "example": {
                "is_valid": False,
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "node_peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "missing_capabilities": ["model:claude-3-5-sonnet"],
                "resource_violations": [
                    {
                        "resource_type": "GPU",
                        "required": 8192,
                        "available": 4096,
                        "unit": "MB"
                    }
                ],
                "error_message": "Node does not meet task requirements: missing capabilities, insufficient GPU memory"
            }
        }


class TokenRotateRequest(BaseModel):
    """Request to rotate a capability token."""

    token: str = Field(..., min_length=10, description="Current capability token (JWT)")
    extends_by_seconds: int = Field(
        default=3600,
        ge=300,
        le=86400,
        description="Extend expiration by this many seconds (5min to 24h)"
    )
    grace_period_seconds: int = Field(
        default=300,
        ge=0,
        le=3600,
        description="Grace period where old token remains valid (0 to 1h)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "extends_by_seconds": 3600,
                "grace_period_seconds": 300
            }
        }


class TokenRotateResponse(BaseModel):
    """Response after rotating a token."""

    new_token: str = Field(..., description="New capability token (JWT)")
    old_token_jti: str = Field(..., description="JTI of the revoked old token")
    new_token_jti: str = Field(..., description="JTI of the new token")
    peer_id: str = Field(..., description="Peer ID associated with the token")
    new_expires_at: datetime = Field(..., description="Expiration time of new token")
    grace_period_ends_at: datetime = Field(..., description="When old token becomes fully invalid")
    capabilities: List[str] = Field(..., description="Capabilities granted in new token")

    class Config:
        json_schema_extra = {
            "example": {
                "new_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.new...",
                "old_token_jti": "old_abc123xyz",
                "new_token_jti": "new_def456uvw",
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "new_expires_at": "2026-03-08T13:15:00Z",
                "grace_period_ends_at": "2026-03-08T12:20:00Z",
                "capabilities": [
                    "model:claude-3-5-sonnet",
                    "feature:code-execution",
                    "data:project-123"
                ]
            }
        }


class TokenValidateRequest(BaseModel):
    """Request to validate a capability token."""

    token: str = Field(..., min_length=10, description="Capability token to validate")
    required_capability: Optional[str] = Field(None, description="Check for specific capability")
    required_data_access: Optional[str] = Field(None, description="Check for specific data scope access")

    class Config:
        json_schema_extra = {
            "example": {
                "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "required_capability": "model:claude-3-5-sonnet",
                "required_data_access": "project-123"
            }
        }


class TokenValidateResponse(BaseModel):
    """Response from token validation."""

    is_valid: bool = Field(..., description="Whether token is valid")
    jti: Optional[str] = Field(None, description="Token JTI if valid")
    peer_id: Optional[str] = Field(None, description="Peer ID if valid")
    expires_at: Optional[datetime] = Field(None, description="Expiration time if valid")
    is_expired: bool = Field(default=False, description="Whether token has expired")
    is_revoked: bool = Field(default=False, description="Whether token has been revoked")
    has_required_capability: Optional[bool] = Field(None, description="If capability check was requested")
    has_required_data_access: Optional[bool] = Field(None, description="If data access check was requested")
    error_message: Optional[str] = Field(None, description="Error description if invalid")

    class Config:
        json_schema_extra = {
            "example": {
                "is_valid": True,
                "jti": "abc123xyz",
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "expires_at": "2026-03-08T13:15:00Z",
                "is_expired": False,
                "is_revoked": False,
                "has_required_capability": True,
                "has_required_data_access": True,
                "error_message": None
            }
        }
