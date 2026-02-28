"""
Global Channel Management API Endpoints

RESTful API for managing OpenClaw Gateway communication channels.
Channels are global workspace-level settings that control which communication
platforms (WhatsApp, Telegram, Discord, Slack, etc.) are enabled.

Part of Issue #81 - Create Global Channel Management API Endpoints
"""

import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import JSONResponse

from backend.schemas.channel_schemas import (
    ChannelListResponse,
    ChannelEnableResponse,
    ChannelDisableResponse,
    ChannelStatusResponse,
    ChannelConfigRequest,
    ChannelConfigResponse,
    ChannelErrorResponse
)
from backend.services.openclaw_gateway_proxy_service import (
    OpenClawGatewayProxyService,
    ChannelNotFoundError,
    ConfigurationError,
    OpenClawGatewayProxyServiceError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/channels", tags=["Channels", "Configuration"])


@router.get(
    "",
    response_model=ChannelListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all available channels",
    description="""
    Get a list of all available communication channels in OpenClaw Gateway.

    Channels represent different communication platforms (WhatsApp, Telegram, Discord,
    Slack, Email, SMS, etc.) that can be enabled globally for the workspace.

    **Query Parameters:**
    - `enabled`: Filter to show only enabled or disabled channels

    **Returns:**
    - List of channel information including enabled/connected status
    - Total count of channels

    **Channel States:**
    - `enabled`: Channel is configured and ready to use
    - `connected`: Channel is actively connected to the platform
    - `disconnected`: Channel is enabled but not currently connected
    - `disabled`: Channel is not available for use

    **Use Cases:**
    - Display available channels in UI settings
    - Monitor which channels are active
    - Configure multi-channel communication strategy
    """,
    responses={
        200: {
            "description": "List of channels retrieved successfully",
            "model": ChannelListResponse
        },
        503: {
            "description": "OpenClaw Gateway unavailable",
            "model": ChannelErrorResponse
        }
    }
)
async def list_channels(
    enabled: Optional[bool] = Query(
        None,
        description="Filter by enabled status (true=enabled only, false=disabled only, null=all)"
    )
) -> ChannelListResponse:
    """
    List all available communication channels.

    Returns channels with their current enabled/connected status.
    Can optionally filter to show only enabled or disabled channels.
    """
    try:
        async with OpenClawGatewayProxyService() as service:
            result = await service.list_channels(enabled_only=enabled if enabled else False)

            # If filtering for disabled only, filter the results
            if enabled is False:
                result["channels"] = [ch for ch in result["channels"] if not ch["enabled"]]
                result["total"] = len(result["channels"])

            logger.info(f"Listed {result['total']} channels (enabled filter: {enabled})")
            return ChannelListResponse(**result)

    except (ConnectionError, TimeoutError) as e:
        logger.error(f"Gateway connection failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenClaw Gateway is unavailable"
        )
    except Exception as e:
        logger.error(f"Failed to list channels: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve channels: {str(e)}"
        )


@router.post(
    "/{channel_id}/enable",
    response_model=ChannelEnableResponse,
    status_code=status.HTTP_200_OK,
    summary="Enable a channel globally",
    description="""
    Enable a communication channel for global use across the workspace.

    This operation:
    1. Updates the channel configuration in ~/.openclaw/openclaw.json
    2. Marks the channel as enabled globally
    3. Allows agents to use this channel for communication

    **Note:** Enabling a channel does not automatically connect it. Connection
    typically requires additional authentication (e.g., WhatsApp QR code scan).

    **Idempotency:** This operation is idempotent. Enabling an already-enabled
    channel will return success without making changes.

    **Path Parameters:**
    - `channel_id`: Channel identifier (whatsapp, telegram, discord, slack, etc.)

    **Use Cases:**
    - Enable WhatsApp for customer support agents
    - Activate Telegram for internal team communication
    - Turn on Discord for community management
    """,
    responses={
        200: {
            "description": "Channel enabled successfully",
            "model": ChannelEnableResponse
        },
        404: {
            "description": "Channel not found",
            "model": ChannelErrorResponse
        },
        500: {
            "description": "Configuration update failed",
            "model": ChannelErrorResponse
        }
    }
)
async def enable_channel(channel_id: str) -> ChannelEnableResponse:
    """
    Enable a communication channel globally.

    Args:
        channel_id: Channel identifier (e.g., 'whatsapp', 'telegram')

    Returns:
        Channel enable confirmation with status
    """
    try:
        async with OpenClawGatewayProxyService() as service:
            result = await service.enable_channel(channel_id)
            logger.info(f"Channel '{channel_id}' enabled successfully")
            return ChannelEnableResponse(**result)

    except (ChannelNotFoundError, ValueError) as e:
        logger.warning(f"Channel not found: {channel_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found"
        )
    except ConfigurationError as e:
        logger.error(f"Configuration update failed for '{channel_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable channel: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error enabling channel '{channel_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to enable channel: {str(e)}"
        )


@router.post(
    "/{channel_id}/disable",
    response_model=ChannelDisableResponse,
    status_code=status.HTTP_200_OK,
    summary="Disable a channel globally",
    description="""
    Disable a communication channel across the workspace.

    This operation:
    1. Updates the channel configuration in ~/.openclaw/openclaw.json
    2. Marks the channel as disabled globally
    3. Prevents agents from using this channel for communication
    4. Disconnects any active connections (if applicable)

    **Idempotency:** This operation is idempotent. Disabling an already-disabled
    channel will return success without making changes.

    **Path Parameters:**
    - `channel_id`: Channel identifier (whatsapp, telegram, discord, slack, etc.)

    **Use Cases:**
    - Temporarily disable a channel during maintenance
    - Turn off unused channels to reduce resource usage
    - Revoke channel access for security reasons
    """,
    responses={
        200: {
            "description": "Channel disabled successfully",
            "model": ChannelDisableResponse
        },
        404: {
            "description": "Channel not found",
            "model": ChannelErrorResponse
        },
        500: {
            "description": "Configuration update failed",
            "model": ChannelErrorResponse
        }
    }
)
async def disable_channel(channel_id: str) -> ChannelDisableResponse:
    """
    Disable a communication channel globally.

    Args:
        channel_id: Channel identifier (e.g., 'whatsapp', 'telegram')

    Returns:
        Channel disable confirmation with status
    """
    try:
        async with OpenClawGatewayProxyService() as service:
            result = await service.disable_channel(channel_id)
            logger.info(f"Channel '{channel_id}' disabled successfully")
            return ChannelDisableResponse(**result)

    except (ChannelNotFoundError, ValueError) as e:
        logger.warning(f"Channel not found: {channel_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found"
        )
    except ConfigurationError as e:
        logger.error(f"Configuration update failed for '{channel_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable channel: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Unexpected error disabling channel '{channel_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to disable channel: {str(e)}"
        )


@router.get(
    "/{channel_id}/status",
    response_model=ChannelStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Get channel connection status",
    description="""
    Get detailed status and connection information for a specific channel.

    This endpoint provides:
    - Whether the channel is enabled
    - Current connection status (connected/disconnected)
    - Last activity timestamp
    - Connection details (session ID, authentication status, etc.)

    **Status Values:**
    - `active`: Channel is enabled and connected
    - `disconnected`: Channel is enabled but not connected
    - `disabled`: Channel is not enabled
    - `error`: Channel encountered an error
    - `connecting`: Channel is attempting to connect

    **Path Parameters:**
    - `channel_id`: Channel identifier (whatsapp, telegram, discord, slack, etc.)

    **Use Cases:**
    - Monitor channel health in dashboard
    - Check if WhatsApp QR code scan is required
    - Verify authentication status before sending messages
    - Troubleshoot connection issues
    """,
    responses={
        200: {
            "description": "Channel status retrieved successfully",
            "model": ChannelStatusResponse
        },
        404: {
            "description": "Channel not found",
            "model": ChannelErrorResponse
        }
    }
)
async def get_channel_status(channel_id: str) -> ChannelStatusResponse:
    """
    Get detailed status of a communication channel.

    Args:
        channel_id: Channel identifier (e.g., 'whatsapp', 'telegram')

    Returns:
        Detailed channel status including connection details
    """
    try:
        async with OpenClawGatewayProxyService() as service:
            result = await service.get_channel_status(channel_id)
            logger.info(
                f"Retrieved status for channel '{channel_id}': "
                f"enabled={result['enabled']}, connected={result['connected']}"
            )
            return ChannelStatusResponse(**result)

    except (ChannelNotFoundError, ValueError) as e:
        logger.warning(f"Channel not found: {channel_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found"
        )
    except Exception as e:
        logger.error(f"Failed to get status for '{channel_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve channel status: {str(e)}"
        )


@router.put(
    "/{channel_id}/config",
    response_model=ChannelConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="Update channel configuration",
    description="""
    Update configuration settings for a specific channel.

    This endpoint allows you to configure channel-specific settings such as:
    - Auto-reconnect behavior
    - Maximum retry attempts
    - Connection timeout
    - Webhook URLs for event notifications
    - Custom channel-specific settings

    **Configuration updates are persisted to ~/.openclaw/openclaw.json**

    **Path Parameters:**
    - `channel_id`: Channel identifier (whatsapp, telegram, discord, slack, etc.)

    **Request Body:**
    All fields are optional. Only provided fields will be updated.

    **Supported Configuration:**
    - `auto_reconnect` (bool): Automatically reconnect on disconnect
    - `max_retries` (int): Maximum reconnection attempts (0-10)
    - `timeout` (int): Connection timeout in seconds (1-300)
    - `webhook_url` (str): URL for receiving channel events
    - `custom_settings` (object): Channel-specific custom settings

    **Use Cases:**
    - Configure WhatsApp auto-reconnect after network issues
    - Set custom timeout for slow networks
    - Configure webhook for real-time event notifications
    - Add channel-specific authentication credentials
    """,
    responses={
        200: {
            "description": "Configuration updated successfully",
            "model": ChannelConfigResponse
        },
        404: {
            "description": "Channel not found",
            "model": ChannelErrorResponse
        },
        422: {
            "description": "Invalid configuration values",
            "model": ChannelErrorResponse
        },
        500: {
            "description": "Configuration file update failed",
            "model": ChannelErrorResponse
        }
    }
)
async def update_channel_config(
    channel_id: str,
    config: ChannelConfigRequest
) -> ChannelConfigResponse:
    """
    Update configuration for a communication channel.

    Args:
        channel_id: Channel identifier (e.g., 'whatsapp', 'telegram')
        config: Configuration values to update

    Returns:
        Updated configuration confirmation
    """
    try:
        # Validate that at least one field is provided
        config_dict = config.model_dump(exclude_none=True)
        if not config_dict:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="At least one configuration field must be provided"
            )

        async with OpenClawGatewayProxyService() as service:
            result = await service.update_channel_config(channel_id, config_dict)
            logger.info(
                f"Updated configuration for channel '{channel_id}': "
                f"{list(config_dict.keys())}"
            )
            return ChannelConfigResponse(**result)

    except (ChannelNotFoundError, ValueError) as e:
        logger.warning(f"Channel not found: {channel_id}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Channel '{channel_id}' not found"
        )
    except ConfigurationError as e:
        logger.error(f"Configuration update failed for '{channel_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update channel configuration: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error updating config for '{channel_id}': {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update channel configuration: {str(e)}"
        )
