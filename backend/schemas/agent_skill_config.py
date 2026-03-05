"""
Pydantic schemas for Agent Skill Configuration API
"""

from pydantic import BaseModel, Field, field_validator
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime


class SkillConfigurationRequest(BaseModel):
    """Request to configure a skill for an agent"""

    # Sensitive credentials (will be encrypted)
    api_key: Optional[str] = Field(None, description="API key for the skill")
    access_token: Optional[str] = Field(None, description="OAuth access token")
    refresh_token: Optional[str] = Field(None, description="OAuth refresh token")
    credentials: Optional[Dict[str, Any]] = Field(
        None, description="Additional credentials as key-value pairs"
    )

    # Non-sensitive configuration
    config: Optional[Dict[str, Any]] = Field(
        None, description="Additional configuration as key-value pairs"
    )

    # Whether to enable the skill
    enabled: bool = Field(True, description="Enable the skill for this agent")

    def get_credentials_dict(self) -> Dict[str, Any]:
        """
        Build credentials dictionary from individual fields

        Returns:
            Dictionary with all credential fields
        """
        creds = {}

        if self.api_key:
            creds["api_key"] = self.api_key
        if self.access_token:
            creds["access_token"] = self.access_token
        if self.refresh_token:
            creds["refresh_token"] = self.refresh_token
        if self.credentials:
            creds.update(self.credentials)

        return creds if creds else None


class SkillConfigurationResponse(BaseModel):
    """Response with skill configuration (credentials redacted)"""

    id: UUID
    agent_id: UUID
    skill_name: str
    enabled: bool

    # Configuration (non-sensitive)
    config: Optional[Dict[str, Any]] = None

    # Indicate if credentials are set (but don't return them)
    has_credentials: bool = Field(
        description="Whether credentials are configured (actual values not returned)"
    )

    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SkillConfigurationSummary(BaseModel):
    """Summary of skill configuration status for an agent"""

    skill_name: str
    enabled: bool
    has_credentials: bool
    config: Optional[Dict[str, Any]] = None


class AgentSkillsConfigResponse(BaseModel):
    """Response listing all skill configurations for an agent"""

    agent_id: UUID
    total_skills: int
    enabled_skills: int
    configured_skills: int  # Skills with credentials set
    skills: list[SkillConfigurationSummary]
