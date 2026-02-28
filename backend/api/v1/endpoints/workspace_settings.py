"""Workspace Settings API Endpoints"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.base import get_db
from backend.models.workspace_settings import WorkspaceSettings
from backend.schemas.workspace_settings import (
    WorkspaceSettingsResponse,
    WorkspaceSettingsUpdate,
    WorkspaceSettingsBase
)

router = APIRouter()


@router.get("/settings", response_model=WorkspaceSettingsResponse)
def get_workspace_settings(db: Session = Depends(get_db)):
    """
    Get workspace settings (creates default if doesn't exist)
    """
    # Get or create settings (single workspace for now)
    settings = db.query(WorkspaceSettings).first()

    if not settings:
        # Create default settings
        settings = WorkspaceSettings(
            workspace_name="My Workspace",
            workspace_slug="my-workspace",
            default_model="anthropic/claude-sonnet-4-6",
            timezone="UTC",
            email_notifications=1,
            agent_error_alerts=1,
            heartbeat_fail_alerts=1,
            weekly_digest=0
        )
        db.add(settings)
        db.commit()
        db.refresh(settings)

    # Convert integer flags to booleans for response
    return WorkspaceSettingsResponse(
        id=settings.id,
        workspace_name=settings.workspace_name,
        workspace_slug=settings.workspace_slug,
        default_model=settings.default_model,
        timezone=settings.timezone,
        email_notifications=bool(settings.email_notifications),
        agent_error_alerts=bool(settings.agent_error_alerts),
        heartbeat_fail_alerts=bool(settings.heartbeat_fail_alerts),
        weekly_digest=bool(settings.weekly_digest),
        created_at=settings.created_at,
        updated_at=settings.updated_at
    )


@router.patch("/settings", response_model=WorkspaceSettingsResponse)
def update_workspace_settings(
    update_data: WorkspaceSettingsUpdate,
    db: Session = Depends(get_db)
):
    """
    Update workspace settings
    """
    settings = db.query(WorkspaceSettings).first()

    if not settings:
        raise HTTPException(status_code=404, detail="Workspace settings not found")

    # Update fields if provided
    update_dict = update_data.model_dump(exclude_unset=True)

    for field, value in update_dict.items():
        if field in ["email_notifications", "agent_error_alerts", "heartbeat_fail_alerts", "weekly_digest"]:
            # Convert boolean to integer for SQLite
            setattr(settings, field, 1 if value else 0)
        else:
            setattr(settings, field, value)

    db.commit()
    db.refresh(settings)

    # Convert integer flags to booleans for response
    return WorkspaceSettingsResponse(
        id=settings.id,
        workspace_name=settings.workspace_name,
        workspace_slug=settings.workspace_slug,
        default_model=settings.default_model,
        timezone=settings.timezone,
        email_notifications=bool(settings.email_notifications),
        agent_error_alerts=bool(settings.agent_error_alerts),
        heartbeat_fail_alerts=bool(settings.heartbeat_fail_alerts),
        weekly_digest=bool(settings.weekly_digest),
        created_at=settings.created_at,
        updated_at=settings.updated_at
    )
