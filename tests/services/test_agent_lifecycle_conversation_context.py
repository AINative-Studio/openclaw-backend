"""
Agent Lifecycle Service Tests for Conversation Context (Issue #107)

TDD RED PHASE - Tests for conversation context integration in AgentSwarmLifecycleService.

Tests cover:
1. provision_agent with conversation_id attachment
2. provision_agent without conversation_id (backward compatibility)
3. update_agent_state includes conversation_id
4. get_agent_conversation_summary returns conversation stats
5. switch_agent_conversation changes agent's conversation
6. Conversation context loading during provision
7. Validation that conversation exists before attachment
8. Heartbeat includes conversation activity metrics

Following strict TDD methodology - all tests should FAIL initially.
"""

import pytest
from datetime import datetime, timezone, timedelta
from uuid import uuid4, UUID
from unittest.mock import Mock, AsyncMock, patch, MagicMock, call
from sqlalchemy.orm import Session

from backend.services.agent_swarm_lifecycle_service import AgentSwarmLifecycleService
from backend.models.agent_swarm_lifecycle import (
    AgentSwarmInstance,
    AgentSwarmStatus,
    HeartbeatInterval
)
from backend.models.conversation import Conversation, ConversationStatus
from backend.models.workspace import Workspace
from backend.schemas.agent_swarm_lifecycle import (
    AgentProvisionRequest,
    HeartbeatConfig,
    HeartbeatIntervalEnum
)
from backend.integrations.zerodb_client import ZeroDBClient


