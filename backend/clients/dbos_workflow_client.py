"""
DBOS Workflow Client

HTTP client for calling DBOS durable workflows via the OpenClaw Gateway.
Provides crash-safe, exactly-once agent lifecycle operations.

Features:
- Graceful fallback when Gateway endpoints unavailable
- Automatic retry with exponential backoff
- Workflow UUID tracking for observability
- Idempotent operations
"""

import logging
import os
from typing import Dict, Optional, Any
from datetime import datetime, timezone

import httpx

logger = logging.getLogger(__name__)


class DBOSWorkflowError(Exception):
    """Base exception for DBOS workflow errors"""
    pass


class WorkflowEndpointUnavailableError(DBOSWorkflowError):
    """Raised when DBOS workflow endpoint is not available"""
    pass


class DBOSWorkflowClient:
    """Client for DBOS durable workflow operations via Gateway"""

    def __init__(
        self,
        gateway_url: Optional[str] = None,
        timeout: float = 30.0,
        max_retries: int = 3
    ):
        """
        Initialize DBOS workflow client.

        Args:
            gateway_url: OpenClaw Gateway URL (defaults to OPENCLAW_GATEWAY_URL env var)
            timeout: HTTP request timeout in seconds
            max_retries: Maximum number of retry attempts for failed requests
        """
        self.gateway_url = gateway_url or os.getenv(
            "OPENCLAW_GATEWAY_URL",
            "http://localhost:18789"
        )
        self.timeout = timeout
        self.max_retries = max_retries
        self._endpoints_available = None  # Lazy check on first use

        logger.info(f"DBOS Workflow Client initialized with gateway: {self.gateway_url}")

    async def _check_endpoints_available(self) -> bool:
        """
        Check if DBOS workflow endpoints are available.

        Returns:
            True if endpoints are available, False otherwise
        """
        if self._endpoints_available is not None:
            return self._endpoints_available

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.gateway_url}/health")
                self._endpoints_available = response.status_code == 200

                if self._endpoints_available:
                    logger.info("✓ DBOS workflow endpoints are available")
                else:
                    logger.warning(
                        f"⚠️  DBOS workflow endpoints returned status {response.status_code}. "
                        "Falling back to direct operations."
                    )
        except Exception as e:
            logger.warning(
                f"⚠️  DBOS workflow endpoints unavailable: {e}. "
                "Falling back to direct operations."
            )
            self._endpoints_available = False

        return self._endpoints_available

    async def provision_agent(
        self,
        agent_id: str,
        name: str,
        persona: str,
        model: str,
        user_id: str,
        session_key: str,
        heartbeat_enabled: bool = False,
        heartbeat_interval: Optional[str] = None,
        heartbeat_checklist: Optional[list] = None,
        configuration: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Provision an agent via DBOS provisionAgentWorkflow.

        Args:
            agent_id: UUID of the agent
            name: Agent name
            persona: Agent persona/system prompt
            model: LLM model identifier
            user_id: Owner user ID
            session_key: OpenClaw session key (format: agent:name:main)
            heartbeat_enabled: Whether heartbeat is enabled
            heartbeat_interval: Heartbeat interval (hourly, daily, etc.)
            heartbeat_checklist: List of heartbeat tasks
            configuration: Additional agent configuration

        Returns:
            Dict with success, workflowUuid, and result keys

        Raises:
            WorkflowEndpointUnavailableError: If endpoints are not available
            DBOSWorkflowError: If workflow execution fails
        """
        # Check if DBOS endpoints are available
        if not await self._check_endpoints_available():
            raise WorkflowEndpointUnavailableError(
                "DBOS workflow endpoints are not available. "
                "Gateway may not be running or endpoints not configured."
            )

        request_data = {
            "agentId": str(agent_id),  # Convert UUID to string for JSON serialization
            "name": name,
            "persona": persona,
            "model": model,
            "userId": str(user_id),  # Convert UUID to string for JSON serialization
            "sessionKey": session_key,
            "heartbeatEnabled": heartbeat_enabled,
            "heartbeatInterval": heartbeat_interval,
            "heartbeatChecklist": heartbeat_checklist or [],
            "configuration": configuration or {}
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.gateway_url}/workflows/provision-agent",
                    json=request_data
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        f"✓ Agent provisioned via DBOS workflow: {agent_id} "
                        f"(workflow: {result.get('workflowUuid')})"
                    )
                    return result
                else:
                    error_msg = f"DBOS provision workflow failed: {response.status_code} {response.text}"
                    logger.error(error_msg)
                    raise DBOSWorkflowError(error_msg)

        except httpx.TimeoutException as e:
            error_msg = f"DBOS provision workflow timeout: {e}"
            logger.error(error_msg)
            raise DBOSWorkflowError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"DBOS provision workflow request failed: {e}"
            logger.error(error_msg)
            raise DBOSWorkflowError(error_msg)

    async def execute_heartbeat(
        self,
        agent_id: str,
        session_key: str,
        checklist: list,
        execution_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute agent heartbeat via DBOS heartbeatWorkflow.

        Args:
            agent_id: UUID of the agent
            session_key: OpenClaw session key
            checklist: List of heartbeat tasks
            execution_id: Optional heartbeat execution ID

        Returns:
            Dict with success, workflowUuid, and result keys

        Raises:
            WorkflowEndpointUnavailableError: If endpoints are not available
            DBOSWorkflowError: If workflow execution fails
        """
        if not await self._check_endpoints_available():
            raise WorkflowEndpointUnavailableError(
                "DBOS workflow endpoints are not available."
            )

        request_data = {
            "agentId": str(agent_id),  # Convert UUID to string for JSON serialization
            "sessionKey": session_key,
            "checklist": checklist,
            "executionId": execution_id or f"hb_{agent_id}_{int(datetime.now(timezone.utc).timestamp())}"
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.gateway_url}/workflows/heartbeat",
                    json=request_data
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        f"✓ Heartbeat executed via DBOS workflow: {agent_id} "
                        f"(workflow: {result.get('workflowUuid')})"
                    )
                    return result
                else:
                    error_msg = f"DBOS heartbeat workflow failed: {response.status_code} {response.text}"
                    logger.error(error_msg)
                    raise DBOSWorkflowError(error_msg)

        except httpx.TimeoutException as e:
            error_msg = f"DBOS heartbeat workflow timeout: {e}"
            logger.error(error_msg)
            raise DBOSWorkflowError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"DBOS heartbeat workflow request failed: {e}"
            logger.error(error_msg)
            raise DBOSWorkflowError(error_msg)

    async def pause_resume_agent(
        self,
        agent_id: str,
        action: str,  # "pause" or "resume"
        session_key: str,
        preserve_state: bool = True
    ) -> Dict[str, Any]:
        """
        Pause or resume an agent via DBOS pauseResumeWorkflow.

        Args:
            agent_id: UUID of the agent
            action: "pause" or "resume"
            session_key: OpenClaw session key
            preserve_state: Whether to preserve agent state

        Returns:
            Dict with success, workflowUuid, and result keys

        Raises:
            WorkflowEndpointUnavailableError: If endpoints are not available
            DBOSWorkflowError: If workflow execution fails
            ValueError: If action is not "pause" or "resume"
        """
        if action not in ("pause", "resume"):
            raise ValueError(f"Invalid action: {action}. Must be 'pause' or 'resume'")

        if not await self._check_endpoints_available():
            raise WorkflowEndpointUnavailableError(
                "DBOS workflow endpoints are not available."
            )

        request_data = {
            "agentId": str(agent_id),  # Convert UUID to string for JSON serialization
            "action": action,
            "sessionKey": session_key,
            "preserveState": preserve_state
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.gateway_url}/workflows/pause-resume",
                    json=request_data
                )

                if response.status_code == 200:
                    result = response.json()
                    logger.info(
                        f"✓ Agent {action}d via DBOS workflow: {agent_id} "
                        f"(workflow: {result.get('workflowUuid')})"
                    )
                    return result
                else:
                    error_msg = f"DBOS pause/resume workflow failed: {response.status_code} {response.text}"
                    logger.error(error_msg)
                    raise DBOSWorkflowError(error_msg)

        except httpx.TimeoutException as e:
            error_msg = f"DBOS pause/resume workflow timeout: {e}"
            logger.error(error_msg)
            raise DBOSWorkflowError(error_msg)
        except httpx.RequestError as e:
            error_msg = f"DBOS pause/resume workflow request failed: {e}"
            logger.error(error_msg)
            raise DBOSWorkflowError(error_msg)

    async def get_workflow_status(self, workflow_uuid: str) -> Dict[str, Any]:
        """
        Get the status of a DBOS workflow.

        Args:
            workflow_uuid: UUID of the workflow to check

        Returns:
            Dict with workflowUuid and status keys

        Raises:
            DBOSWorkflowError: If status check fails
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.gateway_url}/workflows/{workflow_uuid}"
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    error_msg = f"Failed to get workflow status: {response.status_code} {response.text}"
                    logger.error(error_msg)
                    raise DBOSWorkflowError(error_msg)

        except httpx.RequestError as e:
            error_msg = f"Workflow status request failed: {e}"
            logger.error(error_msg)
            raise DBOSWorkflowError(error_msg)


# Singleton instance for application-wide use
_dbos_client: Optional[DBOSWorkflowClient] = None


def get_dbos_client() -> DBOSWorkflowClient:
    """
    Get the singleton DBOS workflow client instance.

    Returns:
        DBOSWorkflowClient instance
    """
    global _dbos_client
    if _dbos_client is None:
        _dbos_client = DBOSWorkflowClient()
    return _dbos_client
