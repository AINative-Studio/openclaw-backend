"""
Unit Tests for Datadog Observability Service

Tests initialization, DogStatsD metrics, LLMObs span helpers, and status
reporting. All tests mock ddtrace imports so they run without Datadog installed.
"""

import os
import pytest
from unittest.mock import patch, MagicMock, PropertyMock

import backend.services.datadog_service as dd_module
from backend.services.datadog_service import (
    DatadogService,
    _NoopContextManager,
)

# Ensure httpx is available for tests
import httpx  # noqa: F401


def _fresh_service(enabled: bool = False, **env_overrides) -> DatadogService:
    """Create a DatadogService with a clean state (bypasses singleton)."""
    env = {"DD_LLMOBS_ENABLED": "1" if enabled else "0"}
    env.update(env_overrides)
    with patch.dict("os.environ", env, clear=False):
        # Reset module-level singleton
        dd_module._datadog_service_instance = None
        svc = DatadogService()
    return svc


class TestDatadogServiceInit:
    """Describe DatadogService initialization"""

    def test_disabled_when_env_not_set(self):
        """
        GIVEN DD_LLMOBS_ENABLED is not set or is '0'
        WHEN creating DatadogService
        THEN it should be disabled
        """
        with patch.dict("os.environ", {"DD_LLMOBS_ENABLED": "0"}, clear=False):
            svc = DatadogService()

        assert svc._enabled is False
        assert svc._metrics_api_ready is False
        assert svc._llmobs_available is False

    def test_disabled_when_ddtrace_unavailable(self):
        """
        GIVEN DD_LLMOBS_ENABLED=1 but ddtrace is not installed
        WHEN creating DatadogService
        THEN it should be disabled (DDTRACE_AVAILABLE=False)
        """
        original = dd_module.DDTRACE_AVAILABLE
        try:
            dd_module.DDTRACE_AVAILABLE = False
            with patch.dict("os.environ", {"DD_LLMOBS_ENABLED": "1"}, clear=False):
                svc = DatadogService()
            assert svc._enabled is False
        finally:
            dd_module.DDTRACE_AVAILABLE = original

    def test_enabled_when_env_set_and_ddtrace_available(self):
        """
        GIVEN DD_LLMOBS_ENABLED=1 and DDTRACE_AVAILABLE=True and DD_API_KEY set
        WHEN creating DatadogService
        THEN it should be enabled with metrics API ready
        """
        original = dd_module.DDTRACE_AVAILABLE
        original_llmobs = dd_module._LLMObs
        try:
            dd_module.DDTRACE_AVAILABLE = True

            mock_llmobs = MagicMock()
            dd_module._LLMObs = mock_llmobs

            with patch.dict("os.environ", {
                "DD_LLMOBS_ENABLED": "1",
                "DD_API_KEY": "test_key_123",
            }, clear=False):
                svc = DatadogService()

            assert svc._enabled is True
            assert svc._metrics_api_ready is True
            mock_llmobs.enable.assert_called_once()
            assert svc._llmobs_available is True
        finally:
            dd_module.DDTRACE_AVAILABLE = original
            dd_module._LLMObs = original_llmobs

    def test_singleton_returns_same_instance(self):
        """
        GIVEN get_datadog_service called twice
        WHEN the singleton already exists
        THEN it should return the same instance
        """
        dd_module._datadog_service_instance = None
        with patch.dict("os.environ", {"DD_LLMOBS_ENABLED": "0"}, clear=False):
            from backend.services.datadog_service import get_datadog_service
            svc1 = get_datadog_service()
            svc2 = get_datadog_service()

        assert svc1 is svc2
        dd_module._datadog_service_instance = None

    def test_metrics_api_disabled_without_api_key(self):
        """
        GIVEN DD_LLMOBS_ENABLED=1 but DD_API_KEY not set
        WHEN initializing DatadogService
        THEN metrics_api_ready should be False but service should not crash
        """
        original = dd_module.DDTRACE_AVAILABLE
        original_llmobs = dd_module._LLMObs
        try:
            dd_module.DDTRACE_AVAILABLE = True
            dd_module._LLMObs = None

            env = {"DD_LLMOBS_ENABLED": "1"}
            # Remove DD_API_KEY if it exists
            with patch.dict("os.environ", env, clear=False):
                os.environ.pop("DD_API_KEY", None)
                svc = DatadogService()

            assert svc._enabled is True
            assert svc._metrics_api_ready is False
        finally:
            dd_module.DDTRACE_AVAILABLE = original
            dd_module._LLMObs = original_llmobs

    def test_llmobs_init_failure_handled_gracefully(self):
        """
        GIVEN LLMObs.enable() raises an exception
        WHEN initializing DatadogService
        THEN llmobs_available should be False but service should not crash
        """
        original = dd_module.DDTRACE_AVAILABLE
        original_llmobs = dd_module._LLMObs
        try:
            dd_module.DDTRACE_AVAILABLE = True

            mock_llmobs = MagicMock()
            mock_llmobs.enable.side_effect = Exception("LLMObs init failed")
            dd_module._LLMObs = mock_llmobs

            with patch.dict("os.environ", {"DD_LLMOBS_ENABLED": "1"}, clear=False):
                svc = DatadogService()

            assert svc._llmobs_available is False
        finally:
            dd_module.DDTRACE_AVAILABLE = original
            dd_module._LLMObs = original_llmobs


