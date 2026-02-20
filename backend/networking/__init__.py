"""
WireGuard Networking Package

Provides WireGuard connectivity management for P2P swarm nodes.
Includes connection initialization, health monitoring, and hub management.
"""

from backend.networking.wireguard_node_connector import (
    WireGuardNodeConnector,
    WireGuardNodeConnectorError,
    ConfigValidationError,
    ConnectionError,
    ConnectionTimeout,
    ping_host
)

from backend.networking.wireguard_hub_manager import (
    WireGuardHubManager,
    PeerConfig,
    WireGuardError,
    ConfigReloadError,
    PeerNotFoundError,
    ConnectivityCheckError,
)

__all__ = [
    "WireGuardNodeConnector",
    "WireGuardNodeConnectorError",
    "ConfigValidationError",
    "ConnectionError",
    "ConnectionTimeout",
    "ping_host",
    "WireGuardHubManager",
    "PeerConfig",
    "WireGuardError",
    "ConfigReloadError",
    "PeerNotFoundError",
    "ConnectivityCheckError",
]
