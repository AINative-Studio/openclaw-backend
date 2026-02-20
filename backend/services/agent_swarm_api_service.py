"""
Agent Swarm API Service

Lightweight CRUD service for the swarm lifecycle REST API.
Manages swarm groups that coordinate multiple agents together.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from backend.models.agent_swarm import (
    AgentSwarm,
    SwarmStatus,
    CoordinationStrategy,
)
from backend.schemas.agent_swarm import (
    CreateSwarmRequest,
    UpdateSwarmRequest,
)

logger = logging.getLogger(__name__)

VALID_STRATEGIES = {e.value for e in CoordinationStrategy}


class AgentSwarmApiService:
    """CRUD service for swarm lifecycle management"""

    def __init__(self, db: Session):
        self.db = db

    def list_swarms(
        self,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AgentSwarm], int]:
        query = self.db.query(AgentSwarm)

        if status:
            try:
                status_enum = SwarmStatus(status)
                query = query.filter(AgentSwarm.status == status_enum)
            except ValueError:
                pass

        total = query.count()
        swarms = (
            query.order_by(AgentSwarm.created_at.desc())
            .offset(offset)
            .limit(limit)
            .all()
        )
        return swarms, total

    def get_swarm(self, swarm_id: str) -> Optional[AgentSwarm]:
        return self.db.query(AgentSwarm).filter(
            AgentSwarm.id == swarm_id
        ).first()

    def create_swarm(
        self, user_id: str, request: CreateSwarmRequest
    ) -> AgentSwarm:
        strategy = CoordinationStrategy.PARALLEL
        if request.strategy in VALID_STRATEGIES:
            strategy = CoordinationStrategy(request.strategy)

        swarm = AgentSwarm(
            id=str(uuid4()),
            name=request.name,
            description=request.description,
            strategy=strategy,
            goal=request.goal,
            status=SwarmStatus.IDLE,
            agent_ids=request.agent_ids or [],
            user_id=user_id,
            configuration=request.configuration or {},
        )
        self.db.add(swarm)
        self.db.commit()
        self.db.refresh(swarm)
        return swarm

    def update_swarm(
        self, swarm_id: str, request: UpdateSwarmRequest
    ) -> Optional[AgentSwarm]:
        swarm = self.get_swarm(swarm_id)
        if not swarm:
            return None

        if request.name is not None:
            swarm.name = request.name
        if request.description is not None:
            swarm.description = request.description
        if request.strategy is not None and request.strategy in VALID_STRATEGIES:
            swarm.strategy = CoordinationStrategy(request.strategy)
        if request.goal is not None:
            swarm.goal = request.goal
        if request.configuration is not None:
            swarm.configuration = request.configuration

        swarm.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(swarm)
        return swarm

    def add_agents(
        self, swarm_id: str, agent_ids: list[str]
    ) -> Optional[AgentSwarm]:
        swarm = self.get_swarm(swarm_id)
        if not swarm:
            return None

        current_ids = list(swarm.agent_ids or [])
        existing_set = set(current_ids)
        for aid in agent_ids:
            if aid not in existing_set:
                current_ids.append(aid)
                existing_set.add(aid)

        swarm.agent_ids = current_ids
        swarm.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(swarm)
        return swarm

    def remove_agents(
        self, swarm_id: str, agent_ids: list[str]
    ) -> Optional[AgentSwarm]:
        swarm = self.get_swarm(swarm_id)
        if not swarm:
            return None

        remove_set = set(agent_ids)
        swarm.agent_ids = [
            aid for aid in (swarm.agent_ids or []) if aid not in remove_set
        ]
        swarm.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(swarm)
        return swarm

    def start_swarm(self, swarm_id: str) -> Optional[AgentSwarm]:
        swarm = self.get_swarm(swarm_id)
        if not swarm:
            return None

        if swarm.status not in (SwarmStatus.IDLE, SwarmStatus.FAILED):
            raise ValueError(
                f"Cannot start swarm in '{swarm.status.value}' state. "
                "Only 'idle' or 'failed' swarms can be started."
            )

        swarm.status = SwarmStatus.RUNNING
        swarm.started_at = datetime.now(timezone.utc)
        swarm.error_message = None
        self.db.commit()
        self.db.refresh(swarm)
        return swarm

    def pause_swarm(self, swarm_id: str) -> Optional[AgentSwarm]:
        swarm = self.get_swarm(swarm_id)
        if not swarm:
            return None

        if swarm.status != SwarmStatus.RUNNING:
            raise ValueError(
                f"Cannot pause swarm in '{swarm.status.value}' state. "
                "Only 'running' swarms can be paused."
            )

        swarm.status = SwarmStatus.PAUSED
        swarm.paused_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(swarm)
        return swarm

    def resume_swarm(self, swarm_id: str) -> Optional[AgentSwarm]:
        swarm = self.get_swarm(swarm_id)
        if not swarm:
            return None

        if swarm.status != SwarmStatus.PAUSED:
            raise ValueError(
                f"Cannot resume swarm in '{swarm.status.value}' state. "
                "Only 'paused' swarms can be resumed."
            )

        swarm.status = SwarmStatus.RUNNING
        swarm.paused_at = None
        self.db.commit()
        self.db.refresh(swarm)
        return swarm

    def stop_swarm(self, swarm_id: str) -> Optional[AgentSwarm]:
        swarm = self.get_swarm(swarm_id)
        if not swarm:
            return None

        swarm.status = SwarmStatus.STOPPED
        swarm.stopped_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(swarm)
        return swarm
