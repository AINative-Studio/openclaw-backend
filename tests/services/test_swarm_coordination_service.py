"""
Test Suite for Swarm Coordination Service

Tests GitHub polling logic, task assignment, and agent picker functionality.
Follows BDD-style testing with comprehensive mocking.

Refs #141
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from uuid import uuid4
from sqlalchemy.orm import Session

from backend.services.swarm_coordination_service import (
    SwarmCoordinationService,
    GitHubTask,
    TaskAssignmentResult,
    AgentSelectionStrategy,
    TaskStatus,
)
from backend.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
)


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = Mock(spec=Session)
    session.query = Mock()
    session.add = Mock()
    session.commit = Mock()
    session.refresh = Mock()
    return session


@pytest.fixture
def mock_github_client():
    """Mock GitHub API client"""
    client = AsyncMock()
    client.get_issues = AsyncMock()
    client.add_label = AsyncMock()
    client.add_comment = AsyncMock()
    return client


@pytest.fixture
def coordination_service(mock_db_session, mock_github_client):
    """Create coordination service with mocked dependencies"""
    return SwarmCoordinationService(
        db=mock_db_session,
        github_client=mock_github_client,
        repository="aginative/openclaw-backend",
        polling_interval_seconds=60
    )


@pytest.fixture
def sample_github_issue():
    """Sample GitHub issue data"""
    return {
        "number": 141,
        "title": "Implement Task Management Swarm Integration",
        "body": "**Assignment**: Update swarm coordinator\n\n**Requirements**: GitHub polling",
        "labels": [{"name": "agent-task"}, {"name": "high-priority"}],
        "state": "open",
        "created_at": "2026-03-10T10:00:00Z",
        "updated_at": "2026-03-10T10:30:00Z",
        "html_url": "https://github.com/aginative/openclaw-backend/issues/141",
        "assignee": None,
    }


@pytest.fixture
def sample_agent():
    """Sample agent instance"""
    return AgentSwarmInstance(
        id=uuid4(),
        name="TestAgent",
        persona="Backend Developer",
        model="claude-sonnet-4",
        user_id=uuid4(),
        workspace_id=uuid4(),
        status=AgentSwarmStatus.RUNNING,
        openclaw_session_key="agent:web:testagent",
    )


# ============================================================================
# FEATURE: GitHub Issue Polling
# ============================================================================


class TestGitHubIssuePolling:
    """Test suite for GitHub issue polling functionality"""

    @pytest.mark.asyncio
    async def test_poll_github_for_agent_tasks_success(
        self, coordination_service, mock_github_client, sample_github_issue
    ):
        """
        GIVEN a GitHub repository with open agent-task issues
        WHEN the service polls for tasks
        THEN it should return a list of GitHubTask objects
        """
        # Arrange
        mock_github_client.get_issues.return_value = [sample_github_issue]

        # Act
        tasks = await coordination_service.poll_github_tasks()

        # Assert
        assert len(tasks) == 1
        assert isinstance(tasks[0], GitHubTask)
        assert tasks[0].issue_number == 141
        assert tasks[0].title == "Implement Task Management Swarm Integration"
        assert tasks[0].status == TaskStatus.UNASSIGNED
        assert "agent-task" in tasks[0].labels

        # Verify GitHub API called with correct filters
        mock_github_client.get_issues.assert_called_once()
        call_kwargs = mock_github_client.get_issues.call_args.kwargs
        assert call_kwargs["labels"] == "agent-task"
        assert call_kwargs["state"] == "open"

    @pytest.mark.asyncio
    async def test_poll_github_filters_assigned_tasks(
        self, coordination_service, mock_github_client
    ):
        """
        GIVEN GitHub issues with both assigned and unassigned tasks
        WHEN polling for tasks
        THEN only unassigned tasks should be returned
        """
        # Arrange
        unassigned_issue = {
            "number": 141,
            "title": "Unassigned Task",
            "labels": [{"name": "agent-task"}],
            "state": "open",
            "assignee": None,
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": "https://github.com/test/repo/issues/141",
        }
        assigned_issue = {
            "number": 142,
            "title": "Assigned Task",
            "labels": [{"name": "agent-task"}],
            "state": "open",
            "assignee": {"login": "agent-123"},
            "created_at": "2026-03-10T09:00:00Z",
            "updated_at": "2026-03-10T09:30:00Z",
            "html_url": "https://github.com/test/repo/issues/142",
        }
        mock_github_client.get_issues.return_value = [unassigned_issue, assigned_issue]

        # Act
        tasks = await coordination_service.poll_github_tasks()

        # Assert
        assert len(tasks) == 1
        assert tasks[0].issue_number == 141
        assert tasks[0].status == TaskStatus.UNASSIGNED

    @pytest.mark.asyncio
    async def test_poll_github_empty_results(
        self, coordination_service, mock_github_client
    ):
        """
        GIVEN no open agent-task issues on GitHub
        WHEN polling for tasks
        THEN an empty list should be returned
        """
        # Arrange
        mock_github_client.get_issues.return_value = []

        # Act
        tasks = await coordination_service.poll_github_tasks()

        # Assert
        assert tasks == []

    @pytest.mark.asyncio
    async def test_poll_github_handles_api_errors(
        self, coordination_service, mock_github_client
    ):
        """
        GIVEN GitHub API is unavailable
        WHEN polling for tasks
        THEN the service should handle errors gracefully
        """
        # Arrange
        mock_github_client.get_issues.side_effect = Exception("GitHub API error")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await coordination_service.poll_github_tasks()

        assert "GitHub API error" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_poll_github_parses_task_requirements(
        self, coordination_service, mock_github_client
    ):
        """
        GIVEN GitHub issue with requirements in body
        WHEN polling for tasks
        THEN requirements should be extracted
        """
        # Arrange
        issue_with_requirements = {
            "number": 150,
            "title": "Complex Task",
            "body": (
                "**Requirements**:\n"
                "- Model: claude-sonnet-4\n"
                "- Skills: Python, FastAPI\n"
                "- Priority: high\n"
            ),
            "labels": [{"name": "agent-task"}],
            "state": "open",
            "assignee": None,
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": "https://github.com/test/repo/issues/150",
        }
        mock_github_client.get_issues.return_value = [issue_with_requirements]

        # Act
        tasks = await coordination_service.poll_github_tasks()

        # Assert
        assert len(tasks) == 1
        assert tasks[0].requirements is not None
        assert "claude-sonnet-4" in tasks[0].requirements.get("model", "")


# ============================================================================
# FEATURE: Task Assignment Logic
# ============================================================================


class TestTaskAssignment:
    """Test suite for task assignment logic"""

    @pytest.mark.asyncio
    async def test_assign_task_to_available_agent(
        self, coordination_service, mock_db_session, sample_agent
    ):
        """
        GIVEN an unassigned task and available agent
        WHEN assigning the task
        THEN the task should be assigned to the agent
        """
        # Arrange
        task = GitHubTask(
            issue_number=141,
            title="Test Task",
            body="Test description",
            labels=["agent-task"],
            status=TaskStatus.UNASSIGNED,
            requirements={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            url="https://github.com/test/repo/issues/141",
        )

        # Mock agent query
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sample_agent]
        mock_db_session.query.return_value = mock_query

        # Act
        result = await coordination_service.assign_task_to_agent(
            task=task,
            strategy=AgentSelectionStrategy.ROUND_ROBIN
        )

        # Assert
        assert result.success is True
        assert result.agent_id == sample_agent.id
        assert result.issue_number == 141

    @pytest.mark.asyncio
    async def test_assign_task_no_available_agents(
        self, coordination_service, mock_db_session
    ):
        """
        GIVEN an unassigned task but no available agents
        WHEN attempting to assign the task
        THEN assignment should fail gracefully
        """
        # Arrange
        task = GitHubTask(
            issue_number=141,
            title="Test Task",
            body="Test description",
            labels=["agent-task"],
            status=TaskStatus.UNASSIGNED,
            requirements={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            url="https://github.com/test/repo/issues/141",
        )

        # Mock empty agent query
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        mock_db_session.query.return_value = mock_query

        # Act
        result = await coordination_service.assign_task_to_agent(
            task=task,
            strategy=AgentSelectionStrategy.ROUND_ROBIN
        )

        # Assert
        assert result.success is False
        assert result.error_message is not None
        assert "no available agents" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_assign_task_matches_agent_capabilities(
        self, coordination_service, mock_db_session
    ):
        """
        GIVEN a task requiring specific capabilities
        WHEN assigning the task
        THEN only agents with matching capabilities should be considered
        """
        # Arrange
        task = GitHubTask(
            issue_number=141,
            title="Backend Task",
            body="Requires Python expertise",
            labels=["agent-task", "backend"],
            status=TaskStatus.UNASSIGNED,
            requirements={"model": "claude-sonnet-4", "persona": "Backend Developer"},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            url="https://github.com/test/repo/issues/141",
        )

        # Create agents with different capabilities
        backend_agent = AgentSwarmInstance(
            id=uuid4(),
            name="BackendAgent",
            persona="Backend Developer",
            model="claude-sonnet-4",
            user_id=uuid4(),
            workspace_id=uuid4(),
            status=AgentSwarmStatus.RUNNING,
        )

        frontend_agent = AgentSwarmInstance(
            id=uuid4(),
            name="FrontendAgent",
            persona="Frontend Developer",
            model="claude-sonnet-4",
            user_id=uuid4(),
            workspace_id=uuid4(),
            status=AgentSwarmStatus.RUNNING,
        )

        # Mock agent query to return both agents
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [backend_agent, frontend_agent]
        mock_db_session.query.return_value = mock_query

        # Act
        result = await coordination_service.assign_task_to_agent(
            task=task,
            strategy=AgentSelectionStrategy.CAPABILITY_MATCH
        )

        # Assert
        assert result.success is True
        assert result.agent_id == backend_agent.id


# ============================================================================
# FEATURE: Agent Selection Strategies
# ============================================================================


class TestAgentSelectionStrategies:
    """Test suite for different agent selection strategies"""

    @pytest.mark.asyncio
    async def test_round_robin_selection(self, coordination_service, mock_db_session):
        """
        GIVEN multiple available agents
        WHEN using round-robin strategy
        THEN agents should be selected in rotation
        """
        # Arrange
        agents = [
            AgentSwarmInstance(
                id=uuid4(),
                name=f"Agent{i}",
                persona="Developer",
                model="claude-sonnet-4",
                user_id=uuid4(),
                workspace_id=uuid4(),
                status=AgentSwarmStatus.RUNNING,
            )
            for i in range(3)
        ]

        task = GitHubTask(
            issue_number=141,
            title="Test Task",
            body="Test",
            labels=["agent-task"],
            status=TaskStatus.UNASSIGNED,
            requirements={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            url="https://github.com/test/repo/issues/141",
        )

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = agents
        mock_db_session.query.return_value = mock_query

        # Act - Assign multiple tasks
        results = []
        for _ in range(3):
            result = await coordination_service.assign_task_to_agent(
                task=task,
                strategy=AgentSelectionStrategy.ROUND_ROBIN
            )
            results.append(result.agent_id)

        # Assert - Each agent should be selected once
        assert len(set(results)) == 3

    @pytest.mark.asyncio
    async def test_least_loaded_selection(self, coordination_service, mock_db_session):
        """
        GIVEN agents with different workloads
        WHEN using least-loaded strategy
        THEN agent with fewest tasks should be selected
        """
        # Arrange
        agent1 = AgentSwarmInstance(
            id=uuid4(),
            name="BusyAgent",
            persona="Developer",
            model="claude-sonnet-4",
            user_id=uuid4(),
            workspace_id=uuid4(),
            status=AgentSwarmStatus.RUNNING,
        )

        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="IdleAgent",
            persona="Developer",
            model="claude-sonnet-4",
            user_id=uuid4(),
            workspace_id=uuid4(),
            status=AgentSwarmStatus.RUNNING,
        )

        task = GitHubTask(
            issue_number=141,
            title="Test Task",
            body="Test",
            labels=["agent-task"],
            status=TaskStatus.UNASSIGNED,
            requirements={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            url="https://github.com/test/repo/issues/141",
        )

        # Mock agent workload - agent1 has 3 tasks, agent2 has 0
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [agent1, agent2]
        mock_db_session.query.return_value = mock_query

        # Mock task count query
        with patch.object(
            coordination_service,
            "_get_agent_task_count",
            side_effect=[3, 0]
        ):
            # Act
            result = await coordination_service.assign_task_to_agent(
                task=task,
                strategy=AgentSelectionStrategy.LEAST_LOADED
            )

            # Assert
            assert result.success is True
            assert result.agent_id == agent2.id


# ============================================================================
# FEATURE: GitHub Label Automation
# ============================================================================


class TestGitHubLabelAutomation:
    """Test suite for GitHub label automation"""

    @pytest.mark.asyncio
    async def test_add_assigned_label_on_task_assignment(
        self, coordination_service, mock_github_client, mock_db_session, sample_agent
    ):
        """
        GIVEN a task assigned to an agent
        WHEN the assignment is successful
        THEN the 'assigned' label should be added to the GitHub issue
        """
        # Arrange
        task = GitHubTask(
            issue_number=141,
            title="Test Task",
            body="Test",
            labels=["agent-task"],
            status=TaskStatus.UNASSIGNED,
            requirements={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            url="https://github.com/test/repo/issues/141",
        )

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sample_agent]
        mock_db_session.query.return_value = mock_query

        # Act
        result = await coordination_service.assign_task_to_agent(task=task)

        # Assert
        assert result.success is True
        # Should add two labels: "assigned" and "agent:testagent"
        assert mock_github_client.add_label.call_count == 2

        # Verify the "assigned" label was added
        label_calls = [call.kwargs["label"] for call in mock_github_client.add_label.call_args_list]
        assert "assigned" in label_calls

    @pytest.mark.asyncio
    async def test_add_agent_label_with_agent_name(
        self, coordination_service, mock_github_client, mock_db_session, sample_agent
    ):
        """
        GIVEN a task assigned to an agent
        WHEN the assignment is successful
        THEN a label with agent name should be added
        """
        # Arrange
        task = GitHubTask(
            issue_number=141,
            title="Test Task",
            body="Test",
            labels=["agent-task"],
            status=TaskStatus.UNASSIGNED,
            requirements={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            url="https://github.com/test/repo/issues/141",
        )

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sample_agent]
        mock_db_session.query.return_value = mock_query

        # Act
        result = await coordination_service.assign_task_to_agent(task=task)

        # Assert
        assert result.success is True
        # Should add two labels: "assigned" and "agent:testagent"
        assert mock_github_client.add_label.call_count == 2

    @pytest.mark.asyncio
    async def test_add_comment_on_assignment(
        self, coordination_service, mock_github_client, mock_db_session, sample_agent
    ):
        """
        GIVEN a task assigned to an agent
        WHEN the assignment is successful
        THEN a comment should be added to the issue
        """
        # Arrange
        task = GitHubTask(
            issue_number=141,
            title="Test Task",
            body="Test",
            labels=["agent-task"],
            status=TaskStatus.UNASSIGNED,
            requirements={},
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            url="https://github.com/test/repo/issues/141",
        )

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sample_agent]
        mock_db_session.query.return_value = mock_query

        # Act
        result = await coordination_service.assign_task_to_agent(task=task)

        # Assert
        assert result.success is True
        mock_github_client.add_comment.assert_called_once()
        call_args = mock_github_client.add_comment.call_args
        assert call_args.kwargs["issue_number"] == 141
        assert "assigned to" in call_args.kwargs["comment"].lower()
        assert "testagent" in call_args.kwargs["comment"].lower()


# ============================================================================
# FEATURE: Task Coordination Loop
# ============================================================================


class TestTaskCoordinationLoop:
    """Test suite for the main coordination loop"""

    @pytest.mark.asyncio
    async def test_coordination_loop_polls_and_assigns(
        self, coordination_service, mock_github_client, mock_db_session, sample_agent
    ):
        """
        GIVEN the coordination service is running
        WHEN the main loop executes
        THEN it should poll for tasks and assign them
        """
        # Arrange
        issue = {
            "number": 141,
            "title": "Test Task",
            "labels": [{"name": "agent-task"}],
            "state": "open",
            "assignee": None,
            "body": "Test description",
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": "https://github.com/test/repo/issues/141",
        }
        mock_github_client.get_issues.return_value = [issue]

        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [sample_agent]
        mock_db_session.query.return_value = mock_query

        # Act
        result = await coordination_service.process_pending_tasks()

        # Assert
        assert result["tasks_polled"] == 1
        assert result["tasks_assigned"] == 1
        assert len(result["assignment_results"]) == 1

    @pytest.mark.asyncio
    async def test_coordination_loop_handles_errors_gracefully(
        self, coordination_service, mock_github_client
    ):
        """
        GIVEN GitHub API error during polling
        WHEN the coordination loop executes
        THEN it should handle the error gracefully
        """
        # Arrange
        mock_github_client.get_issues.side_effect = Exception("API Error")

        # Act & Assert
        with pytest.raises(Exception) as exc_info:
            await coordination_service.process_pending_tasks()

        assert "API Error" in str(exc_info.value)
