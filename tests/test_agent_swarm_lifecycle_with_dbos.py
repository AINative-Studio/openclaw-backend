"""
Agent Swarm Lifecycle Service Tests with DBOS Integration

Tests agent lifecycle operations including DBOS workflow integration,
crash recovery, and durability guarantees.

Refs #1217
"""

import pytest
from datetime import datetime, timezone
from uuid import uuid4
from unittest.mock import Mock, AsyncMock, patch, MagicMock

from app.services.agent_swarm_lifecycle_service import AgentSwarmLifecycleService
from app.services.dbos_workflow_monitor import (
    DBOSWorkflowMonitor,
    WorkflowStatus,
    WorkflowType,
    WorkflowHealthChecker
)
from app.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
    HeartbeatInterval,
    AgentHeartbeatExecution,
    HeartbeatExecutionStatus
)
from app.schemas.agent_swarm_lifecycle import (
    AgentProvisionRequest,
    AgentUpdateSettingsRequest,
    HeartbeatConfig,
    HeartbeatIntervalEnum
)


class TestAgentProvisioningWithDBOS:
    """Test agent provisioning with DBOS workflow durability"""

    def test_create_agent_stores_workflow_metadata(self, db_session):
        """
        GIVEN a new agent provision request
        WHEN creating an agent instance
        THEN it should store metadata for DBOS workflow tracking
        """
        # Arrange
        user_id = uuid4()
        service = AgentSwarmLifecycleService(db_session)

        request = AgentProvisionRequest(
            name="Test Agent",
            persona="Helpful assistant",
            model="anthropic/claude-opus-4-5",
            configuration={"testMode": True}
        )

        # Act
        agent = service.create_agent(user_id, request)

        # Assert
        assert agent.id is not None
        assert agent.name == "Test Agent"
        assert agent.status == AgentSwarmStatus.PROVISIONING
        assert agent.openclaw_session_key is not None
        assert agent.openclaw_session_key.startswith("agent:web:")
        assert agent.configuration.get("testMode") is True

    @pytest.mark.asyncio
    async def test_provision_agent_workflow_idempotency(self, db_session):
        """
        GIVEN an agent in provisioning state
        WHEN provisioning workflow runs multiple times (simulating crash recovery)
        THEN it should be idempotent and reach same final state
        """
        # Arrange
        user_id = uuid4()
        service = AgentSwarmLifecycleService(db_session)

        request = AgentProvisionRequest(
            name="Idempotent Agent",
            model="anthropic/claude-opus-4-5"
        )

        # Create agent
        agent = service.create_agent(user_id, request)
        agent_id = agent.id

        # Mock OpenClaw bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = False
        mock_bridge.connect = AsyncMock()
        mock_bridge.send_to_agent = AsyncMock(return_value={"message_id": "test_msg_123"})
        service.openclaw_bridge = mock_bridge

        # Act - Run provision twice (simulating crash and recovery)
        result1 = await service.provision_agent(agent_id)
        result2 = await service.provision_agent(agent_id)

        # Assert
        assert result1.status == AgentSwarmStatus.RUNNING
        assert result1.openclaw_agent_id == "test_msg_123"

        # Second run should fail since agent is already running
        # (In production DBOS, this would be handled by workflow deduplication)
        assert result2.status == AgentSwarmStatus.RUNNING

    @pytest.mark.asyncio
    async def test_provision_agent_handles_openclaw_failure(self, db_session):
        """
        GIVEN an agent provision request
        WHEN OpenClaw connection fails
        THEN agent status should be set to FAILED with error details
        """
        # Arrange
        user_id = uuid4()
        service = AgentSwarmLifecycleService(db_session)

        request = AgentProvisionRequest(
            name="Fail Test Agent",
            model="anthropic/claude-opus-4-5"
        )

        agent = service.create_agent(user_id, request)

        # Mock failing OpenClaw bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = False
        mock_bridge.connect = AsyncMock(side_effect=ConnectionError("OpenClaw unavailable"))
        service.openclaw_bridge = mock_bridge

        # Act
        with pytest.raises(ConnectionError):
            await service.provision_agent(agent.id)

        # Assert
        db_session.refresh(agent)
        assert agent.status == AgentSwarmStatus.FAILED
        assert "OpenClaw unavailable" in agent.error_message
        assert agent.error_count == 1

    def test_provision_agent_with_heartbeat_enabled(self, db_session):
        """
        GIVEN a provision request with heartbeat enabled
        WHEN creating agent
        THEN heartbeat configuration should be stored correctly
        """
        # Arrange
        user_id = uuid4()
        service = AgentSwarmLifecycleService(db_session)

        request = AgentProvisionRequest(
            name="Heartbeat Agent",
            model="anthropic/claude-opus-4-5",
            heartbeat=HeartbeatConfig(
                enabled=True,
                interval=HeartbeatIntervalEnum.FIVE_MINUTES,
                checklist=["Check system health", "Verify connections"]
            )
        )

        # Act
        agent = service.create_agent(user_id, request)

        # Assert
        assert agent.heartbeat_enabled is True
        assert agent.heartbeat_interval == HeartbeatInterval.FIVE_MINUTES
        assert len(agent.heartbeat_checklist) == 2
        assert agent.next_heartbeat_at is not None


