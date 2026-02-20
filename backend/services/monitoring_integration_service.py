"""
MonitoringIntegrationService (E8-S5).

Unified facade wrapping PrometheusMetricsService, TaskTimelineService,
and SwarmHealthService into a single fire-and-forget API for the
Agent Swarm Monitor dashboard.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Lazy imports — resolved in _initialize_services()
try:
    from backend.services.prometheus_metrics_service import (
        PrometheusMetricsService,
        get_metrics_service,
    )
except (ImportError, ModuleNotFoundError):
    PrometheusMetricsService = None  # type: ignore[assignment,misc]
    get_metrics_service = None  # type: ignore[assignment]

try:
    from backend.services.task_timeline_service import (
        TaskTimelineService,
        TimelineEventType,
        get_timeline_service,
    )
except (ImportError, ModuleNotFoundError):
    TaskTimelineService = None  # type: ignore[assignment,misc]
    TimelineEventType = None  # type: ignore[assignment]
    get_timeline_service = None  # type: ignore[assignment]

try:
    from backend.services.swarm_health_service import (
        SwarmHealthService,
        get_swarm_health_service,
    )
except (ImportError, ModuleNotFoundError):
    SwarmHealthService = None  # type: ignore[assignment,misc]
    get_swarm_health_service = None  # type: ignore[assignment]

try:
    from backend.services.datadog_service import get_datadog_service
except (ImportError, ModuleNotFoundError):
    get_datadog_service = None  # type: ignore[assignment]


class MonitoringIntegrationService:
    """Unified facade combining all monitoring subsystems."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._bootstrapped = False
        self._metrics_service: Optional[Any] = None
        self._timeline_service: Optional[Any] = None
        self._health_service: Optional[Any] = None
        self._datadog_service: Optional[Any] = None
        self._event_types: Optional[Any] = None
        self._initialize_services()

    def _initialize_services(self) -> None:
        """Import and cache references to monitoring singletons."""
        try:
            if get_metrics_service is not None:
                self._metrics_service = get_metrics_service()
            else:
                raise ImportError("get_metrics_service not available")
        except Exception as e:
            logger.warning(f"PrometheusMetricsService unavailable: {e}")
            self._metrics_service = None

        try:
            if get_timeline_service is not None:
                self._timeline_service = get_timeline_service()
            else:
                raise ImportError("get_timeline_service not available")
        except Exception as e:
            logger.warning(f"TaskTimelineService unavailable: {e}")
            self._timeline_service = None

        try:
            if get_swarm_health_service is not None:
                self._health_service = get_swarm_health_service()
            else:
                raise ImportError("get_swarm_health_service not available")
        except Exception as e:
            logger.warning(f"SwarmHealthService unavailable: {e}")
            self._health_service = None

        try:
            if get_datadog_service is not None:
                self._datadog_service = get_datadog_service()
            else:
                raise ImportError("get_datadog_service not available")
        except Exception as e:
            logger.warning(f"DatadogService unavailable: {e}")
            self._datadog_service = None

        self._event_types = TimelineEventType

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap(self, services: Dict[str, Any]) -> Dict[str, bool]:
        """Register subsystem services with health and metrics monitors.

        Args:
            services: Dict mapping subsystem names to service instances.

        Returns:
            Dict of {name: success_bool} for each registration.
        """
        results: Dict[str, bool] = {}
        for name, svc in services.items():
            success = True
            try:
                if self._health_service is not None:
                    self._health_service.register_service(name, svc)
            except Exception as e:
                logger.warning(f"Failed to register {name} with health: {e}")
                success = False

            try:
                if self._metrics_service is not None:
                    self._metrics_service.register_service(name, svc)
            except Exception as e:
                logger.warning(f"Failed to register {name} with metrics: {e}")
                success = False

            results[name] = success

        self._bootstrapped = True
        return results

    # ------------------------------------------------------------------
    # Timeline-only facade methods
    # ------------------------------------------------------------------

    def on_task_created(
        self,
        task_id: str,
        peer_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.TASK_CREATED,
                    task_id=task_id,
                    peer_id=peer_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_task_created: {e}")

    def on_task_queued(
        self,
        task_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.TASK_QUEUED,
                    task_id=task_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_task_queued: {e}")

    def on_task_started(
        self,
        task_id: str,
        peer_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.TASK_STARTED,
                    task_id=task_id,
                    peer_id=peer_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_task_started: {e}")

    def on_task_progress(
        self,
        task_id: str,
        peer_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.TASK_PROGRESS,
                    task_id=task_id,
                    peer_id=peer_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_task_progress: {e}")

    def on_task_completed(
        self,
        task_id: str,
        peer_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.TASK_COMPLETED,
                    task_id=task_id,
                    peer_id=peer_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_task_completed: {e}")

    def on_task_failed(
        self,
        task_id: str,
        peer_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.TASK_FAILED,
                    task_id=task_id,
                    peer_id=peer_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_task_failed: {e}")

    def on_task_expired(
        self,
        task_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.TASK_EXPIRED,
                    task_id=task_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_task_expired: {e}")

    # ------------------------------------------------------------------
    # Combined facade methods (timeline + metrics)
    # ------------------------------------------------------------------

    def on_task_leased(
        self,
        task_id: str,
        peer_id: str,
        complexity: str = "medium",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.TASK_LEASED,
                    task_id=task_id,
                    peer_id=peer_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_task_leased: {e}")

        try:
            if self._metrics_service is not None:
                self._metrics_service.record_lease_issued(complexity)
        except Exception as e:
            logger.debug(f"Metrics error in on_task_leased: {e}")

        try:
            if self._datadog_service is not None:
                self._datadog_service.record_lease_issued(complexity)
        except Exception as e:
            logger.debug(f"Datadog error in on_task_leased: {e}")

    def on_task_requeued(
        self,
        task_id: str,
        result: str = "success",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.TASK_REQUEUED,
                    task_id=task_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_task_requeued: {e}")

        try:
            if self._metrics_service is not None:
                self._metrics_service.record_task_requeued(result)
        except Exception as e:
            logger.debug(f"Metrics error in on_task_requeued: {e}")

        try:
            if self._datadog_service is not None:
                self._datadog_service.record_task_requeued(result)
        except Exception as e:
            logger.debug(f"Datadog error in on_task_requeued: {e}")

    def on_lease_expired(
        self,
        task_id: str,
        peer_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.LEASE_EXPIRED,
                    task_id=task_id,
                    peer_id=peer_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_lease_expired: {e}")

        try:
            if self._metrics_service is not None:
                self._metrics_service.record_lease_expired()
        except Exception as e:
            logger.debug(f"Metrics error in on_lease_expired: {e}")

        try:
            if self._datadog_service is not None:
                self._datadog_service.record_lease_expired()
        except Exception as e:
            logger.debug(f"Datadog error in on_lease_expired: {e}")

    def on_lease_revoked(
        self,
        task_id: str,
        peer_id: Optional[str] = None,
        reason: str = "manual",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.LEASE_REVOKED,
                    task_id=task_id,
                    peer_id=peer_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_lease_revoked: {e}")

        try:
            if self._metrics_service is not None:
                self._metrics_service.record_lease_revoked(reason)
        except Exception as e:
            logger.debug(f"Metrics error in on_lease_revoked: {e}")

        try:
            if self._datadog_service is not None:
                self._datadog_service.record_lease_revoked(reason)
        except Exception as e:
            logger.debug(f"Datadog error in on_lease_revoked: {e}")

    def on_node_crashed(
        self,
        peer_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            if self._timeline_service is not None:
                self._timeline_service.record_event(
                    event_type=self._event_types.NODE_CRASHED,
                    peer_id=peer_id,
                    metadata=metadata or {},
                )
        except Exception as e:
            logger.debug(f"Timeline error in on_node_crashed: {e}")

        try:
            if self._metrics_service is not None:
                self._metrics_service.record_node_crash()
        except Exception as e:
            logger.debug(f"Metrics error in on_node_crashed: {e}")

        try:
            if self._datadog_service is not None:
                self._datadog_service.record_node_crash()
        except Exception as e:
            logger.debug(f"Datadog error in on_node_crashed: {e}")

    # ------------------------------------------------------------------
    # Metrics-only facade methods
    # ------------------------------------------------------------------

    def on_task_assigned(
        self,
        task_id: str,
        peer_id: str,
        status: str = "success",
    ) -> None:
        try:
            if self._metrics_service is not None:
                self._metrics_service.record_task_assignment(status)
        except Exception as e:
            logger.debug(f"Metrics error in on_task_assigned: {e}")

        try:
            if self._datadog_service is not None:
                self._datadog_service.record_task_assignment(status)
        except Exception as e:
            logger.debug(f"Datadog error in on_task_assigned: {e}")

    def on_partition_event(self, event_type: str) -> None:
        try:
            if self._metrics_service is not None:
                self._metrics_service.record_partition_event(event_type)
        except Exception as e:
            logger.debug(f"Metrics error in on_partition_event: {e}")

    def on_result_buffered(self, task_id: Optional[str] = None) -> None:
        try:
            if self._metrics_service is not None:
                self._metrics_service.record_result_buffered()
        except Exception as e:
            logger.debug(f"Metrics error in on_result_buffered: {e}")

    def on_result_flushed(
        self,
        task_id: Optional[str] = None,
        result: str = "success",
    ) -> None:
        try:
            if self._metrics_service is not None:
                self._metrics_service.record_result_flushed(result)
        except Exception as e:
            logger.debug(f"Metrics error in on_result_flushed: {e}")

    def on_recovery_completed(
        self,
        recovery_type: str,
        status: str,
        duration_seconds: Optional[float] = None,
    ) -> None:
        try:
            if self._metrics_service is not None:
                self._metrics_service.record_recovery_operation(
                    recovery_type, status
                )
        except Exception as e:
            logger.debug(f"Metrics error in on_recovery_completed (op): {e}")

        try:
            if self._metrics_service is not None and duration_seconds is not None:
                self._metrics_service.observe_recovery_duration(
                    recovery_type, duration_seconds
                )
        except Exception as e:
            logger.debug(
                f"Metrics error in on_recovery_completed (duration): {e}"
            )

        try:
            if self._datadog_service is not None:
                self._datadog_service.record_recovery_operation(
                    recovery_type, status
                )
                if duration_seconds is not None:
                    self._datadog_service.record_recovery_duration(
                        recovery_type, duration_seconds
                    )
        except Exception as e:
            logger.debug(f"Datadog error in on_recovery_completed: {e}")

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Any]:
        """Return monitoring infrastructure health status."""
        metrics_available = self._metrics_service is not None
        timeline_available = self._timeline_service is not None
        health_available = self._health_service is not None
        datadog_available = self._datadog_service is not None

        available_count = sum(
            [metrics_available, timeline_available, health_available]
        )

        if available_count == 3:
            status = "operational"
        elif available_count > 0:
            status = "partial"
        else:
            status = "unavailable"

        timeline_event_count = 0
        if self._timeline_service is not None:
            try:
                timeline_event_count = self._timeline_service.get_event_count()
            except Exception:
                pass

        registered_count = 0
        if self._health_service is not None:
            try:
                registered_count = len(
                    self._health_service._registered_services
                )
            except Exception:
                pass

        return {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subsystems": {
                "metrics": {"available": metrics_available},
                "timeline": {"available": timeline_available},
                "health": {"available": health_available},
                "datadog": {"available": datadog_available},
            },
            "registered_health_subsystems": registered_count,
            "timeline_event_count": timeline_event_count,
            "bootstrapped": self._bootstrapped,
        }


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_monitoring_integration_instance: Optional[MonitoringIntegrationService] = None
_singleton_lock = threading.Lock()


def get_monitoring_integration_service() -> MonitoringIntegrationService:
    """Return the singleton MonitoringIntegrationService instance."""
    global _monitoring_integration_instance
    if _monitoring_integration_instance is None:
        with _singleton_lock:
            if _monitoring_integration_instance is None:
                _monitoring_integration_instance = (
                    MonitoringIntegrationService()
                )
    return _monitoring_integration_instance
