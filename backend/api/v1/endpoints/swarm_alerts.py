"""
Swarm Alert Threshold Configuration API Endpoint

Provides GET/PUT endpoints for runtime configuration of alert
thresholds used by SwarmHealthService to derive health status.

Operators can adjust thresholds without redeployment to tune
sensitivity for buffer utilization, crash counts, revocation
rates, and IP pool utilization.

Epic E8-S4: Alert Threshold Configuration
Refs: #52
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from backend.services.alert_threshold_service import (
        AlertThresholdService,
        get_alert_threshold_service,
    )
    ALERTS_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Alert threshold service not available: {e}")
    ALERTS_AVAILABLE = False

router = APIRouter(prefix="/swarm", tags=["Swarm", "Monitoring", "Dashboard"])


# ============================================================================
# Request / Response Models
# ============================================================================

class ThresholdUpdateRequest(BaseModel):
    """Partial update request for alert thresholds"""
    buffer_utilization: Optional[float] = Field(
        None, ge=0.0, le=100.0,
        description="Buffer utilization % above which status is degraded",
    )
    crash_count: Optional[int] = Field(
        None, ge=0,
        description="Recent crash count at or above which status is degraded",
    )
    revocation_rate: Optional[float] = Field(
        None, ge=0.0, le=100.0,
        description="Revocation rate % above which status is degraded",
    )
    ip_pool_utilization: Optional[float] = Field(
        None, ge=0.0, le=100.0,
        description="IP pool utilization % above which status is degraded",
    )


class ThresholdResponse(BaseModel):
    """Alert threshold configuration response"""
    buffer_utilization: float = Field(
        ..., description="Buffer utilization threshold %"
    )
    crash_count: int = Field(
        ..., description="Crash count threshold"
    )
    revocation_rate: float = Field(
        ..., description="Revocation rate threshold %"
    )
    ip_pool_utilization: float = Field(
        ..., description="IP pool utilization threshold %"
    )
    updated_at: str = Field(
        ..., description="ISO 8601 timestamp of last update"
    )


# ============================================================================
# API Endpoints
# ============================================================================

@router.get(
    "/alerts/thresholds",
    response_model=ThresholdResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current alert thresholds",
    description="""
    Get the current alert threshold configuration used by the swarm
    health derivation logic.

    Default thresholds:
    - buffer_utilization: 80.0%
    - crash_count: 3
    - revocation_rate: 50.0%
    - ip_pool_utilization: 90.0%
    """,
    responses={
        200: {"description": "Current threshold configuration"},
        500: {"description": "Internal Server Error"},
        503: {"description": "Service Unavailable"},
    },
)
async def get_alert_thresholds() -> ThresholdResponse:
    """Get current alert threshold configuration."""
    try:
        if not ALERTS_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Alert threshold service is not available",
            )

        service = get_alert_threshold_service()
        config = service.get_thresholds()

        return ThresholdResponse(
            buffer_utilization=config.buffer_utilization,
            crash_count=config.crash_count,
            revocation_rate=config.revocation_rate,
            ip_pool_utilization=config.ip_pool_utilization,
            updated_at=config.updated_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting alert thresholds: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get alert thresholds: {str(e)}",
        )


@router.put(
    "/alerts/thresholds",
    response_model=ThresholdResponse,
    status_code=status.HTTP_200_OK,
    summary="Update alert thresholds",
    description="""
    Partially update alert threshold configuration. Only provided
    fields are changed; omitted fields retain their current values.

    An empty body returns the current configuration unchanged.
    Invalid values return 422 with validation error details.
    """,
    responses={
        200: {"description": "Updated threshold configuration"},
        422: {"description": "Validation Error - invalid threshold value"},
        500: {"description": "Internal Server Error"},
        503: {"description": "Service Unavailable"},
    },
)
async def update_alert_thresholds(
    request: ThresholdUpdateRequest,
) -> ThresholdResponse:
    """Update alert threshold configuration."""
    try:
        if not ALERTS_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Alert threshold service is not available",
            )

        service = get_alert_threshold_service()

        # Filter out None values for partial update
        updates = {
            k: v
            for k, v in request.model_dump().items()
            if v is not None
        }

        if updates:
            config = service.update_thresholds(updates)
        else:
            config = service.get_thresholds()

        return ThresholdResponse(
            buffer_utilization=config.buffer_utilization,
            crash_count=config.crash_count,
            revocation_rate=config.revocation_rate,
            ip_pool_utilization=config.ip_pool_utilization,
            updated_at=config.updated_at.isoformat(),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating alert thresholds: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update alert thresholds: {str(e)}",
        )
