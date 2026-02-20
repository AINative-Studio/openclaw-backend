"""
WireGuard Health API Endpoint Tests

Tests for WireGuard health check API endpoints.

Refs #E1-S6
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timezone


@pytest.fixture
def mock_health_summary():
    """Mock health summary response"""
    return {
        'status': 'healthy',
        'interface': 'wg0',
        'public_key': 'ServerPublicKeyABC123==',
        'listening_port': 51820,
        'peer_count': 3,
        'healthy_peers': 3,
        'stale_peers': 0,
        'stale_peer_list': [],
        'total_received_bytes': 1073741824,
        'total_sent_bytes': 536870912,
        'timestamp': '2026-02-19T17:30:00Z'
    }


@pytest.fixture
def mock_quality_metrics():
    """Mock quality metrics response"""
    return {
        'total_received_bytes': 1073741824,
        'total_sent_bytes': 536870912,
        'active_connections': 3,
        'timestamp': '2026-02-19T17:30:00Z'
    }


@pytest.fixture
def mock_peer_stats():
    """Mock peer statistics"""
    return {
        'peer_count': 3,
        'peers': [
            {
                'public_key': 'ClientPeer1ABC==',
                'endpoint': '192.168.1.100:51820',
                'allowed_ips': ['10.0.0.2/32'],
                'latest_handshake_seconds': 60,
                'received_bytes': 52428800,
                'sent_bytes': 126353408,
                'persistent_keepalive': 'every 25 seconds'
            },
            {
                'public_key': 'ClientPeer2DEF==',
                'endpoint': '192.168.1.101:51821',
                'allowed_ips': ['10.0.0.3/32'],
                'latest_handshake_seconds': 120,
                'received_bytes': 10485760,
                'sent_bytes': 5242880
            }
        ],
        'timestamp': '2026-02-19T17:30:00Z'
    }


class TestWireGuardHealthEndpoint:
    """Test WireGuard health check endpoint"""

    def test_get_health_basic(self, mock_health_summary):
        """
        GIVEN WireGuard monitoring service
        WHEN requesting health check
        THEN should return health summary
        """
        from backend.api.v1.endpoints.wireguard_health import get_wireguard_health

        # Mock the service
        with patch('backend.api.v1.endpoints.wireguard_health.get_wireguard_service') as mock_get_service:
            mock_service = Mock()
            mock_service.get_health_summary.return_value = mock_health_summary
            mock_service.stale_threshold_seconds = 300
            mock_get_service.return_value = mock_service

            # Act
            import asyncio
            response = asyncio.run(get_wireguard_health())

            # Assert
            assert response.status == 'healthy'
            assert response.interface == 'wg0'
            assert response.peer_count == 3
            assert response.healthy_peers == 3
            assert response.stale_peers == 0

    def test_get_health_with_peers(self, mock_health_summary, mock_peer_stats):
        """
        GIVEN request with include_peers=True
        WHEN requesting health check
        THEN should include peer details
        """
        from backend.api.v1.endpoints.wireguard_health import get_wireguard_health

        with patch('backend.api.v1.endpoints.wireguard_health.get_wireguard_service') as mock_get_service:
            mock_service = Mock()
            mock_service.get_health_summary.return_value = mock_health_summary
            mock_service.collect_peer_stats.return_value = mock_peer_stats
            mock_service.stale_threshold_seconds = 300
            mock_get_service.return_value = mock_service

            # Act
            import asyncio
            response = asyncio.run(get_wireguard_health(include_peers=True))

            # Assert
            assert response.peers is not None
            assert len(response.peers) == 2
            assert response.peers[0].public_key == 'ClientPeer1ABC=='
            assert response.peers[0].is_stale == False

    def test_get_health_custom_interface(self, mock_health_summary):
        """
        GIVEN custom interface parameter
        WHEN requesting health check
        THEN should use specified interface
        """
        from backend.api.v1.endpoints.wireguard_health import get_wireguard_health

        with patch('backend.api.v1.endpoints.wireguard_health.get_wireguard_service') as mock_get_service:
            mock_service = Mock()
            mock_service.get_health_summary.return_value = {
                **mock_health_summary,
                'interface': 'wg1'
            }
            mock_service.stale_threshold_seconds = 300
            mock_get_service.return_value = mock_service

            # Act
            import asyncio
            response = asyncio.run(get_wireguard_health(interface='wg1'))

            # Assert
            assert response.interface == 'wg1'
            mock_get_service.assert_called_once()
            call_kwargs = mock_get_service.call_args[1]
            assert call_kwargs['interface'] == 'wg1'


class TestNetworkQualityEndpoint:
    """Test network quality metrics endpoint"""

    def test_get_quality_metrics(self, mock_quality_metrics):
        """
        GIVEN WireGuard monitoring service
        WHEN requesting quality metrics
        THEN should return transfer statistics
        """
        from backend.api.v1.endpoints.wireguard_health import get_network_quality

        with patch('backend.api.v1.endpoints.wireguard_health.get_wireguard_service') as mock_get_service:
            mock_service = Mock()
            mock_service.calculate_network_quality.return_value = mock_quality_metrics
            mock_get_service.return_value = mock_service

            # Act
            import asyncio
            response = asyncio.run(get_network_quality())

            # Assert
            assert response.total_received_bytes == 1073741824
            assert response.total_sent_bytes == 536870912
            assert response.active_connections == 3


class TestErrorHandling:
    """Test error handling in endpoints"""

    def test_service_unavailable(self):
        """
        GIVEN WireGuard monitoring not available
        WHEN requesting health check
        THEN should return 503 error
        """
        from backend.api.v1.endpoints.wireguard_health import get_wireguard_health
        from fastapi import HTTPException

        with patch('backend.api.v1.endpoints.wireguard_health.WIREGUARD_MONITORING_AVAILABLE', False):
            # Act & Assert
            import asyncio
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_wireguard_health())

            assert exc_info.value.status_code == 503

    def test_service_error(self, mock_health_summary):
        """
        GIVEN service throws exception
        WHEN requesting health check
        THEN should return 500 error
        """
        from backend.api.v1.endpoints.wireguard_health import get_wireguard_health
        from fastapi import HTTPException

        with patch('backend.api.v1.endpoints.wireguard_health.get_wireguard_service') as mock_get_service:
            mock_service = Mock()
            mock_service.get_health_summary.side_effect = RuntimeError("wg command failed")
            mock_get_service.return_value = mock_service

            # Act & Assert
            import asyncio
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_wireguard_health())

            assert exc_info.value.status_code == 500
            assert "Failed to check WireGuard health" in str(exc_info.value.detail)