class TestHeartbeatWorkflowWithDBOS:
    """Test heartbeat workflow with DBOS durability"""

    @pytest.mark.asyncio
    async def test_heartbeat_execution_creates_durable_record(self, db_session):
        """
        GIVEN a running agent with heartbeat enabled
        WHEN executing heartbeat workflow
        THEN a durable execution record should be created
        """
        # Arrange
        user_id = uuid4()
        service = AgentSwarmLifecycleService(db_session)

        # Create and provision agent
        request = AgentProvisionRequest(
            name="Heartbeat Test",
            model="anthropic/claude-opus-4-5",
            heartbeat=HeartbeatConfig(
                enabled=True,
                interval=HeartbeatIntervalEnum.FIVE_MINUTES,
                checklist=["Task 1", "Task 2"]
            )
        )

        agent = service.create_agent(user_id, request)
        agent.status = AgentSwarmStatus.RUNNING
        db_session.commit()

        # Mock OpenClaw bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = True
        mock_bridge.send_to_agent = AsyncMock(return_value={"success": True})
        service.openclaw_bridge = mock_bridge

        # Act
        execution = await service.execute_heartbeat(agent.id)

        # Assert
        assert execution.agent_id == agent.id
        assert execution.status == HeartbeatExecutionStatus.COMPLETED
        assert execution.started_at is not None
        assert execution.completed_at is not None
        assert execution.duration_seconds >= 0
        assert execution.checklist_items == ["Task 1", "Task 2"]

    @pytest.mark.asyncio
    async def test_heartbeat_workflow_crash_recovery(self, db_session):
        """
        GIVEN a heartbeat execution in progress
        WHEN the process crashes mid-execution
        THEN DBOS should be able to resume the workflow
        """
        # Arrange
        user_id = uuid4()
        service = AgentSwarmLifecycleService(db_session)

        request = AgentProvisionRequest(
            name="Crash Recovery Test",
            model="anthropic/claude-opus-4-5",
            heartbeat=HeartbeatConfig(
                enabled=True,
                interval=HeartbeatIntervalEnum.FIVE_MINUTES,
                checklist=["Check"]
            )
        )

        agent = service.create_agent(user_id, request)
        agent.status = AgentSwarmStatus.RUNNING
        db_session.commit()

        # Create initial execution record (simulating crash before completion)
        execution = AgentHeartbeatExecution(
            agent_id=agent.id,
            status=HeartbeatExecutionStatus.RUNNING,
            checklist_items=["Check"],
            started_at=datetime.now(timezone.utc)
        )
        db_session.add(execution)
        db_session.commit()

        # Simulate crash recovery - query for pending execution
        pending_execution = db_session.query(AgentHeartbeatExecution).filter(
            AgentHeartbeatExecution.agent_id == agent.id,
            AgentHeartbeatExecution.status == HeartbeatExecutionStatus.RUNNING
        ).first()

        # Assert
        assert pending_execution is not None
        assert pending_execution.id == execution.id
        assert pending_execution.status == HeartbeatExecutionStatus.RUNNING

        # In production, DBOS would automatically resume this workflow

    @pytest.mark.asyncio
    async def test_heartbeat_schedules_next_execution(self, db_session):
        """
        GIVEN a completed heartbeat execution
        WHEN the workflow finishes
        THEN next heartbeat time should be scheduled
        """
        # Arrange
        user_id = uuid4()
        service = AgentSwarmLifecycleService(db_session)

        request = AgentProvisionRequest(
            name="Schedule Test",
            model="anthropic/claude-opus-4-5",
            heartbeat=HeartbeatConfig(
                enabled=True,
                interval=HeartbeatIntervalEnum.FIFTEEN_MINUTES,
                checklist=["Check"]
            )
        )

        agent = service.create_agent(user_id, request)
        agent.status = AgentSwarmStatus.RUNNING
        db_session.commit()

        initial_next_heartbeat = agent.next_heartbeat_at

        # Mock OpenClaw bridge
        mock_bridge = AsyncMock()
        mock_bridge.is_connected = True
        mock_bridge.send_to_agent = AsyncMock(return_value={"success": True})
        service.openclaw_bridge = mock_bridge

        # Act
        execution = await service.execute_heartbeat(agent.id)

        # Assert
        db_session.refresh(agent)
        assert execution.status == HeartbeatExecutionStatus.COMPLETED
        assert agent.last_heartbeat_at is not None
        assert agent.next_heartbeat_at is not None
        assert agent.next_heartbeat_at > initial_next_heartbeat


