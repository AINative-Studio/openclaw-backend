"""
Unit Tests for Prometheus Metrics Service

Tests metric registration, counter increments, gauge collection,
histogram observations, and Prometheus text format generation.

Epic E8-S1: Prometheus Metrics Exporter
Refs: #49
"""

import pytest
import sys
import platform
from unittest.mock import Mock, patch, MagicMock

from prometheus_client import CollectorRegistry

from backend.services.prometheus_metrics_service import (
    PrometheusMetricsService,
    get_metrics_service,
)


class TestPrometheusMetricsServiceInit:
    """Test PrometheusMetricsService initialization"""

    @pytest.fixture
    def metrics_service(self):
        """Create fresh metrics service with isolated registry"""
        registry = CollectorRegistry()
        return PrometheusMetricsService(
            namespace="openclaw",
            registry=registry,
        )

    def test_creates_with_custom_registry(self):
        """
        GIVEN a custom CollectorRegistry
        WHEN creating PrometheusMetricsService
        THEN should use the provided registry
        """
        # Given
        registry = CollectorRegistry()

        # When
        service = PrometheusMetricsService(registry=registry)

        # Then
        assert service._registry is registry

    def test_creates_with_default_namespace(self):
        """
        GIVEN no namespace argument
        WHEN creating PrometheusMetricsService
        THEN should use 'openclaw' as default namespace
        """
        # Given/When
        registry = CollectorRegistry()
        service = PrometheusMetricsService(registry=registry)

        # Then
        assert service._namespace == "openclaw"

    def test_creates_with_custom_namespace(self):
        """
        GIVEN custom namespace
        WHEN creating PrometheusMetricsService
        THEN should use the provided namespace
        """
        # Given/When
        registry = CollectorRegistry()
        service = PrometheusMetricsService(
            namespace="test_ns",
            registry=registry,
        )

        # Then
        assert service._namespace == "test_ns"

    def test_registers_build_info(self, metrics_service):
        """
        GIVEN a fresh metrics service
        WHEN initialized
        THEN should have build info metric with version and python_version
        """
        # When
        output = metrics_service.generate_metrics()

        # Then
        assert "openclaw_build_info" in output
        assert platform.python_version() in output

    def test_all_counter_metrics_defined(self, metrics_service):
        """
        GIVEN a fresh metrics service
        WHEN initialized
        THEN should have all required counter metrics registered
        """
        # Then
        assert metrics_service._task_assignments_total is not None
        assert metrics_service._leases_issued_total is not None
        assert metrics_service._leases_expired_total is not None
        assert metrics_service._leases_revoked_total is not None
        assert metrics_service._node_crashes_total is not None
        assert metrics_service._tasks_requeued_total is not None
        assert metrics_service._partition_events_total is not None
        assert metrics_service._results_buffered_total is not None
        assert metrics_service._results_flushed_total is not None
        assert metrics_service._capability_validations_total is not None
        assert metrics_service._tokens_issued_total is not None
        assert metrics_service._tokens_revoked_total is not None
        assert metrics_service._audit_events_total is not None
        assert metrics_service._messages_verified_total is not None
        assert metrics_service._recovery_operations_total is not None

    def test_all_gauge_metrics_defined(self, metrics_service):
        """
        GIVEN a fresh metrics service
        WHEN initialized
        THEN should have all required gauge metrics registered
        """
        # Then
        assert metrics_service._active_leases is not None
        assert metrics_service._buffer_size is not None
        assert metrics_service._buffer_utilization_percent is not None
        assert metrics_service._partition_degraded is not None

    def test_histogram_metrics_defined(self, metrics_service):
        """
        GIVEN a fresh metrics service
        WHEN initialized
        THEN should have recovery duration histogram registered
        """
        # Then
        assert metrics_service._recovery_duration_seconds is not None


