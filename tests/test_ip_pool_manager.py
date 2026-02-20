"""
Unit tests for IP Pool Manager

Tests IP address allocation, deallocation, and exhaustion detection.
Part of E1-S3: WireGuard Peer Provisioning Service
"""

import pytest
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.ip_pool_manager import IPPoolManager
from backend.services.wireguard_provisioning_service import IPPoolExhaustedError


class TestIPPoolManager:
    """Unit tests for IPPoolManager"""

    def test_initialize_pool(self):
        """
        Given network CIDR
        When initializing pool
        Then should create pool with correct capacity
        """
        pool = IPPoolManager(network="10.0.0.0/24", reserved_ips=["10.0.0.1"])

        # 256 addresses - 2 (network/broadcast) - 1 (reserved) = 253 available
        assert pool.available_count() == 253

    def test_allocate_ip_address(self):
        """
        Given IP pool
        When allocating IP
        Then should return valid IP from range
        """
        pool = IPPoolManager(network="10.0.0.0/24", reserved_ips=["10.0.0.1"])

        ip = pool.allocate_ip(peer_id="test-peer-1")

        # Should be valid IP in range
        assert ip.startswith("10.0.0.")
        assert ip != "10.0.0.1"  # Not the reserved IP
        assert ip != "10.0.0.0"  # Not network address
        assert ip != "10.0.0.255"  # Not broadcast

    def test_allocate_multiple_unique_ips(self):
        """
        Given IP pool
        When allocating multiple IPs
        Then should return unique addresses
        """
        pool = IPPoolManager(network="10.0.0.0/24", reserved_ips=["10.0.0.1"])

        ips = set()
        for i in range(10):
            ip = pool.allocate_ip(peer_id=f"peer-{i}")
            ips.add(ip)

        # All should be unique
        assert len(ips) == 10

    def test_duplicate_peer_allocation_fails(self):
        """
        Given peer with allocated IP
        When allocating again
        Then should raise ValueError
        """
        pool = IPPoolManager(network="10.0.0.0/24")

        pool.allocate_ip(peer_id="peer-1")

        with pytest.raises(ValueError, match="already has IP"):
            pool.allocate_ip(peer_id="peer-1")

    def test_deallocate_ip(self):
        """
        Given allocated IP
        When deallocating
        Then should return IP to pool
        """
        pool = IPPoolManager(network="10.0.0.0/24")

        ip = pool.allocate_ip(peer_id="peer-1")
        pool.deallocate_ip(peer_id="peer-1")

        # Should be able to allocate again (will get same IP)
        ip2 = pool.allocate_ip(peer_id="peer-2")
        assert ip2 == ip

    def test_ip_pool_exhaustion(self):
        """
        Given small IP pool
        When all IPs allocated
        Then should raise IPPoolExhaustedError
        """
        # Very small pool: /29 = 8 addresses (6 usable after network/broadcast)
        pool = IPPoolManager(network="10.0.0.0/29", reserved_ips=["10.0.0.1"])

        # Allocate all available IPs (5 after reserved)
        for i in range(5):
            pool.allocate_ip(peer_id=f"peer-{i}")

        # Next allocation should fail
        with pytest.raises(IPPoolExhaustedError):
            pool.allocate_ip(peer_id="peer-overflow")

    def test_get_pool_stats(self):
        """
        Given IP pool with allocations
        When getting stats
        Then should return correct statistics
        """
        pool = IPPoolManager(network="10.0.0.0/24", reserved_ips=["10.0.0.1"])

        # Allocate 10 IPs
        for i in range(10):
            pool.allocate_ip(peer_id=f"peer-{i}")

        stats = pool.get_pool_stats()

        assert stats["total_addresses"] == 254  # 256 - 2 (network/broadcast)
        assert stats["reserved_addresses"] == 1
        assert stats["allocated_addresses"] == 10
        assert stats["available_addresses"] == 243  # 254 - 1 - 10

    def test_thread_safety(self):
        """
        Given concurrent allocations
        When multiple threads allocate
        Then should not allocate duplicate IPs
        """
        import threading

        pool = IPPoolManager(network="10.0.0.0/24")
        allocated_ips = []
        lock = threading.Lock()

        def allocate(peer_id):
            ip = pool.allocate_ip(peer_id=peer_id)
            with lock:
                allocated_ips.append(ip)

        # Create 20 threads
        threads = []
        for i in range(20):
            t = threading.Thread(target=allocate, args=(f"peer-{i}",))
            threads.append(t)
            t.start()

        # Wait for all
        for t in threads:
            t.join()

        # All IPs should be unique
        assert len(allocated_ips) == len(set(allocated_ips))