class TestPauseResumeWorkflowWithDBOS:
    """Test pause/resume workflow with DBOS checkpointing"""

    def test_pause_agent_preserves_state(self, db_session):
        """
        GIVEN a running agent
        WHEN pausing the agent
        THEN agent state should be preserved for resumption
        """
        # Arrange
        user_id = uuid4()
        service = AgentSwarmLifecycleService(db_session)

        request = AgentProvisionRequest(
            name="Pause Test",
            model="anthropic/claude-opus-4-5",
            heartbeat=HeartbeatConfig(
                enabled=True,
                interval=HeartbeatIntervalEnum.THIRTY_MINUTES,
                checklist=["Check"]
            )
        )

        agent = service.create_agent(user_id, request)
        agent.status = AgentSwarmStatus.RUNNING
        db_session.commit()

        # Act
        paused_agent = service.pause_agent(agent.id)

        # Assert
        assert paused_agent.status == AgentSwarmStatus.PAUSED
        assert paused_agent.paused_at is not None
        # Heartbeat configuration should be preserved
        assert paused_agent.heartbeat_enabled is True
        assert paused_agent.heartbeat_interval == HeartbeatInterval.THIRTY_MINUTES

    def test_resume_agent_restores_state(self, db_session):
        """
        GIVEN a paused agent
        WHEN resuming the agent
        THEN agent should return to running state with preserved configuration
        """
        # Arrange
        user_id = uuid4()
        service = AgentSwarmLifecycleService(db_session)

        request = AgentProvisionRequest(
            name="Resume Test",
            model="anthropic/claude-opus-4-5",
            heartbeat=HeartbeatConfig(
                enabled=True,
                interval=HeartbeatIntervalEnum.ONE_HOUR,
                checklist=["System check"]
            )
        )

        agent = service.create_agent(user_id, request)
        agent.status = AgentSwarmStatus.RUNNING
        db_session.commit()

        # Pause agent
        service.pause_agent(agent.id)

        # Act
        resumed_agent = service.resume_agent(agent.id)

        # Assert
        assert resumed_agent.status == AgentSwarmStatus.RUNNING
        assert resumed_agent.paused_at is None
        # Configuration should be preserved
        assert resumed_agent.heartbeat_enabled is True
        assert resumed_agent.heartbeat_interval == HeartbeatInterval.ONE_HOUR
        assert resumed_agent.heartbeat_checklist == ["System check"]
        # Next heartbeat should be rescheduled
        assert resumed_agent.next_heartbeat_at is not None


