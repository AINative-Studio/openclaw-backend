"""
Datadog Observability Service

Provides custom metrics (via HTTP API) and LLMObs span helpers for the
AgentClaw backend. Fully agentless — sends metrics directly to the
Datadog API without requiring a local Datadog Agent.

Gated on DD_LLMOBS_ENABLED=1 — completely no-op when disabled or when
ddtrace is not installed.

Follows the same singleton + conditional-import pattern as
PrometheusMetricsService (E8-S1).
"""

import logging
import os
import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Conditional imports — service is fully functional without ddtrace installed
DDTRACE_AVAILABLE = False
_LLMObs = None

try:
    from ddtrace import tracer  # noqa: F401
    DDTRACE_AVAILABLE = True
except ImportError:
    pass

try:
    from ddtrace.llmobs import LLMObs as _LLMObs  # noqa: F811
except ImportError:
    pass

_httpx = None
try:
    import httpx as _httpx  # noqa: F811
except ImportError:
    pass

# Singleton
_datadog_service_instance: Optional["DatadogService"] = None
_singleton_lock = threading.Lock()


class _NoopContextManager:
    """No-op context manager returned when Datadog is disabled."""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


class DatadogService:
    """
    Datadog Observability Service

    Provides:
    - HTTP API custom metrics (record_*() methods mirroring Prometheus counters)
    - LLMObs span helpers (workflow_span, agent_span, tool_span)
    - annotate_span() for adding input/output metadata
    - get_status() for health checks

    All methods are fire-and-forget — errors are silently caught so callers
    are never affected by Datadog availability.

    Usage:
        service = get_datadog_service()
        service.record_task_assignment("success")

        with service.workflow_span("command_parse"):
            # ... LLM call ...
            service.annotate_span(input_data="hello", output_data="parsed")
    """

    def __init__(self) -> None:
        self._enabled = (
            os.getenv("DD_LLMOBS_ENABLED", "0") == "1"
            and DDTRACE_AVAILABLE
        )
        self._metrics_api_ready = False
        self._api_key: Optional[str] = None
        self._dd_site: str = "datadoghq.com"
        self._llmobs_available = False
        self._noop = _NoopContextManager()

        if self._enabled:
            self._init_metrics_api()
            self._init_llmobs()

    def _init_metrics_api(self) -> None:
        """Initialize direct HTTP API metrics submission (agentless)."""
        try:
            self._api_key = os.getenv("DD_API_KEY")
            self._dd_site = os.getenv("DD_SITE", "datadoghq.com")
            if self._api_key and _httpx is not None:
                self._metrics_api_ready = True
                logger.info("DatadogService: HTTP API metrics initialized (agentless)")
            else:
                if not self._api_key:
                    logger.warning("DatadogService: DD_API_KEY not set — metrics disabled")
                if _httpx is None:
                    logger.warning("DatadogService: httpx not available — metrics disabled")
        except Exception as e:
            logger.warning(f"DatadogService: Metrics API init failed: {e}")
            self._metrics_api_ready = False

    def _init_llmobs(self) -> None:
        """Initialize LLMObs SDK."""
        try:
            if _LLMObs is not None:
                ml_app = os.getenv("DD_LLMOBS_ML_APP", "agentclaw")
                agentless = os.getenv("DD_LLMOBS_AGENTLESS_ENABLED", "0") == "1"
                _LLMObs.enable(
                    ml_app=ml_app,
                    agentless_enabled=agentless,
                )
                self._llmobs_available = True
                logger.info(
                    f"DatadogService: LLMObs enabled (ml_app={ml_app}, "
                    f"agentless={agentless})"
                )
        except Exception as e:
            logger.warning(f"DatadogService: LLMObs init failed: {e}")
            self._llmobs_available = False

    # ------------------------------------------------------------------
    # Metrics via HTTP API (agentless)
    # ------------------------------------------------------------------

    def _submit_metric(
        self,
        metric: str,
        value: float,
        metric_type: str = "count",
        tags: Optional[List[str]] = None,
    ) -> None:
        """Submit a metric directly to Datadog HTTP API."""
        if not self._metrics_api_ready:
            return
        try:
            now = int(time.time())
            payload = {
                "series": [
                    {
                        "metric": f"agentclaw.{metric}",
                        "type": metric_type,
                        "points": [[now, value]],
                        "tags": tags or [],
                    }
                ]
            }
            url = f"https://api.{self._dd_site}/api/v1/series"
            # Fire-and-forget in a thread to avoid blocking
            threading.Thread(
                target=self._post_metric,
                args=(url, payload),
                daemon=True,
            ).start()
        except Exception:
            pass

    def _post_metric(self, url: str, payload: Dict[str, Any]) -> None:
        """POST metric payload to Datadog (runs in background thread)."""
        try:
            resp = _httpx.post(
                url,
                json=payload,
                headers={
                    "DD-API-KEY": self._api_key,
                    "Content-Type": "application/json",
                },
                timeout=5.0,
            )
            if resp.status_code >= 400:
                logger.debug(f"DatadogService: metric submit failed: {resp.status_code}")
        except Exception:
            pass

    def record_task_assignment(self, status: str) -> None:
        self._submit_metric(
            "task_assignments_total", 1, tags=[f"status:{status}"]
        )

    def record_lease_issued(self, complexity: str) -> None:
        self._submit_metric(
            "leases_issued_total", 1, tags=[f"complexity:{complexity}"]
        )

    def record_lease_expired(self) -> None:
        self._submit_metric("leases_expired_total", 1)

    def record_lease_revoked(self, reason: str) -> None:
        self._submit_metric(
            "leases_revoked_total", 1, tags=[f"reason:{reason}"]
        )

    def record_node_crash(self) -> None:
        self._submit_metric("node_crashes_total", 1)

    def record_task_requeued(self, result: str) -> None:
        self._submit_metric(
            "tasks_requeued_total", 1, tags=[f"result:{result}"]
        )

    def record_recovery_duration(
        self, recovery_type: str, duration_seconds: float
    ) -> None:
        self._submit_metric(
            "recovery_duration_seconds",
            duration_seconds,
            metric_type="gauge",
            tags=[f"type:{recovery_type}"],
        )

    def record_recovery_operation(
        self, recovery_type: str, status: str
    ) -> None:
        self._submit_metric(
            "recovery_operations_total",
            1,
            tags=[f"type:{recovery_type}", f"status:{status}"],
        )

    # ------------------------------------------------------------------
    # LLMObs Span Helpers
    # ------------------------------------------------------------------

    @contextmanager
    def workflow_span(self, name: str):
        """Create an LLMObs workflow span context manager."""
        if not self._llmobs_available or _LLMObs is None:
            yield self._noop
            return
        try:
            with _LLMObs.workflow(name) as span:
                yield span
        except Exception:
            yield self._noop

    @contextmanager
    def agent_span(self, name: str):
        """Create an LLMObs agent span context manager."""
        if not self._llmobs_available or _LLMObs is None:
            yield self._noop
            return
        try:
            with _LLMObs.agent(name) as span:
                yield span
        except Exception:
            yield self._noop

    @contextmanager
    def tool_span(self, name: str):
        """Create an LLMObs tool span context manager."""
        if not self._llmobs_available or _LLMObs is None:
            yield self._noop
            return
        try:
            with _LLMObs.tool(name) as span:
                yield span
        except Exception:
            yield self._noop

    def annotate_span(
        self,
        input_data: Optional[str] = None,
        output_data: Optional[str] = None,
    ) -> None:
        """Annotate the current active LLMObs span with input/output data."""
        if not self._llmobs_available or _LLMObs is None:
            return
        try:
            kwargs: Dict[str, Any] = {}
            if input_data is not None:
                kwargs["input_data"] = input_data
            if output_data is not None:
                kwargs["output_data"] = output_data
            if kwargs:
                _LLMObs.annotate(**kwargs)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return Datadog service health status."""
        return {
            "enabled": self._enabled,
            "ddtrace_available": DDTRACE_AVAILABLE,
            "metrics_api_ready": self._metrics_api_ready,
            "llmobs_available": self._llmobs_available,
        }


def get_datadog_service() -> DatadogService:
    """Return the singleton DatadogService instance."""
    global _datadog_service_instance
    if _datadog_service_instance is None:
        with _singleton_lock:
            if _datadog_service_instance is None:
                _datadog_service_instance = DatadogService()
    return _datadog_service_instance