class TestProvisionAgentWithConversation:
    """Test provision_agent with conversation_id parameter"""

    @pytest.mark.asyncio
    async def test_provision_agent_with_conversation_id_attaches_conversation(self):
        """
        GIVEN an agent in PROVISIONING state and a valid conversation_id
        WHEN calling provision_agent with conversation_id parameter
        THEN the agent should be linked to the conversation
        """
        # Arrange
        agent_id = uuid4()
        conversation_id = uuid4()
        workspace_id = uuid4()
        user_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        # Mock agent query
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.status = AgentSwarmStatus.PROVISIONING
        mock_agent.name = "Test Agent"
        mock_agent.openclaw_session_key = "agent:web:test-agent"
        mock_agent.user_id = user_id
        mock_agent.workspace_id = workspace_id
        mock_agent.persona = "Backend Developer"
        mock_agent.model = "claude-sonnet-4"
        mock_agent.heartbeat_enabled = False
        mock_agent.error_count = 0
        mock_agent.current_conversation_id = None  # Initially no conversation

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        # Mock conversation query
        mock_conversation = Mock(spec=Conversation)
        mock_conversation.id = conversation_id
        mock_conversation.status = ConversationStatus.ACTIVE
        mock_conversation.message_count = 5

        service = AgentSwarmLifecycleService(db=mock_db, zerodb_client=mock_zerodb_client)

        # Mock OpenClaw bridge
        with patch.dict('os.environ', {'OPENCLAW_GATEWAY_URL': 'ws://test', 'OPENCLAW_AUTH_TOKEN': 'test-token'}):
            with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge'):
                service.openclaw_bridge = AsyncMock()
                service.openclaw_bridge.is_connected = False
                service.openclaw_bridge.connect = AsyncMock()
                service.openclaw_bridge.send_to_agent = AsyncMock(return_value={"message_id": "msg_123"})

                # Act
                result = await service.provision_agent(agent_id, conversation_id=conversation_id)

                # Assert
                assert mock_agent.current_conversation_id == conversation_id
                mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_provision_agent_without_conversation_id_works_normally(self):
        """
        GIVEN an agent in PROVISIONING state without conversation_id
        WHEN calling provision_agent without conversation_id parameter
        THEN the agent should provision normally without conversation attachment
        """
        # Arrange
        agent_id = uuid4()
        workspace_id = uuid4()
        user_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.status = AgentSwarmStatus.PROVISIONING
        mock_agent.name = "Test Agent"
        mock_agent.openclaw_session_key = "agent:web:test-agent"
        mock_agent.user_id = user_id
        mock_agent.workspace_id = workspace_id
        mock_agent.persona = "Backend Developer"
        mock_agent.model = "claude-sonnet-4"
        mock_agent.heartbeat_enabled = False
        mock_agent.error_count = 0
        mock_agent.current_conversation_id = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        service = AgentSwarmLifecycleService(db=mock_db, zerodb_client=mock_zerodb_client)

        with patch.dict('os.environ', {'OPENCLAW_GATEWAY_URL': 'ws://test', 'OPENCLAW_AUTH_TOKEN': 'test-token'}):
            with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge'):
                service.openclaw_bridge = AsyncMock()
                service.openclaw_bridge.is_connected = False
                service.openclaw_bridge.connect = AsyncMock()
                service.openclaw_bridge.send_to_agent = AsyncMock(return_value={"message_id": "msg_123"})

                # Act
                result = await service.provision_agent(agent_id)

                # Assert - conversation_id should remain None (backward compatibility)
                assert mock_agent.current_conversation_id is None
                assert result.status == AgentSwarmStatus.RUNNING

    @pytest.mark.asyncio
    async def test_provision_agent_validates_conversation_exists(self):
        """
        GIVEN an agent and a non-existent conversation_id
        WHEN calling provision_agent with invalid conversation_id
        THEN it should raise ValueError
        """
        # Arrange
        agent_id = uuid4()
        conversation_id = uuid4()
        workspace_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.status = AgentSwarmStatus.PROVISIONING
        mock_agent.workspace_id = workspace_id

        # Agent query returns agent
        mock_agent_query = Mock()
        mock_agent_query.filter.return_value.first.return_value = mock_agent

        # Conversation query returns None
        mock_conversation_query = Mock()
        mock_conversation_query.filter.return_value.first.return_value = None

        mock_db.query.side_effect = [mock_agent_query, mock_conversation_query]

        service = AgentSwarmLifecycleService(db=mock_db, zerodb_client=mock_zerodb_client)

        # Act & Assert
        with pytest.raises(ValueError, match="Conversation .* not found"):
            await service.provision_agent(agent_id, conversation_id=conversation_id)

    @pytest.mark.asyncio
    async def test_provision_agent_loads_conversation_context(self):
        """
        GIVEN an agent with conversation_id during provisioning
        WHEN calling provision_agent
        THEN it should load last 10 messages from conversation for context
        """
        # Arrange
        agent_id = uuid4()
        conversation_id = uuid4()
        workspace_id = uuid4()
        user_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.status = AgentSwarmStatus.PROVISIONING
        mock_agent.workspace_id = workspace_id
        mock_agent.user_id = user_id
        mock_agent.openclaw_session_key = "agent:web:test"
        mock_agent.current_conversation_id = None

        mock_conversation = Mock(spec=Conversation)
        mock_conversation.id = conversation_id
        mock_conversation.status = ConversationStatus.ACTIVE

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        # Mock ConversationService to return messages
        mock_conversation_service = AsyncMock()
        mock_conversation_service.get_messages = AsyncMock(return_value=[
            {"role": "user", "content": "Hello", "timestamp": "2026-03-08T10:00:00Z"},
            {"role": "assistant", "content": "Hi there", "timestamp": "2026-03-08T10:00:05Z"},
        ])

        service = AgentSwarmLifecycleService(db=mock_db, zerodb_client=mock_zerodb_client)

        with patch.dict('os.environ', {'OPENCLAW_GATEWAY_URL': 'ws://test', 'OPENCLAW_AUTH_TOKEN': 'test-token'}):
            with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge'):
                with patch('backend.services.agent_swarm_lifecycle_service.ConversationService', return_value=mock_conversation_service):
                    service.openclaw_bridge = AsyncMock()
                    service.openclaw_bridge.is_connected = False
                    service.openclaw_bridge.connect = AsyncMock()
                    service.openclaw_bridge.send_to_agent = AsyncMock(return_value={"message_id": "msg_123"})

                    # Act
                    await service.provision_agent(agent_id, conversation_id=conversation_id)

                    # Assert - should have fetched messages (limit=10)
                    mock_conversation_service.get_messages.assert_called_once_with(
                        conversation_id=conversation_id,
                        limit=10,
                        offset=0
                    )

    @pytest.mark.asyncio
    async def test_provision_agent_includes_conversation_context_in_system_message(self):
        """
        GIVEN an agent with conversation context loaded
        WHEN calling provision_agent
        THEN conversation history should be included in provisioning message
        """
        # Arrange
        agent_id = uuid4()
        conversation_id = uuid4()
        workspace_id = uuid4()
        user_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.status = AgentSwarmStatus.PROVISIONING
        mock_agent.workspace_id = workspace_id
        mock_agent.user_id = user_id
        mock_agent.openclaw_session_key = "agent:web:test"
        mock_agent.name = "Test Agent"
        mock_agent.persona = "Backend Dev"
        mock_agent.model = "claude-sonnet-4"
        mock_agent.heartbeat_enabled = False
        mock_agent.error_count = 0
        mock_agent.current_conversation_id = conversation_id

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        service = AgentSwarmLifecycleService(db=mock_db, zerodb_client=mock_zerodb_client)

        # Mock conversation messages
        conversation_messages = [
            {"role": "user", "content": "Hello", "timestamp": "2026-03-08T10:00:00Z"},
            {"role": "assistant", "content": "Hi there", "timestamp": "2026-03-08T10:00:05Z"},
        ]

        with patch.object(service, '_load_conversation_context', return_value=conversation_messages) as mock_load:
            with patch.dict('os.environ', {'OPENCLAW_GATEWAY_URL': 'ws://test', 'OPENCLAW_AUTH_TOKEN': 'test-token'}):
                with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge'):
                    service.openclaw_bridge = AsyncMock()
                    service.openclaw_bridge.is_connected = False
                    service.openclaw_bridge.connect = AsyncMock()
                    service.openclaw_bridge.send_to_agent = AsyncMock(return_value={"message_id": "msg_123"})

                    # Act
                    await service.provision_agent(agent_id, conversation_id=conversation_id)

                    # Assert - provisioning message should include context
                    send_call = service.openclaw_bridge.send_to_agent.call_args
                    provisioning_message = send_call.kwargs['message']
                    assert "Conversation History" in provisioning_message
                    assert "user: Hello" in provisioning_message


