"""
Global Channel Management API Endpoints.

Channels are workspace-level settings (NOT per-agent).
Supports: whatsapp, telegram, discord, slack, email, sms, teams
"""

import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, status

from backend.schemas.channel_schemas import (
    ChannelListResponse,
    ChannelConfigRequest,
    ChannelResponse,
    ChannelStatusResponse
)

logger = logging.getLogger(__name__)

# Try to import gateway proxy service with graceful fallback
try:
    from backend.services.openclaw_gateway_proxy_service import (
        get_gateway_proxy_service,
        ChannelNotFoundError,
        ConfigurationError
    )
    GATEWAY_PROXY_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import OpenClawGatewayProxyService: {e}")
    GATEWAY_PROXY_AVAILABLE = False

# Try to import plugin service with graceful fallback (Issue #98)
try:
    from backend.services.openclaw_plugin_service import (
        get_openclaw_plugin_service,
        PluginNotFoundError,
        PluginConfigurationError,
        PluginCLIError
    )
    PLUGIN_SERVICE_AVAILABLE = True
except ImportError as e:
    logger.error(f"Failed to import OpenClawPluginService: {e}")
    PLUGIN_SERVICE_AVAILABLE = False


router = APIRouter()


@router.get("/channels", response_model=ChannelListResponse, status_code=status.HTTP_200_OK)
async def list_channels():
    """
    List all available channels with their current status.

    Returns:
        ChannelListResponse: List of all supported channels

    Raises:
        503: Service Unavailable if Gateway Proxy Service cannot be loaded
        500: Internal Server Error if configuration is corrupted or cannot be read
    """
    if not GATEWAY_PROXY_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway Proxy Service is not available"
        )

    try:
        service = get_gateway_proxy_service()

        # Wrap the service call to handle ConnectionError gracefully
        try:
            channels = service.list_channels()
        except ConnectionError:
            # Gateway unavailable, return channels from config with all marked unavailable
            channels = service.list_channels()

        return ChannelListResponse(channels=channels)

    except ConfigurationError as e:
        logger.error(f"Configuration error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Configuration error: {str(e)}"}
        )
    except Exception as e:
        logger.error(f"Failed to list channels: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": f"Failed to list channels: {str(e)}"}
        )


@router.post(
    "/channels/{channel_id}/enable",
    response_model=ChannelResponse,
    status_code=status.HTTP_201_CREATED
)
async def enable_channel(channel_id: str, request: ChannelConfigRequest):
    """
    Enable a channel globally with provided configuration.

    Args:
        channel_id: Channel identifier (whatsapp, telegram, discord, slack, email, sms, teams)
        request: Channel configuration

    Returns:
        ChannelResponse: Updated channel information

    Raises:
        404: Channel not found
        422: Invalid configuration (missing required fields)
        503: Service unavailable
    """
    if not GATEWAY_PROXY_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway Proxy Service is not available"
        )

    try:
        service = get_gateway_proxy_service()
        channel_info = service.enable_channel(channel_id, request.config)

        # Check Gateway availability and add warning if needed
        response = ChannelResponse(
            id=channel_info.id,
            name=channel_info.name,
            enabled=channel_info.enabled,
            config=channel_info.config,
            available=channel_info.available
        )

        if not channel_info.available:
            response.warning = "OpenClaw Gateway is currently unavailable"

        return response

    except ChannelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel not found: {str(e)}"
        )
    except ConfigurationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to enable channel {channel_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable channel: {str(e)}"
        )


@router.post(
    "/channels/{channel_id}/disable",
    response_model=ChannelResponse,
    status_code=status.HTTP_200_OK
)
async def disable_channel(channel_id: str):
    """
    Disable a channel globally (preserves configuration).

    Args:
        channel_id: Channel identifier

    Returns:
        ChannelResponse: Updated channel information

    Raises:
        404: Channel not found
        503: Service unavailable
    """
    if not GATEWAY_PROXY_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway Proxy Service is not available"
        )

    try:
        service = get_gateway_proxy_service()
        channel_info = service.disable_channel(channel_id)

        return ChannelResponse(
            id=channel_info.id,
            name=channel_info.name,
            enabled=channel_info.enabled,
            config=channel_info.config
        )

    except ChannelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel not found: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to disable channel {channel_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable channel: {str(e)}"
        )


@router.get(
    "/channels/{channel_id}/status",
    response_model=ChannelStatusResponse,
    status_code=status.HTTP_200_OK
)
async def get_channel_status(channel_id: str):
    """
    Get real-time channel status from OpenClaw Gateway.

    Args:
        channel_id: Channel identifier

    Returns:
        ChannelStatusResponse: Current channel status with connection info

    Raises:
        404: Channel not found
        503: Service unavailable
    """
    if not GATEWAY_PROXY_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway Proxy Service is not available"
        )

    try:
        service = get_gateway_proxy_service()
        status_data = service.get_channel_status(channel_id)

        return ChannelStatusResponse(**status_data)

    except ChannelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel not found: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to get status for channel {channel_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get channel status: {str(e)}"
        )