class TestCounterMetrics:
    """Test counter increment methods"""

    @pytest.fixture
    def metrics_service(self):
        """Create fresh metrics service with isolated registry"""
        registry = CollectorRegistry()
        return PrometheusMetricsService(
            namespace="openclaw",
            registry=registry,
        )

    def test_record_task_assignment_success(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a successful task assignment
        THEN should increment task_assignments_total{status=success}
        """
        # When
        metrics_service.record_task_assignment("success")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_task_assignments_total{status="success"}' in output

    def test_record_task_assignment_failed(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a failed task assignment
        THEN should increment task_assignments_total{status=failed}
        """
        # When
        metrics_service.record_task_assignment("failed")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_task_assignments_total{status="failed"}' in output

    def test_record_task_assignment_no_capable_nodes(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording assignment with no capable nodes
        THEN should increment task_assignments_total{status=no_capable_nodes}
        """
        # When
        metrics_service.record_task_assignment("no_capable_nodes")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_task_assignments_total{status="no_capable_nodes"}' in output

    def test_record_lease_issued(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a lease issuance
        THEN should increment leases_issued_total with complexity label
        """
        # When
        metrics_service.record_lease_issued("high")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_leases_issued_total{complexity="high"}' in output

    def test_record_lease_expired(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a lease expiration
        THEN should increment leases_expired_total
        """
        # When
        metrics_service.record_lease_expired()
        metrics_service.record_lease_expired()

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_leases_expired_total" in output
        assert "2.0" in output

    def test_record_lease_revoked(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a lease revocation
        THEN should increment leases_revoked_total with reason label
        """
        # When
        metrics_service.record_lease_revoked("crash")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_leases_revoked_total{reason="crash"}' in output

    def test_record_node_crash(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a node crash
        THEN should increment node_crashes_total
        """
        # When
        metrics_service.record_node_crash()

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_node_crashes_total" in output

    def test_record_task_requeued(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a task requeue
        THEN should increment tasks_requeued_total with result label
        """
        # When
        metrics_service.record_task_requeued("success")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_tasks_requeued_total{result="success"}' in output

    def test_record_partition_event(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a partition event
        THEN should increment partition_events_total with type label
        """
        # When
        metrics_service.record_partition_event("detected")
        metrics_service.record_partition_event("recovered")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_partition_events_total{type="detected"}' in output
        assert 'openclaw_partition_events_total{type="recovered"}' in output

    def test_record_result_buffered(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a buffered result
        THEN should increment results_buffered_total
        """
        # When
        metrics_service.record_result_buffered()

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_results_buffered_total" in output

    def test_record_result_flushed(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a flushed result
        THEN should increment results_flushed_total with result label
        """
        # When
        metrics_service.record_result_flushed("success")
        metrics_service.record_result_flushed("failed")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_results_flushed_total{result="success"}' in output
        assert 'openclaw_results_flushed_total{result="failed"}' in output

    def test_record_capability_validation(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a capability validation
        THEN should increment capability_validations_total with result label
        """
        # When
        metrics_service.record_capability_validation("valid")
        metrics_service.record_capability_validation("capability_missing")
        metrics_service.record_capability_validation("resource_exceeded")
        metrics_service.record_capability_validation("scope_violation")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_capability_validations_total{result="valid"}' in output
        assert 'openclaw_capability_validations_total{result="capability_missing"}' in output
        assert 'openclaw_capability_validations_total{result="resource_exceeded"}' in output
        assert 'openclaw_capability_validations_total{result="scope_violation"}' in output

    def test_record_token_issued(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a token issuance
        THEN should increment tokens_issued_total
        """
        # When
        metrics_service.record_token_issued()

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_tokens_issued_total" in output

    def test_record_token_revoked(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording a token revocation
        THEN should increment tokens_revoked_total with reason label
        """
        # When
        metrics_service.record_token_revoked("rotation")
        metrics_service.record_token_revoked("compromise")
        metrics_service.record_token_revoked("manual")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_tokens_revoked_total{reason="rotation"}' in output
        assert 'openclaw_tokens_revoked_total{reason="compromise"}' in output
        assert 'openclaw_tokens_revoked_total{reason="manual"}' in output

    def test_record_audit_event(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording audit events of various types
        THEN should increment audit_events_total with type label
        """
        # When
        metrics_service.record_audit_event("AUTHENTICATION_SUCCESS")
        metrics_service.record_audit_event("AUTHORIZATION_FAILURE")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_audit_events_total{type="AUTHENTICATION_SUCCESS"}' in output
        assert 'openclaw_audit_events_total{type="AUTHORIZATION_FAILURE"}' in output

    def test_record_message_verified(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording message verifications
        THEN should increment messages_verified_total with result label
        """
        # When
        metrics_service.record_message_verified("success")
        metrics_service.record_message_verified("failed")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_messages_verified_total{result="success"}' in output
        assert 'openclaw_messages_verified_total{result="failed"}' in output

    def test_record_recovery_operation(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording recovery operations
        THEN should increment recovery_operations_total with type and status labels
        """
        # When
        metrics_service.record_recovery_operation("node_crash", "success")
        metrics_service.record_recovery_operation("partition_healed", "failed")

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_recovery_operations_total{status="success",type="node_crash"}' in output
        assert 'openclaw_recovery_operations_total{status="failed",type="partition_healed"}' in output

    def test_multiple_increments(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording the same counter multiple times
        THEN should correctly accumulate count
        """
        # When
        for _ in range(5):
            metrics_service.record_node_crash()

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_node_crashes_total 5.0" in output


class TestGaugeMetrics:
    """Test gauge collection from registered services"""

    @pytest.fixture
    def metrics_service(self):
        """Create fresh metrics service with isolated registry"""
        registry = CollectorRegistry()
        return PrometheusMetricsService(
            namespace="openclaw",
            registry=registry,
        )

    def test_collect_service_stats_with_lease_service(self, metrics_service):
        """
        GIVEN a lease expiration service registered
        WHEN collecting service stats
        THEN should update active_leases gauge
        """
        # Given
        mock_lease_service = Mock()
        mock_lease_service.get_expiration_stats.return_value = {
            "active_leases": 42,
            "upcoming_expirations": 5,
        }
        metrics_service.register_service("lease_expiration", mock_lease_service)

        # When
        metrics_service.collect_service_stats()

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_active_leases 42.0" in output

    def test_collect_service_stats_with_buffer_service(self, metrics_service):
        """
        GIVEN a result buffer service registered
        WHEN collecting service stats
        THEN should update buffer_size and buffer_utilization gauges
        """
        # Given
        mock_buffer_service = Mock()
        mock_buffer_service.get_buffer_metrics.return_value = Mock(
            current_size=150,
            utilization_percent=75.0,
        )
        metrics_service.register_service("result_buffer", mock_buffer_service)

        # When
        metrics_service.collect_service_stats()

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_buffer_size 150.0" in output
        assert "openclaw_buffer_utilization_percent 75.0" in output

    def test_collect_service_stats_with_partition_service(self, metrics_service):
        """
        GIVEN a partition detection service registered
        WHEN collecting service stats in degraded mode
        THEN should set partition_degraded gauge to 1
        """
        # Given
        mock_partition_service = Mock()
        mock_partition_service.get_partition_statistics.return_value = {
            "current_state": "degraded",
            "total_partitions": 3,
        }
        metrics_service.register_service("partition_detection", mock_partition_service)

        # When
        metrics_service.collect_service_stats()

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_partition_degraded 1.0" in output

    def test_collect_service_stats_normal_partition_state(self, metrics_service):
        """
        GIVEN a partition detection service registered
        WHEN collecting service stats in normal mode
        THEN should set partition_degraded gauge to 0
        """
        # Given
        mock_partition_service = Mock()
        mock_partition_service.get_partition_statistics.return_value = {
            "current_state": "normal",
            "total_partitions": 0,
        }
        metrics_service.register_service("partition_detection", mock_partition_service)

        # When
        metrics_service.collect_service_stats()

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_partition_degraded 0.0" in output

    def test_collect_service_stats_handles_missing_services(self, metrics_service):
        """
        GIVEN no services registered
        WHEN collecting service stats
        THEN should not raise errors (gauges stay at default 0)
        """
        # When - no services registered
        metrics_service.collect_service_stats()

        # Then - should not raise, gauges at 0
        output = metrics_service.generate_metrics()
        assert "openclaw_active_leases 0.0" in output

    def test_collect_service_stats_handles_service_errors(self, metrics_service):
        """
        GIVEN a service that raises an exception
        WHEN collecting service stats
        THEN should not raise, other services should still work
        """
        # Given
        mock_failing_service = Mock()
        mock_failing_service.get_expiration_stats.side_effect = RuntimeError("DB down")
        metrics_service.register_service("lease_expiration", mock_failing_service)

        mock_partition_service = Mock()
        mock_partition_service.get_partition_statistics.return_value = {
            "current_state": "normal",
        }
        metrics_service.register_service("partition_detection", mock_partition_service)

        # When - should not raise
        metrics_service.collect_service_stats()

        # Then - partition gauge should still be updated
        output = metrics_service.generate_metrics()
        assert "openclaw_partition_degraded 0.0" in output


class TestHistogramMetrics:
    """Test histogram observation methods"""

    @pytest.fixture
    def metrics_service(self):
        """Create fresh metrics service with isolated registry"""
        registry = CollectorRegistry()
        return PrometheusMetricsService(
            namespace="openclaw",
            registry=registry,
        )

    def test_observe_recovery_duration(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN observing recovery duration
        THEN should record in recovery_duration_seconds histogram
        """
        # When
        metrics_service.observe_recovery_duration("node_crash", 5.2)
        metrics_service.observe_recovery_duration("partition_healed", 12.8)

        # Then
        output = metrics_service.generate_metrics()
        assert "openclaw_recovery_duration_seconds" in output
        assert "node_crash" in output
        assert "partition_healed" in output

    def test_observe_recovery_duration_multiple_samples(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN observing multiple recovery durations
        THEN should track count and sum correctly
        """
        # When
        metrics_service.observe_recovery_duration("node_crash", 1.0)
        metrics_service.observe_recovery_duration("node_crash", 2.0)
        metrics_service.observe_recovery_duration("node_crash", 3.0)

        # Then
        output = metrics_service.generate_metrics()
        assert 'openclaw_recovery_duration_seconds_count{type="node_crash"} 3.0' in output
        assert 'openclaw_recovery_duration_seconds_sum{type="node_crash"} 6.0' in output


class TestGenerateMetrics:
    """Test Prometheus text format output"""

    @pytest.fixture
    def metrics_service(self):
        """Create fresh metrics service with isolated registry"""
        registry = CollectorRegistry()
        return PrometheusMetricsService(
            namespace="openclaw",
            registry=registry,
        )

    def test_generate_metrics_returns_string(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN generating metrics
        THEN should return a string
        """
        # When
        output = metrics_service.generate_metrics()

        # Then
        assert isinstance(output, str)

    def test_generate_metrics_contains_help_lines(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN generating metrics
        THEN should contain HELP lines for defined metrics
        """
        # When
        output = metrics_service.generate_metrics()

        # Then
        assert "# HELP openclaw_task_assignments_total" in output
        assert "# HELP openclaw_active_leases" in output

    def test_generate_metrics_contains_type_lines(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN generating metrics
        THEN should contain TYPE lines for defined metrics
        """
        # When
        output = metrics_service.generate_metrics()

        # Then
        assert "# TYPE openclaw_task_assignments_total counter" in output
        assert "# TYPE openclaw_active_leases gauge" in output
        assert "# TYPE openclaw_recovery_duration_seconds histogram" in output

    def test_generate_metrics_valid_prometheus_format(self, metrics_service):
        """
        GIVEN a metrics service with some recorded metrics
        WHEN generating metrics
        THEN output should be valid Prometheus text format
        """
        # Given
        metrics_service.record_task_assignment("success")
        metrics_service.record_node_crash()

        # When
        output = metrics_service.generate_metrics()

        # Then - each non-empty line should be a comment or metric line
        for line in output.strip().split("\n"):
            if line.strip() == "":
                continue
            assert (
                line.startswith("# ") or
                line.startswith("openclaw_") or
                line.startswith("# EOF")
            ), f"Invalid Prometheus format line: {line}"

    def test_generate_metrics_after_recording(self, metrics_service):
        """
        GIVEN a metrics service
        WHEN recording metrics then generating output
        THEN output should contain recorded values
        """
        # Given
        metrics_service.record_task_assignment("success")
        metrics_service.record_task_assignment("success")
        metrics_service.record_task_assignment("failed")

        # When
        output = metrics_service.generate_metrics()

        # Then
        assert 'openclaw_task_assignments_total{status="success"} 2.0' in output
        assert 'openclaw_task_assignments_total{status="failed"} 1.0' in output


class TestSingletonFactory:
    """Test get_metrics_service() singleton behavior"""

    def test_returns_same_instance(self):
        """
        GIVEN get_metrics_service called multiple times
        WHEN comparing returned instances
        THEN should return the same instance
        """
        # Reset singleton for test isolation
        import backend.services.prometheus_metrics_service as mod
        mod._metrics_service_instance = None

        # When
        service1 = get_metrics_service()
        service2 = get_metrics_service()

        # Then
        assert service1 is service2

        # Cleanup
        mod._metrics_service_instance = None

    def test_returns_prometheus_metrics_service(self):
        """
        GIVEN get_metrics_service called
        WHEN checking return type
        THEN should return PrometheusMetricsService instance
        """
        # Reset singleton
        import backend.services.prometheus_metrics_service as mod
        mod._metrics_service_instance = None

        # When
        service = get_metrics_service()

        # Then
        assert isinstance(service, PrometheusMetricsService)

        # Cleanup
        mod._metrics_service_instance = None
