"""
Agent Lifecycle API Schemas

Pydantic v2 request/response models for the agent CRUD REST API.
Maps to frontend OpenClawAgent type definitions.
"""

from typing import Optional
from pydantic import BaseModel, Field


class HeartbeatConfig(BaseModel):
    """Heartbeat configuration for agent creation/update"""
    enabled: bool
    interval: Optional[str] = None
    checklist: Optional[list[str]] = None


class CreateAgentRequest(BaseModel):
    """Request body for POST /agents"""
    name: str = Field(..., min_length=1, max_length=255)
    persona: Optional[str] = None
    model: str = Field(..., min_length=1, max_length=255)
    heartbeat: Optional[HeartbeatConfig] = None
    configuration: Optional[dict] = None


class UpdateAgentSettingsRequest(BaseModel):
    """Request body for PATCH /agents/{agent_id}/settings"""
    persona: Optional[str] = None
    model: Optional[str] = None
    heartbeat: Optional[HeartbeatConfig] = None
    configuration: Optional[dict] = None


class AgentResponse(BaseModel):
    """Single agent response matching frontend OpenClawAgent type"""
    id: str
    name: str
    persona: Optional[str] = None
    model: str
    user_id: str
    status: str
    openclaw_session_key: Optional[str] = None
    openclaw_agent_id: Optional[str] = None
    heartbeat_enabled: bool
    heartbeat_interval: Optional[str] = None
    heartbeat_checklist: Optional[list[str]] = None
    last_heartbeat_at: Optional[str] = None
    next_heartbeat_at: Optional[str] = None
    configuration: Optional[dict] = None
    error_message: Optional[str] = None
    error_count: int = 0
    created_at: str
    updated_at: Optional[str] = None
    provisioned_at: Optional[str] = None
    paused_at: Optional[str] = None
    stopped_at: Optional[str] = None


class AgentListResponse(BaseModel):
    """Paginated agent list response"""
    agents: list[AgentResponse]
    total: int
    limit: int
    offset: int


class AgentStatusResponse(BaseModel):
    """Status change response"""
    id: str
    name: str
    status: str
    message: str


class HeartbeatExecutionResponse(BaseModel):
    """Heartbeat execution response"""
    status: str
    message: str
