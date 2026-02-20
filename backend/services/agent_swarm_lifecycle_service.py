"""
Agent Swarm Lifecycle Service

Business logic for agent lifecycle management including provisioning, pause/resume,
heartbeat execution, and OpenClaw integration.

Refs #1213
"""

import os
import logging
from typing import Optional, List
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
    HeartbeatInterval,
    AgentHeartbeatExecution,
    HeartbeatExecutionStatus
)
from app.schemas.agent_swarm_lifecycle import (
    AgentProvisionRequest,
    AgentUpdateSettingsRequest,
    AgentProvisionResponse,
    AgentDetailResponse,
    AgentStatusResponse,
    HeartbeatExecutionResponse,
)

# Initialize logger first
logger = logging.getLogger(__name__)

# Optional import - OpenClaw integration may not be available
try:
    from app.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge
except ImportError:
    ProductionOpenClawBridge = None
    logger.warning("ProductionOpenClawBridge not available - OpenClaw integration disabled")


class AgentSwarmLifecycleService:
    """
    Service for managing agent lifecycle operations

    Handles:
    - Agent creation and provisioning
    - Pause/resume functionality
    - Heartbeat execution and scheduling
    - OpenClaw integration
    - Error tracking and recovery
    """

    def __init__(self, db: Session):
        """
        Initialize lifecycle service

        Args:
            db: Database session
        """
        self.db = db
        self.openclaw_bridge = None

        # Initialize OpenClaw bridge if configured and available
        openclaw_url = os.getenv("OPENCLAW_GATEWAY_URL")
        openclaw_token = os.getenv("OPENCLAW_AUTH_TOKEN")

        if ProductionOpenClawBridge and openclaw_url and openclaw_token:
            try:
                self.openclaw_bridge = ProductionOpenClawBridge(
                    url=openclaw_url,
                    token=openclaw_token
                )
                logger.info("OpenClaw bridge initialized successfully")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenClaw bridge: {e}")

    def create_agent(
        self,
        user_id: UUID,
        request: AgentProvisionRequest
    ) -> AgentSwarmInstance:
        """
        Create a new agent instance in provisioning state

        Args:
            user_id: Owner user ID
            request: Agent provision request

        Returns:
            Created agent instance

        Raises:
            IntegrityError: If session key already exists
        """
        # Generate session key (ensure uniqueness)
        base_session_key = self._generate_session_key(request.name)
        session_key = base_session_key

        # Check for existing session key and append suffix if needed
        suffix = 0
        while self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.openclaw_session_key == session_key
        ).first() is not None:
            suffix += 1
            session_key = f"{base_session_key}-{suffix}"

        # Extract heartbeat configuration
        heartbeat_enabled = False
        heartbeat_interval = None
        heartbeat_checklist = None
        next_heartbeat_at = None

        if request.heartbeat:
            heartbeat_enabled = request.heartbeat.enabled
            heartbeat_interval = request.heartbeat.interval
            heartbeat_checklist = request.heartbeat.checklist

            if heartbeat_enabled and heartbeat_interval:
                next_heartbeat_at = self._calculate_next_heartbeat(heartbeat_interval)

        # Create agent instance
        agent = AgentSwarmInstance(
            name=request.name,
            persona=request.persona,
            model=request.model,
            user_id=user_id,
            status=AgentSwarmStatus.PROVISIONING,
            openclaw_session_key=session_key,
            heartbeat_enabled=heartbeat_enabled,
            heartbeat_interval=HeartbeatInterval(heartbeat_interval) if heartbeat_interval else None,
            heartbeat_checklist=heartbeat_checklist,
            next_heartbeat_at=next_heartbeat_at,
            configuration=request.configuration or {}
        )

        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)

        logger.info(
            f"Agent created: {agent.name} (ID: {agent.id})",
            extra={
                "agent_id": str(agent.id),
                "user_id": str(user_id),
                "session_key": session_key
            }
        )

        return agent

    async def provision_agent(self, agent_id: UUID) -> AgentStatusResponse:
        """
        Provision agent by registering with OpenClaw

        Args:
            agent_id: Agent instance ID

        Returns:
            Agent status response

        Raises:
            ValueError: If agent not found or in wrong state
            ConnectionError: If OpenClaw connection fails
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Allow provisioning if already running (idempotency)
        if agent.status == AgentSwarmStatus.RUNNING:
            logger.info(f"Agent {agent_id} already provisioned")
            return AgentStatusResponse(
                id=agent.id,
                name=agent.name,
                status=AgentSwarmStatus.RUNNING,
                message="Agent already provisioned"
            )

        if agent.status not in [AgentSwarmStatus.PROVISIONING, AgentSwarmStatus.FAILED]:
            raise ValueError(f"Cannot provision agent in {agent.status} state")

        try:
            # Connect to OpenClaw if not connected
            if self.openclaw_bridge and not self.openclaw_bridge.is_connected:
                await self.openclaw_bridge.connect()

            # Build provisioning message
            provisioning_message = self._build_provisioning_message(agent)

            # Send to OpenClaw
            if self.openclaw_bridge:
                result = await self.openclaw_bridge.send_to_agent(
                    session_key=agent.openclaw_session_key,
                    message=provisioning_message,
                    metadata={"type": "provisioning", "agent_id": str(agent.id)}
                )

                # Update agent status
                agent.status = AgentSwarmStatus.RUNNING
                agent.openclaw_agent_id = result.get("message_id")
                agent.provisioned_at = datetime.now(timezone.utc)
                agent.error_message = None
                agent.error_count = 0
            else:
                # Mock provisioning if OpenClaw not available
                logger.warning("OpenClaw not configured, mock provisioning")
                agent.status = AgentSwarmStatus.RUNNING
                agent.provisioned_at = datetime.now(timezone.utc)

            self.db.commit()
            self.db.refresh(agent)

            logger.info(
                f"Agent provisioned: {agent.name} (ID: {agent.id})",
                extra={"agent_id": str(agent.id)}
            )

            return AgentStatusResponse(
                id=agent.id,
                name=agent.name,
                status=agent.status,
                message="Agent provisioned successfully"
            )

        except Exception as e:
            # Update error tracking
            agent.status = AgentSwarmStatus.FAILED
            agent.error_message = str(e)
            agent.error_count += 1
            agent.last_error_at = datetime.now(timezone.utc)
            self.db.commit()

            logger.error(
                f"Agent provisioning failed: {agent.name} (ID: {agent.id}): {e}",
                extra={"agent_id": str(agent.id), "error": str(e)}
            )
            raise

    def pause_agent(self, agent_id: UUID) -> AgentSwarmInstance:
        """
        Pause a running agent

        Args:
            agent_id: Agent instance ID

        Returns:
            Updated agent instance

        Raises:
            ValueError: If agent not found or not running
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent.status != AgentSwarmStatus.RUNNING:
            raise ValueError(f"Cannot pause agent in {agent.status} state")

        agent.status = AgentSwarmStatus.PAUSED
        agent.paused_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(agent)

        logger.info(
            f"Agent paused: {agent.name} (ID: {agent.id})",
            extra={"agent_id": str(agent.id)}
        )

        return agent

    def resume_agent(self, agent_id: UUID) -> AgentSwarmInstance:
        """
        Resume a paused agent

        Args:
            agent_id: Agent instance ID

        Returns:
            Updated agent instance

        Raises:
            ValueError: If agent not found or not paused
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent.status != AgentSwarmStatus.PAUSED:
            raise ValueError(f"Cannot resume agent in {agent.status} state")

        agent.status = AgentSwarmStatus.RUNNING
        agent.paused_at = None

        # Recalculate next heartbeat if enabled
        if agent.heartbeat_enabled and agent.heartbeat_interval:
            agent.next_heartbeat_at = self._calculate_next_heartbeat(agent.heartbeat_interval)

        self.db.commit()
        self.db.refresh(agent)

        logger.info(
            f"Agent resumed: {agent.name} (ID: {agent.id})",
            extra={"agent_id": str(agent.id)}
        )

        return agent

    def delete_agent(self, agent_id: UUID) -> None:
        """
        Delete agent (soft delete - mark as stopped)

        Args:
            agent_id: Agent instance ID

        Raises:
            ValueError: If agent not found
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        agent.status = AgentSwarmStatus.STOPPED
        agent.stopped_at = datetime.now(timezone.utc)

        self.db.commit()

        logger.info(
            f"Agent deleted: {agent.name} (ID: {agent.id})",
            extra={"agent_id": str(agent.id)}
        )

    async def execute_heartbeat(self, agent_id: UUID) -> HeartbeatExecutionResponse:
        """
        Execute heartbeat for an agent

        Args:
            agent_id: Agent instance ID

        Returns:
            Heartbeat execution response

        Raises:
            ValueError: If agent not found, not running, or heartbeat not enabled
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if agent.status != AgentSwarmStatus.RUNNING:
            raise ValueError(f"Cannot execute heartbeat for agent in {agent.status} state")

        if not agent.heartbeat_enabled:
            raise ValueError("Heartbeat not enabled for this agent")

        # Create execution record
        execution = AgentHeartbeatExecution(
            agent_id=agent.id,
            status=HeartbeatExecutionStatus.RUNNING,
            checklist_items=agent.heartbeat_checklist,
            started_at=datetime.now(timezone.utc)
        )

        self.db.add(execution)
        self.db.commit()

        try:
            # Connect to OpenClaw if not connected
            if self.openclaw_bridge and not self.openclaw_bridge.is_connected:
                await self.openclaw_bridge.connect()

            # Build heartbeat message
            heartbeat_message = self._build_heartbeat_message(agent)

            # Execute heartbeat via OpenClaw
            if self.openclaw_bridge:
                result = await self.openclaw_bridge.send_to_agent(
                    session_key=agent.openclaw_session_key,
                    message=heartbeat_message,
                    metadata={"type": "heartbeat", "execution_id": str(execution.id)}
                )
            else:
                # Mock execution if OpenClaw not available
                logger.warning("OpenClaw not configured, mock heartbeat execution")
                result = {"success": True}

            # Update execution record
            execution.status = HeartbeatExecutionStatus.COMPLETED
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_seconds = (execution.completed_at - execution.started_at).total_seconds()

            # Update agent timestamps
            agent.last_heartbeat_at = datetime.now(timezone.utc)
            if agent.heartbeat_interval:
                agent.next_heartbeat_at = self._calculate_next_heartbeat(agent.heartbeat_interval)

            self.db.commit()
            self.db.refresh(execution)

            logger.info(
                f"Heartbeat executed: {agent.name} (ID: {agent.id})",
                extra={
                    "agent_id": str(agent.id),
                    "execution_id": str(execution.id),
                    "duration_seconds": execution.duration_seconds
                }
            )

            return HeartbeatExecutionResponse(
                id=execution.id,
                agent_id=execution.agent_id,
                status=execution.status,
                checklist_items=execution.checklist_items,
                started_at=execution.started_at,
                completed_at=execution.completed_at,
                duration_seconds=execution.duration_seconds,
                error_message=execution.error_message
            )

        except Exception as e:
            # Update execution record
            execution.status = HeartbeatExecutionStatus.FAILED
            execution.error_message = str(e)
            execution.completed_at = datetime.now(timezone.utc)
            execution.duration_seconds = (execution.completed_at - execution.started_at).total_seconds()

            # Update agent error tracking
            agent.error_message = str(e)
            agent.error_count += 1
            agent.last_error_at = datetime.now(timezone.utc)

            self.db.commit()

            logger.error(
                f"Heartbeat execution failed: {agent.name} (ID: {agent.id}): {e}",
                extra={
                    "agent_id": str(agent.id),
                    "execution_id": str(execution.id),
                    "error": str(e)
                }
            )
            raise

    def update_agent_settings(
        self,
        agent_id: UUID,
        request: AgentUpdateSettingsRequest
    ) -> AgentSwarmInstance:
        """
        Update agent settings

        Args:
            agent_id: Agent instance ID
            request: Settings update request

        Returns:
            Updated agent instance

        Raises:
            ValueError: If agent not found
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Update fields if provided
        if request.persona is not None:
            agent.persona = request.persona

        if request.model is not None:
            agent.model = request.model

        if request.configuration is not None:
            agent.configuration = request.configuration

        if request.heartbeat is not None:
            agent.heartbeat_enabled = request.heartbeat.enabled
            agent.heartbeat_interval = HeartbeatInterval(request.heartbeat.interval) if request.heartbeat.interval else None
            agent.heartbeat_checklist = request.heartbeat.checklist

            # Recalculate next heartbeat if enabled and running
            if agent.heartbeat_enabled and agent.heartbeat_interval and agent.status == AgentSwarmStatus.RUNNING:
                agent.next_heartbeat_at = self._calculate_next_heartbeat(agent.heartbeat_interval)

        self.db.commit()
        self.db.refresh(agent)

        logger.info(
            f"Agent settings updated: {agent.name} (ID: {agent.id})",
            extra={"agent_id": str(agent.id)}
        )

        return agent

    def get_agent(self, agent_id: UUID) -> Optional[AgentSwarmInstance]:
        """
        Get agent by ID

        Args:
            agent_id: Agent instance ID

        Returns:
            Agent instance or None if not found
        """
        return self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

    def list_agents(
        self,
        user_id: Optional[UUID] = None,
        status: Optional[AgentSwarmStatus] = None,
        limit: int = 100,
        offset: int = 0
    ) -> tuple[List[AgentSwarmInstance], int]:
        """
        List agents with filtering

        Args:
            user_id: Filter by user ID
            status: Filter by status
            limit: Maximum results
            offset: Pagination offset

        Returns:
            Tuple of (agent list, total count)
        """
        query = self.db.query(AgentSwarmInstance)

        if user_id:
            query = query.filter(AgentSwarmInstance.user_id == user_id)

        if status:
            query = query.filter(AgentSwarmInstance.status == status)

        total = query.count()
        agents = query.order_by(AgentSwarmInstance.created_at.desc()).offset(offset).limit(limit).all()

        return agents, total

    def _generate_session_key(self, name: str) -> str:
        """
        Generate OpenClaw session key from agent name

        Args:
            name: Agent name

        Returns:
            Session key in format "agent:web:{name}"
        """
        # Sanitize name for session key
        sanitized_name = name.lower().replace(" ", "-").replace("_", "-")
        return f"agent:web:{sanitized_name}"

    def _calculate_next_heartbeat(self, interval: HeartbeatInterval) -> datetime:
        """
        Calculate next heartbeat execution time

        Args:
            interval: Heartbeat interval

        Returns:
            Next heartbeat timestamp
        """
        now = datetime.now(timezone.utc)

        interval_mapping = {
            HeartbeatInterval.FIVE_MINUTES: timedelta(minutes=5),
            HeartbeatInterval.FIFTEEN_MINUTES: timedelta(minutes=15),
            HeartbeatInterval.THIRTY_MINUTES: timedelta(minutes=30),
            HeartbeatInterval.ONE_HOUR: timedelta(hours=1),
            HeartbeatInterval.TWO_HOURS: timedelta(hours=2),
        }

        delta = interval_mapping.get(interval, timedelta(minutes=15))
        return now + delta

    def _build_provisioning_message(self, agent: AgentSwarmInstance) -> str:
        """
        Build provisioning message for OpenClaw

        Args:
            agent: Agent instance

        Returns:
            Provisioning message text
        """
        message = f"Provisioning agent: {agent.name}\n\n"

        if agent.persona:
            message += f"Persona: {agent.persona}\n\n"

        message += f"Model: {agent.model}\n"
        message += f"Session: {agent.openclaw_session_key}\n"

        if agent.heartbeat_enabled:
            message += f"\nHeartbeat: Enabled ({agent.heartbeat_interval})\n"

        return message

    def _build_heartbeat_message(self, agent: AgentSwarmInstance) -> str:
        """
        Build heartbeat checklist message for OpenClaw

        Args:
            agent: Agent instance

        Returns:
            Heartbeat message text
        """
        message = f"Heartbeat checklist for {agent.name}:\n\n"

        if agent.heartbeat_checklist:
            for idx, task in enumerate(agent.heartbeat_checklist, 1):
                message += f"{idx}. {task}\n"

        return message
