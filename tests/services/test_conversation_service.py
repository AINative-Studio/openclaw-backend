"""
Tests for ConversationService

Comprehensive test coverage for conversation management with ZeroDB integration.
Tests use mocked ZeroDBClient to avoid external dependencies.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import (
    ZeroDBClient,
    ZeroDBConnectionError,
    ZeroDBAPIError
)
from backend.models.conversation import Conversation
from backend.models.workspace import Workspace
from backend.models.user import User
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance


@pytest.fixture
def mock_zerodb_client():
    """Create a mocked ZeroDBClient"""
    client = AsyncMock(spec=ZeroDBClient)
    client.create_table_row = AsyncMock()
    client.query_table = AsyncMock()
    client.create_memory = AsyncMock()
    client.search_memories = AsyncMock()
    return client


@pytest.fixture
def mock_db_session():
    """Create a mocked async database session"""
    session = AsyncMock(spec=AsyncSession)
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    session.rollback = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def conversation_service(mock_db_session, mock_zerodb_client):
    """Create ConversationService instance with mocked dependencies"""
    return ConversationService(db=mock_db_session, zerodb_client=mock_zerodb_client)


@pytest.fixture
def sample_workspace():
    """Create sample workspace with ZeroDB project ID"""
    workspace = Workspace(
        id=uuid4(),
        name="Test Workspace",
        slug="test-workspace",
        zerodb_project_id="proj_test123"
    )
    return workspace


@pytest.fixture
def sample_user(sample_workspace):
    """Create sample user"""
    user = User(
        id=uuid4(),
        email="test@example.com",
        workspace_id=sample_workspace.id
    )
    user.workspace = sample_workspace
    return user


@pytest.fixture
def sample_agent(sample_user):
    """Create sample agent"""
    agent = AgentSwarmInstance(
        id=uuid4(),
        name="Test Agent",
        model="claude-3-5-sonnet",
        user_id=sample_user.id,
        openclaw_session_key="session_abc123"
    )
    return agent


@pytest.fixture
def sample_conversation(sample_workspace, sample_agent, sample_user):
    """Create sample conversation"""
    conversation = Conversation(
        id=uuid4(),
        workspace_id=sample_workspace.id,
        agent_id=sample_agent.id,
        user_id=sample_user.id,
        openclaw_session_key="session_conv_xyz",
        status="active",
        message_count=0
    )
    conversation.workspace = sample_workspace
    conversation.agent = sample_agent
    conversation.user = sample_user
    return conversation


class TestCreateConversation:
    """Test suite for create_conversation method"""

    @pytest.mark.asyncio
    async def test_create_conversation_success(
        self,
        conversation_service,
        mock_db_session,
        sample_workspace,
        sample_agent,
        sample_user
    ):
        """Test successful conversation creation"""
        # Setup mock to return workspace with agent and user
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_workspace
        mock_db_session.execute.return_value = mock_result

        # Execute
        result = await conversation_service.create_conversation(
            workspace_id=sample_workspace.id,
            agent_id=sample_agent.id,
            user_id=sample_user.id,
            openclaw_session_key="session_new_123"
        )

        # Verify
        assert isinstance(result, Conversation)
        assert result.workspace_id == sample_workspace.id
        assert result.agent_id == sample_agent.id
        assert result.user_id == sample_user.id
        assert result.openclaw_session_key == "session_new_123"
        assert result.status == "active"
        assert result.message_count == 0

        # Verify database operations
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_called_once()
        mock_db_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_conversation_workspace_not_found(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test conversation creation fails when workspace not found"""
        # Setup mock to return None (workspace not found)
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Execute and verify exception
        with pytest.raises(ValueError, match="Workspace .* not found"):
            await conversation_service.create_conversation(
                workspace_id=uuid4(),
                agent_id=uuid4(),
                user_id=uuid4(),
                openclaw_session_key="session_fail"
            )

        # Verify rollback was called
        mock_db_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_conversation_missing_zerodb_project_id(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test conversation creation fails when workspace has no ZeroDB project ID"""
        # Create workspace without zerodb_project_id
        workspace = Workspace(
            id=uuid4(),
            name="No ZeroDB Workspace",
            slug="no-zerodb",
            zerodb_project_id=None
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = workspace
        mock_db_session.execute.return_value = mock_result

        # Execute and verify exception
        with pytest.raises(ValueError, match="Workspace .* does not have a ZeroDB project"):
            await conversation_service.create_conversation(
                workspace_id=workspace.id,
                agent_id=uuid4(),
                user_id=uuid4(),
                openclaw_session_key="session_fail"
            )

        # Verify rollback was called
        mock_db_session.rollback.assert_called_once()


class TestGetConversationBySessionKey:
    """Test suite for get_conversation_by_session_key method"""

    @pytest.mark.asyncio
    async def test_get_conversation_found(
        self,
        conversation_service,
        mock_db_session,
        sample_conversation
    ):
        """Test successful conversation retrieval by session key"""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Execute
        result = await conversation_service.get_conversation_by_session_key(
            "session_conv_xyz"
        )

        # Verify
        assert result == sample_conversation
        assert result.openclaw_session_key == "session_conv_xyz"

    @pytest.mark.asyncio
    async def test_get_conversation_not_found(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test conversation retrieval returns None when not found"""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Execute
        result = await conversation_service.get_conversation_by_session_key(
            "nonexistent_session"
        )

        # Verify
        assert result is None


class TestAddMessage:
    """Test suite for add_message method - dual storage implementation"""

    @pytest.mark.asyncio
    async def test_add_message_success_dual_storage(
        self,
        conversation_service,
        mock_db_session,
        mock_zerodb_client,
        sample_conversation
    ):
        """Test message is stored in both ZeroDB table and memory"""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Mock ZeroDB responses
        mock_zerodb_client.create_table_row.return_value = {
            "id": "row_123",
            "data": {
                "conversation_id": str(sample_conversation.id),
                "role": "user",
                "content": "Hello agent"
            }
        }
        mock_zerodb_client.create_memory.return_value = {
            "id": "mem_123",
            "title": f"Message in conversation {sample_conversation.id}",
            "content": "Hello agent"
        }

        # Execute
        result = await conversation_service.add_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Hello agent",
            metadata={"source": "whatsapp"}
        )

        # Verify dual storage calls
        mock_zerodb_client.create_table_row.assert_called_once()
        mock_zerodb_client.create_memory.assert_called_once()

        # Verify table row call details
        table_call = mock_zerodb_client.create_table_row.call_args
        assert table_call.kwargs["project_id"] == sample_conversation.workspace.zerodb_project_id
        assert table_call.kwargs["table_name"] == "messages"
        assert table_call.kwargs["row_data"]["role"] == "user"
        assert table_call.kwargs["row_data"]["content"] == "Hello agent"
        assert "timestamp" in table_call.kwargs["row_data"]

        # Verify memory call details
        memory_call = mock_zerodb_client.create_memory.call_args
        assert memory_call.kwargs["content"] == "Hello agent"
        assert memory_call.kwargs["type"] == "conversation"
        assert str(sample_conversation.id) in memory_call.kwargs["tags"]

        # Verify conversation metadata updated
        assert sample_conversation.message_count == 1
        assert sample_conversation.last_message_at is not None
        mock_db_session.commit.assert_called()

        # Verify result structure
        assert result["id"] == "row_123"
        assert result["memory_id"] == "mem_123"

    @pytest.mark.asyncio
    async def test_add_message_conversation_not_found(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test add_message fails when conversation not found"""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Execute and verify exception
        with pytest.raises(ValueError, match="Conversation .* not found"):
            await conversation_service.add_message(
                conversation_id=uuid4(),
                role="user",
                content="Test message"
            )

    @pytest.mark.asyncio
    async def test_add_message_zerodb_table_failure(
        self,
        conversation_service,
        mock_db_session,
        mock_zerodb_client,
        sample_conversation
    ):
        """Test add_message handles ZeroDB table storage failure"""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Mock ZeroDB table failure
        mock_zerodb_client.create_table_row.side_effect = ZeroDBAPIError(
            "Table creation failed", status_code=500
        )

        # Execute and verify exception
        with pytest.raises(ZeroDBAPIError):
            await conversation_service.add_message(
                conversation_id=sample_conversation.id,
                role="user",
                content="Test message"
            )

        # Verify memory was not called (fail fast)
        mock_zerodb_client.create_memory.assert_not_called()

    @pytest.mark.asyncio
    async def test_add_message_zerodb_memory_failure_continues(
        self,
        conversation_service,
        mock_db_session,
        mock_zerodb_client,
        sample_conversation
    ):
        """Test add_message continues if memory storage fails (graceful degradation)"""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Mock successful table creation but failed memory
        mock_zerodb_client.create_table_row.return_value = {
            "id": "row_123",
            "data": {"content": "Test"}
        }
        mock_zerodb_client.create_memory.side_effect = ZeroDBAPIError(
            "Memory creation failed", status_code=500
        )

        # Execute - should succeed despite memory failure
        result = await conversation_service.add_message(
            conversation_id=sample_conversation.id,
            role="user",
            content="Test message"
        )

        # Verify result only has table row id
        assert result["id"] == "row_123"
        assert result["memory_id"] is None

        # Verify conversation was still updated
        assert sample_conversation.message_count == 1
        mock_db_session.commit.assert_called()


class TestGetMessages:
    """Test suite for get_messages method"""

    @pytest.mark.asyncio
    async def test_get_messages_success(
        self,
        conversation_service,
        mock_db_session,
        mock_zerodb_client,
        sample_conversation
    ):
        """Test successful message retrieval with pagination"""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Mock ZeroDB response
        mock_zerodb_client.query_table.return_value = [
            {
                "id": "row_1",
                "role": "user",
                "content": "Hello",
                "timestamp": "2024-01-01T10:00:00Z"
            },
            {
                "id": "row_2",
                "role": "assistant",
                "content": "Hi there",
                "timestamp": "2024-01-01T10:00:05Z"
            }
        ]

        # Execute
        result = await conversation_service.get_messages(
            conversation_id=sample_conversation.id,
            limit=50,
            offset=0
        )

        # Verify
        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[1]["role"] == "assistant"

        # Verify ZeroDB query call
        mock_zerodb_client.query_table.assert_called_once_with(
            project_id=sample_conversation.workspace.zerodb_project_id,
            table_name="messages",
            limit=50,
            skip=0
        )

    @pytest.mark.asyncio
    async def test_get_messages_pagination(
        self,
        conversation_service,
        mock_db_session,
        mock_zerodb_client,
        sample_conversation
    ):
        """Test message pagination parameters"""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result
        mock_zerodb_client.query_table.return_value = []

        # Execute with custom pagination
        await conversation_service.get_messages(
            conversation_id=sample_conversation.id,
            limit=10,
            offset=20
        )

        # Verify pagination parameters
        mock_zerodb_client.query_table.assert_called_once_with(
            project_id=sample_conversation.workspace.zerodb_project_id,
            table_name="messages",
            limit=10,
            skip=20
        )

    @pytest.mark.asyncio
    async def test_get_messages_conversation_not_found(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test get_messages fails when conversation not found"""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Execute and verify exception
        with pytest.raises(ValueError, match="Conversation .* not found"):
            await conversation_service.get_messages(conversation_id=uuid4())


class TestSearchConversationSemantic:
    """Test suite for search_conversation_semantic method"""

    @pytest.mark.asyncio
    async def test_search_semantic_success(
        self,
        conversation_service,
        mock_db_session,
        mock_zerodb_client,
        sample_conversation
    ):
        """Test successful semantic search"""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Mock ZeroDB search response
        mock_zerodb_client.search_memories.return_value = {
            "results": [
                {
                    "id": "mem_1",
                    "content": "How to deploy",
                    "score": 0.95,
                    "metadata": {"conversation_id": str(sample_conversation.id)}
                },
                {
                    "id": "mem_2",
                    "content": "Deployment steps",
                    "score": 0.87,
                    "metadata": {"conversation_id": str(sample_conversation.id)}
                }
            ],
            "total": 2,
            "query": "deployment"
        }

        # Execute
        result = await conversation_service.search_conversation_semantic(
            conversation_id=sample_conversation.id,
            query="deployment",
            limit=5
        )

        # Verify
        assert result["total"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["score"] == 0.95

        # Verify ZeroDB search call
        mock_zerodb_client.search_memories.assert_called_once_with(
            query="deployment",
            limit=5,
            type="conversation"
        )

    @pytest.mark.asyncio
    async def test_search_semantic_filters_by_conversation(
        self,
        conversation_service,
        mock_db_session,
        mock_zerodb_client,
        sample_conversation
    ):
        """Test semantic search filters results to current conversation"""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Mock response with mixed conversation IDs
        other_conv_id = uuid4()
        mock_zerodb_client.search_memories.return_value = {
            "results": [
                {
                    "id": "mem_1",
                    "content": "Match from this conversation",
                    "metadata": {"conversation_id": str(sample_conversation.id)}
                },
                {
                    "id": "mem_2",
                    "content": "Match from other conversation",
                    "metadata": {"conversation_id": str(other_conv_id)}
                },
                {
                    "id": "mem_3",
                    "content": "Another match from this conversation",
                    "metadata": {"conversation_id": str(sample_conversation.id)}
                }
            ],
            "total": 3
        }

        # Execute
        result = await conversation_service.search_conversation_semantic(
            conversation_id=sample_conversation.id,
            query="test",
            limit=10
        )

        # Verify only results from this conversation are returned
        assert len(result["results"]) == 2
        assert all(
            r["metadata"]["conversation_id"] == str(sample_conversation.id)
            for r in result["results"]
        )

    @pytest.mark.asyncio
    async def test_search_semantic_conversation_not_found(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test semantic search fails when conversation not found"""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Execute and verify exception
        with pytest.raises(ValueError, match="Conversation .* not found"):
            await conversation_service.search_conversation_semantic(
                conversation_id=uuid4(),
                query="test"
            )


class TestArchiveConversation:
    """Test suite for archive_conversation method"""

    @pytest.mark.asyncio
    async def test_archive_conversation_success(
        self,
        conversation_service,
        mock_db_session,
        sample_conversation
    ):
        """Test successful conversation archival"""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Execute
        result = await conversation_service.archive_conversation(
            sample_conversation.id
        )

        # Verify
        assert result.status == "archived"
        assert result.archived_at is not None
        assert isinstance(result.archived_at, datetime)

        # Verify database operations
        mock_db_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_conversation_not_found(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test archive fails when conversation not found"""
        # Setup mock
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db_session.execute.return_value = mock_result

        # Execute and verify exception
        with pytest.raises(ValueError, match="Conversation .* not found"):
            await conversation_service.archive_conversation(uuid4())

    @pytest.mark.asyncio
    async def test_archive_already_archived_conversation(
        self,
        conversation_service,
        mock_db_session,
        sample_conversation
    ):
        """Test archiving an already archived conversation is idempotent"""
        # Setup already archived conversation
        sample_conversation.status = "archived"
        sample_conversation.archived_at = datetime.now(timezone.utc)
        original_archived_at = sample_conversation.archived_at

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Execute
        result = await conversation_service.archive_conversation(
            sample_conversation.id
        )

        # Verify status remains archived and timestamp unchanged
        assert result.status == "archived"
        assert result.archived_at == original_archived_at


class TestListConversations:
    """Test suite for list_conversations method"""

    @pytest.mark.asyncio
    async def test_list_conversations_no_filters(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test list all conversations without filters"""
        # Create sample conversations
        conversations = [
            Conversation(
                id=uuid4(),
                workspace_id=uuid4(),
                agent_id=uuid4(),
                user_id=uuid4(),
                openclaw_session_key=f"session_{i}",
                status="active"
            )
            for i in range(3)
        ]

        # Setup mocks - count query executes first, then main query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 3

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = conversations

        mock_db_session.execute.side_effect = [mock_count_result, mock_result]

        # Execute
        result_conversations, total = await conversation_service.list_conversations(
            limit=50,
            offset=0
        )

        # Verify
        assert len(result_conversations) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_list_conversations_filter_by_workspace(
        self,
        conversation_service,
        mock_db_session,
        sample_workspace
    ):
        """Test list conversations filtered by workspace"""
        # Setup mocks - count query executes first, then main query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db_session.execute.side_effect = [mock_count_result, mock_result]

        # Execute
        result_conversations, total = await conversation_service.list_conversations(
            workspace_id=sample_workspace.id,
            limit=50,
            offset=0
        )

        # Verify execute was called (filters applied)
        assert mock_db_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_conversations_filter_by_agent(
        self,
        conversation_service,
        mock_db_session,
        sample_agent
    ):
        """Test list conversations filtered by agent"""
        # Setup mocks - count query executes first, then main query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db_session.execute.side_effect = [mock_count_result, mock_result]

        # Execute
        result_conversations, total = await conversation_service.list_conversations(
            agent_id=sample_agent.id,
            limit=50,
            offset=0
        )

        # Verify execute was called
        assert mock_db_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_conversations_filter_by_status(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test list conversations filtered by status"""
        # Setup mocks - count query executes first, then main query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db_session.execute.side_effect = [mock_count_result, mock_result]

        # Execute
        result_conversations, total = await conversation_service.list_conversations(
            status="archived",
            limit=50,
            offset=0
        )

        # Verify execute was called
        assert mock_db_session.execute.call_count == 2

    @pytest.mark.asyncio
    async def test_list_conversations_pagination(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test list conversations with pagination"""
        # Create sample conversations
        conversations = [
            Conversation(
                id=uuid4(),
                workspace_id=uuid4(),
                agent_id=uuid4(),
                user_id=uuid4(),
                openclaw_session_key=f"session_{i}",
                status="active"
            )
            for i in range(10)
        ]

        # Setup mocks - count query executes first, then main query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 100

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = conversations

        mock_db_session.execute.side_effect = [mock_count_result, mock_result]

        # Execute with pagination
        result_conversations, total = await conversation_service.list_conversations(
            limit=10,
            offset=20
        )

        # Verify
        assert len(result_conversations) == 10
        assert total == 100

    @pytest.mark.asyncio
    async def test_list_conversations_combined_filters(
        self,
        conversation_service,
        mock_db_session,
        sample_workspace,
        sample_agent
    ):
        """Test list conversations with multiple filters combined"""
        # Setup mocks - count query executes first, then main query
        mock_count_result = MagicMock()
        mock_count_result.scalar.return_value = 0

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db_session.execute.side_effect = [mock_count_result, mock_result]

        # Execute with multiple filters
        result_conversations, total = await conversation_service.list_conversations(
            workspace_id=sample_workspace.id,
            agent_id=sample_agent.id,
            status="active",
            limit=25,
            offset=10
        )

        # Verify execute was called with combined filters
        assert mock_db_session.execute.call_count == 2


class TestErrorHandling:
    """Test suite for error handling scenarios"""

    @pytest.mark.asyncio
    async def test_zerodb_connection_error_handling(
        self,
        conversation_service,
        mock_db_session,
        mock_zerodb_client,
        sample_conversation
    ):
        """Test handling of ZeroDB connection errors"""
        # Setup mocks
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = sample_conversation
        mock_db_session.execute.return_value = mock_result

        # Mock ZeroDB connection error
        mock_zerodb_client.create_table_row.side_effect = ZeroDBConnectionError(
            "Failed to connect to ZeroDB"
        )

        # Execute and verify exception propagates
        with pytest.raises(ZeroDBConnectionError):
            await conversation_service.add_message(
                conversation_id=sample_conversation.id,
                role="user",
                content="Test"
            )

    @pytest.mark.asyncio
    async def test_database_rollback_on_error(
        self,
        conversation_service,
        mock_db_session
    ):
        """Test database rollback on exceptions"""
        # Setup mock to raise exception
        mock_db_session.execute.side_effect = Exception("Database error")

        # Execute and verify exception
        with pytest.raises(Exception):
            await conversation_service.create_conversation(
                workspace_id=uuid4(),
                agent_id=uuid4(),
                user_id=uuid4(),
                openclaw_session_key="session_test"
            )

        # Verify rollback was called
        mock_db_session.rollback.assert_called_once()
