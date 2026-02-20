"""
Agent Lifecycle CRUD REST API

Exposes the AgentSwarmLifecycle CRUD operations as HTTP endpoints
for the agent-swarm-monitor frontend dashboard.

9 endpoints: list, get, create, provision, pause, resume, update settings,
delete (soft), and execute heartbeat.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

try:
    from backend.db.base import get_db
    from backend.services.agent_lifecycle_api_service import AgentLifecycleApiService
    from backend.schemas.agent_lifecycle import (
        AgentResponse,
        AgentListResponse,
        CreateAgentRequest,
        UpdateAgentSettingsRequest,
        HeartbeatExecutionResponse,
    )
    from backend.models.agent_lifecycle import AgentSwarmInstance
    AGENT_LIFECYCLE_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Agent lifecycle service not available: {e}")
    AGENT_LIFECYCLE_AVAILABLE = False

router = APIRouter(prefix="/agents", tags=["Agents", "Lifecycle"])

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _agent_to_response(agent: "AgentSwarmInstance") -> "AgentResponse":
    """Convert ORM model to API response"""
    def _dt(val) -> Optional[str]:
        if val is None:
            return None
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return str(val)

    return AgentResponse(
        id=str(agent.id),
        name=agent.name,
        persona=agent.persona,
        model=agent.model,
        user_id=str(agent.user_id),
        status=agent.status.value if hasattr(agent.status, "value") else str(agent.status),
        openclaw_session_key=agent.openclaw_session_key,
        openclaw_agent_id=agent.openclaw_agent_id,
        heartbeat_enabled=agent.heartbeat_enabled,
        heartbeat_interval=(
            agent.heartbeat_interval.value
            if agent.heartbeat_interval and hasattr(agent.heartbeat_interval, "value")
            else agent.heartbeat_interval
        ),
        heartbeat_checklist=agent.heartbeat_checklist,
        last_heartbeat_at=_dt(agent.last_heartbeat_at),
        next_heartbeat_at=_dt(agent.next_heartbeat_at),
        configuration=agent.configuration,
        error_message=agent.error_message,
        error_count=agent.error_count or 0,
        created_at=_dt(agent.created_at) or "",
        updated_at=_dt(agent.updated_at),
        provisioned_at=_dt(agent.provisioned_at),
        paused_at=_dt(agent.paused_at),
        stopped_at=_dt(agent.stopped_at),
    )


def _check_available() -> None:
    if not AGENT_LIFECYCLE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent lifecycle service is not available",
        )


@router.get(
    "",
    response_model=AgentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List agents",
)
def list_agents(
    agent_status: Optional[str] = Query(None, alias="status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> AgentListResponse:
    _check_available()
    try:
        service = AgentLifecycleApiService(db)
        agents, total = service.list_agents(status=agent_status, limit=limit, offset=offset)
        return AgentListResponse(
            agents=[_agent_to_response(a) for a in agents],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"Error listing agents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agents: {str(e)}",
        )


@router.get(
    "/{agent_id}",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get agent detail",
)
def get_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentResponse:
    _check_available()
    try:
        service = AgentLifecycleApiService(db)
        agent = service.get_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        return _agent_to_response(agent)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get agent: {str(e)}",
        )


@router.post(
    "",
    response_model=AgentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create agent",
)
def create_agent(
    request: CreateAgentRequest,
    db: Session = Depends(get_db),
) -> AgentResponse:
    _check_available()
    try:
        service = AgentLifecycleApiService(db)
        agent = service.create_agent(user_id=DEFAULT_USER_ID, request=request)
        return _agent_to_response(agent)
    except Exception as e:
        logger.error(f"Error creating agent: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create agent: {str(e)}",
        )


@router.post(
    "/{agent_id}/provision",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Provision agent",
)
def provision_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentResponse:
    _check_available()
    try:
        service = AgentLifecycleApiService(db)
        agent = service.provision_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        return _agent_to_response(agent)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error provisioning agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to provision agent: {str(e)}",
        )


@router.post(
    "/{agent_id}/pause",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Pause running agent",
)
def pause_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentResponse:
    _check_available()
    try:
        service = AgentLifecycleApiService(db)
        agent = service.pause_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        return _agent_to_response(agent)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error pausing agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to pause agent: {str(e)}",
        )


@router.post(
    "/{agent_id}/resume",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Resume paused agent",
)
def resume_agent(agent_id: str, db: Session = Depends(get_db)) -> AgentResponse:
    _check_available()
    try:
        service = AgentLifecycleApiService(db)
        agent = service.resume_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        return _agent_to_response(agent)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error resuming agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to resume agent: {str(e)}",
        )


@router.patch(
    "/{agent_id}/settings",
    response_model=AgentResponse,
    status_code=status.HTTP_200_OK,
    summary="Update agent settings",
)
def update_agent_settings(
    agent_id: str,
    request: UpdateAgentSettingsRequest,
    db: Session = Depends(get_db),
) -> AgentResponse:
    _check_available()
    try:
        service = AgentLifecycleApiService(db)
        agent = service.update_settings(agent_id, request)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        return _agent_to_response(agent)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update agent settings: {str(e)}",
        )


@router.delete(
    "/{agent_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete agent (soft delete)",
)
def delete_agent(agent_id: str, db: Session = Depends(get_db)) -> None:
    _check_available()
    try:
        service = AgentLifecycleApiService(db)
        agent = service.delete_agent(agent_id)
        if not agent:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete agent: {str(e)}",
        )


@router.post(
    "/{agent_id}/heartbeat",
    response_model=HeartbeatExecutionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute heartbeat",
)
def execute_heartbeat(
    agent_id: str, db: Session = Depends(get_db)
) -> HeartbeatExecutionResponse:
    _check_available()
    try:
        service = AgentLifecycleApiService(db)
        result = service.execute_heartbeat(agent_id)
        if not result:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Agent {agent_id} not found",
            )
        return HeartbeatExecutionResponse(**result)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error executing heartbeat for {agent_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to execute heartbeat: {str(e)}",
        )
