"""Workspace Settings Model"""
from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from backend.db.base_class import Base


class WorkspaceSettings(Base):
    """Workspace-level settings and configuration"""
    __tablename__ = "workspace_settings"

    id = Column(Integer, primary_key=True, index=True)
    workspace_name = Column(String(255), nullable=False, default="My Workspace")
    workspace_slug = Column(String(100), unique=True, nullable=False)
    default_model = Column(String(100), nullable=False, default="anthropic/claude-sonnet-4-6")
    timezone = Column(String(50), nullable=False, default="UTC")

    # Notification preferences
    email_notifications = Column(Integer, nullable=False, default=1)  # SQLite doesn't have boolean
    agent_error_alerts = Column(Integer, nullable=False, default=1)
    heartbeat_fail_alerts = Column(Integer, nullable=False, default=1)
    weekly_digest = Column(Integer, nullable=False, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
