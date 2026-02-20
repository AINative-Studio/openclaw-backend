"""
OpenClaw Gateway Status API Endpoint

Provides real-time status monitoring for OpenClaw Gateway integration.
Part of Issue #1058 - Agent Monitoring Dashboard.

Returns:
- Connection status and state
- Gateway URL and WhatsApp session info
- Uptime metrics
- Last command details
- Optional command history (last 10 commands)

Refs #1058
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)

try:
    from app.agents.orchestration.openclaw_bridge_factory import get_openclaw_bridge
    OPENCLAW_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"OpenClaw bridge not available: {e}")
    OPENCLAW_AVAILABLE = False

    # Create mock function for when OpenClaw is not available
    def get_openclaw_bridge():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenClaw Gateway integration is not available"
        )

router = APIRouter(prefix="/openclaw", tags=["OpenClaw", "Monitoring"])


# ============================================================================
# Response Models
# ============================================================================

class OpenClawCommand(BaseModel):
    """Command executed on OpenClaw Gateway"""
    command: str = Field(..., description="Command name (e.g., 'send_message')")
    session_key: Optional[str] = Field(None, description="Target session key")
    message: Optional[str] = Field(None, description="Message content if applicable")
    timestamp: str = Field(..., description="ISO 8601 timestamp of command execution")
    status: str = Field(..., description="Command status: 'success', 'failed', 'pending'")


class OpenClawStatusResponse(BaseModel):
    """OpenClaw Gateway status response"""
    model_config = ConfigDict(exclude_none=True)

    connected: bool = Field(..., description="Whether bridge is connected to gateway")
    connection_state: str = Field(..., description="Current connection state")
    gateway_url: str = Field(..., description="WebSocket URL of OpenClaw Gateway")
    whatsapp_session: Optional[str] = Field(None, description="Active WhatsApp session key")
    uptime_seconds: int = Field(..., description="Time since connection in seconds")
    last_command: Optional[OpenClawCommand] = Field(None, description="Last command executed")
    command_history: Optional[List[OpenClawCommand]] = Field(
        None,
        description="Last 10 commands executed (only if include_history=true)"
    )


# ============================================================================
# Helper Functions
# ============================================================================

def calculate_uptime(connected_at: Optional[datetime]) -> int:
    """
    Calculate uptime in seconds since connection.

    Args:
        connected_at: Timestamp when connection was established

    Returns:
        Uptime in seconds (0 if not connected)
    """
    if not connected_at:
        return 0

    uptime_delta = datetime.utcnow() - connected_at
    return int(uptime_delta.total_seconds())


def format_command_history(
    command_history: List[Dict[str, Any]],
    limit: int = 10
) -> List[OpenClawCommand]:
    """
    Format command history for response, limiting to last N commands.

    Args:
        command_history: List of command dictionaries
        limit: Maximum number of commands to return

    Returns:
        List of OpenClawCommand models (most recent first)
    """
    # Take last N commands and reverse to get most recent first
    recent_commands = command_history[-limit:] if command_history else []
    recent_commands.reverse()

    formatted_commands = []
    for cmd in recent_commands:
        try:
            formatted_commands.append(OpenClawCommand(**cmd))
        except Exception as e:
            logger.warning(f"Failed to format command: {cmd}. Error: {e}")
            continue

    return formatted_commands


# ============================================================================
# API Endpoint
# ============================================================================

@router.get(
    "/status",
    response_model=OpenClawStatusResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Get OpenClaw Gateway status",
    description="""
    Get real-time status of OpenClaw Gateway connection and activity.

    This endpoint provides:
    - Connection status and state (connected, disconnected, reconnecting)
    - Gateway WebSocket URL
    - Active WhatsApp session identifier
    - Connection uptime in seconds
    - Last command executed with details
    - Optional command history (last 10 commands)

    **Connection States:**
    - `connected`: Active connection to gateway
    - `disconnected`: No connection
    - `connecting`: Attempting initial connection
    - `reconnecting`: Attempting to restore connection
    - `failed`: Connection failed

    **Query Parameters:**
    - `include_history`: Include last 10 commands in response (default: false)

    **Use Case:**
    Used by Agent Monitoring Dashboard to display real-time OpenClaw Gateway status.

    **Rate Limiting:** No specific limits for monitoring endpoints
    """,
    responses={
        200: {
            "description": "Status retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "connected": True,
                        "connection_state": "connected",
                        "gateway_url": "ws://127.0.0.1:18789",
                        "whatsapp_session": "whatsapp:group:120363401780756402@g.us",
                        "uptime_seconds": 7200,
                        "last_command": {
                            "command": "send_message",
                            "session_key": "whatsapp:group:120363401780756402@g.us",
                            "message": "Agent task completed",
                            "timestamp": "2026-02-06T10:30:00Z",
                            "status": "success"
                        },
                        "command_history": [
                            {
                                "command": "send_message",
                                "session_key": "whatsapp:group:120363401780756402@g.us",
                                "message": "Agent task completed",
                                "timestamp": "2026-02-06T10:30:00Z",
                                "status": "success"
                            }
                        ]
                    }
                }
            }
        },
        500: {"description": "Internal Server Error - Failed to retrieve status"}
    }
)
async def get_openclaw_status(
    include_history: bool = Query(
        False,
        description="Include command history (last 10 commands) in response"
    )
) -> OpenClawStatusResponse:
    """
    Get OpenClaw Gateway connection status and metrics.

    This endpoint implements monitoring for Issue #1058 - Agent Monitoring Dashboard.

    **Query Parameters:**
    - `include_history`: If true, include last 10 commands in response

    **Returns:**
    - Connection status and state
    - Gateway URL and session information
    - Uptime metrics
    - Last command executed
    - Optional command history
    """
    try:
        # Get OpenClaw bridge instance (singleton)
        bridge = get_openclaw_bridge()

        # Extract connection state
        connection_state = bridge.connection_state.value if hasattr(bridge.connection_state, 'value') else str(bridge.connection_state)

        # Calculate uptime
        uptime_seconds = calculate_uptime(
            getattr(bridge, 'connected_at', None)
        )

        # Format last command
        last_command = None
        if hasattr(bridge, 'last_command') and bridge.last_command:
            try:
                last_command = OpenClawCommand(**bridge.last_command)
            except Exception as e:
                logger.warning(f"Failed to format last_command: {e}")

        # Format command history if requested
        command_history = None
        if include_history:
            if hasattr(bridge, 'command_history'):
                command_history = format_command_history(bridge.command_history, limit=10)
            else:
                command_history = []

        # Build response
        response = OpenClawStatusResponse(
            connected=bridge.is_connected,
            connection_state=connection_state,
            gateway_url=bridge.url,
            whatsapp_session=getattr(bridge, 'whatsapp_session', None),
            uptime_seconds=uptime_seconds,
            last_command=last_command,
            command_history=command_history
        )

        logger.info(
            f"OpenClaw status retrieved: connected={response.connected}, "
            f"state={response.connection_state}, uptime={response.uptime_seconds}s"
        )

        return response

    except Exception as e:
        logger.error(
            f"Error retrieving OpenClaw Gateway status: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve OpenClaw status: {str(e)}"
        )
