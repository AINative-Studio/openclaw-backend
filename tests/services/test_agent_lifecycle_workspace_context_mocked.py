"""
Agent Swarm Lifecycle Service Tests with Workspace Context (Mocked)

Tests for Issue #107: Update Agent Lifecycle Service for Conversation Context
Uses comprehensive mocking to avoid database dependencies.

Following TDD principles.
"""

import pytest
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch
from sqlalchemy.orm import Session

from backend.services.agent_swarm_lifecycle_service import AgentSwarmLifecycleService
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance, AgentSwarmStatus
from backend.models.workspace import Workspace
from backend.integrations.zerodb_client import ZeroDBClient


class TestAgentLifecycleServiceConstructor:
    """Test AgentSwarmLifecycleService accepts ZeroDB client"""

    def test_service_accepts_zerodb_client_in_constructor(self):
        """Service should accept zerodb_client parameter"""
        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        assert service.db == mock_db
        assert service.zerodb_client == mock_zerodb_client

    def test_service_accepts_none_zerodb_client(self):
        """Service should work with None zerodb_client (optional parameter)"""
        mock_db = Mock(spec=Session)

        service = AgentSwarmLifecycleService(db=mock_db, zerodb_client=None)

        assert service.db == mock_db
        assert service.zerodb_client is None


class TestWorkspaceHelperMethod:
    """Test _get_or_create_default_workspace helper method"""

    @pytest.mark.asyncio
    async def test_creates_new_workspace_when_none_exists(self):
        """Should create new workspace with ZeroDB project when none exists"""
        # Arrange
        mock_db = Mock(spec=Session)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)
        mock_zerodb_client.create_project = AsyncMock(return_value={
            "project_id": "zerodb_proj_123"
        })

        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Act
        workspace = await service._get_or_create_default_workspace()

        # Assert
        assert workspace.name == "Default Workspace"
        assert workspace.slug == "default"
        assert workspace.zerodb_project_id == "zerodb_proj_123"
        mock_zerodb_client.create_project.assert_called_once()
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_existing_workspace_when_found(self):
        """Should return existing workspace without creating new one"""
        # Arrange
        existing_workspace = Workspace(
            name="Default Workspace",
            slug="default",
            zerodb_project_id="existing_proj_123"
        )
        existing_workspace.id = uuid4()

        mock_db = Mock(spec=Session)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_workspace
        mock_db.execute.return_value = mock_result

        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Act
        workspace = await service._get_or_create_default_workspace()

        # Assert
        assert workspace.id == existing_workspace.id
        assert workspace.zerodb_project_id == "existing_proj_123"
        mock_zerodb_client.create_project.assert_not_called()
        mock_db.add.assert_not_called()


class TestProvisionAgentWorkspaceCreation:
    """Test provision_agent auto-creates workspace"""

    @pytest.mark.asyncio
    async def test_provision_creates_workspace_when_missing(self):
        """Should auto-create default workspace if agent has none"""
        # Arrange
        agent_id = uuid4()
        user_id = uuid4()

        agent = Mock(spec=AgentSwarmInstance)
        agent.id = agent_id
        agent.user_id = user_id
        agent.workspace_id = None  # Missing workspace
        agent.status = AgentSwarmStatus.PROVISIONING
        agent.openclaw_session_key = "test:session:key"
        agent.name = "Test Agent"

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = agent
        mock_db.query.return_value = mock_query

        # Mock workspace creation
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)
        mock_zerodb_client.create_project = AsyncMock(return_value={
            "project_id": "auto_proj_123"
        })

        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Mock bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = False
        mock_bridge.connect = AsyncMock()
        mock_bridge.send_to_agent = AsyncMock(return_value={"message_id": "msg_123"})

        with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge') as MockBridge:
            with patch.dict('os.environ', {'OPENCLAW_GATEWAY_URL': 'http://test', 'OPENCLAW_AUTH_TOKEN': 'token'}):
                MockBridge.return_value = mock_bridge

                # Act
                result = await service.provision_agent(agent_id)

        # Assert
        # Verify workspace creation was triggered
        mock_zerodb_client.create_project.assert_called_once_with(
            name="Default Workspace",
            description="Auto-created default workspace"
        )
        # Verify agent status updated
        assert result.status == AgentSwarmStatus.RUNNING
        # Verify workspace was added to agent (check it was assigned)
        assert agent.workspace_id is not None or mock_db.commit.called


