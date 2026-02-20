"""
Networking module for WireGuard and P2P infrastructure

This module contains networking-related components for the OpenClaw P2P swarm.
"""

from backend.networking.wireguard_config import (
    WireGuardConfig,
    WireGuardInterface,
    WireGuardPeer,
    IPAddressAllocator,
    generate_wireguard_keypair,
    generate_node_config,
)

__all__ = [
    "WireGuardConfig",
    "WireGuardInterface",
    "WireGuardPeer",
    "IPAddressAllocator",
    "generate_wireguard_keypair",
    "generate_node_config",
]
