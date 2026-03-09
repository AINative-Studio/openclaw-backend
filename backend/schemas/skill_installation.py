"""
Skill Installation Schemas

Pydantic models for skill installation requests and responses.

Security: Issue #131 - Input validation for skill names and paths
"""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field, field_validator
from backend.validators import validate_alphanumeric_id


class SkillInstallRequest(BaseModel):
    """
    Request to install a skill

    Security: Issue #131 - Validates timeout ranges
    """
    force: bool = Field(
        default=False,
        description="Force reinstallation even if already installed"
    )
    timeout: int = Field(
        default=300,
        ge=30,
        le=600,
        description="Installation timeout in seconds (30-600, validated)"
    )


class SkillInstallResponse(BaseModel):
    """
    Response from skill installation attempt

    Security: Issue #131 - Validates method enum and log size
    """
    success: bool = Field(
        description="Whether the installation succeeded"
    )
    message: str = Field(
        max_length=1000,
        description="Human-readable success/error message"
    )
    logs: List[str] = Field(
        default_factory=list,
        max_length=100,
        description="Installation logs (stdout/stderr, max 100 lines)"
    )
    method: Optional[Literal["go", "npm", "pip", "manual"]] = Field(
        None,
        description="Installation method used (enforced enum)"
    )
    package: Optional[str] = Field(
        None,
        max_length=500,
        description="Package name/path that was installed"
    )


class SkillInstallInfoResponse(BaseModel):
    """Information about how to install a skill"""
    skill_name: str = Field(
        description="Name of the skill"
    )
    method: str = Field(
        description="Installation method (go, npm, manual)"
    )
    package: Optional[str] = Field(
        None,
        description="Package name/path for auto-installable skills"
    )
    description: str = Field(
        description="Description of the skill"
    )
    installable: bool = Field(
        description="Whether the skill can be auto-installed"
    )
    docs: Optional[str] = Field(
        None,
        description="Documentation URL for manual installation"
    )
    requirements: Optional[List[str]] = Field(
        None,
        description="List of requirements for manual installation"
    )


class SkillInstallProgress(BaseModel):
    """
    Progress update for streaming installation
    (Future enhancement - not implemented yet)

    Security: Issue #131 - Validates status enum and progress range
    """
    skill_name: str = Field(max_length=255)
    status: Literal["queued", "installing", "completed", "failed"] = Field(
        description="Status (enforced enum)"
    )
    progress_percent: int = Field(
        ge=0,
        le=100,
        description="Installation progress percentage (0-100)"
    )
    current_step: str = Field(
        max_length=500,
        description="Current installation step"
    )
    logs: List[str] = Field(
        default_factory=list,
        max_length=20,
        description="Recent log lines (max 20)"
    )


class SkillListResponse(BaseModel):
    """List of all installable skills"""
    skills: List[SkillInstallInfoResponse] = Field(
        description="List of skill installation information"
    )
    total: int = Field(
        description="Total number of skills"
    )
    auto_installable: int = Field(
        description="Number of auto-installable skills"
    )
    manual: int = Field(
        description="Number of manual installation skills"
    )