@router.put(
    "/channels/{channel_id}/config",
    response_model=ChannelResponse,
    status_code=status.HTTP_200_OK
)
async def update_channel_config(channel_id: str, request: ChannelConfigRequest):
    """
    Update channel configuration (supports partial updates).

    Args:
        channel_id: Channel identifier
        request: Configuration parameters to update

    Returns:
        ChannelResponse: Updated channel information

    Raises:
        404: Channel not found
        422: Invalid configuration
        503: Service unavailable
    """
    if not GATEWAY_PROXY_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Gateway Proxy Service is not available"
        )

    try:
        service = get_gateway_proxy_service()
        channel_info = service.update_channel_config(channel_id, request.config)

        return ChannelResponse(
            id=channel_info.id,
            name=channel_info.name,
            enabled=channel_info.enabled,
            config=channel_info.config
        )

    except ChannelNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel not found: {str(e)}"
        )
    except ConfigurationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to update config for channel {channel_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update channel config: {str(e)}"
        )


# ============================================================================
# NEW ENDPOINTS (Issue #98): OpenClaw Plugin Integration
# ============================================================================


@router.post(
    "/channels/{channel_id}/connect",
    response_model=ChannelResponse,
    status_code=status.HTTP_201_CREATED
)
async def connect_channel(channel_id: str, request: ChannelConfigRequest):
    """
    Connect a channel via OpenClaw plugin (Issue #98).

    This endpoint enables and configures OpenClaw plugins for:
    - Telegram (@openclaw/telegram)
    - Discord (@openclaw/discord)
    - Slack (@openclaw/slack)
    - Microsoft Teams (@openclaw/msteams)
    - Signal (@openclaw/signal)

    Args:
        channel_id: Channel identifier
        request: Channel configuration (botToken, appToken, etc.)

    Returns:
        ChannelResponse: Updated channel information

    Raises:
        404: Channel/plugin not found
        422: Invalid configuration (missing required fields)
        503: Service unavailable
    """
    if not PLUGIN_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenClaw Plugin Service is not available"
        )

    try:
        plugin_service = get_openclaw_plugin_service()
        result = plugin_service.enable_plugin(channel_id, request.config)

        return ChannelResponse(
            id=result["plugin_id"],
            name=result["name"],
            enabled=result["enabled"],
            config=result["config"]
        )

    except PluginNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel plugin not found: {str(e)}"
        )
    except PluginConfigurationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )
    except PluginCLIError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"OpenClaw CLI error: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to connect channel {channel_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to connect channel: {str(e)}"
        )


@router.delete(
    "/channels/{channel_id}/disconnect",
    response_model=ChannelResponse,
    status_code=status.HTTP_200_OK
)
async def disconnect_channel(channel_id: str):
    """
    Disconnect a channel via OpenClaw plugin (Issue #98).

    Disables the plugin but preserves configuration.

    Args:
        channel_id: Channel identifier

    Returns:
        ChannelResponse: Updated channel information

    Raises:
        404: Channel/plugin not found
        503: Service unavailable
    """
    if not PLUGIN_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenClaw Plugin Service is not available"
        )

    try:
        plugin_service = get_openclaw_plugin_service()
        result = plugin_service.disable_plugin(channel_id)

        return ChannelResponse(
            id=result["plugin_id"],
            name=result["name"],
            enabled=result["enabled"],
            config=result.get("config", {})
        )

    except PluginNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel plugin not found: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to disconnect channel {channel_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disconnect channel: {str(e)}"
        )


@router.post(
    "/channels/{channel_id}/test",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK
)
async def test_channel_connection(channel_id: str):
    """
    Test channel connection (Issue #98).

    Verifies that the channel plugin is enabled and configuration is valid.

    Args:
        channel_id: Channel identifier

    Returns:
        Test result with connection status

    Raises:
        404: Channel/plugin not found
        503: Service unavailable
    """
    if not PLUGIN_SERVICE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenClaw Plugin Service is not available"
        )

    try:
        plugin_service = get_openclaw_plugin_service()
        plugin_info = plugin_service.get_plugin_info(channel_id)

        # Check if enabled
        if not plugin_info["enabled"]:
            return {
                "channel_id": channel_id,
                "success": False,
                "message": "Channel is not enabled",
                "enabled": False
            }

        # Validate configuration
        is_valid, errors = plugin_service.validate_plugin_config(
            channel_id,
            plugin_info["config"]
        )

        if not is_valid:
            return {
                "channel_id": channel_id,
                "success": False,
                "message": f"Invalid configuration: {'; '.join(errors)}",
                "enabled": True,
                "errors": errors
            }

        return {
            "channel_id": channel_id,
            "success": True,
            "message": "Channel configuration is valid",
            "enabled": True
        }

    except PluginNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel plugin not found: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to test channel {channel_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to test channel: {str(e)}"
        )
