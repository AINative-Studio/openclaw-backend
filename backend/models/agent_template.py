"""
Agent Template ORM Model

Standalone model using backend.db.base_class.Base for the template CRUD API.
Stores pre-configured agent templates with default settings.
"""

from enum import Enum
from uuid import uuid4

from sqlalchemy import (
    Column,
    String,
    Text,
    DateTime,
    JSON,
    Enum as SQLEnum,
)
from sqlalchemy.sql import func

from backend.db.base_class import Base


class TemplateCategory(str, Enum):
    """Template category enumeration"""
    ENGINEERING = "engineering"
    SALES_OUTREACH = "sales-outreach"
    DEVOPS_INFRASTRUCTURE = "devops-infrastructure"
    PRODUCTIVITY = "productivity"


class AgentTemplate(Base):
    """
    Agent Template Model

    Represents a pre-configured template that can be used to quickly
    create new agents with sensible defaults.
    """
    __tablename__ = "agent_templates"
    __table_args__ = {"extend_existing": True}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name = Column(String(255), nullable=False, index=True)
    description = Column(Text, nullable=True)
    category = Column(
        SQLEnum(
            TemplateCategory,
            name="template_category",
            native_enum=False,
            create_constraint=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        index=True,
    )
    icons = Column(JSON, default=list)
    default_model = Column(String(255), default="anthropic/claude-opus-4-5")
    default_persona = Column(Text, nullable=True)
    default_heartbeat_interval = Column(String(10), nullable=True, default="5m")
    default_checklist = Column(JSON, default=list)
    user_id = Column(String(36), nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<AgentTemplate {self.name} ({self.category})>"
