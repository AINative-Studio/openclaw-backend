"""
Unit Tests for Swarm Health Service

Tests service registration, health snapshot collection, health status
derivation, and singleton factory behavior.

Epic E8-S2: Swarm Health Dashboard Data API
Refs: #50
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch

from backend.services.swarm_health_service import (
    SwarmHealthService,
    get_swarm_health_service,
)


class TestSwarmHealthServiceRegistration:
    """Test service registration and unregistration"""

    @pytest.fixture
    def swarm_health_service(self):
        """Create fresh SwarmHealthService instance"""
        return SwarmHealthService()

    def test_register_service(self, swarm_health_service):
        """
        GIVEN a SwarmHealthService instance
        WHEN registering a service by name
        THEN the service should be stored in the registry
        """
        # Given
        mock_service = Mock()

        # When
        swarm_health_service.register_service("lease_expiration", mock_service)

        # Then
        assert "lease_expiration" in swarm_health_service._registered_services
        assert swarm_health_service._registered_services["lease_expiration"] is mock_service

    def test_unregister_service(self, swarm_health_service):
        """
        GIVEN a SwarmHealthService with a registered service
        WHEN unregistering that service
        THEN the service should be removed from the registry
        """
        # Given
        mock_service = Mock()
        swarm_health_service.register_service("lease_expiration", mock_service)

        # When
        swarm_health_service.unregister_service("lease_expiration")

        # Then
        assert "lease_expiration" not in swarm_health_service._registered_services

    def test_register_replaces_existing(self, swarm_health_service):
        """
        GIVEN a SwarmHealthService with a registered service
        WHEN registering a new service with the same name
        THEN the old service should be replaced
        """
        # Given
        old_service = Mock()
        new_service = Mock()
        swarm_health_service.register_service("lease_expiration", old_service)

        # When
        swarm_health_service.register_service("lease_expiration", new_service)

        # Then
        assert swarm_health_service._registered_services["lease_expiration"] is new_service


class TestHealthSnapshotCollection:
    """Test health snapshot collection from registered subsystems"""

    @pytest.fixture
    def swarm_health_service(self):
        """Create fresh SwarmHealthService instance"""
        return SwarmHealthService()

    def test_all_subsystems_available(self, swarm_health_service):
        """
        GIVEN all 8 subsystems registered and responding
        WHEN collecting a health snapshot
        THEN all subsystems should be available with correct stats
        """
        # Given
        mock_lease = Mock()
        mock_lease.get_expiration_stats.return_value = {
            "active_leases": 10,
            "upcoming_expirations": 2,
            "scan_interval": 10,
            "grace_period": 2,
        }
        mock_buffer = Mock()
        mock_buffer.get_buffer_metrics = AsyncMock(return_value={
            "current_size": 50,
            "max_capacity": 1000,
            "utilization_percent": 5.0,
            "oldest_result_age_seconds": 120.5,
            "newest_result_age_seconds": 1.2,
        })
        mock_partition = Mock()
        mock_partition.get_partition_statistics.return_value = {
            "total_partitions": 0,
            "total_recoveries": 0,
            "total_partition_duration_seconds": 0.0,
            "current_state": "normal",
            "current_partition_duration_seconds": 0,
            "buffered_results_count": 0,
            "in_progress_tasks_count": 0,
        }
        mock_crash = Mock()
        mock_crash.get_crash_statistics.return_value = {
            "total_crashes_detected": 1,
            "crash_detection_threshold_seconds": 60,
            "recent_crashes": 0,
            "max_history_size": 100,
        }
        mock_revocation = Mock()
        mock_revocation.get_revocation_stats = AsyncMock(return_value={
            "total_leases": 20,
            "revoked_leases": 2,
            "active_leases": 18,
            "revocation_rate": 10.0,
        })
        mock_duplicate = Mock()
        mock_duplicate.get_duplicate_statistics.return_value = {
            "total_tasks": 100,
            "unique_idempotency_keys": 100,
            "potential_duplicates_prevented": 0,
            "duplicate_prevention_active": True,
        }
        mock_ip_pool = Mock()
        mock_ip_pool.get_pool_stats.return_value = {
            "total_addresses": 254,
            "reserved_addresses": 10,
            "allocated_addresses": 20,
            "available_addresses": 224,
            "utilization_percent": 11,
        }
        mock_verification = Mock()
        mock_verification.get_cache_stats.return_value = {
            "cache_size": 5,
            "cache_hits": 42,
        }

        swarm_health_service.register_service("lease_expiration", mock_lease)
        swarm_health_service.register_service("result_buffer", mock_buffer)
        swarm_health_service.register_service("partition_detection", mock_partition)
        swarm_health_service.register_service("node_crash_detection", mock_crash)
        swarm_health_service.register_service("lease_revocation", mock_revocation)
        swarm_health_service.register_service("duplicate_prevention", mock_duplicate)
        swarm_health_service.register_service("ip_pool", mock_ip_pool)
        swarm_health_service.register_service("message_verification", mock_verification)

        # When
        snapshot = asyncio.run(swarm_health_service.collect_health_snapshot())

        # Then
        assert snapshot["status"] == "healthy"
        assert snapshot["subsystems_available"] == 8
        assert snapshot["subsystems_total"] == 8
        assert snapshot["lease_expiration"]["available"] is True
        assert snapshot["lease_expiration"]["active_leases"] == 10
        assert snapshot["result_buffer"]["available"] is True
        assert snapshot["result_buffer"]["utilization_percent"] == 5.0
        assert snapshot["partition_detection"]["available"] is True
        assert snapshot["partition_detection"]["current_state"] == "normal"
        assert snapshot["node_crash_detection"]["available"] is True
        assert snapshot["lease_revocation"]["available"] is True
        assert snapshot["duplicate_prevention"]["available"] is True
        assert snapshot["ip_pool"]["available"] is True
        assert snapshot["message_verification"]["available"] is True

    def test_no_subsystems_registered(self, swarm_health_service):
        """
        GIVEN no subsystems registered
        WHEN collecting a health snapshot
        THEN status should be unhealthy with 0 available
        """
        # When
        snapshot = asyncio.run(swarm_health_service.collect_health_snapshot())

        # Then
        assert snapshot["status"] == "unhealthy"
        assert snapshot["subsystems_available"] == 0
        assert snapshot["subsystems_total"] == 0

    def test_partial_subsystems_available(self, swarm_health_service):
        """
        GIVEN 3 of 8 subsystems registered, one failing
        WHEN collecting a health snapshot
        THEN status should be degraded with correct counts
        """
        # Given
        mock_lease = Mock()
        mock_lease.get_expiration_stats.return_value = {
            "active_leases": 5,
            "upcoming_expirations": 1,
            "scan_interval": 10,
            "grace_period": 2,
        }
        mock_partition = Mock()
        mock_partition.get_partition_statistics.return_value = {
            "current_state": "normal",
            "total_partitions": 0,
            "total_recoveries": 0,
            "total_partition_duration_seconds": 0.0,
            "current_partition_duration_seconds": 0,
            "buffered_results_count": 0,
            "in_progress_tasks_count": 0,
        }
        mock_crash = Mock()
        mock_crash.get_crash_statistics.side_effect = RuntimeError("Service down")

        swarm_health_service.register_service("lease_expiration", mock_lease)
        swarm_health_service.register_service("partition_detection", mock_partition)
        swarm_health_service.register_service("node_crash_detection", mock_crash)

        # When
        snapshot = asyncio.run(swarm_health_service.collect_health_snapshot())

        # Then
        assert snapshot["status"] == "degraded"
        assert snapshot["subsystems_available"] == 2
        assert snapshot["subsystems_total"] == 3
        assert snapshot["lease_expiration"]["available"] is True
        assert snapshot["partition_detection"]["available"] is True
        assert snapshot["node_crash_detection"]["available"] is False
        assert "Service down" in snapshot["node_crash_detection"]["error"]

    def test_service_error_returns_error_message(self, swarm_health_service):
        """
        GIVEN a subsystem that raises an exception
        WHEN collecting a health snapshot
        THEN the subsystem should show available=False with error message
        """
        # Given
        mock_lease = Mock()
        mock_lease.get_expiration_stats.side_effect = ConnectionError("DB unreachable")
        swarm_health_service.register_service("lease_expiration", mock_lease)

        # When
        snapshot = asyncio.run(swarm_health_service.collect_health_snapshot())

        # Then
        assert snapshot["lease_expiration"]["available"] is False
        assert "DB unreachable" in snapshot["lease_expiration"]["error"]

    def test_async_services_awaited(self, swarm_health_service):
        """
        GIVEN async subsystems (result_buffer, lease_revocation) registered
        WHEN collecting a health snapshot
        THEN their async methods should be awaited correctly
        """
        # Given
        mock_buffer = Mock()
        mock_buffer.get_buffer_metrics = AsyncMock(return_value={
            "current_size": 100,
            "max_capacity": 500,
            "utilization_percent": 20.0,
            "oldest_result_age_seconds": None,
            "newest_result_age_seconds": None,
        })
        mock_revocation = Mock()
        mock_revocation.get_revocation_stats = AsyncMock(return_value={
            "total_leases": 10,
            "revoked_leases": 1,
            "active_leases": 9,
            "revocation_rate": 10.0,
        })

        swarm_health_service.register_service("result_buffer", mock_buffer)
        swarm_health_service.register_service("lease_revocation", mock_revocation)

        # When
        snapshot = asyncio.run(swarm_health_service.collect_health_snapshot())

        # Then
        assert snapshot["result_buffer"]["available"] is True
        assert snapshot["result_buffer"]["current_size"] == 100
        assert snapshot["lease_revocation"]["available"] is True
        assert snapshot["lease_revocation"]["revocation_rate"] == 10.0
        mock_buffer.get_buffer_metrics.assert_awaited_once()
        mock_revocation.get_revocation_stats.assert_awaited_once()


class TestHealthStatusDerivation:
    """Test health status derivation algorithm"""

    @pytest.fixture
    def swarm_health_service(self):
        """Create fresh SwarmHealthService instance"""
        return SwarmHealthService()

    def test_healthy_all_normal(self, swarm_health_service):
        """
        GIVEN all subsystems available with normal stats
        WHEN deriving health status
        THEN status should be healthy
        """
        # Given
        results = {
            "partition_detection": {"available": True, "current_state": "normal"},
            "result_buffer": {"available": True, "utilization_percent": 50.0},
            "node_crash_detection": {"available": True, "recent_crashes": 1},
            "lease_revocation": {"available": True, "revocation_rate": 10.0},
            "ip_pool": {"available": True, "utilization_percent": 50},
        }

        # When
        status = swarm_health_service._derive_health_status(results, 5)

        # Then
        assert status == "healthy"

    def test_unhealthy_partition_degraded(self, swarm_health_service):
        """
        GIVEN partition_detection in degraded state
        WHEN deriving health status
        THEN status should be unhealthy
        """
        # Given
        results = {
            "partition_detection": {"available": True, "current_state": "degraded"},
        }

        # When
        status = swarm_health_service._derive_health_status(results, 5)

        # Then
        assert status == "unhealthy"

    def test_unhealthy_no_subsystems(self, swarm_health_service):
        """
        GIVEN zero available subsystems
        WHEN deriving health status
        THEN status should be unhealthy
        """
        # Given
        results = {}

        # When
        status = swarm_health_service._derive_health_status(results, 0)

        # Then
        assert status == "unhealthy"

    def test_degraded_missing_subsystems(self, swarm_health_service):
        """
        GIVEN fewer available subsystems than total registered
        WHEN deriving health status
        THEN status should be degraded
        """
        # Given - 3 registered, but only 1 available
        results = {
            "partition_detection": {"available": True, "current_state": "normal"},
            "lease_expiration": {"available": False, "error": "DB down"},
            "node_crash_detection": {"available": False, "error": "Timeout"},
        }

        # When - 1 available out of 3 total
        status = swarm_health_service._derive_health_status(results, 1)

        # Then
        assert status == "degraded"

    def test_degraded_high_buffer_utilization(self, swarm_health_service):
        """
        GIVEN result_buffer utilization above 80%
        WHEN deriving health status
        THEN status should be degraded
        """
        # Given
        results = {
            "partition_detection": {"available": True, "current_state": "normal"},
            "result_buffer": {"available": True, "utilization_percent": 85.0},
        }

        # When - all registered are available
        status = swarm_health_service._derive_health_status(results, 2)

        # Then
        assert status == "degraded"

    def test_degraded_high_crash_count(self, swarm_health_service):
        """
        GIVEN 3 or more recent crashes
        WHEN deriving health status
        THEN status should be degraded
        """
        # Given
        results = {
            "partition_detection": {"available": True, "current_state": "normal"},
            "node_crash_detection": {"available": True, "recent_crashes": 3},
        }

        # When
        status = swarm_health_service._derive_health_status(results, 2)

        # Then
        assert status == "degraded"

    def test_degraded_high_revocation_rate(self, swarm_health_service):
        """
        GIVEN revocation_rate above 50%
        WHEN deriving health status
        THEN status should be degraded
        """
        # Given
        results = {
            "partition_detection": {"available": True, "current_state": "normal"},
            "lease_revocation": {"available": True, "revocation_rate": 55.0},
        }

        # When
        status = swarm_health_service._derive_health_status(results, 2)

        # Then
        assert status == "degraded"

    def test_degraded_high_ip_pool_utilization(self, swarm_health_service):
        """
        GIVEN IP pool utilization above 90%
        WHEN deriving health status
        THEN status should be degraded
        """
        # Given
        results = {
            "partition_detection": {"available": True, "current_state": "normal"},
            "ip_pool": {"available": True, "utilization_percent": 95},
        }

        # When
        status = swarm_health_service._derive_health_status(results, 2)

        # Then
        assert status == "degraded"

    def test_healthy_at_just_below_thresholds(self, swarm_health_service):
        """
        GIVEN all metrics just below degraded thresholds
        WHEN deriving health status
        THEN status should be healthy
        """
        # Given
        results = {
            "partition_detection": {"available": True, "current_state": "normal"},
            "result_buffer": {"available": True, "utilization_percent": 80.0},
            "node_crash_detection": {"available": True, "recent_crashes": 2},
            "lease_revocation": {"available": True, "revocation_rate": 50.0},
            "ip_pool": {"available": True, "utilization_percent": 90},
        }

        # When - all available == total
        status = swarm_health_service._derive_health_status(results, 5)

        # Then
        assert status == "healthy"


class TestSingletonFactory:
    """Test get_swarm_health_service() singleton behavior"""

    def test_returns_same_instance(self):
        """
        GIVEN get_swarm_health_service called multiple times
        WHEN comparing returned instances
        THEN should return the same instance
        """
        # Reset singleton for test isolation
        import backend.services.swarm_health_service as mod
        mod._swarm_health_service_instance = None

        # When
        service1 = get_swarm_health_service()
        service2 = get_swarm_health_service()

        # Then
        assert service1 is service2

        # Cleanup
        mod._swarm_health_service_instance = None

    def test_returns_correct_type(self):
        """
        GIVEN get_swarm_health_service called
        WHEN checking return type
        THEN should return SwarmHealthService instance
        """
        # Reset singleton
        import backend.services.swarm_health_service as mod
        mod._swarm_health_service_instance = None

        # When
        service = get_swarm_health_service()

        # Then
        assert isinstance(service, SwarmHealthService)

        # Cleanup
        mod._swarm_health_service_instance = None
