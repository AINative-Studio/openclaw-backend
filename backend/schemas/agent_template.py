"""
Agent Template API Schemas

Pydantic v2 request/response models for the template CRUD REST API.
Maps to frontend OpenClawTemplate type definitions.

Security: Issue #131 - Input validation and XSS prevention
"""

from typing import Optional
from pydantic import BaseModel, Field, field_validator
from backend.validators import sanitize_html


class CreateTemplateRequest(BaseModel):
    """
    Request body for POST /templates

    Security: Issue #131 - Sanitizes HTML from text fields
    """
    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Template name (XSS sanitized)"
    )
    description: Optional[str] = Field(
        None,
        max_length=2000,
        description="Template description (XSS sanitized)"
    )
    category: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Template category (XSS sanitized)"
    )
    icons: list[str] = Field(
        default_factory=list,
        max_length=10,
        description="List of icon names (max 10)"
    )
    default_model: str = Field(
        default="anthropic/claude-opus-4-5",
        max_length=255,
        description="Model identifier (validated format)"
    )
    default_persona: Optional[str] = Field(
        None,
        max_length=5000,
        description="Agent persona (XSS sanitized)"
    )
    default_heartbeat_interval: Optional[str] = Field(
        default="5m",
        max_length=10,
        description="Heartbeat interval (e.g., 5m, 1h)"
    )
    default_checklist: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="Checklist items (XSS sanitized)"
    )

    @field_validator('name', 'description', 'category', 'default_persona')
    @classmethod
    def sanitize_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize text fields to prevent XSS attacks (Issue #131)."""
        if v is None:
            return v
        return sanitize_html(v)

    @field_validator('icons')
    @classmethod
    def validate_icons(cls, v: list[str]) -> list[str]:
        """Validate icon names are safe strings (Issue #131)."""
        validated = []
        for icon in v:
            if len(icon) > 100:
                raise ValueError("Icon name exceeds maximum length of 100 characters")
            # Allow alphanumeric, dash, underscore for icon names
            if not icon.replace('-', '').replace('_', '').isalnum():
                raise ValueError(f"Icon name contains invalid characters: {icon}")
            validated.append(icon)
        return validated

    @field_validator('default_checklist')
    @classmethod
    def sanitize_checklist(cls, v: list[str]) -> list[str]:
        """Sanitize checklist items to prevent XSS (Issue #131)."""
        return [sanitize_html(item) for item in v]

    @field_validator('default_heartbeat_interval')
    @classmethod
    def validate_heartbeat_interval(cls, v: Optional[str]) -> Optional[str]:
        """Validate heartbeat interval format (Issue #131)."""
        if v is None:
            return v

        import re
        # Format: <number><unit> where unit is s, m, h, d
        if not re.match(r'^\d+[smhd]$', v):
            raise ValueError(
                "Invalid heartbeat interval format. Must be like: 5m, 1h, 30s, 1d"
            )
        return v


class UpdateTemplateRequest(BaseModel):
    """
    Request body for PATCH /templates/{template_id}

    Security: Issue #131 - Same validation as CreateTemplateRequest
    """
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    category: Optional[str] = Field(None, max_length=50)
    icons: Optional[list[str]] = Field(None, max_length=10)
    default_model: Optional[str] = Field(None, max_length=255)
    default_persona: Optional[str] = Field(None, max_length=5000)
    default_heartbeat_interval: Optional[str] = Field(None, max_length=10)
    default_checklist: Optional[list[str]] = Field(None, max_length=50)

    @field_validator('name', 'description', 'category', 'default_persona')
    @classmethod
    def sanitize_text_fields(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize text fields to prevent XSS attacks (Issue #131)."""
        if v is None:
            return v
        return sanitize_html(v)

    @field_validator('icons')
    @classmethod
    def validate_icons(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """Validate icon names are safe strings (Issue #131)."""
        if v is None:
            return v
        validated = []
        for icon in v:
            if len(icon) > 100:
                raise ValueError("Icon name exceeds maximum length of 100 characters")
            if not icon.replace('-', '').replace('_', '').isalnum():
                raise ValueError(f"Icon name contains invalid characters: {icon}")
            validated.append(icon)
        return validated

    @field_validator('default_checklist')
    @classmethod
    def sanitize_checklist(cls, v: Optional[list[str]]) -> Optional[list[str]]:
        """Sanitize checklist items to prevent XSS (Issue #131)."""
        if v is None:
            return v
        return [sanitize_html(item) for item in v]

    @field_validator('default_heartbeat_interval')
    @classmethod
    def validate_heartbeat_interval(cls, v: Optional[str]) -> Optional[str]:
        """Validate heartbeat interval format (Issue #131)."""
        if v is None:
            return v

        import re
        if not re.match(r'^\d+[smhd]$', v):
            raise ValueError(
                "Invalid heartbeat interval format. Must be like: 5m, 1h, 30s, 1d"
            )
        return v


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