class TestUpdateAgentState:
    """Test update_agent_state includes conversation_id"""

    def test_update_agent_state_includes_conversation_id(self):
        """
        GIVEN an agent with conversation_id
        WHEN calling update_agent_state
        THEN the returned state should include conversation_id
        """
        # Arrange
        agent_id = uuid4()
        conversation_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.current_conversation_id = conversation_id
        mock_agent.status = AgentSwarmStatus.RUNNING
        mock_agent.name = "Test Agent"
        mock_agent.user_id = uuid4()
        mock_agent.workspace_id = uuid4()

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act
        state = service.update_agent_state(agent_id)

        # Assert
        assert state is not None
        assert state.get('conversation_id') == str(conversation_id)

    def test_update_agent_state_handles_null_conversation_id(self):
        """
        GIVEN an agent without conversation_id
        WHEN calling update_agent_state
        THEN the returned state should include conversation_id as None
        """
        # Arrange
        agent_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.current_conversation_id = None
        mock_agent.status = AgentSwarmStatus.RUNNING

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act
        state = service.update_agent_state(agent_id)

        # Assert
        assert state.get('conversation_id') is None


class TestGetAgentConversationSummary:
    """Test get_agent_conversation_summary returns conversation stats"""

    @pytest.mark.asyncio
    async def test_get_agent_conversation_summary_returns_stats(self):
        """
        GIVEN an agent with an active conversation
        WHEN calling get_agent_conversation_summary
        THEN it should return conversation statistics
        """
        # Arrange
        agent_id = uuid4()
        conversation_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.current_conversation_id = conversation_id

        mock_conversation = Mock(spec=Conversation)
        mock_conversation.id = conversation_id
        mock_conversation.message_count = 15
        mock_conversation.started_at = datetime(2026, 3, 8, 10, 0, 0, tzinfo=timezone.utc)
        mock_conversation.last_message_at = datetime(2026, 3, 8, 12, 30, 0, tzinfo=timezone.utc)
        mock_conversation.status = ConversationStatus.ACTIVE

        # Mock query chain
        mock_agent_query = Mock()
        mock_agent_query.filter.return_value.first.return_value = mock_agent

        mock_conversation_query = Mock()
        mock_conversation_query.filter.return_value.first.return_value = mock_conversation

        mock_db.query.side_effect = [mock_agent_query, mock_conversation_query]

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act
        summary = await service.get_agent_conversation_summary(agent_id)

        # Assert
        assert summary is not None
        assert summary['conversation_id'] == str(conversation_id)
        assert summary['message_count'] == 15
        assert summary['status'] == 'active'
        assert 'started_at' in summary
        assert 'last_message_at' in summary

    @pytest.mark.asyncio
    async def test_get_agent_conversation_summary_handles_no_conversation(self):
        """
        GIVEN an agent without a conversation
        WHEN calling get_agent_conversation_summary
        THEN it should return None
        """
        # Arrange
        agent_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.current_conversation_id = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act
        summary = await service.get_agent_conversation_summary(agent_id)

        # Assert
        assert summary is None

    @pytest.mark.asyncio
    async def test_get_agent_conversation_summary_raises_error_for_invalid_agent(self):
        """
        GIVEN a non-existent agent_id
        WHEN calling get_agent_conversation_summary
        THEN it should raise ValueError
        """
        # Arrange
        agent_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_db.query.return_value.filter.return_value.first.return_value = None

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act & Assert
        with pytest.raises(ValueError, match="Agent .* not found"):
            await service.get_agent_conversation_summary(agent_id)


