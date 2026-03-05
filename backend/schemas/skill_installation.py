"""
Skill Installation Schemas

Pydantic models for skill installation requests and responses.
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SkillInstallRequest(BaseModel):
    """Request to install a skill"""
    force: bool = Field(
        default=False,
        description="Force reinstallation even if already installed"
    )
    timeout: int = Field(
        default=300,
        ge=30,
        le=600,
        description="Installation timeout in seconds (30-600)"
    )


class SkillInstallResponse(BaseModel):
    """Response from skill installation attempt"""
    success: bool = Field(
        description="Whether the installation succeeded"
    )
    message: str = Field(
        description="Human-readable success/error message"
    )
    logs: List[str] = Field(
        default_factory=list,
        description="Installation logs (stdout/stderr)"
    )
    method: Optional[str] = Field(
        None,
        description="Installation method used (go, npm, manual)"
    )
    package: Optional[str] = Field(
        None,
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
    """
    skill_name: str
    status: str = Field(
        description="Status: queued, installing, completed, failed"
    )
    progress_percent: int = Field(
        ge=0,
        le=100,
        description="Installation progress percentage"
    )
    current_step: str = Field(
        description="Current installation step"
    )
    logs: List[str] = Field(
        default_factory=list,
        description="Recent log lines"
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
