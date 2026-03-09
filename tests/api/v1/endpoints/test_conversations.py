"""
Integration tests for Conversation API endpoints (Issue #108)

Tests API endpoints for conversation management and message retrieval.
Uses FastAPI TestClient with mocked ConversationService.

Test Coverage:
- GET /conversations (list with filters and pagination)
- GET /conversations/{conversation_id} (retrieve single conversation)
- GET /conversations/{conversation_id}/messages (retrieve messages with pagination)
- POST /conversations/{conversation_id}/search (semantic search)
"""

import pytest
from uuid import uuid4, UUID
from datetime import datetime, timezone
from unittest.mock import Mock, AsyncMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

# We'll create a minimal test app to avoid import errors from the full app
test_app = FastAPI()


@pytest.fixture
def db_session():
    """Mock database session (not actually used since we mock the service)."""
    return Mock()


@pytest.fixture
def mock_conversation_service():
    """Create a mocked ConversationService."""
    service = Mock()
    # Make async methods return AsyncMock
    service.list_conversations = AsyncMock()
    service.get_conversation = AsyncMock()
    service.get_messages = AsyncMock()
    service.search_conversation_semantic = AsyncMock()
    service.create_conversation = AsyncMock()
    service.add_message = AsyncMock()
    service.archive_conversation = AsyncMock()
    service.get_conversation_context = AsyncMock()
    service.attach_agent = AsyncMock()
    return service


@pytest.fixture(scope="function")
def client(db_session, mock_conversation_service):
    """Create FastAPI test client with mocked service."""
    from backend.api.v1.endpoints.conversations import router, get_conversation_service
    from backend.db.base import get_async_db

    # Include the conversations router in our test app
    test_app.include_router(router, prefix="/api/v1")

    async def override_get_async_db():
        yield db_session

    def override_get_conversation_service():
        return mock_conversation_service

    test_app.dependency_overrides[get_async_db] = override_get_async_db
    test_app.dependency_overrides[get_conversation_service] = override_get_conversation_service

    yield TestClient(test_app)

    # Cleanup
    test_app.dependency_overrides.clear()
    test_app.routes.clear()


@pytest.fixture
def sample_conversation_data():
    """Sample conversation data for tests."""
    workspace_id = uuid4()
    agent_id = uuid4()
    user_id = uuid4()
    conversation_id = uuid4()

    # Create a mock Conversation object that behaves like the ORM model
    conv = Mock()
    conv.id = conversation_id
    conv.workspace_id = workspace_id
    conv.agent_id = agent_id
    conv.user_id = user_id
    conv.openclaw_session_key = f"session_{conversation_id}"
    conv.started_at = datetime.now(timezone.utc)
    conv.last_message_at = datetime.now(timezone.utc)
    conv.message_count = 5
    conv.status = "active"

    return conv


