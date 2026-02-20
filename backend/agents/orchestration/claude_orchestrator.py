"""
Claude Orchestrator - Main orchestration controller for NousCoder agents

Ties together all OpenClaw integration components into a 24/7 autonomous system:
- Receives WhatsApp commands via OpenClaw bridge
- Parses commands (work on issue, status, stop, list)
- Spawns NousCoder agents via spawner
- Monitors agent progress
- Sends status updates to WhatsApp

Architecture:
WhatsApp (@mention) → OpenClaw Gateway → Claude Orchestrator → NousCoder Spawner
                                                 ↓
                                         GitHub Issue Work + PR
                                                 ↓
                                         Status Updates → WhatsApp

Refs #1076
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from dataclasses import dataclass, field

from app.agents.orchestration.command_parser import CommandParser, CommandType, CommandParseError
from app.agents.orchestration.notification_service import NotificationService
from app.agents.swarm.nouscoder_agent_spawner import NousCoderAgentSpawner, AgentLifecycleState

logger = logging.getLogger(__name__)


class WorkflowState(Enum):
    """States in the orchestration workflow"""
    PARSING_COMMAND = "parsing_command"
    SPAWNING_AGENT = "spawning_agent"
    AGENT_READY = "agent_ready"
    WORK_IN_PROGRESS = "work_in_progress"
    PR_CREATED = "pr_created"
    TESTS_RUNNING = "tests_running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


class OrchestrationError(Exception):
    """Raised when orchestration fails"""
    pass


@dataclass
class WorkflowTracker:
    """Tracks state of a workflow for an issue"""
    issue_number: int
    agent_id: Optional[str] = None
    state: WorkflowState = WorkflowState.PARSING_COMMAND
    started_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    pr_url: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "issue_number": self.issue_number,
            "agent_id": self.agent_id,
            "state": self.state.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "pr_url": self.pr_url,
            "error": self.error
        }


class ClaudeOrchestrator:
    """
    Main orchestration controller for Claude-powered NousCoder agents

    Responsibilities:
    - Parse WhatsApp commands
    - Spawn and manage NousCoder agents
    - Monitor workflow progress
    - Send status notifications

    Usage:
        orchestrator = ClaudeOrchestrator(
            spawner=nouscoder_spawner,
            notification_service=notification_service
        )
        result = await orchestrator.handle_whatsapp_command("work on issue #1234")
    """

    def __init__(
        self,
        spawner: NousCoderAgentSpawner,
        notification_service: Optional[NotificationService] = None,
        command_parser: Optional[CommandParser] = None,
        openclaw_bridge: Optional[Any] = None,
        whatsapp_session_key: str = "agent:whatsapp:main"
    ):
        """
        Initialize Claude orchestrator

        Args:
            spawner: NousCoder agent spawner instance
            notification_service: Notification service for WhatsApp updates
            command_parser: Optional command parser (creates default if None)
            openclaw_bridge: Optional OpenClaw bridge (auto-creates notification_service if provided)
            whatsapp_session_key: WhatsApp session key for notifications (default: "agent:whatsapp:main")

        Raises:
            ValueError: If neither notification_service nor openclaw_bridge provided
        """
        self.spawner = spawner

        # Support both initialization patterns
        if notification_service:
            # Direct notification_service provided (production pattern)
            self.notification_service = notification_service
        elif openclaw_bridge:
            # OpenClaw bridge provided (test pattern) - auto-create notification_service
            from app.agents.orchestration.notification_service import NotificationService
            self.notification_service = NotificationService(
                openclaw_bridge=openclaw_bridge,
                whatsapp_session_key=whatsapp_session_key
            )
        else:
            # Neither provided - error
            raise ValueError(
                "Either notification_service or openclaw_bridge must be provided. "
                "Use notification_service for production or openclaw_bridge for testing."
            )

        self.command_parser = command_parser or CommandParser()

        # Track active workflows by issue number
        self.active_workflows: Dict[int, WorkflowTracker] = {}

        logger.info("ClaudeOrchestrator initialized")

    async def handle_whatsapp_command(self, command: str) -> Dict[str, Any]:
        """
        Handle incoming WhatsApp command

        Args:
            command: Raw command string from WhatsApp

        Returns:
            Result dictionary with status and details
        """
        try:
            # Parse command
            parsed = self.command_parser.parse(command)

            # Route to appropriate handler
            if parsed.command_type == CommandType.WORK_ON_ISSUE:
                return await self._handle_work_on_issue(parsed)

            elif parsed.command_type == CommandType.STATUS_CHECK:
                return await self._handle_status_check(parsed)

            elif parsed.command_type == CommandType.STOP_WORK:
                return await self._handle_stop_work(parsed)

            elif parsed.command_type == CommandType.LIST_AGENTS:
                return await self._handle_list_agents(parsed)

            else:
                raise OrchestrationError(f"Unsupported command type: {parsed.command_type}")

        except CommandParseError as e:
            logger.error(f"Command parse error: {e}")
            return {
                "success": False,
                "error": str(e),
                "error_type": "parse_error"
            }

        except Exception as e:
            logger.error(f"Orchestration error: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "error_type": "orchestration_error"
            }

    async def _handle_work_on_issue(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'work on issue' command

        Args:
            parsed: Parsed command

        Returns:
            Result dictionary
        """
        issue_number = parsed.issue_number
        task_description = getattr(parsed, 'task_description', None)

        # Create workflow tracker
        workflow = WorkflowTracker(issue_number=issue_number)
        self.active_workflows[issue_number] = workflow

        try:
            # Spawn agent
            workflow.state = WorkflowState.SPAWNING_AGENT
            logger.info(f"Spawning agent for issue #{issue_number}")

            agent = await self.spawner.spawn_agent_with_retry(
                issue_number=issue_number,
                task_description=task_description,
                max_retries=3
            )

            workflow.agent_id = agent.agent_id
            workflow.state = WorkflowState.AGENT_READY

            # Send spawned notification
            await self.notification_service.notify_agent_spawned(
                issue_number=issue_number,
                agent_id=agent.agent_id
            )

            logger.info(f"Agent {agent.agent_id} spawned successfully for issue #{issue_number}")

            return {
                "success": True,
                "issue_number": issue_number,
                "agent_id": agent.agent_id,
                "state": workflow.state.value
            }

        except Exception as e:
            # Mark workflow as failed
            workflow.state = WorkflowState.FAILED
            workflow.error = str(e)

            # Send error notification
            try:
                await self.notification_service.notify_error(
                    issue_number=issue_number,
                    error_message=str(e)
                )
            except Exception as notify_error:
                logger.error(f"Failed to send error notification: {notify_error}")

            logger.error(f"Failed to spawn agent for issue #{issue_number}: {e}")

            return {
                "success": False,
                "issue_number": issue_number,
                "error": str(e),
                "state": workflow.state.value
            }

    async def _handle_status_check(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'status check' command

        Args:
            parsed: Parsed command

        Returns:
            Status dictionary
        """
        issue_number = parsed.issue_number

        # Check if workflow exists
        if issue_number not in self.active_workflows:
            return {
                "success": True,
                "issue_number": issue_number,
                "status": "No active work found for this issue"
            }

        workflow = self.active_workflows[issue_number]

        # Get agent status if agent exists
        agent_status = None
        if workflow.agent_id:
            agent = self.spawner.get_agent(workflow.agent_id)
            if agent:
                agent_status = {
                    "agent_id": agent.agent_id,
                    "state": agent.state.value,
                    "spawned_at": agent.spawned_at.isoformat()
                }

        return {
            "success": True,
            "issue_number": issue_number,
            "status": workflow.state.value,
            "workflow": workflow.to_dict(),
            "agent": agent_status
        }

    async def _handle_stop_work(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'stop work' command

        Args:
            parsed: Parsed command

        Returns:
            Result dictionary
        """
        issue_number = parsed.issue_number

        # Check if workflow exists
        if issue_number not in self.active_workflows:
            return {
                "success": True,
                "issue_number": issue_number,
                "message": "No active work found for this issue"
            }

        workflow = self.active_workflows[issue_number]

        # Cleanup agent if exists
        if workflow.agent_id:
            try:
                await self.spawner.cleanup_agent(workflow.agent_id)
                logger.info(f"Cleaned up agent {workflow.agent_id} for issue #{issue_number}")
            except Exception as e:
                logger.error(f"Failed to cleanup agent: {e}")

        # Mark workflow as stopped
        workflow.state = WorkflowState.STOPPED
        workflow.completed_at = datetime.now()

        # Remove from active workflows
        del self.active_workflows[issue_number]

        return {
            "success": True,
            "issue_number": issue_number,
            "message": f"Stopped work on issue #{issue_number}"
        }

    async def _handle_list_agents(self, parsed: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle 'list agents' command

        Args:
            parsed: Parsed command

        Returns:
            List of active agents
        """
        # Get all agent statuses from spawner
        status = self.spawner.get_all_agents_status()

        return {
            "success": True,
            **status
        }

    def get_active_workflows(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all active workflows

        Returns:
            Dictionary mapping issue_number to workflow dict
        """
        return {
            issue_num: workflow.to_dict()
            for issue_num, workflow in self.active_workflows.items()
        }

    def get_workflow(self, issue_number: int) -> Optional[Dict[str, Any]]:
        """
        Get workflow for specific issue

        Args:
            issue_number: GitHub issue number

        Returns:
            Workflow dictionary or None
        """
        workflow = self.active_workflows.get(issue_number)
        return workflow.to_dict() if workflow else None
