"""
Pydantic schemas for OpenClaw Channels API
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ChannelCapability(BaseModel):
    """Channel capabilities and supported features"""
    channel: str
    account_id: str
    configured: bool
    enabled: bool
    support: Dict[str, Any] = Field(default_factory=dict)
    actions: List[str] = Field(default_factory=list)


class ChannelAuthInstruction(BaseModel):
    """Authentication instructions for a channel"""
    auth_type: str
    instructions: List[str]
    docs_url: Optional[str] = None
    required_fields: List[str] = Field(default_factory=list)


class ChannelStatus(BaseModel):
    """Current status of a channel"""
    channel: str
    account_id: str
    configured: bool
    capabilities: Optional[Dict[str, Any]] = None


class ChannelListResponse(BaseModel):
    """Response for listing all configured channels"""
    chat: Dict[str, List[str]] = Field(default_factory=dict)
    auth: List[Dict[str, Any]] = Field(default_factory=list)
    usage: Dict[str, Any] = Field(default_factory=dict)


class AvailableChannelsResponse(BaseModel):
    """Response for listing all available channel types"""
    channels: List[ChannelCapability]


class AddChannelBotTokenRequest(BaseModel):
    """Request to add a channel using bot token"""
    channel: str = Field(..., description="Channel type (telegram, discord, etc.)")
    token: str = Field(..., description="Bot token")
    account_id: str = Field(default="default", description="Account identifier")
    name: Optional[str] = Field(None, description="Display name for this account")


class AddChannelSlackRequest(BaseModel):
    """Request to add Slack channel"""
    bot_token: str = Field(..., description="Slack bot token (xoxb-...)")
    app_token: str = Field(..., description="Slack app token (xapp-...)")
    account_id: str = Field(default="default", description="Account identifier")
    name: Optional[str] = Field(None, description="Display name for this account")


class AddChannelMatrixRequest(BaseModel):
    """Request to add Matrix channel"""
    homeserver: str = Field(..., description="Matrix homeserver URL")
    user_id: str = Field(..., description="Matrix user ID")
    access_token: Optional[str] = Field(None, description="Matrix access token")
    password: Optional[str] = Field(None, description="Matrix password (if no access token)")
    device_name: Optional[str] = Field(None, description="Device name")
    account_id: str = Field(default="default", description="Account identifier")


class AddChannelSignalRequest(BaseModel):
    """Request to add Signal channel"""
    signal_number: str = Field(..., description="Signal phone number (E.164 format)")
    cli_path: Optional[str] = Field(None, description="Path to signal-cli executable")
    http_url: Optional[str] = Field(None, description="Signal HTTP daemon base URL")
    account_id: str = Field(default="default", description="Account identifier")


class LoginChannelRequest(BaseModel):
    """Request to initiate channel login"""
    channel: str = Field(..., description="Channel type")
    account_id: str = Field(default="default", description="Account identifier")
    verbose: bool = Field(default=False, description="Enable verbose logging")


class ChannelOperationResponse(BaseModel):
    """Generic response for channel operations"""
    success: bool
    channel: str
    account_id: str
    message: str
    output: Optional[str] = None


class RemoveChannelRequest(BaseModel):
    """Request to remove a channel"""
    channel: str = Field(..., description="Channel type")
    account_id: str = Field(default="default", description="Account identifier")


class ChannelAuthInstructionsResponse(BaseModel):
    """Response with authentication instructions"""
    channel: str
    auth_type: str
    instructions: List[str]
    docs_url: Optional[str] = None
    required_fields: List[str]


class ChannelErrorResponse(BaseModel):
    """Error response for channel operations"""
    error: str
    detail: str
    channel: Optional[str] = None
