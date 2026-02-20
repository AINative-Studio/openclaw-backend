"""
Notification Service for Claude Orchestration Layer

Sends status updates to WhatsApp via OpenClaw bridge at key workflow points:
- Agent spawned
- Work started
- PR created
- Tests passing/failing
- Work completed
- Errors

Refs #1076
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class NotificationType(Enum):
    """Types of notifications"""
    AGENT_SPAWNED = "agent_spawned"
    WORK_STARTED = "work_started"
    PR_CREATED = "pr_created"
    TESTS_PASSING = "tests_passing"
    TESTS_FAILING = "tests_failing"
    WORK_COMPLETED = "work_completed"
    ERROR = "error"


class NotificationError(Exception):
    """Raised when notification sending fails"""
    pass


class NotificationService:
    """
    Service for sending WhatsApp notifications via OpenClaw bridge

    Handles retry logic, connection validation, and message formatting.

    Usage:
        service = NotificationService(openclaw_bridge=bridge)
        await service.notify_agent_spawned(issue_number=1234, agent_id="nouscoder_abc")
    """

    def __init__(
        self,
        openclaw_bridge,
        whatsapp_session_key: str = "agent:whatsapp:main",
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        """
        Initialize notification service

        Args:
            openclaw_bridge: OpenClaw bridge instance
            whatsapp_session_key: Session key for WhatsApp agent
            max_retries: Maximum retry attempts for failed notifications
            retry_delay: Initial delay between retries (exponential backoff)
        """
        self.openclaw_bridge = openclaw_bridge
        self.whatsapp_session_key = whatsapp_session_key
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def notify_agent_spawned(
        self,
        issue_number: int,
        agent_id: str
    ) -> None:
        """
        Send notification that agent has been spawned

        Args:
            issue_number: GitHub issue number
            agent_id: Spawned agent identifier

        Raises:
            NotificationError: If notification fails after retries
        """
        message = f"✓ Agent spawned for issue #{issue_number}\n\nAgent ID: {agent_id}"
        await self._send_notification(message)

    async def notify_work_started(
        self,
        issue_number: int,
        agent_id: str,
        task_description: str
    ) -> None:
        """
        Send notification that work has started

        Args:
            issue_number: GitHub issue number
            agent_id: Agent identifier
            task_description: Description of task

        Raises:
            NotificationError: If notification fails
        """
        message = (
            f"🚀 Work started on issue #{issue_number}\n\n"
            f"Agent: {agent_id}\n"
            f"Task: {task_description}"
        )
        await self._send_notification(message)

    async def notify_pr_created(
        self,
        issue_number: int,
        pr_number: int,
        pr_url: str
    ) -> None:
        """
        Send notification that PR has been created

        Args:
            issue_number: GitHub issue number
            pr_number: Pull request number
            pr_url: Pull request URL

        Raises:
            NotificationError: If notification fails
        """
        message = (
            f"✓ PR #{pr_number} created for issue #{issue_number}\n\n"
            f"URL: {pr_url}"
        )
        await self._send_notification(message)

    async def notify_tests_status(
        self,
        issue_number: int,
        tests_passing: bool,
        coverage_percent: Optional[int] = None,
        error_message: Optional[str] = None
    ) -> None:
        """
        Send notification about test status

        Args:
            issue_number: GitHub issue number
            tests_passing: Whether tests are passing
            coverage_percent: Test coverage percentage (if passing)
            error_message: Error message (if failing)

        Raises:
            NotificationError: If notification fails
        """
        if tests_passing:
            message = f"✓ All tests passing for issue #{issue_number}"
            if coverage_percent is not None:
                message += f"\n\nCoverage: {coverage_percent}%"
        else:
            message = f"❌ Tests failing for issue #{issue_number}"
            if error_message:
                message += f"\n\nError: {error_message}"

        await self._send_notification(message)

    async def notify_work_completed(
        self,
        issue_number: int,
        pr_number: int,
        pr_url: str
    ) -> None:
        """
        Send notification that work is completed

        Args:
            issue_number: GitHub issue number
            pr_number: Pull request number
            pr_url: Pull request URL

        Raises:
            NotificationError: If notification fails
        """
        message = (
            f"✅ Issue #{issue_number} completed\n\n"
            f"PR #{pr_number} ready for review\n"
            f"URL: {pr_url}"
        )
        await self._send_notification(message)

    async def notify_error(
        self,
        issue_number: int,
        error_message: str
    ) -> None:
        """
        Send error notification

        Args:
            issue_number: GitHub issue number
            error_message: Error message

        Raises:
            NotificationError: If notification fails
        """
        message = (
            f"❌ Error on issue #{issue_number}\n\n"
            f"Error: {error_message}"
        )
        await self._send_notification(message)

    async def _send_notification(
        self,
        message: str
    ) -> None:
        """
        Send notification with retry logic

        Args:
            message: Message to send

        Raises:
            NotificationError: If notification fails after max retries
        """
        # Check bridge connection
        if not self.openclaw_bridge.is_connected:
            raise NotificationError("OpenClaw bridge is not connected")

        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(self.max_retries):
            try:
                await self.openclaw_bridge.send_to_agent(
                    session_key=self.whatsapp_session_key,
                    message=message
                )
                logger.info(f"Notification sent successfully: {message[:50]}...")
                return

            except Exception as e:
                last_error = e
                if attempt < self.max_retries - 1:
                    # Exponential backoff
                    delay = self.retry_delay * (2 ** attempt)
                    logger.warning(
                        f"Notification failed (attempt {attempt + 1}): {e}. "
                        f"Retrying in {delay}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"Notification failed after {self.max_retries} attempts: {e}"
                    )

        # All retries exhausted
        raise NotificationError(
            f"Failed to send notification after {self.max_retries} retries. "
            f"Last error: {last_error}"
        )
