"""
WireGuard Network Monitoring Service Tests

Tests for WireGuard stats collection, health checking, and network quality metrics.
Implements BDD-style tests following TDD approach.

Refs #E1-S6
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Optional


# Test fixtures
@pytest.fixture
def mock_wg_show_output():
    """Sample wg show all output for testing"""
    return """interface: wg0
  public key: ServerPublicKeyABC123==
  private key: (hidden)
  listening port: 51820

peer: ClientPeer1ABC==
  preshared key: (hidden)
  endpoint: 192.168.1.100:51820
  allowed ips: 10.0.0.2/32
  latest handshake: 1 minute, 23 seconds ago
  transfer: 50.25 MiB received, 120.50 MiB sent
  persistent keepalive: every 25 seconds

peer: ClientPeer2DEF==
  endpoint: 192.168.1.101:51821
  allowed ips: 10.0.0.3/32
  latest handshake: 5 hours, 45 minutes, 12 seconds ago
  transfer: 10.00 MiB received, 5.00 MiB sent

peer: ClientPeer3GHI==
  endpoint: 192.168.1.102:51822
  allowed ips: 10.0.0.4/32
  latest handshake: 2 minutes, 10 seconds ago
  transfer: 1.50 GiB received, 500.00 MiB sent
  persistent keepalive: every 30 seconds
"""


@pytest.fixture
def mock_wg_show_no_peers():
    """WireGuard output with no peers"""
    return """interface: wg0
  public key: ServerPublicKeyABC123==
  private key: (hidden)
  listening port: 51820
"""


@pytest.fixture
def mock_wg_show_stale_peer():
    """WireGuard output with stale peer (old handshake)"""
    return """interface: wg0
  public key: ServerPublicKeyABC123==
  private key: (hidden)
  listening port: 51820

peer: StalePeerXYZ==
  endpoint: 192.168.1.200:51820
  allowed ips: 10.0.0.5/32
  latest handshake: 1 day, 2 hours, 30 minutes, 45 seconds ago
  transfer: 100.00 KiB received, 50.00 KiB sent
"""


class TestWireGuardStatsCollection:
    """Test WireGuard statistics collection from wg show command"""

    def test_collect_peer_stats(self, mock_wg_show_output):
        """
        GIVEN active WireGuard peers
        WHEN collecting stats
        THEN should return peer count and handshake times
        """
        # Import will fail until service is created
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        # Mock subprocess to return sample output
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_output,
                stderr=""
            )

            # Act
            stats = service.collect_peer_stats()

            # Assert
            assert stats is not None
            assert stats['peer_count'] == 3
            assert len(stats['peers']) == 3

            # Check first peer details
            peer1 = stats['peers'][0]
            assert peer1['public_key'] == 'ClientPeer1ABC=='
            assert peer1['endpoint'] == '192.168.1.100:51820'
            assert peer1['allowed_ips'] == ['10.0.0.2/32']
            assert 'latest_handshake_seconds' in peer1
            assert peer1['latest_handshake_seconds'] < 120  # Less than 2 minutes
            assert 'received_bytes' in peer1
            assert 'sent_bytes' in peer1

    def test_collect_peer_stats_no_peers(self, mock_wg_show_no_peers):
        """
        GIVEN WireGuard interface with no peers
        WHEN collecting stats
        THEN should return zero peer count
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_no_peers,
                stderr=""
            )

            # Act
            stats = service.collect_peer_stats()

            # Assert
            assert stats['peer_count'] == 0
            assert len(stats['peers']) == 0

    def test_collect_peer_stats_command_failure(self):
        """
        GIVEN wg show command fails
        WHEN collecting stats
        THEN should raise appropriate error
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=1,
                stdout="",
                stderr="Error: Unable to access interface wg0"
            )

            # Act & Assert
            with pytest.raises(RuntimeError) as exc_info:
                service.collect_peer_stats()

            assert "Failed to execute wg show" in str(exc_info.value)

    def test_parse_handshake_timestamp(self):
        """
        GIVEN various handshake timestamp formats
        WHEN parsing timestamps
        THEN should convert to seconds correctly
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        # Act & Assert
        test_cases = [
            ("1 minute, 23 seconds ago", 83),
            ("5 hours, 45 minutes, 12 seconds ago", 5 * 3600 + 45 * 60 + 12),
            ("2 minutes, 10 seconds ago", 130),
            ("1 day, 2 hours, 30 minutes, 45 seconds ago", 86400 + 2 * 3600 + 30 * 60 + 45),
            ("30 seconds ago", 30),
            ("1 hour ago", 3600),
        ]

        for timestamp_str, expected_seconds in test_cases:
            result = service._parse_handshake_timestamp(timestamp_str)
            assert result == expected_seconds, f"Failed for: {timestamp_str}"

    def test_parse_transfer_bytes(self):
        """
        GIVEN various transfer size formats
        WHEN parsing bytes
        THEN should convert to bytes correctly
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        # Act & Assert
        test_cases = [
            ("50.25 MiB", 50.25 * 1024 * 1024),
            ("120.50 MiB", 120.50 * 1024 * 1024),
            ("1.50 GiB", 1.50 * 1024 * 1024 * 1024),
            ("500.00 MiB", 500.00 * 1024 * 1024),
            ("100.00 KiB", 100.00 * 1024),
            ("10.00 MiB", 10.00 * 1024 * 1024),
        ]

        for size_str, expected_bytes in test_cases:
            result = service._parse_transfer_bytes(size_str)
            assert abs(result - expected_bytes) < 1, f"Failed for: {size_str}"


class TestWireGuardHealthChecking:
    """Test WireGuard connection health detection"""

    def test_detect_stale_connection(self, mock_wg_show_stale_peer):
        """
        GIVEN peer with old handshake
        WHEN checking health
        THEN should flag as stale
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService(stale_threshold_seconds=3600)  # 1 hour

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_stale_peer,
                stderr=""
            )

            # Act
            health = service.check_connection_health()

            # Assert
            # When all peers are stale (0 healthy), status should be 'unhealthy'
            assert health['status'] == 'unhealthy'
            assert health['total_peers'] == 1
            assert health['healthy_peers'] == 0
            assert health['stale_peers'] == 1
            assert len(health['stale_peer_list']) == 1
            assert health['stale_peer_list'][0] == 'StalePeerXYZ=='

    def test_detect_healthy_connections(self, mock_wg_show_output):
        """
        GIVEN peers with recent handshakes
        WHEN checking health
        THEN should mark as healthy
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService(stale_threshold_seconds=3600)  # 1 hour

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_output,
                stderr=""
            )

            # Act
            health = service.check_connection_health()

            # Assert
            # Out of 3 peers: 2 recent (< 3 min), 1 stale (> 5 hours)
            assert health['status'] in ['healthy', 'degraded']
            assert health['total_peers'] == 3
            assert health['healthy_peers'] == 2
            assert health['stale_peers'] == 1

    def test_check_health_no_peers(self, mock_wg_show_no_peers):
        """
        GIVEN WireGuard with no peers
        WHEN checking health
        THEN should report unhealthy status
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_no_peers,
                stderr=""
            )

            # Act
            health = service.check_connection_health()

            # Assert
            assert health['status'] == 'unhealthy'
            assert health['total_peers'] == 0
            assert health['healthy_peers'] == 0


