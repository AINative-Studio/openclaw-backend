"""
Swarm Health Dashboard API Endpoint

Provides a unified JSON health snapshot of all backend subsystems
for the agent-swarm-monitor Next.js dashboard.

Complementary to E8-S1's /metrics endpoint (Prometheus text format).
This endpoint returns structured JSON for dashboard charts and panels.

Epic E8-S2: Swarm Health Dashboard Data API
Refs: #50
"""

import logging
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)

try:
    from backend.services.swarm_health_service import (
        SwarmHealthService,
        get_swarm_health_service,
    )
    SWARM_HEALTH_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Swarm health service not available: {e}")
    SWARM_HEALTH_AVAILABLE = False

router = APIRouter(prefix="/swarm", tags=["Swarm", "Monitoring", "Dashboard"])


# ============================================================================
# Response Models
# ============================================================================

class SubsystemStatus(BaseModel):
    """Base status for any subsystem"""
    available: bool = Field(..., description="Whether the subsystem responded")
    error: Optional[str] = Field(None, description="Error message if unavailable")


class LeaseExpirationStats(SubsystemStatus):
    """Lease expiration subsystem stats"""
    model_config = ConfigDict(extra="allow")

    active_leases: Optional[int] = Field(None, description="Current active leases")
    upcoming_expirations: Optional[int] = Field(None, description="Leases expiring soon")
    scan_interval: Optional[int] = Field(None, description="Scan interval in seconds")
    grace_period: Optional[int] = Field(None, description="Grace period in seconds")


class ResultBufferStats(SubsystemStatus):
    """Result buffer subsystem stats"""
    model_config = ConfigDict(extra="allow")

    current_size: Optional[int] = Field(None, description="Current buffer size")
    max_capacity: Optional[int] = Field(None, description="Maximum buffer capacity")
    utilization_percent: Optional[float] = Field(None, description="Buffer utilization %")
    oldest_result_age_seconds: Optional[float] = Field(None, description="Age of oldest buffered result")
    newest_result_age_seconds: Optional[float] = Field(None, description="Age of newest buffered result")


class PartitionDetectionStats(SubsystemStatus):
    """Partition detection subsystem stats"""
    model_config = ConfigDict(extra="allow")

    total_partitions: Optional[int] = Field(None, description="Total partition events")
    total_recoveries: Optional[int] = Field(None, description="Total recovery events")
    total_partition_duration_seconds: Optional[float] = Field(None, description="Total partition duration")
    current_state: Optional[str] = Field(None, description="Current state: normal or degraded")
    current_partition_duration_seconds: Optional[float] = Field(None, description="Current partition duration")
    buffered_results_count: Optional[int] = Field(None, description="Results buffered during partition")
    in_progress_tasks_count: Optional[int] = Field(None, description="In-progress tasks during partition")


class NodeCrashStats(SubsystemStatus):
    """Node crash detection subsystem stats"""
    model_config = ConfigDict(extra="allow")

    total_crashes_detected: Optional[int] = Field(None, description="Total crashes detected")
    crash_detection_threshold_seconds: Optional[int] = Field(None, description="Crash detection threshold")
    recent_crashes: Optional[int] = Field(None, description="Recent crash count")
    max_history_size: Optional[int] = Field(None, description="Max crash history size")


class LeaseRevocationStats(SubsystemStatus):
    """Lease revocation subsystem stats"""
    model_config = ConfigDict(extra="allow")

    total_leases: Optional[int] = Field(None, description="Total leases")
    revoked_leases: Optional[int] = Field(None, description="Revoked lease count")
    active_leases: Optional[int] = Field(None, description="Active lease count")
    revocation_rate: Optional[float] = Field(None, description="Revocation rate %")


class DuplicatePreventionStats(SubsystemStatus):
    """Duplicate prevention subsystem stats"""
    model_config = ConfigDict(extra="allow")

    total_tasks: Optional[int] = Field(None, description="Total tasks")
    unique_idempotency_keys: Optional[int] = Field(None, description="Unique idempotency keys")
    potential_duplicates_prevented: Optional[int] = Field(None, description="Duplicates prevented")
    duplicate_prevention_active: Optional[bool] = Field(None, description="Whether prevention is active")