class TestSwitchAgentConversation:
    """Test switch_agent_conversation changes agent's conversation"""

    @pytest.mark.asyncio
    async def test_switch_agent_conversation_changes_conversation_id(self):
        """
        GIVEN an agent with conversation A
        WHEN calling switch_agent_conversation to conversation B
        THEN the agent's conversation_id should be updated to B
        """
        # Arrange
        agent_id = uuid4()
        old_conversation_id = uuid4()
        new_conversation_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.current_conversation_id = old_conversation_id
        mock_agent.status = AgentSwarmStatus.RUNNING

        mock_new_conversation = Mock(spec=Conversation)
        mock_new_conversation.id = new_conversation_id
        mock_new_conversation.status = ConversationStatus.ACTIVE

        # Mock query chain
        mock_agent_query = Mock()
        mock_agent_query.filter.return_value.first.return_value = mock_agent

        mock_conversation_query = Mock()
        mock_conversation_query.filter.return_value.first.return_value = mock_new_conversation

        mock_db.query.side_effect = [mock_agent_query, mock_conversation_query]

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act
        result = await service.switch_agent_conversation(agent_id, new_conversation_id)

        # Assert
        assert mock_agent.current_conversation_id == new_conversation_id
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_switch_agent_conversation_validates_new_conversation_exists(self):
        """
        GIVEN an agent
        WHEN calling switch_agent_conversation with non-existent conversation
        THEN it should raise ValueError
        """
        # Arrange
        agent_id = uuid4()
        new_conversation_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id

        # Agent query returns agent
        mock_agent_query = Mock()
        mock_agent_query.filter.return_value.first.return_value = mock_agent

        # Conversation query returns None
        mock_conversation_query = Mock()
        mock_conversation_query.filter.return_value.first.return_value = None

        mock_db.query.side_effect = [mock_agent_query, mock_conversation_query]

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act & Assert
        with pytest.raises(ValueError, match="Conversation .* not found"):
            await service.switch_agent_conversation(agent_id, new_conversation_id)

    @pytest.mark.asyncio
    async def test_switch_agent_conversation_logs_the_switch(self):
        """
        GIVEN an agent switching conversations
        WHEN calling switch_agent_conversation
        THEN it should log the conversation switch event
        """
        # Arrange
        agent_id = uuid4()
        old_conversation_id = uuid4()
        new_conversation_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.name = "Test Agent"
        mock_agent.current_conversation_id = old_conversation_id

        mock_new_conversation = Mock(spec=Conversation)
        mock_new_conversation.id = new_conversation_id
        mock_new_conversation.status = ConversationStatus.ACTIVE

        mock_agent_query = Mock()
        mock_agent_query.filter.return_value.first.return_value = mock_agent

        mock_conversation_query = Mock()
        mock_conversation_query.filter.return_value.first.return_value = mock_new_conversation

        mock_db.query.side_effect = [mock_agent_query, mock_conversation_query]

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act
        with patch('backend.services.agent_swarm_lifecycle_service.logger') as mock_logger:
            await service.switch_agent_conversation(agent_id, new_conversation_id)

            # Assert - should have logged the switch
            mock_logger.info.assert_called()
            log_call = mock_logger.info.call_args[0][0]
            assert "switched conversation" in log_call.lower() or "conversation switched" in log_call.lower()

    @pytest.mark.asyncio
    async def test_switch_agent_conversation_allows_clearing_conversation(self):
        """
        GIVEN an agent with a conversation
        WHEN calling switch_agent_conversation with conversation_id=None
        THEN the agent's conversation_id should be cleared
        """
        # Arrange
        agent_id = uuid4()
        old_conversation_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.current_conversation_id = old_conversation_id

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act
        result = await service.switch_agent_conversation(agent_id, None)

        # Assert
        assert mock_agent.current_conversation_id is None
        mock_db.commit.assert_called()


