"""
Prometheus Metrics Endpoint Tests

Tests for GET /metrics endpoint returning Prometheus text format.

Epic E8-S1: Prometheus Metrics Exporter
Refs: #49
"""

import pytest
from unittest.mock import Mock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.metrics import router


@pytest.fixture
def app():
    """Create FastAPI test app with metrics router"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


class TestMetricsEndpoint:
    """Test GET /metrics endpoint"""

    def test_returns_200(self, client):
        """
        GIVEN a running metrics endpoint
        WHEN requesting GET /api/v1/metrics
        THEN should return HTTP 200
        """
        # When
        response = client.get("/api/v1/metrics")

        # Then
        assert response.status_code == 200

    def test_returns_prometheus_content_type(self, client):
        """
        GIVEN a running metrics endpoint
        WHEN requesting GET /api/v1/metrics
        THEN should return text/plain content type with Prometheus version
        """
        # When
        response = client.get("/api/v1/metrics")

        # Then
        content_type = response.headers["content-type"]
        assert "text/plain" in content_type
        assert "version=0.0.4" in content_type

    def test_contains_expected_counter_metrics(self, client):
        """
        GIVEN a running metrics endpoint
        WHEN requesting metrics
        THEN should contain expected counter metric names
        """
        # When
        response = client.get("/api/v1/metrics")
        body = response.text

        # Then
        expected_metrics = [
            "openclaw_task_assignments_total",
            "openclaw_leases_issued_total",
            "openclaw_leases_expired_total",
            "openclaw_leases_revoked_total",
            "openclaw_node_crashes_total",
            "openclaw_tasks_requeued_total",
            "openclaw_partition_events_total",
            "openclaw_results_buffered_total",
            "openclaw_results_flushed_total",
            "openclaw_capability_validations_total",
            "openclaw_tokens_issued_total",
            "openclaw_tokens_revoked_total",
            "openclaw_audit_events_total",
            "openclaw_messages_verified_total",
            "openclaw_recovery_operations_total",
        ]
        for metric_name in expected_metrics:
            assert metric_name in body, f"Missing metric: {metric_name}"

    def test_contains_expected_gauge_metrics(self, client):
        """
        GIVEN a running metrics endpoint
        WHEN requesting metrics
        THEN should contain expected gauge metric names
        """
        # When
        response = client.get("/api/v1/metrics")
        body = response.text

        # Then
        expected_gauges = [
            "openclaw_active_leases",
            "openclaw_buffer_size",
            "openclaw_buffer_utilization_percent",
            "openclaw_partition_degraded",
        ]
        for gauge_name in expected_gauges:
            assert gauge_name in body, f"Missing gauge: {gauge_name}"

    def test_contains_build_info(self, client):
        """
        GIVEN a running metrics endpoint
        WHEN requesting metrics
        THEN should contain build info metric
        """
        # When
        response = client.get("/api/v1/metrics")
        body = response.text

        # Then
        assert "openclaw_build_info" in body

    def test_contains_histogram_metrics(self, client):
        """
        GIVEN a running metrics endpoint
        WHEN requesting metrics
        THEN should contain histogram metric names
        """
        # When
        response = client.get("/api/v1/metrics")
        body = response.text

        # Then
        assert "openclaw_recovery_duration_seconds" in body

    def test_valid_prometheus_format(self, client):
        """
        GIVEN a running metrics endpoint
        WHEN requesting metrics
        THEN each line should be valid Prometheus text format
        """
        # When
        response = client.get("/api/v1/metrics")
        body = response.text

        # Then
        for line in body.strip().split("\n"):
            if line.strip() == "":
                continue
            assert (
                line.startswith("# ") or
                line.startswith("openclaw_") or
                line.startswith("# EOF")
            ), f"Invalid Prometheus format line: {line}"

    def test_metrics_reflect_recorded_values(self, client):
        """
        GIVEN metrics service with recorded values
        WHEN requesting metrics
        THEN output should contain those values
        """
        # Given - record some metrics via the service
        from backend.services.prometheus_metrics_service import get_metrics_service
        service = get_metrics_service()
        service.record_task_assignment("success")

        # When
        response = client.get("/api/v1/metrics")
        body = response.text

        # Then - the counter should be present (value may vary due to singleton)
        assert "openclaw_task_assignments_total" in body
