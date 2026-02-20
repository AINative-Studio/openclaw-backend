"""
Tests for GET /swarm/monitoring/status endpoint (E8-S5).

Verifies the monitoring infrastructure status endpoint returns correct
operational state, handles service unavailability, and follows the
error-handling patterns from swarm_alerts.py.
"""

import asyncio

import pytest
from unittest.mock import Mock, patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.swarm_monitoring import router


@pytest.fixture(autouse=True)
def reset_monitoring_singleton():
    import backend.services.monitoring_integration_service as mod
    mod._monitoring_integration_instance = None
    yield
    mod._monitoring_integration_instance = None


@pytest.fixture
def app():
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    return TestClient(app)


class TestMonitoringStatusEndpoint:
    """Tests for GET /swarm/monitoring/status happy path."""

    def test_returns_200_with_operational_status(self, client):
        """
        GIVEN monitoring services are available
        WHEN GET /swarm/monitoring/status is called
        THEN should return 200 with operational status
        """
        response = client.get("/api/v1/swarm/monitoring/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] in ("operational", "partial", "unavailable")

    def test_response_json_structure(self, client):
        """
        GIVEN monitoring services are available
        WHEN GET /swarm/monitoring/status is called
        THEN response should contain all required fields
        """
        response = client.get("/api/v1/swarm/monitoring/status")
        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "subsystems" in data
        assert "metrics" in data["subsystems"]
        assert "timeline" in data["subsystems"]
        assert "health" in data["subsystems"]
        assert "registered_health_subsystems" in data
        assert "timeline_event_count" in data
        assert "bootstrapped" in data

    def test_response_correct_types(self, client):
        """
        GIVEN monitoring services are available
        WHEN GET /swarm/monitoring/status is called
        THEN response fields should have correct types
        """
        response = client.get("/api/v1/swarm/monitoring/status")
        data = response.json()
        assert isinstance(data["status"], str)
        assert isinstance(data["timestamp"], str)
        assert isinstance(data["subsystems"], dict)
        assert isinstance(data["subsystems"]["metrics"]["available"], bool)
        assert isinstance(data["subsystems"]["timeline"]["available"], bool)
        assert isinstance(data["subsystems"]["health"]["available"], bool)
        assert isinstance(data["registered_health_subsystems"], int)
        assert isinstance(data["timeline_event_count"], int)
        assert isinstance(data["bootstrapped"], bool)

    def test_returns_partial_when_some_subsystems_missing(self, client):
        """
        GIVEN some monitoring services are unavailable
        WHEN GET /swarm/monitoring/status is called
        THEN status should reflect partial availability
        """
        with patch(
            "backend.api.v1.endpoints.swarm_monitoring.get_monitoring_integration_service"
        ) as mock_get:
            mock_svc = Mock()
            mock_svc.get_status.return_value = {
                "status": "partial",
                "timestamp": "2026-02-20T00:00:00+00:00",
                "subsystems": {
                    "metrics": {"available": False},
                    "timeline": {"available": True},
                    "health": {"available": True},
                },
                "registered_health_subsystems": 0,
                "timeline_event_count": 5,
                "bootstrapped": False,
            }
            mock_get.return_value = mock_svc
            response = client.get("/api/v1/swarm/monitoring/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        assert data["subsystems"]["metrics"]["available"] is False


class TestMonitoringStatusErrorHandling:
    """Tests for error handling in the monitoring status endpoint."""

    def test_503_when_service_unavailable(self):
        """
        GIVEN MONITORING_AVAILABLE is False
        WHEN GET /swarm/monitoring/status is called
        THEN should raise 503
        """
        from backend.api.v1.endpoints.swarm_monitoring import (
            get_monitoring_status,
        )
        with patch(
            "backend.api.v1.endpoints.swarm_monitoring.MONITORING_AVAILABLE",
            False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_monitoring_status())
            assert exc_info.value.status_code == 503

    def test_500_on_unexpected_error(self):
        """
        GIVEN get_monitoring_integration_service raises an unexpected error
        WHEN GET /swarm/monitoring/status is called
        THEN should raise 500
        """
        from backend.api.v1.endpoints.swarm_monitoring import (
            get_monitoring_status,
        )
        with patch(
            "backend.api.v1.endpoints.swarm_monitoring.get_monitoring_integration_service"
        ) as mock_get:
            mock_get.side_effect = RuntimeError("Unexpected crash")
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_monitoring_status())
            assert exc_info.value.status_code == 500

    def test_503_detail_message(self):
        """
        GIVEN MONITORING_AVAILABLE is False
        WHEN GET /swarm/monitoring/status is called
        THEN should include descriptive detail message
        """
        from backend.api.v1.endpoints.swarm_monitoring import (
            get_monitoring_status,
        )
        with patch(
            "backend.api.v1.endpoints.swarm_monitoring.MONITORING_AVAILABLE",
            False,
        ):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_monitoring_status())
            assert "not available" in exc_info.value.detail.lower()


class TestMonitoringStatusIntegration:
    """Integration tests for the monitoring status endpoint."""

    def test_full_http_round_trip(self):
        """
        GIVEN a fresh FastAPI app with monitoring router
        WHEN GET /swarm/monitoring/status is called via HTTP
        THEN should return a valid response
        """
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/v1")
        test_client = TestClient(test_app)
        response = test_client.get("/api/v1/swarm/monitoring/status")
        assert response.status_code == 200
        assert "status" in response.json()

    def test_response_content_type_is_json(self):
        """
        GIVEN monitoring endpoint is called
        WHEN response is returned
        THEN content-type should be application/json
        """
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/v1")
        test_client = TestClient(test_app)
        response = test_client.get("/api/v1/swarm/monitoring/status")
        assert "application/json" in response.headers["content-type"]
