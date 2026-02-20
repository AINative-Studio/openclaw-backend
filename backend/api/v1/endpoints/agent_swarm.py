"""
Agent Swarm CRUD REST API

Exposes swarm lifecycle CRUD operations as HTTP endpoints
for the agent-swarm-monitor frontend dashboard.

10 endpoints: list, get, create, update, add agents, remove agents,
start, pause, resume, delete (soft).
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

try:
    from backend.db.base import get_db
    from backend.services.agent_swarm_api_service import AgentSwarmApiService
    from backend.schemas.agent_swarm import (
        SwarmResponse,
        SwarmListResponse,
        CreateSwarmRequest,
        UpdateSwarmRequest,
        AddAgentsRequest,
        RemoveAgentsRequest,
    )
    from backend.models.agent_swarm import AgentSwarm
    AGENT_SWARM_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Agent swarm service not available: {e}")
    AGENT_SWARM_AVAILABLE = False

router = APIRouter(prefix="/swarms", tags=["Swarms", "Lifecycle"])

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _swarm_to_response(swarm: "AgentSwarm") -> "SwarmResponse":
    """Convert ORM model to API response"""
    def _dt(val) -> Optional[str]:
        if val is None:
            return None
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return str(val)

    agent_ids = swarm.agent_ids or []

    return SwarmResponse(
        id=str(swarm.id),
        name=swarm.name,
        description=swarm.description,
        strategy=swarm.strategy.value if hasattr(swarm.strategy, "value") else str(swarm.strategy),
        goal=swarm.goal,
        status=swarm.status.value if hasattr(swarm.status, "value") else str(swarm.status),
        agent_ids=agent_ids,
        agent_count=len(agent_ids),
        user_id=str(swarm.user_id),
        configuration=swarm.configuration,
        error_message=swarm.error_message,
        created_at=_dt(swarm.created_at) or "",
        updated_at=_dt(swarm.updated_at),
        started_at=_dt(swarm.started_at),
        paused_at=_dt(swarm.paused_at),
        stopped_at=_dt(swarm.stopped_at),
    )


def _check_available() -> None:
    if not AGENT_SWARM_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent swarm service is not available",
        )


@router.get(
    "",
    response_model=SwarmListResponse,
    status_code=status.HTTP_200_OK,
    summary="List swarms",
)
def list_swarms(
    swarm_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> SwarmListResponse:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarms, total = service.list_swarms(status=swarm_status, limit=limit, offset=offset)
        return SwarmListResponse(
            swarms=[_swarm_to_response(s) for s in swarms],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"Error listing swarms: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list swarms: {str(e)}",
        )


@router.get(
    "/{swarm_id}",
    response_model=SwarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Get swarm detail",
)
def get_swarm(swarm_id: str, db: Session = Depends(get_db)) -> SwarmResponse:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarm = service.get_swarm(swarm_id)
        if not swarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Swarm {swarm_id} not found",
            )
        return _swarm_to_response(swarm)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting swarm {swarm_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get swarm: {str(e)}",
        )


@router.post(
    "",
    response_model=SwarmResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create swarm",
)
def create_swarm(
    request: CreateSwarmRequest,
    db: Session = Depends(get_db),
) -> SwarmResponse:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarm = service.create_swarm(user_id=DEFAULT_USER_ID, request=request)
        return _swarm_to_response(swarm)
    except Exception as e:
        logger.error(f"Error creating swarm: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create swarm: {str(e)}",
        )


@router.patch(
    "/{swarm_id}",
    response_model=SwarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Update swarm settings",
)
def update_swarm(
    swarm_id: str,
    request: UpdateSwarmRequest,
    db: Session = Depends(get_db),
) -> SwarmResponse:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarm = service.update_swarm(swarm_id, request)
        if not swarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Swarm {swarm_id} not found",
            )
        return _swarm_to_response(swarm)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating swarm {swarm_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update swarm: {str(e)}",
        )


@router.post(
    "/{swarm_id}/agents",
    response_model=SwarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Add agents to swarm",
)
def add_agents(
    swarm_id: str,
    request: AddAgentsRequest,
    db: Session = Depends(get_db),
) -> SwarmResponse:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarm = service.add_agents(swarm_id, request.agent_ids)
        if not swarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Swarm {swarm_id} not found",
            )
        return _swarm_to_response(swarm)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding agents to swarm {swarm_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add agents: {str(e)}",
        )


@router.delete(
    "/{swarm_id}/agents",
    response_model=SwarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove agents from swarm",
)
def remove_agents(
    swarm_id: str,
    request: RemoveAgentsRequest,
    db: Session = Depends(get_db),
) -> SwarmResponse:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarm = service.remove_agents(swarm_id, request.agent_ids)
        if not swarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Swarm {swarm_id} not found",
            )
        return _swarm_to_response(swarm)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing agents from swarm {swarm_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to remove agents: {str(e)}",
        )


@router.post(
    "/{swarm_id}/start",
    response_model=SwarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Start swarm",
)
def start_swarm(swarm_id: str, db: Session = Depends(get_db)) -> SwarmResponse:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarm = service.start_swarm(swarm_id)
        if not swarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Swarm {swarm_id} not found",
            )
        return _swarm_to_response(swarm)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error starting swarm {swarm_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start swarm: {str(e)}",
        )


@router.post(
    "/{swarm_id}/pause",
    response_model=SwarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Pause running swarm",
)
def pause_swarm(swarm_id: str, db: Session = Depends(get_db)) -> SwarmResponse:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarm = service.pause_swarm(swarm_id)
        if not swarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Swarm {swarm_id} not found",
            )
        return _swarm_to_response(swarm)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error pausing swarm {swarm_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause swarm: {str(e)}",
        )


@router.post(
    "/{swarm_id}/resume",
    response_model=SwarmResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume paused swarm",
)
def resume_swarm(swarm_id: str, db: Session = Depends(get_db)) -> SwarmResponse:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarm = service.resume_swarm(swarm_id)
        if not swarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Swarm {swarm_id} not found",
            )
        return _swarm_to_response(swarm)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error resuming swarm {swarm_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume swarm: {str(e)}",
        )


@router.delete(
    "/{swarm_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete swarm (soft delete)",
)
def delete_swarm(swarm_id: str, db: Session = Depends(get_db)) -> None:
    _check_available()
    try:
        service = AgentSwarmApiService(db)
        swarm = service.stop_swarm(swarm_id)
        if not swarm:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Swarm {swarm_id} not found",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting swarm {swarm_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete swarm: {str(e)}",
        )
