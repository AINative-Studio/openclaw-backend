"""
IP Address Pool Manager

Manages IP address allocation for WireGuard peers.
Implements thread-safe IP allocation with exhaustion detection.

Part of E1-S3: WireGuard Peer Provisioning Service

Security considerations:
- Thread-safe allocation to prevent race conditions
- Reserved IPs protected from allocation
- Network/broadcast addresses excluded
"""

import ipaddress
import threading
from typing import Set, Optional, List, Dict
import logging

logger = logging.getLogger(__name__)


class IPPoolManager:
    """
    Thread-safe IP address pool manager for WireGuard peers

    Manages allocation and deallocation of IP addresses from a given network range.
    Prevents duplicate allocations and tracks reserved IPs.

    Attributes:
        network: IPv4Network representing the address pool
        reserved_ips: Set of reserved IP addresses (e.g., hub IP)
        allocated: Dict mapping peer_id to allocated IP address
        _lock: Thread lock for concurrent access safety
    """

    def __init__(
        self,
        network: str,
        reserved_ips: Optional[List[str]] = None
    ):
        """
        Initialize IP pool manager

        Args:
            network: Network CIDR (e.g., "10.0.0.0/24")
            reserved_ips: List of reserved IP addresses (e.g., ["10.0.0.1"])

        Raises:
            ValueError: If network CIDR is invalid
        """
        try:
            self.network = ipaddress.ip_network(network, strict=False)
        except ValueError as e:
            raise ValueError(f"Invalid network CIDR: {e}")

        # Initialize reserved IPs (network, broadcast, and user-specified)
        self.reserved_ips: Set[str] = set()

        # Always reserve network and broadcast addresses
        self.reserved_ips.add(str(self.network.network_address))
        self.reserved_ips.add(str(self.network.broadcast_address))

        # Add user-specified reserved IPs
        if reserved_ips:
            for ip_str in reserved_ips:
                try:
                    ip = ipaddress.ip_address(ip_str)
                    if ip not in self.network:
                        raise ValueError(
                            f"Reserved IP {ip_str} is not in network {network}"
                        )
                    self.reserved_ips.add(str(ip))
                except ValueError as e:
                    raise ValueError(f"Invalid reserved IP {ip_str}: {e}")

        # Track allocated IPs: peer_id -> IP address
        self.allocated: Dict[str, str] = {}

        # Thread lock for concurrent access
        self._lock = threading.Lock()

        logger.info(
            f"Initialized IP pool: network={network}, "
            f"reserved={len(self.reserved_ips)}, "
            f"available={self.available_count()}"
        )

    def available_count(self) -> int:
        """
        Get count of available IP addresses

        Returns:
            Number of unallocated, non-reserved IPs
        """
        total_hosts = self.network.num_addresses - 2  # Exclude network/broadcast
        reserved_count = len(self.reserved_ips) - 2  # Already excluded network/broadcast
        allocated_count = len(self.allocated)
        return total_hosts - reserved_count - allocated_count

    def allocate_ip(self, peer_id: str) -> str:
        """
        Allocate an IP address to a peer

        Thread-safe allocation that prevents duplicate IPs.

        Args:
            peer_id: Unique identifier for the peer

        Returns:
            Allocated IP address as string

        Raises:
            IPPoolExhaustedError: If no IPs available
            ValueError: If peer_id already has an IP allocated
        """
        with self._lock:
            # Check if peer already has an IP
            if peer_id in self.allocated:
                raise ValueError(
                    f"Peer {peer_id} already has IP {self.allocated[peer_id]} allocated"
                )

            # Find first available IP
            allocated_set = set(self.allocated.values())

            for ip in self.network.hosts():
                ip_str = str(ip)

                # Skip reserved and allocated IPs
                if ip_str in self.reserved_ips or ip_str in allocated_set:
                    continue

                # Allocate this IP
                self.allocated[peer_id] = ip_str
                logger.info(f"Allocated IP {ip_str} to peer {peer_id}")
                return ip_str

            # No IPs available
            from backend.services.wireguard_provisioning_service import IPPoolExhaustedError
            raise IPPoolExhaustedError(
                pool_range=str(self.network),
                allocated_count=len(self.allocated)
            )

    def deallocate_ip(self, peer_id: str) -> None:
        """
        Deallocate IP address from a peer

        Args:
            peer_id: Peer identifier to deallocate

        Raises:
            ValueError: If peer_id has no IP allocated
        """
        with self._lock:
            if peer_id not in self.allocated:
                raise ValueError(f"Peer {peer_id} has no IP allocated")

            ip = self.allocated.pop(peer_id)
            logger.info(f"Deallocated IP {ip} from peer {peer_id}")

    def get_allocated_ip(self, peer_id: str) -> Optional[str]:
        """
        Get IP address allocated to a peer

        Args:
            peer_id: Peer identifier

        Returns:
            Allocated IP address or None if not allocated
        """
        return self.allocated.get(peer_id)

    def is_allocated(self, ip_address: str) -> bool:
        """
        Check if an IP address is allocated

        Args:
            ip_address: IP address to check

        Returns:
            True if IP is allocated to a peer
        """
        return ip_address in self.allocated.values()

    def get_pool_stats(self) -> Dict[str, int]:
        """
        Get pool statistics

        Returns:
            Dictionary with pool statistics
        """
        total = self.network.num_addresses - 2  # Exclude network/broadcast
        reserved = len(self.reserved_ips) - 2
        allocated = len(self.allocated)
        available = total - reserved - allocated

        return {
            "total_addresses": total,
            "reserved_addresses": reserved,
            "allocated_addresses": allocated,
            "available_addresses": available,
            "utilization_percent": int((allocated / total) * 100) if total > 0 else 0
        }
