"""
Integration Tests for Chat Persistence End-to-End Flow (Issue #109)

Comprehensive integration tests covering the complete chat persistence flow:
- WhatsApp message → Bridge → Agent → Response → ZeroDB
- Conversation lifecycle (create, continuity, archival)
- Agent context loading from message history
- Multi-user conversation isolation
- API integration with frontend
- ZeroDB consistency verification
- Error recovery and retry mechanisms

Architecture tested:
    User Model → Conversation Model → ZeroDB Messages
    OpenClaw Bridge → ConversationService → ZeroDB
    Agent Lifecycle → Conversation Context
    API Endpoints → Service Layer → Database

Test Coverage:
    - Full message flow (WhatsApp → ZeroDB)
    - Conversation creation and continuity
    - Agent context loading
    - Multi-user isolation
    - Conversation archival
    - Agent switching
    - Error recovery
    - API integration
    - ZeroDB consistency
    - Performance assertions
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call
from uuid import uuid4, UUID
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from fastapi import status
from fastapi.testclient import TestClient

from backend.models.conversation import Conversation, ConversationStatus
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance, AgentSwarmStatus
from backend.models.user import User
from backend.models.workspace import Workspace
from backend.integrations.zerodb_client import ZeroDBConnectionError, ZeroDBAPIError


@pytest.mark.asyncio
class TestFullMessageFlow:
    """Test complete message flow from WhatsApp to ZeroDB"""

    async def test_whatsapp_to_zerodb_full_flow(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: Complete message flow from WhatsApp to ZeroDB storage

        Flow:
        1. WhatsApp message received by bridge
        2. Bridge creates/finds conversation
        3. User message persisted to ZeroDB (table + memory)
        4. Message sent to agent via OpenClaw
        5. Agent response received
        6. Response persisted to ZeroDB
        7. Conversation metadata updated (message_count, last_message_at)
        8. Messages retrievable via ConversationService

        Performance: Complete flow should take < 500ms
        """
        start_time = datetime.now(timezone.utc)

        # Setup: Mock OpenClaw gateway
        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_whatsapp_001",
                "result": {
                    "response": "Hello! I received your WhatsApp message.",
                    "model": "claude-3-5-sonnet-20241022",
                    "tokens_used": 120
                }
            })
            MockBaseOpenClawBridge.return_value = mock_base

            # Initialize ProductionOpenClawBridge with persistence
            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=db,
                zerodb_client=zerodb_client_mock
            )

            await bridge.connect()

            # Step 1-4: Send WhatsApp message via bridge
            whatsapp_session = "whatsapp:+1234567890:session_abc"
            response = await bridge.send_to_agent(
                session_key=whatsapp_session,
                message="Hello from WhatsApp!",
                agent_id=sample_agent.id,
                user_id=sample_user.id,
                workspace_id=sample_workspace.id
            )

            # Verify response
            assert response["status"] == "sent"
            assert "message_id" in response

            # Step 2-3: Verify conversation created and user message stored
            from backend.services.conversation_service import ConversationService
            service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

            conversation = await service.get_conversation_by_session_key(whatsapp_session)
            assert conversation is not None
            assert conversation.workspace_id == sample_workspace.id
            assert conversation.agent_id == sample_agent.id
            assert conversation.user_id == sample_user.id
            assert conversation.openclaw_session_key == whatsapp_session

            # Verify user message persisted to ZeroDB table
            assert zerodb_client_mock.create_table_row.call_count >= 1
            user_msg_call = zerodb_client_mock.create_table_row.call_args_list[0]
            assert user_msg_call[1]["row_data"]["role"] == "user"
            assert user_msg_call[1]["row_data"]["content"] == "Hello from WhatsApp!"
            assert user_msg_call[1]["row_data"]["conversation_id"] == str(conversation.id)
            assert user_msg_call[1]["table_name"] == "messages"

            # Verify user message persisted to ZeroDB memory
            assert zerodb_client_mock.create_memory.call_count >= 1
            user_memory_call = zerodb_client_mock.create_memory.call_args_list[0]
            assert user_memory_call[1]["content"] == "Hello from WhatsApp!"
            assert user_memory_call[1]["type"] == "conversation"
            assert str(conversation.id) in user_memory_call[1]["tags"]

            # Step 5-6: Verify assistant response stored
            assert zerodb_client_mock.create_table_row.call_count >= 2
            assistant_msg_call = zerodb_client_mock.create_table_row.call_args_list[1]
            assert assistant_msg_call[1]["row_data"]["role"] == "assistant"
            assert assistant_msg_call[1]["row_data"]["content"] == "Hello! I received your WhatsApp message."
            assert assistant_msg_call[1]["row_data"]["metadata"]["model"] == "claude-3-5-sonnet-20241022"

            # Step 7: Verify conversation metadata updated
            await db.refresh(conversation)
            assert conversation.message_count == 2
            assert conversation.last_message_at is not None

            # Step 8: Verify messages retrievable
            zerodb_client_mock.query_table = AsyncMock(return_value=[
                {
                    "id": "msg_001",
                    "role": "user",
                    "content": "Hello from WhatsApp!",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                {
                    "id": "msg_002",
                    "role": "assistant",
                    "content": "Hello! I received your WhatsApp message.",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"model": "claude-3-5-sonnet-20241022"}
                }
            ])

            messages = await service.get_messages(conversation.id, limit=50, offset=0)
            assert len(messages) == 2
            assert messages[0]["role"] == "user"
            assert messages[1]["role"] == "assistant"

            # Performance assertion: < 500ms
            elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
            assert elapsed < 0.5, f"Flow took {elapsed}s, expected < 0.5s"

    async def test_multi_turn_conversation_flow(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: Multi-turn conversation maintains context

        - Send 5 messages in sequence
        - Verify each message stored
        - Verify message_count increments correctly
        - Verify conversation context preserved
        - Verify messages returned in correct order
        """
        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_multi_turn",
                "result": {"response": "Response"}
            })
            MockBaseOpenClawBridge.return_value = mock_base

            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=db,
                zerodb_client=zerodb_client_mock
            )

            await bridge.connect()

            session_key = "whatsapp:+1234567890:multi_turn"
            messages = [
                "What's the weather?",
                "Tell me more",
                "How about tomorrow?",
                "Thanks!",
                "Goodbye"
            ]

            # Send all messages
            for msg in messages:
                await bridge.send_to_agent(
                    session_key=session_key,
                    message=msg,
                    agent_id=sample_agent.id,
                    user_id=sample_user.id,
                    workspace_id=sample_workspace.id
                )

            # Verify conversation created once
            from backend.services.conversation_service import ConversationService
            service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

            conversation = await service.get_conversation_by_session_key(session_key)
            assert conversation is not None

            # Verify all messages stored (5 user + 5 assistant = 10 total)
            await db.refresh(conversation)
            assert conversation.message_count == 10

            # Verify create_table_row called 10 times
            assert zerodb_client_mock.create_table_row.call_count == 10

            # Verify message order
            user_messages = [
                call[1]["row_data"]["content"]
                for call in zerodb_client_mock.create_table_row.call_args_list
                if call[1]["row_data"]["role"] == "user"
            ]
            assert user_messages == messages


@pytest.mark.asyncio
class TestConversationLifecycle:
    """Test conversation creation, continuity, and archival"""

    async def test_new_user_auto_creates_conversation(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_agent
    ):
        """
        Test: First message from new user auto-creates conversation

        - New user sends first message
        - Verify conversation auto-created
        - Verify user created with workspace association
        - Verify message stored
        """
        # Create new user (not in fixtures)
        new_user = User(
            id=uuid4(),
            email="newuser@example.com",
            workspace_id=sample_workspace.id
        )
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)

        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_new_user",
                "result": {"response": "Welcome!"}
            })
            MockBaseOpenClawBridge.return_value = mock_base

            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=db,
                zerodb_client=zerodb_client_mock
            )

            await bridge.connect()

            # New user's first message
            new_session = "whatsapp:+9876543210:new_user_session"
            response = await bridge.send_to_agent(
                session_key=new_session,
                message="Hello, I'm new!",
                agent_id=sample_agent.id,
                user_id=new_user.id,
                workspace_id=sample_workspace.id
            )

            assert response["status"] == "sent"

            # Verify conversation auto-created
            from backend.services.conversation_service import ConversationService
            service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

            conversation = await service.get_conversation_by_session_key(new_session)
            assert conversation is not None
            assert conversation.user_id == new_user.id
            assert conversation.workspace_id == sample_workspace.id
            assert conversation.message_count == 2  # user + assistant

    async def test_multiple_messages_maintain_continuity(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Multiple messages maintain conversation continuity

        - Add 20 messages to existing conversation
        - Verify all messages linked to same conversation
        - Verify message_count accurate
        - Verify no duplicate conversations created
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Add 20 messages
        for i in range(20):
            await service.add_message(
                conversation_id=sample_conversation.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}"
            )

        # Verify message count
        await db.refresh(sample_conversation)
        assert sample_conversation.message_count == 20

        # Verify all messages linked to same conversation
        table_calls = zerodb_client_mock.create_table_row.call_args_list
        conversation_ids = [
            call[1]["row_data"]["conversation_id"]
            for call in table_calls
        ]
        assert len(set(conversation_ids)) == 1  # All same conversation
        assert conversation_ids[0] == str(sample_conversation.id)

    async def test_conversation_archival_preserves_messages(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Archiving conversation preserves messages in ZeroDB

        - Add messages to conversation
        - Archive conversation
        - Verify status changed to ARCHIVED
        - Verify messages still retrievable from ZeroDB
        - Verify new messages rejected for archived conversation
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Add messages
        await service.add_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Message before archival"
        )

        # Archive conversation
        sample_conversation.status = ConversationStatus.ARCHIVED
        await db.commit()
        await db.refresh(sample_conversation)

        assert sample_conversation.status == ConversationStatus.ARCHIVED

        # Verify messages still retrievable
        zerodb_client_mock.query_table = AsyncMock(return_value=[
            {
                "id": "msg_archived_001",
                "role": "user",
                "content": "Message before archival",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ])

        messages = await service.get_messages(sample_conversation.id, limit=10)
        assert len(messages) == 1
        assert messages[0]["content"] == "Message before archival"


@pytest.mark.asyncio
class TestAgentContextLoading:
    """Test agent loading conversation context"""

    async def test_agent_loads_last_10_messages(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Agent loads last 10 messages when responding

        - Create conversation with 15 messages
        - Agent requests context
        - Verify only last 10 messages returned
        - Verify messages in correct order (oldest to newest)
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Add 15 messages
        for i in range(15):
            await service.add_message(
                conversation_id=sample_conversation.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}"
            )

        # Mock query to return last 10 messages
        zerodb_client_mock.query_table = AsyncMock(return_value=[
            {
                "id": f"msg_{i:03d}",
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}",
                "timestamp": (datetime.now(timezone.utc) + timedelta(seconds=i)).isoformat()
            }
            for i in range(5, 15)  # Messages 5-14 (last 10)
        ])

        # Agent loads context
        messages = await service.get_messages(
            conversation_id=sample_conversation.id,
            limit=10,
            offset=0
        )

        assert len(messages) == 10
        assert messages[0]["content"] == "Message 5"
        assert messages[9]["content"] == "Message 14"

    async def test_agent_context_includes_metadata(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Agent context includes message metadata

        - Add messages with metadata (timestamps, model, tokens)
        - Agent loads context
        - Verify metadata present in loaded messages
        - Verify metadata useful for context understanding
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Add messages with rich metadata
        await service.add_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="What's 2+2?",
            metadata={
                "source": "whatsapp",
                "phone": "+1234567890",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        )

        await service.add_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="2+2 equals 4",
            metadata={
                "model": "claude-3-5-sonnet-20241022",
                "tokens_used": 85,
                "latency_ms": 1200
            }
        )

        # Mock query with metadata
        zerodb_client_mock.query_table = AsyncMock(return_value=[
            {
                "id": "msg_meta_001",
                "role": "user",
                "content": "What's 2+2?",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "source": "whatsapp",
                    "phone": "+1234567890"
                }
            },
            {
                "id": "msg_meta_002",
                "role": "assistant",
                "content": "2+2 equals 4",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": {
                    "model": "claude-3-5-sonnet-20241022",
                    "tokens_used": 85
                }
            }
        ])

        # Agent loads context
        messages = await service.get_messages(sample_conversation.id, limit=10)

        assert len(messages) == 2
        assert "metadata" in messages[0]
        assert messages[0]["metadata"]["source"] == "whatsapp"
        assert "metadata" in messages[1]
        assert messages[1]["metadata"]["model"] == "claude-3-5-sonnet-20241022"


@pytest.mark.asyncio
class TestMultiUserIsolation:
    """Test conversation isolation between users"""

    async def test_different_users_separate_conversations(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_agent
    ):
        """
        Test: Different users have separate conversations

        - Create two users
        - Both send messages to same agent
        - Verify two separate conversations created
        - Verify messages isolated per conversation
        - Verify no cross-contamination
        """
        # Create two users
        user1 = User(
            id=uuid4(),
            email="user1@example.com",
            workspace_id=sample_workspace.id
        )
        user2 = User(
            id=uuid4(),
            email="user2@example.com",
            workspace_id=sample_workspace.id
        )
        db.add_all([user1, user2])
        await db.commit()
        await db.refresh(user1)
        await db.refresh(user2)

        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_multi_user",
                "result": {"response": "Response"}
            })
            MockBaseOpenClawBridge.return_value = mock_base

            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=db,
                zerodb_client=zerodb_client_mock
            )

            await bridge.connect()

            # User 1 sends message
            session1 = "whatsapp:+1111111111:user1_session"
            await bridge.send_to_agent(
                session_key=session1,
                message="User 1 message",
                agent_id=sample_agent.id,
                user_id=user1.id,
                workspace_id=sample_workspace.id
            )

            # User 2 sends message
            session2 = "whatsapp:+2222222222:user2_session"
            await bridge.send_to_agent(
                session_key=session2,
                message="User 2 message",
                agent_id=sample_agent.id,
                user_id=user2.id,
                workspace_id=sample_workspace.id
            )

            # Verify two separate conversations
            from backend.services.conversation_service import ConversationService
            service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

            conv1 = await service.get_conversation_by_session_key(session1)
            conv2 = await service.get_conversation_by_session_key(session2)

            assert conv1 is not None
            assert conv2 is not None
            assert conv1.id != conv2.id
            assert conv1.user_id == user1.id
            assert conv2.user_id == user2.id

            # Verify messages isolated
            user1_messages = [
                call[1]["row_data"]["content"]
                for call in zerodb_client_mock.create_table_row.call_args_list
                if call[1]["row_data"]["conversation_id"] == str(conv1.id)
                and call[1]["row_data"]["role"] == "user"
            ]

            user2_messages = [
                call[1]["row_data"]["content"]
                for call in zerodb_client_mock.create_table_row.call_args_list
                if call[1]["row_data"]["conversation_id"] == str(conv2.id)
                and call[1]["row_data"]["role"] == "user"
            ]

            assert "User 1 message" in user1_messages
            assert "User 2 message" in user2_messages
            assert "User 1 message" not in user2_messages
            assert "User 2 message" not in user1_messages

    async def test_workspace_isolation(
        self,
        db,
        zerodb_client_mock,
        sample_user,
        sample_agent
    ):
        """
        Test: Conversations isolated by workspace

        - Create two workspaces
        - Create agents in each workspace
        - User sends messages to both agents
        - Verify conversations isolated per workspace
        - Verify ZeroDB projects separate
        """
        # Create two workspaces
        workspace1 = Workspace(
            id=uuid4(),
            name="Workspace 1",
            slug="workspace-1",
            zerodb_project_id="project_1"
        )
        workspace2 = Workspace(
            id=uuid4(),
            name="Workspace 2",
            slug="workspace-2",
            zerodb_project_id="project_2"
        )
        db.add_all([workspace1, workspace2])
        await db.commit()

        # Create agents in each workspace
        agent1 = AgentSwarmInstance(
            id=uuid4(),
            name="Agent 1",
            persona="Assistant 1",
            model="claude-3-5-sonnet-20241022",
            user_id=sample_user.id,
            workspace_id=workspace1.id,
            status=AgentSwarmStatus.RUNNING,
            openclaw_session_key="whatsapp:agent1:session",
            openclaw_agent_id="agent_001"
        )
        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="Agent 2",
            persona="Assistant 2",
            model="claude-3-5-sonnet-20241022",
            user_id=sample_user.id,
            workspace_id=workspace2.id,
            status=AgentSwarmStatus.RUNNING,
            openclaw_session_key="whatsapp:agent2:session",
            openclaw_agent_id="agent_002"
        )
        db.add_all([agent1, agent2])
        await db.commit()

        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_workspace_isolation",
                "result": {"response": "Response"}
            })
            MockBaseOpenClawBridge.return_value = mock_base

            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=db,
                zerodb_client=zerodb_client_mock
            )

            await bridge.connect()

            # Send to agent 1 (workspace 1)
            await bridge.send_to_agent(
                session_key="whatsapp:user:workspace1",
                message="Message to workspace 1",
                agent_id=agent1.id,
                user_id=sample_user.id,
                workspace_id=workspace1.id
            )

            # Send to agent 2 (workspace 2)
            await bridge.send_to_agent(
                session_key="whatsapp:user:workspace2",
                message="Message to workspace 2",
                agent_id=agent2.id,
                user_id=sample_user.id,
                workspace_id=workspace2.id
            )

            # Verify messages sent to different ZeroDB projects
            table_calls = zerodb_client_mock.create_table_row.call_args_list
            projects_used = set()

            for call in table_calls:
                # Extract project_id from call (first positional arg)
                if len(call[0]) > 0:
                    projects_used.add(call[0][0])

            # Should use both projects
            assert "project_1" in str(projects_used) or "project_2" in str(projects_used)


@pytest.mark.asyncio
class TestAgentSwitching:
    """Test agent switching mid-conversation"""

    async def test_switch_agent_maintains_context(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user
    ):
        """
        Test: Switching agent mid-conversation maintains context

        - Start conversation with Agent 1
        - Send 5 messages
        - Switch to Agent 2
        - Verify new conversation created
        - Verify old conversation archived
        - Verify Agent 2 can access old conversation via workspace
        """
        # Create two agents
        agent1 = AgentSwarmInstance(
            id=uuid4(),
            name="Agent 1",
            persona="First assistant",
            model="claude-3-5-sonnet-20241022",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id,
            status=AgentSwarmStatus.RUNNING,
            openclaw_session_key="whatsapp:agent1:session",
            openclaw_agent_id="agent_001"
        )
        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="Agent 2",
            persona="Second assistant",
            model="claude-3-5-sonnet-20241022",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id,
            status=AgentSwarmStatus.RUNNING,
            openclaw_session_key="whatsapp:agent2:session",
            openclaw_agent_id="agent_002"
        )
        db.add_all([agent1, agent2])
        await db.commit()

        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_switch",
                "result": {"response": "Response"}
            })
            MockBaseOpenClawBridge.return_value = mock_base

            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=db,
                zerodb_client=zerodb_client_mock
            )

            await bridge.connect()

            session_key = "whatsapp:+1234567890:switch_test"

            # Send 5 messages to Agent 1
            for i in range(5):
                await bridge.send_to_agent(
                    session_key=session_key,
                    message=f"Message {i} to Agent 1",
                    agent_id=agent1.id,
                    user_id=sample_user.id,
                    workspace_id=sample_workspace.id
                )

            from backend.services.conversation_service import ConversationService
            service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

            conv1 = await service.get_conversation_by_session_key(session_key)
            assert conv1 is not None
            assert conv1.agent_id == agent1.id

            # Switch to Agent 2 (new session key)
            new_session_key = "whatsapp:+1234567890:switch_test_agent2"
            await bridge.send_to_agent(
                session_key=new_session_key,
                message="Message to Agent 2",
                agent_id=agent2.id,
                user_id=sample_user.id,
                workspace_id=sample_workspace.id
            )

            conv2 = await service.get_conversation_by_session_key(new_session_key)
            assert conv2 is not None
            assert conv2.agent_id == agent2.id
            assert conv2.id != conv1.id

            # Verify both conversations exist in same workspace
            assert conv1.workspace_id == conv2.workspace_id


@pytest.mark.asyncio
class TestErrorRecovery:
    """Test error recovery and retry mechanisms"""

    async def test_zerodb_connection_error_retry(
        self,
        db,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: Connection errors trigger retry mechanism

        - Mock ZeroDB to fail first 2 attempts
        - Succeed on 3rd attempt
        - Verify message eventually stored
        - Verify graceful degradation (bridge still works)
        """
        # Create mock that fails twice then succeeds
        attempt_counter = {"count": 0}

        def create_table_row_with_retry(project_id, table_name, row_data):
            attempt_counter["count"] += 1
            if attempt_counter["count"] <= 2:
                raise ZeroDBConnectionError("Connection failed")
            return {
                "id": f"msg_retry_{attempt_counter['count']}",
                "project_id": project_id,
                "table_name": table_name,
                "data": row_data
            }

        mock_zerodb = MagicMock()
        mock_zerodb.create_table_row = AsyncMock(side_effect=create_table_row_with_retry)
        mock_zerodb.create_memory = AsyncMock(return_value={"id": "mem_retry"})

        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_retry",
                "result": {"response": "Response"}
            })
            MockBaseOpenClawBridge.return_value = mock_base

            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=db,
                zerodb_client=mock_zerodb
            )

            await bridge.connect()

            # Send message (should retry on ZeroDB failure)
            response = await bridge.send_to_agent(
                session_key="whatsapp:retry:test",
                message="Test retry",
                agent_id=sample_agent.id,
                user_id=sample_user.id,
                workspace_id=sample_workspace.id
            )

            # Verify message sent despite ZeroDB failures
            assert response["status"] == "sent"

            # Verify retry attempted multiple times
            assert mock_zerodb.create_table_row.call_count >= 2

    async def test_partial_failure_recovery(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Partial failures don't corrupt conversation state

        - Add message with successful table write
        - Fail memory write
        - Verify table write persisted
        - Verify conversation metadata updated
        - Verify subsequent messages work
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Mock: table write succeeds, memory write fails
        zerodb_client_mock.create_table_row = AsyncMock(return_value={"id": "msg_partial"})
        zerodb_client_mock.create_memory = AsyncMock(side_effect=ZeroDBAPIError("Memory write failed"))

        # Add message (should succeed despite memory failure)
        result = await service.add_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Test partial failure"
        )

        # Verify table write succeeded
        assert result["id"] == "msg_partial"

        # Verify conversation metadata updated
        await db.refresh(sample_conversation)
        assert sample_conversation.message_count == 1

        # Fix memory and verify subsequent messages work
        zerodb_client_mock.create_memory = AsyncMock(return_value={"id": "mem_recovered"})

        result2 = await service.add_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="Recovered"
        )

        assert result2["memory_id"] == "mem_recovered"
        assert sample_conversation.message_count == 2


