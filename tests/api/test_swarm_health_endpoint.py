"""
Swarm Health Dashboard API Endpoint Tests

Tests for GET /swarm/health endpoint returning aggregated swarm health
as JSON for the dashboard UI.

Epic E8-S2: Swarm Health Dashboard Data API
Refs: #50
"""

import asyncio
import pytest
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.swarm_health import router


@pytest.fixture
def app():
    """Create FastAPI test app with swarm health router"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


def _make_healthy_snapshot():
    """Build a fully healthy snapshot dict"""
    return {
        "status": "healthy",
        "timestamp": "2026-02-20T12:00:00+00:00",
        "subsystems_available": 8,
        "subsystems_total": 8,
        "lease_expiration": {
            "available": True,
            "active_leases": 10,
            "upcoming_expirations": 2,
            "scan_interval": 10,
            "grace_period": 2,
        },
        "result_buffer": {
            "available": True,
            "current_size": 50,
            "max_capacity": 1000,
            "utilization_percent": 5.0,
            "oldest_result_age_seconds": 120.5,
            "newest_result_age_seconds": 1.2,
        },
        "partition_detection": {
            "available": True,
            "total_partitions": 0,
            "total_recoveries": 0,
            "total_partition_duration_seconds": 0.0,
            "current_state": "normal",
            "current_partition_duration_seconds": 0,
            "buffered_results_count": 0,
            "in_progress_tasks_count": 0,
        },
        "node_crash_detection": {
            "available": True,
            "total_crashes_detected": 1,
            "crash_detection_threshold_seconds": 60,
            "recent_crashes": 0,
            "max_history_size": 100,
        },
        "lease_revocation": {
            "available": True,
            "total_leases": 20,
            "revoked_leases": 2,
            "active_leases": 18,
            "revocation_rate": 10.0,
        },
        "duplicate_prevention": {
            "available": True,
            "total_tasks": 100,
            "unique_idempotency_keys": 100,
            "potential_duplicates_prevented": 0,
            "duplicate_prevention_active": True,
        },
        "ip_pool": {
            "available": True,
            "total_addresses": 254,
            "reserved_addresses": 10,
            "allocated_addresses": 20,
            "available_addresses": 224,
            "utilization_percent": 11,
        },
        "message_verification": {
            "available": True,
            "cache_size": 5,
            "cache_hits": 42,
        },
    }


def _make_degraded_snapshot():
    """Build a degraded snapshot dict"""
    snapshot = _make_healthy_snapshot()
    snapshot["status"] = "degraded"
    snapshot["subsystems_available"] = 6
    snapshot["node_crash_detection"] = {
        "available": False,
        "error": "Service unreachable",
    }
    snapshot["lease_revocation"] = {
        "available": False,
        "error": "DB connection timeout",
    }
    return snapshot


def _make_unhealthy_snapshot():
    """Build an unhealthy snapshot dict"""
    snapshot = _make_healthy_snapshot()
    snapshot["status"] = "unhealthy"
    snapshot["partition_detection"]["current_state"] = "degraded"
    return snapshot


class TestSwarmHealthEndpoint:
    """Test GET /swarm/health endpoint responses"""

    def test_returns_200_healthy(self, client):
        """
        GIVEN all subsystems healthy
        WHEN requesting GET /api/v1/swarm/health
        THEN should return HTTP 200 with healthy status
        """
        # Given
        snapshot = _make_healthy_snapshot()

        with patch(
            "backend.api.v1.endpoints.swarm_health.get_swarm_health_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.collect_health_snapshot = AsyncMock(return_value=snapshot)
            mock_get.return_value = mock_service

            # When
            response = client.get("/api/v1/swarm/health")

            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "healthy"
            assert data["subsystems_available"] == 8
            assert data["subsystems_total"] == 8

    def test_returns_200_degraded(self, client):
        """
        GIVEN some subsystems unavailable
        WHEN requesting GET /api/v1/swarm/health
        THEN should return HTTP 200 with degraded status
        """
        # Given
        snapshot = _make_degraded_snapshot()

        with patch(
            "backend.api.v1.endpoints.swarm_health.get_swarm_health_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.collect_health_snapshot = AsyncMock(return_value=snapshot)
            mock_get.return_value = mock_service

            # When
            response = client.get("/api/v1/swarm/health")

            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert data["subsystems_available"] == 6

    def test_returns_200_unhealthy(self, client):
        """
        GIVEN active DBOS partition
        WHEN requesting GET /api/v1/swarm/health
        THEN should return HTTP 200 with unhealthy status
        """
        # Given
        snapshot = _make_unhealthy_snapshot()

        with patch(
            "backend.api.v1.endpoints.swarm_health.get_swarm_health_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.collect_health_snapshot = AsyncMock(return_value=snapshot)
            mock_get.return_value = mock_service

            # When
            response = client.get("/api/v1/swarm/health")

            # Then
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "unhealthy"

    def test_response_json_structure(self, client):
        """
        GIVEN a healthy swarm
        WHEN requesting health endpoint
        THEN response should contain all expected top-level keys
        """
        # Given
        snapshot = _make_healthy_snapshot()

        with patch(
            "backend.api.v1.endpoints.swarm_health.get_swarm_health_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.collect_health_snapshot = AsyncMock(return_value=snapshot)
            mock_get.return_value = mock_service

            # When
            response = client.get("/api/v1/swarm/health")

            # Then
            data = response.json()
            expected_keys = {
                "status",
                "timestamp",
                "subsystems_available",
                "subsystems_total",
                "lease_expiration",
                "result_buffer",
                "partition_detection",
                "node_crash_detection",
                "lease_revocation",
                "duplicate_prevention",
                "ip_pool",
                "message_verification",
            }
            assert set(data.keys()) == expected_keys

    def test_response_correct_types(self, client):
        """
        GIVEN a healthy swarm
        WHEN requesting health endpoint
        THEN response values should have correct types
        """
        # Given
        snapshot = _make_healthy_snapshot()

        with patch(
            "backend.api.v1.endpoints.swarm_health.get_swarm_health_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.collect_health_snapshot = AsyncMock(return_value=snapshot)
            mock_get.return_value = mock_service

            # When
            response = client.get("/api/v1/swarm/health")

            # Then
            data = response.json()
            assert isinstance(data["status"], str)
            assert isinstance(data["timestamp"], str)
            assert isinstance(data["subsystems_available"], int)
            assert isinstance(data["subsystems_total"], int)
            assert isinstance(data["lease_expiration"], dict)
            assert isinstance(data["lease_expiration"]["available"], bool)

    def test_unavailable_subsystem_shows_error(self, client):
        """
        GIVEN a subsystem that failed to respond
        WHEN requesting health endpoint
        THEN the subsystem should show available=false with error
        """
        # Given
        snapshot = _make_degraded_snapshot()

        with patch(
            "backend.api.v1.endpoints.swarm_health.get_swarm_health_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.collect_health_snapshot = AsyncMock(return_value=snapshot)
            mock_get.return_value = mock_service

            # When
            response = client.get("/api/v1/swarm/health")

            # Then
            data = response.json()
            crash_data = data["node_crash_detection"]
            assert crash_data["available"] is False
            assert "error" in crash_data
            assert crash_data["error"] == "Service unreachable"


class TestSwarmHealthEndpointErrorHandling:
    """Test error handling in the health endpoint"""

    def test_returns_503_when_service_unavailable(self):
        """
        GIVEN SwarmHealthService import fails
        WHEN requesting health endpoint
        THEN should return HTTP 503
        """
        from backend.api.v1.endpoints.swarm_health import get_swarm_health

        with patch(
            "backend.api.v1.endpoints.swarm_health.SWARM_HEALTH_AVAILABLE", False
        ):
            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_swarm_health())

            assert exc_info.value.status_code == 503

    def test_returns_500_on_unexpected_error(self):
        """
        GIVEN SwarmHealthService raises unexpected exception
        WHEN requesting health endpoint
        THEN should return HTTP 500
        """
        from backend.api.v1.endpoints.swarm_health import get_swarm_health

        with patch(
            "backend.api.v1.endpoints.swarm_health.get_swarm_health_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.collect_health_snapshot = AsyncMock(
                side_effect=RuntimeError("Unexpected crash")
            )
            mock_get.return_value = mock_service

            # Act & Assert
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_swarm_health())

            assert exc_info.value.status_code == 500
            assert "Failed to collect swarm health" in str(exc_info.value.detail)


class TestSwarmHealthEndpointIntegration:
    """Integration test with TestClient"""

    def test_full_round_trip(self):
        """
        GIVEN a FastAPI app with swarm health router
        WHEN performing full HTTP round-trip
        THEN should return valid JSON response
        """
        # Given
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/v1")
        test_client = TestClient(test_app)
        snapshot = _make_healthy_snapshot()

        with patch(
            "backend.api.v1.endpoints.swarm_health.get_swarm_health_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.collect_health_snapshot = AsyncMock(return_value=snapshot)
            mock_get.return_value = mock_service

            # When
            response = test_client.get("/api/v1/swarm/health")

            # Then
            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"
            data = response.json()
            assert data["status"] == "healthy"
            assert "timestamp" in data
            assert data["lease_expiration"]["active_leases"] == 10
            assert data["result_buffer"]["utilization_percent"] == 5.0
