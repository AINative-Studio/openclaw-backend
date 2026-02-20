"""
P2P networking module for OpenCLAW Agent Swarm.

This module provides libp2p integration for peer-to-peer communication,
including bootstrap node connectivity and DHT-based peer discovery.
"""

from .libp2p_bootstrap import (
    LibP2PBootstrapClient,
    BootstrapConnectionError,
    BootstrapResult,
    PeerInfo,
    DHTStatus,
)

__all__ = [
    'LibP2PBootstrapClient',
    'BootstrapConnectionError',
    'BootstrapResult',
    'PeerInfo',
    'DHTStatus',
]