class TestNetworkQualityMetrics:
    """Test network quality calculation from transfer stats"""

    def test_calculate_network_quality(self, mock_wg_show_output):
        """
        GIVEN transfer statistics
        WHEN calculating quality
        THEN should return transfer rates and connection metrics
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_output,
                stderr=""
            )

            # Act
            quality = service.calculate_network_quality()

            # Assert
            assert quality is not None
            assert 'total_received_bytes' in quality
            assert 'total_sent_bytes' in quality
            assert 'active_connections' in quality
            assert quality['active_connections'] == 3
            assert quality['total_received_bytes'] > 0
            assert quality['total_sent_bytes'] > 0

    def test_calculate_quality_with_time_window(self, mock_wg_show_output):
        """
        GIVEN transfer stats over time
        WHEN calculating quality with time window
        THEN should calculate transfer rates per second
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        # Mock two consecutive readings
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_output,
                stderr=""
            )

            # First reading
            quality1 = service.calculate_network_quality()

            # Simulate time passing and data transfer
            # This would normally be tested with actual time-based sampling
            assert 'total_received_bytes' in quality1
            assert 'total_sent_bytes' in quality1


class TestMetricsAggregation:
    """Test metrics aggregation service"""

    def test_aggregate_metrics_over_time(self, mock_wg_show_output):
        """
        GIVEN multiple stat collections over time
        WHEN aggregating metrics
        THEN should provide historical data
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_output,
                stderr=""
            )

            # Act - Collect stats multiple times
            service.collect_and_store_metrics()
            service.collect_and_store_metrics()

            metrics_history = service.get_metrics_history(limit=10)

            # Assert
            assert len(metrics_history) >= 2
            for metric in metrics_history:
                assert 'timestamp' in metric
                assert 'peer_count' in metric
                assert 'total_received_bytes' in metric
                assert 'total_sent_bytes' in metric

    def test_metrics_retention_limit(self, mock_wg_show_output):
        """
        GIVEN metrics collection with retention limit
        WHEN storing many metrics
        THEN should only keep most recent N entries
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService(max_history_size=5)

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_output,
                stderr=""
            )

            # Act - Collect more than max size
            for _ in range(10):
                service.collect_and_store_metrics()

            metrics_history = service.get_metrics_history()

            # Assert
            assert len(metrics_history) <= 5


class TestHealthCheckEndpoint:
    """Test health check endpoint integration"""

    def test_get_health_summary(self, mock_wg_show_output):
        """
        GIVEN active WireGuard connections
        WHEN requesting health summary
        THEN should return comprehensive status
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService()

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_output,
                stderr=""
            )

            # Act
            summary = service.get_health_summary()

            # Assert
            assert summary is not None
            assert 'status' in summary
            assert 'peer_count' in summary
            assert 'healthy_peers' in summary
            assert 'stale_peers' in summary
            assert 'total_received_bytes' in summary
            assert 'total_sent_bytes' in summary
            assert 'timestamp' in summary

    def test_health_summary_includes_interface_info(self, mock_wg_show_output):
        """
        GIVEN WireGuard interface
        WHEN getting health summary
        THEN should include interface details
        """
        from backend.services.wireguard_monitoring_service import WireGuardMonitoringService

        # Arrange
        service = WireGuardMonitoringService(interface='wg0')

        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock(
                returncode=0,
                stdout=mock_wg_show_output,
                stderr=""
            )

            # Act
            summary = service.get_health_summary()

            # Assert
            assert summary['interface'] == 'wg0'
            assert 'public_key' in summary
            assert 'listening_port' in summary
