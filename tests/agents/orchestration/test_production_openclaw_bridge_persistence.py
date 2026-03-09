"""
Tests for ProductionOpenClawBridge with ConversationService integration

Tests cover:
- Backward compatibility (send_to_agent without optional params)
- Message persistence with ConversationService when IDs provided
- Graceful degradation when ConversationService unavailable
- Error handling for conversation creation/message storage
- Coverage >= 90%
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4
from datetime import datetime, timezone

# conftest.py sets up app.* mocks before this file is loaded

from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge
from backend.services.conversation_service import ConversationService
from backend.models.conversation import Conversation
from backend.integrations.zerodb_client import ZeroDBClient, ZeroDBAPIError


@pytest.fixture
def mock_base_bridge():
    """Create mocked BaseOpenClawBridge"""
    mock_bridge = AsyncMock()
    mock_bridge.is_connected = True
    mock_bridge.send_to_agent = AsyncMock()
    mock_bridge.connect = AsyncMock()
    mock_bridge.close = AsyncMock()
    mock_bridge.on_event = MagicMock()
    return mock_bridge


@pytest.fixture
def mock_conversation_service():
    """Create mocked ConversationService"""
    service = AsyncMock(spec=ConversationService)
    service.get_conversation_by_session_key = AsyncMock()
    service.create_conversation = AsyncMock()
    service.add_message = AsyncMock()
    return service


@pytest.fixture
def mock_db_session():
    """Create mocked database session"""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    return session


@pytest.fixture
def mock_zerodb_client():
    """Create mocked ZeroDBClient"""
    client = AsyncMock(spec=ZeroDBClient)
    return client


@pytest.fixture
def sample_conversation():
    """Create sample conversation (mock object to avoid SQLAlchemy init)"""
    conversation = MagicMock()
    conversation.id = uuid4()
    conversation.workspace_id = uuid4()
    conversation.agent_id = uuid4()
    conversation.user_id = uuid4()
    conversation.openclaw_session_key = "whatsapp:group:test123"
    conversation.status = "active"
    conversation.message_count = 0
    return conversation


class TestProductionOpenClawBridgeConstruction:
    """Test bridge initialization with optional persistence"""

    def test_bridge_without_persistence_dependencies(self):
        """Test bridge initializes without db or zerodb_client (backward compatible)"""
        bridge = ProductionOpenClawBridge(
            url="ws://localhost:18789",
            token="test-token"
        )

        assert bridge is not None
        assert hasattr(bridge, '_base_bridge')
        assert hasattr(bridge, '_conversation_service')
        assert bridge._conversation_service is None

    def test_bridge_with_persistence_dependencies(self, mock_db_session, mock_zerodb_client):
        """Test bridge initializes with db and zerodb_client"""
        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge'):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=mock_db_session,
                zerodb_client=mock_zerodb_client
            )

            assert bridge._db == mock_db_session
            assert bridge._zerodb == mock_zerodb_client
            assert bridge._conversation_service is not None

    def test_bridge_with_only_db_no_zerodb(self, mock_db_session):
        """Test bridge with db but no zerodb_client (no persistence)"""
        bridge = ProductionOpenClawBridge(
            url="ws://localhost:18789",
            token="test-token",
            db=mock_db_session,
            zerodb_client=None
        )

        assert bridge._conversation_service is None

    def test_bridge_with_only_zerodb_no_db(self, mock_zerodb_client):
        """Test bridge with zerodb_client but no db (no persistence)"""
        bridge = ProductionOpenClawBridge(
            url="ws://localhost:18789",
            token="test-token",
            db=None,
            zerodb_client=mock_zerodb_client
        )

        assert bridge._conversation_service is None


class TestSendToAgentBackwardCompatibility:
    """Test send_to_agent maintains backward compatibility"""

    @pytest.mark.asyncio
    async def test_send_without_optional_params(self, mock_base_bridge):
        """Test send_to_agent works without agent_id, user_id, workspace_id"""
        # Setup
        mock_base_bridge.send_to_agent.return_value = {
            "id": "msg_123",
            "status": "sent"
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            # Execute - old signature (no optional params)
            result = await bridge.send_to_agent(
                session_key="whatsapp:dm:test123",
                message="Hello agent"
            )

            # Verify
            assert result["status"] == "sent"
            mock_base_bridge.send_to_agent.assert_called_once_with(
                session_key="whatsapp:dm:test123",
                message="Hello agent"
            )

    @pytest.mark.asyncio
    async def test_send_without_metadata_param(self, mock_base_bridge):
        """Test send_to_agent works without metadata parameter"""
        # Setup
        mock_base_bridge.send_to_agent.return_value = {
            "id": "msg_456",
            "status": "sent"
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            # Execute without metadata
            result = await bridge.send_to_agent(
                session_key="whatsapp:dm:test456",
                message="Test message"
            )

            assert result is not None
            assert "status" in result


class TestSendToAgentWithPersistence:
    """Test send_to_agent with conversation persistence"""

    @pytest.mark.asyncio
    async def test_send_creates_new_conversation(
        self,
        mock_base_bridge,
        mock_conversation_service,
        sample_conversation
    ):
        """Test send_to_agent creates new conversation when IDs provided and conversation doesn't exist"""
        # Setup
        workspace_id = uuid4()
        agent_id = uuid4()
        user_id = uuid4()
        session_key = "whatsapp:group:new_conv_123"

        # No existing conversation
        mock_conversation_service.get_conversation_by_session_key.return_value = None

        # Create conversation returns sample
        sample_conversation.workspace_id = workspace_id
        sample_conversation.agent_id = agent_id
        sample_conversation.user_id = user_id
        sample_conversation.openclaw_session_key = session_key
        mock_conversation_service.create_conversation.return_value = sample_conversation

        # Mock successful message sends
        mock_conversation_service.add_message.return_value = {
            "id": "msg_123",
            "conversation_id": str(sample_conversation.id),
            "role": "user",
            "content": "Hello"
        }

        mock_base_bridge.send_to_agent.return_value = {
            "id": "gateway_msg_123",
            "status": "sent",
            "result": {
                "response": "Hi there!",
                "model": "claude-3-5-sonnet",
                "tokens_used": 150
            }
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute
            result = await bridge.send_to_agent(
                session_key=session_key,
                message="Hello",
                agent_id=agent_id,
                user_id=user_id,
                workspace_id=workspace_id
            )

            # Verify conversation created
            mock_conversation_service.create_conversation.assert_called_once_with(
                workspace_id=workspace_id,
                agent_id=agent_id,
                user_id=user_id,
                openclaw_session_key=session_key
            )

            # Verify user message stored
            assert mock_conversation_service.add_message.call_count == 2  # user + assistant
            user_call = mock_conversation_service.add_message.call_args_list[0]
            assert user_call.kwargs["conversation_id"] == sample_conversation.id
            assert user_call.kwargs["role"] == "user"
            assert user_call.kwargs["content"] == "Hello"

            # Verify assistant message stored
            assistant_call = mock_conversation_service.add_message.call_args_list[1]
            assert assistant_call.kwargs["conversation_id"] == sample_conversation.id
            assert assistant_call.kwargs["role"] == "assistant"
            assert assistant_call.kwargs["content"] == "Hi there!"

    @pytest.mark.asyncio
    async def test_send_uses_existing_conversation(
        self,
        mock_base_bridge,
        mock_conversation_service,
        sample_conversation
    ):
        """Test send_to_agent uses existing conversation when found"""
        # Setup
        workspace_id = sample_conversation.workspace_id
        agent_id = sample_conversation.agent_id
        user_id = sample_conversation.user_id
        session_key = sample_conversation.openclaw_session_key

        # Existing conversation found
        mock_conversation_service.get_conversation_by_session_key.return_value = sample_conversation

        # Mock successful message sends
        mock_conversation_service.add_message.return_value = {
            "id": "msg_456",
            "conversation_id": str(sample_conversation.id)
        }

        mock_base_bridge.send_to_agent.return_value = {
            "id": "gateway_msg_456",
            "status": "sent",
            "result": {
                "response": "Response text"
            }
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute
            await bridge.send_to_agent(
                session_key=session_key,
                message="Follow-up message",
                agent_id=agent_id,
                user_id=user_id,
                workspace_id=workspace_id
            )

            # Verify conversation NOT created (uses existing)
            mock_conversation_service.create_conversation.assert_not_called()

            # Verify get was called
            mock_conversation_service.get_conversation_by_session_key.assert_called_once_with(session_key)

    @pytest.mark.asyncio
    async def test_send_with_partial_ids_no_persistence(
        self,
        mock_base_bridge,
        mock_conversation_service
    ):
        """Test send_to_agent without all required IDs skips persistence"""
        # Setup
        mock_base_bridge.send_to_agent.return_value = {
            "id": "msg_789",
            "status": "sent"
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute with only agent_id (missing user_id and workspace_id)
            await bridge.send_to_agent(
                session_key="whatsapp:dm:partial123",
                message="Test",
                agent_id=uuid4()
                # Missing user_id and workspace_id
            )

            # Verify no persistence attempted
            mock_conversation_service.get_conversation_by_session_key.assert_not_called()
            mock_conversation_service.create_conversation.assert_not_called()
            mock_conversation_service.add_message.assert_not_called()


class TestGracefulDegradation:
    """Test graceful degradation when persistence fails"""

    @pytest.mark.asyncio
    async def test_send_continues_on_conversation_creation_failure(
        self,
        mock_base_bridge,
        mock_conversation_service
    ):
        """Test send_to_agent continues if conversation creation fails"""
        # Setup
        mock_conversation_service.get_conversation_by_session_key.return_value = None
        mock_conversation_service.create_conversation.side_effect = ValueError("Workspace not found")

        mock_base_bridge.send_to_agent.return_value = {
            "id": "msg_123",
            "status": "sent"
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute - should not raise exception
            result = await bridge.send_to_agent(
                session_key="whatsapp:dm:fail123",
                message="Test message",
                agent_id=uuid4(),
                user_id=uuid4(),
                workspace_id=uuid4()
            )

            # Verify message still sent to gateway
            assert result["status"] == "sent"
            mock_base_bridge.send_to_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_continues_on_user_message_storage_failure(
        self,
        mock_base_bridge,
        mock_conversation_service,
        sample_conversation
    ):
        """Test send_to_agent continues if user message storage fails"""
        # Setup
        mock_conversation_service.get_conversation_by_session_key.return_value = sample_conversation
        mock_conversation_service.add_message.side_effect = ZeroDBAPIError(
            "Failed to store message", status_code=500
        )

        mock_base_bridge.send_to_agent.return_value = {
            "id": "msg_456",
            "status": "sent",
            "result": {"response": "Response"}
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute - should not raise exception
            result = await bridge.send_to_agent(
                session_key=sample_conversation.openclaw_session_key,
                message="Test",
                agent_id=sample_conversation.agent_id,
                user_id=sample_conversation.user_id,
                workspace_id=sample_conversation.workspace_id
            )

            # Verify message still sent to gateway
            assert result["status"] == "sent"
            mock_base_bridge.send_to_agent.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_continues_on_assistant_message_storage_failure(
        self,
        mock_base_bridge,
        mock_conversation_service,
        sample_conversation
    ):
        """Test send_to_agent continues if assistant message storage fails"""
        # Setup
        mock_conversation_service.get_conversation_by_session_key.return_value = sample_conversation

        # User message succeeds, assistant message fails
        mock_conversation_service.add_message.side_effect = [
            {"id": "user_msg_123"},  # First call (user) succeeds
            ZeroDBAPIError("Failed to store assistant message", status_code=500)  # Second call fails
        ]

        mock_base_bridge.send_to_agent.return_value = {
            "id": "msg_789",
            "status": "sent",
            "result": {"response": "Assistant response"}
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute - should not raise exception
            result = await bridge.send_to_agent(
                session_key=sample_conversation.openclaw_session_key,
                message="Test",
                agent_id=sample_conversation.agent_id,
                user_id=sample_conversation.user_id,
                workspace_id=sample_conversation.workspace_id
            )

            # Verify response returned
            assert result["status"] == "sent"


class TestAssistantResponsePersistence:
    """Test assistant response metadata extraction and storage"""

    @pytest.mark.asyncio
    async def test_assistant_response_with_metadata(
        self,
        mock_base_bridge,
        mock_conversation_service,
        sample_conversation
    ):
        """Test assistant response metadata (model, tokens) is stored"""
        # Setup
        mock_conversation_service.get_conversation_by_session_key.return_value = sample_conversation
        mock_conversation_service.add_message.return_value = {"id": "msg_123"}

        mock_base_bridge.send_to_agent.return_value = {
            "id": "gateway_msg",
            "status": "sent",
            "result": {
                "response": "Detailed response",
                "model": "claude-3-opus",
                "tokens_used": 500
            }
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute
            await bridge.send_to_agent(
                session_key=sample_conversation.openclaw_session_key,
                message="Question",
                agent_id=sample_conversation.agent_id,
                user_id=sample_conversation.user_id,
                workspace_id=sample_conversation.workspace_id
            )

            # Verify assistant message call includes metadata
            assistant_call = mock_conversation_service.add_message.call_args_list[1]
            assert assistant_call.kwargs.get("metadata") is not None
            metadata = assistant_call.kwargs["metadata"]
            assert metadata["model"] == "claude-3-opus"
            assert metadata["tokens_used"] == 500

    @pytest.mark.asyncio
    async def test_assistant_response_without_result_key(
        self,
        mock_base_bridge,
        mock_conversation_service,
        sample_conversation
    ):
        """Test assistant response without 'result' key (no persistence)"""
        # Setup
        mock_conversation_service.get_conversation_by_session_key.return_value = sample_conversation
        mock_conversation_service.add_message.return_value = {"id": "user_msg"}

        # Response without 'result' key
        mock_base_bridge.send_to_agent.return_value = {
            "id": "gateway_msg",
            "status": "sent"
            # No 'result' key
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute
            await bridge.send_to_agent(
                session_key=sample_conversation.openclaw_session_key,
                message="Question",
                agent_id=sample_conversation.agent_id,
                user_id=sample_conversation.user_id,
                workspace_id=sample_conversation.workspace_id
            )

            # Verify only user message stored (no assistant message)
            assert mock_conversation_service.add_message.call_count == 1

    @pytest.mark.asyncio
    async def test_assistant_response_without_response_text(
        self,
        mock_base_bridge,
        mock_conversation_service,
        sample_conversation
    ):
        """Test assistant response without 'response' text (no persistence)"""
        # Setup
        mock_conversation_service.get_conversation_by_session_key.return_value = sample_conversation
        mock_conversation_service.add_message.return_value = {"id": "user_msg"}

        # Response with 'result' but no 'response' text
        mock_base_bridge.send_to_agent.return_value = {
            "id": "gateway_msg",
            "status": "sent",
            "result": {
                "model": "claude-3-5-sonnet"
                # No 'response' key
            }
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute
            await bridge.send_to_agent(
                session_key=sample_conversation.openclaw_session_key,
                message="Question",
                agent_id=sample_conversation.agent_id,
                user_id=sample_conversation.user_id,
                workspace_id=sample_conversation.workspace_id
            )

            # Verify only user message stored
            assert mock_conversation_service.add_message.call_count == 1


class TestSessionValidation:
    """Test session key validation"""

    @pytest.mark.asyncio
    async def test_send_to_agent_invalid_session_key(self, mock_base_bridge):
        """Test send_to_agent raises SessionError for invalid session key"""
        mock_base_bridge.is_connected = True

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            # Should raise SessionError for invalid format
            with pytest.raises(Exception):  # SessionError from protocol
                await bridge.send_to_agent(
                    session_key="invalid_format",  # Missing channel prefix
                    message="Test"
                )

    @pytest.mark.asyncio
    async def test_send_to_agent_empty_session_key(self, mock_base_bridge):
        """Test send_to_agent raises SessionError for empty session key"""
        mock_base_bridge.is_connected = True

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            # Should raise SessionError for empty key
            with pytest.raises(Exception):
                await bridge.send_to_agent(
                    session_key="",
                    message="Test"
                )


class TestConnectionHandling:
    """Test connection-related functionality"""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_base_bridge):
        """Test successful connection"""
        mock_base_bridge.connect = AsyncMock()

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            await bridge.connect()

            # Check connection state (enum name without .value)
            assert str(bridge.connection_state) == "BridgeConnectionState.CONNECTED"
            mock_base_bridge.connect.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_retries_on_failure(self, mock_base_bridge):
        """Test connect retries on failure"""
        # Fail once, succeed on second attempt
        mock_base_bridge.connect = AsyncMock(side_effect=[
            Exception("Connection failed"),
            None  # Success
        ])

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                max_retries=2,
                initial_delay=0.01
            )

            await bridge.connect()

            assert str(bridge.connection_state) == "BridgeConnectionState.CONNECTED"
            assert mock_base_bridge.connect.call_count == 2

    @pytest.mark.asyncio
    async def test_connect_exhausts_retries(self, mock_base_bridge):
        """Test connect raises ConnectionError after max retries"""
        mock_base_bridge.connect = AsyncMock(side_effect=Exception("Persistent connection error"))

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                max_retries=2,
                initial_delay=0.01
            )

            # Should raise ConnectionError after exhausting retries
            with pytest.raises(Exception):
                await bridge.connect()

            assert str(bridge.connection_state) == "BridgeConnectionState.FAILED"
            assert mock_base_bridge.connect.call_count == 2

    @pytest.mark.asyncio
    async def test_send_to_agent_disconnected_raises_error(self, mock_base_bridge):
        """Test send_to_agent raises ConnectionError when not connected"""
        mock_base_bridge.is_connected = False

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            # Should raise ConnectionError
            with pytest.raises(Exception):  # Using Exception since ConnectionError is from protocol
                await bridge.send_to_agent(
                    session_key="whatsapp:dm:test123",
                    message="Test"
                )

    @pytest.mark.asyncio
    async def test_send_to_agent_retries_on_failure(self, mock_base_bridge):
        """Test send_to_agent retries on transient failures"""
        mock_base_bridge.is_connected = True

        # Fail twice, succeed on third attempt
        mock_base_bridge.send_to_agent.side_effect = [
            Exception("Network error"),
            Exception("Timeout"),
            {"id": "msg_success", "result": {"response": "Success"}}
        ]

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                max_retries=3,
                initial_delay=0.01  # Fast retries for testing
            )

            # Should succeed after retries
            result = await bridge.send_to_agent(
                session_key="whatsapp:dm:retry_test",
                message="Test retry"
            )

            assert result["status"] == "sent"
            assert mock_base_bridge.send_to_agent.call_count == 3

    @pytest.mark.asyncio
    async def test_send_to_agent_exhausts_retries(self, mock_base_bridge):
        """Test send_to_agent raises SendError after max retries"""
        mock_base_bridge.is_connected = True
        mock_base_bridge.send_to_agent.side_effect = Exception("Persistent error")

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                max_retries=2,
                initial_delay=0.01
            )

            # Should raise SendError after exhausting retries
            with pytest.raises(Exception):
                await bridge.send_to_agent(
                    session_key="whatsapp:dm:exhaust_test",
                    message="Test exhausted retries"
                )

            # Verify it tried max_retries times
            assert mock_base_bridge.send_to_agent.call_count == 2


class TestExistingMethodsUnchanged:
    """Test existing bridge methods remain unchanged"""

    @pytest.mark.asyncio
    async def test_connect_method_unchanged(self, mock_base_bridge):
        """Test connect method still works"""
        mock_base_bridge.connect.return_value = None

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            await bridge.connect()
            mock_base_bridge.connect.assert_called()

    @pytest.mark.asyncio
    async def test_close_method_unchanged(self, mock_base_bridge):
        """Test close method still works"""
        mock_base_bridge.close.return_value = None

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            await bridge.close()
            mock_base_bridge.close.assert_called()

    def test_on_event_method_unchanged(self, mock_base_bridge):
        """Test on_event method still works"""
        handler = MagicMock()

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            bridge.on_event("test_event", handler)
            mock_base_bridge.on_event.assert_called_with("test_event", handler)

    def test_properties_unchanged(self, mock_base_bridge):
        """Test properties still work"""
        mock_base_bridge.is_connected = True

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )

            assert bridge.is_connected is True


class TestConversationContextLoading:
    """Test conversation context loading for message handlers"""

    @pytest.mark.asyncio
    async def test_load_conversation_context_retrieves_recent_messages(
        self,
        mock_conversation_service,
        sample_conversation
    ):
        """Test _load_conversation_context retrieves last N messages"""
        # Setup
        mock_messages = [
            {"id": "msg_1", "role": "user", "content": "First message", "timestamp": "2026-03-08T10:00:00Z"},
            {"id": "msg_2", "role": "assistant", "content": "First response", "timestamp": "2026-03-08T10:00:05Z"},
            {"id": "msg_3", "role": "user", "content": "Second message", "timestamp": "2026-03-08T10:01:00Z"},
        ]
        mock_conversation_service.get_messages.return_value = mock_messages

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge'):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute
            context = await bridge._load_conversation_context(
                conversation_id=sample_conversation.id,
                max_messages=10
            )

            # Verify
            assert context is not None
            assert len(context) == 3
            assert context[0]["content"] == "First message"
            assert context[2]["role"] == "user"
            mock_conversation_service.get_messages.assert_called_once_with(
                conversation_id=sample_conversation.id,
                limit=10,
                offset=0
            )

    @pytest.mark.asyncio
    async def test_load_conversation_context_respects_max_messages_limit(
        self,
        mock_conversation_service,
        sample_conversation
    ):
        """Test _load_conversation_context respects max_messages parameter"""
        mock_messages = [
            {"id": f"msg_{i}", "role": "user", "content": f"Message {i}"}
            for i in range(5)
        ]
        mock_conversation_service.get_messages.return_value = mock_messages

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge'):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute with max_messages=3
            context = await bridge._load_conversation_context(
                conversation_id=sample_conversation.id,
                max_messages=3
            )

            # Verify limit was applied
            mock_conversation_service.get_messages.assert_called_once_with(
                conversation_id=sample_conversation.id,
                limit=3,
                offset=0
            )

    @pytest.mark.asyncio
    async def test_load_conversation_context_returns_empty_on_error(
        self,
        mock_conversation_service,
        sample_conversation
    ):
        """Test _load_conversation_context returns empty list on error (graceful degradation)"""
        # Setup - simulate ZeroDB failure
        mock_conversation_service.get_messages.side_effect = Exception("ZeroDB unavailable")

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge'):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute - should not raise exception
            context = await bridge._load_conversation_context(
                conversation_id=sample_conversation.id,
                max_messages=10
            )

            # Verify graceful degradation
            assert context == []

    @pytest.mark.asyncio
    async def test_load_conversation_context_without_conversation_service(self):
        """Test _load_conversation_context returns empty list when service unavailable"""
        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge'):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            # No conversation service initialized

            # Execute
            context = await bridge._load_conversation_context(
                conversation_id=uuid4(),
                max_messages=10
            )

            # Verify empty context when service unavailable
            assert context == []


class TestConversationMetadataTracking:
    """Test conversation_id tracking in session metadata"""

    @pytest.mark.asyncio
    async def test_send_to_agent_returns_conversation_id_in_response(
        self,
        mock_base_bridge,
        mock_conversation_service,
        sample_conversation
    ):
        """Test send_to_agent includes conversation_id in response metadata"""
        # Setup
        mock_conversation_service.get_conversation_by_session_key.return_value = sample_conversation
        mock_conversation_service.add_message.return_value = {"id": "msg_123"}

        mock_base_bridge.send_to_agent.return_value = {
            "id": "gateway_msg",
            "status": "sent",
            "result": {"response": "Response text"}
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute
            result = await bridge.send_to_agent(
                session_key=sample_conversation.openclaw_session_key,
                message="Test message",
                agent_id=sample_conversation.agent_id,
                user_id=sample_conversation.user_id,
                workspace_id=sample_conversation.workspace_id
            )

            # Verify conversation_id in response metadata
            assert "conversation_id" in result
            assert result["conversation_id"] == str(sample_conversation.id)

    @pytest.mark.asyncio
    async def test_send_to_agent_no_conversation_id_when_persistence_disabled(
        self,
        mock_base_bridge
    ):
        """Test send_to_agent excludes conversation_id when persistence disabled"""
        # Setup
        mock_base_bridge.send_to_agent.return_value = {
            "id": "gateway_msg",
            "status": "sent"
        }

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            # No conversation service

            # Execute
            result = await bridge.send_to_agent(
                session_key="whatsapp:dm:test123",
                message="Test message"
            )

            # Verify no conversation_id when persistence disabled
            assert "conversation_id" not in result

    @pytest.mark.asyncio
    async def test_send_to_agent_conversation_id_added_to_custom_metadata(
        self,
        mock_base_bridge,
        mock_conversation_service,
        sample_conversation
    ):
        """Test send_to_agent merges conversation_id with custom metadata"""
        # Setup
        mock_conversation_service.get_conversation_by_session_key.return_value = sample_conversation
        mock_conversation_service.add_message.return_value = {"id": "msg_123"}

        mock_base_bridge.send_to_agent.return_value = {
            "id": "gateway_msg",
            "status": "sent",
            "result": {"response": "Response"}
        }

        custom_metadata = {"custom_field": "custom_value"}

        with patch('backend.agents.orchestration.production_openclaw_bridge.BaseOpenClawBridge', return_value=mock_base_bridge):
            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token"
            )
            bridge._conversation_service = mock_conversation_service

            # Execute with custom metadata
            result = await bridge.send_to_agent(
                session_key=sample_conversation.openclaw_session_key,
                message="Test",
                agent_id=sample_conversation.agent_id,
                user_id=sample_conversation.user_id,
                workspace_id=sample_conversation.workspace_id,
                metadata=custom_metadata
            )

            # Verify both conversation_id and custom metadata present
            assert result["conversation_id"] == str(sample_conversation.id)
            assert result["metadata"]["custom_field"] == "custom_value"
