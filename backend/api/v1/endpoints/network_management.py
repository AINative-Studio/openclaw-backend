"""
P2P Network Management UI Endpoints

FastAPI endpoints for P2P network visualization and management.
Designed for UI consumption with rich metadata for WireGuard peers,
network topology graphs, QR code generation, and IP pool monitoring.

Story: Issue #85 - Create P2P Network Management UI Endpoints
Story Points: 3

Provides:
- GET /api/v1/network/peers - List all peers with rich metadata
- GET /api/v1/network/peers/{peer_id}/quality - Network quality metrics for peer
- POST /api/v1/network/peers/{peer_id}/provision-qr - Generate QR code for mobile provisioning
- GET /api/v1/network/ip-pool - IP pool status and allocation
- GET /api/v1/network/topology - Network graph data (nodes + edges)

Security:
- Input validation via Pydantic models
- Error handling with appropriate HTTP status codes
- QR codes generated server-side to prevent tampering
"""

import logging
import asyncio
import subprocess
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field, ConfigDict
import base64
import io

# QR code generation
try:
    import qrcode
    QRCODE_AVAILABLE = True
except ImportError:
    QRCODE_AVAILABLE = False
    logging.warning("qrcode library not available - QR generation will fail")

from backend.services.wireguard_provisioning_service import WireGuardProvisioningService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/network", tags=["Network Management", "P2P", "UI"])


# ============================================================================
# Response Models
# ============================================================================

class PeerMetadata(BaseModel):
    """Rich metadata for a WireGuard peer"""
    node_id: str = Field(..., description="Unique node identifier")
    assigned_ip: str = Field(..., description="Assigned IP address")
    wireguard_public_key: str = Field(..., description="WireGuard public key")
    provisioned_at: str = Field(..., description="ISO 8601 provisioning timestamp")
    capabilities: Dict[str, Any] = Field(..., description="Node capabilities")
    version: str = Field(..., description="Node software version")


class PeerListResponse(BaseModel):
    """Response for peer list endpoint"""
    peers: List[PeerMetadata] = Field(..., description="List of provisioned peers")
    total_count: int = Field(..., description="Total number of peers")
    timestamp: str = Field(..., description="ISO 8601 timestamp of response")


class PeerQualityMetrics(BaseModel):
    """Network quality metrics for a specific peer"""
    peer_id: str = Field(..., description="Node identifier")
    assigned_ip: str = Field(..., description="Peer IP address")
    latency_ms: Optional[float] = Field(None, description="Round-trip latency in milliseconds")
    packet_loss_percent: Optional[float] = Field(None, description="Packet loss percentage")
    bandwidth_mbps: Optional[float] = Field(None, description="Estimated bandwidth in Mbps")
    last_handshake_seconds: Optional[int] = Field(None, description="Seconds since last handshake")
    connection_status: str = Field(..., description="Connection status: healthy/degraded/unhealthy")
    received_bytes: Optional[int] = Field(None, description="Total bytes received")
    sent_bytes: Optional[int] = Field(None, description="Total bytes sent")
    uptime_seconds: Optional[int] = Field(None, description="Connection uptime in seconds")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class QRCodeResponse(BaseModel):
    """Response for QR code generation"""
    peer_id: str = Field(..., description="Node identifier")
    qr_code: str = Field(..., description="Base64-encoded PNG QR code image")
    config_text: str = Field(..., description="Plain text WireGuard configuration")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class IPAllocation(BaseModel):
    """Individual IP allocation"""
    peer_id: str = Field(..., description="Node identifier")
    ip_address: str = Field(..., description="Allocated IP address")
    allocated_at: str = Field(..., description="ISO 8601 allocation timestamp")


class IPPoolStatus(BaseModel):
    """IP pool status and statistics"""
    total_addresses: int = Field(..., description="Total addresses in pool")
    reserved_addresses: int = Field(..., description="Reserved addresses (hub, broadcast)")
    allocated_addresses: int = Field(..., description="Currently allocated addresses")
    available_addresses: int = Field(..., description="Available addresses")
    utilization_percent: int = Field(..., description="Pool utilization percentage")
    network_cidr: str = Field(..., description="Network CIDR notation")
    hub_ip: str = Field(..., description="Hub IP address")
    allocations: List[IPAllocation] = Field(..., description="Current IP allocations")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class TopologyNode(BaseModel):
    """Network topology node (hub or peer)"""
    id: str = Field(..., description="Node identifier")
    label: str = Field(..., description="Human-readable label")
    type: str = Field(..., description="Node type: hub or peer")
    ip_address: str = Field(..., description="IP address")
    public_key: str = Field(..., description="WireGuard public key")
    capabilities: Optional[Dict[str, Any]] = Field(None, description="Node capabilities (peers only)")
    status: Optional[str] = Field(None, description="Health status (peers only)")