class TestDatadogServiceMetrics:
    """Describe DogStatsD metric recording"""

    def test_record_methods_noop_when_disabled(self):
        """
        GIVEN DatadogService is disabled
        WHEN calling record_* methods
        THEN no exceptions should be raised
        """
        svc = _fresh_service(enabled=False)

        # All these should be silent no-ops
        svc.record_task_assignment("success")
        svc.record_lease_issued("medium")
        svc.record_lease_expired()
        svc.record_lease_revoked("crash")
        svc.record_node_crash()
        svc.record_task_requeued("success")
        svc.record_recovery_duration("node_crash", 1.5)
        svc.record_recovery_operation("node_crash", "success")

    def test_record_task_assignment_submits_metric(self):
        """
        GIVEN DatadogService with metrics API ready
        WHEN calling record_task_assignment
        THEN _submit_metric should be called with correct metric and tags
        """
        svc = _fresh_service(enabled=False)
        svc._metrics_api_ready = True
        svc._api_key = "test_key"
        with patch.object(svc, "_submit_metric") as mock_submit:
            svc.record_task_assignment("success")
            mock_submit.assert_called_once_with(
                "task_assignments_total", 1, tags=["status:success"]
            )

    def test_record_lease_issued_submits_metric(self):
        """
        GIVEN DatadogService with metrics API ready
        WHEN calling record_lease_issued
        THEN _submit_metric should be called with correct metric and tags
        """
        svc = _fresh_service(enabled=False)
        svc._metrics_api_ready = True
        with patch.object(svc, "_submit_metric") as mock_submit:
            svc.record_lease_issued("high")
            mock_submit.assert_called_once_with(
                "leases_issued_total", 1, tags=["complexity:high"]
            )

    def test_record_lease_expired_submits_metric(self):
        """
        GIVEN DatadogService with metrics API ready
        WHEN calling record_lease_expired
        THEN _submit_metric should be called
        """
        svc = _fresh_service(enabled=False)
        svc._metrics_api_ready = True
        with patch.object(svc, "_submit_metric") as mock_submit:
            svc.record_lease_expired()
            mock_submit.assert_called_once_with("leases_expired_total", 1)

    def test_record_lease_revoked_submits_metric(self):
        """
        GIVEN DatadogService with metrics API ready
        WHEN calling record_lease_revoked
        THEN _submit_metric should be called with reason tag
        """
        svc = _fresh_service(enabled=False)
        svc._metrics_api_ready = True
        with patch.object(svc, "_submit_metric") as mock_submit:
            svc.record_lease_revoked("manual")
            mock_submit.assert_called_once_with(
                "leases_revoked_total", 1, tags=["reason:manual"]
            )

    def test_record_node_crash_submits_metric(self):
        """
        GIVEN DatadogService with metrics API ready
        WHEN calling record_node_crash
        THEN _submit_metric should be called
        """
        svc = _fresh_service(enabled=False)
        svc._metrics_api_ready = True
        with patch.object(svc, "_submit_metric") as mock_submit:
            svc.record_node_crash()
            mock_submit.assert_called_once_with("node_crashes_total", 1)

    def test_record_task_requeued_submits_metric(self):
        """
        GIVEN DatadogService with metrics API ready
        WHEN calling record_task_requeued
        THEN _submit_metric should be called with result tag
        """
        svc = _fresh_service(enabled=False)
        svc._metrics_api_ready = True
        with patch.object(svc, "_submit_metric") as mock_submit:
            svc.record_task_requeued("permanently_failed")
            mock_submit.assert_called_once_with(
                "tasks_requeued_total", 1, tags=["result:permanently_failed"]
            )

    def test_record_recovery_duration_submits_gauge(self):
        """
        GIVEN DatadogService with metrics API ready
        WHEN calling record_recovery_duration
        THEN _submit_metric should be called with gauge type
        """
        svc = _fresh_service(enabled=False)
        svc._metrics_api_ready = True
        with patch.object(svc, "_submit_metric") as mock_submit:
            svc.record_recovery_duration("partition_healed", 2.5)
            mock_submit.assert_called_once_with(
                "recovery_duration_seconds",
                2.5,
                metric_type="gauge",
                tags=["type:partition_healed"],
            )

    def test_record_recovery_operation_submits_metric(self):
        """
        GIVEN DatadogService with metrics API ready
        WHEN calling record_recovery_operation
        THEN _submit_metric should be called with type and status tags
        """
        svc = _fresh_service(enabled=False)
        svc._metrics_api_ready = True
        with patch.object(svc, "_submit_metric") as mock_submit:
            svc.record_recovery_operation("node_crash", "success")
            mock_submit.assert_called_once_with(
                "recovery_operations_total",
                1,
                tags=["type:node_crash", "status:success"],
            )

    def test_submit_metric_noop_when_not_ready(self):
        """
        GIVEN DatadogService with metrics API not ready
        WHEN calling _submit_metric
        THEN no HTTP call should be made
        """
        svc = _fresh_service(enabled=False)
        svc._metrics_api_ready = False
        with patch.object(svc, "_post_metric") as mock_post:
            svc._submit_metric("test_metric", 1)
            mock_post.assert_not_called()

    def test_post_metric_sends_http_request(self):
        """
        GIVEN DatadogService with valid API key
        WHEN calling _post_metric
        THEN httpx.post should be called with correct payload
        """
        svc = _fresh_service(enabled=False)
        svc._api_key = "test_key"
        payload = {"series": [{"metric": "agentclaw.test", "type": "count", "points": [[1, 1]], "tags": []}]}

        with patch.object(dd_module._httpx, "post", return_value=MagicMock(status_code=202)) as mock_post:
            svc._post_metric("https://api.datadoghq.com/api/v1/series", payload)
            mock_post.assert_called_once()


