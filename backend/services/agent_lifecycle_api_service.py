"""
Agent Lifecycle API Service

Lightweight CRUD service for the agent lifecycle REST API.
Wraps SQLAlchemy operations without OpenClaw bridge integration.
"""

import logging
import os
import time
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
from integrations.openclaw_bridge import OpenClawBridge
from backend.clients.dbos_workflow_client import (
    get_dbos_client,
    WorkflowEndpointUnavailableError,
    DBOSWorkflowError,
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

        # Auto-generate OpenClaw identifiers from agent name
        base_session_key = self._generate_session_key(request.name)
        session_key = base_session_key

        # Check for existing session key and append suffix if needed
        suffix = 0
        while self.db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.openclaw_session_key == session_key
        ).first() is not None:
            suffix += 1
            session_key = f"{base_session_key}-{suffix}"

        # Generate agent ID (without "agent:" prefix and ":main" suffix)
        agent_id = self._generate_agent_id(request.name)
        if suffix > 0:
            agent_id = f"{agent_id}-{suffix}"

        agent = AgentSwarmInstance(
            id=str(uuid4()),
            name=request.name,
            persona=request.persona,
            model=request.model,
            user_id=user_id,
            status=AgentSwarmStatus.PROVISIONING,
            openclaw_session_key=session_key,
            openclaw_agent_id=agent_id,
            heartbeat_enabled=heartbeat_enabled,
            heartbeat_interval=heartbeat_interval,
            heartbeat_checklist=heartbeat_checklist,
            configuration=request.configuration or {},
            error_count=0,
        )
        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)

        logger.info(
            f"Created agent '{request.name}' with auto-generated identifiers: "
            f"session_key={session_key}, agent_id={agent_id}"
        )

        return agent

    async def provision_agent(self, agent_id: str) -> Optional[AgentSwarmInstance]:
        agent = self.get_agent(agent_id)
        if not agent:
            return None

        if agent.status not in (AgentSwarmStatus.PROVISIONING, AgentSwarmStatus.FAILED):
            raise ValueError(
                f"Cannot provision agent in '{agent.status.value}' state. "
                "Only 'provisioning' or 'failed' agents can be provisioned."
            )

        # Generate session key if not exists
        if not agent.openclaw_session_key:
            base_session_key = self._generate_session_key(agent.name)
            session_key = base_session_key

            # Check for existing session key and append suffix if needed
            suffix = 0
            while self.db.query(AgentSwarmInstance).filter(
                AgentSwarmInstance.openclaw_session_key == session_key
            ).first() is not None:
                suffix += 1
                session_key = f"{base_session_key}-{suffix}"

            agent.openclaw_session_key = session_key

        # Try DBOS workflow first for crash-safe provisioning
        dbos_client = get_dbos_client()
        try:
            logger.info(f"Attempting DBOS workflow provisioning for agent {agent_id}")
            workflow_result = await dbos_client.provision_agent(
                agent_id=agent.id,
                name=agent.name,
                persona=agent.persona,
                model=agent.model,
                user_id=agent.user_id,
                session_key=agent.openclaw_session_key,
                heartbeat_enabled=agent.heartbeat_enabled,
                heartbeat_interval=agent.heartbeat_interval.value if agent.heartbeat_interval else None,
                heartbeat_checklist=agent.heartbeat_checklist,
                configuration=agent.configuration
            )
            logger.info(
                f"✓ Agent {agent_id} provisioned via DBOS workflow "
                f"(UUID: {workflow_result.get('workflowUuid')})"
            )

            # Update database to reflect successful provision
            agent.status = AgentSwarmStatus.RUNNING
            agent.provisioned_at = datetime.now(timezone.utc)
            agent.error_message = None
            agent.error_count = 0
            self.db.commit()
            self.db.refresh(agent)
            return agent

        except WorkflowEndpointUnavailableError:
            logger.warning(
                f"⚠️  DBOS workflows unavailable for agent {agent_id}. "
                "Falling back to direct provisioning."
            )
            # Fall through to direct provisioning below
        except DBOSWorkflowError as e:
            logger.error(
                f"❌ DBOS workflow failed for agent {agent_id}: {e}. "
                "Falling back to direct provisioning."
            )
            # Fall through to direct provisioning below

        # Fallback: Direct database provisioning (no crash safety)
        logger.info(f"Provisioning agent {agent_id} via direct database operation")
        agent.status = AgentSwarmStatus.RUNNING
        agent.provisioned_at = datetime.now(timezone.utc)
        agent.error_message = None
        agent.error_count = 0
        self.db.commit()
        self.db.refresh(agent)
        return agent

    def _generate_session_key(self, agent_name: str) -> str:
        """Generate OpenClaw session key from agent name

        Format: agent:{normalized-name}:main
        Example: "Main Agent" -> "agent:main-agent:main"
        """
        # Convert to lowercase, replace spaces/special chars with hyphens
        key = agent_name.lower()
        key = ''.join(c if c.isalnum() else '-' for c in key)
        # Remove consecutive hyphens and strip
        key = '-'.join(filter(None, key.split('-')))
        return f"agent:{key}:main"

    def _generate_agent_id(self, agent_name: str) -> str:
        """Generate OpenClaw agent ID from agent name

        Format: {normalized-name} (no prefix/suffix)
        Example: "Main Agent" -> "main-agent"
        """
        # Convert to lowercase, replace spaces/special chars with hyphens
        agent_id = agent_name.lower()
        agent_id = ''.join(c if c.isalnum() else '-' for c in agent_id)
        # Remove consecutive hyphens and strip
        agent_id = '-'.join(filter(None, agent_id.split('-')))
        return agent_id

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

        # Actually delete the agent record from the database
        self.db.delete(agent)
        self.db.commit()
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

    async def send_message_to_agent(self, agent_id: str, message: str) -> dict:
        """Send a message to an agent via OpenClaw Gateway

        Implements production-ready communication with OpenClaw Gateway Protocol v3.
        Authenticates with the gateway, sends the message to the agent's session,
        and returns the agent's response.

        Args:
            agent_id: ID of the agent to send message to
            message: Message content to send

        Returns:
            dict with response, status, runId, and messageId

        Raises:
            ValueError: If agent not found, not provisioned, or not running
            OpenClawBridgeError: If gateway communication fails
        """
        agent = self.get_agent(agent_id)
        if not agent:
            raise ValueError(f"Agent {agent_id} not found")

        if not agent.openclaw_session_key:
            raise ValueError("Agent must be provisioned before sending messages")

        if agent.status != AgentSwarmStatus.RUNNING:
            raise ValueError(
                f"Cannot send message to agent in '{agent.status.value}' state. "
                "Agent must be 'running'."
            )

        # Get gateway URL from environment
        gateway_url = os.getenv("OPENCLAW_GATEWAY_URL", "ws://localhost:18789")
        gateway_token = os.getenv("OPENCLAW_TOKEN")

        # Convert http:// to ws:// if needed
        if gateway_url.startswith("http://"):
            gateway_url = gateway_url.replace("http://", "ws://")
        elif gateway_url.startswith("https://"):
            gateway_url = gateway_url.replace("https://", "wss://")

        # Create bridge client and connect
        bridge = OpenClawBridge(url=gateway_url, token=gateway_token)

        try:
            # Connect with proper authentication
            await bridge.connect()

            # Send message to agent and wait for final response
            result = await bridge.send_to_agent(
                session_key=agent.openclaw_session_key,
                message=message,
                timeout_seconds=600
            )

            # Extract response text from payloads
            # Result structure: {result: {payloads: [{text: "..."}], meta: {...}}}
            payloads = result.get("result", {}).get("payloads", [])
            response_parts = []

            for payload in payloads:
                text = payload.get("text", "")
                if text:
                    response_parts.append(text)

            response_text = "\n".join(response_parts) if response_parts else "No response received from agent."

            return {
                "response": response_text,
                "status": "completed",
                "runId": result.get("runId"),
                "payloads": payloads,
                "meta": result.get("result", {}).get("meta", {})
            }

        finally:
            # Always close the connection
            await bridge.close()