class TopologyEdge(BaseModel):
    """Network topology edge (connection)"""
    source: str = Field(..., description="Source node ID")
    target: str = Field(..., description="Target node ID")
    bandwidth_mbps: Optional[float] = Field(None, description="Connection bandwidth")
    latency_ms: Optional[float] = Field(None, description="Connection latency")
    status: str = Field(..., description="Connection status: active/inactive")


class TopologyMetadata(BaseModel):
    """Topology metadata"""
    total_peers: int = Field(..., description="Total number of peers")
    healthy_peers: int = Field(..., description="Number of healthy peers")
    total_connections: int = Field(..., description="Total active connections")
    timestamp: str = Field(..., description="ISO 8601 timestamp")


class NetworkTopology(BaseModel):
    """Complete network topology graph"""
    nodes: List[TopologyNode] = Field(..., description="Network nodes (hub + peers)")
    edges: List[TopologyEdge] = Field(..., description="Network connections")
    metadata: TopologyMetadata = Field(..., description="Topology metadata")


# ============================================================================
# Dependency Injection
# ============================================================================

# Singleton instance of provisioning service (reuse from wireguard_provisioning.py)
_provisioning_service: Optional[WireGuardProvisioningService] = None


def get_provisioning_service() -> WireGuardProvisioningService:
    """
    Get or create provisioning service instance

    Returns:
        WireGuardProvisioningService instance
    """
    import os
    global _provisioning_service

    if _provisioning_service is None:
        config_path = os.getenv(
            "WIREGUARD_CONFIG_PATH",
            "/Users/aideveloper/openclaw-backend/.wireguard/wg0.conf"
        )
        _provisioning_service = WireGuardProvisioningService(
            ip_pool_network=os.getenv("WIREGUARD_IP_POOL", "10.8.0.0/24"),
            hub_public_key=os.getenv("WIREGUARD_HUB_PUBLIC_KEY", "hub_wireguard_public_key_placeholder=="),
            hub_endpoint=os.getenv("WIREGUARD_HUB_ENDPOINT", "localhost:51820"),
            hub_ip=os.getenv("WIREGUARD_HUB_IP", "10.8.0.1"),
            config_path=config_path,
            enable_dbos=False
        )

    return _provisioning_service


# ============================================================================
# Helper Functions
# ============================================================================

def _calculate_peer_quality(peer_id: str, assigned_ip: str) -> Dict[str, Any]:
    """
    Calculate network quality metrics for a peer

    Uses ping tests and WireGuard stats to determine connection quality.

    Args:
        peer_id: Node identifier
        assigned_ip: Peer IP address

    Returns:
        Dictionary with quality metrics
    """
    timestamp = datetime.now(timezone.utc).isoformat()

    # Ping peer to measure latency
    is_reachable, latency_ms = _ping_peer(assigned_ip, timeout=2)

    # Determine connection status
    if not is_reachable:
        connection_status = "unhealthy"
    elif latency_ms and latency_ms > 100:
        connection_status = "degraded"
    else:
        connection_status = "healthy"

    # Try to get WireGuard stats
    wg_stats = _get_wireguard_peer_stats(assigned_ip)

    return {
        'peer_id': peer_id,
        'assigned_ip': assigned_ip,
        'latency_ms': latency_ms,
        'packet_loss_percent': 0.0 if is_reachable else 100.0,
        'bandwidth_mbps': wg_stats.get('bandwidth_mbps'),
        'last_handshake_seconds': wg_stats.get('last_handshake_seconds'),
        'connection_status': connection_status,
        'received_bytes': wg_stats.get('received_bytes'),
        'sent_bytes': wg_stats.get('sent_bytes'),
        'uptime_seconds': wg_stats.get('uptime_seconds'),
        'timestamp': timestamp
    }


