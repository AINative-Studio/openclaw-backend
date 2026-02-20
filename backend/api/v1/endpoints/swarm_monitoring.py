"""
Monitoring status endpoint for the Agent Swarm Monitor dashboard (E8-S5).

Provides GET /swarm/monitoring/status to inspect the health of the
monitoring infrastructure itself (Prometheus, Timeline, SwarmHealth).
"""

import logging
from typing import Dict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/swarm", tags=["Swarm", "Monitoring", "Dashboard"])

try:
    from backend.services.monitoring_integration_service import (
        MonitoringIntegrationService,
        get_monitoring_integration_service,
    )
    MONITORING_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Monitoring integration service not available: {e}")
    MONITORING_AVAILABLE = False


# ------------------------------------------------------------------
# Response models
# ------------------------------------------------------------------

class SubsystemAvailability(BaseModel):
    available: bool = Field(..., description="Whether the subsystem is available")


class MonitoringStatusResponse(BaseModel):
    status: str = Field(
        ..., description="Overall status: operational/partial/unavailable"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    subsystems: Dict[str, SubsystemAvailability] = Field(
        ..., description="Availability of each monitoring subsystem"
    )
    registered_health_subsystems: int = Field(
        ..., description="Number of subsystems registered with SwarmHealthService"
    )
    timeline_event_count: int = Field(
        ..., description="Total events recorded in TaskTimelineService"
    )
    bootstrapped: bool = Field(
        ..., description="Whether bootstrap() has been called"
    )


# ------------------------------------------------------------------
# Endpoint
# ------------------------------------------------------------------

@router.get(
    "/monitoring/status",
    response_model=MonitoringStatusResponse,
    summary="Get monitoring infrastructure status",
    responses={
        200: {"description": "Monitoring status retrieved"},
        503: {"description": "Monitoring service not available"},
        500: {"description": "Unexpected server error"},
    },
)
async def get_monitoring_status() -> MonitoringStatusResponse:
    """Return the current health of the monitoring infrastructure."""
    if not MONITORING_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="Monitoring integration service not available",
        )

    try:
        service = get_monitoring_integration_service()
        status_data = service.get_status()
        return MonitoringStatusResponse(
            status=status_data["status"],
            timestamp=status_data["timestamp"],
            subsystems={
                name: SubsystemAvailability(**info)
                for name, info in status_data["subsystems"].items()
            },
            registered_health_subsystems=status_data[
                "registered_health_subsystems"
            ],
            timeline_event_count=status_data["timeline_event_count"],
            bootstrapped=status_data["bootstrapped"],
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in monitoring status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {e}",
        )
