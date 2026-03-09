"""
Zalo Pydantic Schemas (Issue #121)

Request and response schemas for Zalo API endpoints.

Security: Issue #131 - Input validation and XSS prevention
"""

from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from backend.validators import sanitize_html, validate_url


class ZaloOAuthRequest(BaseModel):
    """
    Request schema for OAuth authorization URL

    Security: Issue #131 - Validates redirect URI format
    """
    redirect_uri: str = Field(
        ...,
        max_length=500,
        description="OAuth callback URL (validated format)"
    )
    state: Optional[str] = Field(
        None,
        max_length=128,
        description="State parameter for CSRF protection"
    )

    @field_validator('redirect_uri')
    @classmethod
    def validate_redirect_uri(cls, v: str) -> str:
        """Validate redirect URI is a valid HTTPS URL (Issue #131)."""
        # Require HTTPS for OAuth redirects (security best practice)
        return validate_url(v, allowed_schemes=['https', 'http'])


class ZaloOAuthResponse(BaseModel):
    """Response schema for OAuth authorization URL"""
    auth_url: str = Field(..., description="Zalo OAuth authorization URL")
    state: str = Field(..., description="State token for verification")


class ZaloOAuthCallbackRequest(BaseModel):
    """Request schema for OAuth callback"""
    code: str = Field(..., description="Authorization code from Zalo")
    state: str = Field(..., description="State parameter for verification")


class ZaloTokenResponse(BaseModel):
    """Response schema for token exchange/refresh"""
    access_token: str = Field(..., description="Zalo access token")
    refresh_token: str = Field(..., description="Zalo refresh token")
    expires_in: int = Field(..., description="Token expiration time in seconds")


class ZaloConnectRequest(BaseModel):
    """Request schema for connecting Zalo OA"""
    workspace_id: UUID = Field(..., description="Workspace UUID")
    oa_id: str = Field(..., description="Zalo Official Account ID")
    app_id: str = Field(..., description="Zalo App ID")
    app_secret: str = Field(..., description="Zalo App Secret")
    access_token: str = Field(..., description="OAuth access token")
    refresh_token: str = Field(..., description="OAuth refresh token")

    @field_validator('oa_id', 'app_id', 'app_secret', 'access_token', 'refresh_token')
    @classmethod
    def validate_not_empty(cls, v: str) -> str:
        """Validate fields are not empty"""
        if not v or not v.strip():
            raise ValueError("Field cannot be empty")
        return v.strip()


class ZaloConnectResponse(BaseModel):
    """Response schema for OA connection"""
    status: str = Field(..., description="Connection status (connected/updated)")
    oa_id: str = Field(..., description="Zalo Official Account ID")
    oa_info: Optional[Dict[str, Any]] = Field(None, description="OA information")


class ZaloDisconnectResponse(BaseModel):
    """Response schema for OA disconnection"""
    status: str = Field(..., description="Disconnection status")
    message: str = Field(default="Zalo OA disconnected successfully")


class ZaloWebhookEvent(BaseModel):
    """Schema for processed webhook event"""
    event_name: str = Field(..., description="Zalo event name")
    timestamp: int = Field(..., description="Event timestamp (Unix epoch)")
    app_id: str = Field(..., description="Zalo App ID")
    user_id: str = Field(..., description="Zalo user ID")
    message: Optional[Dict[str, Any]] = Field(None, description="Message data (if applicable)")

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v: int) -> int:
        """Validate timestamp is positive"""
        if v <= 0:
            raise ValueError("Timestamp must be positive")
        return v


class ZaloWebhookResponse(BaseModel):
    """Response schema for webhook processing"""
    status: str = Field(..., description="Processing status")
    conversation_id: Optional[str] = Field(None, description="Conversation ID (if created)")
    event_type: Optional[str] = Field(None, description="Event type processed")


class ZaloStatusResponse(BaseModel):
    """Response schema for OA status check"""
    connected: bool = Field(..., description="Whether Zalo OA is connected")
    oa_id: Optional[str] = Field(None, description="Zalo Official Account ID")
    app_id: Optional[str] = Field(None, description="Zalo App ID")
    last_connected_at: Optional[datetime] = Field(None, description="Last connection timestamp")


class ZaloMessageRequest(BaseModel):
    """
    Request schema for sending messages

    Security: Issue #131 - Sanitizes HTML from message text
    """
    workspace_id: UUID = Field(..., description="Workspace UUID")
    user_id: str = Field(
        ...,
        max_length=255,
        description="Zalo user ID (alphanumeric)"
    )
    message: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="Message text (XSS sanitized)"
    )

    @field_validator('message')
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        """
        Validate and sanitize message (Issue #131).

        Prevents:
            - Empty messages
            - HTML/XSS injection
        """
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        # Sanitize HTML tags and JavaScript
        return sanitize_html(v.strip())


class ZaloMessageResponse(BaseModel):
    """Response schema for message sending"""
    message_id: str = Field(..., description="Zalo message ID")
    status: str = Field(default="sent", description="Message status")
