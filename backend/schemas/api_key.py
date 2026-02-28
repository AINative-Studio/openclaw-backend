"""
Pydantic schemas for API Key Management (Issue #83)

Request/response models for API key CRUD operations.
"""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from uuid import UUID


# Supported service names
SupportedService = Literal["anthropic", "openai", "cohere", "huggingface"]


class APIKeyCreate(BaseModel):
    """Request schema for creating a new API key."""

    service_name: SupportedService = Field(
        ...,
        description="Service identifier (anthropic, openai, cohere, huggingface)"
    )
    api_key: str = Field(
        ...,
        min_length=1,
        description="Plaintext API key (will be encrypted before storage)"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_not_empty(cls, v: str) -> str:
        """Validate API key is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("API key cannot be empty")
        return v.strip()


class APIKeyUpdate(BaseModel):
    """Request schema for updating an existing API key."""

    api_key: str = Field(
        ...,
        min_length=1,
        description="New plaintext API key (will be encrypted before storage)"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key_not_empty(cls, v: str) -> str:
        """Validate API key is not empty or whitespace."""
        if not v or not v.strip():
            raise ValueError("API key cannot be empty")
        return v.strip()


class APIKeyResponse(BaseModel):
    """Response schema for API key operations (masked key)."""

    id: UUID
    service_name: str
    masked_key: str = Field(
        ...,
        description="Masked API key (shows only last 4 characters)"
    )
    created_at: datetime
    updated_at: datetime
    is_active: bool

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "service_name": "anthropic",
                "masked_key": "sk-...1234",
                "created_at": "2024-01-15T10:30:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
                "is_active": True
            }
        }
    }


class APIKeyVerifyResponse(BaseModel):
    """Response schema for API key verification."""

    service_name: str
    is_valid: bool
    message: str = Field(
        ...,
        description="Human-readable verification result message"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "service_name": "anthropic",
                "is_valid": True,
                "message": "API key is valid and authenticated successfully"
            }
        }
    }
