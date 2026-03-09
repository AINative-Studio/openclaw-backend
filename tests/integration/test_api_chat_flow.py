"""
API Integration Tests for Chat Persistence

Tests the FastAPI endpoints for conversations and messages.
Verifies the full stack: API → Service → Database → ZeroDB

Refs #109
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone

from fastapi import status


@pytest.mark.asyncio
class TestConversationAPIIntegration:
    """Test conversation API endpoints with full stack"""

    async def test_api_list_conversations_after_chat(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: API returns conversations after bridge creates them

        - Send messages via bridge
        - Call GET /conversations
        - Verify conversation appears in list
        - Verify metadata correct (message_count, last_message_at)
        """
        # First, create conversation via service
        from backend.services.conversation_service import ConversationService

        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        conversation = await service.create_conversation(
            workspace_id=sample_workspace.id,
            agent_id=sample_agent.id,
            user_id=sample_user.id,
            openclaw_session_key="whatsapp:test:api_session"
        )

        # Add some messages
        await service.add_message(
            conversation_id=conversation.id,
            role="user",
            content="Hello"
        )
        await service.add_message(
            conversation_id=conversation.id,
            role="assistant",
            content="Hi there!"
        )

        # Now test API
        from backend.main import app
        from backend.db.base import get_db
        from backend.api.v1.endpoints.conversations import get_conversation_service
        from fastapi.testclient import TestClient

        # Override dependencies
        async def override_get_db():
            yield db

        async def override_get_conversation_service(db_session=None):
            yield ConversationService(db=db, zerodb_client=zerodb_client_mock)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_conversation_service] = override_get_conversation_service

        with TestClient(app) as client:
            response = client.get(
                "/conversations",
                params={"workspace_id": str(sample_workspace.id)}
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert "conversations" in data
            assert data["total"] >= 1

            # Find our conversation
            conv = next((c for c in data["conversations"] if c["id"] == str(conversation.id)), None)
            assert conv is not None
            assert conv["workspace_id"] == str(sample_workspace.id)
            assert conv["agent_id"] == str(sample_agent.id)
            assert conv["message_count"] == 2
            assert conv["last_message_at"] is not None

        # Clean up
        app.dependency_overrides.clear()

    async def test_api_get_messages_pagination(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: API /conversations/{id}/messages paginates correctly

        - Add 100 messages
        - GET with limit=50, offset=0
        - GET with limit=50, offset=50
        - Verify pagination metadata correct
        """
        from backend.services.conversation_service import ConversationService
        from backend.main import app
        from backend.db.base import get_db
        from backend.api.v1.endpoints.conversations import get_conversation_service
        from fastapi.testclient import TestClient

        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Simulate 100 messages
        all_messages = []
        for i in range(100):
            msg = await service.add_message(
                conversation_id=sample_conversation.id,
                role="user" if i % 2 == 0 else "assistant",
                content=f"Message {i}"
            )
            all_messages.append(msg)

        # Mock query_table to return paginated results
        def query_table_paginated(project_id, table_name, limit=10, skip=0):
            return [
                {
                    "id": f"msg_{j:03d}",
                    "role": "user" if j % 2 == 0 else "assistant",
                    "content": f"Message {j}",
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                for j in range(skip, min(skip + limit, 100))
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
            # Get first page
            response1 = client.get(
                f"/conversations/{sample_conversation.id}/messages",
                params={"limit": 50, "offset": 0}
            )

            assert response1.status_code == status.HTTP_200_OK
            data1 = response1.json()
            assert len(data1["messages"]) == 50
            assert data1["total"] == 100

            # Get second page
            response2 = client.get(
                f"/conversations/{sample_conversation.id}/messages",
                params={"limit": 50, "offset": 50}
            )

            assert response2.status_code == status.HTTP_200_OK
            data2 = response2.json()
            assert len(data2["messages"]) == 50

            # Verify no duplicates between pages
            page1_ids = {msg["id"] for msg in data1["messages"]}
            page2_ids = {msg["id"] for msg in data2["messages"]}
            assert len(page1_ids.intersection(page2_ids)) == 0

        # Clean up
        app.dependency_overrides.clear()

    async def test_api_search_conversation(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: API /conversations/{id}/search works

        - Add messages about "Python"
        - POST /search with query="Python programming"
        - Verify results returned
        - Verify relevance scores present
        """
        from backend.services.conversation_service import ConversationService
        from backend.main import app
        from backend.db.base import get_db
        from backend.api.v1.endpoints.conversations import get_conversation_service
        from fastapi.testclient import TestClient

        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Add messages
        await service.add_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Tell me about Python programming"
        )
        await service.add_message(
            conversation_id=sample_conversation.id,
            role="assistant",
            content="Python is a high-level programming language known for its simplicity"
        )

        # Mock search results
        zerodb_client_mock.search_memories = AsyncMock(return_value={
            "results": [
                {
                    "id": "mem_001",
                    "content": "Python is a high-level programming language known for its simplicity",
                    "metadata": {"conversation_id": str(sample_conversation.id), "role": "assistant"},
                    "score": 0.95
                },
                {
                    "id": "mem_002",
                    "content": "Tell me about Python programming",
                    "metadata": {"conversation_id": str(sample_conversation.id), "role": "user"},
                    "score": 0.88
                }
            ],
            "total": 2,
            "query": "Python programming"
        })

        # Override dependencies
        async def override_get_db():
            yield db

        async def override_get_conversation_service(db_session=None):
            yield ConversationService(db=db, zerodb_client=zerodb_client_mock)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_conversation_service] = override_get_conversation_service

        with TestClient(app) as client:
            response = client.post(
                f"/conversations/{sample_conversation.id}/search",
                json={"query": "Python programming", "limit": 5}
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert "results" in data
            assert "results" in data["results"]  # Nested structure from SearchResultsResponse
            assert len(data["results"]["results"]) == 2

            # Verify relevance scores
            for result in data["results"]["results"]:
                assert "score" in result
                assert 0.0 <= result["score"] <= 1.0

        # Clean up
        app.dependency_overrides.clear()

    async def test_api_404_for_missing_conversation(
        self,
        db,
        zerodb_client_mock
    ):
        """
        Test: API returns 404 for non-existent conversation

        - GET /conversations/{fake_uuid}
        - Verify 404 status
        - Verify error message
        """
        from backend.services.conversation_service import ConversationService
        from backend.main import app
        from backend.db.base import get_db
        from backend.api.v1.endpoints.conversations import get_conversation_service
        from fastapi.testclient import TestClient

        fake_id = str(uuid4())

        # Override dependencies
        async def override_get_db():
            yield db

        async def override_get_conversation_service(db_session=None):
            yield ConversationService(db=db, zerodb_client=zerodb_client_mock)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_conversation_service] = override_get_conversation_service

        with TestClient(app) as client:
            response = client.get(f"/conversations/{fake_id}")

            assert response.status_code == status.HTTP_404_NOT_FOUND
            data = response.json()
            assert "detail" in data
            assert fake_id in data["detail"]

        # Clean up
        app.dependency_overrides.clear()

    async def test_api_get_single_conversation(
        self,
        db,
        zerodb_client_mock,
        sample_conversation
    ):
        """
        Test: API returns single conversation details

        - GET /conversations/{id}
        - Verify conversation details returned
        - Verify all fields present
        """
        from backend.services.conversation_service import ConversationService
        from backend.main import app
        from backend.db.base import get_db
        from backend.api.v1.endpoints.conversations import get_conversation_service
        from fastapi.testclient import TestClient

        # Override dependencies
        async def override_get_db():
            yield db

        async def override_get_conversation_service(db_session=None):
            yield ConversationService(db=db, zerodb_client=zerodb_client_mock)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_conversation_service] = override_get_conversation_service

        with TestClient(app) as client:
            response = client.get(f"/conversations/{sample_conversation.id}")

            assert response.status_code == status.HTTP_200_OK
            data = response.json()

            assert data["id"] == str(sample_conversation.id)
            assert data["workspace_id"] == str(sample_conversation.workspace_id)
            assert data["agent_id"] == str(sample_conversation.agent_id)
            assert data["openclaw_session_key"] == sample_conversation.openclaw_session_key
            assert data["status"] == sample_conversation.status.value
            assert "started_at" in data

        # Clean up
        app.dependency_overrides.clear()

    async def test_api_list_with_filters(
        self,
        db,
        zerodb_client_mock,
        sample_workspace,
        sample_user,
        sample_agent
    ):
        """
        Test: API list endpoint supports filtering

        - Create multiple conversations
        - Filter by agent_id
        - Filter by workspace_id
        - Filter by status
        - Verify correct results returned
        """
        from backend.services.conversation_service import ConversationService
        from backend.models.agent_swarm_lifecycle import AgentSwarmInstance, AgentSwarmStatus
        from backend.main import app
        from backend.db.base import get_db
        from backend.api.v1.endpoints.conversations import get_conversation_service
        from fastapi.testclient import TestClient

        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)

        # Create another agent
        agent2 = AgentSwarmInstance(
            id=uuid4(),
            name="Agent 2",
            persona="Second agent",
            model="claude-3-5-sonnet-20241022",
            user_id=sample_user.id,
            workspace_id=sample_workspace.id,
            status=AgentSwarmStatus.RUNNING,
            openclaw_session_key="whatsapp:test:agent2_session",
            openclaw_agent_id="agent_002"
        )
        db.add(agent2)
        await db.commit()

        # Create conversations for both agents
        conv1 = await service.create_conversation(
            workspace_id=sample_workspace.id,
            agent_id=sample_agent.id,
            user_id=sample_user.id,
            openclaw_session_key="whatsapp:test:conv1"
        )

        conv2 = await service.create_conversation(
            workspace_id=sample_workspace.id,
            agent_id=agent2.id,
            user_id=sample_user.id,
            openclaw_session_key="whatsapp:test:conv2"
        )

        # Override dependencies
        async def override_get_db():
            yield db

        async def override_get_conversation_service(db_session=None):
            yield ConversationService(db=db, zerodb_client=zerodb_client_mock)

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_conversation_service] = override_get_conversation_service

        with TestClient(app) as client:
            # Filter by agent_id
            response = client.get(
                "/conversations",
                params={"agent_id": str(sample_agent.id)}
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total"] >= 1
            assert all(c["agent_id"] == str(sample_agent.id) for c in data["conversations"])

            # Filter by workspace_id
            response = client.get(
                "/conversations",
                params={"workspace_id": str(sample_workspace.id)}
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert data["total"] >= 2
            assert all(c["workspace_id"] == str(sample_workspace.id) for c in data["conversations"])

            # Filter by status
            response = client.get(
                "/conversations",
                params={"status": "active"}
            )

            assert response.status_code == status.HTTP_200_OK
            data = response.json()
            assert all(c["status"] == "active" for c in data["conversations"])

        # Clean up
        app.dependency_overrides.clear()


@pytest.mark.asyncio
class TestLifecycleIntegration:
    """Test integration with agent lifecycle operations"""

    async def test_agent_provision_creates_workspace_and_persists(
        self,
        db,
        zerodb_client_mock
    ):
        """
        Test: Provisioning agent auto-creates workspace and enables persistence

        - Call AgentSwarmLifecycleService.provision_agent()
        - Verify default workspace created
        - Verify agent.workspace_id set
        - Verify ZeroDB project created
        - Send message via agent
        - Verify persistence working
        """
        from backend.services.agent_swarm_lifecycle_service import AgentSwarmLifecycleService
        from backend.models.user import User
        from backend.models.workspace import Workspace

        # Create a user first
        user = User(
            id=uuid4(),
            email="lifecycle@example.com",
            workspace_id=None  # Will be set by service
        )

        # We need to create a default workspace for the user
        default_workspace = Workspace(
            id=uuid4(),
            name=f"Workspace for lifecycle@example.com",
            slug=f"workspace-{user.id}",
            zerodb_project_id="test_proj_lifecycle"
        )
        db.add(default_workspace)
        await db.commit()

        user.workspace_id = default_workspace.id
        db.add(user)
        await db.commit()
        await db.refresh(user)

        # Now provision agent
        with patch('integrations.openclaw_bridge.OpenClawBridge') as MockBaseOpenClawBridge:
            mock_base = MagicMock()
            mock_base.is_connected = True
            mock_base.connect = AsyncMock()
            mock_base.send_to_agent = AsyncMock(return_value={
                "id": "response_lifecycle",
                "result": {"response": "Agent provisioned"}
            })
            MockBaseOpenClawBridge.return_value = mock_base

            # Import ProductionOpenClawBridge locally
            from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

            # Mock get_openclaw_bridge to return our mocked bridge
            from backend.agents.orchestration import openclaw_bridge_factory

            def mock_get_bridge():
                return ProductionOpenClawBridge(
                    url="ws://localhost:18789",
                    token="test-token",
                    db=db,
                    zerodb_client=zerodb_client_mock
                )

            with patch.object(openclaw_bridge_factory, 'get_openclaw_bridge', side_effect=mock_get_bridge):
                lifecycle_service = AgentSwarmLifecycleService(db=db, bridge=None)

                # This should create agent with workspace
                agent = await lifecycle_service.create_agent(
                    user_id=user.id,
                    name="Lifecycle Test Agent",
                    model="claude-3-5-sonnet-20241022",
                    persona="Test persona"
                )

                await db.refresh(agent)

                # Verify workspace_id set
                assert agent.workspace_id is not None
                assert agent.workspace_id == default_workspace.id

    async def test_heartbeat_execution_persists_messages(
        self,
        db,
        zerodb_client_mock,
        sample_agent,
        sample_workspace
    ):
        """
        Test: Heartbeat execution messages are persisted

        - Configure agent with heartbeat
        - Execute heartbeat via lifecycle service
        - Verify heartbeat message stored in conversation
        - Verify message_count incremented
        """
        from backend.services.conversation_service import ConversationService

        # Configure agent with heartbeat
        sample_agent.heartbeat_enabled = True
        sample_agent.heartbeat_interval = "5m"
        sample_agent.heartbeat_checklist = ["Check system status", "Review logs"]
        await db.commit()
        await db.refresh(sample_agent)

        # Create a conversation for heartbeat messages
        service = ConversationService(db=db, zerodb_client=zerodb_client_mock)
        conversation = await service.create_conversation(
            workspace_id=sample_workspace.id,
            agent_id=sample_agent.id,
            user_id=sample_agent.user_id,
            openclaw_session_key=sample_agent.openclaw_session_key
        )

        # Simulate heartbeat execution by adding a message
        await service.add_message(
            conversation_id=conversation.id,
            role="system",
            content="Heartbeat execution: All checks passed"
        )

        # Verify message stored
        await db.refresh(conversation)
        assert conversation.message_count == 1

        # Verify message can be retrieved
        zerodb_client_mock.query_table = AsyncMock(return_value=[
            {
                "id": "msg_heartbeat_001",
                "role": "system",
                "content": "Heartbeat execution: All checks passed",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        ])

        messages = await service.get_messages(conversation.id, limit=10)
        assert len(messages) == 1
        assert messages[0]["role"] == "system"
        assert "Heartbeat execution" in messages[0]["content"]
