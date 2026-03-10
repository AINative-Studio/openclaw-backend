"""
Integration Tests for Swarm Coordination Service

End-to-end tests for GitHub polling, task assignment, and label automation.

Refs #141
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock, patch
from uuid import uuid4

from backend.services.swarm_coordination_service import (
    SwarmCoordinationService,
    GitHubTask,
    TaskStatus,
    AgentSelectionStrategy,
)
from backend.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
)
from backend.integrations.github_client import GitHubClient


@pytest.fixture
def mock_db_session():
    """Mock database session with transaction support"""
    session = Mock()
    session.query = Mock()
    session.add = Mock()
    session.commit = Mock()
    session.rollback = Mock()
    session.refresh = Mock()
    session.close = Mock()
    return session


@pytest.fixture
def mock_github_client():
    """Mock GitHub client with full API support"""
    client = AsyncMock(spec=GitHubClient)
    client.get_issues = AsyncMock()
    client.get_issue = AsyncMock()
    client.add_label = AsyncMock()
    client.remove_label = AsyncMock()
    client.add_comment = AsyncMock()
    client.update_issue = AsyncMock()
    return client


@pytest.fixture
def sample_agents():
    """Create sample agents with different capabilities"""
    agents = [
        AgentSwarmInstance(
            id=uuid4(),
            name="BackendAgent",
            persona="Backend Developer",
            model="claude-sonnet-4",
            user_id=uuid4(),
            workspace_id=uuid4(),
            status=AgentSwarmStatus.RUNNING,
            openclaw_session_key="agent:web:backendagent",
        ),
        AgentSwarmInstance(
            id=uuid4(),
            name="FrontendAgent",
            persona="Frontend Developer",
            model="claude-sonnet-4",
            user_id=uuid4(),
            workspace_id=uuid4(),
            status=AgentSwarmStatus.RUNNING,
            openclaw_session_key="agent:web:frontendagent",
        ),
        AgentSwarmInstance(
            id=uuid4(),
            name="DevOpsAgent",
            persona="DevOps Engineer",
            model="claude-opus-4",
            user_id=uuid4(),
            workspace_id=uuid4(),
            status=AgentSwarmStatus.RUNNING,
            openclaw_session_key="agent:web:devopsagent",
        ),
    ]
    return agents


@pytest.fixture
def coordination_service(mock_db_session, mock_github_client):
    """Create coordination service with mocked dependencies"""
    return SwarmCoordinationService(
        db=mock_db_session,
        github_client=mock_github_client,
        repository="aginative/openclaw-backend",
        polling_interval_seconds=60,
    )


# ============================================================================
# INTEGRATION TEST: Full Workflow
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_full_workflow_poll_and_assign(
    coordination_service, mock_github_client, mock_db_session, sample_agents
):
    """
    INTEGRATION TEST: Complete workflow from polling to assignment

    GIVEN multiple unassigned GitHub issues and available agents
    WHEN the coordination service processes pending tasks
    THEN all tasks should be polled, assigned, and GitHub updated
    """
    # Arrange: Mock GitHub issues
    github_issues = [
        {
            "number": 141,
            "title": "Backend Task: Add API endpoint",
            "body": "**Requirements**: Python, FastAPI\n**Persona**: Backend Developer",
            "labels": [{"name": "agent-task"}, {"name": "backend"}],
            "state": "open",
            "assignee": None,
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": "https://github.com/test/repo/issues/141",
        },
        {
            "number": 142,
            "title": "Frontend Task: Build UI component",
            "body": "**Requirements**: React, TypeScript\n**Persona**: Frontend Developer",
            "labels": [{"name": "agent-task"}, {"name": "frontend"}],
            "state": "open",
            "assignee": None,
            "created_at": "2026-03-10T11:00:00Z",
            "updated_at": "2026-03-10T11:30:00Z",
            "html_url": "https://github.com/test/repo/issues/142",
        },
    ]

    mock_github_client.get_issues.return_value = github_issues

    # Mock database query for agents
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = sample_agents
    mock_db_session.query.return_value = mock_query

    # Act: Process pending tasks
    result = await coordination_service.process_pending_tasks()

    # Assert: Verify results
    assert result["tasks_polled"] == 2
    assert result["tasks_assigned"] == 2
    assert result["tasks_failed"] == 0

    # Verify GitHub API calls
    mock_github_client.get_issues.assert_called_once()
    assert mock_github_client.add_label.call_count == 4  # 2 tasks x 2 labels each
    assert mock_github_client.add_comment.call_count == 2

    # Verify assignment results
    assignments = result["assignment_results"]
    assert len(assignments) == 2
    assert all(a["success"] for a in assignments)
    assert assignments[0]["issue_number"] == 141
    assert assignments[1]["issue_number"] == 142


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_with_capability_matching(
    coordination_service, mock_github_client, mock_db_session, sample_agents
):
    """
    INTEGRATION TEST: Task assignment with capability matching

    GIVEN tasks with specific capability requirements
    WHEN using capability matching strategy
    THEN tasks should be assigned to agents with matching capabilities
    """
    # Arrange: Backend-specific task
    github_issues = [
        {
            "number": 150,
            "title": "Backend Security Fix",
            "body": "**Model**: claude-sonnet-4\n**Persona**: Backend Developer",
            "labels": [{"name": "agent-task"}, {"name": "security"}],
            "state": "open",
            "assignee": None,
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": "https://github.com/test/repo/issues/150",
        }
    ]

    mock_github_client.get_issues.return_value = github_issues

    # Mock database query
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = sample_agents
    mock_db_session.query.return_value = mock_query

    # Override default strategy to capability matching
    coordination_service.default_strategy = AgentSelectionStrategy.CAPABILITY_MATCH

    # Act
    result = await coordination_service.process_pending_tasks()

    # Assert: Should assign to BackendAgent (matching persona)
    assert result["tasks_assigned"] == 1
    assignment = result["assignment_results"][0]
    assert assignment["success"]
    assert assignment["agent_name"] == "BackendAgent"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_handles_no_available_agents(
    coordination_service, mock_github_client, mock_db_session
):
    """
    INTEGRATION TEST: Graceful handling when no agents available

    GIVEN unassigned tasks but no available agents
    WHEN processing pending tasks
    THEN assignments should fail gracefully with error messages
    """
    # Arrange
    github_issues = [
        {
            "number": 160,
            "title": "Unassignable Task",
            "labels": [{"name": "agent-task"}],
            "state": "open",
            "assignee": None,
            "body": "Test task",
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": "https://github.com/test/repo/issues/160",
        }
    ]

    mock_github_client.get_issues.return_value = github_issues

    # Mock empty agent query
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = []
    mock_db_session.query.return_value = mock_query

    # Act
    result = await coordination_service.process_pending_tasks()

    # Assert
    assert result["tasks_polled"] == 1
    assert result["tasks_assigned"] == 0
    assert result["tasks_failed"] == 1

    assignment = result["assignment_results"][0]
    assert not assignment["success"]
    assert "no available agents" in assignment["error_message"].lower()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_handles_github_api_errors(
    coordination_service, mock_github_client
):
    """
    INTEGRATION TEST: Error handling for GitHub API failures

    GIVEN GitHub API is unavailable
    WHEN processing pending tasks
    THEN appropriate exception should be raised
    """
    # Arrange: Simulate GitHub API error
    mock_github_client.get_issues.side_effect = Exception("GitHub API unavailable")

    # Act & Assert
    with pytest.raises(Exception) as exc_info:
        await coordination_service.process_pending_tasks()

    assert "GitHub API unavailable" in str(exc_info.value)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_workflow_filters_already_assigned_issues(
    coordination_service, mock_github_client, mock_db_session, sample_agents
):
    """
    INTEGRATION TEST: Filter already assigned issues

    GIVEN mix of assigned and unassigned issues
    WHEN polling for tasks
    THEN only unassigned issues should be processed
    """
    # Arrange
    github_issues = [
        {
            "number": 170,
            "title": "Unassigned Task",
            "labels": [{"name": "agent-task"}],
            "state": "open",
            "assignee": None,
            "body": "Unassigned",
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": "https://github.com/test/repo/issues/170",
        },
        {
            "number": 171,
            "title": "Already Assigned Task",
            "labels": [{"name": "agent-task"}, {"name": "assigned"}],
            "state": "open",
            "assignee": {"login": "existing-agent"},
            "body": "Already assigned",
            "created_at": "2026-03-10T09:00:00Z",
            "updated_at": "2026-03-10T09:30:00Z",
            "html_url": "https://github.com/test/repo/issues/171",
        },
    ]

    mock_github_client.get_issues.return_value = github_issues

    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = sample_agents
    mock_db_session.query.return_value = mock_query

    # Act
    result = await coordination_service.process_pending_tasks()

    # Assert: Only one task should be processed
    assert result["tasks_polled"] == 1
    assert result["tasks_assigned"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_round_robin_distribution(
    coordination_service, mock_github_client, mock_db_session, sample_agents
):
    """
    INTEGRATION TEST: Round-robin task distribution

    GIVEN multiple tasks and agents
    WHEN using round-robin strategy
    THEN tasks should be distributed evenly across agents
    """
    # Arrange: 3 tasks for 3 agents
    github_issues = [
        {
            "number": 180 + i,
            "title": f"Task {i}",
            "labels": [{"name": "agent-task"}],
            "state": "open",
            "assignee": None,
            "body": f"Task {i}",
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": f"https://github.com/test/repo/issues/{180 + i}",
        }
        for i in range(3)
    ]

    mock_github_client.get_issues.return_value = github_issues

    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = sample_agents
    mock_db_session.query.return_value = mock_query

    # Act
    result = await coordination_service.process_pending_tasks()

    # Assert: All tasks assigned
    assert result["tasks_assigned"] == 3

    # Verify different agents were selected
    agent_ids = [a["agent_id"] for a in result["assignment_results"]]
    assert len(set(agent_ids)) == 3  # All 3 agents used


@pytest.mark.asyncio
@pytest.mark.integration
async def test_github_label_automation(
    coordination_service, mock_github_client, mock_db_session, sample_agents
):
    """
    INTEGRATION TEST: GitHub label automation

    GIVEN successful task assignment
    WHEN GitHub labels are added
    THEN both 'assigned' and agent-specific labels should be applied
    """
    # Arrange
    github_issues = [
        {
            "number": 190,
            "title": "Test Task",
            "labels": [{"name": "agent-task"}],
            "state": "open",
            "assignee": None,
            "body": "Test",
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": "https://github.com/test/repo/issues/190",
        }
    ]

    mock_github_client.get_issues.return_value = github_issues

    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = [sample_agents[0]]  # Only BackendAgent
    mock_db_session.query.return_value = mock_query

    # Act
    await coordination_service.process_pending_tasks()

    # Assert: Verify label calls
    assert mock_github_client.add_label.call_count == 2

    label_calls = [
        call.kwargs["label"]
        for call in mock_github_client.add_label.call_args_list
    ]

    assert "assigned" in label_calls
    assert "agent:backendagent" in label_calls


@pytest.mark.asyncio
@pytest.mark.integration
async def test_assignment_comment_format(
    coordination_service, mock_github_client, mock_db_session, sample_agents
):
    """
    INTEGRATION TEST: Assignment comment format

    GIVEN successful task assignment
    WHEN comment is added to GitHub
    THEN comment should contain agent details
    """
    # Arrange
    github_issues = [
        {
            "number": 200,
            "title": "Test Task",
            "labels": [{"name": "agent-task"}],
            "state": "open",
            "assignee": None,
            "body": "Test",
            "created_at": "2026-03-10T10:00:00Z",
            "updated_at": "2026-03-10T10:30:00Z",
            "html_url": "https://github.com/test/repo/issues/200",
        }
    ]

    mock_github_client.get_issues.return_value = github_issues

    backend_agent = sample_agents[0]
    mock_query = Mock()
    mock_query.filter.return_value = mock_query
    mock_query.all.return_value = [backend_agent]
    mock_db_session.query.return_value = mock_query

    # Act
    await coordination_service.process_pending_tasks()

    # Assert: Verify comment content
    assert mock_github_client.add_comment.call_count == 1

    comment_call = mock_github_client.add_comment.call_args
    comment_text = comment_call.kwargs["comment"]

    assert "BackendAgent" in comment_text
    assert str(backend_agent.id) in comment_text
    assert "claude-sonnet-4" in comment_text
    assert "Backend Developer" in comment_text
