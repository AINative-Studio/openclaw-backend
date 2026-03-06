"""
OpenClaw Channels API Endpoints

Provides REST API for managing OpenClaw messaging channels.
Wraps OpenClaw CLI commands for channel management.
"""

import logging
from uuid import UUID
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, status, Depends, Path, Query
from sqlalchemy.orm import Session

from backend.db.base import get_db
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance
from backend.services.openclaw_channels_service import (
    get_available_channels,
    get_configured_channels,
    get_channel_status,
    add_channel_bot_token,
    add_channel_slack,
    login_channel,
    logout_channel,
    remove_channel,
    get_channel_auth_instructions,
)
from backend.schemas.openclaw_channels import (
    AvailableChannelsResponse,
    ChannelListResponse,
    ChannelStatus,
    AddChannelBotTokenRequest,
    AddChannelSlackRequest,
    AddChannelMatrixRequest,
    AddChannelSignalRequest,
    LoginChannelRequest,
    ChannelOperationResponse,
    RemoveChannelRequest,
    ChannelAuthInstructionsResponse,
    ChannelErrorResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/openclaw/channels", tags=["OpenClaw Channels"])


def _validate_agent_exists(db: Session, agent_id: UUID) -> AgentSwarmInstance:
    """
    Validate that agent exists in database.

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        AgentSwarmInstance object

    Raises:
        HTTPException: 404 if agent not found
    """
    agent = db.query(AgentSwarmInstance).filter(AgentSwarmInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return agent


@router.get(
    "/available",
    response_model=Dict,
    status_code=status.HTTP_200_OK,
    summary="Get all available channel types",
    description="Returns all channel types supported by OpenClaw with their capabilities",
)
def list_available_channels():
    """
    Get all available messaging channel types.

    Returns channel capabilities including:
    - Supported chat types (direct, group, channel, thread)
    - Features (polls, reactions, media, etc.)
    - Available actions (send, broadcast, react, etc.)
    """
    try:
        channels_data = get_available_channels()
        return channels_data
    except RuntimeError as e:
        logger.error(f"Failed to get available channels: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error getting available channels: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get available channels: {str(e)}",
        )


@router.get(
    "/configured",
    response_model=Dict,
    status_code=status.HTTP_200_OK,
    summary="Get all configured channels",
    description="Returns all channels currently configured in OpenClaw",
)
def list_configured_channels():
    """
    Get all currently configured messaging channels.

    Returns configuration for all active channels including:
    - Channel type and account ID
    - Authentication status
    - Usage statistics
    """
    try:
        channels_data = get_configured_channels()
        return channels_data
    except RuntimeError as e:
        logger.error(f"Failed to get configured channels: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error getting configured channels: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get configured channels: {str(e)}",
        )


@router.get(
    "/{channel}/status",
    response_model=ChannelStatus,
    status_code=status.HTTP_200_OK,
    summary="Get channel status",
    description="Get detailed status for a specific channel",
)
def get_channel_status_endpoint(
    channel: str = Path(..., description="Channel type (whatsapp, slack, etc.)"),
    account_id: str = Query("default", description="Account identifier"),
):
    """
    Get detailed status for a specific channel.

    Args:
        channel: Channel type (e.g., "whatsapp", "slack")
        account_id: Account identifier (default: "default")

    Returns:
        Channel status including configuration and capabilities
    """
    try:
        status_data = get_channel_status(channel, account_id)
        return ChannelStatus(**status_data)
    except RuntimeError as e:
        logger.error(f"Failed to get channel status: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error getting channel status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get channel status: {str(e)}",
        )


@router.get(
    "/{channel}/auth-instructions",
    response_model=ChannelAuthInstructionsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get authentication instructions",
    description="Get step-by-step instructions for connecting a channel",
)
def get_channel_auth_instructions_endpoint(
    channel: str = Path(..., description="Channel type"),
):
    """
    Get authentication instructions for a channel.

    Returns:
        Step-by-step instructions, required fields, and documentation links
    """
    try:
        instructions = get_channel_auth_instructions(channel)
        return ChannelAuthInstructionsResponse(
            channel=channel,
            **instructions
        )
    except Exception as e:
        logger.error(f"Error getting auth instructions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get auth instructions: {str(e)}",
        )


@router.post(
    "/add/bot-token",
    response_model=ChannelOperationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add channel with bot token",
    description="Add a channel using bot token authentication (Telegram, Discord)",
)
def add_channel_bot_token_endpoint(
    request: AddChannelBotTokenRequest,
):
    """
    Add a channel using bot token authentication.

    Supported channels: Telegram, Discord

    Args:
        request: Channel configuration with bot token

    Returns:
        Operation result
    """
    try:
        result = add_channel_bot_token(
            channel=request.channel,
            token=request.token,
            account_id=request.account_id,
            name=request.name,
        )
        return ChannelOperationResponse(**result)
    except RuntimeError as e:
        logger.error(f"Failed to add channel: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error adding channel: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add channel: {str(e)}",
        )


@router.post(
    "/add/slack",
    response_model=ChannelOperationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Add Slack channel",
    description="Add Slack channel with bot and app tokens",
)
def add_slack_channel_endpoint(
    request: AddChannelSlackRequest,
):
    """
    Add Slack channel with bot and app tokens.

    Requires:
    - Bot token (xoxb-...)
    - App token (xapp-...)

    Args:
        request: Slack configuration

    Returns:
        Operation result
    """
    try:
        result = add_channel_slack(
            bot_token=request.bot_token,
            app_token=request.app_token,
            account_id=request.account_id,
            name=request.name,
        )
        return ChannelOperationResponse(**result)
    except RuntimeError as e:
        logger.error(f"Failed to add Slack channel: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error adding Slack: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add Slack channel: {str(e)}",
        )


@router.post(
    "/login",
    response_model=ChannelOperationResponse,
    status_code=status.HTTP_200_OK,
    summary="Initiate channel login",
    description="Start login flow for a channel (QR code, OAuth, etc.)",
)
def login_channel_endpoint(
    request: LoginChannelRequest,
):
    """
    Initiate login flow for a channel.

    For WhatsApp: Generates QR code to scan
    For OAuth channels: Returns authorization URL

    Args:
        request: Login request with channel and account ID

    Returns:
        Login instructions and status
    """
    try:
        result = login_channel(
            channel=request.channel,
            account_id=request.account_id,
            verbose=request.verbose,
        )
        return ChannelOperationResponse(**result)
    except RuntimeError as e:
        logger.error(f"Failed to login to channel: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during login: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to login: {str(e)}",
        )


@router.post(
    "/logout",
    response_model=ChannelOperationResponse,
    status_code=status.HTTP_200_OK,
    summary="Logout from channel",
    description="Logout from a channel session",
)
def logout_channel_endpoint(
    channel: str = Query(..., description="Channel type"),
    account_id: str = Query("default", description="Account identifier"),
):
    """
    Logout from a channel session.

    Args:
        channel: Channel type
        account_id: Account identifier

    Returns:
        Operation result
    """
    try:
        result = logout_channel(
            channel=channel,
            account_id=account_id,
        )
        return ChannelOperationResponse(**result)
    except RuntimeError as e:
        logger.error(f"Failed to logout from channel: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error during logout: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to logout: {str(e)}",
        )


@router.delete(
    "/remove",
    response_model=ChannelOperationResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove channel",
    description="Remove/disable a channel account",
)
def remove_channel_endpoint(
    channel: str = Query(..., description="Channel type"),
    account_id: str = Query("default", description="Account identifier"),
):
    """
    Remove/disable a channel account.

    Args:
        channel: Channel type
        account_id: Account identifier

    Returns:
        Operation result
    """
    try:
        result = remove_channel(
            channel=channel,
            account_id=account_id,
        )
        return ChannelOperationResponse(**result)
    except RuntimeError as e:
        logger.error(f"Failed to remove channel: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error removing channel: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove channel: {str(e)}",
        )


# Agent-specific channel endpoints
@router.get(
    "/agents/{agent_id}/channels",
    response_model=Dict,
    status_code=status.HTTP_200_OK,
    summary="Get agent's configured channels",
    description="Get all channels configured for a specific agent",
)
def get_agent_channels(
    agent_id: UUID = Path(..., description="Agent UUID"),
    db: Session = Depends(get_db),
):
    """
    Get all channels configured for a specific agent.

    Note: OpenClaw channels are system-wide, but this endpoint
    validates the agent exists and returns the global channel config.

    Args:
        agent_id: Agent UUID
        db: Database session

    Returns:
        Configured channels
    """
    try:
        # Validate agent exists
        _validate_agent_exists(db, agent_id)

        # Return global OpenClaw channels
        # (In future, could filter by agent-specific routing rules)
        channels_data = get_configured_channels()
        return channels_data
    except HTTPException:
        raise
    except RuntimeError as e:
        logger.error(f"Failed to get agent channels: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Unexpected error getting agent channels: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent channels: {str(e)}",
        )
