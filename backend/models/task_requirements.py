"""
Task Requirements Models

Defines task capability requirements, resource limits, and data scope constraints
for capability validation during task assignment.

Refs #46 (E7-S4: Capability Validation on Task Assignment)
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from enum import Enum


class ResourceType(str, Enum):
    """Resource type enumeration"""
    CPU = "cpu"
    GPU = "gpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"


class CapabilityRequirement(BaseModel):
    """
    Capability Requirement Model

    Defines specific capabilities required for task execution.
    Examples: "can_execute:llama-2-7b", "supports:gpu-compute"
    """
    capability_id: str = Field(
        ...,
        description="Capability identifier (e.g., can_execute:llama-2-7b)",
        min_length=1,
        max_length=255
    )
    required: bool = Field(
        default=True,
        description="Whether this capability is mandatory"
    )

    @field_validator("capability_id")
    @classmethod
    def validate_capability_format(cls, v: str) -> str:
        """Validate capability ID format"""
        if not v or v.isspace():
            raise ValueError("capability_id cannot be empty or whitespace")
        if ":" not in v:
            raise ValueError("capability_id must follow format 'type:value'")
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "capability_id": "can_execute:llama-2-7b",
                "required": True
            }
        }


class ResourceLimit(BaseModel):
    """
    Resource Limit Model

    Defines resource constraints and limits for task execution.
    """
    resource_type: ResourceType = Field(..., description="Type of resource")
    min_required: Optional[float] = Field(
        None,
        ge=0,
        description="Minimum required resource amount"
    )
    max_allowed: Optional[float] = Field(
        None,
        ge=0,
        description="Maximum allowed resource usage"
    )
    unit: str = Field(
        ...,
        description="Unit of measurement (e.g., MB, cores, minutes)",
        min_length=1
    )

    @field_validator("max_allowed")
    @classmethod
    def validate_max_greater_than_min(cls, v: Optional[float], info) -> Optional[float]:
        """Ensure max_allowed >= min_required"""
        if v is not None and "min_required" in info.data:
            min_required = info.data["min_required"]
            if min_required is not None and v < min_required:
                raise ValueError("max_allowed must be >= min_required")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "resource_type": "gpu",
                "min_required": 8192,
                "max_allowed": 16384,
                "unit": "MB"
            }
        }


class DataScope(BaseModel):
    """
    Data Scope Model

    Defines data access permissions and project scope for task execution.
    """
    project_id: str = Field(
        ...,
        description="Project identifier for data scope",
        min_length=1,
        max_length=255
    )
    data_classification: Optional[str] = Field(
        None,
        description="Data classification level (e.g., public, internal, confidential)",
        max_length=50
    )
    allowed_regions: Optional[List[str]] = Field(
        None,
        description="Allowed geographic regions for data processing"
    )

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: str) -> str:
        """Validate project_id format"""
        if not v or v.isspace():
            raise ValueError("project_id cannot be empty or whitespace")
        return v.strip()

    class Config:
        json_schema_extra = {
            "example": {
                "project_id": "project-alpha",
                "data_classification": "internal",
                "allowed_regions": ["us-west-2", "us-east-1"]
            }
        }


class TaskRequirements(BaseModel):
    """
    Task Requirements Model

    Complete specification of requirements for task execution including
    capabilities, resource limits, and data scope constraints.
    """
    task_id: str = Field(
        ...,
        description="Task identifier",
        min_length=1,
        max_length=255
    )
    model_name: Optional[str] = Field(
        None,
        description="AI model name if applicable (e.g., llama-2-7b)",
        max_length=255
    )
    capabilities: List[CapabilityRequirement] = Field(
        default_factory=list,
        description="Required capabilities for task execution"
    )
    resource_limits: List[ResourceLimit] = Field(
        default_factory=list,
        description="Resource constraints and limits"
    )
    data_scope: Optional[DataScope] = Field(
        None,
        description="Data access scope and permissions"
    )
    estimated_duration_minutes: Optional[int] = Field(
        None,
        ge=1,
        le=1440,
        description="Estimated task duration in minutes"
    )
    max_concurrent_tasks: Optional[int] = Field(
        None,
        ge=1,
        description="Maximum concurrent tasks allowed for assigned node"
    )

    @field_validator("task_id")
    @classmethod
    def validate_task_id(cls, v: str) -> str:
        """Validate task_id format"""
        if not v or v.isspace():
            raise ValueError("task_id cannot be empty or whitespace")
        return v.strip()

    def get_gpu_memory_requirement(self) -> Optional[float]:
        """Extract GPU memory requirement from resource limits"""
        for limit in self.resource_limits:
            if limit.resource_type == ResourceType.GPU and limit.unit.upper() == "MB":
                return limit.min_required
        return None

    def requires_capability(self, capability_id: str) -> bool:
        """Check if specific capability is required"""
        for cap in self.capabilities:
            if cap.capability_id == capability_id and cap.required:
                return True
        return False

    def get_required_capabilities(self) -> List[str]:
        """Get list of all required capability IDs"""
        return [cap.capability_id for cap in self.capabilities if cap.required]

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "task-123",
                "model_name": "llama-2-7b",
                "capabilities": [
                    {
                        "capability_id": "can_execute:llama-2-7b",
                        "required": True
                    }
                ],
                "resource_limits": [
                    {
                        "resource_type": "gpu",
                        "min_required": 8192,
                        "max_allowed": 16384,
                        "unit": "MB"
                    },
                    {
                        "resource_type": "gpu",
                        "min_required": 100,
                        "max_allowed": 500,
                        "unit": "minutes"
                    }
                ],
                "data_scope": {
                    "project_id": "project-alpha",
                    "data_classification": "internal"
                },
                "estimated_duration_minutes": 30,
                "max_concurrent_tasks": 3
            }
        }


class CapabilityToken(BaseModel):
    """
    Capability Token Model

    Represents node's capability token with authorized capabilities,
    resource limits, and data scope permissions.

    This is a placeholder for E7-S1 implementation.
    """
    peer_id: str = Field(..., description="Peer identifier", min_length=1)
    capabilities: List[str] = Field(
        default_factory=list,
        description="List of authorized capabilities"
    )
    limits: Dict[str, Any] = Field(
        default_factory=dict,
        description="Resource limits (max_gpu_minutes, max_concurrent_tasks, etc.)"
    )
    data_scopes: List[str] = Field(
        default_factory=list,
        description="Authorized data scopes/projects"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "peer_id": "QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG",
                "capabilities": [
                    "can_execute:llama-2-7b",
                    "can_execute:stable-diffusion"
                ],
                "limits": {
                    "max_gpu_minutes": 1000,
                    "max_concurrent_tasks": 5,
                    "max_gpu_memory_mb": 16384
                },
                "data_scopes": ["project-alpha", "project-beta"]
            }
        }


class ValidationResult(BaseModel):
    """
    Validation Result Model

    Result of capability validation check with detailed error information.
    """
    is_valid: bool = Field(..., description="Whether validation passed")
    error_code: Optional[str] = Field(
        None,
        description="Error code if validation failed"
    )
    error_message: Optional[str] = Field(
        None,
        description="Human-readable error message"
    )
    missing_capabilities: List[str] = Field(
        default_factory=list,
        description="List of missing required capabilities"
    )
    resource_violations: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of resource limit violations"
    )
    scope_violations: List[str] = Field(
        default_factory=list,
        description="List of data scope violations"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "is_valid": False,
                "error_code": "CAPABILITY_MISSING",
                "error_message": "Node missing required capability: can_execute:llama-2-7b",
                "missing_capabilities": ["can_execute:llama-2-7b"],
                "resource_violations": [],
                "scope_violations": []
            }
        }
