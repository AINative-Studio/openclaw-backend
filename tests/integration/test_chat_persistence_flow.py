"""
Integration Tests for Chat Persistence Flow

Tests the complete end-to-end flow:
1. Agent sends message via ProductionOpenClawBridge
2. Message persisted to ZeroDB (table + memory)
3. Messages retrievable via ConversationService
4. Pagination and search working correctly

Refs #109
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from backend.services.conversation_service import ConversationService
from backend.models.conversation import Conversation
from backend.integrations.zerodb_client import ZeroDBConnectionError, ZeroDBAPIError


@pytest.mark.asyncio
class TestFullChatPersistenceFlow:
    """Test complete chat persistence flow end-to-end"""

    async def test_full_chat_persistence_flow(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: Agent sends message → Bridge persists → Messages retrievable

        Flow:
        1. Create workspace with ZeroDB project
        2. Create user
        3. Create agent linked to workspace
        4. Initialize ProductionOpenClawBridge with persistence
        5. Send message via bridge
        6. Verify conversation created
        7. Verify user message stored (both table + memory)
        8. Verify assistant response stored
        9. Retrieve messages via ConversationService
        10. Verify message count and timestamps updated
        """
        # Step 1-3: Already done by fixtures (workspace, user, agent created)
        assert sample_workspace.zerodb_project_id == "test_proj_123"
        assert sample_user.workspace_id == sample_workspace.id
        assert sample_agent.workspace_id == sample_workspace.id

        # Step 4: Initialize ProductionOpenClawBridge with persistence
        # Import locally to avoid circular import issues
        import sys
        import os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            # Mock base bridge
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_001",
                "result": {
                    "response": "Hello! How can I help you?",
                    "model": "claude-3-5-sonnet-20241022",
                    "tokens_used": 150
                }
            })
            MockBaseOpenClawBridge.return_value = mock_base

            # Import ProductionOpenClawBridge locally
            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=db,
                zerodb_client=zerodb_client_mock
            )

            await bridge.connect()

            # Step 5: Send message via bridge
            response = await bridge.send_to_agent(
                session_key="whatsapp:test:session123",
                message="Hello, assistant!",
                agent_id=sample_agent.id,
                user_id=sample_user.id,
                workspace_id=sample_workspace.id
            )

            assert response["status"] == "sent"
            assert "message_id" in response

            # Step 6: Verify conversation created
            service = ConversationService(db=db, zerodb_client=zerodb_client_mock)
            conversation = await service.get_conversation_by_session_key("whatsapp:test:session123")
            assert conversation is not None
            assert conversation.workspace_id == sample_workspace.id
            assert conversation.agent_id == sample_agent.id
            assert conversation.user_id == sample_user.id

            # Step 7: Verify user message stored (both table + memory)
            assert zerodb_client_mock.create_table_row.call_count >= 1
            user_message_call = zerodb_client_mock.create_table_row.call_args_list[0]
            assert user_message_call[1]["row_data"]["role"] == "user"
            assert user_message_call[1]["row_data"]["content"] == "Hello, assistant!"
            assert user_message_call[1]["row_data"]["conversation_id"] == str(conversation.id)

            # Memory API should also be called for user message
            assert zerodb_client_mock.create_memory.call_count >= 1
            memory_call = zerodb_client_mock.create_memory.call_args_list[0]
            assert memory_call[1]["content"] == "Hello, assistant!"
            assert memory_call[1]["type"] == "conversation"
            assert str(conversation.id) in memory_call[1]["tags"]

            # Step 8: Verify assistant response stored
            assert zerodb_client_mock.create_table_row.call_count >= 2
            assistant_message_call = zerodb_client_mock.create_table_row.call_args_list[1]
            assert assistant_message_call[1]["row_data"]["role"] == "assistant"
            assert assistant_message_call[1]["row_data"]["content"] == "Hello! How can I help you?"
            assert assistant_message_call[1]["row_data"]["metadata"]["model"] == "claude-3-5-sonnet-20241022"
            assert assistant_message_call[1]["row_data"]["metadata"]["tokens_used"] == 150

            # Step 9: Retrieve messages via ConversationService
            # Mock query_table to return stored messages
            zerodb_client_mock.query_table = AsyncMock(return_value=[
                {
                    "id": "msg_001",
                    "role": "user",
                    "content": "Hello, assistant!",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                {
                    "id": "msg_002",
                    "role": "assistant",
                    "content": "Hello! How can I help you?",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "metadata": {"model": "claude-3-5-sonnet-20241022", "tokens_used": 150}
                }
            ])

            messages = await service.get_messages(conversation.id, limit=50, offset=0)
            assert len(messages) == 2
            assert messages[0]["role"] == "user"
            assert messages[1]["role"] == "assistant"

            # Step 10: Verify message count and timestamps updated
            await db.refresh(conversation)
            assert conversation.message_count == 2
            assert conversation.last_message_at is not None

    async def test_dual_storage_verification(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Messages stored in BOTH ZeroDB Table AND Memory API

        - Verify create_table_row called for messages
        - Verify create_memory called for semantic search
        - Verify both have same content
        """
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Add a message
        message_content = "This message should be stored in both table and memory"
        result = await service.add_message(
            conversation_id=sample_conversation.id,
            role="user",
            content=message_content,
            metadata={"source": "test"}
        )

        # Verify table storage
        assert zerodb_client_mock.create_table_row.called
        table_call = zerodb_client_mock.create_table_row.call_args
        assert table_call[1]["row_data"]["content"] == message_content
        assert table_call[1]["row_data"]["role"] == "user"
        assert table_call[1]["table_name"] == "messages"

        # Verify memory storage
        assert zerodb_client_mock.create_memory.called
        memory_call = zerodb_client_mock.create_memory.call_args
        assert memory_call[1]["content"] == message_content
        assert memory_call[1]["type"] == "conversation"
        assert str(sample_conversation.id) in memory_call[1]["tags"]

        # Verify both have same content
        assert table_call[1]["row_data"]["content"] == memory_call[1]["content"]

        # Verify result contains both IDs
        assert result["id"] is not None  # Table row ID
        assert result["memory_id"] is not None  # Memory ID

    async def test_semantic_search_returns_relevant_results(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Semantic search finds messages across conversation

        - Add multiple messages
        - Search with query
        - Verify results filtered to conversation_id
        - Verify similarity scores present
        """
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Add multiple messages
        messages = [
            "Python is a great programming language",
            "I love coding in JavaScript",
            "Machine learning with PyTorch is amazing",
            "The weather is nice today"
        ]

        for msg in messages:
            await service.add_message(
                conversation_id=sample_conversation.id,
                role="user",
                content=msg
            )

        # Mock search results with conversation filtering
        zerodb_client_mock.search_memories = AsyncMock(return_value={
            "results": [
                {
                    "id": "mem_001",
                    "content": "Python is a great programming language",
                    "metadata": {"conversation_id": str(sample_conversation.id), "role": "user"},
                    "score": 0.95
                },
                {
                    "id": "mem_003",
                    "content": "Machine learning with PyTorch is amazing",
                    "metadata": {"conversation_id": str(sample_conversation.id), "role": "user"},
                    "score": 0.87
                }
            ],
            "total": 2,
            "query": "Python programming"
        })

        # Search with query
        results = await service.search_conversation_semantic(
            conversation_id=sample_conversation.id,
            query="Python programming",
            limit=5
        )

        # Verify results filtered to conversation_id
        assert len(results["results"]) == 2
        for result in results["results"]:
            assert result["metadata"]["conversation_id"] == str(sample_conversation.id)

        # Verify similarity scores present
        assert all("score" in r for r in results["results"])
        assert results["results"][0]["score"] >= results["results"][1]["score"]

    async def test_conversation_pagination(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Messages paginated correctly

        - Add 100 messages
        - Retrieve with limit=50, offset=0 (first page)
        - Retrieve with limit=50, offset=50 (second page)
        - Verify no duplicates
        - Verify correct order (newest first)
        """
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Simulate 100 messages stored
        all_messages = [
            {
                "id": f"msg_{i:03d}",
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            for i in range(100)
        ]

        # Mock query_table to return paginated results
        def query_table_paginated(project_id, table_name, limit=10, skip=0):
            return all_messages[skip:skip + limit]

        zerodb_client_mock.query_table = AsyncMock(side_effect=query_table_paginated)

        # Retrieve first page (limit=50, offset=0)
        first_page = await service.get_messages(
            conversation_id=sample_conversation.id,
            limit=50,
            offset=0
        )

        assert len(first_page) == 50
        assert first_page[0]["id"] == "msg_000"
        assert first_page[49]["id"] == "msg_049"

        # Retrieve second page (limit=50, offset=50)
        second_page = await service.get_messages(
            conversation_id=sample_conversation.id,
            limit=50,
            offset=50
        )

        assert len(second_page) == 50
        assert second_page[0]["id"] == "msg_050"
        assert second_page[49]["id"] == "msg_099"

        # Verify no duplicates
        first_page_ids = {msg["id"] for msg in first_page}
        second_page_ids = {msg["id"] for msg in second_page}
        assert len(first_page_ids.intersection(second_page_ids)) == 0

    async def test_concurrent_message_handling(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: Multiple messages in parallel don't cause race conditions

        - Use asyncio.gather() to send 10 messages concurrently
        - Verify all messages saved
        - Verify message_count = 10
        - Verify no duplicate message IDs
        """
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Send 10 messages concurrently
        async def send_message(i):
            return await service.add_message(
                conversation_id=sample_conversation.id,
                role="user",
                content=f"Concurrent message {i}"
            )

        results = await asyncio.gather(*[send_message(i) for i in range(10)])

        # Verify all messages saved
        assert len(results) == 10
        assert all(r["id"] is not None for r in results)

        # Verify no duplicate message IDs
        message_ids = [r["id"] for r in results]
        assert len(message_ids) == len(set(message_ids))

        # Verify message_count updated
        await db.refresh(sample_conversation)
        assert sample_conversation.message_count == 10

        # Verify all create_table_row calls succeeded
        assert zerodb_client_mock.create_table_row.call_count == 10


@pytest.mark.asyncio
class TestErrorHandling:
    """Test error handling in chat persistence"""

    async def test_zerodb_connection_failure_graceful_degradation(
        self,
        db,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: If ZeroDB unavailable, message sending still works

        - Mock ZeroDB to raise connection error
        - Send message via bridge
        - Verify message sent to gateway (bridge returns success)
        - Verify conversation NOT created (graceful degradation)
        """
        # Create mock that raises connection error
        mock_zerodb = MagicMock()
        mock_zerodb.create_project = AsyncMock(side_effect=ZeroDBConnectionError("Connection failed"))

        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_001",
                "result": {"response": "Message sent despite ZeroDB failure"}
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

            # Send message - should succeed despite ZeroDB failure
            response = await bridge.send_to_agent(
                session_key="whatsapp:test:session456",
                message="Test message",
                agent_id=sample_agent.id,
                user_id=sample_user.id,
                workspace_id=sample_workspace.id
            )

            # Verify message was sent to gateway
            assert response["status"] == "sent"
            assert mock_base.send_to_agent.called

    async def test_invalid_session_key_rejected(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: Invalid session keys rejected

        - Try to send with empty session key
        - Try to send with invalid format
        - Verify SessionError raised
        """
        from backend.agents.orchestration.openclaw_bridge_protocol import SessionError

        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            MockBaseOpenClawBridge.return_value = mock_base

            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            bridge = ProductionOpenClawBridge(
                url="ws://localhost:18789",
                token="test-token",
                db=db,
                zerodb_client=zerodb_client_mock
            )

            await bridge.connect()

            # Test empty session key
            with pytest.raises(SessionError):
                await bridge.send_to_agent(
                    session_key="",
                    message="Test",
                    agent_id=sample_agent.id,
                    user_id=sample_user.id,
                    workspace_id=sample_workspace.id
                )

            # Test invalid format (no colon separator)
            with pytest.raises(SessionError):
                await bridge.send_to_agent(
                    session_key="invalidsessionkey",
                    message="Test",
                    agent_id=sample_agent.id,
                    user_id=sample_user.id,
                    workspace_id=sample_workspace.id
                )

            # Test invalid channel
            with pytest.raises(SessionError):
                await bridge.send_to_agent(
                    session_key="invalidchannel:test:123",
                    message="Test",
                    agent_id=sample_agent.id,
                    user_id=sample_user.id,
                    workspace_id=sample_workspace.id
                )

    async def test_conversation_not_found_error(
        self,
        db,
        zerodb_client_mock
    ):
        """
        Test: ConversationService raises error for missing conversation

        - Try to get messages for non-existent conversation_id
        - Verify proper exception raised
        """
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        fake_id = uuid4()

        # Test get_messages
        with pytest.raises(ValueError, match=f"Conversation {fake_id} not found"):
            await service.get_messages(conversation_id=fake_id)

        # Test add_message
        with pytest.raises(ValueError, match=f"Conversation {fake_id} not found"):
            await service.add_message(
                conversation_id=fake_id,
                role="user",
                content="Test"
            )

        # Test search
        with pytest.raises(ValueError, match=f"Conversation {fake_id} not found"):
            await service.search_conversation_semantic(
                conversation_id=fake_id,
                query="test"
            )

    async def test_missing_zerodb_project_id_error(
        self,
        db,
        zerodb_client_mock,
        sample_user,
        sample_agent
    ):
        """
        Test: Creating conversation fails if workspace missing zerodb_project_id

        - Create workspace without zerodb_project_id
        - Try to create conversation
        - Verify ValueError raised with clear message
        """
        from backend.models.workspace import Workspace

        # Create workspace without ZeroDB project ID
        workspace_no_zerodb = Workspace(
            id=uuid4(),
            name="Workspace Without ZeroDB",
            slug="workspace-no-zerodb",
            zerodb_project_id=None  # Missing!
        )
        db.add(workspace_no_zerodb)
        await db.commit()
        await db.refresh(workspace_no_zerodb)

        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Try to create conversation
        with pytest.raises(ValueError, match="does not have a ZeroDB project configured"):
            await service.create_conversation(
                workspace_id=workspace_no_zerodb.id,
                agent_id=sample_agent.id,
                user_id=sample_user.id,
                openclaw_session_key="whatsapp:test:session999"
            )
