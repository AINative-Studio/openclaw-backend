"""
Swarm Alerts API Endpoint Tests

Tests for GET/PUT /swarm/alerts/thresholds endpoints for
runtime alert threshold configuration.

Epic E8-S4: Alert Threshold Configuration
Refs: #52
"""

import asyncio
import pytest
from unittest.mock import Mock, patch, PropertyMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.swarm_alerts import router


@pytest.fixture(autouse=True)
def reset_threshold_singleton():
    """Reset alert threshold singleton for test isolation"""
    import backend.services.alert_threshold_service as mod
    mod._alert_threshold_service_instance = None
    yield
    mod._alert_threshold_service_instance = None


@pytest.fixture
def app():
    """Create FastAPI test app with swarm alerts router"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


class TestGetAlertThresholds:
    """Test GET /swarm/alerts/thresholds endpoint"""

    def test_returns_200_with_defaults(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN requesting GET /api/v1/swarm/alerts/thresholds
        THEN should return HTTP 200 with default threshold values
        """
        response = client.get("/api/v1/swarm/alerts/thresholds")

        assert response.status_code == 200
        data = response.json()
        assert data["buffer_utilization"] == 80.0
        assert data["crash_count"] == 3
        assert data["revocation_rate"] == 50.0
        assert data["ip_pool_utilization"] == 90.0

    def test_response_json_structure(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN requesting GET /api/v1/swarm/alerts/thresholds
        THEN response should contain all expected keys
        """
        response = client.get("/api/v1/swarm/alerts/thresholds")

        data = response.json()
        assert "buffer_utilization" in data
        assert "crash_count" in data
        assert "revocation_rate" in data
        assert "ip_pool_utilization" in data
        assert "updated_at" in data

    def test_response_correct_types(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN requesting GET /api/v1/swarm/alerts/thresholds
        THEN all fields should have correct types
        """
        response = client.get("/api/v1/swarm/alerts/thresholds")

        data = response.json()
        assert isinstance(data["buffer_utilization"], float)
        assert isinstance(data["crash_count"], int)
        assert isinstance(data["revocation_rate"], float)
        assert isinstance(data["ip_pool_utilization"], float)
        assert isinstance(data["updated_at"], str)


class TestUpdateAlertThresholds:
    """Test PUT /swarm/alerts/thresholds endpoint"""

    def test_update_single_field_returns_200(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN updating a single threshold field via PUT
        THEN should return HTTP 200 with updated value
        """
        response = client.put(
            "/api/v1/swarm/alerts/thresholds",
            json={"buffer_utilization": 95.0},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["buffer_utilization"] == 95.0

    def test_partial_update_preserves_other_fields(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN updating only one field
        THEN other fields should retain their values
        """
        response = client.put(
            "/api/v1/swarm/alerts/thresholds",
            json={"buffer_utilization": 95.0},
        )

        data = response.json()
        assert data["crash_count"] == 3
        assert data["revocation_rate"] == 50.0
        assert data["ip_pool_utilization"] == 90.0

    def test_update_all_fields(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN updating all threshold fields
        THEN all fields should change
        """
        response = client.put(
            "/api/v1/swarm/alerts/thresholds",
            json={
                "buffer_utilization": 60.0,
                "crash_count": 10,
                "revocation_rate": 30.0,
                "ip_pool_utilization": 85.0,
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["buffer_utilization"] == 60.0
        assert data["crash_count"] == 10
        assert data["revocation_rate"] == 30.0
        assert data["ip_pool_utilization"] == 85.0

    def test_update_refreshes_timestamp(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN updating thresholds via PUT
        THEN updated_at should change
        """
        get_response = client.get("/api/v1/swarm/alerts/thresholds")
        original_timestamp = get_response.json()["updated_at"]

        put_response = client.put(
            "/api/v1/swarm/alerts/thresholds",
            json={"buffer_utilization": 75.0},
        )

        new_timestamp = put_response.json()["updated_at"]
        assert new_timestamp >= original_timestamp

    def test_empty_body_returns_current(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN sending PUT with empty JSON body
        THEN should return 200 with current config unchanged
        """
        response = client.put(
            "/api/v1/swarm/alerts/thresholds",
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["buffer_utilization"] == 80.0
        assert data["crash_count"] == 3

    def test_rejects_out_of_range_value_422(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN sending PUT with out-of-range value
        THEN should return HTTP 422
        """
        response = client.put(
            "/api/v1/swarm/alerts/thresholds",
            json={"buffer_utilization": 150.0},
        )

        assert response.status_code == 422

    def test_rejects_negative_crash_count_422(self, client):
        """
        GIVEN a fresh alert threshold service
        WHEN sending PUT with negative crash_count
        THEN should return HTTP 422
        """
        response = client.put(
            "/api/v1/swarm/alerts/thresholds",
            json={"crash_count": -1},
        )

        assert response.status_code == 422


class TestErrorHandling:
    """Test error handling in alert threshold endpoints"""

    def test_get_503_when_service_unavailable(self):
        """
        GIVEN AlertThresholdService import fails
        WHEN requesting GET /swarm/alerts/thresholds
        THEN should return HTTP 503
        """
        from backend.api.v1.endpoints.swarm_alerts import get_alert_thresholds

        with patch(
            "backend.api.v1.endpoints.swarm_alerts.ALERTS_AVAILABLE", False
        ):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_alert_thresholds())

            assert exc_info.value.status_code == 503

    def test_put_503_when_service_unavailable(self):
        """
        GIVEN AlertThresholdService import fails
        WHEN requesting PUT /swarm/alerts/thresholds
        THEN should return HTTP 503
        """
        from backend.api.v1.endpoints.swarm_alerts import (
            update_alert_thresholds,
            ThresholdUpdateRequest,
        )

        with patch(
            "backend.api.v1.endpoints.swarm_alerts.ALERTS_AVAILABLE", False
        ):
            request = ThresholdUpdateRequest()
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(update_alert_thresholds(request))

            assert exc_info.value.status_code == 503

    def test_get_500_on_unexpected_error(self):
        """
        GIVEN AlertThresholdService raises unexpected exception
        WHEN requesting GET /swarm/alerts/thresholds
        THEN should return HTTP 500
        """
        from backend.api.v1.endpoints.swarm_alerts import get_alert_thresholds

        with patch(
            "backend.api.v1.endpoints.swarm_alerts.get_alert_threshold_service"
        ) as mock_get:
            mock_get.side_effect = RuntimeError("Unexpected crash")

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_alert_thresholds())

            assert exc_info.value.status_code == 500

    def test_put_500_on_unexpected_error(self):
        """
        GIVEN AlertThresholdService raises unexpected exception
        WHEN requesting PUT /swarm/alerts/thresholds
        THEN should return HTTP 500
        """
        from backend.api.v1.endpoints.swarm_alerts import (
            update_alert_thresholds,
            ThresholdUpdateRequest,
        )

        with patch(
            "backend.api.v1.endpoints.swarm_alerts.get_alert_threshold_service"
        ) as mock_get:
            mock_get.side_effect = RuntimeError("Unexpected crash")

            request = ThresholdUpdateRequest(buffer_utilization=75.0)
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(update_alert_thresholds(request))

            assert exc_info.value.status_code == 500


class TestIntegration:
    """Integration tests for alert threshold endpoints"""

    def test_full_get_put_get_round_trip(self):
        """
        GIVEN a FastAPI app with swarm alerts router
        WHEN performing GET -> PUT -> GET round trip
        THEN PUT changes should be reflected in subsequent GET
        """
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/v1")
        test_client = TestClient(test_app)

        # GET defaults
        response1 = test_client.get("/api/v1/swarm/alerts/thresholds")
        assert response1.status_code == 200
        assert response1.json()["buffer_utilization"] == 80.0

        # PUT update
        response2 = test_client.put(
            "/api/v1/swarm/alerts/thresholds",
            json={"buffer_utilization": 65.0, "crash_count": 7},
        )
        assert response2.status_code == 200
        assert response2.json()["buffer_utilization"] == 65.0
        assert response2.json()["crash_count"] == 7

        # GET verify changes persisted
        response3 = test_client.get("/api/v1/swarm/alerts/thresholds")
        assert response3.status_code == 200
        assert response3.json()["buffer_utilization"] == 65.0
        assert response3.json()["crash_count"] == 7
        assert response3.json()["revocation_rate"] == 50.0  # unchanged
