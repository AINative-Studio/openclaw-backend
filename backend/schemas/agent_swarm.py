"""
Agent Swarm API Schemas

Pydantic v2 request/response models for the swarm CRUD REST API.
Maps to frontend AgentSwarm type definitions.

Security: Issue #131 - Input validation and XSS prevention
"""

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator
from backend.validators import sanitize_html, validate_safe_json_metadata, validate_alphanumeric_id


class CreateSwarmRequest(BaseModel):
    """
    Request body for POST /swarms

    Security: Issue #131 - Sanitizes HTML, validates configuration structure
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Swarm name (XSS sanitized)"
    )
    description: Optional[str] = Field(
        None,
        max_length=2000,
        description="Swarm description (XSS sanitized)"
    )
    strategy: Literal[
        "sequential", "parallel", "hierarchical", "democratic", "custom"
    ] = Field(
        ...,
        description="Swarm coordination strategy (enforced enum)"
    )
    goal: Optional[str] = Field(
        None,
        max_length=1000,
        description="Swarm goal (XSS sanitized)"
    )
    agent_ids: list[str] = Field(
        default_factory=list,
        max_length=100,
        description="List of agent IDs (validated alphanumeric)"
    )
    configuration: Optional[dict] = Field(
        None,
        description="Swarm configuration (validated structure)"
    )

    @field_validator('name', 'description', 'goal')
    @classmethod
    def sanitize_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize text fields to prevent XSS attacks (Issue #131)."""
        if v is None:
            return v
        return sanitize_html(v)

    @field_validator('agent_ids')
    @classmethod
    def validate_agent_ids(cls, v: list[str]) -> list[str]:
        """Validate agent IDs are alphanumeric with dashes/underscores (Issue #131)."""
        validated = []
        for agent_id in v:
            validated.append(validate_alphanumeric_id(agent_id, allow_dash=True, allow_underscore=True))
        return validated

    @field_validator('configuration')
    @classmethod
    def validate_configuration(cls, v: Optional[dict]) -> Optional[dict]:
        """
        Validate configuration structure to prevent DoS attacks (Issue #131).

        Enforces:
            - Max depth: 4 levels (swarms may have complex configs)
            - Max keys: 100 total
            - Max string length: 2000 chars
        """
        if v is None:
            return v
        return validate_safe_json_metadata(v, max_depth=4, max_keys=100, max_value_length=2000)


class UpdateSwarmRequest(BaseModel):
    """
    Request body for PATCH /swarms/{swarm_id}

    Security: Issue #131 - Same validation as CreateSwarmRequest
    """
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    strategy: Optional[Literal[
        "sequential", "parallel", "hierarchical", "democratic", "custom"
    ]] = None
    goal: Optional[str] = Field(None, max_length=1000)
    configuration: Optional[dict] = None

    @field_validator('name', 'description', 'goal')
    @classmethod
    def sanitize_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize text fields to prevent XSS attacks (Issue #131)."""
        if v is None:
            return v
        return sanitize_html(v)

    @field_validator('configuration')
    @classmethod
    def validate_configuration(cls, v: Optional[dict]) -> Optional[dict]:
        """Validate configuration structure (Issue #131)."""
        if v is None:
            return v
        return validate_safe_json_metadata(v, max_depth=4, max_keys=100, max_value_length=2000)


class AddAgentsRequest(BaseModel):
    """
    Request body for POST /swarms/{swarm_id}/agents

    Security: Issue #131 - Validates agent IDs
    """
    agent_ids: list[str] = Field(..., min_length=1, max_length=100)

    @field_validator('agent_ids')
    @classmethod
    def validate_agent_ids(cls, v: list[str]) -> list[str]:
        """Validate agent IDs are alphanumeric (Issue #131)."""
        validated = []
        for agent_id in v:
            validated.append(validate_alphanumeric_id(agent_id, allow_dash=True, allow_underscore=True))
        return validated


class RemoveAgentsRequest(BaseModel):
    """
    Request body for DELETE /swarms/{swarm_id}/agents

    Security: Issue #131 - Validates agent IDs
    """
    agent_ids: list[str] = Field(..., min_length=1, max_length=100)

    @field_validator('agent_ids')
    @classmethod
    def validate_agent_ids(cls, v: list[str]) -> list[str]:
        """Validate agent IDs are alphanumeric (Issue #131)."""
        validated = []
        for agent_id in v:
            validated.append(validate_alphanumeric_id(agent_id, allow_dash=True, allow_underscore=True))
        return validated


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
