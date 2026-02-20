"""
Prometheus Metrics Service

Provides a centralized metrics registry for instrumenting the OpenClaw backend.
Exposes counters, gauges, histograms, and info metrics in standard Prometheus
text format via generate_metrics().

Services can push counter/histogram observations via record_*() methods.
Gauges are pulled from registered services via collect_service_stats().

Epic E8-S1: Prometheus Metrics Exporter
Refs: #49
"""

import logging
import platform
import threading
from typing import Any, Dict, Optional

from prometheus_client import (
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    Info,
    generate_latest,
)

logger = logging.getLogger(__name__)

# Singleton instance
_metrics_service_instance: Optional["PrometheusMetricsService"] = None
_singleton_lock = threading.Lock()


class PrometheusMetricsService:
    """
    Prometheus Metrics Service

    Central registry for all OpenClaw metrics. Provides:
    - record_*() methods for counters (push model, fire-and-forget)
    - observe_*() methods for histograms
    - collect_service_stats() for gauges (pull model from registered services)
    - generate_metrics() for Prometheus text format output

    Usage:
        service = get_metrics_service()
        service.record_task_assignment("success")
        service.record_node_crash()
        output = service.generate_metrics()
    """

    def __init__(
        self,
        namespace: str = "openclaw",
        registry: Optional[CollectorRegistry] = None,
    ):
        self._namespace = namespace
        self._registry = registry or CollectorRegistry(auto_describe=True)
        self._lock = threading.Lock()
        self._registered_services: Dict[str, Any] = {}

        self._define_metrics()

    def _define_metrics(self) -> None:
        """Define all Prometheus metrics on the registry."""
        ns = self._namespace
        reg = self._registry

        # ── Counters ──

        self._task_assignments_total = Counter(
            f"{ns}_task_assignments_total",
            "Total task assignments",
            ["status"],
            registry=reg,
        )

        self._leases_issued_total = Counter(
            f"{ns}_leases_issued_total",
            "Total leases issued",
            ["complexity"],
            registry=reg,
        )

        self._leases_expired_total = Counter(
            f"{ns}_leases_expired_total",
            "Total leases expired",
            registry=reg,
        )

        self._leases_revoked_total = Counter(
            f"{ns}_leases_revoked_total",
            "Total leases revoked",
            ["reason"],
            registry=reg,
        )

        self._node_crashes_total = Counter(
            f"{ns}_node_crashes_total",
            "Total node crash events detected",
            registry=reg,
        )

        self._tasks_requeued_total = Counter(
            f"{ns}_tasks_requeued_total",
            "Total tasks requeued",
            ["result"],
            registry=reg,
        )

        self._partition_events_total = Counter(
            f"{ns}_partition_events_total",
            "Total partition events",
            ["type"],
            registry=reg,
        )

        self._results_buffered_total = Counter(
            f"{ns}_results_buffered_total",
            "Total results buffered during partition",
            registry=reg,
        )

        self._results_flushed_total = Counter(
            f"{ns}_results_flushed_total",
            "Total results flushed from buffer",
            ["result"],
            registry=reg,
        )

        self._capability_validations_total = Counter(
            f"{ns}_capability_validations_total",
            "Total capability validations performed",
            ["result"],
            registry=reg,
        )

        self._tokens_issued_total = Counter(
            f"{ns}_tokens_issued_total",
            "Total capability tokens issued",
            registry=reg,
        )

        self._tokens_revoked_total = Counter(
            f"{ns}_tokens_revoked_total",
            "Total capability tokens revoked",
            ["reason"],
            registry=reg,
        )

        self._audit_events_total = Counter(
            f"{ns}_audit_events_total",
            "Total security audit events logged",
            ["type"],
            registry=reg,
        )

        self._messages_verified_total = Counter(
            f"{ns}_messages_verified_total",
            "Total messages verified",
            ["result"],
            registry=reg,
        )

        self._recovery_operations_total = Counter(
            f"{ns}_recovery_operations_total",
            "Total recovery operations",
            ["type", "status"],
            registry=reg,
        )

        # ── Gauges ──

        self._active_leases = Gauge(
            f"{ns}_active_leases",
            "Current number of active leases",
            registry=reg,
        )

        self._buffer_size = Gauge(
            f"{ns}_buffer_size",
            "Current result buffer size",
            registry=reg,
        )

        self._buffer_utilization_percent = Gauge(
            f"{ns}_buffer_utilization_percent",
            "Current result buffer utilization percentage",
            registry=reg,
        )

        self._partition_degraded = Gauge(
            f"{ns}_partition_degraded",
            "Whether the system is in degraded partition mode (0 or 1)",
            registry=reg,
        )

        # ── Histograms ──

        self._recovery_duration_seconds = Histogram(
            f"{ns}_recovery_duration_seconds",
            "Duration of recovery operations in seconds",
            ["type"],
            registry=reg,
        )

        # ── Info ──

        self._build_info = Info(
            f"{ns}_build",
            "Build information",
            registry=reg,
        )
        self._build_info.info({
            "version": "0.1.0",
            "python_version": platform.python_version(),
        })

    # ── Service Registration (Pull Model for Gauges) ──

    def register_service(self, name: str, service: Any) -> None:
        """
        Register a service for gauge stat collection.

        Args:
            name: Service identifier (e.g. "lease_expiration", "result_buffer")
            service: Service instance with get_*_stats() methods
        """
        with self._lock:
            self._registered_services[name] = service

    def collect_service_stats(self) -> None:
        """
        Pull latest gauge values from registered services.

        Calls get_*_stats() / get_*_statistics() on registered services
        and updates gauge metrics. Errors in one service do not affect others.
        """
        with self._lock:
            services = dict(self._registered_services)

        # Lease stats
        lease_service = services.get("lease_expiration")
        if lease_service:
            try:
                stats = lease_service.get_expiration_stats()
                self._active_leases.set(stats.get("active_leases", 0))
            except Exception as e:
                logger.warning(f"Failed to collect lease stats: {e}")

        # Buffer stats
        buffer_service = services.get("result_buffer")
        if buffer_service:
            try:
                metrics = buffer_service.get_buffer_metrics()
                self._buffer_size.set(metrics.current_size)
                self._buffer_utilization_percent.set(metrics.utilization_percent)
            except Exception as e:
                logger.warning(f"Failed to collect buffer stats: {e}")

        # Partition stats
        partition_service = services.get("partition_detection")
        if partition_service:
            try:
                stats = partition_service.get_partition_statistics()
                is_degraded = 1.0 if stats.get("current_state") == "degraded" else 0.0
                self._partition_degraded.set(is_degraded)
            except Exception as e:
                logger.warning(f"Failed to collect partition stats: {e}")

    # ── Counter Record Methods (Push Model) ──

    def record_task_assignment(self, status: str) -> None:
        """Record a task assignment event. status: success/failed/no_capable_nodes"""
        self._task_assignments_total.labels(status=status).inc()

    def record_lease_issued(self, complexity: str) -> None:
        """Record a lease issuance. complexity: low/medium/high"""
        self._leases_issued_total.labels(complexity=complexity).inc()

    def record_lease_expired(self) -> None:
        """Record a lease expiration."""
        self._leases_expired_total.inc()

    def record_lease_revoked(self, reason: str) -> None:
        """Record a lease revocation. reason: crash/manual/expired"""
        self._leases_revoked_total.labels(reason=reason).inc()

    def record_node_crash(self) -> None:
        """Record a node crash detection."""
        self._node_crashes_total.inc()

    def record_task_requeued(self, result: str) -> None:
        """Record a task requeue. result: success/permanently_failed"""
        self._tasks_requeued_total.labels(result=result).inc()

    def record_partition_event(self, event_type: str) -> None:
        """Record a partition event. type: detected/recovered"""
        self._partition_events_total.labels(type=event_type).inc()

    def record_result_buffered(self) -> None:
        """Record a result being buffered during partition."""
        self._results_buffered_total.inc()

    def record_result_flushed(self, result: str) -> None:
        """Record a result flush. result: success/failed"""
        self._results_flushed_total.labels(result=result).inc()

    def record_capability_validation(self, result: str) -> None:
        """Record a capability validation. result: valid/capability_missing/resource_exceeded/scope_violation"""
        self._capability_validations_total.labels(result=result).inc()

    def record_token_issued(self) -> None:
        """Record a capability token issuance."""
        self._tokens_issued_total.inc()

    def record_token_revoked(self, reason: str) -> None:
        """Record a token revocation. reason: rotation/compromise/manual"""
        self._tokens_revoked_total.labels(reason=reason).inc()

    def record_audit_event(self, event_type: str) -> None:
        """Record a security audit event. event_type: one of AuditEventType values"""
        self._audit_events_total.labels(type=event_type).inc()

    def record_message_verified(self, result: str) -> None:
        """Record a message verification. result: success/failed"""
        self._messages_verified_total.labels(result=result).inc()

    def record_recovery_operation(self, recovery_type: str, status: str) -> None:
        """Record a recovery operation. type: node_crash/partition_healed etc. status: success/failed"""
        self._recovery_operations_total.labels(type=recovery_type, status=status).inc()

    # ── Histogram Observation Methods ──

    def observe_recovery_duration(self, recovery_type: str, duration_seconds: float) -> None:
        """Observe recovery duration. type: node_crash/partition_healed etc."""
        self._recovery_duration_seconds.labels(type=recovery_type).observe(duration_seconds)

    # ── Output ──

    def generate_metrics(self) -> str:
        """
        Generate Prometheus text format metrics output.

        Returns:
            Prometheus exposition format string
        """
        return generate_latest(self._registry).decode("utf-8")


def get_metrics_service() -> PrometheusMetricsService:
    """
    Get the singleton PrometheusMetricsService instance.

    Returns:
        The shared PrometheusMetricsService instance
    """
    global _metrics_service_instance
    if _metrics_service_instance is None:
        with _singleton_lock:
            if _metrics_service_instance is None:
                _metrics_service_instance = PrometheusMetricsService()
    return _metrics_service_instance
