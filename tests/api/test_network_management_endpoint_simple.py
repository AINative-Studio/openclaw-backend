"""
P2P Network Management UI Endpoint Tests (Simplified)

Basic tests for network management endpoints.
Story: Issue #85
"""

import pytest
from unittest.mock import Mock, patch
import base64


class TestNetworkManagementEndpoints:
    """Test network management endpoints"""

    def test_list_peers_success(self):
        """Test listing peers with mock data"""
        from backend.api.v1.endpoints.network_management import list_network_peers
        
        mock_service = Mock()
        mock_service.list_provisioned_peers.return_value = {
            'peer-001': {
                'node_id': 'peer-001',
                'assigned_ip': '10.0.0.2',
                'wireguard_public_key': 'PeerKey1==',
                'provisioned_at': '2026-02-27T10:00:00Z',
                'capabilities': {'gpu_count': 1, 'cpu_cores': 8},
                'version': '1.0.0'
            }
        }
        
        import asyncio
        response = asyncio.run(list_network_peers(service=mock_service))

        assert response.total_count == 1
        assert len(response.peers) == 1
        assert response.peers[0].node_id == 'peer-001'

    def test_get_peer_quality(self):
        """Test getting peer quality metrics"""
        from backend.api.v1.endpoints.network_management import get_peer_quality
        
        mock_service = Mock()
        mock_service.get_peer_config.return_value = {
            'node_id': 'peer-001',
            'assigned_ip': '10.0.0.2'
        }
        
        with patch('backend.api.v1.endpoints.network_management._calculate_peer_quality') as mock_calc:
            from datetime import datetime, timezone
            mock_calc.return_value = {
                'peer_id': 'peer-001',
                'assigned_ip': '10.0.0.2',
                'latency_ms': 23.5,
                'connection_status': 'healthy',
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

            import asyncio
            response = asyncio.run(get_peer_quality('peer-001', service=mock_service))

            assert response.peer_id == 'peer-001'
            assert response.latency_ms == 23.5
            assert response.connection_status == 'healthy'

    def test_generate_qr_code(self):
        """Test QR code generation"""
        from backend.api.v1.endpoints.network_management import generate_provision_qr
        
        mock_service = Mock()
        mock_service.get_peer_config.return_value = {
            'assigned_ip': '10.0.0.2',
            'hub_public_key': 'HubKey==',
            'hub_endpoint': 'hub.example.com:51820',
            'allowed_ips': '10.0.0.0/24',
            'dns_servers': ['10.0.0.1']
        }
        
        import asyncio
        response = asyncio.run(generate_provision_qr('peer-001', service=mock_service))

        assert response.qr_code is not None
        assert response.config_text is not None
        assert '[Interface]' in response.config_text
        assert '[Peer]' in response.config_text

    def test_get_ip_pool_status(self):
        """Test IP pool status endpoint"""
        from backend.api.v1.endpoints.network_management import get_ip_pool_status
        
        mock_service = Mock()
        mock_service.get_pool_stats.return_value = {
            'total_addresses': 253,
            'allocated_addresses': 2,
            'available_addresses': 250,
            'utilization_percent': 0,
            'reserved_addresses': 1
        }
        mock_service.ip_pool = Mock()
        mock_service.ip_pool.network = Mock()
        mock_service.ip_pool.network.with_prefixlen = '10.0.0.0/24'
        mock_service.ip_pool.allocated = {}
        mock_service.hub_ip = '10.0.0.1'
        
        import asyncio
        response = asyncio.run(get_ip_pool_status(service=mock_service))

        assert response.total_addresses == 253
        assert response.network_cidr == '10.0.0.0/24'
        assert response.hub_ip == '10.0.0.1'

    def test_get_network_topology(self):
        """Test network topology endpoint"""
        from backend.api.v1.endpoints.network_management import get_network_topology
        
        mock_service = Mock()
        mock_service.list_provisioned_peers.return_value = {
            'peer-001': {
                'node_id': 'peer-001',
                'assigned_ip': '10.0.0.2',
                'wireguard_public_key': 'PeerKey1==',
                'capabilities': {'gpu_count': 1}
            }
        }
        mock_service.hub_ip = '10.0.0.1'
        mock_service.hub_public_key = 'HubKey=='
        
        with patch('backend.api.v1.endpoints.network_management._calculate_peer_quality') as mock_calc:
            mock_calc.return_value = {
                'latency_ms': 23.5,
                'connection_status': 'healthy'
            }
            
            import asyncio
            response = asyncio.run(get_network_topology(service=mock_service))

            assert response.nodes is not None
            assert response.edges is not None
            assert len(response.nodes) == 2  # hub + 1 peer
            assert response.nodes[0].type == 'hub'