class TestDatadogServiceLLMObs:
    """Describe LLMObs span helpers"""

    def test_workflow_span_returns_noop_when_disabled(self):
        """
        GIVEN DatadogService is disabled
        WHEN calling workflow_span
        THEN it should return a NoopContextManager
        """
        svc = _fresh_service(enabled=False)

        with svc.workflow_span("test") as span:
            assert isinstance(span, _NoopContextManager)

    def test_agent_span_returns_noop_when_disabled(self):
        """
        GIVEN DatadogService is disabled
        WHEN calling agent_span
        THEN it should return a NoopContextManager
        """
        svc = _fresh_service(enabled=False)

        with svc.agent_span("test") as span:
            assert isinstance(span, _NoopContextManager)

    def test_tool_span_returns_noop_when_disabled(self):
        """
        GIVEN DatadogService is disabled
        WHEN calling tool_span
        THEN it should return a NoopContextManager
        """
        svc = _fresh_service(enabled=False)

        with svc.tool_span("test") as span:
            assert isinstance(span, _NoopContextManager)

    def test_workflow_span_calls_llmobs_when_enabled(self):
        """
        GIVEN DatadogService with LLMObs available
        WHEN calling workflow_span
        THEN LLMObs.workflow should be called
        """
        svc = _fresh_service(enabled=False)
        svc._llmobs_available = True

        mock_llmobs = MagicMock()
        mock_span = MagicMock()
        mock_llmobs.workflow.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_llmobs.workflow.return_value.__exit__ = MagicMock(return_value=False)

        original_llmobs = dd_module._LLMObs
        try:
            dd_module._LLMObs = mock_llmobs
            with svc.workflow_span("test_workflow") as span:
                assert span is mock_span
            mock_llmobs.workflow.assert_called_once_with("test_workflow")
        finally:
            dd_module._LLMObs = original_llmobs

    def test_agent_span_calls_llmobs_when_enabled(self):
        """
        GIVEN DatadogService with LLMObs available
        WHEN calling agent_span
        THEN LLMObs.agent should be called
        """
        svc = _fresh_service(enabled=False)
        svc._llmobs_available = True

        mock_llmobs = MagicMock()
        mock_span = MagicMock()
        mock_llmobs.agent.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_llmobs.agent.return_value.__exit__ = MagicMock(return_value=False)

        original_llmobs = dd_module._LLMObs
        try:
            dd_module._LLMObs = mock_llmobs
            with svc.agent_span("test_agent") as span:
                assert span is mock_span
            mock_llmobs.agent.assert_called_once_with("test_agent")
        finally:
            dd_module._LLMObs = original_llmobs

    def test_tool_span_calls_llmobs_when_enabled(self):
        """
        GIVEN DatadogService with LLMObs available
        WHEN calling tool_span
        THEN LLMObs.tool should be called
        """
        svc = _fresh_service(enabled=False)
        svc._llmobs_available = True

        mock_llmobs = MagicMock()
        mock_span = MagicMock()
        mock_llmobs.tool.return_value.__enter__ = MagicMock(return_value=mock_span)
        mock_llmobs.tool.return_value.__exit__ = MagicMock(return_value=False)

        original_llmobs = dd_module._LLMObs
        try:
            dd_module._LLMObs = mock_llmobs
            with svc.tool_span("test_tool") as span:
                assert span is mock_span
            mock_llmobs.tool.assert_called_once_with("test_tool")
        finally:
            dd_module._LLMObs = original_llmobs

    def test_annotate_span_noop_when_disabled(self):
        """
        GIVEN DatadogService is disabled
        WHEN calling annotate_span
        THEN no exception should be raised
        """
        svc = _fresh_service(enabled=False)

        svc.annotate_span(input_data="hello", output_data="world")

    def test_annotate_span_calls_llmobs_when_enabled(self):
        """
        GIVEN DatadogService with LLMObs available
        WHEN calling annotate_span
        THEN LLMObs.annotate should be called with input/output data
        """
        svc = _fresh_service(enabled=False)
        svc._llmobs_available = True

        mock_llmobs = MagicMock()
        original_llmobs = dd_module._LLMObs
        try:
            dd_module._LLMObs = mock_llmobs
            svc.annotate_span(input_data="hello", output_data="world")
            mock_llmobs.annotate.assert_called_once_with(
                input_data="hello", output_data="world"
            )
        finally:
            dd_module._LLMObs = original_llmobs

    def test_annotate_span_skips_none_values(self):
        """
        GIVEN DatadogService with LLMObs available
        WHEN calling annotate_span with only input_data
        THEN LLMObs.annotate should only receive input_data
        """
        svc = _fresh_service(enabled=False)
        svc._llmobs_available = True

        mock_llmobs = MagicMock()
        original_llmobs = dd_module._LLMObs
        try:
            dd_module._LLMObs = mock_llmobs
            svc.annotate_span(input_data="hello")
            mock_llmobs.annotate.assert_called_once_with(input_data="hello")
        finally:
            dd_module._LLMObs = original_llmobs

    def test_llmobs_exception_silently_caught_in_span(self):
        """
        GIVEN LLMObs.workflow raises an exception
        WHEN calling workflow_span
        THEN no exception should propagate
        """
        svc = _fresh_service(enabled=False)
        svc._llmobs_available = True

        mock_llmobs = MagicMock()
        mock_llmobs.workflow.side_effect = Exception("LLMObs error")

        original_llmobs = dd_module._LLMObs
        try:
            dd_module._LLMObs = mock_llmobs
            with svc.workflow_span("test") as span:
                assert isinstance(span, _NoopContextManager)
        finally:
            dd_module._LLMObs = original_llmobs


