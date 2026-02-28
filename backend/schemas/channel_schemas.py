"""
Pydantic schemas for Global Channel Management API

Defines request and response models for managing OpenClaw Gateway
communication channels (WhatsApp, Telegram, Discord, Slack, etc.).

Part of Issue #81 - Create Global Channel Management API Endpoints
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, ConfigDict
from datetime import datetime


class ChannelInfo(BaseModel):
    """Information about a communication channel"""
    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique channel identifier (e.g., 'whatsapp', 'telegram')")
    name: str = Field(..., description="Human-readable channel name")
    description: str = Field(..., description="Channel description")
    enabled: bool = Field(..., description="Whether channel is enabled globally")
    connected: bool = Field(..., description="Whether channel is currently connected")
    capabilities: List[str] = Field(
        default_factory=list,
        description="Supported message types (text, image, voice, etc.)"
    )
    version: str = Field(..., description="Channel plugin version")

    @field_validator('id')
    @classmethod
    def validate_channel_id(cls, v: str) -> str:
        """Validate channel ID format"""
        if not v or not v.replace('-', '').replace('_', '').isalnum():
            raise ValueError("Channel ID must contain only alphanumeric characters, hyphens, and underscores")
        return v.lower()


class ChannelListResponse(BaseModel):
    """Response for listing all channels"""
    model_config = ConfigDict(from_attributes=True)

    channels: List[ChannelInfo] = Field(..., description="List of available channels")
    total: int = Field(..., description="Total number of channels", ge=0)


class ChannelEnableResponse(BaseModel):
    """Response for enabling a channel"""
    model_config = ConfigDict(from_attributes=True)

    channel_id: str = Field(..., description="Channel identifier")
    enabled: bool = Field(..., description="New enabled state (should be True)")
    message: str = Field(..., description="Success message")


class ChannelDisableResponse(BaseModel):
    """Response for disabling a channel"""
    model_config = ConfigDict(from_attributes=True)

    channel_id: str = Field(..., description="Channel identifier")
    enabled: bool = Field(..., description="New enabled state (should be False)")
    message: str = Field(..., description="Success message")


class ConnectionDetails(BaseModel):
    """Detailed connection information for a channel"""
    model_config = ConfigDict(from_attributes=True)

    session_id: Optional[str] = Field(None, description="Active session identifier")
    qr_code_required: Optional[bool] = Field(None, description="Whether QR code authentication is required")
    authenticated: Optional[bool] = Field(None, description="Whether channel is authenticated")
    error: Optional[str] = Field(None, description="Connection error message if any")


class ChannelStatusResponse(BaseModel):
    """Response for channel status query"""
    model_config = ConfigDict(from_attributes=True)

    channel_id: str = Field(..., description="Channel identifier")
    enabled: bool = Field(..., description="Whether channel is enabled")
    connected: bool = Field(..., description="Whether channel is currently connected")
    status: str = Field(
        ...,
        description="Current status: 'active', 'disconnected', 'disabled', 'error'"
    )
    last_activity: Optional[str] = Field(
        None,
        description="ISO 8601 timestamp of last activity"
    )
    connection_details: Optional[ConnectionDetails] = Field(
        None,
        description="Detailed connection information"
    )

    @field_validator('status')
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status value"""
        allowed_statuses = ['active', 'disconnected', 'disabled', 'error', 'connecting']
        if v not in allowed_statuses:
            raise ValueError(f"Status must be one of: {', '.join(allowed_statuses)}")
        return v


class ChannelConfigRequest(BaseModel):
    """Request to update channel configuration"""
    model_config = ConfigDict(from_attributes=True)

    auto_reconnect: Optional[bool] = Field(
        None,
        description="Whether to automatically reconnect on disconnect"
    )
    max_retries: Optional[int] = Field(
        None,
        ge=0,
        le=10,
        description="Maximum number of reconnection attempts (0-10)"
    )
    timeout: Optional[int] = Field(
        None,
        ge=1,
        le=300,
        description="Connection timeout in seconds (1-300)"
    )
    webhook_url: Optional[str] = Field(
        None,
        description="Webhook URL for receiving channel events"
    )
    custom_settings: Optional[Dict[str, Any]] = Field(
        None,
        description="Channel-specific custom settings"
    )

    @field_validator('webhook_url')
    @classmethod
    def validate_webhook_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate webhook URL format"""
        if v and not (v.startswith('http://') or v.startswith('https://')):
            raise ValueError("Webhook URL must start with http:// or https://")
        return v

    def model_dump(self, **kwargs):
        """Override to exclude None values by default"""
        kwargs.setdefault('exclude_none', True)
        return super().model_dump(**kwargs)


class ChannelConfigResponse(BaseModel):
    """Response for configuration update"""
    model_config = ConfigDict(from_attributes=True)

    channel_id: str = Field(..., description="Channel identifier")
    updated: bool = Field(..., description="Whether update was successful")
    message: str = Field(..., description="Success or error message")
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Updated configuration values"
    )


class ChannelErrorResponse(BaseModel):
    """Error response for channel operations"""
    model_config = ConfigDict(from_attributes=True)

    error_code: str = Field(..., description="Machine-readable error code")
    error_message: str = Field(..., description="Human-readable error message")
    channel_id: Optional[str] = Field(None, description="Channel identifier if applicable")
    details: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional error details"
    )
