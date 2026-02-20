"""
DBOS Workflow Monitoring Service

Monitors DBOS workflows for agent lifecycle operations, providing
observability, metrics, and health monitoring.

Refs #1217
"""

import logging
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone, timedelta
from enum import Enum
import httpx
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from uuid import UUID

from app.core.config import settings

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """DBOS workflow status enumeration"""
    SUCCESS = "SUCCESS"
    ERROR = "ERROR"
    PENDING = "PENDING"
    RETRIES_EXCEEDED = "RETRIES_EXCEEDED"


class WorkflowType(str, Enum):
    """Workflow type enumeration"""
    PROVISION = "provision_agent"
    HEARTBEAT = "heartbeat"
    PAUSE_RESUME = "pause_resume"
    RECOVERY = "recovery"


class DBOSWorkflowMonitor:
    """
    Monitor DBOS workflows for agent lifecycle operations

    Provides:
    - Workflow status tracking
    - Error detection and alerting
    - Performance metrics
    - Health monitoring
    - Recovery coordination
    """

    def __init__(self, openclaw_gateway_url: str):
        """
        Initialize workflow monitor

        Args:
            openclaw_gateway_url: Base URL for OpenClaw Gateway with DBOS
        """
        self.openclaw_gateway_url = openclaw_gateway_url.rstrip('/')
        self.client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def get_workflow_status(self, workflow_uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get workflow status from DBOS

        Args:
            workflow_uuid: DBOS workflow UUID

        Returns:
            Workflow status details or None if not found
        """
        try:
            response = await self.client.get(
                f"{self.openclaw_gateway_url}/workflows/{workflow_uuid}"
            )

            if response.status_code == 404:
                logger.warning(f"Workflow not found: {workflow_uuid}")
                return None

            response.raise_for_status()
            return response.json()

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error getting workflow status: {e}")
            return None
        except Exception as e:
            logger.error(f"Error getting workflow status: {e}")
            return None

    async def check_workflow_health(
        self,
        workflow_uuid: str,
        expected_status: Optional[WorkflowStatus] = None
    ) -> Dict[str, Any]:
        """
        Check workflow health and status

        Args:
            workflow_uuid: DBOS workflow UUID
            expected_status: Expected workflow status

        Returns:
            Health check results
        """
        status = await self.get_workflow_status(workflow_uuid)

        if not status:
            return {
                "healthy": False,
                "reason": "workflow_not_found",
                "workflow_uuid": workflow_uuid
            }

        current_status = status.get("status")
        is_healthy = True
        reason = None

        if expected_status and current_status != expected_status.value:
            is_healthy = False
            reason = f"unexpected_status: expected {expected_status.value}, got {current_status}"

        if current_status == WorkflowStatus.ERROR.value:
            is_healthy = False
            reason = "workflow_failed"

        if current_status == WorkflowStatus.RETRIES_EXCEEDED.value:
            is_healthy = False
            reason = "retries_exceeded"

        return {
            "healthy": is_healthy,
            "workflow_uuid": workflow_uuid,
            "status": current_status,
            "reason": reason,
            "details": status
        }

    async def list_failed_workflows(
        self,
        workflow_type: Optional[WorkflowType] = None,
        since: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        List failed workflows for monitoring

        Args:
            workflow_type: Filter by workflow type
            since: Only workflows since this timestamp

        Returns:
            List of failed workflow details
        """
        # This would query DBOS system tables through the gateway
        # For now, returning placeholder implementation
        logger.info(f"Listing failed workflows (type: {workflow_type}, since: {since})")

        # In production, this would call a custom endpoint on OpenClaw Gateway
        # that queries dbos_system.workflow_status WHERE status = 'ERROR'
        return []

    async def get_workflow_metrics(
        self,
        workflow_type: WorkflowType,
        time_range: timedelta = timedelta(hours=24)
    ) -> Dict[str, Any]:
        """
        Get workflow performance metrics

        Args:
            workflow_type: Type of workflow to analyze
            time_range: Time range for metrics

        Returns:
            Workflow metrics including success rate, duration, etc.
        """
        since = datetime.now(timezone.utc) - time_range

        # In production, this would aggregate metrics from DBOS system tables
        return {
            "workflow_type": workflow_type.value,
            "time_range_hours": time_range.total_seconds() / 3600,
            "since": since.isoformat(),
            "metrics": {
                "total_workflows": 0,
                "successful": 0,
                "failed": 0,
                "pending": 0,
                "success_rate": 0.0,
                "avg_duration_seconds": 0.0,
                "p95_duration_seconds": 0.0,
                "p99_duration_seconds": 0.0
            }
        }

    async def trigger_workflow_recovery(
        self,
        workflow_uuid: str
    ) -> Dict[str, Any]:
        """
        Trigger recovery for a failed workflow

        Args:
            workflow_uuid: DBOS workflow UUID to recover

        Returns:
            Recovery operation result
        """
        try:
            response = await self.client.post(
                f"{self.openclaw_gateway_url}/workflows/{workflow_uuid}/recover"
            )

            response.raise_for_status()
            return {
                "success": True,
                "workflow_uuid": workflow_uuid,
                "result": response.json()
            }

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error triggering recovery: {e}")
            return {
                "success": False,
                "workflow_uuid": workflow_uuid,
                "error": str(e)
            }
        except Exception as e:
            logger.error(f"Error triggering recovery: {e}")
            return {
                "success": False,
                "workflow_uuid": workflow_uuid,
                "error": str(e)
            }

    async def monitor_agent_workflows(
        self,
        agent_id: UUID,
        db: Session
    ) -> Dict[str, Any]:
        """
        Monitor all workflows for a specific agent

        Args:
            agent_id: Agent unique identifier
            db: Database session

        Returns:
            Monitoring summary for agent workflows
        """
        # Query agent's workflow UUIDs from database
        from app.models.agent_swarm_lifecycle import AgentSwarmInstance

        agent = db.query(AgentSwarmInstance).filter(
            AgentSwarmInstance.id == agent_id
        ).first()

        if not agent:
            return {
                "error": "agent_not_found",
                "agent_id": str(agent_id)
            }

        workflows = []

        # Check provisioning workflow if available
        # (In full implementation, workflow UUIDs would be stored in database)

        return {
            "agent_id": str(agent_id),
            "agent_name": agent.name,
            "agent_status": agent.status.value,
            "workflows": workflows,
            "overall_health": "healthy" if agent.error_count == 0 else "degraded"
        }


class WorkflowHealthChecker:
    """
    Background health checker for DBOS workflows

    Periodically checks workflow health and triggers recovery if needed
    """

    def __init__(
        self,
        monitor: DBOSWorkflowMonitor,
        check_interval: int = 60
    ):
        """
        Initialize health checker

        Args:
            monitor: DBOS workflow monitor instance
            check_interval: Health check interval in seconds
        """
        self.monitor = monitor
        self.check_interval = check_interval
        self.running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        """Start background health checking"""
        if self.running:
            logger.warning("Health checker already running")
            return

        self.running = True
        self._task = asyncio.create_task(self._health_check_loop())
        logger.info(f"Workflow health checker started (interval: {self.check_interval}s)")

    async def stop(self):
        """Stop background health checking"""
        self.running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Workflow health checker stopped")

    async def _health_check_loop(self):
        """Background health check loop"""
        while self.running:
            try:
                await self._check_workflows()
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

            await asyncio.sleep(self.check_interval)

    async def _check_workflows(self):
        """Check all active workflows"""
        # In production, this would:
        # 1. Query database for all active agent workflows
        # 2. Check status of each workflow
        # 3. Trigger recovery for failed workflows
        # 4. Send alerts for critical failures

        logger.debug("Running workflow health check")

        # Get failed workflows
        failed = await self.monitor.list_failed_workflows(
            since=datetime.now(timezone.utc) - timedelta(hours=1)
        )

        if failed:
            logger.warning(f"Found {len(failed)} failed workflows")

            # Trigger recovery for failed workflows
            for workflow in failed:
                workflow_uuid = workflow.get("workflow_uuid")
                if workflow_uuid:
                    logger.info(f"Triggering recovery for workflow {workflow_uuid}")
                    await self.monitor.trigger_workflow_recovery(workflow_uuid)


# Global monitor instance
_monitor: Optional[DBOSWorkflowMonitor] = None
_health_checker: Optional[WorkflowHealthChecker] = None


def get_workflow_monitor() -> DBOSWorkflowMonitor:
    """
    Get global workflow monitor instance

    Returns:
        DBOS workflow monitor
    """
    global _monitor

    if _monitor is None:
        openclaw_url = getattr(settings, "OPENCLAW_GATEWAY_URL", "http://localhost:8080")
        _monitor = DBOSWorkflowMonitor(openclaw_url)

    return _monitor


async def start_workflow_health_checker(check_interval: int = 60):
    """
    Start background workflow health checker

    Args:
        check_interval: Health check interval in seconds
    """
    global _health_checker

    if _health_checker is None:
        monitor = get_workflow_monitor()
        _health_checker = WorkflowHealthChecker(monitor, check_interval)

    await _health_checker.start()


async def stop_workflow_health_checker():
    """Stop background workflow health checker"""
    global _health_checker

    if _health_checker:
        await _health_checker.stop()
