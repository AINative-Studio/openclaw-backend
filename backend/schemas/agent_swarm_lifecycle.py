"""
Agent Swarm Lifecycle Schemas

Pydantic v2 models for agent swarm lifecycle operations including
provisioning, heartbeat configuration, and status management.

Refs #1213
"""

from typing import Optional, List
from enum import Enum
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime


class HeartbeatIntervalEnum(str, Enum):
    """Heartbeat interval enumeration for API requests"""
    FIVE_MINUTES = "5m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    ONE_HOUR = "1h"
    TWO_HOURS = "2h"


class HeartbeatConfig(BaseModel):
    """Heartbeat configuration for agent creation/update"""
    enabled: bool
    interval: Optional[HeartbeatIntervalEnum] = None
    checklist: Optional[List[str]] = None


class AgentProvisionRequest(BaseModel):
    """Request to provision a new agent swarm instance"""
    name: str = Field(..., min_length=1, max_length=255)
    persona: Optional[str] = None
    model: str = Field(..., min_length=1, max_length=255)
    heartbeat: Optional[HeartbeatConfig] = None
    configuration: Optional[dict] = None
    workspace_id: Optional[UUID] = None


class AgentUpdateSettingsRequest(BaseModel):
    """Request to update agent settings"""
    persona: Optional[str] = None
    model: Optional[str] = None
    heartbeat: Optional[HeartbeatConfig] = None
    configuration: Optional[dict] = None


class AgentProvisionResponse(BaseModel):
    """Response for agent provisioning"""
    id: UUID
    name: str
    status: str
    message: str
    openclaw_session_key: Optional[str] = None
    openclaw_agent_id: Optional[str] = None


class AgentDetailResponse(BaseModel):
    """Detailed agent response"""
    id: UUID
    name: str
    persona: Optional[str] = None
    model: str
    user_id: UUID
    workspace_id: Optional[UUID] = None
    status: str
    openclaw_session_key: Optional[str] = None
    openclaw_agent_id: Optional[str] = None
    heartbeat_enabled: bool
    heartbeat_interval: Optional[str] = None
    heartbeat_checklist: Optional[List[str]] = None
    last_heartbeat_at: Optional[datetime] = None
    next_heartbeat_at: Optional[datetime] = None
    configuration: Optional[dict] = None
    error_message: Optional[str] = None
    error_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    provisioned_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    stopped_at: Optional[datetime] = None


class AgentStatusResponse(BaseModel):
    """Response for agent status changes"""
    id: UUID
    name: str
    status: str
    message: str
    openclaw_agent_id: Optional[str] = None


class HeartbeatExecutionResponse(BaseModel):
    """Response for heartbeat execution"""
    id: UUID
    agent_id: UUID
    status: str
    checklist_items: Optional[List[str]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    error_message: Optional[str] = None


# Backwards compatibility aliases for agent_lifecycle.py endpoint
class CreateAgentRequest(BaseModel):
    """Request body for POST /agents (alias for AgentProvisionRequest)"""
    name: str = Field(..., min_length=1, max_length=255)
    persona: Optional[str] = None
    model: str = Field(..., min_length=1, max_length=255)
    heartbeat: Optional[HeartbeatConfig] = None
    configuration: Optional[dict] = None
    workspace_id: Optional[UUID] = None


class UpdateAgentSettingsRequest(BaseModel):
    """Request body for PATCH /agents/{agent_id}/settings (alias)"""
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
    workspace_id: Optional[str] = None
    status: str
    openclaw_session_key: Optional[str] = None
    openclaw_agent_id: Optional[str] = None
    heartbeat_enabled: bool
    heartbeat_interval: Optional[str] = None
    heartbeat_checklist: Optional[List[str]] = None
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
    agents: List[AgentResponse]
    total: int
    limit: int
    offset: int