class TestHeartbeatConversationMetrics:
    """Test heartbeat includes conversation activity metrics"""

    @pytest.mark.asyncio
    async def test_heartbeat_includes_conversation_metrics_when_conversation_attached(self):
        """
        GIVEN an agent with an active conversation
        WHEN executing heartbeat
        THEN heartbeat metadata should include conversation activity metrics
        """
        # Arrange
        agent_id = uuid4()
        conversation_id = uuid4()
        workspace_id = uuid4()
        user_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.current_conversation_id = conversation_id
        mock_agent.workspace_id = workspace_id
        mock_agent.user_id = user_id
        mock_agent.status = AgentSwarmStatus.RUNNING
        mock_agent.heartbeat_enabled = True
        mock_agent.heartbeat_checklist = ["Task 1", "Task 2"]
        mock_agent.heartbeat_interval = HeartbeatInterval.FIFTEEN_MINUTES
        mock_agent.openclaw_session_key = "agent:web:test"
        mock_agent.name = "Test Agent"

        mock_conversation = Mock(spec=Conversation)
        mock_conversation.id = conversation_id
        mock_conversation.message_count = 20
        mock_conversation.last_message_at = datetime.now(timezone.utc) - timedelta(minutes=5)

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        service = AgentSwarmLifecycleService(db=mock_db)

        with patch.dict('os.environ', {'OPENCLAW_GATEWAY_URL': 'ws://test', 'OPENCLAW_AUTH_TOKEN': 'test-token'}):
            with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge'):
                service.openclaw_bridge = AsyncMock()
                service.openclaw_bridge.is_connected = False
                service.openclaw_bridge.connect = AsyncMock()
                service.openclaw_bridge.send_to_agent = AsyncMock(return_value={"success": True})

                # Act
                await service.execute_heartbeat(agent_id)

                # Assert - heartbeat metadata should include conversation metrics
                send_call = service.openclaw_bridge.send_to_agent.call_args
                metadata = send_call.kwargs.get('metadata', {})
                assert 'conversation_id' in metadata or 'conversation_message_count' in metadata


class TestBackwardCompatibility:
    """Test backward compatibility - existing functionality still works"""

    @pytest.mark.asyncio
    async def test_provision_agent_backward_compatible_signature(self):
        """
        GIVEN existing code calling provision_agent without conversation_id
        WHEN calling provision_agent(agent_id)
        THEN it should work without breaking changes
        """
        # Arrange
        agent_id = uuid4()
        workspace_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.status = AgentSwarmStatus.PROVISIONING
        mock_agent.workspace_id = workspace_id
        mock_agent.user_id = uuid4()
        mock_agent.openclaw_session_key = "agent:web:test"
        mock_agent.name = "Test"
        mock_agent.error_count = 0

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        service = AgentSwarmLifecycleService(db=mock_db)

        with patch.dict('os.environ', {'OPENCLAW_GATEWAY_URL': 'ws://test', 'OPENCLAW_AUTH_TOKEN': 'test-token'}):
            with patch('backend.services.agent_swarm_lifecycle_service.ProductionOpenClawBridge'):
                service.openclaw_bridge = AsyncMock()
                service.openclaw_bridge.is_connected = False
                service.openclaw_bridge.connect = AsyncMock()
                service.openclaw_bridge.send_to_agent = AsyncMock(return_value={"message_id": "msg_123"})

                # Act - call without conversation_id (existing behavior)
                result = await service.provision_agent(agent_id)

                # Assert - should work normally
                assert result.status == AgentSwarmStatus.RUNNING