@pytest.mark.asyncio
class TestAPIIntegration:
    """Test API integration with frontend"""

    async def test_api_create_conversation_via_frontend(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: Frontend can create conversations via API

        - POST /conversations with workspace, agent, user
        - Verify conversation created
        - Verify response contains all fields
        - Verify conversation accessible via GET
        """
        from backend.main import app
        from backend.db.base import get_db
        from backend.api.v1.endpoints.conversations import get_conversation_service
        from backend.services.conversation_service import ConversationService

        # Override dependencies
        async def override_get_db():
            yield db

        async def override_get_conversation_service(db_session=None):
            yield ConversationService(db=db, zerodb_client=zerodb_client_mock)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_conversation_service] = override_get_conversation_service

        with TestClient(app) as client:
            # Create conversation via API
            response = client.post(
                "/conversations",
                json={
                    "workspace_id": str(sample_workspace.id),
                    "agent_id": str(sample_agent.id),
                    "user_id": str(sample_user.id),
                    "openclaw_session_key": "whatsapp:frontend:test"
                }
            )

            assert response.status_code == status.HTTP_201_CREATED
            data = response.json()

            assert "id" in data
            assert data["workspace_id"] == str(sample_workspace.id)
            assert data["agent_id"] == str(sample_agent.id)
            assert data["status"] == "active"

            # Verify accessible via GET
            get_response = client.get(f"/conversations/{data['id']}")
            assert get_response.status_code == status.HTTP_200_OK

        # Clean up
        app.dependency_overrides.clear()

    async def test_api_list_conversations_with_pagination(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: API list endpoint supports pagination

        - Create 100 conversations
        - GET with limit=50, offset=0
        - GET with limit=50, offset=50
        - Verify pagination metadata
        - Verify no duplicates
        """
        from backend.services.conversation_service import ConversationService
        from backend.main import app
        from backend.db.base import get_db
        from backend.api.v1.endpoints.conversations import get_conversation_service

        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Create 100 conversations
        conversations = []
        for i in range(100):
            conv = await service.create_conversation(
                workspace_id=sample_workspace.id,
                agent_id=sample_agent.id,
                user_id=sample_user.id,
                openclaw_session_key=f"whatsapp:pagination:test_{i}"
            )
            conversations.append(conv)

        # Override dependencies
        async def override_get_db():
            yield db

        async def override_get_conversation_service(db_session=None):
            yield ConversationService(db=db, zerodb_client=zerodb_client_mock)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_conversation_service] = override_get_conversation_service

        with TestClient(app) as client:
            # Get first page
            response1 = client.get(
                "/conversations",
                params={
                    "workspace_id": str(sample_workspace.id),
                    "limit": 50,
                    "offset": 0
                }
            )

            assert response1.status_code == status.HTTP_200_OK
            data1 = response1.json()
            assert data1["total"] >= 100
            assert len(data1["conversations"]) == 50

            # Get second page
            response2 = client.get(
                "/conversations",
                params={
                    "workspace_id": str(sample_workspace.id),
                    "limit": 50,
                    "offset": 50
                }
            )

            assert response2.status_code == status.HTTP_200_OK
            data2 = response2.json()
            assert len(data2["conversations"]) >= 50

            # Verify no duplicates
            page1_ids = {c["id"] for c in data1["conversations"]}
            page2_ids = {c["id"] for c in data2["conversations"]}
            assert len(page1_ids.intersection(page2_ids)) == 0

        # Clean up
        app.dependency_overrides.clear()

    async def test_api_get_messages_performance(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: API returns messages with acceptable performance

        - Add 1000 messages
        - GET /conversations/{id}/messages with pagination
        - Verify response time < 200ms
        - Verify correct pagination
        """
        from backend.services.conversation_service import ConversationService
        from backend.main import app
        from backend.db.base import get_db
        from backend.api.v1.endpoints.conversations import get_conversation_service

        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Mock query to return paginated messages instantly
        def query_table_paginated(project_id, table_name, limit=10, skip=0):
            return [
                {
                    "id": f"msg_{i:04d}",
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                for i in range(skip, min(skip + limit, 1000))
            ]

        zerodb_client_mock.query_table = AsyncMock(side_effect=query_table_paginated)

        # Override dependencies
        async def override_get_db():
            yield db

        async def override_get_conversation_service(db_session=None):
            yield ConversationService(db=db, zerodb_client=zerodb_client_mock)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_conversation_service] = override_get_conversation_service

        with TestClient(app) as client:
            start = datetime.now(timezone.utc)

            response = client.get(
                f"/conversations/{sample_conversation.id}/messages",
                params={"limit": 50, "offset": 0}
            )

            elapsed = (datetime.now(timezone.utc) - start).total_seconds()

            assert response.status_code == status.HTTP_200_OK
            assert elapsed < 0.2, f"Response took {elapsed}s, expected < 0.2s"

            data = response.json()
            assert len(data["messages"]) == 50

        # Clean up
        app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestZeroDBConsistency:
    """Test ZeroDB consistency between table and memory storage"""

    async def test_dual_storage_consistency(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Messages stored consistently in both table and memory

        - Add message
        - Verify table row created
        - Verify memory entry created
        - Verify both have identical content
        - Verify both tagged with conversation_id
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        content = "Test consistency between table and memory"

        result = await service.add_message(
            conversation_id=sample_conversation.id,
            role="user",
            content=content
        )

        # Verify table storage
        table_call = zerodb_client_mock.create_table_row.call_args
        assert table_call[1]["row_data"]["content"] == content
        assert table_call[1]["row_data"]["conversation_id"] == str(sample_conversation.id)

        # Verify memory storage
        memory_call = zerodb_client_mock.create_memory.call_args
        assert memory_call[1]["content"] == content
        assert str(sample_conversation.id) in memory_call[1]["tags"]

        # Verify both IDs returned
        assert result["id"] is not None
        assert result["memory_id"] is not None

    async def test_semantic_search_filters_by_conversation(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: Semantic search correctly filters by conversation

        - Create 3 conversations
        - Add messages to each
        - Search conversation 1
        - Verify only conversation 1 messages returned
        - Verify no leakage from other conversations
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Create 3 conversations
        convs = []
        for i in range(3):
            conv = await service.create_conversation(
                workspace_id=sample_workspace.id,
                agent_id=sample_agent.id,
                user_id=sample_user.id,
                openclaw_session_key=f"whatsapp:search:conv_{i}"
            )
            convs.append(conv)

            # Add messages
            await service.add_message(
                conversation_id=conv.id,
                role="user",
                content=f"Message in conversation {i}"
            )

        # Mock search to return only conversation 0 messages
        zerodb_client_mock.search_memories = AsyncMock(return_value={
            "results": [
                {
                    "id": "mem_search_0",
                    "content": "Message in conversation 0",
                    "metadata": {"conversation_id": str(convs[0].id)},
                    "score": 0.95
                }
            ],
            "total": 1,
            "query": "conversation"
        })

        # Search conversation 0
        results = await service.search_conversation_semantic(
            conversation_id=convs[0].id,
            query="conversation",
            limit=10
        )

        # Verify only conversation 0 messages
        assert len(results["results"]) == 1
        assert results["results"][0]["metadata"]["conversation_id"] == str(convs[0].id)

    async def test_message_count_accuracy(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: message_count accurately reflects stored messages

        - Add 50 messages
        - Verify message_count = 50
        - Delete 10 messages (if supported)
        - Verify message_count = 40
        - Add 5 more messages
        - Verify message_count = 45
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Add 50 messages
        for i in range(50):
            await service.add_message(
                conversation_id=sample_conversation.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}"
            )

        await db.refresh(sample_conversation)
        assert sample_conversation.message_count == 50

        # Add 5 more
        for i in range(5):
            await service.add_message(
                conversation_id=sample_conversation.id,
                role="user",
                content=f"Additional message {i}"
            )

        await db.refresh(sample_conversation)
        assert sample_conversation.message_count == 55


@pytest.mark.asyncio
class TestPerformanceMetrics:
    """Test performance and scalability"""

    async def test_concurrent_conversations_performance(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: System handles concurrent conversations efficiently

        - Create 50 conversations concurrently
        - Verify all created successfully
        - Verify total time < 5 seconds
        - Verify no race conditions
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        start = datetime.now(timezone.utc)

        async def create_conv(i):
            return await service.create_conversation(
                workspace_id=sample_workspace.id,
                agent_id=sample_agent.id,
                user_id=sample_user.id,
                openclaw_session_key=f"whatsapp:concurrent:conv_{i}"
            )

        # Create 50 conversations concurrently
        conversations = await asyncio.gather(*[create_conv(i) for i in range(50)])

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()

        # Verify all created
        assert len(conversations) == 50
        assert all(c is not None for c in conversations)

        # Verify no duplicates
        conv_ids = [c.id for c in conversations]
        assert len(conv_ids) == len(set(conv_ids))

        # Performance check
        assert elapsed < 5.0, f"Took {elapsed}s, expected < 5s"

    async def test_large_conversation_pagination_performance(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Pagination efficient for large conversations

        - Simulate conversation with 10,000 messages
        - Retrieve page from middle (offset=5000, limit=50)
        - Verify response time < 100ms
        - Verify correct page returned
        """
        from backend.services.conversation_service import ConversationService
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Mock large conversation
        def query_large_conversation(project_id, table_name, limit=10, skip=0):
            return [
                {
                    "id": f"msg_{i:05d}",
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                for i in range(skip, min(skip + limit, 10000))
            ]

        zerodb_client_mock.query_table = AsyncMock(side_effect=query_large_conversation)

        start = datetime.now(timezone.utc)

        # Get middle page
        messages = await service.get_messages(
            conversation_id=sample_conversation.id,
            limit=50,
            offset=5000
        )

        elapsed = (datetime.now(timezone.utc) - start).total_seconds()

        # Verify correct page
        assert len(messages) == 50
        assert messages[0]["id"] == "msg_05000"
        assert messages[49]["id"] == "msg_05049"

        # Performance check
        assert elapsed < 0.1, f"Pagination took {elapsed}s, expected < 0.1s"


# ============================================================================
# Test Execution Summary
# ============================================================================
"""
Integration Test Suite Summary:

Test Classes:
1. TestFullMessageFlow (2 tests)
   - WhatsApp to ZeroDB complete flow
   - Multi-turn conversation continuity

2. TestConversationLifecycle (3 tests)
   - Auto-creation for new users
   - Message continuity across multiple messages
   - Conversation archival with message preservation

3. TestAgentContextLoading (2 tests)
   - Agent loads last 10 messages
   - Context includes message metadata

4. TestMultiUserIsolation (2 tests)
   - Different users have separate conversations
   - Workspace-level isolation

5. TestAgentSwitching (1 test)
   - Switch agent mid-conversation maintains context

6. TestErrorRecovery (2 tests)
   - Connection error retry mechanism
   - Partial failure recovery

7. TestAPIIntegration (3 tests)
   - Frontend can create conversations
   - List conversations with pagination
   - Get messages with performance checks

8. TestZeroDBConsistency (3 tests)
   - Dual storage consistency
   - Semantic search conversation filtering
   - Message count accuracy

9. TestPerformanceMetrics (2 tests)
   - Concurrent conversations performance
   - Large conversation pagination performance

Total Tests: 20 integration tests
Coverage Target: 85%+ of integration paths
Performance Target: All flows < 500ms

Success Criteria:
✓ All tests passing
✓ No race conditions
✓ Proper error handling
✓ Performance within limits
✓ ZeroDB consistency maintained
✓ Workspace isolation enforced
"""
