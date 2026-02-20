"""
Agent Swarm API Schemas

Pydantic v2 request/response models for the swarm CRUD REST API.
Maps to frontend AgentSwarm type definitions.
"""

from typing import Optional
from pydantic import BaseModel, Field


class CreateSwarmRequest(BaseModel):
    """Request body for POST /swarms"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    strategy: str = Field(..., min_length=1, max_length=50)
    goal: Optional[str] = None
    agent_ids: list[str] = []
    configuration: Optional[dict] = None


class UpdateSwarmRequest(BaseModel):
    """Request body for PATCH /swarms/{swarm_id}"""
    name: Optional[str] = None
    description: Optional[str] = None
    strategy: Optional[str] = None
    goal: Optional[str] = None
    configuration: Optional[dict] = None


class AddAgentsRequest(BaseModel):
    """Request body for POST /swarms/{swarm_id}/agents"""
    agent_ids: list[str] = Field(..., min_length=1)


class RemoveAgentsRequest(BaseModel):
    """Request body for DELETE /swarms/{swarm_id}/agents"""
    agent_ids: list[str] = Field(..., min_length=1)


class SwarmResponse(BaseModel):
    """Single swarm response matching frontend AgentSwarm type"""
    id: str
    name: str
    description: Optional[str] = None
    strategy: str
    goal: Optional[str] = None
    status: str
    agent_ids: list[str] = []
    agent_count: int = 0
    user_id: str
    configuration: Optional[dict] = None
    error_message: Optional[str] = None
    created_at: str
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    paused_at: Optional[str] = None
    stopped_at: Optional[str] = None


class SwarmListResponse(BaseModel):
    """Paginated swarm list response"""
    swarms: list[SwarmResponse]
    total: int
    limit: int
    offset: int
