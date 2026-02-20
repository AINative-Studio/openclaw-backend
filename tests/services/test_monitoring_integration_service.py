"""
Tests for MonitoringIntegrationService (E8-S5).

Unified facade wrapping PrometheusMetricsService + TaskTimelineService +
SwarmHealthService into a single fire-and-forget API.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestMonitoringIntegrationInit:
    """Tests for MonitoringIntegrationService initialization."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        import backend.services.monitoring_integration_service as mod
        mod._monitoring_integration_instance = None
        yield
        mod._monitoring_integration_instance = None

    def test_initializes_with_all_services_available(self):
        """
        GIVEN all three monitoring services are importable
        WHEN MonitoringIntegrationService is created
        THEN all three service references should be set
        """
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        service = MonitoringIntegrationService()
        assert service._metrics_service is not None
        assert service._timeline_service is not None
        assert service._health_service is not None
        assert service._event_types is not None
        assert service._bootstrapped is False

    def test_handles_missing_metrics_service(self):
        """
        GIVEN PrometheusMetricsService import fails
        WHEN MonitoringIntegrationService is created
        THEN _metrics_service should be None but others available
        """
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        with patch(
            "backend.services.monitoring_integration_service.get_metrics_service",
            side_effect=ImportError("no metrics"),
        ):
            service = MonitoringIntegrationService()
        assert service._metrics_service is None
        assert service._timeline_service is not None
        assert service._health_service is not None

    def test_handles_missing_timeline_service(self):
        """
        GIVEN TaskTimelineService import fails
        WHEN MonitoringIntegrationService is created
        THEN _timeline_service should be None but others available
        """
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        with patch(
            "backend.services.monitoring_integration_service.get_timeline_service",
            side_effect=ImportError("no timeline"),
        ):
            service = MonitoringIntegrationService()
        assert service._metrics_service is not None
        assert service._timeline_service is None
        assert service._health_service is not None

    def test_handles_all_services_missing(self):
        """
        GIVEN all three monitoring service imports fail
        WHEN MonitoringIntegrationService is created
        THEN all service references should be None
        """
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        with patch(
            "backend.services.monitoring_integration_service.get_metrics_service",
            side_effect=ImportError("no metrics"),
        ), patch(
            "backend.services.monitoring_integration_service.get_timeline_service",
            side_effect=ImportError("no timeline"),
        ), patch(
            "backend.services.monitoring_integration_service.get_swarm_health_service",
            side_effect=ImportError("no health"),
        ):
            service = MonitoringIntegrationService()
        assert service._metrics_service is None
        assert service._timeline_service is None
        assert service._health_service is None
        assert service._bootstrapped is False


