"""
Integration tests for WireGuard Peer Provisioning Service

Tests the complete provisioning workflow from API endpoint to database persistence.
Implements E1-S3: WireGuard Peer Provisioning Service

Test Coverage Requirements:
- >= 80% code coverage
- BDD-style test naming (Given/When/Then)
- Integration tests for cross-component functionality
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
import ipaddress
from datetime import datetime
from typing import Dict, Any


class TestWireGuardProvisioning:
    """Integration tests for WireGuard peer provisioning"""

    @pytest.fixture
    def mock_app(self):
        """Create a mock FastAPI application with provisioning endpoint"""
        from fastapi import FastAPI
        app = FastAPI()

        # Import and include the router (will be created later)
        try:
            from backend.api.v1.endpoints.wireguard_provisioning import router
            app.include_router(router, prefix="/api/v1")
        except ImportError:
            # Router doesn't exist yet - this is TDD
            pass

        return app

    @pytest.fixture
    def client(self, mock_app):
        """Create test client"""
        return TestClient(mock_app)

    @pytest.fixture
    def valid_provision_request(self) -> Dict[str, Any]:
        """Valid provisioning request payload"""
        return {
            "node_id": "test-node-001",
            "public_key": "jKlMnOpQrStUvWxYzAbCdEfGhIjKlMnO=",
            "wireguard_public_key": "test_wireguard_public_key_base64==",
            "capabilities": {
                "gpu_count": 1,
                "gpu_memory_mb": 16384,
                "cpu_cores": 8,
                "models": ["llama-2-7b"]
            },
            "version": "1.0.0"
        }

    def test_provision_new_peer_success(self, client, valid_provision_request):
        """
        Given valid node credentials
        When provisioning new peer
        Then should return config with assigned IP

        Acceptance Criteria:
        - Validate node credentials
        - Assign unique IP address
        - Update hub WireGuard config
        - Return peer configuration
        - Store provisioning record in DBOS (if available)
        """
        # Mock the provisioning service
        with patch('backend.services.wireguard_provisioning_service.WireGuardProvisioningService') as mock_service:
            mock_instance = MagicMock()
            mock_service.return_value = mock_instance

            # Setup mock response
            mock_instance.provision_peer.return_value = {
                "node_id": "test-node-001",
                "assigned_ip": "10.0.0.2",
                "subnet_mask": "255.255.255.0",
                "hub_public_key": "hub_public_key_base64==",
                "hub_endpoint": "hub.example.com:51820",
                "allowed_ips": "10.0.0.0/24",
                "persistent_keepalive": 25,
                "dns_servers": ["10.0.0.1"],
                "provisioned_at": datetime.utcnow().isoformat()
            }

            # Make request
            response = client.post(
                "/api/v1/wireguard/provision",
                json=valid_provision_request
            )

            # Assertions
            assert response.status_code == 200
            data = response.json()

            assert "assigned_ip" in data
            assert "hub_public_key" in data
            assert "hub_endpoint" in data

            # Validate IP address format
            ip = ipaddress.ip_address(data["assigned_ip"])
            assert ip.is_private
            assert str(ip).startswith("10.0.0.")

    def test_provision_duplicate_peer_rejected(self, client, valid_provision_request):
        """
        Given already provisioned peer
        When provisioning again
        Then should return error with existing config

        Acceptance Criteria:
        - Detect duplicate peer_id or public_key
        - Return 409 Conflict status
        - Include existing configuration in error response
        """
        with patch('backend.services.wireguard_provisioning_service.WireGuardProvisioningService') as mock_service:
            mock_instance = MagicMock()
            mock_service.return_value = mock_instance

            # Setup mock to raise duplicate error
            from backend.services.wireguard_provisioning_service import DuplicatePeerError
            mock_instance.provision_peer.side_effect = DuplicatePeerError(
                peer_id="test-node-001",
                existing_config={
                    "node_id": "test-node-001",
                    "assigned_ip": "10.0.0.2"
                }
            )

            response = client.post(
                "/api/v1/wireguard/provision",
                json=valid_provision_request
            )

            # Should return 409 Conflict
            assert response.status_code == 409
            data = response.json()

            assert "already provisioned" in data["detail"].lower()
            assert "existing_config" in data

    def test_provision_ip_exhaustion(self, client, valid_provision_request):
        """
        Given IP pool exhausted
        When provisioning new peer
        Then should return error indicating no IPs available

        Acceptance Criteria:
        - Detect when IP address pool is exhausted
        - Return 503 Service Unavailable
        - Provide helpful error message
        """
        with patch('backend.services.wireguard_provisioning_service.WireGuardProvisioningService') as mock_service:
            mock_instance = MagicMock()
            mock_service.return_value = mock_instance

            # Setup mock to raise IP exhaustion error
            from backend.services.wireguard_provisioning_service import IPPoolExhaustedError
            mock_instance.provision_peer.side_effect = IPPoolExhaustedError(
                pool_range="10.0.0.2-10.0.0.254",
                allocated_count=253
            )

            response = client.post(
                "/api/v1/wireguard/provision",
                json=valid_provision_request
            )

            # Should return 503 Service Unavailable
            assert response.status_code == 503
            data = response.json()

            assert "ip" in data["detail"].lower()
            assert "exhausted" in data["detail"].lower() or "available" in data["detail"].lower()

    def test_provision_invalid_credentials(self, client):
        """
        Given invalid node credentials
        When provisioning
        Then should return 400 Bad Request with validation errors
        """
        invalid_request = {
            "node_id": "",  # Empty node_id
            "public_key": "invalid_key",  # Invalid format
        }

        response = client.post(
            "/api/v1/wireguard/provision",
            json=invalid_request
        )

        assert response.status_code == 422  # Validation error
        data = response.json()
        assert "detail" in data

    def test_provision_missing_required_fields(self, client):
        """
        Given request missing required fields
        When provisioning
        Then should return 422 with validation errors
        """
        incomplete_request = {
            "node_id": "test-node-001"
            # Missing public_key, wireguard_public_key, etc.
        }

        response = client.post(
            "/api/v1/wireguard/provision",
            json=incomplete_request
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data


class TestIPAddressPoolManagement:
    """Tests for IP address pool management"""

    def test_allocate_unique_ip_addresses(self):
        """
        Given IP address pool
        When allocating multiple IPs
        Then should return unique addresses
        """
        from backend.services.ip_pool_manager import IPPoolManager

        pool = IPPoolManager(
            network="10.0.0.0/24",
            reserved_ips=["10.0.0.1"]  # Hub IP
        )

        # Allocate 10 IPs
        allocated_ips = set()
        for i in range(10):
            ip = pool.allocate_ip(peer_id=f"peer-{i}")
            allocated_ips.add(ip)

        # All should be unique
        assert len(allocated_ips) == 10

        # All should be in valid range
        for ip_str in allocated_ips:
            ip = ipaddress.ip_address(ip_str)
            assert ip in ipaddress.ip_network("10.0.0.0/24")
            assert str(ip) != "10.0.0.1"  # Not the reserved hub IP

    def test_ip_pool_exhaustion_detection(self):
        """
        Given small IP pool
        When all IPs allocated
        Then should raise IPPoolExhaustedError
        """
        from backend.services.ip_pool_manager import IPPoolManager
        from backend.services.wireguard_provisioning_service import IPPoolExhaustedError

        # Very small pool: 10.0.0.0/29 = 8 addresses (6 usable)
        pool = IPPoolManager(
            network="10.0.0.0/29",
            reserved_ips=["10.0.0.1"]
        )

        # Allocate all available IPs
        for i in range(6):
            pool.allocate_ip(peer_id=f"peer-{i}")

        # Next allocation should fail
        with pytest.raises(IPPoolExhaustedError):
            pool.allocate_ip(peer_id="peer-overflow")

    def test_deallocate_ip_address(self):
        """
        Given allocated IP address
        When deallocating
        Then should return IP to pool
        """
        from backend.services.ip_pool_manager import IPPoolManager

        pool = IPPoolManager(network="10.0.0.0/24")

        # Allocate IP
        ip1 = pool.allocate_ip(peer_id="peer-1")

        # Deallocate
        pool.deallocate_ip(peer_id="peer-1")

        # Should be able to allocate again
        ip2 = pool.allocate_ip(peer_id="peer-2")

        # Should get the same IP (first available)
        assert ip2 == ip1


class TestWireGuardConfigUpdate:
    """Tests for WireGuard configuration update automation"""

    def test_add_peer_to_hub_config(self):
        """
        Given new peer configuration
        When adding to hub config
        Then should update config file and reload
        """
        from backend.services.wireguard_config_manager import WireGuardConfigManager

        manager = WireGuardConfigManager(
            config_path="/tmp/test_wg0.conf"
        )

        # Add peer
        manager.add_peer(
            public_key="test_public_key==",
            allowed_ips=["10.0.0.2/32"],
            persistent_keepalive=25
        )

        # Config should contain peer
        config = manager.get_config()
        assert "test_public_key==" in config

    def test_remove_peer_from_hub_config(self):
        """
        Given existing peer
        When removing from hub config
        Then should update config and reload
        """
        from backend.services.wireguard_config_manager import WireGuardConfigManager

        manager = WireGuardConfigManager(
            config_path="/tmp/test_wg0.conf"
        )

        # Add then remove peer
        manager.add_peer(
            public_key="test_public_key==",
            allowed_ips=["10.0.0.2/32"]
        )
        manager.remove_peer(public_key="test_public_key==")

        # Config should not contain peer
        config = manager.get_config()
        assert "test_public_key==" not in config


class TestProvisioningServiceIntegration:
    """End-to-end integration tests for provisioning service"""

    def test_complete_provisioning_workflow(self):
        """
        Given valid provisioning request
        When processing through service layer
        Then should complete all steps successfully

        Steps:
        1. Validate credentials
        2. Allocate IP from pool
        3. Update hub WireGuard config
        4. Store record in database (if available)
        5. Return complete configuration
        """
        from backend.services.wireguard_provisioning_service import WireGuardProvisioningService

        service = WireGuardProvisioningService(
            ip_pool_network="10.0.0.0/24",
            hub_public_key="hub_key==",
            hub_endpoint="hub.example.com:51820"
        )

        config = service.provision_peer(
            node_id="test-node-001",
            public_key="peer_key==",
            wireguard_public_key="wg_peer_key==",
            capabilities={
                "gpu_count": 1,
                "cpu_cores": 8
            }
        )

        # Verify complete configuration returned
        assert config["node_id"] == "test-node-001"
        assert "assigned_ip" in config
        assert config["hub_public_key"] == "hub_key=="
        assert config["hub_endpoint"] == "hub.example.com:51820"
        assert "provisioned_at" in config

    def test_concurrent_provisioning_no_ip_collision(self):
        """
        Given multiple concurrent provisioning requests
        When processing simultaneously
        Then should not assign same IP to different peers
        """
        from backend.services.wireguard_provisioning_service import WireGuardProvisioningService
        import threading

        service = WireGuardProvisioningService(
            ip_pool_network="10.0.0.0/24"
        )

        allocated_ips = []
        errors = []

        def provision_peer(node_id: str):
            try:
                config = service.provision_peer(
                    node_id=node_id,
                    public_key=f"key_{node_id}",
                    wireguard_public_key=f"wg_key_{node_id}",
                    capabilities={}
                )
                allocated_ips.append(config["assigned_ip"])
            except Exception as e:
                errors.append(e)

        # Create 10 threads
        threads = []
        for i in range(10):
            t = threading.Thread(target=provision_peer, args=(f"node-{i}",))
            threads.append(t)
            t.start()

        # Wait for all threads
        for t in threads:
            t.join()

        # No errors should occur
        assert len(errors) == 0

        # All IPs should be unique
        assert len(allocated_ips) == len(set(allocated_ips))
