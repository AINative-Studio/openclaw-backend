"""
Agent Template CRUD REST API

Exposes template CRUD operations as HTTP endpoints
for the agent-swarm-monitor frontend dashboard.

6 endpoints: list, get, create, update, delete, seed.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

try:
    from backend.db.base import get_db
    from backend.services.agent_template_api_service import AgentTemplateApiService
    from backend.schemas.agent_template import (
        TemplateResponse,
        TemplateListResponse,
        CreateTemplateRequest,
        UpdateTemplateRequest,
    )
    from backend.models.agent_template import AgentTemplate
    AGENT_TEMPLATE_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Agent template service not available: {e}")
    AGENT_TEMPLATE_AVAILABLE = False

router = APIRouter(prefix="/templates", tags=["Templates"])

DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001"


def _template_to_response(template: "AgentTemplate") -> "TemplateResponse":
    """Convert ORM model to API response"""
    def _dt(val) -> Optional[str]:
        if val is None:
            return None
        if hasattr(val, "isoformat"):
            return val.isoformat()
        return str(val)

    return TemplateResponse(
        id=str(template.id),
        name=template.name,
        description=template.description,
        category=(
            template.category.value
            if hasattr(template.category, "value")
            else str(template.category)
        ),
        icons=template.icons or [],
        default_model=template.default_model or "anthropic/claude-opus-4-5",
        default_persona=template.default_persona,
        default_heartbeat_interval=template.default_heartbeat_interval,
        default_checklist=template.default_checklist or [],
        user_id=str(template.user_id),
        created_at=_dt(template.created_at) or "",
        updated_at=_dt(template.updated_at),
    )


def _check_available() -> None:
    if not AGENT_TEMPLATE_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent template service is not available",
        )


@router.get(
    "",
    response_model=TemplateListResponse,
    status_code=status.HTTP_200_OK,
    summary="List templates",
)
def list_templates(
    category: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
) -> TemplateListResponse:
    """List all templates, optionally filtered by category."""
    _check_available()
    try:
        service = AgentTemplateApiService(db)
        templates, total = service.list_templates(
            category=category, limit=limit, offset=offset
        )
        return TemplateListResponse(
            templates=[_template_to_response(t) for t in templates],
            total=total,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        logger.error(f"Error listing templates: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list templates: {str(e)}",
        )


@router.get(
    "/{template_id}",
    response_model=TemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Get template",
)
def get_template(
    template_id: str,
    db: Session = Depends(get_db),
) -> TemplateResponse:
    """Get a single template by ID."""
    _check_available()
    try:
        service = AgentTemplateApiService(db)
        template = service.get_template(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{template_id}' not found",
            )
        return _template_to_response(template)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get template: {str(e)}",
        )


@router.post(
    "",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create template",
)
def create_template(
    request: CreateTemplateRequest,
    db: Session = Depends(get_db),
) -> TemplateResponse:
    """Create a new template."""
    _check_available()
    try:
        service = AgentTemplateApiService(db)
        template = service.create_template(DEFAULT_USER_ID, request)
        return _template_to_response(template)
    except Exception as e:
        logger.error(f"Error creating template: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create template: {str(e)}",
        )


@router.patch(
    "/{template_id}",
    response_model=TemplateResponse,
    status_code=status.HTTP_200_OK,
    summary="Update template",
)
def update_template(
    template_id: str,
    request: UpdateTemplateRequest,
    db: Session = Depends(get_db),
) -> TemplateResponse:
    """Partially update a template."""
    _check_available()
    try:
        service = AgentTemplateApiService(db)
        template = service.update_template(template_id, request)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{template_id}' not found",
            )
        return _template_to_response(template)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating template: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update template: {str(e)}",
        )


@router.delete(
    "/{template_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete template",
)
def delete_template(
    template_id: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete a template."""
    _check_available()
    try:
        service = AgentTemplateApiService(db)
        template = service.delete_template(template_id)
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Template '{template_id}' not found",
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete template: {str(e)}",
        )


@router.post(
    "/seed",
    response_model=TemplateListResponse,
    status_code=status.HTTP_200_OK,
    summary="Seed default templates",
)
def seed_templates(
    db: Session = Depends(get_db),
) -> TemplateListResponse:
    """Seed default templates (idempotent)."""
    _check_available()
    try:
        service = AgentTemplateApiService(db)
        seeded = service.seed_templates(DEFAULT_USER_ID)
        return TemplateListResponse(
            templates=[_template_to_response(t) for t in seeded],
            total=len(seeded),
            limit=len(seeded),
            offset=0,
        )
    except Exception as e:
        logger.error(f"Error seeding templates: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to seed templates: {str(e)}",
        )
