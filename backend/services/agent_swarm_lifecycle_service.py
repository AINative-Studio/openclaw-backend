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
from sqlalchemy import select

from backend.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
    HeartbeatInterval,
    AgentHeartbeatExecution,
    HeartbeatExecutionStatus
)
from backend.models.workspace import Workspace
from backend.models.conversation import Conversation, ConversationStatus
from backend.personality import PersonalityManager
from backend.schemas.agent_swarm_lifecycle import (
    AgentProvisionRequest,
    AgentUpdateSettingsRequest,
    AgentProvisionResponse,
    AgentDetailResponse,
    AgentStatusResponse,
    HeartbeatExecutionResponse,
)
from backend.integrations.zerodb_client import ZeroDBClient

# Initialize logger first
logger = logging.getLogger(__name__)

# Optional import - OpenClaw integration may not be available
try:
    from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge
except ImportError:
    ProductionOpenClawBridge = None
    logger.warning("ProductionOpenClawBridge not available - OpenClaw integration disabled")

# Optional import - ConversationService for context loading
try:
    from backend.services.conversation_service import ConversationService
except ImportError:
    ConversationService = None
    logger.warning("ConversationService not available - conversation context disabled")


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

    def __init__(self, db: Session, zerodb_client: Optional[ZeroDBClient] = None):
        """
        Initialize lifecycle service

        Args:
            db: Database session
            zerodb_client: ZeroDBClient instance for workspace management
        """
        self.db = db
        self.zerodb_client = zerodb_client
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

    async def _get_or_create_default_workspace(self) -> Workspace:
        """
        Get or create default workspace

        Returns:
            Default workspace instance

        Raises:
            ValueError: If zerodb_client not configured
        """
        if not self.zerodb_client:
            raise ValueError("ZeroDBClient not configured - cannot create workspace")

        # Check if default workspace exists
        result = self.db.execute(
            select(Workspace).where(Workspace.slug == "default")
        )
        workspace = result.scalar_one_or_none()

        if not workspace:
            # Create ZeroDB project
            project = await self.zerodb_client.create_project(
                name="Default Workspace",
                description="Auto-created default workspace"
            )

            # Create workspace record
            workspace = Workspace(
                name="Default Workspace",
                slug="default",
                zerodb_project_id=project["project_id"]
            )
            self.db.add(workspace)
            self.db.commit()
            self.db.refresh(workspace)

            logger.info(
                f"Created default workspace with ZeroDB project {project['project_id']}",
                extra={"workspace_id": str(workspace.id), "zerodb_project_id": project["project_id"]}
            )

        return workspace

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

        # Initialize personality files for the agent
        try:
            personality_manager = PersonalityManager()
            personality_manager.initialize_agent_personality(
                agent_id=str(agent.id),
                agent_name=agent.name,
                model=agent.model,
                persona=agent.persona
            )
            logger.info(
                f"Initialized personality files for agent {agent.name}",
                extra={"agent_id": str(agent.id)}
            )
        except Exception as e:
            logger.warning(
                f"Failed to initialize personality files for agent {agent.name}: {e}",
                extra={"agent_id": str(agent.id), "error": str(e)}
            )
            # Don't fail agent creation if personality initialization fails

        return agent

    async def provision_agent(self, agent_id: UUID, conversation_id: Optional[UUID] = None) -> AgentStatusResponse:
        """
        Provision agent by registering with OpenClaw

        Args:
            agent_id: Agent instance ID
            conversation_id: Optional conversation ID to attach to agent

        Returns:
            Agent status response

        Raises:
            ValueError: If agent not found or in wrong state, or conversation validation fails
            ConnectionError: If OpenClaw connection fails
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Validate and attach conversation if provided
        if conversation_id is not None:
            conversation = self.db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()

            if not conversation:
                raise ValueError(f"Conversation {conversation_id} not found")

            # Validate conversation belongs to same workspace
            if conversation.workspace_id != agent.workspace_id:
                raise ValueError("Conversation does not belong to agent's workspace")

            # Attach conversation
            agent.current_conversation_id = conversation_id
            logger.info(
                f"Attached conversation {conversation_id} to agent {agent_id}",
                extra={"agent_id": str(agent_id), "conversation_id": str(conversation_id)}
            )

        # Ensure agent has workspace - auto-create default if missing
        if not agent.workspace_id:
            workspace = await self._get_or_create_default_workspace()
            agent.workspace_id = workspace.id
            self.db.commit()
            self.db.refresh(agent)
            logger.info(
                f"Assigned default workspace to agent {agent.id}",
                extra={"agent_id": str(agent.id), "workspace_id": str(workspace.id)}
            )

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
            # Create or reinitialize bridge with db and zerodb_client
            openclaw_url = os.getenv("OPENCLAW_GATEWAY_URL")
            openclaw_token = os.getenv("OPENCLAW_AUTH_TOKEN")

            if ProductionOpenClawBridge and openclaw_url and openclaw_token:
                # Inject db and zerodb_client into bridge
                self.openclaw_bridge = ProductionOpenClawBridge(
                    url=openclaw_url,
                    token=openclaw_token,
                    db=self.db,
                    zerodb_client=self.zerodb_client
                )

            # Connect to OpenClaw if not connected
            if self.openclaw_bridge and not self.openclaw_bridge.is_connected:
                await self.openclaw_bridge.connect()

            # Load conversation context if conversation attached
            conversation_context = []
            if agent.current_conversation_id:
                conversation_context = await self._load_conversation_context(agent.current_conversation_id)

            # Build provisioning message with conversation context
            provisioning_message = self._build_provisioning_message(agent, conversation_context)

            # Send to OpenClaw with context
            if self.openclaw_bridge:
                result = await self.openclaw_bridge.send_to_agent(
                    session_key=agent.openclaw_session_key,
                    message=provisioning_message,
                    metadata={"type": "provisioning", "agent_id": str(agent.id)},
                    agent_id=agent.id,
                    user_id=agent.user_id,
                    workspace_id=agent.workspace_id
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

            # Execute heartbeat via OpenClaw with context
            if self.openclaw_bridge:
                result = await self.openclaw_bridge.send_to_agent(
                    session_key=agent.openclaw_session_key,
                    message=heartbeat_message,
                    metadata={"type": "heartbeat", "execution_id": str(execution.id)},
                    agent_id=agent.id,
                    user_id=agent.user_id,
                    workspace_id=agent.workspace_id
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

    def _build_provisioning_message(self, agent: AgentSwarmInstance, conversation_context: List = None) -> str:
        """
        Build provisioning message for OpenClaw

        Args:
            agent: Agent instance
            conversation_context: Optional conversation history messages

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

        # Include conversation context if available
        if conversation_context:
            message += f"\n--- Conversation History ({len(conversation_context)} messages) ---\n\n"
            for msg in conversation_context:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                message += f"{role}: {content}\n"
            message += "\n--- End Conversation History ---\n"

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

    async def _load_conversation_context(self, conversation_id: UUID) -> List:
        """
        Load last 10 messages from conversation for context

        Args:
            conversation_id: Conversation UUID

        Returns:
            List of message dictionaries (max 10, most recent first)
        """
        try:
            if not ConversationService or not self.zerodb_client:
                logger.warning("ConversationService or ZeroDB client not available - skipping context load")
                return []

            # Create async session wrapper for ConversationService
            from sqlalchemy.ext.asyncio import AsyncSession
            from backend.db.base import async_session_maker

            async with async_session_maker() as async_db:
                conversation_service = ConversationService(db=async_db, zerodb_client=self.zerodb_client)
                messages = await conversation_service.get_messages(
                    conversation_id=conversation_id,
                    limit=10,
                    offset=0
                )
                return messages

        except Exception as e:
            logger.warning(
                f"Failed to load conversation context for {conversation_id}: {e}",
                extra={"conversation_id": str(conversation_id), "error": str(e)}
            )
            # Graceful degradation - return empty list
            return []

    def update_agent_state(self, agent_id: UUID) -> dict:
        """
        Get agent state including conversation_id

        Args:
            agent_id: Agent instance ID

        Returns:
            Dictionary with agent state information
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            return None

        return {
            "id": str(agent.id),
            "name": agent.name,
            "status": agent.status.value if agent.status else None,
            "conversation_id": str(agent.current_conversation_id) if agent.current_conversation_id else None,
            "workspace_id": str(agent.workspace_id) if agent.workspace_id else None,
            "updated_at": agent.updated_at.isoformat() if agent.updated_at else None
        }

    async def get_agent_conversation_summary(self, agent_id: UUID) -> Optional[dict]:
        """
        Get conversation summary for agent

        Args:
            agent_id: Agent instance ID

        Returns:
            Conversation summary dict or None if no conversation

        Raises:
            ValueError: If agent not found
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.current_conversation_id:
            return None

        # Get conversation details
        conversation = self.db.query(Conversation).filter(
            Conversation.id == agent.current_conversation_id
        ).first()

        if not conversation:
            logger.warning(
                f"Agent {agent_id} references non-existent conversation {agent.current_conversation_id}",
                extra={"agent_id": str(agent_id), "conversation_id": str(agent.current_conversation_id)}
            )
            return None

        return {
            "conversation_id": str(conversation.id),
            "message_count": conversation.message_count,
            "status": conversation.status.value if hasattr(conversation.status, 'value') else str(conversation.status),
            "started_at": conversation.started_at.isoformat() if conversation.started_at else None,
            "last_message_at": conversation.last_message_at.isoformat() if conversation.last_message_at else None,
        }

    async def switch_agent_conversation(self, agent_id: UUID, new_conversation_id: Optional[UUID]) -> AgentSwarmInstance:
        """
        Switch agent to a different conversation

        Args:
            agent_id: Agent instance ID
            new_conversation_id: New conversation ID (or None to clear)

        Returns:
            Updated agent instance

        Raises:
            ValueError: If agent not found, conversation not found, or invalid state
        """
        agent = self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        # Validate agent is in a state where conversation can be switched
        if agent.status not in [AgentSwarmStatus.RUNNING, AgentSwarmStatus.PAUSED]:
            raise ValueError(f"Cannot switch conversation for agent in {agent.status} state")

        # Validate new conversation exists if provided
        if new_conversation_id is not None:
            conversation = self.db.query(Conversation).filter(
                Conversation.id == new_conversation_id
            ).first()

            if not conversation:
                raise ValueError(f"Conversation {new_conversation_id} not found")

            # Validate conversation belongs to same workspace
            if conversation.workspace_id != agent.workspace_id:
                raise ValueError("Conversation does not belong to agent's workspace")

        # Store old conversation for logging
        old_conversation_id = agent.current_conversation_id

        # Switch conversation
        agent.current_conversation_id = new_conversation_id
        self.db.commit()
        self.db.refresh(agent)

        logger.info(
            f"Agent {agent.name} switched conversation from {old_conversation_id} to {new_conversation_id}",
            extra={
                "agent_id": str(agent_id),
                "old_conversation_id": str(old_conversation_id) if old_conversation_id else None,
                "new_conversation_id": str(new_conversation_id) if new_conversation_id else None
            }
        )

        return agent