def _ping_peer(ip_address: str, timeout: int = 2) -> tuple[bool, Optional[float]]:
    """
    Ping peer to check reachability and measure latency

    Args:
        ip_address: Target IP address
        timeout: Ping timeout in seconds

    Returns:
        Tuple of (is_reachable, latency_ms)
    """
    try:
        # Use platform-specific ping command
        # macOS/Linux: ping -c 1 -W <timeout>
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), ip_address],
            capture_output=True,
            text=True,
            timeout=timeout + 1
        )

        if result.returncode == 0:
            # Parse latency from output
            # Example: "time=23.5 ms"
            import re
            match = re.search(r'time=([0-9.]+)\s*ms', result.stdout)
            latency_ms = float(match.group(1)) if match else None
            return True, latency_ms

        return False, None

    except (subprocess.TimeoutExpired, Exception) as e:
        logger.debug(f"Ping to {ip_address} failed: {e}")
        return False, None


def _get_wireguard_peer_stats(peer_ip: str) -> Dict[str, Any]:
    """
    Get WireGuard statistics for a peer

    Args:
        peer_ip: Peer IP address

    Returns:
        Dictionary with WireGuard stats (or empty if unavailable)
    """
    try:
        # Run `wg show wg0 dump` to get peer stats
        result = subprocess.run(
            ["wg", "show", "wg0", "dump"],
            capture_output=True,
            text=True,
            timeout=5
        )

        if result.returncode == 0:
            # Parse output to find peer by allowed IPs
            # Format: <public_key>\t<preshared_key>\t<endpoint>\t<allowed_ips>\t<latest_handshake>\t<rx_bytes>\t<tx_bytes>\t<keepalive>
            for line in result.stdout.strip().split('\n')[1:]:  # Skip header
                parts = line.split('\t')
                if len(parts) >= 7:
                    allowed_ips = parts[3]
                    if peer_ip in allowed_ips:
                        latest_handshake = int(parts[4]) if parts[4] and parts[4] != '0' else None
                        rx_bytes = int(parts[5]) if parts[5] else 0
                        tx_bytes = int(parts[6]) if parts[6] else 0

                        # Calculate last handshake age
                        import time
                        current_time = int(time.time())
                        last_handshake_seconds = current_time - latest_handshake if latest_handshake else None

                        return {
                            'last_handshake_seconds': last_handshake_seconds,
                            'received_bytes': rx_bytes,
                            'sent_bytes': tx_bytes,
                            'bandwidth_mbps': None,  # Would need time-series data
                            'uptime_seconds': None
                        }

        return {}

    except Exception as e:
        logger.debug(f"Failed to get WireGuard stats for {peer_ip}: {e}")
        return {}


def _generate_wireguard_config_text(peer_config: Dict[str, Any]) -> str:
    """
    Generate WireGuard configuration file text

    Args:
        peer_config: Peer configuration dictionary

    Returns:
        WireGuard configuration in INI format
    """
    dns_servers = peer_config.get('dns_servers', ['10.0.0.1'])
    dns_line = ', '.join(dns_servers)

    config_text = f"""[Interface]
Address = {peer_config['assigned_ip']}/32
DNS = {dns_line}
# PrivateKey = <GENERATE_YOUR_PRIVATE_KEY>

[Peer]
PublicKey = {peer_config['hub_public_key']}
Endpoint = {peer_config['hub_endpoint']}
AllowedIPs = {peer_config['allowed_ips']}
PersistentKeepalive = 25
"""

    return config_text


def _generate_qr_code_image(data: str) -> str:
    """
    Generate QR code image and encode as base64

    Args:
        data: Data to encode in QR code

    Returns:
        Base64-encoded PNG image

    Raises:
        HTTPException: If qrcode library not available
    """
    if not QRCODE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="QR code generation not available - qrcode library not installed"
        )

    # Generate QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    # Create image
    img = qr.make_image(fill_color="black", back_color="white")

    # Convert to base64
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    img_base64 = base64.b64encode(buffer.read()).decode('utf-8')

    return img_base64


# ============================================================================
# API Endpoints
# ============================================================================

