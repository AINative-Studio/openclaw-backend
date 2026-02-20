"""
Alert Threshold Configuration Service

Provides runtime-configurable alert thresholds for swarm health status
derivation. Replaces hardcoded threshold values in SwarmHealthService
with an externally adjustable configuration.

Default values exactly match the original hardcoded thresholds:
- buffer_utilization: 80.0%
- crash_count: 3
- revocation_rate: 50.0%
- ip_pool_utilization: 90.0%

Epic E8-S4: Alert Threshold Configuration
Refs: #52
"""

import logging
import threading
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Singleton instance
_alert_threshold_service_instance: Optional["AlertThresholdService"] = None
_singleton_lock = threading.Lock()

# Fields that callers are allowed to update
_ALLOWED_FIELDS = frozenset({
    "buffer_utilization",
    "crash_count",
    "revocation_rate",
    "ip_pool_utilization",
})


class AlertThresholdConfig(BaseModel):
    """
    Validated alert threshold configuration.

    All defaults match the original hardcoded values in
    SwarmHealthService._derive_health_status() so deployment
    is zero-behavioral-change.
    """

    buffer_utilization: float = Field(
        default=80.0, ge=0.0, le=100.0,
        description="Buffer utilization % above which status is degraded",
    )
    crash_count: int = Field(
        default=3, ge=0,
        description="Recent crash count at or above which status is degraded",
    )
    revocation_rate: float = Field(
        default=50.0, ge=0.0, le=100.0,
        description="Revocation rate % above which status is degraded",
    )
    ip_pool_utilization: float = Field(
        default=90.0, ge=0.0, le=100.0,
        description="IP pool utilization % above which status is degraded",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp of last configuration change",
    )


class AlertThresholdService:
    """
    In-memory alert threshold configuration service.

    Thread-safe singleton that stores and serves configurable
    alert thresholds for the swarm health derivation logic.

    Usage:
        service = get_alert_threshold_service()
        thresholds = service.get_thresholds()
        service.update_thresholds({"buffer_utilization": 95.0})
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._config = AlertThresholdConfig()

    def get_thresholds(self) -> AlertThresholdConfig:
        """
        Return a copy of the current threshold configuration.

        Returns a model_copy() to prevent callers from mutating
        internal state.
        """
        with self._lock:
            return self._config.model_copy()

    def update_thresholds(self, updates: Dict[str, Any]) -> AlertThresholdConfig:
        """
        Partially update threshold configuration.

        Only the 4 threshold fields are accepted. Unknown fields and
        updated_at overrides are silently filtered out. Invalid values
        raise ValueError via Pydantic validation.

        Args:
            updates: Dict of field names to new values

        Returns:
            Updated AlertThresholdConfig copy

        Raises:
            ValueError: If any value fails Pydantic validation
        """
        filtered = {
            k: v for k, v in updates.items()
            if k in _ALLOWED_FIELDS
        }

        with self._lock:
            current_data = self._config.model_dump()
            current_data.update(filtered)
            current_data["updated_at"] = datetime.now(timezone.utc)

            try:
                self._config = AlertThresholdConfig(**current_data)
            except Exception as e:
                raise ValueError(str(e)) from e

            return self._config.model_copy()

    def reset_to_defaults(self) -> AlertThresholdConfig:
        """
        Reset all thresholds to their original default values.

        Useful for test isolation and operational recovery.

        Returns:
            Fresh default AlertThresholdConfig copy
        """
        with self._lock:
            self._config = AlertThresholdConfig()
            return self._config.model_copy()


def get_alert_threshold_service() -> AlertThresholdService:
    """
    Get the singleton AlertThresholdService instance.

    Uses double-checked locking for thread safety.

    Returns:
        The shared AlertThresholdService instance
    """
    global _alert_threshold_service_instance
    if _alert_threshold_service_instance is None:
        with _singleton_lock:
            if _alert_threshold_service_instance is None:
                _alert_threshold_service_instance = AlertThresholdService()
    return _alert_threshold_service_instance
