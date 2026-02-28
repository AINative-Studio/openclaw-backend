"""
Pydantic schemas for Global Channel Management API.

Channels are workspace-level settings (NOT per-agent).
"""

from datetime import datetime
from typing import Dict, Any, List, Optional

from pydantic import BaseModel, Field, validator


class ChannelInfo(BaseModel):
    """Information about a single channel."""
    id: str = Field(..., description="Channel identifier (e.g., 'whatsapp', 'telegram')")
    name: str = Field(..., description="Human-readable channel name")
    enabled: bool = Field(default=False, description="Whether channel is enabled globally")
    available: bool = Field(default=True, description="Whether channel is available via Gateway")
    config: Dict[str, Any] = Field(default_factory=dict, description="Channel-specific configuration")


class ChannelListResponse(BaseModel):
    """Response for listing all available channels."""
    channels: List[ChannelInfo] = Field(..., description="List of all available channels")


class ChannelConfigRequest(BaseModel):
    """Request to update channel configuration."""
    config: Dict[str, Any] = Field(..., description="Channel configuration parameters")

    @validator("config")
    def config_must_not_be_none(cls, v):
        if v is None:
            raise ValueError("config cannot be None")
        return v


class ChannelResponse(BaseModel):
    """Response for enable/disable/update operations."""
    id: str = Field(..., description="Channel identifier")
    name: str = Field(..., description="Channel name")
    enabled: bool = Field(..., description="Whether channel is enabled")
    config: Dict[str, Any] = Field(default_factory=dict, description="Current channel configuration")
    warning: Optional[str] = Field(None, description="Warning message if any")
    available: Optional[bool] = Field(None, description="Gateway availability status")


class ChannelStatusResponse(BaseModel):
    """Response for channel status endpoint."""
    id: str = Field(..., description="Channel identifier")
    name: str = Field(..., description="Channel name")
    enabled: bool = Field(..., description="Whether channel is enabled")
    connected: bool = Field(default=False, description="Whether channel is currently connected")
    last_message_at: Optional[str] = Field(None, description="ISO 8601 timestamp of last message")
    message_count: Optional[int] = Field(None, description="Total message count from Gateway")
    error: Optional[str] = Field(None, description="Error message if connection failed")