@router.get(
    "/peers",
    response_model=PeerListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all WireGuard peers with rich metadata",
    description="""
    Get list of all provisioned WireGuard peers with rich metadata for UI display.

    Returns comprehensive information for each peer including:
    - Node identifier and IP address
    - WireGuard public key
    - Provisioning timestamp
    - Hardware capabilities (GPU, CPU, memory)
    - Software version

    **Use Case:**
    Used by UI to display peer inventory in network management dashboard.
    """
)
async def list_network_peers(
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> PeerListResponse:
    """
    List all provisioned peers with rich metadata

    Args:
        service: Provisioning service instance (injected)

    Returns:
        PeerListResponse with peer list and count
    """
    try:
        peers_dict = service.list_provisioned_peers()

        # Convert to rich metadata format
        peers = [
            PeerMetadata(
                node_id=peer_config['node_id'],
                assigned_ip=peer_config['assigned_ip'],
                wireguard_public_key=peer_config.get('wireguard_public_key', ''),
                provisioned_at=peer_config.get('provisioned_at', ''),
                capabilities=peer_config.get('capabilities', {}),
                version=peer_config.get('version', 'unknown')
            )
            for peer_config in peers_dict.values()
        ]

        timestamp = datetime.now(timezone.utc).isoformat()

        return PeerListResponse(
            peers=peers,
            total_count=len(peers),
            timestamp=timestamp
        )

    except Exception as e:
        logger.error(f"Error listing network peers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list network peers"
        )


@router.get(
    "/peers/{peer_id}/quality",
    response_model=PeerQualityMetrics,
    status_code=status.HTTP_200_OK,
    summary="Get network quality metrics for peer",
    description="""
    Get detailed network quality metrics for a specific peer.

    Metrics include:
    - Latency (round-trip time)
    - Packet loss percentage
    - Bandwidth estimation
    - Last handshake time
    - Connection status (healthy/degraded/unhealthy)
    - Data transfer statistics

    **Use Case:**
    Used by UI to display real-time connection quality and troubleshoot issues.
    """
)
async def get_peer_quality(
    peer_id: str,
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> PeerQualityMetrics:
    """
    Get network quality metrics for a peer

    Args:
        peer_id: Node identifier
        service: Provisioning service instance (injected)

    Returns:
        PeerQualityMetrics with connection quality data

    Raises:
        HTTPException: If peer not found
    """
    try:
        # Check if peer exists
        peer_config = service.get_peer_config(node_id=peer_id)

        if peer_config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Peer {peer_id} not found"
            )

        # Calculate quality metrics
        quality = _calculate_peer_quality(peer_id, peer_config['assigned_ip'])

        return PeerQualityMetrics(**quality)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting peer quality: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get peer quality metrics"
        )


@router.post(
    "/peers/{peer_id}/provision-qr",
    response_model=QRCodeResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate QR code for mobile provisioning",
    description="""
    Generate a QR code for easy mobile WireGuard provisioning.

    The QR code contains the complete WireGuard configuration that can be scanned
    by the WireGuard mobile app for instant setup.

    **Returns:**
    - Base64-encoded PNG QR code image
    - Plain text WireGuard configuration
    - Timestamp

    **Use Case:**
    Used by UI to display QR code for mobile device provisioning.
    User scans QR code with WireGuard app to automatically configure connection.

    **Note:**
    User must generate their own private key and insert it into the config.
    """
)
async def generate_provision_qr(
    peer_id: str,
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> QRCodeResponse:
    """
    Generate QR code for WireGuard provisioning

    Args:
        peer_id: Node identifier
        service: Provisioning service instance (injected)

    Returns:
        QRCodeResponse with QR code image and config text

    Raises:
        HTTPException: If peer not found or QR generation fails
    """
    try:
        # Get peer configuration
        peer_config = service.get_peer_config(node_id=peer_id)

        if peer_config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Peer {peer_id} not found"
            )

        # Generate WireGuard config text
        config_text = _generate_wireguard_config_text(peer_config)

        # Generate QR code
        qr_code_base64 = _generate_qr_code_image(config_text)

        timestamp = datetime.now(timezone.utc).isoformat()

        return QRCodeResponse(
            peer_id=peer_id,
            qr_code=qr_code_base64,
            config_text=config_text,
            timestamp=timestamp
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating QR code: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate QR code"
        )


