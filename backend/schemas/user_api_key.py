"""
Pydantic schemas for User API Key Management (Issue #96)

Request/response models for workspace-level API key CRUD operations.
"""

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator
from uuid import UUID


# Supported provider names (Issue #119: Added Groq, Mistral, Ollama)
SupportedProvider = Literal["anthropic", "openai", "cohere", "huggingface", "google", "groq", "mistral", "ollama"]


class UserAPIKeyCreate(BaseModel):
    """Request schema for creating a new user API key."""

    workspace_id: str = Field(
        ...,
        description="Workspace UUID (as string)",
        min_length=36,
        max_length=36
    )
    provider: SupportedProvider = Field(
        ...,
        description="Provider identifier (anthropic, openai, cohere, huggingface, google, groq, mistral, ollama)"
    )
    api_key: str = Field(
        ...,
        min_length=1,
        description="Plaintext API key (will be encrypted before storage)"
    )
    validate: bool = Field(
        default=False,
        description="If true, validate key against provider API before saving"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_not_empty(cls, v: str) -> str:
        """Validate API key is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("API key cannot be empty")
        return v.strip()

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id_format(cls, v: str) -> str:
        """Validate workspace_id is a valid UUID format."""
        try:
            UUID(v)
        except ValueError:
            raise ValueError("workspace_id must be a valid UUID")
        return v


class UserAPIKeyUpdate(BaseModel):
    """Request schema for updating an existing user API key."""

    api_key: str = Field(
        ...,
        min_length=1,
        description="New plaintext API key (will be encrypted before storage)"
    )
    validate: bool = Field(
        default=False,
        description="If true, validate key against provider API before saving"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_not_empty(cls, v: str) -> str:
        """Validate API key is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("API key cannot be empty")
        return v.strip()


class UserAPIKeyResponse(BaseModel):
    """Response schema for user API key operations (masked key)."""

    id: UUID
    workspace_id: str
    provider: str
    masked_key: str = Field(
        ...,
        description="Masked API key (shows only prefix and last 4 characters)"
    )
    is_active: bool
    last_validated_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
                "provider": "anthropic",
                "masked_key": "sk-ant-***...1234",
                "is_active": True,
                "last_validated_at": "2024-01-15T10:30:00Z",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z"
            }
        }
    }


class UserAPIKeyListItem(BaseModel):
    """Response schema for listing user API keys (minimal info)."""

    id: UUID
    provider: str
    masked_key: str
    is_active: bool
    last_validated_at: Optional[datetime]
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class UserAPIKeyTestRequest(BaseModel):
    """Request schema for testing an API key before saving."""

    provider: SupportedProvider = Field(
        ...,
        description="Provider to test against"
    )
    api_key: str = Field(
        ...,
        min_length=1,
        description="Plaintext API key to test"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_not_empty(cls, v: str) -> str:
        """Validate API key is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("API key cannot be empty")
        return v.strip()


class UserAPIKeyTestResponse(BaseModel):
    """Response schema for API key testing."""

    provider: str
    is_valid: bool
    message: str = Field(
        ...,
        description="Human-readable test result message"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "provider": "anthropic",
                "is_valid": True,
                "message": "Anthropic API key is valid and authenticated successfully"
            }
        }
    }


class UserAPIKeyDeleteResponse(BaseModel):
    """Response schema for API key deletion."""

    success: bool
    message: str
    deleted_id: Optional[UUID] = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "success": True,
                "message": "API key deleted successfully",
                "deleted_id": "123e4567-e89b-12d3-a456-426614174000"
            }
        }
    }