class TestDatadogServiceStatus:
    """Describe get_status()"""

    def test_status_when_disabled(self):
        """
        GIVEN DatadogService is disabled
        WHEN calling get_status
        THEN it should return disabled flags
        """
        svc = _fresh_service(enabled=False)
        status = svc.get_status()

        assert status["enabled"] is False
        assert status["metrics_api_ready"] is False
        assert status["llmobs_available"] is False
        assert "ddtrace_available" in status

    def test_status_when_enabled_with_all_components(self):
        """
        GIVEN DatadogService is enabled with metrics API and LLMObs
        WHEN calling get_status
        THEN it should return all flags as True
        """
        svc = _fresh_service(enabled=False)
        svc._enabled = True
        svc._metrics_api_ready = True
        svc._llmobs_available = True

        status = svc.get_status()

        assert status["enabled"] is True
        assert status["metrics_api_ready"] is True
        assert status["llmobs_available"] is True

    def test_status_returns_dict_with_expected_keys(self):
        """
        GIVEN any DatadogService instance
        WHEN calling get_status
        THEN it should return a dict with all expected keys
        """
        svc = _fresh_service(enabled=False)
        status = svc.get_status()

        expected_keys = {"enabled", "ddtrace_available", "metrics_api_ready", "llmobs_available"}
        assert set(status.keys()) == expected_keys


class TestNoopContextManager:
    """Describe _NoopContextManager"""

    def test_can_be_used_as_context_manager(self):
        """
        GIVEN a _NoopContextManager
        WHEN used in a with statement
        THEN it should enter and exit without error
        """
        noop = _NoopContextManager()
        with noop as ctx:
            assert ctx is noop

    def test_exit_returns_none(self):
        """
        GIVEN a _NoopContextManager
        WHEN __exit__ is called
        THEN it should return None (not suppress exceptions)
        """
        noop = _NoopContextManager()
        result = noop.__exit__(None, None, None)
        assert result is None