class TestConversationContextLoading:
    """Test conversation context loading during provisioning"""

    @pytest.mark.asyncio
    async def test_load_conversation_context_fetches_last_10_messages(self):
        """
        GIVEN a conversation with 15 messages
        WHEN calling _load_conversation_context
        THEN it should fetch exactly 10 most recent messages
        """
        # Arrange
        conversation_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        service = AgentSwarmLifecycleService(db=mock_db, zerodb_client=mock_zerodb_client)

        # Mock ConversationService
        mock_conversation_service = AsyncMock()
        mock_messages = [
            {"role": "user", "content": f"Message {i}", "timestamp": f"2026-03-08T10:{i:02d}:00Z"}
            for i in range(10)
        ]
        mock_conversation_service.get_messages = AsyncMock(return_value=mock_messages)

        with patch('backend.services.agent_swarm_lifecycle_service.ConversationService', return_value=mock_conversation_service):
            # Act
            context = await service._load_conversation_context(conversation_id)

            # Assert
            mock_conversation_service.get_messages.assert_called_once_with(
                conversation_id=conversation_id,
                limit=10,
                offset=0
            )
            assert len(context) == 10

    @pytest.mark.asyncio
    async def test_load_conversation_context_returns_empty_list_on_error(self):
        """
        GIVEN ConversationService raises an error
        WHEN calling _load_conversation_context
        THEN it should return empty list (graceful degradation)
        """
        # Arrange
        conversation_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_zerodb_client = Mock(spec=ZeroDBClient)

        service = AgentSwarmLifecycleService(db=mock_db, zerodb_client=mock_zerodb_client)

        # Mock ConversationService that raises error
        mock_conversation_service = AsyncMock()
        mock_conversation_service.get_messages = AsyncMock(side_effect=Exception("ZeroDB unavailable"))

        with patch('backend.services.agent_swarm_lifecycle_service.ConversationService', return_value=mock_conversation_service):
            # Act
            context = await service._load_conversation_context(conversation_id)

            # Assert - should return empty list, not raise
            assert context == []


class TestValidation:
    """Test validation and error handling"""

    @pytest.mark.asyncio
    async def test_provision_agent_validates_conversation_belongs_to_workspace(self):
        """
        GIVEN an agent in workspace A and conversation in workspace B
        WHEN calling provision_agent with that conversation
        THEN it should raise ValueError for workspace mismatch
        """
        # Arrange
        agent_id = uuid4()
        conversation_id = uuid4()
        workspace_a = uuid4()
        workspace_b = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.workspace_id = workspace_a
        mock_agent.status = AgentSwarmStatus.PROVISIONING

        mock_conversation = Mock(spec=Conversation)
        mock_conversation.id = conversation_id
        mock_conversation.workspace_id = workspace_b  # Different workspace!

        mock_agent_query = Mock()
        mock_agent_query.filter.return_value.first.return_value = mock_agent

        mock_conversation_query = Mock()
        mock_conversation_query.filter.return_value.first.return_value = mock_conversation

        mock_db.query.side_effect = [mock_agent_query, mock_conversation_query]

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act & Assert
        with pytest.raises(ValueError, match="Conversation does not belong to agent's workspace"):
            await service.provision_agent(agent_id, conversation_id=conversation_id)

    @pytest.mark.asyncio
    async def test_switch_agent_conversation_validates_agent_is_running(self):
        """
        GIVEN an agent in STOPPED state
        WHEN calling switch_agent_conversation
        THEN it should raise ValueError
        """
        # Arrange
        agent_id = uuid4()
        new_conversation_id = uuid4()

        mock_db = Mock(spec=Session)
        mock_agent = Mock(spec=AgentSwarmInstance)
        mock_agent.id = agent_id
        mock_agent.status = AgentSwarmStatus.STOPPED

        mock_db.query.return_value.filter.return_value.first.return_value = mock_agent

        service = AgentSwarmLifecycleService(db=mock_db)

        # Act & Assert
        with pytest.raises(ValueError, match="Cannot switch conversation for agent in .* state"):
            await service.switch_agent_conversation(agent_id, new_conversation_id)
