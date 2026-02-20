"""
Swarm Health Service

Aggregation service that collects stats from all registered subsystems
and derives an overall swarm health status for the dashboard API.

Each subsystem exposes a get_*_stats() method returning a plain dict.
This service collects all of them, handles errors gracefully, and
derives an overall health status (healthy/degraded/unhealthy).

Epic E8-S2: Swarm Health Dashboard Data API
Refs: #50
"""

import asyncio
import inspect
import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

from backend.services.alert_threshold_service import get_alert_threshold_service

logger = logging.getLogger(__name__)

# Singleton instance
_swarm_health_service_instance: Optional["SwarmHealthService"] = None
_singleton_lock = threading.Lock()

# Subsystems whose stats methods are async and require await
ASYNC_SUBSYSTEMS: Set[str] = {"result_buffer", "lease_revocation"}

# Mapping from subsystem name to its stats method name
SUBSYSTEM_METHODS: Dict[str, str] = {
    "lease_expiration": "get_expiration_stats",
    "result_buffer": "get_buffer_metrics",
    "partition_detection": "get_partition_statistics",
    "node_crash_detection": "get_crash_statistics",
    "lease_revocation": "get_revocation_stats",
    "duplicate_prevention": "get_duplicate_statistics",
    "ip_pool": "get_pool_stats",
    "message_verification": "get_cache_stats",
}


class SwarmHealthService:
    """
    Swarm Health Aggregation Service

    Collects stats from all registered subsystems and derives an overall
    health status for the agent swarm monitoring dashboard.

    Usage:
        service = get_swarm_health_service()
        service.register_service("lease_expiration", lease_service)
        snapshot = await service.collect_health_snapshot()
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._registered_services: Dict[str, Any] = {}

    def register_service(self, name: str, service: Any) -> None:
        """
        Register a service for health stat collection.

        Args:
            name: Subsystem identifier (e.g. "lease_expiration", "result_buffer")
            service: Service instance with the appropriate get_*_stats() method
        """
        with self._lock:
            self._registered_services[name] = service

    def unregister_service(self, name: str) -> None:
        """
        Remove a service from the health registry.

        Args:
            name: Subsystem identifier to remove
        """
        with self._lock:
            self._registered_services.pop(name, None)

    async def collect_health_snapshot(self) -> Dict[str, Any]:
        """
        Collect a full health snapshot from all registered subsystems.

        Returns:
            Dict containing overall status, timestamp, subsystem counts,
            and per-subsystem stats with availability flags.
        """
        with self._lock:
            services = dict(self._registered_services)

        results: Dict[str, Dict[str, Any]] = {}
        available_count = 0

        for name, service in services.items():
            subsystem_result = await self._collect_subsystem_stats(name, service)
            results[name] = subsystem_result
            if subsystem_result.get("available", False):
                available_count += 1

        total = len(services)
        status = self._derive_health_status(results, available_count)

        snapshot: Dict[str, Any] = {
            "status": status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subsystems_available": available_count,
            "subsystems_total": total,
        }

        # Add each subsystem's results
        for name in SUBSYSTEM_METHODS:
            snapshot[name] = results.get(name)

        return snapshot

    async def _collect_subsystem_stats(
        self, name: str, service: Any
    ) -> Dict[str, Any]:
        """
        Collect stats from a single subsystem, handling errors gracefully.

        Args:
            name: Subsystem identifier
            service: Service instance

        Returns:
            Dict with available flag, optional error, and stats data
        """
        method_name = SUBSYSTEM_METHODS.get(name)
        if not method_name:
            return {"available": False, "error": f"Unknown subsystem: {name}"}

        method = getattr(service, method_name, None)
        if method is None:
            return {
                "available": False,
                "error": f"Method {method_name} not found on service",
            }

        try:
            if name in ASYNC_SUBSYSTEMS:
                stats = await method()
            else:
                stats = method()

            result = {"available": True}
            result.update(stats)
            return result
        except Exception as e:
            logger.warning(f"Failed to collect stats from {name}: {e}")
            return {"available": False, "error": str(e)}

    def _derive_health_status(
        self, results: Dict[str, Dict[str, Any]], available_count: int
    ) -> str:
        """
        Derive overall health status from subsystem results.

        Rules (evaluated in order):
        1. partition_detection.current_state == "degraded" -> UNHEALTHY
        2. available_count == 0 -> UNHEALTHY
        3. available_count < total registered -> DEGRADED
        4. Domain thresholds exceeded -> DEGRADED:
           - result_buffer.utilization_percent > 80
           - node_crash_detection.recent_crashes >= 3
           - lease_revocation.revocation_rate > 50.0
           - ip_pool.utilization_percent > 90
        5. Otherwise -> HEALTHY

        Args:
            results: Per-subsystem stat dicts
            available_count: Number of subsystems that responded

        Returns:
            Health status string: "healthy", "degraded", or "unhealthy"
        """
        # Rule 1: Active DBOS partition
        partition = results.get("partition_detection", {})
        if (
            partition.get("available")
            and partition.get("current_state") == "degraded"
        ):
            return "unhealthy"

        # Rule 2: Nothing responding
        if available_count == 0:
            return "unhealthy"

        # Rule 3: Some subsystems down
        total = len(results)
        if available_count < total:
            return "degraded"

        # Rule 4: Domain thresholds (configurable via AlertThresholdService)
        thresholds = get_alert_threshold_service().get_thresholds()

        buffer = results.get("result_buffer", {})
        if buffer.get("available") and buffer.get("utilization_percent", 0) > thresholds.buffer_utilization:
            return "degraded"

        crash = results.get("node_crash_detection", {})
        if crash.get("available") and crash.get("recent_crashes", 0) >= thresholds.crash_count:
            return "degraded"

        revocation = results.get("lease_revocation", {})
        if (
            revocation.get("available")
            and revocation.get("revocation_rate", 0) > thresholds.revocation_rate
        ):
            return "degraded"

        ip_pool = results.get("ip_pool", {})
        if ip_pool.get("available") and ip_pool.get("utilization_percent", 0) > thresholds.ip_pool_utilization:
            return "degraded"

        # Rule 5: Everything looks good
        return "healthy"


def get_swarm_health_service() -> SwarmHealthService:
    """
    Get the singleton SwarmHealthService instance.

    Returns:
        The shared SwarmHealthService instance
    """
    global _swarm_health_service_instance
    if _swarm_health_service_instance is None:
        with _singleton_lock:
            if _swarm_health_service_instance is None:
                _swarm_health_service_instance = SwarmHealthService()
    return _swarm_health_service_instance
