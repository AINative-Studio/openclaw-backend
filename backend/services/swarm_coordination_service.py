"""
Swarm Coordination Service

Coordinates task management for agent swarms by polling GitHub issues,
assigning tasks to available agents, and managing task lifecycle.

Features:
- GitHub issue polling for agent-task labeled issues
- Intelligent agent selection using multiple strategies
- Automatic GitHub label and comment updates
- Task assignment tracking

Refs #141
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_

from backend.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
)

# Configure logging
logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task status enumeration"""
    UNASSIGNED = "unassigned"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentSelectionStrategy(str, Enum):
    """Agent selection strategy enumeration"""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    CAPABILITY_MATCH = "capability_match"
    RANDOM = "random"


@dataclass
class GitHubTask:
    """
    Represents a task from GitHub issue

    Attributes:
        issue_number: GitHub issue number
        title: Issue title
        body: Issue description
        labels: List of label names
        status: Current task status
        requirements: Extracted task requirements (model, skills, etc.)
        created_at: Issue creation timestamp
        updated_at: Last update timestamp
        url: GitHub issue URL
        assignee: Current assignee (if any)
    """
    issue_number: int
    title: str
    body: str
    labels: List[str]
    status: TaskStatus
    requirements: Dict[str, Any]
    created_at: datetime
    updated_at: datetime
    url: str
    assignee: Optional[str] = None


@dataclass
class TaskAssignmentResult:
    """
    Result of task assignment operation

    Attributes:
        success: Whether assignment succeeded
        issue_number: GitHub issue number
        agent_id: Assigned agent UUID (if successful)
        agent_name: Assigned agent name (if successful)
        error_message: Error message (if failed)
        assigned_at: Assignment timestamp
    """
    success: bool
    issue_number: int
    agent_id: Optional[UUID] = None
    agent_name: Optional[str] = None
    error_message: Optional[str] = None
    assigned_at: Optional[datetime] = None


