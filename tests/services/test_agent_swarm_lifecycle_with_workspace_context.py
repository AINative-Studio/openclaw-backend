"""
Agent Swarm Lifecycle Service Tests with Workspace Context

Tests for Issue #107: Update Agent Lifecycle Service for Conversation Context
- ZeroDB client injection
- Workspace auto-creation
- Context propagation (agent_id, user_id, workspace_id)

Following TDD principles - these tests should fail initially.
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from backend.services.agent_swarm_lifecycle_service import AgentSwarmLifecycleService
from backend.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
    HeartbeatInterval
)
from backend.models.workspace import Workspace
from backend.schemas.agent_swarm_lifecycle import (
    AgentProvisionRequest,
    HeartbeatConfig,
    HeartbeatIntervalEnum
)
from backend.integrations.zerodb_client import ZeroDBClient


class TestAgentLifecycleServiceWithZeroDBClient:
    """Test AgentSwarmLifecycleService accepts and uses ZeroDB client"""

    def test_service_accepts_zerodb_client_in_constructor(self):
        """
        GIVEN a database session and ZeroDB client
        WHEN initializing AgentSwarmLifecycleService
        THEN it should accept zerodb_client parameter
        """
        # Arrange
        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        # Act
        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Assert
        assert service.db == mock_db
        assert service.zerodb_client == mock_zerodb_client

    def test_service_stores_zerodb_client_as_instance_variable(self):
        """
        GIVEN AgentSwarmLifecycleService initialized with zerodb_client
        WHEN accessing the zerodb_client attribute
        THEN it should be available as instance variable
        """
        # Arrange
        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        # Act
        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Assert
        assert hasattr(service, 'zerodb_client')
        assert service.zerodb_client is mock_zerodb_client


class TestWorkspaceAutoCreation:
    """Test automatic workspace creation during agent provisioning"""

    @pytest.mark.asyncio
    async def test_get_or_create_default_workspace_creates_new_workspace(self):
        """
        GIVEN no default workspace exists in database
        WHEN calling _get_or_create_default_workspace
        THEN it should create a new workspace with ZeroDB project
        """
        # Arrange - Mock database session
        mock_db = Mock(spec=Session)
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None  # No existing workspace
        mock_db.execute.return_value = mock_result

        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)
        mock_zerodb_client.create_project = AsyncMock(return_value={
            "project_id": "zerodb_proj_123",
            "name": "Default Workspace",
            "description": "Auto-created default workspace"
        })

        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Act
        workspace = await service._get_or_create_default_workspace()

        # Assert
        assert workspace is not None
        assert workspace.name == "Default Workspace"
        assert workspace.slug == "default"
        assert workspace.zerodb_project_id == "zerodb_proj_123"

        # Verify ZeroDB client was called
        mock_zerodb_client.create_project.assert_called_once_with(
            name="Default Workspace",
            description="Auto-created default workspace"
        )

        # Verify database operations
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_or_create_default_workspace_returns_existing_workspace(self):
        """
        GIVEN a default workspace already exists
        WHEN calling _get_or_create_default_workspace
        THEN it should return existing workspace without creating new one
        """
        # Arrange - Mock database session
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
        assert workspace is not None
        assert workspace.id == existing_workspace.id
        assert workspace.zerodb_project_id == "existing_proj_123"

        # Verify ZeroDB client was NOT called (workspace already existed)
        mock_zerodb_client.create_project.assert_not_called()

        # Verify workspace was not added or committed
        mock_db.add.assert_not_called()
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_provision_agent_auto_creates_workspace_if_missing(self):
        """
        GIVEN an agent provision request without workspace_id
        WHEN provisioning the agent
        THEN it should auto-create default workspace
        """
        # Arrange
        user_id = uuid4()
        agent_id = uuid4()

        # Mock agent without workspace_id
        agent = Mock(spec=AgentSwarmInstance)
        agent.id = agent_id
        agent.user_id = user_id
        agent.workspace_id = None  # No workspace initially
        agent.status = AgentSwarmStatus.PROVISIONING
        agent.openclaw_session_key = "test_session"
        agent.name = "Test Agent"

        mock_db = Mock(spec=Session)
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = agent
        mock_db.query.return_value = mock_query

        # Mock workspace creation
        new_workspace = Workspace(
            name="Default Workspace",
            slug="default",
            zerodb_project_id="auto_created_proj_123"
        )
        new_workspace.id = uuid4()

        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None  # No existing workspace
        mock_db.execute.return_value = mock_result

        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)
        mock_zerodb_client.create_project = AsyncMock(return_value={
            "project_id": "auto_created_proj_123",
            "name": "Default Workspace",
            "description": "Auto-created default workspace"
        })

        service = AgentSwarmLifecycleService(
            db=mock_db,
            zerodb_client=mock_zerodb_client
        )

        # Mock OpenClaw bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = False
        mock_bridge.connect = AsyncMock()
        mock_bridge.send_to_agent = AsyncMock(return_value={"message_id": "test_msg"})

        # Mock ProductionOpenClawBridge constructor
        with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge') as MockBridge:
            MockBridge.return_value = mock_bridge

            # Act
            result = await service.provision_agent(agent_id)

        # Assert
        assert agent.workspace_id is not None
        mock_zerodb_client.create_project.assert_called_once()
        assert result.status == AgentSwarmStatus.RUNNING


class TestProductionBridgeInjection:
    """Test ProductionOpenClawBridge receives db and zerodb_client"""

    @pytest.mark.asyncio
    async def test_provision_agent_injects_db_into_bridge(self):
        """
        GIVEN agent provisioning workflow
        WHEN creating ProductionOpenClawBridge
        THEN it should receive db parameter
        """
        # Arrange
        user_id = uuid4()
        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        # Create workspace first
        workspace = Workspace(
            name="Test Workspace",
            slug="test",
            zerodb_project_id="test_proj_123"
        )
        async_db_session.add(workspace)
        async_db_session.commit()

        service = AgentSwarmLifecycleService(
            db=async_db_session,
            zerodb_client=mock_zerodb_client
        )

        request = AgentProvisionRequest(
            name="Test Agent",
            model="anthropic/claude-opus-4-5"
        )

        agent = service.create_agent(user_id, request)
        agent.workspace_id = workspace.id
        async_db_session.commit()

        # Mock ProductionOpenClawBridge
        with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge') as MockBridge:
            mock_bridge_instance = AsyncMock()
            mock_bridge_instance.is_connected = False
            mock_bridge_instance.connect = AsyncMock()
            mock_bridge_instance.send_to_agent = AsyncMock(return_value={"message_id": "test"})
            MockBridge.return_value = mock_bridge_instance

            # Act
            await service.provision_agent(agent.id)

            # Assert - Verify bridge was created with db and zerodb_client
            MockBridge.assert_called()
            call_kwargs = MockBridge.call_args[1]
            assert 'db' in call_kwargs
            assert call_kwargs['db'] == async_db_session
            assert 'zerodb_client' in call_kwargs
            assert call_kwargs['zerodb_client'] == mock_zerodb_client

    @pytest.mark.asyncio
    async def test_provision_agent_injects_zerodb_client_into_bridge(self, async_db_session):
        """
        GIVEN agent provisioning workflow
        WHEN creating ProductionOpenClawBridge
        THEN it should receive zerodb_client parameter
        """
        # Arrange
        user_id = uuid4()
        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        workspace = Workspace(
            name="Test Workspace",
            slug="test",
            zerodb_project_id="test_proj_123"
        )
        async_db_session.add(workspace)
        async_db_session.commit()

        service = AgentSwarmLifecycleService(
            db=async_db_session,
            zerodb_client=mock_zerodb_client
        )

        request = AgentProvisionRequest(
            name="Test Agent",
            model="anthropic/claude-opus-4-5"
        )

        agent = service.create_agent(user_id, request)
        agent.workspace_id = workspace.id
        async_db_session.commit()

        # Mock ProductionOpenClawBridge
        with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge') as MockBridge:
            mock_bridge_instance = AsyncMock()
            mock_bridge_instance.is_connected = False
            mock_bridge_instance.connect = AsyncMock()
            mock_bridge_instance.send_to_agent = AsyncMock(return_value={"message_id": "test"})
            MockBridge.return_value = mock_bridge_instance

            # Act
            await service.provision_agent(agent.id)

            # Assert
            call_kwargs = MockBridge.call_args[1]
            assert call_kwargs['zerodb_client'] is mock_zerodb_client


class TestContextPropagation:
    """Test agent_id, user_id, workspace_id are passed to send_message"""

    @pytest.mark.asyncio
    async def test_provision_agent_passes_context_to_send_to_agent(self, async_db_session):
        """
        GIVEN agent provisioning with context (agent_id, user_id, workspace_id)
        WHEN calling bridge.send_to_agent
        THEN it should receive all context parameters
        """
        # Arrange
        user_id = uuid4()
        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        workspace = Workspace(
            name="Test Workspace",
            slug="test",
            zerodb_project_id="test_proj_123"
        )
        async_db_session.add(workspace)
        async_db_session.commit()

        service = AgentSwarmLifecycleService(
            db=async_db_session,
            zerodb_client=mock_zerodb_client
        )

        request = AgentProvisionRequest(
            name="Context Test Agent",
            persona="Test persona",
            model="anthropic/claude-opus-4-5"
        )

        agent = service.create_agent(user_id, request)
        agent.workspace_id = workspace.id
        async_db_session.commit()

        # Mock bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = False
        mock_bridge.connect = AsyncMock()
        mock_bridge.send_to_agent = AsyncMock(return_value={"message_id": "test_msg"})
        service.openclaw_bridge = mock_bridge

        # Act
        await service.provision_agent(agent.id)

        # Assert - Verify send_to_agent was called with context
        mock_bridge.send_to_agent.assert_called_once()
        call_kwargs = mock_bridge.send_to_agent.call_args[1]

        assert 'agent_id' in call_kwargs
        assert call_kwargs['agent_id'] == agent.id
        assert 'user_id' in call_kwargs
        assert call_kwargs['user_id'] == user_id
        assert 'workspace_id' in call_kwargs
        assert call_kwargs['workspace_id'] == workspace.id

    @pytest.mark.asyncio
    async def test_execute_heartbeat_passes_context_to_send_to_agent(self, async_db_session):
        """
        GIVEN heartbeat execution with agent context
        WHEN calling bridge.send_to_agent
        THEN it should receive agent_id, user_id, workspace_id
        """
        # Arrange
        user_id = uuid4()
        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        workspace = Workspace(
            name="Test Workspace",
            slug="test",
            zerodb_project_id="test_proj_123"
        )
        async_db_session.add(workspace)
        async_db_session.commit()

        service = AgentSwarmLifecycleService(
            db=async_db_session,
            zerodb_client=mock_zerodb_client
        )

        request = AgentProvisionRequest(
            name="Heartbeat Context Agent",
            model="anthropic/claude-opus-4-5",
            heartbeat=HeartbeatConfig(
                enabled=True,
                interval=HeartbeatIntervalEnum.FIVE_MINUTES,
                checklist=["Check 1", "Check 2"]
            )
        )

        agent = service.create_agent(user_id, request)
        agent.status = AgentSwarmStatus.RUNNING
        agent.workspace_id = workspace.id
        async_db_session.commit()

        # Mock bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = True
        mock_bridge.send_to_agent = AsyncMock(return_value={"success": True})
        service.openclaw_bridge = mock_bridge

        # Act
        await service.execute_heartbeat(agent.id)

        # Assert
        mock_bridge.send_to_agent.assert_called_once()
        call_kwargs = mock_bridge.send_to_agent.call_args[1]

        assert call_kwargs['agent_id'] == agent.id
        assert call_kwargs['user_id'] == user_id
        assert call_kwargs['workspace_id'] == workspace.id


class TestBackwardCompatibility:
    """Test that existing workflows still work without breaking changes"""

    @pytest.mark.asyncio
    async def test_provision_agent_works_with_existing_workspace(self, async_db_session):
        """
        GIVEN an agent with existing workspace_id
        WHEN provisioning the agent
        THEN it should use existing workspace without creating new one
        """
        # Arrange
        user_id = uuid4()
        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        existing_workspace = Workspace(
            name="Existing Workspace",
            slug="existing",
            zerodb_project_id="existing_proj_123"
        )
        async_db_session.add(existing_workspace)
        async_db_session.commit()

        service = AgentSwarmLifecycleService(
            db=async_db_session,
            zerodb_client=mock_zerodb_client
        )

        request = AgentProvisionRequest(
            name="Test Agent",
            model="anthropic/claude-opus-4-5"
        )

        agent = service.create_agent(user_id, request)
        agent.workspace_id = existing_workspace.id
        async_db_session.commit()

        # Mock bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = False
        mock_bridge.connect = AsyncMock()
        mock_bridge.send_to_agent = AsyncMock(return_value={"message_id": "test"})
        service.openclaw_bridge = mock_bridge

        # Act
        result = await service.provision_agent(agent.id)

        # Assert
        async_db_session.refresh(agent)
        assert agent.workspace_id == existing_workspace.id

        # Verify no new workspace was created
        mock_zerodb_client.create_project.assert_not_called()
        assert result.status == AgentSwarmStatus.RUNNING

    @pytest.mark.asyncio
    async def test_pause_resume_still_works(self, async_db_session):
        """
        GIVEN existing pause/resume functionality
        WHEN using pause and resume
        THEN they should continue working without changes
        """
        # Arrange
        user_id = uuid4()
        mock_zerodb_client = AsyncMock(spec=ZeroDBClient)

        workspace = Workspace(
            name="Test Workspace",
            slug="test",
            zerodb_project_id="test_proj_123"
        )
        async_db_session.add(workspace)
        async_db_session.commit()

        service = AgentSwarmLifecycleService(
            db=async_db_session,
            zerodb_client=mock_zerodb_client
        )

        request = AgentProvisionRequest(
            name="Pause Resume Agent",
            model="anthropic/claude-opus-4-5",
            heartbeat=HeartbeatConfig(
                enabled=True,
                interval=HeartbeatIntervalEnum.THIRTY_MINUTES,
                checklist=["Check"]
            )
        )

        agent = service.create_agent(user_id, request)
        agent.status = AgentSwarmStatus.RUNNING
        agent.workspace_id = workspace.id
        async_db_session.commit()

        # Act - Pause
        paused_agent = service.pause_agent(agent.id)

        # Assert - Pause works
        assert paused_agent.status == AgentSwarmStatus.PAUSED
        assert paused_agent.paused_at is not None

        # Act - Resume
        resumed_agent = service.resume_agent(agent.id)

        # Assert - Resume works
        assert resumed_agent.status == AgentSwarmStatus.RUNNING
        assert resumed_agent.paused_at is None
        assert resumed_agent.next_heartbeat_at is not None


@pytest.fixture
def async_db_session():
    """Create test database session using Railway PostgreSQL"""
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from backend.db.base_class import Base

    # Use Railway PostgreSQL database
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured - skipping database tests")

    engine = create_engine(database_url, pool_pre_ping=True)

    # Ensure all tables exist
    Base.metadata.create_all(engine)

    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
    session = SessionLocal()

    yield session

    # Cleanup: rollback any uncommitted changes
    session.rollback()
    session.close()
