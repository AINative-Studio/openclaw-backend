"""
Swarm Timeline Dashboard API Endpoint

Provides task execution timeline events as structured JSON for
the agent-swarm-monitor Next.js dashboard.

Complementary to E8-S2's /swarm/health endpoint. This endpoint
returns individual timeline events for task flow visualization.

Epic E8-S3: Task Execution Timeline
Refs: #51
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

try:
    from backend.services.task_timeline_service import (
        TaskTimelineService,
        TimelineEventType,
        get_timeline_service,
    )
    TIMELINE_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Task timeline service not available: {e}")
    TIMELINE_AVAILABLE = False

router = APIRouter(prefix="/swarm", tags=["Swarm", "Monitoring", "Dashboard"])


# ============================================================================
# Response Models
# ============================================================================

class TimelineEventResponse(BaseModel):
    """Single timeline event in API response"""
    event_type: str = Field(..., description="Event type (e.g. TASK_CREATED)")
    task_id: Optional[str] = Field(None, description="Task identifier")
    peer_id: Optional[str] = Field(None, description="Peer identifier")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional event data"
    )


class TimelineResponse(BaseModel):
    """Paginated timeline response"""
    events: List[TimelineEventResponse] = Field(
        ..., description="Timeline events"
    )
    total_count: int = Field(..., description="Total matching events")
    limit: int = Field(..., description="Pagination limit")
    offset: int = Field(..., description="Pagination offset")


# ============================================================================
# API Endpoint
# ============================================================================

@router.get(
    "/timeline",
    response_model=TimelineResponse,
    status_code=status.HTTP_200_OK,
    summary="Get task execution timeline events",
    description="""
    Get timeline events for task state transitions, lease events,
    failures, and recoveries in the agent swarm.

    Supports filtering by task_id, peer_id, event_type, and time range.
    Results are sorted newest-first for dashboard display.

    **Event Types:**
    TASK_CREATED, TASK_QUEUED, TASK_LEASED, TASK_STARTED, TASK_PROGRESS,
    TASK_COMPLETED, TASK_FAILED, TASK_EXPIRED, TASK_REQUEUED,
    LEASE_ISSUED, LEASE_EXPIRED, LEASE_REVOKED, NODE_CRASHED

    **Fault Tolerance:**
    Invalid event_type returns empty results (200), not 422.
    """,
    responses={
        200: {"description": "Timeline events retrieved successfully"},
        500: {"description": "Internal Server Error"},
        503: {"description": "Service Unavailable - Timeline service not loaded"},
    },
)
async def get_swarm_timeline(
    task_id: Optional[str] = Query(None, description="Filter by task ID"),
    peer_id: Optional[str] = Query(None, description="Filter by peer ID"),
    event_type: Optional[str] = Query(
        None, description="Filter by event type (e.g. TASK_LEASED)"
    ),
    since: Optional[datetime] = Query(
        None, description="Events at or after this ISO 8601 timestamp"
    ),
    until: Optional[datetime] = Query(
        None, description="Events at or before this timestamp"
    ),
    limit: int = Query(100, ge=1, le=1000, description="Max events (1-1000)"),
    offset: int = Query(0, ge=0, description="Skip N events"),
) -> TimelineResponse:
    """
    Get task execution timeline events.

    Queries the in-memory timeline service with optional filters
    and pagination. Returns events sorted newest-first.
    """
    try:
        if not TIMELINE_AVAILABLE:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Task timeline service is not available",
            )

        service = get_timeline_service()

        # Resolve event_type string to enum (graceful degradation)
        resolved_event_type = None
        if event_type is not None:
            try:
                resolved_event_type = TimelineEventType(event_type)
            except ValueError:
                # Invalid event type: return empty results
                return TimelineResponse(
                    events=[],
                    total_count=0,
                    limit=limit,
                    offset=offset,
                )

        events, total_count = service.query_events(
            task_id=task_id,
            peer_id=peer_id,
            event_type=resolved_event_type,
            since=since,
            until=until,
            limit=limit,
            offset=offset,
        )

        event_responses = [
            TimelineEventResponse(
                event_type=(
                    e.event_type.value
                    if hasattr(e.event_type, "value")
                    else str(e.event_type)
                ),
                task_id=e.task_id,
                peer_id=e.peer_id,
                timestamp=e.timestamp.isoformat(),
                metadata=e.metadata,
            )
            for e in events
        ]

        return TimelineResponse(
            events=event_responses,
            total_count=total_count,
            limit=limit,
            offset=offset,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error querying timeline: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to query timeline: {str(e)}",
        )
