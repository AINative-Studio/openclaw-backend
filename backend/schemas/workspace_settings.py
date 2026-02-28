"""Workspace Settings Schemas"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class WorkspaceSettingsBase(BaseModel):
    """Base workspace settings"""
    workspace_name: str = Field(..., min_length=1, max_length=255)
    workspace_slug: str = Field(..., pattern="^[a-z0-9-]+$", min_length=1, max_length=100)
    default_model: str = Field(default="anthropic/claude-sonnet-4-6")
    timezone: str = Field(default="UTC")
    email_notifications: bool = True
    agent_error_alerts: bool = True
    heartbeat_fail_alerts: bool = True
    weekly_digest: bool = False


class WorkspaceSettingsUpdate(BaseModel):
    """Update workspace settings (all fields optional)"""
    workspace_name: Optional[str] = Field(None, min_length=1, max_length=255)
    workspace_slug: Optional[str] = Field(None, pattern="^[a-z0-9-]+$", min_length=1, max_length=100)
    default_model: Optional[str] = None
    timezone: Optional[str] = None
    email_notifications: Optional[bool] = None
    agent_error_alerts: Optional[bool] = None
    heartbeat_fail_alerts: Optional[bool] = None
    weekly_digest: Optional[bool] = None


class WorkspaceSettingsResponse(WorkspaceSettingsBase):
    """Workspace settings response"""
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