@router.get(
    "/ip-pool",
    response_model=IPPoolStatus,
    status_code=status.HTTP_200_OK,
    summary="Get IP pool status and allocations",
    description="""
    Get detailed IP address pool status and allocation information.

    Returns:
    - Total, reserved, allocated, and available address counts
    - Pool utilization percentage
    - Network CIDR and hub IP
    - Complete list of current allocations with timestamps

    **Use Case:**
    Used by UI to monitor IP pool capacity and troubleshoot allocation issues.
    Alert when utilization exceeds threshold (e.g., 90%).
    """
)
async def get_ip_pool_status(
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> IPPoolStatus:
    """
    Get IP pool status and allocations

    Args:
        service: Provisioning service instance (injected)

    Returns:
        IPPoolStatus with pool statistics and allocations
    """
    try:
        # Get pool statistics
        pool_stats = service.get_pool_stats()

        # Get network details
        network_cidr = str(service.ip_pool.network.with_prefixlen)
        hub_ip = service.hub_ip

        # Build allocation list
        allocations = []
        for peer_id, ip_address in service.ip_pool.allocated.items():
            # Get provisioning timestamp
            peer_config = service.get_peer_config(node_id=peer_id)
            allocated_at = peer_config.get('provisioned_at', '') if peer_config else ''

            allocations.append(IPAllocation(
                peer_id=peer_id,
                ip_address=ip_address,
                allocated_at=allocated_at
            ))

        timestamp = datetime.now(timezone.utc).isoformat()

        return IPPoolStatus(
            total_addresses=pool_stats['total_addresses'],
            reserved_addresses=pool_stats['reserved_addresses'],
            allocated_addresses=pool_stats['allocated_addresses'],
            available_addresses=pool_stats['available_addresses'],
            utilization_percent=pool_stats['utilization_percent'],
            network_cidr=network_cidr,
            hub_ip=hub_ip,
            allocations=allocations,
            timestamp=timestamp
        )

    except Exception as e:
        logger.error(f"Error getting IP pool status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get IP pool status"
        )


@router.get(
    "/topology",
    response_model=NetworkTopology,
    status_code=status.HTTP_200_OK,
    summary="Get network topology graph data",
    description="""
    Get network topology as a graph with nodes and edges for visualization.

    **Nodes:**
    - Hub node (central VPN server)
    - Peer nodes (connected devices/agents)

    **Edges:**
    - Hub-to-peer connections with quality metrics

    **Use Case:**
    Used by UI to render interactive network topology graph.
    Visualize network structure, peer capabilities, and connection health.

    **Visualization Libraries:**
    Compatible with D3.js, Cytoscape.js, vis.js, etc.
    """
)
async def get_network_topology(
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> NetworkTopology:
    """
    Get network topology graph data

    Args:
        service: Provisioning service instance (injected)

    Returns:
        NetworkTopology with nodes, edges, and metadata
    """
    try:
        peers_dict = service.list_provisioned_peers()

        # Build nodes list
        nodes = []

        # Add hub node (hub is always online if this endpoint is serving)
        hub_node = TopologyNode(
            id='hub',
            label='Hub Node',
            type='hub',
            ip_address=service.hub_ip,
            public_key=service.hub_public_key,
            status='online'
        )
        nodes.append(hub_node)

        # Add peer nodes
        edges = []
        healthy_count = 0

        for peer_config in peers_dict.values():
            peer_id = peer_config['node_id']
            assigned_ip = peer_config['assigned_ip']

            # Calculate peer quality for status
            quality = _calculate_peer_quality(peer_id, assigned_ip)
            peer_status = quality['connection_status']

            if peer_status == 'healthy':
                healthy_count += 1

            # Add peer node
            peer_node = TopologyNode(
                id=peer_id,
                label=f"Peer {peer_id}",
                type='peer',
                ip_address=assigned_ip,
                public_key=peer_config.get('wireguard_public_key', ''),
                capabilities=peer_config.get('capabilities', {}),
                status=peer_status
            )
            nodes.append(peer_node)

            # Add edge from hub to peer
            edge = TopologyEdge(
                source='hub',
                target=peer_id,
                bandwidth_mbps=quality.get('bandwidth_mbps'),
                latency_ms=quality.get('latency_ms'),
                status='active' if peer_status != 'unhealthy' else 'inactive'
            )
            edges.append(edge)

        # Build metadata
        timestamp = datetime.now(timezone.utc).isoformat()
        metadata = TopologyMetadata(
            total_peers=len(peers_dict),
            healthy_peers=healthy_count,
            total_connections=len(edges),
            timestamp=timestamp
        )

        return NetworkTopology(
            nodes=nodes,
            edges=edges,
            metadata=metadata
        )

    except Exception as e:
        logger.error(f"Error getting network topology: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get network topology"
        )