class TestListConversations:
    """Test GET /conversations endpoint."""

    def test_list_conversations_no_filters(self, client, mock_conversation_service, sample_conversation_data):
        """Test listing all conversations without filters."""
        # Service returns (List[Conversation], total_count)
        mock_conversation_service.list_conversations.return_value = ([sample_conversation_data], 1)

        response = client.get("/api/v1/conversations")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["status"] == "active"
        assert data["conversations"][0]["message_count"] == 5

        # Verify service was called with correct parameters
        mock_conversation_service.list_conversations.assert_called_once()
        call_kwargs = mock_conversation_service.list_conversations.call_args.kwargs
        assert call_kwargs["agent_id"] is None
        assert call_kwargs["workspace_id"] is None
        assert call_kwargs["status"] is None
        assert call_kwargs["limit"] == 50
        assert call_kwargs["offset"] == 0

    def test_list_conversations_with_agent_id_filter(self, client, mock_conversation_service, sample_conversation_data):
        """Test listing conversations filtered by agent_id."""
        agent_id = sample_conversation_data.agent_id
        mock_conversation_service.list_conversations.return_value = ([sample_conversation_data], 1)

        response = client.get(f"/api/v1/conversations?agent_id={agent_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["conversations"]) == 1

        # Verify service was called with agent_id filter
        call_kwargs = mock_conversation_service.list_conversations.call_args.kwargs
        assert str(call_kwargs["agent_id"]) == str(agent_id)

    def test_list_conversations_with_workspace_id_filter(self, client, mock_conversation_service, sample_conversation_data):
        """Test listing conversations filtered by workspace_id."""
        workspace_id = sample_conversation_data.workspace_id
        mock_conversation_service.list_conversations.return_value = ([sample_conversation_data], 1)

        response = client.get(f"/api/v1/conversations?workspace_id={workspace_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1

        # Verify service was called with workspace_id filter
        call_kwargs = mock_conversation_service.list_conversations.call_args.kwargs
        assert str(call_kwargs["workspace_id"]) == str(workspace_id)

    def test_list_conversations_with_status_filter(self, client, mock_conversation_service, sample_conversation_data):
        """Test listing conversations filtered by status."""
        mock_conversation_service.list_conversations.return_value = ([sample_conversation_data], 1)

        response = client.get("/api/v1/conversations?status=active")

        assert response.status_code == 200
        data = response.json()
        assert len(data["conversations"]) == 1
        assert data["conversations"][0]["status"] == "active"

        # Verify service was called with status filter
        call_kwargs = mock_conversation_service.list_conversations.call_args.kwargs
        assert call_kwargs["status"] == "active"

    def test_list_conversations_with_pagination(self, client, mock_conversation_service, sample_conversation_data):
        """Test listing conversations with custom pagination."""
        mock_conversation_service.list_conversations.return_value = ([sample_conversation_data], 100)

        response = client.get("/api/v1/conversations?limit=10&offset=20")

        assert response.status_code == 200
        data = response.json()
        assert data["limit"] == 10
        assert data["offset"] == 20
        assert data["total"] == 100

        # Verify service was called with pagination
        call_kwargs = mock_conversation_service.list_conversations.call_args.kwargs
        assert call_kwargs["limit"] == 10
        assert call_kwargs["offset"] == 20

    def test_list_conversations_limit_validation(self, client, mock_conversation_service):
        """Test limit parameter validation (must be 1-200)."""
        # Test limit too low
        response = client.get("/api/v1/conversations?limit=0")
        assert response.status_code == 422

        # Test limit too high
        response = client.get("/api/v1/conversations?limit=201")
        assert response.status_code == 422

        # Test valid limits
        for limit in [1, 50, 200]:
            mock_conversation_service.list_conversations.return_value = ([], 0)
            response = client.get(f"/api/v1/conversations?limit={limit}")
            assert response.status_code == 200

    def test_list_conversations_offset_validation(self, client, mock_conversation_service):
        """Test offset parameter validation (must be >= 0)."""
        # Test negative offset
        response = client.get("/api/v1/conversations?offset=-1")
        assert response.status_code == 422

        # Test valid offset
        mock_conversation_service.list_conversations.return_value = ([], 0)
        response = client.get("/api/v1/conversations?offset=0")
        assert response.status_code == 200

    def test_list_conversations_all_filters_combined(self, client, mock_conversation_service, sample_conversation_data):
        """Test listing conversations with all filters combined."""
        agent_id = sample_conversation_data.agent_id
        workspace_id = sample_conversation_data.workspace_id

        mock_conversation_service.list_conversations.return_value = ([sample_conversation_data], 1)

        response = client.get(
            f"/api/v1/conversations?agent_id={agent_id}&workspace_id={workspace_id}&status=active&limit=25&offset=10"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["limit"] == 25
        assert data["offset"] == 10

        # Verify all filters passed to service
        call_kwargs = mock_conversation_service.list_conversations.call_args.kwargs
        assert str(call_kwargs["agent_id"]) == str(agent_id)
        assert str(call_kwargs["workspace_id"]) == str(workspace_id)
        assert call_kwargs["status"] == "active"
        assert call_kwargs["limit"] == 25
        assert call_kwargs["offset"] == 10

    def test_list_conversations_empty_result(self, client, mock_conversation_service):
        """Test listing conversations with no results."""
        mock_conversation_service.list_conversations.return_value = ([], 0)

        response = client.get("/api/v1/conversations")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["conversations"]) == 0


class TestGetConversation:
    """Test GET /conversations/{conversation_id} endpoint."""

    def test_get_conversation_success(self, client, mock_conversation_service, sample_conversation_data):
        """Test successfully retrieving a single conversation."""
        conversation_id = sample_conversation_data.id
        mock_conversation_service.get_conversation.return_value = sample_conversation_data

        response = client.get(f"/api/v1/conversations/{conversation_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(conversation_id)
        assert data["status"] == "active"
        assert data["message_count"] == 5
        assert "workspace_id" in data
        assert "agent_id" in data
        assert "started_at" in data

        # Verify service was called with correct ID
        mock_conversation_service.get_conversation.assert_called_once()
        call_args = mock_conversation_service.get_conversation.call_args
        assert str(call_args[0][0]) == str(conversation_id)

    def test_get_conversation_not_found(self, client, mock_conversation_service):
        """Test retrieving a non-existent conversation."""
        conversation_id = uuid4()
        mock_conversation_service.get_conversation.return_value = None

        response = client.get(f"/api/v1/conversations/{conversation_id}")

        assert response.status_code == 404
        data = response.json()
        assert "detail" in data
        assert "not found" in data["detail"].lower()

    def test_get_conversation_invalid_uuid(self, client, mock_conversation_service):
        """Test retrieving conversation with invalid UUID format."""
        response = client.get("/api/v1/conversations/invalid-uuid")

        assert response.status_code == 422


class TestGetConversationMessages:
    """Test GET /conversations/{conversation_id}/messages endpoint."""

    def test_get_messages_success(self, client, mock_conversation_service):
        """Test successfully retrieving conversation messages."""
        conversation_id = uuid4()
        mock_messages = [
                {
                    "role": "user",
                    "content": "Hello, AI!",
                    "timestamp": "2024-01-15T10:00:00Z",
                    "metadata": {}
                },
                {
                    "role": "assistant",
                    "content": "Hello! How can I help you today?",
                    "timestamp": "2024-01-15T10:00:05Z",
                    "metadata": {}
                }
            ]
        mock_conversation_service.get_messages.return_value = mock_messages

        # Mock get_conversation to provide total message count
        mock_conv = Mock()
        mock_conv.message_count = 2
        mock_conversation_service.get_conversation.return_value = mock_conv

        response = client.get(f"/api/v1/conversations/{conversation_id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

        # Verify service was called with correct parameters
        mock_conversation_service.get_messages.assert_called_once()
        call_kwargs = mock_conversation_service.get_messages.call_args.kwargs
        assert str(call_kwargs["conversation_id"]) == str(conversation_id)
        assert call_kwargs["limit"] == 50
        assert call_kwargs["offset"] == 0

    def test_get_messages_with_pagination(self, client, mock_conversation_service):
        """Test retrieving messages with custom pagination."""
        conversation_id = uuid4()
        mock_conversation_service.get_messages.return_value = []

        # Mock get_conversation to provide total message count
        mock_conv = Mock()
        mock_conv.message_count = 100
        mock_conversation_service.get_conversation.return_value = mock_conv

        response = client.get(f"/api/v1/conversations/{conversation_id}/messages?limit=20&offset=40")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 100

        # Verify pagination parameters
        call_kwargs = mock_conversation_service.get_messages.call_args.kwargs
        assert call_kwargs["limit"] == 20
        assert call_kwargs["offset"] == 40

    def test_get_messages_limit_validation(self, client, mock_conversation_service):
        """Test message limit parameter validation (1-200)."""
        conversation_id = uuid4()

        # Test limit too low
        response = client.get(f"/api/v1/conversations/{conversation_id}/messages?limit=0")
        assert response.status_code == 422

        # Test limit too high
        response = client.get(f"/api/v1/conversations/{conversation_id}/messages?limit=201")
        assert response.status_code == 422

        # Test valid limit
        mock_conversation_service.get_messages.return_value = []
        response = client.get(f"/api/v1/conversations/{conversation_id}/messages?limit=100")
        assert response.status_code == 200

    def test_get_messages_offset_validation(self, client, mock_conversation_service):
        """Test message offset parameter validation (>= 0)."""
        conversation_id = uuid4()

        # Test negative offset
        response = client.get(f"/api/v1/conversations/{conversation_id}/messages?offset=-1")
        assert response.status_code == 422

        # Test valid offset
        mock_conversation_service.get_messages.return_value = []
        response = client.get(f"/api/v1/conversations/{conversation_id}/messages?offset=0")
        assert response.status_code == 200

    def test_get_messages_invalid_conversation_uuid(self, client, mock_conversation_service):
        """Test retrieving messages with invalid conversation UUID."""
        response = client.get("/api/v1/conversations/invalid-uuid/messages")
        assert response.status_code == 422

    def test_get_messages_empty_result(self, client, mock_conversation_service):
        """Test retrieving messages from conversation with no messages."""
        conversation_id = uuid4()
        mock_conversation_service.get_messages.return_value = []

        # Mock get_conversation to provide total message count
        mock_conv = Mock()
        mock_conv.message_count = 0
        mock_conversation_service.get_conversation.return_value = mock_conv

        response = client.get(f"/api/v1/conversations/{conversation_id}/messages")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["messages"]) == 0


class TestSearchConversation:
    """Test POST /conversations/{conversation_id}/search endpoint."""

    def test_search_conversation_success(self, client, mock_conversation_service):
        """Test successfully searching a conversation."""
        conversation_id = uuid4()
        # Service returns {"results": [...], "total": N, "query": "..."}
        mock_search_results = {
            "results": [
                {
                    "content": "Relevant message content",
                    "score": 0.95,
                    "timestamp": "2024-01-15T10:00:00Z"
                }
            ],
            "total": 1,
            "query": "test query"
        }
        mock_conversation_service.search_conversation_semantic.return_value = mock_search_results

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/search",
            json={"query": "test query", "limit": 5}
        )

        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        # The endpoint wraps the service response in a "results" field
        assert data["results"]["total"] == 1
        assert data["results"]["query"] == "test query"

        # Verify service was called correctly
        mock_conversation_service.search_conversation_semantic.assert_called_once()
        call_kwargs = mock_conversation_service.search_conversation_semantic.call_args.kwargs
        assert str(call_kwargs["conversation_id"]) == str(conversation_id)
        assert call_kwargs["query"] == "test query"
        assert call_kwargs["limit"] == 5

    def test_search_conversation_default_limit(self, client, mock_conversation_service):
        """Test search with default limit value."""
        conversation_id = uuid4()
        mock_conversation_service.search_conversation_semantic.return_value = {"results": {}}

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/search",
            json={"query": "test"}
        )

        assert response.status_code == 200

        # Verify default limit is 5
        call_kwargs = mock_conversation_service.search_conversation_semantic.call_args.kwargs
        assert call_kwargs["limit"] == 5

    def test_search_conversation_custom_limit(self, client, mock_conversation_service):
        """Test search with custom limit value."""
        conversation_id = uuid4()
        mock_conversation_service.search_conversation_semantic.return_value = {"results": {}}

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/search",
            json={"query": "test", "limit": 20}
        )

        assert response.status_code == 200

        # Verify custom limit
        call_kwargs = mock_conversation_service.search_conversation_semantic.call_args.kwargs
        assert call_kwargs["limit"] == 20

    def test_search_conversation_limit_validation(self, client, mock_conversation_service):
        """Test search limit validation (1-50)."""
        conversation_id = uuid4()

        # Test limit too low
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/search",
            json={"query": "test", "limit": 0}
        )
        assert response.status_code == 422

        # Test limit too high
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/search",
            json={"query": "test", "limit": 51}
        )
        assert response.status_code == 422

        # Test valid limits
        for limit in [1, 25, 50]:
            mock_conversation_service.search_conversation_semantic.return_value = {"results": {}}
            response = client.post(
                f"/api/v1/conversations/{conversation_id}/search",
                json={"query": "test", "limit": limit}
            )
            assert response.status_code == 200

    def test_search_conversation_empty_query(self, client, mock_conversation_service):
        """Test search with empty query string."""
        conversation_id = uuid4()

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/search",
            json={"query": ""}
        )

        assert response.status_code == 422

    def test_search_conversation_missing_query(self, client, mock_conversation_service):
        """Test search without query field."""
        conversation_id = uuid4()

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/search",
            json={"limit": 5}
        )

        assert response.status_code == 422

    def test_search_conversation_invalid_uuid(self, client, mock_conversation_service):
        """Test search with invalid conversation UUID."""
        response = client.post(
            "/api/v1/conversations/invalid-uuid/search",
            json={"query": "test"}
        )

        assert response.status_code == 422

    def test_search_conversation_no_results(self, client, mock_conversation_service):
        """Test search with no matching results."""
        conversation_id = uuid4()
        mock_conversation_service.search_conversation_semantic.return_value = {
            "results": [],
            "total": 0,
            "query": "no matches"
        }

        response = client.post(
            f"/api/v1/conversations/{conversation_id}/search",
            json={"query": "no matches"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["results"]["total"] == 0
        assert len(data["results"]["results"]) == 0


class TestCreateConversation:
    """Test POST /conversations endpoint."""

    def test_create_conversation_success(self, client, mock_conversation_service, sample_conversation_data):
        """Test successfully creating a new conversation."""
        mock_conversation_service.create_conversation.return_value = sample_conversation_data

        request_data = {
            "agent_id": str(sample_conversation_data.agent_id),
            "workspace_id": str(sample_conversation_data.workspace_id),
            "user_id": str(sample_conversation_data.user_id)
        }

        response = client.post("/api/v1/conversations", json=request_data)

        assert response.status_code == 201
        data = response.json()
        assert data["id"] == str(sample_conversation_data.id)
        assert data["status"] == "active"
        assert data["message_count"] == 5

        # Verify service was called with correct parameters
        mock_conversation_service.create_conversation.assert_called_once()
        call_kwargs = mock_conversation_service.create_conversation.call_args.kwargs
        assert str(call_kwargs["agent_id"]) == str(sample_conversation_data.agent_id)
        assert str(call_kwargs["workspace_id"]) == str(sample_conversation_data.workspace_id)
        assert str(call_kwargs["user_id"]) == str(sample_conversation_data.user_id)

    def test_create_conversation_without_user_id(self, client, mock_conversation_service, sample_conversation_data):
        """Test creating conversation without optional user_id."""
        sample_conversation_data.user_id = None
        mock_conversation_service.create_conversation.return_value = sample_conversation_data

        request_data = {
            "agent_id": str(sample_conversation_data.agent_id),
            "workspace_id": str(sample_conversation_data.workspace_id)
        }

        response = client.post("/api/v1/conversations", json=request_data)

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] is None

    def test_create_conversation_missing_required_fields(self, client, mock_conversation_service):
        """Test creating conversation with missing required fields."""
        # Missing agent_id
        response = client.post("/api/v1/conversations", json={"workspace_id": str(uuid4())})
        assert response.status_code == 422

        # Missing workspace_id
        response = client.post("/api/v1/conversations", json={"agent_id": str(uuid4())})
        assert response.status_code == 422

        # Empty body
        response = client.post("/api/v1/conversations", json={})
        assert response.status_code == 422

    def test_create_conversation_invalid_uuid_format(self, client, mock_conversation_service):
        """Test creating conversation with invalid UUID format."""
        request_data = {
            "agent_id": "invalid-uuid",
            "workspace_id": str(uuid4())
        }

        response = client.post("/api/v1/conversations", json=request_data)
        assert response.status_code == 422


class TestAddMessage:
    """Test POST /conversations/{conversation_id}/messages endpoint."""

    def test_add_message_success(self, client, mock_conversation_service, sample_conversation_data):
        """Test successfully adding a message to a conversation."""
        conversation_id = sample_conversation_data.id
        mock_conversation_service.get_conversation.return_value = sample_conversation_data
        mock_conversation_service.add_message.return_value = None

        request_data = {
            "role": "user",
            "content": "Hello, AI!",
            "metadata": {"source": "test"}
        }

        response = client.post(f"/api/v1/conversations/{conversation_id}/messages", json=request_data)

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "user"
        assert data["content"] == "Hello, AI!"
        assert "timestamp" in data
        assert data["metadata"]["source"] == "test"

        # Verify service calls
        mock_conversation_service.get_conversation.assert_called_once()
        mock_conversation_service.add_message.assert_called_once()
        call_kwargs = mock_conversation_service.add_message.call_args.kwargs
        assert str(call_kwargs["conversation_id"]) == str(conversation_id)
        assert call_kwargs["role"] == "user"
        assert call_kwargs["content"] == "Hello, AI!"

    def test_add_message_without_metadata(self, client, mock_conversation_service, sample_conversation_data):
        """Test adding message without optional metadata."""
        conversation_id = sample_conversation_data.id
        mock_conversation_service.get_conversation.return_value = sample_conversation_data
        mock_conversation_service.add_message.return_value = None

        request_data = {
            "role": "assistant",
            "content": "Hello! How can I help?"
        }

        response = client.post(f"/api/v1/conversations/{conversation_id}/messages", json=request_data)

        assert response.status_code == 201
        data = response.json()
        assert data["role"] == "assistant"
        assert data["metadata"] == {}

    def test_add_message_conversation_not_found(self, client, mock_conversation_service):
        """Test adding message to non-existent conversation."""
        conversation_id = uuid4()
        mock_conversation_service.get_conversation.return_value = None

        request_data = {
            "role": "user",
            "content": "Hello"
        }

        response = client.post(f"/api/v1/conversations/{conversation_id}/messages", json=request_data)

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_add_message_missing_required_fields(self, client, mock_conversation_service, sample_conversation_data):
        """Test adding message with missing required fields."""
        conversation_id = sample_conversation_data.id
        mock_conversation_service.get_conversation.return_value = sample_conversation_data

        # Missing content
        response = client.post(f"/api/v1/conversations/{conversation_id}/messages", json={"role": "user"})
        assert response.status_code == 422

        # Missing role
        response = client.post(f"/api/v1/conversations/{conversation_id}/messages", json={"content": "Hello"})
        assert response.status_code == 422

        # Empty body
        response = client.post(f"/api/v1/conversations/{conversation_id}/messages", json={})
        assert response.status_code == 422

    def test_add_message_empty_content(self, client, mock_conversation_service, sample_conversation_data):
        """Test adding message with empty content."""
        conversation_id = sample_conversation_data.id
        mock_conversation_service.get_conversation.return_value = sample_conversation_data

        request_data = {
            "role": "user",
            "content": ""
        }

        response = client.post(f"/api/v1/conversations/{conversation_id}/messages", json=request_data)
        assert response.status_code == 422

    def test_add_message_invalid_conversation_uuid(self, client, mock_conversation_service):
        """Test adding message with invalid conversation UUID."""
        request_data = {
            "role": "user",
            "content": "Hello"
        }

        response = client.post("/api/v1/conversations/invalid-uuid/messages", json=request_data)
        assert response.status_code == 422


class TestArchiveConversation:
    """Test POST /conversations/{conversation_id}/archive endpoint."""

    def test_archive_conversation_success(self, client, mock_conversation_service, sample_conversation_data):
        """Test successfully archiving a conversation."""
        conversation_id = sample_conversation_data.id
        sample_conversation_data.status = "archived"
        mock_conversation_service.archive_conversation.return_value = sample_conversation_data

        response = client.post(f"/api/v1/conversations/{conversation_id}/archive")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(conversation_id)
        assert data["status"] == "archived"

        # Verify service was called
        mock_conversation_service.archive_conversation.assert_called_once_with(conversation_id)

    def test_archive_conversation_not_found(self, client, mock_conversation_service):
        """Test archiving a non-existent conversation."""
        conversation_id = uuid4()
        mock_conversation_service.archive_conversation.return_value = None

        response = client.post(f"/api/v1/conversations/{conversation_id}/archive")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_archive_conversation_invalid_uuid(self, client, mock_conversation_service):
        """Test archiving conversation with invalid UUID."""
        response = client.post("/api/v1/conversations/invalid-uuid/archive")
        assert response.status_code == 422

    def test_archive_conversation_already_archived(self, client, mock_conversation_service, sample_conversation_data):
        """Test archiving an already archived conversation (idempotent)."""
        conversation_id = sample_conversation_data.id
        sample_conversation_data.status = "archived"
        mock_conversation_service.archive_conversation.return_value = sample_conversation_data

        response = client.post(f"/api/v1/conversations/{conversation_id}/archive")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "archived"


class TestGetConversationContext:
    """Test GET /conversations/{conversation_id}/context endpoint."""

    def test_get_context_success(self, client, mock_conversation_service):
        """Test successfully retrieving conversation context for LLM."""
        conversation_id = uuid4()
        mock_context = {
            "conversation_id": str(conversation_id),
            "messages": [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"}
            ],
            "total_messages": 2,
            "agent_id": str(uuid4()),
            "metadata": {"model": "claude-3"}
        }
        mock_conversation_service.get_conversation_context.return_value = mock_context

        response = client.get(f"/api/v1/conversations/{conversation_id}/context")

        assert response.status_code == 200
        data = response.json()
        assert data["conversation_id"] == str(conversation_id)
        assert len(data["messages"]) == 2
        assert data["total_messages"] == 2
        assert "metadata" in data

        # Verify service was called
        mock_conversation_service.get_conversation_context.assert_called_once()

    def test_get_context_with_limit(self, client, mock_conversation_service):
        """Test getting context with custom message limit."""
        conversation_id = uuid4()
        mock_context = {
            "conversation_id": str(conversation_id),
            "messages": [],
            "total_messages": 0
        }
        mock_conversation_service.get_conversation_context.return_value = mock_context

        response = client.get(f"/api/v1/conversations/{conversation_id}/context?limit=10")

        assert response.status_code == 200

        # Verify limit was passed to service
        call_kwargs = mock_conversation_service.get_conversation_context.call_args.kwargs
        assert call_kwargs.get("limit") == 10

    def test_get_context_conversation_not_found(self, client, mock_conversation_service):
        """Test getting context for non-existent conversation."""
        conversation_id = uuid4()
        mock_conversation_service.get_conversation_context.return_value = None

        response = client.get(f"/api/v1/conversations/{conversation_id}/context")

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_get_context_invalid_uuid(self, client, mock_conversation_service):
        """Test getting context with invalid UUID."""
        response = client.get("/api/v1/conversations/invalid-uuid/context")
        assert response.status_code == 422

    def test_get_context_limit_validation(self, client, mock_conversation_service):
        """Test context limit parameter validation."""
        conversation_id = uuid4()

        # Test limit too low
        response = client.get(f"/api/v1/conversations/{conversation_id}/context?limit=0")
        assert response.status_code == 422

        # Test limit too high
        response = client.get(f"/api/v1/conversations/{conversation_id}/context?limit=1001")
        assert response.status_code == 422

        # Test valid limit
        mock_conversation_service.get_conversation_context.return_value = {
            "conversation_id": str(conversation_id),
            "messages": [],
            "total_messages": 0
        }
        response = client.get(f"/api/v1/conversations/{conversation_id}/context?limit=100")
        assert response.status_code == 200


class TestAttachAgent:
    """Test POST /conversations/{conversation_id}/attach-agent endpoint."""

    def test_attach_agent_success(self, client, mock_conversation_service, sample_conversation_data):
        """Test successfully attaching an agent to a conversation."""
        conversation_id = sample_conversation_data.id
        new_agent_id = uuid4()
        sample_conversation_data.agent_id = new_agent_id
        mock_conversation_service.attach_agent.return_value = sample_conversation_data

        request_data = {"agent_id": str(new_agent_id)}

        response = client.post(f"/api/v1/conversations/{conversation_id}/attach-agent", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(conversation_id)
        assert data["agent_id"] == str(new_agent_id)

        # Verify service was called
        mock_conversation_service.attach_agent.assert_called_once()
        call_kwargs = mock_conversation_service.attach_agent.call_args.kwargs
        assert str(call_kwargs["conversation_id"]) == str(conversation_id)
        assert str(call_kwargs["agent_id"]) == str(new_agent_id)

    def test_attach_agent_conversation_not_found(self, client, mock_conversation_service):
        """Test attaching agent to non-existent conversation."""
        conversation_id = uuid4()
        mock_conversation_service.attach_agent.return_value = None

        request_data = {"agent_id": str(uuid4())}

        response = client.post(f"/api/v1/conversations/{conversation_id}/attach-agent", json=request_data)

        assert response.status_code == 404
        data = response.json()
        assert "not found" in data["detail"].lower()

    def test_attach_agent_missing_agent_id(self, client, mock_conversation_service):
        """Test attaching agent without agent_id."""
        conversation_id = uuid4()

        response = client.post(f"/api/v1/conversations/{conversation_id}/attach-agent", json={})

        assert response.status_code == 422

    def test_attach_agent_invalid_agent_uuid(self, client, mock_conversation_service):
        """Test attaching agent with invalid agent UUID."""
        conversation_id = uuid4()

        request_data = {"agent_id": "invalid-uuid"}

        response = client.post(f"/api/v1/conversations/{conversation_id}/attach-agent", json=request_data)

        assert response.status_code == 422

    def test_attach_agent_invalid_conversation_uuid(self, client, mock_conversation_service):
        """Test attaching agent with invalid conversation UUID."""
        request_data = {"agent_id": str(uuid4())}

        response = client.post("/api/v1/conversations/invalid-uuid/attach-agent", json=request_data)

        assert response.status_code == 422

    def test_attach_agent_replace_existing(self, client, mock_conversation_service, sample_conversation_data):
        """Test replacing an existing agent attachment."""
        conversation_id = sample_conversation_data.id
        old_agent_id = sample_conversation_data.agent_id
        new_agent_id = uuid4()

        # Update the mock to reflect new agent
        sample_conversation_data.agent_id = new_agent_id
        mock_conversation_service.attach_agent.return_value = sample_conversation_data

        request_data = {"agent_id": str(new_agent_id)}

        response = client.post(f"/api/v1/conversations/{conversation_id}/attach-agent", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["agent_id"] == str(new_agent_id)
        assert data["agent_id"] != str(old_agent_id)
