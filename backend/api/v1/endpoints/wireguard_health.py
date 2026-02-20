"""
WireGuard Network Health API Endpoint

Provides real-time health monitoring for WireGuard network connections.
Part of E1-S6 - WireGuard Network Monitoring.

Returns:
- Connection health status (healthy/degraded/unhealthy)
- Peer count and health metrics
- Data transfer statistics
- Network quality metrics
- Optional detailed peer information

Refs #E1-S6
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)

try:
    from backend.services.wireguard_monitoring_service import WireGuardMonitoringService
    WIREGUARD_MONITORING_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"WireGuard monitoring service not available: {e}")
    WIREGUARD_MONITORING_AVAILABLE = False

router = APIRouter(prefix="/wireguard", tags=["WireGuard", "Monitoring", "Networking"])


# ============================================================================
# Response Models
# ============================================================================

class PeerDetail(BaseModel):
    """Detailed information about a WireGuard peer"""
    public_key: str = Field(..., description="Peer public key")
    endpoint: Optional[str] = Field(None, description="Peer endpoint (IP:port)")
    allowed_ips: List[str] = Field(..., description="Allowed IP addresses for this peer")
    latest_handshake_seconds: Optional[int] = Field(
        None,
        description="Seconds since last handshake (None if never connected)"
    )
    received_bytes: int = Field(..., description="Total bytes received from peer")
    sent_bytes: int = Field(..., description="Total bytes sent to peer")
    persistent_keepalive: Optional[str] = Field(
        None,
        description="Persistent keepalive setting"
    )
    is_stale: bool = Field(..., description="Whether connection is considered stale")


class WireGuardHealthResponse(BaseModel):
    """WireGuard network health response"""
    model_config = ConfigDict(exclude_none=True)

    status: str = Field(
        ...,
        description="Overall health status: 'healthy', 'degraded', 'unhealthy'"
    )
    interface: str = Field(..., description="WireGuard interface name")
    public_key: Optional[str] = Field(None, description="Interface public key")
    listening_port: Optional[int] = Field(None, description="WireGuard listening port")
    peer_count: int = Field(..., description="Total number of peers")
    healthy_peers: int = Field(..., description="Number of healthy peers (recent handshake)")
    stale_peers: int = Field(..., description="Number of stale peers (old handshake)")
    stale_peer_list: List[str] = Field(
        ...,
        description="List of public keys for stale peers"
    )
    total_received_bytes: int = Field(..., description="Total bytes received across all peers")
    total_sent_bytes: int = Field(..., description="Total bytes sent across all peers")
    timestamp: str = Field(..., description="ISO 8601 timestamp of health check")
    peers: Optional[List[PeerDetail]] = Field(
        None,
        description="Detailed peer information (only if include_peers=true)"
    )


class NetworkQualityResponse(BaseModel):
    """Network quality metrics"""
    total_received_bytes: int = Field(..., description="Total bytes received")
    total_sent_bytes: int = Field(..., description="Total bytes sent")
    active_connections: int = Field(..., description="Number of active peer connections")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


# ============================================================================
# Helper Functions
# ============================================================================

def get_wireguard_service(
    interface: str = 'wg0',
    stale_threshold: int = 300
) -> WireGuardMonitoringService:
    """
    Get WireGuard monitoring service instance

    Args:
        interface: WireGuard interface name
        stale_threshold: Seconds after which connection is considered stale

    Returns:
        WireGuardMonitoringService instance

    Raises:
        HTTPException: If service is not available
    """
    if not WIREGUARD_MONITORING_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="WireGuard monitoring service is not available"
        )

    return WireGuardMonitoringService(
        interface=interface,
        stale_threshold_seconds=stale_threshold
    )


def format_peer_details(
    peers: List[Dict[str, Any]],
    stale_threshold_seconds: int
) -> List[PeerDetail]:
    """
    Format peer data into PeerDetail models

    Args:
        peers: List of peer dictionaries
        stale_threshold_seconds: Threshold for stale detection

    Returns:
        List of PeerDetail models
    """
    formatted_peers = []

    for peer in peers:
        handshake_age = peer.get('latest_handshake_seconds')
        is_stale = (
            handshake_age is not None and
            handshake_age > stale_threshold_seconds
        )

        formatted_peers.append(PeerDetail(
            public_key=peer['public_key'],
            endpoint=peer.get('endpoint'),
            allowed_ips=peer.get('allowed_ips', []),
            latest_handshake_seconds=handshake_age,
            received_bytes=peer.get('received_bytes', 0),
            sent_bytes=peer.get('sent_bytes', 0),
            persistent_keepalive=peer.get('persistent_keepalive'),
            is_stale=is_stale
        ))

    return formatted_peers


# ============================================================================
# API Endpoints
# ============================================================================

@router.get(
    "/health",
    response_model=WireGuardHealthResponse,
    response_model_exclude_none=True,
    status_code=status.HTTP_200_OK,
    summary="Get WireGuard network health",
    description="""
    Get real-time health status of WireGuard network connections.

    This endpoint provides:
    - Overall health status (healthy/degraded/unhealthy)
    - Interface information and listening port
    - Peer count and health metrics
    - Stale connection detection
    - Data transfer statistics
    - Optional detailed peer information

    **Health Status Definitions:**
    - `healthy`: All peers have recent handshakes
    - `degraded`: Some peers are healthy, some are stale
    - `unhealthy`: No peers or all peers are stale

    **Query Parameters:**
    - `interface`: WireGuard interface name (default: wg0)
    - `stale_threshold`: Seconds after which peer is stale (default: 300)
    - `include_peers`: Include detailed peer list (default: false)

    **Use Case:**
    Used for monitoring WireGuard VPN connections and detecting network issues.

    **Rate Limiting:** No specific limits for monitoring endpoints
    """,
    responses={
        200: {
            "description": "Health check completed successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "interface": "wg0",
                        "public_key": "ServerPublicKeyABC123==",
                        "listening_port": 51820,
                        "peer_count": 3,
                        "healthy_peers": 3,
                        "stale_peers": 0,
                        "stale_peer_list": [],
                        "total_received_bytes": 1073741824,
                        "total_sent_bytes": 536870912,
                        "timestamp": "2026-02-19T17:30:00Z"
                    }
                }
            }
        },
        500: {"description": "Internal Server Error - Failed to check health"},
        503: {"description": "Service Unavailable - WireGuard monitoring not available"}
    }
)
async def get_wireguard_health(
    interface: str = Query('wg0', description="WireGuard interface name"),
    stale_threshold: int = Query(
        300,
        description="Seconds after which peer is considered stale",
        ge=60,
        le=3600
    ),
    include_peers: bool = Query(
        False,
        description="Include detailed peer information in response"
    )
) -> WireGuardHealthResponse:
    """
    Get WireGuard network health status and metrics.

    This endpoint implements monitoring for E1-S6 - WireGuard Network Monitoring.

    **Query Parameters:**
    - `interface`: WireGuard interface to monitor (default: wg0)
    - `stale_threshold`: Seconds before peer is stale (default: 300, range: 60-3600)
    - `include_peers`: If true, include detailed peer list

    **Returns:**
    - Health status and metrics
    - Peer counts and stale detection
    - Transfer statistics
    - Optional peer details
    """
    try:
        # Get monitoring service
        service = get_wireguard_service(
            interface=interface,
            stale_threshold=stale_threshold
        )

        # Get comprehensive health summary
        health = service.get_health_summary()

        # Format peer details if requested
        peers = None
        if include_peers:
            stats = service.collect_peer_stats()
            peers = format_peer_details(
                stats['peers'],
                service.stale_threshold_seconds
            )

        # Build response
        response = WireGuardHealthResponse(
            status=health['status'],
            interface=health['interface'],
            public_key=health.get('public_key'),
            listening_port=health.get('listening_port'),
            peer_count=health['peer_count'],
            healthy_peers=health['healthy_peers'],
            stale_peers=health['stale_peers'],
            stale_peer_list=health['stale_peer_list'],
            total_received_bytes=health['total_received_bytes'],
            total_sent_bytes=health['total_sent_bytes'],
            timestamp=health['timestamp'],
            peers=peers
        )

        logger.info(
            f"WireGuard health check: status={response.status}, "
            f"peers={response.peer_count}, healthy={response.healthy_peers}"
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Error checking WireGuard health: {e}",
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check WireGuard health: {str(e)}"
        )


@router.get(
    "/quality",
    response_model=NetworkQualityResponse,
    status_code=status.HTTP_200_OK,
    summary="Get network quality metrics",
    description="""
    Get network quality metrics from WireGuard transfer statistics.

    Returns aggregated data transfer metrics across all peers.

    **Query Parameters:**
    - `interface`: WireGuard interface name (default: wg0)
    """,
    responses={
        200: {"description": "Quality metrics retrieved successfully"},
        500: {"description": "Internal Server Error"},
        503: {"description": "Service Unavailable"}
    }
)
async def get_network_quality(
    interface: str = Query('wg0', description="WireGuard interface name")
) -> NetworkQualityResponse:
    """
    Get network quality metrics

    **Returns:**
    - Total bytes transferred (sent/received)
    - Active connection count
    """
    try:
        service = get_wireguard_service(interface=interface)
        quality = service.calculate_network_quality()

        return NetworkQualityResponse(**quality)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating network quality: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to calculate network quality: {str(e)}"
        )
