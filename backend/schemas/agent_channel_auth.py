"""
Pydantic schemas for Agent Channel OAuth Authentication.

Supports OAuth flows for email (Google, Microsoft), Slack, Discord, etc.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, validator


class OAuthStartRequest(BaseModel):
    """Request to initiate OAuth flow for a channel."""

    scopes: Optional[List[str]] = Field(
        None,
        description="Optional OAuth scopes to request (uses defaults if not provided)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "scopes": ["https://www.googleapis.com/auth/gmail.send", "https://www.googleapis.com/auth/gmail.readonly"]
            }
        }


class OAuthStartResponse(BaseModel):
    """Response containing OAuth authorization URL."""

    oauth_url: str = Field(..., description="OAuth authorization URL to redirect user to")
    state: str = Field(..., description="State token for CSRF protection")

    class Config:
        json_schema_extra = {
            "example": {
                "oauth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...&redirect_uri=...&state=...",
                "state": "abc123def456..."
            }
        }


class OAuthCallbackRequest(BaseModel):
    """OAuth callback parameters."""

    code: str = Field(..., description="Authorization code from OAuth provider")
    state: str = Field(..., description="State token to validate CSRF protection")
    error: Optional[str] = Field(None, description="Error code if OAuth failed")
    error_description: Optional[str] = Field(None, description="Human-readable error description")

    class Config:
        json_schema_extra = {
            "example": {
                "code": "4/0AY0e-g7...",
                "state": "abc123def456..."
            }
        }


class ChannelCredentialInfo(BaseModel):
    """Information about stored channel credentials (without exposing tokens)."""

    id: UUID = Field(..., description="Credential record ID")
    agent_id: UUID = Field(..., description="Agent ID")
    channel_type: str = Field(..., description="Channel type (email, slack, etc.)")
    provider: str = Field(..., description="OAuth provider (google, microsoft, etc.)")
    has_credentials: bool = Field(..., description="Whether valid credentials are stored")
    is_expired: bool = Field(..., description="Whether credentials have expired")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Non-sensitive metadata")
    expires_at: Optional[datetime] = Field(None, description="Token expiration timestamp")
    created_at: datetime = Field(..., description="When credentials were first stored")
    updated_at: Optional[datetime] = Field(None, description="When credentials were last updated")

    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": "550e8400-e29b-41d4-a716-446655440000",
                "agent_id": "660e8400-e29b-41d4-a716-446655440000",
                "channel_type": "email",
                "provider": "google",
                "has_credentials": True,
                "is_expired": False,
                "metadata": {
                    "email_address": "agent@example.com",
                    "scopes": ["gmail.send", "gmail.readonly"]
                },
                "expires_at": "2026-04-04T12:00:00Z",
                "created_at": "2026-03-04T12:00:00Z",
                "updated_at": "2026-03-04T12:00:00Z"
            }
        }


class ChannelCredentialsListResponse(BaseModel):
    """Response listing all channel credentials for an agent."""

    credentials: List[ChannelCredentialInfo] = Field(
        ...,
        description="List of configured channel credentials"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "credentials": [
                    {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "agent_id": "660e8400-e29b-41d4-a716-446655440000",
                        "channel_type": "email",
                        "provider": "google",
                        "has_credentials": True,
                        "is_expired": False,
                        "metadata": {"email_address": "agent@example.com"},
                        "created_at": "2026-03-04T12:00:00Z"
                    }
                ]
            }
        }


class OAuthSuccessResponse(BaseModel):
    """Response after successful OAuth token exchange."""

    success: bool = Field(True, description="Whether OAuth was successful")
    message: str = Field(..., description="Success message")
    credential_id: UUID = Field(..., description="ID of stored credential")
    channel_type: str = Field(..., description="Channel type")
    provider: str = Field(..., description="OAuth provider")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Email channel authenticated successfully",
                "credential_id": "550e8400-e29b-41d4-a716-446655440000",
                "channel_type": "email",
                "provider": "google"
            }
        }


class OAuthErrorResponse(BaseModel):
    """Response for OAuth errors."""

    success: bool = Field(False, description="Whether OAuth was successful")
    error: str = Field(..., description="Error code")
    error_description: Optional[str] = Field(None, description="Human-readable error description")

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "access_denied",
                "error_description": "User denied access to requested scopes"
            }
        }
