"""
Zalo Pydantic Schemas (Issue #121)

Request and response schemas for Zalo API endpoints.
"""

from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field, field_validator
from datetime import datetime


class ZaloOAuthRequest(BaseModel):
    """Request schema for OAuth authorization URL"""
    redirect_uri: str = Field(..., description="OAuth callback URL")
    state: Optional[str] = Field(None, description="State parameter for CSRF protection")


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
    """Request schema for sending messages"""
    workspace_id: UUID = Field(..., description="Workspace UUID")
    user_id: str = Field(..., description="Zalo user ID")
    message: str = Field(..., description="Message text")

    @field_validator('message')
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        """Validate message is not empty"""
        if not v or not v.strip():
            raise ValueError("Message cannot be empty")
        return v.strip()


class ZaloMessageResponse(BaseModel):
    """Response schema for message sending"""
    message_id: str = Field(..., description="Zalo message ID")
    status: str = Field(default="sent", description="Message status")