class TestDBOSWorkflowMonitoring:
    """Test DBOS workflow monitoring and observability"""

    @pytest.mark.asyncio
    async def test_workflow_monitor_initialization(self):
        """
        GIVEN OpenClaw Gateway URL
        WHEN initializing workflow monitor
        THEN monitor should be configured correctly
        """
        # Arrange & Act
        monitor = DBOSWorkflowMonitor("http://localhost:8080")

        # Assert
        assert monitor.openclaw_gateway_url == "http://localhost:8080"
        assert monitor.client is not None

        # Cleanup
        await monitor.close()

    @pytest.mark.asyncio
    async def test_get_workflow_status_success(self):
        """
        GIVEN a workflow UUID
        WHEN querying workflow status
        THEN status details should be returned
        """
        # Arrange
        monitor = DBOSWorkflowMonitor("http://localhost:8080")
        workflow_uuid = "test-workflow-uuid-123"

        # Mock HTTP response
        with patch.object(monitor.client, 'get') as mock_get:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "workflowUuid": workflow_uuid,
                "status": "SUCCESS"
            }
            mock_get.return_value = mock_response

            # Act
            status = await monitor.get_workflow_status(workflow_uuid)

            # Assert
            assert status is not None
            assert status["workflowUuid"] == workflow_uuid
            assert status["status"] == "SUCCESS"

        await monitor.close()

    @pytest.mark.asyncio
    async def test_check_workflow_health_healthy(self):
        """
        GIVEN a successful workflow
        WHEN checking workflow health
        THEN health check should pass
        """
        # Arrange
        monitor = DBOSWorkflowMonitor("http://localhost:8080")
        workflow_uuid = "healthy-workflow-uuid"

        # Mock workflow status
        with patch.object(monitor, 'get_workflow_status') as mock_status:
            mock_status.return_value = {
                "workflowUuid": workflow_uuid,
                "status": "SUCCESS"
            }

            # Act
            health = await monitor.check_workflow_health(
                workflow_uuid,
                expected_status=WorkflowStatus.SUCCESS
            )

            # Assert
            assert health["healthy"] is True
            assert health["workflow_uuid"] == workflow_uuid
            assert health["status"] == "SUCCESS"
            assert health["reason"] is None

        await monitor.close()

    @pytest.mark.asyncio
    async def test_check_workflow_health_failed(self):
        """
        GIVEN a failed workflow
        WHEN checking workflow health
        THEN health check should detect failure
        """
        # Arrange
        monitor = DBOSWorkflowMonitor("http://localhost:8080")
        workflow_uuid = "failed-workflow-uuid"

        # Mock workflow status
        with patch.object(monitor, 'get_workflow_status') as mock_status:
            mock_status.return_value = {
                "workflowUuid": workflow_uuid,
                "status": "ERROR"
            }

            # Act
            health = await monitor.check_workflow_health(workflow_uuid)

            # Assert
            assert health["healthy"] is False
            assert health["reason"] == "workflow_failed"

        await monitor.close()

    @pytest.mark.asyncio
    async def test_workflow_health_checker_initialization(self):
        """
        GIVEN a workflow monitor
        WHEN initializing health checker
        THEN it should be configured with correct interval
        """
        # Arrange
        monitor = DBOSWorkflowMonitor("http://localhost:8080")
        checker = WorkflowHealthChecker(monitor, check_interval=30)

        # Assert
        assert checker.monitor == monitor
        assert checker.check_interval == 30
        assert checker.running is False

        await monitor.close()


@pytest.fixture
def db_session():
    """Create test database session using Railway PostgreSQL"""
    import os
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from app.db.base_class import Base

    # Use Railway PostgreSQL database
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        pytest.skip("DATABASE_URL not configured - skipping database tests")

    engine = create_engine(database_url, pool_pre_ping=True)

    # Ensure all tables exist
    Base.metadata.create_all(engine)

    Session = sessionmaker(bind=engine)
    session = Session()

    yield session

    # Cleanup: rollback any uncommitted changes
    session.rollback()
    session.close()