class TestBootstrap:
    """Tests for bootstrap() service registration."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        import backend.services.monitoring_integration_service as mod
        mod._monitoring_integration_instance = None
        yield
        mod._monitoring_integration_instance = None

    @pytest.fixture
    def service(self):
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        svc = MonitoringIntegrationService()
        svc._health_service = Mock()
        svc._metrics_service = Mock()
        return svc

    def test_registers_services_with_health_and_metrics(self, service):
        """
        GIVEN a MonitoringIntegrationService with health and metrics available
        WHEN bootstrap is called with subsystem services
        THEN each subsystem should be registered with both health and metrics
        """
        mock_lease_svc = Mock()
        mock_buffer_svc = Mock()
        results = service.bootstrap({
            "lease_expiration": mock_lease_svc,
            "result_buffer": mock_buffer_svc,
        })
        assert service._health_service.register_service.call_count == 2
        assert service._metrics_service.register_service.call_count == 2
        service._health_service.register_service.assert_any_call(
            "lease_expiration", mock_lease_svc
        )
        service._metrics_service.register_service.assert_any_call(
            "lease_expiration", mock_lease_svc
        )
        assert results["lease_expiration"] is True
        assert results["result_buffer"] is True

    def test_sets_bootstrapped_flag(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN bootstrap is called
        THEN _bootstrapped should be set to True
        """
        assert service._bootstrapped is False
        service.bootstrap({"lease_expiration": Mock()})
        assert service._bootstrapped is True

    def test_handles_missing_health_service_gracefully(self):
        """
        GIVEN health service is unavailable
        WHEN bootstrap is called
        THEN should still register with metrics and not raise
        """
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        svc = MonitoringIntegrationService()
        svc._health_service = None
        svc._metrics_service = Mock()
        results = svc.bootstrap({"lease_expiration": Mock()})
        assert svc._metrics_service.register_service.call_count == 1
        assert results["lease_expiration"] is True
        assert svc._bootstrapped is True

    def test_returns_registration_results(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN bootstrap is called with multiple subsystems
        THEN should return dict of {name: success_bool}
        """
        service._health_service.register_service.side_effect = [
            None,
            Exception("fail"),
        ]
        results = service.bootstrap({
            "lease_expiration": Mock(),
            "partition_detection": Mock(),
        })
        assert isinstance(results, dict)
        assert "lease_expiration" in results
        assert "partition_detection" in results


class TestTimelineOnlyMethods:
    """Tests for on_*() methods that only record timeline events."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        import backend.services.monitoring_integration_service as mod
        mod._monitoring_integration_instance = None
        yield
        mod._monitoring_integration_instance = None

    @pytest.fixture
    def service(self):
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        svc = MonitoringIntegrationService()
        svc._timeline_service = Mock()
        svc._metrics_service = Mock()
        return svc

    def test_on_task_created(self, service):
        """
        GIVEN a MonitoringIntegrationService with timeline available
        WHEN on_task_created is called
        THEN should record TASK_CREATED event and NOT call any metrics method
        """
        service.on_task_created("task-1", peer_id="peer-1", metadata={"key": "val"})
        service._timeline_service.record_event.assert_called_once()
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.TASK_CREATED
        assert call_args[1]["task_id"] == "task-1"
        assert call_args[1]["peer_id"] == "peer-1"
        # Verify no metrics methods called (except register_service which is mock default)
        service._metrics_service.record_task_assignment.assert_not_called()

    def test_on_task_queued(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_task_queued is called
        THEN should record TASK_QUEUED event
        """
        service.on_task_queued("task-2", metadata={"priority": "high"})
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.TASK_QUEUED
        assert call_args[1]["task_id"] == "task-2"

    def test_on_task_started(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_task_started is called
        THEN should record TASK_STARTED event
        """
        service.on_task_started("task-3", "peer-1")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.TASK_STARTED
        assert call_args[1]["task_id"] == "task-3"
        assert call_args[1]["peer_id"] == "peer-1"

    def test_on_task_progress(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_task_progress is called
        THEN should record TASK_PROGRESS event
        """
        service.on_task_progress("task-4", "peer-2")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.TASK_PROGRESS

    def test_on_task_completed(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_task_completed is called
        THEN should record TASK_COMPLETED event
        """
        service.on_task_completed("task-5", "peer-3")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.TASK_COMPLETED

    def test_on_task_failed(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_task_failed is called
        THEN should record TASK_FAILED event
        """
        service.on_task_failed("task-6", "peer-4")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.TASK_FAILED

    def test_on_task_expired(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_task_expired is called
        THEN should record TASK_EXPIRED event
        """
        service.on_task_expired("task-7")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.TASK_EXPIRED
        assert call_args[1]["task_id"] == "task-7"


class TestCombinedMethods:
    """Tests for on_*() methods that record both timeline events AND metrics."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        import backend.services.monitoring_integration_service as mod
        mod._monitoring_integration_instance = None
        yield
        mod._monitoring_integration_instance = None

    @pytest.fixture
    def service(self):
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        svc = MonitoringIntegrationService()
        svc._timeline_service = Mock()
        svc._metrics_service = Mock()
        return svc

    def test_on_task_leased(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_task_leased is called
        THEN should record TASK_LEASED event AND call record_lease_issued
        """
        service.on_task_leased("task-1", "peer-1", complexity="high")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.TASK_LEASED
        assert call_args[1]["task_id"] == "task-1"
        assert call_args[1]["peer_id"] == "peer-1"
        service._metrics_service.record_lease_issued.assert_called_once_with("high")

    def test_on_task_requeued(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_task_requeued is called
        THEN should record TASK_REQUEUED event AND call record_task_requeued
        """
        service.on_task_requeued("task-2", result="timeout")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.TASK_REQUEUED
        service._metrics_service.record_task_requeued.assert_called_once_with("timeout")

    def test_on_lease_expired(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_lease_expired is called
        THEN should record LEASE_EXPIRED event AND call record_lease_expired
        """
        service.on_lease_expired("task-3", peer_id="peer-2")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.LEASE_EXPIRED
        service._metrics_service.record_lease_expired.assert_called_once()

    def test_on_lease_revoked(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_lease_revoked is called
        THEN should record LEASE_REVOKED event AND call record_lease_revoked
        """
        service.on_lease_revoked("task-4", peer_id="peer-3", reason="timeout")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.LEASE_REVOKED
        service._metrics_service.record_lease_revoked.assert_called_once_with("timeout")

    def test_on_node_crashed(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_node_crashed is called
        THEN should record NODE_CRASHED event AND call record_node_crash
        """
        service.on_node_crashed("peer-5")
        call_args = service._timeline_service.record_event.call_args
        assert call_args[1]["event_type"] == service._event_types.NODE_CRASHED
        assert call_args[1]["peer_id"] == "peer-5"
        service._metrics_service.record_node_crash.assert_called_once()


class TestMetricsOnlyMethods:
    """Tests for on_*() methods that only call Prometheus metrics."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        import backend.services.monitoring_integration_service as mod
        mod._monitoring_integration_instance = None
        yield
        mod._monitoring_integration_instance = None

    @pytest.fixture
    def service(self):
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        svc = MonitoringIntegrationService()
        svc._timeline_service = Mock()
        svc._metrics_service = Mock()
        return svc

    def test_on_task_assigned(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_task_assigned is called
        THEN should call record_task_assignment and NOT record timeline event
        """
        service.on_task_assigned("task-1", "peer-1", status="success")
        service._metrics_service.record_task_assignment.assert_called_once_with(
            "success"
        )
        service._timeline_service.record_event.assert_not_called()

    def test_on_partition_event(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_partition_event is called
        THEN should call record_partition_event
        """
        service.on_partition_event("split")
        service._metrics_service.record_partition_event.assert_called_once_with("split")
        service._timeline_service.record_event.assert_not_called()

    def test_on_result_buffered(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_result_buffered is called
        THEN should call record_result_buffered
        """
        service.on_result_buffered(task_id="task-2")
        service._metrics_service.record_result_buffered.assert_called_once()
        service._timeline_service.record_event.assert_not_called()

    def test_on_result_flushed(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_result_flushed is called
        THEN should call record_result_flushed
        """
        service.on_result_flushed(task_id="task-3", result="success")
        service._metrics_service.record_result_flushed.assert_called_once_with(
            "success"
        )
        service._timeline_service.record_event.assert_not_called()

    def test_on_recovery_completed(self, service):
        """
        GIVEN a MonitoringIntegrationService
        WHEN on_recovery_completed is called
        THEN should call record_recovery_operation AND observe_recovery_duration
        """
        service.on_recovery_completed("lease", "success", duration_seconds=1.5)
        service._metrics_service.record_recovery_operation.assert_called_once_with(
            "lease", "success"
        )
        service._metrics_service.observe_recovery_duration.assert_called_once_with(
            "lease", 1.5
        )
        service._timeline_service.record_event.assert_not_called()


class TestFireAndForget:
    """Tests for error isolation — failures in one subsystem don't affect others."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        import backend.services.monitoring_integration_service as mod
        mod._monitoring_integration_instance = None
        yield
        mod._monitoring_integration_instance = None

    @pytest.fixture
    def service(self):
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        svc = MonitoringIntegrationService()
        svc._timeline_service = Mock()
        svc._metrics_service = Mock()
        return svc

    def test_timeline_error_does_not_prevent_metrics(self, service):
        """
        GIVEN timeline service raises an exception
        WHEN on_task_leased is called (combined method)
        THEN metrics call should still succeed without raising
        """
        service._timeline_service.record_event.side_effect = RuntimeError("boom")
        # Should not raise
        service.on_task_leased("task-1", "peer-1", complexity="low")
        service._metrics_service.record_lease_issued.assert_called_once_with("low")

    def test_metrics_error_does_not_raise(self, service):
        """
        GIVEN metrics service raises an exception
        WHEN on_task_leased is called (combined method)
        THEN timeline call should still succeed and no exception raised
        """
        service._metrics_service.record_lease_issued.side_effect = RuntimeError("boom")
        # Should not raise
        service.on_task_leased("task-1", "peer-1")
        service._timeline_service.record_event.assert_called_once()

    def test_missing_timeline_silently_skipped(self, service):
        """
        GIVEN timeline service is None
        WHEN on_task_created is called (timeline-only method)
        THEN should not raise
        """
        service._timeline_service = None
        # Should not raise
        service.on_task_created("task-1")

    def test_missing_metrics_silently_skipped(self, service):
        """
        GIVEN metrics service is None
        WHEN on_task_assigned is called (metrics-only method)
        THEN should not raise
        """
        service._metrics_service = None
        # Should not raise
        service.on_task_assigned("task-1", "peer-1")

    def test_both_missing_silently_skipped(self, service):
        """
        GIVEN both timeline and metrics services are None
        WHEN on_task_leased is called (combined method)
        THEN should not raise
        """
        service._timeline_service = None
        service._metrics_service = None
        # Should not raise
        service.on_task_leased("task-1", "peer-1")

    def test_timeline_error_in_timeline_only_method(self, service):
        """
        GIVEN timeline service raises on a timeline-only method
        WHEN on_task_created is called
        THEN should not raise
        """
        service._timeline_service.record_event.side_effect = RuntimeError("fail")
        service.on_task_created("task-1")
        service.on_task_queued("task-2")
        service.on_task_started("task-3", "peer-1")
        service.on_task_progress("task-4", "peer-1")
        service.on_task_completed("task-5", "peer-1")
        service.on_task_failed("task-6", "peer-1")
        service.on_task_expired("task-7")

    def test_metrics_error_in_metrics_only_method(self, service):
        """
        GIVEN metrics service raises on metrics-only methods
        WHEN on_task_assigned and others are called
        THEN should not raise
        """
        service._metrics_service.record_task_assignment.side_effect = RuntimeError("fail")
        service._metrics_service.record_partition_event.side_effect = RuntimeError("fail")
        service._metrics_service.record_result_buffered.side_effect = RuntimeError("fail")
        service._metrics_service.record_result_flushed.side_effect = RuntimeError("fail")
        service._metrics_service.record_recovery_operation.side_effect = RuntimeError("fail")
        service.on_task_assigned("t", "p")
        service.on_partition_event("split")
        service.on_result_buffered()
        service.on_result_flushed()
        service.on_recovery_completed("lease", "success", duration_seconds=1.0)

    def test_combined_method_errors_all_paths(self, service):
        """
        GIVEN timeline and metrics both raise errors
        WHEN combined methods are called
        THEN should not raise for any of them
        """
        service._timeline_service.record_event.side_effect = RuntimeError("fail")
        service._metrics_service.record_task_requeued.side_effect = RuntimeError("fail")
        service._metrics_service.record_lease_expired.side_effect = RuntimeError("fail")
        service._metrics_service.record_lease_revoked.side_effect = RuntimeError("fail")
        service._metrics_service.record_node_crash.side_effect = RuntimeError("fail")
        service.on_task_requeued("t")
        service.on_lease_expired("t")
        service.on_lease_revoked("t")
        service.on_node_crashed("p")


class TestGetStatus:
    """Tests for get_status() monitoring infrastructure health."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        import backend.services.monitoring_integration_service as mod
        mod._monitoring_integration_instance = None
        yield
        mod._monitoring_integration_instance = None

    def test_returns_operational_when_all_available(self):
        """
        GIVEN all three monitoring services are available
        WHEN get_status is called
        THEN status should be 'operational' with correct subsystem info
        """
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        svc = MonitoringIntegrationService()
        svc._metrics_service = Mock()
        svc._timeline_service = Mock()
        svc._timeline_service.get_event_count.return_value = 42
        svc._health_service = Mock()
        svc._health_service._registered_services = {"a": Mock(), "b": Mock()}
        svc._bootstrapped = True

        status = svc.get_status()
        assert status["status"] == "operational"
        assert status["subsystems"]["metrics"]["available"] is True
        assert status["subsystems"]["timeline"]["available"] is True
        assert status["subsystems"]["health"]["available"] is True
        assert status["timeline_event_count"] == 42
        assert status["registered_health_subsystems"] == 2
        assert status["bootstrapped"] is True
        assert "timestamp" in status

    def test_returns_partial_when_some_missing(self):
        """
        GIVEN metrics service is unavailable
        WHEN get_status is called
        THEN status should be 'partial'
        """
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        svc = MonitoringIntegrationService()
        svc._metrics_service = None
        svc._timeline_service = Mock()
        svc._timeline_service.get_event_count.return_value = 10
        svc._health_service = Mock()
        svc._health_service._registered_services = {}

        status = svc.get_status()
        assert status["status"] == "partial"
        assert status["subsystems"]["metrics"]["available"] is False
        assert status["subsystems"]["timeline"]["available"] is True
        assert status["subsystems"]["health"]["available"] is True

    def test_returns_unavailable_when_all_missing(self):
        """
        GIVEN all three monitoring services are unavailable
        WHEN get_status is called
        THEN status should be 'unavailable' with zero counts
        """
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
        )
        svc = MonitoringIntegrationService()
        svc._metrics_service = None
        svc._timeline_service = None
        svc._health_service = None

        status = svc.get_status()
        assert status["status"] == "unavailable"
        assert status["subsystems"]["metrics"]["available"] is False
        assert status["subsystems"]["timeline"]["available"] is False
        assert status["subsystems"]["health"]["available"] is False
        assert status["timeline_event_count"] == 0
        assert status["registered_health_subsystems"] == 0
        assert status["bootstrapped"] is False


class TestSingleton:
    """Tests for the singleton factory function."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        import backend.services.monitoring_integration_service as mod
        mod._monitoring_integration_instance = None
        yield
        mod._monitoring_integration_instance = None

    def test_returns_same_instance(self):
        """
        GIVEN the singleton has been created
        WHEN get_monitoring_integration_service is called twice
        THEN should return the same instance
        """
        from backend.services.monitoring_integration_service import (
            get_monitoring_integration_service,
        )
        service1 = get_monitoring_integration_service()
        service2 = get_monitoring_integration_service()
        assert service1 is service2

    def test_returns_correct_type(self):
        """
        GIVEN the singleton factory is called
        WHEN the instance is returned
        THEN it should be a MonitoringIntegrationService
        """
        from backend.services.monitoring_integration_service import (
            MonitoringIntegrationService,
            get_monitoring_integration_service,
        )
        service = get_monitoring_integration_service()
        assert isinstance(service, MonitoringIntegrationService)
