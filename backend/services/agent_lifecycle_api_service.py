"""
Agent Lifecycle API Service

Lightweight CRUD service for the agent lifecycle REST API.
Wraps SQLAlchemy operations without OpenClaw bridge integration.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.models.agent_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
    HeartbeatInterval,
)
from backend.schemas.agent_lifecycle import (
    CreateAgentRequest,
    UpdateAgentSettingsRequest,
)

logger = logging.getLogger(__name__)

VALID_HEARTBEAT_INTERVALS = {e.value for e in HeartbeatInterval}


class AgentLifecycleApiService:
    """CRUD service for agent lifecycle management"""

    def __init__(self, db: Session):
        self.db = db

    def list_agents(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentSwarmInstance], int]:
        query = self.db.query(AgentSwarmInstance)

        if status:
            try:
                status_enum = AgentSwarmStatus(status)
                query = query.filter(AgentSwarmInstance.status == status_enum)
            except ValueError:
                pass

        total = query.count()
        agents = (
            query.order_by(AgentSwarmInstance.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return agents, total

    def get_agent(self, agent_id: str) -> Optional[AgentSwarmInstance]:
        return self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

    def create_agent(
        self, user_id: str, request: CreateAgentRequest
    ) -> AgentSwarmInstance:
        heartbeat_enabled = False
        heartbeat_interval = None
        heartbeat_checklist = None

        if request.heartbeat:
            heartbeat_enabled = request.heartbeat.enabled
            if request.heartbeat.interval and request.heartbeat.interval in VALID_HEARTBEAT_INTERVALS:
                heartbeat_interval = HeartbeatInterval(request.heartbeat.interval)
            heartbeat_checklist = request.heartbeat.checklist

        agent = AgentSwarmInstance(
            id=uuid4(),
            name=request.name,
            persona=request.persona,
            model=request.model,
            user_id=user_id,
            status=AgentSwarmStatus.PROVISIONING,
            heartbeat_enabled=heartbeat_enabled,
            heartbeat_interval=heartbeat_interval,
            heartbeat_checklist=heartbeat_checklist,
            configuration=request.configuration or {},
            error_count=0,
        )
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def provision_agent(self, agent_id: str) -> Optional[AgentSwarmInstance]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        if agent.status not in (AgentSwarmStatus.PROVISIONING, AgentSwarmStatus.FAILED):
            raise ValueError(
                f"Cannot provision agent in '{agent.status.value}' state. "
                "Only 'provisioning' or 'failed' agents can be provisioned."
            )

        agent.status = AgentSwarmStatus.RUNNING
        agent.provisioned_at = datetime.now(timezone.utc)
        agent.error_message = None
        agent.error_count = 0
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def pause_agent(self, agent_id: str) -> Optional[AgentSwarmInstance]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        if agent.status != AgentSwarmStatus.RUNNING:
            raise ValueError(
                f"Cannot pause agent in '{agent.status.value}' state. "
                "Only 'running' agents can be paused."
            )

        agent.status = AgentSwarmStatus.PAUSED
        agent.paused_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def resume_agent(self, agent_id: str) -> Optional[AgentSwarmInstance]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        if agent.status != AgentSwarmStatus.PAUSED:
            raise ValueError(
                f"Cannot resume agent in '{agent.status.value}' state. "
                "Only 'paused' agents can be resumed."
            )

        agent.status = AgentSwarmStatus.RUNNING
        agent.paused_at = None
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def update_settings(
        self, agent_id: str, request: UpdateAgentSettingsRequest
    ) -> Optional[AgentSwarmInstance]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        if request.persona is not None:
            agent.persona = request.persona
        if request.model is not None:
            agent.model = request.model
        if request.configuration is not None:
            agent.configuration = request.configuration

        if request.heartbeat:
            agent.heartbeat_enabled = request.heartbeat.enabled
            if request.heartbeat.interval and request.heartbeat.interval in VALID_HEARTBEAT_INTERVALS:
                agent.heartbeat_interval = HeartbeatInterval(request.heartbeat.interval)
            if request.heartbeat.checklist is not None:
                agent.heartbeat_checklist = request.heartbeat.checklist

        agent.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def delete_agent(self, agent_id: str) -> Optional[AgentSwarmInstance]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        agent.status = AgentSwarmStatus.STOPPED
        agent.stopped_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def execute_heartbeat(self, agent_id: str) -> Optional[dict]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        if agent.status != AgentSwarmStatus.RUNNING:
            raise ValueError(
                f"Cannot execute heartbeat for agent in '{agent.status.value}' state. "
                "Agent must be 'running'."
            )

        now = datetime.now(timezone.utc)
        agent.last_heartbeat_at = now
        self.db.commit()
        self.db.refresh(agent)

        return {
            "status": "completed",
            "message": f"Heartbeat executed for agent '{agent.name}'",
        }
