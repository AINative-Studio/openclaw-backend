"""
Unit tests for WireGuard Provisioning Service

Tests the complete provisioning service layer.
Part of E1-S3: WireGuard Peer Provisioning Service
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.services.wireguard_provisioning_service import (
    WireGuardProvisioningService,
    DuplicatePeerError,
    IPPoolExhaustedError,
    InvalidCredentialsError
)


class TestWireGuardProvisioningService:
    """Unit tests for WireGuardProvisioningService"""

    @pytest.fixture
    def service(self, tmp_path):
        """Create provisioning service with temporary config"""
        config_path = tmp_path / "wg0.conf"
        return WireGuardProvisioningService(
            ip_pool_network="10.0.0.0/28",  # Small pool for testing (14 addresses)
            hub_public_key="hub_test_key==",
            hub_endpoint="hub.test.com:51820",
            hub_ip="10.0.0.1",
            config_path=str(config_path),
            enable_dbos=False
        )

    def test_provision_peer_success(self, service):
        """
        Given valid peer request
        When provisioning
        Then should return complete configuration
        """
        config = service.provision_peer(
            node_id="test-node-1",
            public_key="peer_public_key==",
            wireguard_public_key="wg_peer_key==",
            capabilities={"gpu_count": 1, "cpu_cores": 8},
            version="1.0.0"
        )

        assert config["node_id"] == "test-node-1"
        assert "assigned_ip" in config
        assert config["hub_public_key"] == "hub_test_key=="
        assert config["hub_endpoint"] == "hub.test.com:51820"
        assert "provisioned_at" in config

    def test_provision_duplicate_peer_fails(self, service):
        """
        Given already provisioned peer
        When provisioning again
        Then should raise DuplicatePeerError
        """
        service.provision_peer(
            node_id="test-node-1",
            public_key="peer_key==",
            wireguard_public_key="wg_key==",
            capabilities={}
        )

        with pytest.raises(DuplicatePeerError) as exc_info:
            service.provision_peer(
                node_id="test-node-1",
                public_key="peer_key==",
                wireguard_public_key="wg_key==",
                capabilities={}
            )

        assert exc_info.value.peer_id == "test-node-1"

    def test_provision_ip_pool_exhaustion(self, service):
        """
        Given small IP pool
        When all IPs allocated
        Then should raise IPPoolExhaustedError
        """
        # Pool has 13 available IPs (14 - 1 reserved hub IP)
        for i in range(13):
            service.provision_peer(
                node_id=f"node-{i}",
                public_key=f"key-{i}",
                wireguard_public_key=f"wg_key-{i}",
                capabilities={}
            )

        # Next allocation should fail
        with pytest.raises(IPPoolExhaustedError):
            service.provision_peer(
                node_id="overflow-node",
                public_key="overflow_key",
                wireguard_public_key="wg_overflow_key",
                capabilities={}
            )

    def test_provision_invalid_credentials(self, service):
        """
        Given invalid credentials
        When provisioning
        Then should raise InvalidCredentialsError
        """
        with pytest.raises(InvalidCredentialsError):
            service.provision_peer(
                node_id="",  # Empty node_id
                public_key="key",
                wireguard_public_key="",  # Empty wg key
                capabilities={}
            )

    def test_get_peer_config(self, service):
        """
        Given provisioned peer
        When getting config
        Then should return configuration
        """
        service.provision_peer(
            node_id="test-node-1",
            public_key="key",
            wireguard_public_key="wg_key",
            capabilities={}
        )

        config = service.get_peer_config("test-node-1")

        assert config is not None
        assert config["node_id"] == "test-node-1"

    def test_get_nonexistent_peer_config(self, service):
        """
        Given nonexistent peer
        When getting config
        Then should return None
        """
        config = service.get_peer_config("nonexistent")

        assert config is None

    def test_list_provisioned_peers(self, service):
        """
        Given multiple provisioned peers
        When listing peers
        Then should return all peers
        """
        service.provision_peer(
            node_id="peer-1",
            public_key="key1",
            wireguard_public_key="wg_key1",
            capabilities={}
        )
        service.provision_peer(
            node_id="peer-2",
            public_key="key2",
            wireguard_public_key="wg_key2",
            capabilities={}
        )

        peers = service.list_provisioned_peers()

        assert len(peers) == 2
        assert "peer-1" in peers
        assert "peer-2" in peers

    def test_get_pool_stats(self, service):
        """
        Given provisioning service
        When getting pool stats
        Then should return statistics
        """
        stats = service.get_pool_stats()

        assert "total_addresses" in stats
        assert "available_addresses" in stats
        assert "allocated_addresses" in stats

    def test_concurrent_provisioning(self, service):
        """
        Given concurrent provisioning requests
        When multiple threads provision
        Then should not allocate duplicate IPs
        """
        import threading

        results = []
        errors = []
        lock = threading.Lock()

        def provision(node_id):
            try:
                config = service.provision_peer(
                    node_id=node_id,
                    public_key=f"key_{node_id}",
                    wireguard_public_key=f"wg_key_{node_id}",
                    capabilities={}
                )
                with lock:
                    results.append(config["assigned_ip"])
            except Exception as e:
                with lock:
                    errors.append(e)

        threads = []
        for i in range(10):
            t = threading.Thread(target=provision, args=(f"concurrent-node-{i}",))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # No duplicate IPs
        assert len(results) == len(set(results))

        # No errors
        assert len(errors) == 0
