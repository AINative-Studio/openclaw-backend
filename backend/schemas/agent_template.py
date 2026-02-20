"""
Agent Template API Schemas

Pydantic v2 request/response models for the template CRUD REST API.
Maps to frontend OpenClawTemplate type definitions.
"""

from typing import Optional
from pydantic import BaseModel, Field


class CreateTemplateRequest(BaseModel):
    """Request body for POST /templates"""
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    category: str = Field(..., min_length=1, max_length=50)
    icons: list[str] = []
    default_model: str = Field(default="anthropic/claude-opus-4-5", max_length=255)
    default_persona: Optional[str] = None
    default_heartbeat_interval: Optional[str] = Field(default="5m", max_length=10)
    default_checklist: list[str] = []


class UpdateTemplateRequest(BaseModel):
    """Request body for PATCH /templates/{template_id}"""
    name: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=50)
    icons: Optional[list[str]] = None
    default_model: Optional[str] = Field(default=None, max_length=255)
    default_persona: Optional[str] = None
    default_heartbeat_interval: Optional[str] = Field(default=None, max_length=10)
    default_checklist: Optional[list[str]] = None


class TemplateResponse(BaseModel):
    """Single template response matching frontend OpenClawTemplate type"""
    id: str
    name: str
    description: Optional[str] = None
    category: str
    icons: list[str]
    default_model: str
    default_persona: Optional[str] = None
    default_heartbeat_interval: Optional[str] = None
    default_checklist: list[str]
    user_id: str
    created_at: str
    updated_at: Optional[str] = None


class TemplateListResponse(BaseModel):
    """Paginated template list response"""
    templates: list[TemplateResponse]
    total: int
    limit: int
    offset: int
