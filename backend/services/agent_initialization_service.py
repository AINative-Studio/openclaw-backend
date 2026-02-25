"""
Agent Initialization Service using DBOS Workflows
Auto-creates and provisions default agents on startup
"""
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.models.agent_lifecycle import AgentSwarmInstance, AgentSwarmStatus as AgentStatus
from backend.services.agent_lifecycle_api_service import AgentLifecycleApiService

logger = logging.getLogger(__name__)


class AgentInitializationService:
    """
    Manages automatic initialization of default agents using DBOS workflows

    Features:
    - Idempotent agent creation (safe to run multiple times)
    - Automatic provisioning to 'running' status
    - Uses cheapest model (Haiku) for main agent by default
    - DBOS durable workflow for crash-safe initialization
    """

    # Default agent configuration
    DEFAULT_MAIN_AGENT = {
        "name": "Main Agent",
        "persona": (
            "You are the main AI assistant that manages the AINative agent swarm platform via WhatsApp. "
            "You coordinate work between specialized agents and can check their status."
        ),
        "model": "anthropic/claude-3-haiku-20240307",  # Cheapest model
        "openclaw_session_key": "agent:main:main",
        "heartbeat_enabled": False,
    }

    def __init__(self, db: Session):
        self.db = db

    async def initialize_default_agents(self) -> Dict[str, Any]:
        """
        Initialize all default agents (idempotent) via DBOS workflows

        This is designed to be called on application startup.
        Safe to run multiple times - will skip if agents already exist.

        Returns:
            Dict with initialization results
        """
        results = {
            "main_agent": await self._ensure_main_agent_exists(),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        logger.info(f"Agent initialization completed: {results}")
        return results

    async def _ensure_main_agent_exists(self) -> Dict[str, Any]:
        """
        Ensure the main agent exists and is provisioned via DBOS workflows

        Returns:
            Dict with status: 'created', 'already_exists', or 'provisioned'
        """
        # Check if main agent already exists
        stmt = select(AgentSwarmInstance).where(
            AgentSwarmInstance.name == self.DEFAULT_MAIN_AGENT["name"]
        )
        existing_agent = self.db.execute(stmt).scalar_one_or_none()

        if existing_agent:
            # Agent exists - check if it needs provisioning
            if existing_agent.status == AgentStatus.PROVISIONING:
                logger.info(f"Main agent exists but is provisioning, auto-provisioning via DBOS workflow...")

                # Use AgentLifecycleApiService which now has DBOS integration
                lifecycle_service = AgentLifecycleApiService(self.db)
                provisioned_agent = await lifecycle_service.provision_agent(str(existing_agent.id))

                if provisioned_agent:
                    return {
                        "status": "provisioned",
                        "agent_id": str(provisioned_agent.id),
                        "message": "Main agent provisioned via DBOS workflow"
                    }
                else:
                    # Fallback to direct provisioning if DBOS unavailable
                    logger.warning("DBOS workflow failed, using direct provisioning")
                    existing_agent.status = AgentStatus.RUNNING
                    existing_agent.provisioned_at = datetime.now(timezone.utc)
                    existing_agent.updated_at = datetime.now(timezone.utc)
                    self.db.commit()

                    return {
                        "status": "provisioned",
                        "agent_id": str(existing_agent.id),
                        "message": "Main agent provisioned (fallback mode)"
                    }
            else:
                logger.info(f"Main agent already exists with status: {existing_agent.status}")
                return {
                    "status": "already_exists",
                    "agent_id": str(existing_agent.id),
                    "current_status": existing_agent.status.value
                }

        # Create new main agent in PROVISIONING status
        logger.info("Creating new main agent with default configuration...")

        agent = AgentSwarmInstance(
            id=str(uuid4()),
            name=self.DEFAULT_MAIN_AGENT["name"],
            persona=self.DEFAULT_MAIN_AGENT["persona"],
            model=self.DEFAULT_MAIN_AGENT["model"],
            status=AgentStatus.PROVISIONING,  # Will be provisioned via DBOS
            openclaw_session_key=self.DEFAULT_MAIN_AGENT["openclaw_session_key"],
            heartbeat_enabled=self.DEFAULT_MAIN_AGENT["heartbeat_enabled"],
            created_at=datetime.now(timezone.utc),
        )

        self.db.add(agent)
        self.db.commit()
        self.db.refresh(agent)

        logger.info(f"Main agent created: {agent.id}, now provisioning via DBOS workflow...")

        # Provision via AgentLifecycleApiService (which has DBOS integration)
        lifecycle_service = AgentLifecycleApiService(self.db)
        provisioned_agent = await lifecycle_service.provision_agent(str(agent.id))

        if provisioned_agent:
            logger.info(f"✅ Main agent created and provisioned via DBOS: {provisioned_agent.id}")
            return {
                "status": "created",
                "agent_id": str(provisioned_agent.id),
                "model": provisioned_agent.model,
                "message": "Main agent created and provisioned via DBOS workflow"
            }
        else:
            # Fallback
            agent.status = AgentStatus.RUNNING
            agent.provisioned_at = datetime.now(timezone.utc)
            self.db.commit()
            self.db.refresh(agent)

            logger.warning(f"⚠️  Main agent created with fallback provisioning: {agent.id}")
            return {
                "status": "created",
                "agent_id": str(agent.id),
                "model": agent.model,
                "message": "Main agent created and provisioned (fallback mode)"
            }

    def get_or_create_main_agent(self) -> AgentSwarmInstance:
        """
        Get the main agent, creating it if it doesn't exist

        Returns:
            The main agent instance
        """
        stmt = select(AgentSwarmInstance).where(
            AgentSwarmInstance.name == self.DEFAULT_MAIN_AGENT["name"]
        )
        agent = self.db.execute(stmt).scalar_one_or_none()

        if not agent:
            logger.info("Main agent not found, creating...")
            result = self._ensure_main_agent_exists()

            # Fetch the newly created agent
            agent = self.db.execute(stmt).scalar_one()

        return agent


async def initialize_agents_on_startup(db: Session) -> Dict[str, Any]:
    """
    Startup hook to initialize default agents via DBOS workflows

    Call this from your FastAPI startup event or DBOS workflow

    Args:
        db: Database session

    Returns:
        Initialization results
    """
    service = AgentInitializationService(db)
    return await service.initialize_default_agents()


# Singleton instance for convenience
_service_instance: Optional[AgentInitializationService] = None


def get_agent_initialization_service(db: Session) -> AgentInitializationService:
    """Get or create the agent initialization service singleton"""
    global _service_instance
    if _service_instance is None:
        _service_instance = AgentInitializationService(db)
    return _service_instance