class IPPoolStats(SubsystemStatus):
    """IP pool subsystem stats"""
    model_config = ConfigDict(extra="allow")

    total_addresses: Optional[int] = Field(None, description="Total IP addresses")
    reserved_addresses: Optional[int] = Field(None, description="Reserved addresses")
    allocated_addresses: Optional[int] = Field(None, description="Allocated addresses")
    available_addresses: Optional[int] = Field(None, description="Available addresses")
    utilization_percent: Optional[int] = Field(None, description="Pool utilization %")


class MessageVerificationStats(SubsystemStatus):
    """Message verification subsystem stats"""
    model_config = ConfigDict(extra="allow")

    cache_size: Optional[int] = Field(None, description="Verification cache size")
    cache_hits: Optional[int] = Field(None, description="Cache hit count")


class SwarmHealthResponse(BaseModel):
    """Aggregated swarm health response for dashboard"""

    status: str = Field(
        ...,
        description="Overall health: 'healthy', 'degraded', 'unhealthy'"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp of health check")
    subsystems_available: int = Field(..., description="Number of responding subsystems")
    subsystems_total: int = Field(..., description="Total registered subsystems")
    lease_expiration: Optional[LeaseExpirationStats] = Field(
        None, description="Lease expiration subsystem"
    )
    result_buffer: Optional[ResultBufferStats] = Field(
        None, description="Result buffer subsystem"
    )
    partition_detection: Optional[PartitionDetectionStats] = Field(
        None, description="Partition detection subsystem"
    )
    node_crash_detection: Optional[NodeCrashStats] = Field(
        None, description="Node crash detection subsystem"
    )
    lease_revocation: Optional[LeaseRevocationStats] = Field(
        None, description="Lease revocation subsystem"
    )
    duplicate_prevention: Optional[DuplicatePreventionStats] = Field(
        None, description="Duplicate prevention subsystem"
    )
    ip_pool: Optional[IPPoolStats] = Field(
        None, description="IP pool subsystem"
    )
    message_verification: Optional[MessageVerificationStats] = Field(
        None, description="Message verification subsystem"
    )


# ============================================================================
# API Endpoint
# ============================================================================

@router.get(
    "/health",
    response_model=SwarmHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Get aggregated swarm health",
    description="""
    Get real-time health status of all agent swarm backend subsystems.

    This endpoint aggregates stats from 8 subsystems into a unified JSON
    response for the dashboard UI:

    - **lease_expiration**: Active lease counts and scan config
    - **result_buffer**: Buffer size and utilization
    - **partition_detection**: DBOS partition state
    - **node_crash_detection**: Crash counts and thresholds
    - **lease_revocation**: Revocation rates
    - **duplicate_prevention**: Task deduplication stats
    - **ip_pool**: IP address pool utilization
    - **message_verification**: Signature cache stats

    **Health Status Definitions:**
    - `healthy`: All subsystems responding, metrics within thresholds
    - `degraded`: Some subsystems down or threshold exceeded
    - `unhealthy`: Active partition or no subsystems responding

    **Fault Tolerance:**
    Individual subsystem failures do not cause a 500 response. Each
    subsystem section shows `available: false` with an error message.
    """,
    responses={
        200: {
            "description": "Health snapshot collected successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "healthy",
                        "timestamp": "2026-02-20T12:00:00+00:00",
                        "subsystems_available": 8,
                        "subsystems_total": 8,
                        "lease_expiration": {
                            "available": True,
                            "active_leases": 10,
                            "upcoming_expirations": 2,
                        },
                    }
                }
            },
        },
        500: {"description": "Internal Server Error"},
        503: {"description": "Service Unavailable - Swarm health service not loaded"},
    },
)
async def get_swarm_health() -> SwarmHealthResponse:
    """
    Get aggregated swarm health snapshot.

    Collects stats from all registered subsystems, derives overall
    health status, and returns structured JSON for the dashboard.
    """
    try:
        if not SWARM_HEALTH_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Swarm health service is not available",
            )

        service = get_swarm_health_service()
        snapshot = await service.collect_health_snapshot()

        return SwarmHealthResponse(**snapshot)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error collecting swarm health: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to collect swarm health: {str(e)}",
        )