class SwarmCoordinationService:
    """
    Swarm Coordination Service

    Manages task assignment for agent swarms by:
    1. Polling GitHub for agent-task issues
    2. Selecting appropriate agents using configurable strategies
    3. Assigning tasks and updating GitHub with labels/comments
    4. Tracking assignment state
    """

    def __init__(
        self,
        db: Session,
        github_client: Any,
        repository: str,
        polling_interval_seconds: int = 60,
        default_strategy: AgentSelectionStrategy = AgentSelectionStrategy.ROUND_ROBIN,
    ):
        """
        Initialize coordination service

        Args:
            db: Database session
            github_client: GitHub API client (async)
            repository: GitHub repository in format "owner/repo"
            polling_interval_seconds: Polling interval (default: 60)
            default_strategy: Default agent selection strategy
        """
        self.db = db
        self.github_client = github_client
        self.repository = repository
        self.polling_interval_seconds = polling_interval_seconds
        self.default_strategy = default_strategy

        # Round-robin state
        self._round_robin_index = 0

        logger.info(
            f"SwarmCoordinationService initialized for repository {repository}",
            extra={
                "repository": repository,
                "polling_interval": polling_interval_seconds,
                "default_strategy": default_strategy.value,
            }
        )

    async def poll_github_tasks(self) -> List[GitHubTask]:
        """
        Poll GitHub for open agent-task issues

        Returns:
            List of GitHubTask objects for unassigned tasks

        Raises:
            Exception: If GitHub API call fails
        """
        logger.info("Polling GitHub for agent-task issues")

        try:
            # Fetch open issues with agent-task label
            issues = await self.github_client.get_issues(
                labels="agent-task",
                state="open",
            )

            logger.info(
                f"Fetched {len(issues)} issues from GitHub",
                extra={"issue_count": len(issues)}
            )

            # Convert to GitHubTask objects and filter unassigned
            tasks = []
            for issue in issues:
                # Skip if already assigned
                if issue.get("assignee") is not None:
                    continue

                task = self._parse_github_issue(issue)
                tasks.append(task)

            logger.info(
                f"Found {len(tasks)} unassigned tasks",
                extra={"unassigned_count": len(tasks)}
            )

            return tasks

        except Exception as e:
            logger.error(
                f"Failed to poll GitHub tasks: {e}",
                extra={"error": str(e)}
            )
            raise

    async def assign_task_to_agent(
        self,
        task: GitHubTask,
        strategy: Optional[AgentSelectionStrategy] = None,
    ) -> TaskAssignmentResult:
        """
        Assign task to an available agent

        Args:
            task: GitHubTask to assign
            strategy: Agent selection strategy (uses default if None)

        Returns:
            TaskAssignmentResult with assignment details
        """
        strategy = strategy or self.default_strategy

        logger.info(
            f"Assigning task #{task.issue_number} using {strategy.value} strategy",
            extra={
                "issue_number": task.issue_number,
                "strategy": strategy.value,
            }
        )

        try:
            # Get available agents
            agents = self._get_available_agents()

            if not agents:
                error_msg = "No available agents for task assignment"
                logger.warning(error_msg)
                return TaskAssignmentResult(
                    success=False,
                    issue_number=task.issue_number,
                    error_message=error_msg,
                )

            # Select agent based on strategy
            selected_agent = await self._select_agent(
                agents=agents,
                task=task,
                strategy=strategy,
            )

            if not selected_agent:
                error_msg = "No suitable agent found for task requirements"
                logger.warning(error_msg)
                return TaskAssignmentResult(
                    success=False,
                    issue_number=task.issue_number,
                    error_message=error_msg,
                )

            # Update GitHub with assignment
            await self._update_github_assignment(
                task=task,
                agent=selected_agent,
            )

            assigned_at = datetime.now(timezone.utc)

            logger.info(
                f"Task #{task.issue_number} assigned to agent {selected_agent.name}",
                extra={
                    "issue_number": task.issue_number,
                    "agent_id": str(selected_agent.id),
                    "agent_name": selected_agent.name,
                }
            )

            return TaskAssignmentResult(
                success=True,
                issue_number=task.issue_number,
                agent_id=selected_agent.id,
                agent_name=selected_agent.name,
                assigned_at=assigned_at,
            )

        except Exception as e:
            error_msg = f"Failed to assign task: {str(e)}"
            logger.error(
                error_msg,
                extra={
                    "issue_number": task.issue_number,
                    "error": str(e),
                }
            )
            return TaskAssignmentResult(
                success=False,
                issue_number=task.issue_number,
                error_message=error_msg,
            )

    async def process_pending_tasks(self) -> Dict[str, Any]:
        """
        Main coordination loop: poll and assign tasks

        Returns:
            Dictionary with processing statistics

        Raises:
            Exception: If critical error occurs during processing
        """
        logger.info("Processing pending tasks")

        # Poll for tasks
        tasks = await self.poll_github_tasks()

        # Assign each task
        results = []
        for task in tasks:
            result = await self.assign_task_to_agent(task=task)
            results.append(result)

        # Calculate statistics
        successful_assignments = sum(1 for r in results if r.success)
        failed_assignments = sum(1 for r in results if not r.success)

        logger.info(
            f"Processed {len(tasks)} tasks: "
            f"{successful_assignments} assigned, {failed_assignments} failed",
            extra={
                "tasks_polled": len(tasks),
                "tasks_assigned": successful_assignments,
                "tasks_failed": failed_assignments,
            }
        )

        return {
            "tasks_polled": len(tasks),
            "tasks_assigned": successful_assignments,
            "tasks_failed": failed_assignments,
            "assignment_results": [
                {
                    "issue_number": r.issue_number,
                    "success": r.success,
                    "agent_id": str(r.agent_id) if r.agent_id else None,
                    "agent_name": r.agent_name,
                    "error_message": r.error_message,
                }
                for r in results
            ],
        }

    def _parse_github_issue(self, issue: Dict[str, Any]) -> GitHubTask:
        """
        Parse GitHub issue into GitHubTask object

        Args:
            issue: GitHub issue dictionary

        Returns:
            GitHubTask object
        """
        # Extract labels
        labels = [label["name"] for label in issue.get("labels", [])]

        # Parse requirements from body
        requirements = self._extract_requirements(issue.get("body", ""))

        # Parse timestamps
        created_at = datetime.fromisoformat(
            issue["created_at"].replace("Z", "+00:00")
        )
        updated_at = datetime.fromisoformat(
            issue["updated_at"].replace("Z", "+00:00")
        )

        # Determine status
        status = TaskStatus.UNASSIGNED
        if issue.get("assignee"):
            status = TaskStatus.ASSIGNED

        return GitHubTask(
            issue_number=issue["number"],
            title=issue["title"],
            body=issue.get("body", ""),
            labels=labels,
            status=status,
            requirements=requirements,
            created_at=created_at,
            updated_at=updated_at,
            url=issue["html_url"],
            assignee=issue.get("assignee", {}).get("login") if issue.get("assignee") else None,
        )

    def _extract_requirements(self, body: str) -> Dict[str, Any]:
        """
        Extract task requirements from issue body

        Args:
            body: Issue body text

        Returns:
            Dictionary of requirements
        """
        requirements = {}

        if not body:
            return requirements

        # Simple extraction - look for common patterns
        lines = body.lower().split("\n")

        for line in lines:
            # Model requirement
            if "model:" in line:
                model = line.split("model:")[-1].strip()
                requirements["model"] = model

            # Persona requirement
            if "persona:" in line:
                persona = line.split("persona:")[-1].strip()
                requirements["persona"] = persona

            # Skills requirement
            if "skills:" in line:
                skills = line.split("skills:")[-1].strip()
                requirements["skills"] = skills

            # Priority
            if "priority:" in line:
                priority = line.split("priority:")[-1].strip()
                requirements["priority"] = priority

        return requirements

    def _get_available_agents(self) -> List[AgentSwarmInstance]:
        """
        Get list of available agents (RUNNING status)

        Returns:
            List of available agent instances
        """
        agents = (
            self.db.query(AgentSwarmInstance)
            .filter(AgentSwarmInstance.status == AgentSwarmStatus.RUNNING)
            .all()
        )

        logger.debug(
            f"Found {len(agents)} available agents",
            extra={"available_count": len(agents)}
        )

        return agents

    async def _select_agent(
        self,
        agents: List[AgentSwarmInstance],
        task: GitHubTask,
        strategy: AgentSelectionStrategy,
    ) -> Optional[AgentSwarmInstance]:
        """
        Select agent based on strategy

        Args:
            agents: List of available agents
            task: Task to assign
            strategy: Selection strategy

        Returns:
            Selected agent or None
        """
        if not agents:
            return None

        if strategy == AgentSelectionStrategy.ROUND_ROBIN:
            return self._select_round_robin(agents)

        elif strategy == AgentSelectionStrategy.LEAST_LOADED:
            return await self._select_least_loaded(agents)

        elif strategy == AgentSelectionStrategy.CAPABILITY_MATCH:
            return self._select_by_capability(agents, task)

        elif strategy == AgentSelectionStrategy.RANDOM:
            import random
            return random.choice(agents)

        else:
            # Default to round-robin
            return self._select_round_robin(agents)

    def _select_round_robin(
        self, agents: List[AgentSwarmInstance]
    ) -> AgentSwarmInstance:
        """
        Select agent using round-robin

        Args:
            agents: List of available agents

        Returns:
            Selected agent
        """
        agent = agents[self._round_robin_index % len(agents)]
        self._round_robin_index += 1
        return agent

    async def _select_least_loaded(
        self, agents: List[AgentSwarmInstance]
    ) -> AgentSwarmInstance:
        """
        Select agent with least number of assigned tasks

        Args:
            agents: List of available agents

        Returns:
            Agent with lowest load
        """
        # Get task count for each agent
        agent_loads = []
        for agent in agents:
            task_count = await self._get_agent_task_count(agent.id)
            agent_loads.append((agent, task_count))

        # Sort by task count and select agent with minimum load
        agent_loads.sort(key=lambda x: x[1])
        return agent_loads[0][0]

    def _select_by_capability(
        self,
        agents: List[AgentSwarmInstance],
        task: GitHubTask,
    ) -> Optional[AgentSwarmInstance]:
        """
        Select agent based on capability match

        Args:
            agents: List of available agents
            task: Task with requirements

        Returns:
            Best matching agent or None
        """
        requirements = task.requirements

        if not requirements:
            # No specific requirements, use first agent
            return agents[0]

        # Score each agent based on capability match
        scored_agents = []
        for agent in agents:
            score = self._calculate_capability_score(agent, requirements)
            scored_agents.append((agent, score))

        # Sort by score (descending) and select best match
        scored_agents.sort(key=lambda x: x[1], reverse=True)

        # Return agent with highest score if score > 0
        if scored_agents[0][1] > 0:
            return scored_agents[0][0]

        return None

    def _calculate_capability_score(
        self,
        agent: AgentSwarmInstance,
        requirements: Dict[str, Any],
    ) -> float:
        """
        Calculate capability match score for agent

        Args:
            agent: Agent instance
            requirements: Task requirements

        Returns:
            Score (0-1) indicating match quality
        """
        score = 0.0
        total_criteria = 0

        # Model match
        if "model" in requirements:
            total_criteria += 1
            if agent.model and requirements["model"].lower() in agent.model.lower():
                score += 1.0

        # Persona match
        if "persona" in requirements:
            total_criteria += 1
            if agent.persona and requirements["persona"].lower() in agent.persona.lower():
                score += 1.0

        # Normalize score
        if total_criteria > 0:
            return score / total_criteria

        return 0.0

    async def _get_agent_task_count(self, agent_id: UUID) -> int:
        """
        Get number of active tasks for agent

        Args:
            agent_id: Agent UUID

        Returns:
            Count of active tasks
        """
        # This is a placeholder - in production, query actual task assignments
        # For now, return 0 as we don't have task tracking table yet
        return 0

    async def _update_github_assignment(
        self,
        task: GitHubTask,
        agent: AgentSwarmInstance,
    ) -> None:
        """
        Update GitHub issue with assignment labels and comment

        Args:
            task: GitHubTask being assigned
            agent: Agent assigned to task
        """
        issue_number = task.issue_number

        # Add "assigned" label
        await self.github_client.add_label(
            issue_number=issue_number,
            label="assigned",
        )

        # Add agent-specific label
        agent_label = f"agent:{agent.name.lower().replace(' ', '-')}"
        await self.github_client.add_label(
            issue_number=issue_number,
            label=agent_label,
        )

        # Add assignment comment
        comment = (
            f"Task assigned to agent: **{agent.name}**\n\n"
            f"- Agent ID: `{agent.id}`\n"
            f"- Model: {agent.model}\n"
            f"- Persona: {agent.persona or 'Not specified'}\n"
            f"- Assigned at: {datetime.now(timezone.utc).isoformat()}\n"
        )

        await self.github_client.add_comment(
            issue_number=issue_number,
            comment=comment,
        )

        logger.info(
            f"Updated GitHub issue #{issue_number} with assignment details",
            extra={
                "issue_number": issue_number,
                "agent_id": str(agent.id),
            }
        )
