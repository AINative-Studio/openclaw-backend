"""
P2P Network Management UI Endpoint Tests

Tests for network management endpoints designed for UI consumption.
Provides rich metadata for WireGuard peers, network topology visualization,
QR code generation for mobile provisioning, and IP pool status.

Story: Issue #85 - Create P2P Network Management UI Endpoints
Story Points: 3
Coverage Target: >= 80%
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone
import base64
import io


@pytest.fixture
def mock_provisioned_peers():
    """Mock provisioned peers data"""
    return {
        'peer-node-001': {
            'node_id': 'peer-node-001',
            'assigned_ip': '10.0.0.2',
            'wireguard_public_key': 'PeerKey1ABC123==',
            'provisioned_at': '2026-02-27T10:00:00Z',
            'capabilities': {
                'gpu_count': 1,
                'gpu_memory_mb': 8192,
                'cpu_cores': 8,
                'memory_mb': 16384,
                'models': ['gpt-4', 'claude-3']
            },
            'version': '1.0.0'
        },
        'peer-node-002': {
            'node_id': 'peer-node-002',
            'assigned_ip': '10.0.0.3',
            'wireguard_public_key': 'PeerKey2DEF456==',
            'provisioned_at': '2026-02-27T11:00:00Z',
            'capabilities': {
                'gpu_count': 0,
                'cpu_cores': 4,
                'memory_mb': 8192,
                'models': ['gpt-3.5']
            },
            'version': '1.0.1'
        }
    }


@pytest.fixture
def mock_peer_quality_metrics():
    """Mock network quality metrics for a peer"""
    return {
        'peer_id': 'peer-node-001',
        'assigned_ip': '10.0.0.2',
        'latency_ms': 23.5,
        'packet_loss_percent': 0.1,
        'bandwidth_mbps': 125.0,
        'last_handshake_seconds': 45,
        'connection_status': 'healthy',
        'received_bytes': 52428800,
        'sent_bytes': 126353408,
        'uptime_seconds': 3600,
        'timestamp': '2026-02-27T12:00:00Z'
    }


@pytest.fixture
def mock_ip_pool_stats():
    """Mock IP pool statistics"""
    return {
        'total_addresses': 253,
        'reserved_addresses': 1,
        'allocated_addresses': 2,
        'available_addresses': 250,
        'utilization_percent': 0,
        'network_cidr': '10.0.0.0/24',
        'hub_ip': '10.0.0.1',
        'allocations': [
            {
                'peer_id': 'peer-node-001',
                'ip_address': '10.0.0.2',
                'allocated_at': '2026-02-27T10:00:00Z'
            },
            {
                'peer_id': 'peer-node-002',
                'ip_address': '10.0.0.3',
                'allocated_at': '2026-02-27T11:00:00Z'
            }
        ]
    }


@pytest.fixture
def mock_network_topology():
    """Mock network topology graph data"""
    return {
        'nodes': [
            {
                'id': 'hub',
                'label': 'Hub Node',
                'type': 'hub',
                'ip_address': '10.0.0.1',
                'public_key': 'HubPublicKeyXYZ=='
            },
            {
                'id': 'peer-node-001',
                'label': 'Peer Node 001',
                'type': 'peer',
                'ip_address': '10.0.0.2',
                'public_key': 'PeerKey1ABC123==',
                'capabilities': {
                    'gpu_count': 1,
                    'cpu_cores': 8
                },
                'status': 'healthy'
            },
            {
                'id': 'peer-node-002',
                'label': 'Peer Node 002',
                'type': 'peer',
                'ip_address': '10.0.0.3',
                'public_key': 'PeerKey2DEF456==',
                'capabilities': {
                    'gpu_count': 0,
                    'cpu_cores': 4
                },
                'status': 'healthy'
            }
        ],
        'edges': [
            {
                'source': 'hub',
                'target': 'peer-node-001',
                'bandwidth_mbps': 125.0,
                'latency_ms': 23.5,
                'status': 'active'
            },
            {
                'source': 'hub',
                'target': 'peer-node-002',
                'bandwidth_mbps': 100.0,
                'latency_ms': 18.2,
                'status': 'active'
            }
        ],
        'metadata': {
            'total_peers': 2,
            'healthy_peers': 2,
            'total_connections': 2,
            'timestamp': '2026-02-27T12:00:00Z'
        }
    }


class TestNetworkPeersEndpoint:
    """Test GET /api/v1/network/peers endpoint"""

    def test_list_peers_success(self, mock_provisioned_peers):
        """
        GIVEN provisioned WireGuard peers
        WHEN requesting peer list
        THEN should return all peers with rich metadata
        """
        from backend.api.v1.endpoints.network_management import list_network_peers

        # Mock the provisioning service
        mock_service = Mock()
        mock_service.list_provisioned_peers.return_value = mock_provisioned_peers

        # Act
        import asyncio
        response = asyncio.run(list_network_peers(service=mock_service))

        # Assert
        assert 'peers' in response
        assert len(response['peers']) == 2
        assert response['total_count'] == 2

        # Verify peer details
        peer1 = next(p for p in response['peers'] if p['node_id'] == 'peer-node-001')
        assert peer1['assigned_ip'] == '10.0.0.2'
        assert peer1['capabilities']['gpu_count'] == 1
        assert peer1['version'] == '1.0.0'

    def test_list_peers_empty(self):
        """
        GIVEN no provisioned peers
        WHEN requesting peer list
        THEN should return empty list
        """
        from backend.api.v1.endpoints.network_management import list_network_peers

        mock_service = Mock()
        mock_service.list_provisioned_peers.return_value = {}

        import asyncio
        response = asyncio.run(list_network_peers(service=mock_service))

        assert response['peers'] == []
        assert response['total_count'] == 0

    def test_list_peers_service_error(self):
        """
        GIVEN provisioning service error
        WHEN requesting peer list
        THEN should raise HTTPException
        """
        from backend.api.v1.endpoints.network_management import list_network_peers
        from fastapi import HTTPException

        mock_service = Mock()
        mock_service.list_provisioned_peers.side_effect = Exception("Service unavailable")

        import asyncio
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(list_network_peers(service=mock_service))

        assert exc_info.value.status_code == 500


class TestPeerQualityEndpoint:
    """Test GET /api/v1/network/peers/{peer_id}/quality endpoint"""

    def test_get_peer_quality_success(self, mock_peer_quality_metrics):
        """
        GIVEN existing peer with quality metrics
        WHEN requesting peer quality
        THEN should return detailed quality metrics
        """
        from backend.api.v1.endpoints.network_management import get_peer_quality

        mock_service = Mock()
        # Simulate peer exists
        mock_service.get_peer_config.return_value = {
            'node_id': 'peer-node-001',
            'assigned_ip': '10.0.0.2'
        }

        # Mock quality metrics calculation
        with patch('backend.api.v1.endpoints.network_management._calculate_peer_quality') as mock_calc:
            mock_calc.return_value = mock_peer_quality_metrics

            import asyncio
            response = asyncio.run(get_peer_quality('peer-node-001', service=mock_service))

            assert response['peer_id'] == 'peer-node-001'
            assert response['latency_ms'] == 23.5
            assert response['packet_loss_percent'] == 0.1
            assert response['connection_status'] == 'healthy'

    def test_get_peer_quality_not_found(self):
        """
        GIVEN non-existent peer
        WHEN requesting peer quality
        THEN should raise 404 HTTPException
        """
        from backend.api.v1.endpoints.network_management import get_peer_quality
        from fastapi import HTTPException

        mock_service = Mock()
        mock_service.get_peer_config.return_value = None

        import asyncio
        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(get_peer_quality('non-existent-peer', service=mock_service))

        assert exc_info.value.status_code == 404

    def test_get_peer_quality_stale_connection(self):
        """
        GIVEN peer with stale connection
        WHEN requesting peer quality
        THEN should return degraded status
        """
        from backend.api.v1.endpoints.network_management import get_peer_quality

        mock_service = Mock()
        mock_service.get_peer_config.return_value = {
            'node_id': 'peer-node-001',
            'assigned_ip': '10.0.0.2'
        }

        with patch('backend.api.v1.endpoints.network_management._calculate_peer_quality') as mock_calc:
            mock_calc.return_value = {
                'peer_id': 'peer-node-001',
                'assigned_ip': '10.0.0.2',
                'latency_ms': 150.0,
                'packet_loss_percent': 5.0,
                'last_handshake_seconds': 400,
                'connection_status': 'degraded'
            }

            import asyncio
            response = asyncio.run(get_peer_quality('peer-node-001', service=mock_service))

        assert response['connection_status'] == 'degraded'
        assert response['latency_ms'] > 100


class TestProvisionQREndpoint:
    """Test POST /api/v1/network/peers/{peer_id}/provision-qr endpoint"""

    def test_generate_qr_code_success(self):
        """
        GIVEN existing peer configuration
        WHEN requesting QR code
        THEN should return base64-encoded QR code image
        """
        from backend.api.v1.endpoints.network_management import generate_provision_qr

        peer_config = {
            'node_id': 'peer-node-001',
            'assigned_ip': '10.0.0.2',
            'wireguard_public_key': 'PeerKey1ABC123==',
            'hub_public_key': 'HubKeyXYZ==',
            'hub_endpoint': 'hub.example.com:51820',
            'allowed_ips': '10.0.0.0/24'
        }

        mock_service = Mock()
        mock_service.get_peer_config.return_value = peer_config
        import asyncio
        response = asyncio.run(generate_provision_qr('peer-node-001', service=mock_service))

        assert 'qr_code' in response
        assert 'config_text' in response
        assert 'peer_id' in response
        assert response['peer_id'] == 'peer-node-001'

        # Verify QR code is base64-encoded
        try:
            base64.b64decode(response['qr_code'])
            is_valid_base64 = True
        except Exception:
            is_valid_base64 = False
        assert is_valid_base64

    def test_generate_qr_code_not_found(self):
        """
        GIVEN non-existent peer
        WHEN requesting QR code
        THEN should raise 404 HTTPException
        """
        from backend.api.v1.endpoints.network_management import generate_provision_qr
        from fastapi import HTTPException

        mock_service = Mock()
        mock_service.get_peer_config.return_value = None
        import asyncio
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(generate_provision_qr('non-existent-peer', service=mock_service))

        assert exc_info.value.status_code == 404

    def test_qr_code_contains_wireguard_config(self):
        """
        GIVEN peer configuration
        WHEN QR code is generated
        THEN config text should contain WireGuard format
        """
        from backend.api.v1.endpoints.network_management import generate_provision_qr

        peer_config = {
            'node_id': 'peer-node-001',
            'assigned_ip': '10.0.0.2',
            'wireguard_public_key': 'PeerKey1ABC123==',
            'hub_public_key': 'HubKeyXYZ==',
            'hub_endpoint': 'hub.example.com:51820',
            'allowed_ips': '10.0.0.0/24'
        }

        mock_service = Mock()
        mock_service.get_peer_config.return_value = peer_config
        import asyncio
        response = asyncio.run(generate_provision_qr('peer-node-001', service=mock_service))

        config_text = response['config_text']
        assert '[Interface]' in config_text
        assert '[Peer]' in config_text
        assert 'Address = 10.0.0.2' in config_text
        assert 'PublicKey = HubKeyXYZ==' in config_text
        assert 'Endpoint = hub.example.com:51820' in config_text


class TestIPPoolEndpoint:
    """Test GET /api/v1/network/ip-pool endpoint"""

    def test_get_ip_pool_stats_success(self, mock_ip_pool_stats):
        """
        GIVEN IP pool with allocations
        WHEN requesting IP pool stats
        THEN should return detailed pool status
        """
        from backend.api.v1.endpoints.network_management import get_ip_pool_status

        mock_service = Mock()
        mock_service.get_pool_stats.return_value = {
                'total_addresses': 253,
                'reserved_addresses': 1,
                'allocated_addresses': 2,
                'available_addresses': 250,
                'utilization_percent': 0
            }
        mock_service.ip_pool.network = Mock()
        mock_service.ip_pool.network.with_prefixlen = '10.0.0.0/24'
        mock_service.hub_ip = '10.0.0.1'
        mock_service.ip_pool.allocated = {
                'peer-node-001': '10.0.0.2',
                'peer-node-002': '10.0.0.3'
            }

            # Mock peer configs with timestamps
        def get_peer_config_side_effect(node_id):
                if node_id == 'peer-node-001':
                    return {'provisioned_at': '2026-02-27T10:00:00Z'}
                elif node_id == 'peer-node-002':
                    return {'provisioned_at': '2026-02-27T11:00:00Z'}
                return None

        mock_service.get_peer_config.side_effect = get_peer_config_side_effect
        import asyncio
        response = asyncio.run(get_ip_pool_status(service=mock_service))

        assert response['total_addresses'] == 253
        assert response['available_addresses'] == 250
        assert response['network_cidr'] == '10.0.0.0/24'
        assert response['hub_ip'] == '10.0.0.1'
        assert len(response['allocations']) == 2

    def test_get_ip_pool_stats_empty(self):
        """
        GIVEN IP pool with no allocations
        WHEN requesting IP pool stats
        THEN should return stats with empty allocations
        """
        from backend.api.v1.endpoints.network_management import get_ip_pool_status

        mock_service = Mock()
        mock_service.get_pool_stats.return_value = {
                'total_addresses': 253,
                'reserved_addresses': 1,
                'allocated_addresses': 0,
                'available_addresses': 252,
                'utilization_percent': 0
            }
        mock_service.ip_pool.network = Mock()
        mock_service.ip_pool.network.with_prefixlen = '10.0.0.0/24'
        mock_service.hub_ip = '10.0.0.1'
        mock_service.ip_pool.allocated = {}
        import asyncio
        response = asyncio.run(get_ip_pool_status(service=mock_service))

        assert response['allocated_addresses'] == 0
        assert response['allocations'] == []

    def test_get_ip_pool_high_utilization(self):
        """
        GIVEN IP pool with high utilization
        WHEN requesting IP pool stats
        THEN should reflect high utilization percentage
        """
        from backend.api.v1.endpoints.network_management import get_ip_pool_status

        mock_service = Mock()
        mock_service.get_pool_stats.return_value = {
                'total_addresses': 253,
                'reserved_addresses': 1,
                'allocated_addresses': 240,
                'available_addresses': 12,
                'utilization_percent': 94
            }
        mock_service.ip_pool.network = Mock()
        mock_service.ip_pool.network.with_prefixlen = '10.0.0.0/24'
        mock_service.hub_ip = '10.0.0.1'
        mock_service.ip_pool.allocated = {}
        import asyncio
        response = asyncio.run(get_ip_pool_status(service=mock_service))

        assert response['utilization_percent'] == 94
        assert response['available_addresses'] == 12


class TestNetworkTopologyEndpoint:
    """Test GET /api/v1/network/topology endpoint"""

    def test_get_topology_success(self, mock_network_topology, mock_provisioned_peers):
        """
        GIVEN active network with peers
        WHEN requesting topology
        THEN should return graph data with nodes and edges
        """
        from backend.api.v1.endpoints.network_management import get_network_topology

        mock_service = Mock()
        mock_service.list_provisioned_peers.return_value = mock_provisioned_peers
        mock_service.hub_ip = '10.0.0.1'
        mock_service.hub_public_key = 'HubPublicKeyXYZ=='
            # Mock quality metrics for edges
            with patch('backend.api.v1.endpoints.network_management._calculate_peer_quality') as mock_calc:
                def quality_side_effect(peer_id, assigned_ip):
                    if peer_id == 'peer-node-001':
                        return {'latency_ms': 23.5, 'bandwidth_mbps': 125.0, 'connection_status': 'healthy'}
                    else:
                        return {'latency_ms': 18.2, 'bandwidth_mbps': 100.0, 'connection_status': 'healthy'}

                mock_calc.side_effect = quality_side_effect

            import asyncio
            response = asyncio.run(get_network_topology(service=mock_service))

                assert 'nodes' in response
                assert 'edges' in response
                assert 'metadata' in response

                # Verify hub node exists
                hub_node = next(n for n in response['nodes'] if n['type'] == 'hub')
                assert hub_node['ip_address'] == '10.0.0.1'

                # Verify peer nodes
                peer_nodes = [n for n in response['nodes'] if n['type'] == 'peer']
                assert len(peer_nodes) == 2

                # Verify edges
                assert len(response['edges']) == 2
                edge1 = response['edges'][0]
                assert edge1['source'] == 'hub'
                assert 'latency_ms' in edge1

    def test_get_topology_no_peers(self):
        """
        GIVEN network with no peers
        WHEN requesting topology
        THEN should return only hub node
        """
        from backend.api.v1.endpoints.network_management import get_network_topology

        mock_service = Mock()
        mock_service.list_provisioned_peers.return_value = {}
        mock_service.hub_ip = '10.0.0.1'
        mock_service.hub_public_key = 'HubPublicKeyXYZ=='
        import asyncio
        response = asyncio.run(get_network_topology(service=mock_service))

        assert len(response['nodes']) == 1
        assert response['nodes'][0]['type'] == 'hub'
        assert len(response['edges']) == 0
        assert response['metadata']['total_peers'] == 0

    def test_get_topology_with_unhealthy_peers(self, mock_provisioned_peers):
        """
        GIVEN network with unhealthy peers
        WHEN requesting topology
        THEN should reflect peer health in node status
        """
        from backend.api.v1.endpoints.network_management import get_network_topology

        mock_service = Mock()
        mock_service.list_provisioned_peers.return_value = mock_provisioned_peers
        mock_service.hub_ip = '10.0.0.1'
        mock_service.hub_public_key = 'HubPublicKeyXYZ=='
            with patch('backend.api.v1.endpoints.network_management._calculate_peer_quality') as mock_calc:
                def quality_side_effect(peer_id, assigned_ip):
                    if peer_id == 'peer-node-001':
                        return {'latency_ms': 23.5, 'connection_status': 'healthy'}
                    else:
                        return {'latency_ms': 500.0, 'connection_status': 'unhealthy'}

                mock_calc.side_effect = quality_side_effect

            import asyncio
            response = asyncio.run(get_network_topology(service=mock_service))

                # Find unhealthy peer node
                unhealthy_node = next(n for n in response['nodes'] if n['id'] == 'peer-node-002')
                assert unhealthy_node['status'] == 'unhealthy'

                assert response['metadata']['healthy_peers'] == 1


class TestHelperFunctions:
    """Test helper functions for network management"""

    def test_calculate_peer_quality_healthy(self):
        """
        GIVEN peer with good metrics
        WHEN calculating quality
        THEN should return healthy status
        """
        from backend.api.v1.endpoints.network_management import _calculate_peer_quality

        # This will use mocked WireGuard monitoring or ping tests
        # For now, test basic structure
        with patch('backend.api.v1.endpoints.network_management._ping_peer') as mock_ping:
            mock_ping.return_value = (True, 23.5)

            quality = _calculate_peer_quality('peer-node-001', '10.0.0.2')

            assert quality['peer_id'] == 'peer-node-001'
            assert quality['assigned_ip'] == '10.0.0.2'
            assert 'connection_status' in quality

    def test_generate_wireguard_config_text(self):
        """
        GIVEN peer configuration
        WHEN generating WireGuard config text
        THEN should produce valid WireGuard format
        """
        from backend.api.v1.endpoints.network_management import _generate_wireguard_config_text

        peer_config = {
            'assigned_ip': '10.0.0.2',
            'hub_public_key': 'HubKeyXYZ==',
            'hub_endpoint': 'hub.example.com:51820',
            'allowed_ips': '10.0.0.0/24',
            'dns_servers': ['10.0.0.1']
        }

        config_text = _generate_wireguard_config_text(peer_config)

        assert '[Interface]' in config_text
        assert 'Address = 10.0.0.2/32' in config_text
        assert 'DNS = 10.0.0.1' in config_text
        assert '[Peer]' in config_text
        assert 'PublicKey = HubKeyXYZ==' in config_text
        assert 'Endpoint = hub.example.com:51820' in config_text
        assert 'AllowedIPs = 10.0.0.0/24' in config_text
        assert 'PersistentKeepalive = 25' in config_text