class TestBridgeInjection:
    """Test ProductionOpenClawBridge receives db and zerodb_client"""

    @pytest.mark.asyncio
    async def test_bridge_receives_db_and_zerodb_client(self):
        """Should inject db and zerodb_client into bridge constructor"""
        # Arrange
        agent_id = uuid4()
        workspace_id = uuid4()

        agent = Mock(spec=AgentSwarmInstance)
        agent.id = agent_id
        agent.user_id = uuid4()
        agent.workspace_id = workspace_id  # Already has workspace
        agent.status = AgentSwarmStatus.PROVISIONING
        agent.openclaw_session_key = "test:session"
        agent.name = "Test Agent"

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = agent
        mock_db.query.return_value = mock_query

        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Mock bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = False
        mock_bridge.connect = AsyncMock()
        mock_bridge.send_to_agent = AsyncMock(return_value={"message_id": "msg"})

        with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge') as MockBridge:
            with patch.dict('os.environ', {'OPENCLAW_GATEWAY_URL': 'http://test', 'OPENCLAW_AUTH_TOKEN': 'token'}):
                MockBridge.return_value = mock_bridge

                # Act
                await service.provision_agent(agent_id)

        # Assert - Verify bridge was created with db and zerodb_client
        MockBridge.assert_called_once()
        call_kwargs = MockBridge.call_args[1]
        assert 'db' in call_kwargs
        assert call_kwargs['db'] == mock_db
        assert 'zerodb_client' in call_kwargs
        assert call_kwargs['zerodb_client'] == mock_zerodb_client


class TestContextPropagation:
    """Test agent_id, user_id, workspace_id passed to send_to_agent"""

    @pytest.mark.asyncio
    async def test_provision_passes_context_to_bridge(self):
        """Should pass agent_id, user_id, workspace_id to send_to_agent"""
        # Arrange
        agent_id = uuid4()
        user_id = uuid4()
        workspace_id = uuid4()

        agent = Mock(spec=AgentSwarmInstance)
        agent.id = agent_id
        agent.user_id = user_id
        agent.workspace_id = workspace_id
        agent.status = AgentSwarmStatus.PROVISIONING
        agent.openclaw_session_key = "test:session"
        agent.name = "Test Agent"

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = agent
        mock_db.query.return_value = mock_query

        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Mock bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = False
        mock_bridge.connect = AsyncMock()
        mock_bridge.send_to_agent = AsyncMock(return_value={"message_id": "msg"})

        with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge') as MockBridge:
            with patch.dict('os.environ', {'OPENCLAW_GATEWAY_URL': 'http://test', 'OPENCLAW_AUTH_TOKEN': 'token'}):
                MockBridge.return_value = mock_bridge

                # Act
                await service.provision_agent(agent_id)

        # Assert - Verify send_to_agent received context
        mock_bridge.send_to_agent.assert_called_once()
        call_kwargs = mock_bridge.send_to_agent.call_args[1]
        assert call_kwargs['agent_id'] == agent_id
        assert call_kwargs['user_id'] == user_id
        assert call_kwargs['workspace_id'] == workspace_id

    @pytest.mark.asyncio
    async def test_heartbeat_passes_context_to_bridge(self):
        """Should pass context to send_to_agent during heartbeat execution"""
        # Arrange
        agent_id = uuid4()
        user_id = uuid4()
        workspace_id = uuid4()
        execution_id = uuid4()

        agent = Mock(spec=AgentSwarmInstance)
        agent.id = agent_id
        agent.user_id = user_id
        agent.workspace_id = workspace_id
        agent.status = AgentSwarmStatus.RUNNING
        agent.heartbeat_enabled = True
        agent.heartbeat_checklist = ["Check 1", "Check 2"]
        agent.openclaw_session_key = "test:session"
        agent.name = "Test Agent"
        agent.error_count = 0  # Initialize for error handling

        # Create mock execution object
        mock_execution = Mock()
        mock_execution.id = execution_id
        mock_execution.agent_id = agent_id
        mock_execution.status = "completed"
        mock_execution.checklist_items = ["Check 1", "Check 2"]
        mock_execution.started_at = Mock()
        mock_execution.completed_at = Mock()
        mock_execution.duration_seconds = 1.5
        mock_execution.error_message = None

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = agent
        mock_db.query.return_value = mock_query
        mock_db.add.return_value = None  # Mock add execution
        mock_db.refresh.side_effect = lambda obj: setattr(obj, 'id', execution_id)

        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Mock bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = True
        mock_bridge.send_to_agent = AsyncMock(return_value={"success": True})
        service.openclaw_bridge = mock_bridge

        # Act
        result = await service.execute_heartbeat(agent_id)

        # Assert - Verify send_to_agent received context
        mock_bridge.send_to_agent.assert_called_once()
        call_kwargs = mock_bridge.send_to_agent.call_args[1]
        assert call_kwargs['agent_id'] == agent_id
        assert call_kwargs['user_id'] == user_id
        assert call_kwargs['workspace_id'] == workspace_id
