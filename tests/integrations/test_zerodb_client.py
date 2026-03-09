"""
Test suite for ZeroDBClient wrapper.

Following TDD methodology - tests written before implementation.
Coverage target: 100%
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from typing import List, Dict, Any
import httpx


@pytest.fixture
def zerodb_client():
    """Fixture to create a ZeroDBClient instance."""
    from backend.integrations.zerodb_client import ZeroDBClient
    return ZeroDBClient(
        api_url="https://api.ainative.studio",
        api_key="test-api-key-12345"
    )


@pytest.fixture
def mock_httpx_client():
    """Fixture to create a mock httpx.AsyncClient."""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    return mock_client


class TestZeroDBClientInitialization:
    """Test ZeroDBClient initialization."""

    def test_init_with_explicit_params(self):
        """Test initialization with explicit API URL and key."""
        from backend.integrations.zerodb_client import ZeroDBClient

        client = ZeroDBClient(
            api_url="https://custom.api.url",
            api_key="custom-key"
        )

        assert client.api_url == "https://custom.api.url"
        assert client.api_key == "custom-key"

    def test_init_with_default_url(self):
        """Test initialization with default API URL."""
        from backend.integrations.zerodb_client import ZeroDBClient

        client = ZeroDBClient(api_key="test-key")

        assert client.api_url == "https://api.ainative.studio"
        assert client.api_key == "test-key"

    def test_init_stores_headers(self):
        """Test that authorization headers are properly configured."""
        from backend.integrations.zerodb_client import ZeroDBClient

        client = ZeroDBClient(api_key="test-key")

        assert hasattr(client, 'headers')
        assert client.headers.get("Authorization") == "Bearer test-key"
        assert client.headers.get("Content-Type") == "application/json"


class TestCreateProject:
    """Test create_project method."""

    @pytest.mark.asyncio
    async def test_create_project_success(self, zerodb_client, mock_httpx_client):
        """Test successful project creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "proj_123",
            "name": "Test Project",
            "description": "Test Description",
            "created_at": "2026-03-02T10:00:00Z"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.create_project(
                name="Test Project",
                description="Test Description"
            )

        assert result["id"] == "proj_123"
        assert result["name"] == "Test Project"
        assert result["description"] == "Test Description"
        mock_httpx_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_project_api_error(self, zerodb_client, mock_httpx_client):
        """Test project creation with API error."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=Mock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBAPIError) as exc_info:
                await zerodb_client.create_project(
                    name="Test Project",
                    description="Test Description"
                )

        assert "400" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_project_connection_error(self, zerodb_client, mock_httpx_client):
        """Test project creation with connection error."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        mock_httpx_client.post.side_effect = httpx.ConnectError("Connection failed")

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBConnectionError) as exc_info:
                await zerodb_client.create_project(
                    name="Test Project",
                    description="Test Description"
                )

        assert "Connection failed" in str(exc_info.value)


class TestCreateTable:
    """Test create_table method."""

    @pytest.mark.asyncio
    async def test_create_table_success(self, zerodb_client, mock_httpx_client):
        """Test successful table creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "table_456",
            "project_id": "proj_123",
            "table_name": "users",
            "created_at": "2026-03-02T10:00:00Z"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.create_table(
                project_id="proj_123",
                table_name="users"
            )

        assert result["id"] == "table_456"
        assert result["table_name"] == "users"
        assert result["project_id"] == "proj_123"

    @pytest.mark.asyncio
    async def test_create_table_api_error(self, zerodb_client, mock_httpx_client):
        """Test table creation with API error."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Project not found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBAPIError) as exc_info:
                await zerodb_client.create_table(
                    project_id="invalid_proj",
                    table_name="users"
                )

        assert "404" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_table_connection_error(self, zerodb_client, mock_httpx_client):
        """Test table creation with connection error."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        mock_httpx_client.post.side_effect = httpx.ConnectError("Connection failed")

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBConnectionError) as exc_info:
                await zerodb_client.create_table(
                    project_id="proj_123",
                    table_name="users"
                )

        assert "Connection failed" in str(exc_info.value)


class TestCreateTableRow:
    """Test create_table_row method."""

    @pytest.mark.asyncio
    async def test_create_table_row_success(self, zerodb_client, mock_httpx_client):
        """Test successful row creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "row_789",
            "project_id": "proj_123",
            "table_name": "users",
            "data": {"name": "John", "email": "john@example.com"},
            "created_at": "2026-03-02T10:00:00Z"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.create_table_row(
                project_id="proj_123",
                table_name="users",
                row_data={"name": "John", "email": "john@example.com"}
            )

        assert result["id"] == "row_789"
        assert result["data"]["name"] == "John"

    @pytest.mark.asyncio
    async def test_create_table_row_validation_error(self, zerodb_client, mock_httpx_client):
        """Test row creation with validation error."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        mock_response = Mock()
        mock_response.status_code = 422
        mock_response.text = "Validation failed"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Unprocessable Entity", request=Mock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBAPIError) as exc_info:
                await zerodb_client.create_table_row(
                    project_id="proj_123",
                    table_name="users",
                    row_data={"invalid": "data"}
                )

        assert "422" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_table_row_connection_error(self, zerodb_client, mock_httpx_client):
        """Test row creation with connection error."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        mock_httpx_client.post.side_effect = httpx.ConnectError("Network unreachable")

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBConnectionError) as exc_info:
                await zerodb_client.create_table_row(
                    project_id="proj_123",
                    table_name="users",
                    row_data={"name": "John"}
                )

        assert "Network unreachable" in str(exc_info.value)


class TestQueryTable:
    """Test query_table method."""

    @pytest.mark.asyncio
    async def test_query_table_success(self, zerodb_client, mock_httpx_client):
        """Test successful table query."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [
                {"id": "row_1", "name": "John"},
                {"id": "row_2", "name": "Jane"}
            ],
            "total": 2,
            "limit": 10,
            "skip": 0
        }
        mock_httpx_client.get.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.query_table(
                project_id="proj_123",
                table_name="users",
                limit=10,
                skip=0
            )

        assert len(result) == 2
        assert result[0]["name"] == "John"
        assert result[1]["name"] == "Jane"

    @pytest.mark.asyncio
    async def test_query_table_with_pagination(self, zerodb_client, mock_httpx_client):
        """Test table query with pagination parameters."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"id": "row_3", "name": "Bob"}],
            "total": 100,
            "limit": 1,
            "skip": 2
        }
        mock_httpx_client.get.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.query_table(
                project_id="proj_123",
                table_name="users",
                limit=1,
                skip=2
            )

        assert len(result) == 1
        mock_httpx_client.get.assert_called_once()

    @pytest.mark.asyncio
    async def test_query_table_empty_result(self, zerodb_client, mock_httpx_client):
        """Test table query with empty result."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [],
            "total": 0,
            "limit": 10,
            "skip": 0
        }
        mock_httpx_client.get.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.query_table(
                project_id="proj_123",
                table_name="users",
                limit=10,
                skip=0
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_query_table_api_error(self, zerodb_client, mock_httpx_client):
        """Test table query with API error."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.text = "Table not found"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not Found", request=Mock(), response=mock_response
        )
        mock_httpx_client.get.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBAPIError) as exc_info:
                await zerodb_client.query_table(
                    project_id="proj_123",
                    table_name="nonexistent",
                    limit=10,
                    skip=0
                )

        assert "404" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_query_table_connection_error(self, zerodb_client, mock_httpx_client):
        """Test table query with connection error."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        mock_httpx_client.get.side_effect = httpx.ConnectError("Connection timeout")

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBConnectionError) as exc_info:
                await zerodb_client.query_table(
                    project_id="proj_123",
                    table_name="users",
                    limit=10,
                    skip=0
                )

        assert "Connection timeout" in str(exc_info.value)


class TestCreateMemory:
    """Test create_memory method."""

    @pytest.mark.asyncio
    async def test_create_memory_success(self, zerodb_client, mock_httpx_client):
        """Test successful memory creation."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "mem_111",
            "title": "Important Note",
            "content": "This is a test memory",
            "type": "note",
            "tags": ["test", "important"],
            "metadata": {"source": "test"},
            "created_at": "2026-03-02T10:00:00Z"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.create_memory(
                title="Important Note",
                content="This is a test memory",
                type="note",
                tags=["test", "important"],
                metadata={"source": "test"}
            )

        assert result["id"] == "mem_111"
        assert result["title"] == "Important Note"
        assert result["type"] == "note"
        assert len(result["tags"]) == 2

    @pytest.mark.asyncio
    async def test_create_memory_with_empty_tags(self, zerodb_client, mock_httpx_client):
        """Test memory creation with empty tags."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "mem_222",
            "title": "Simple Note",
            "content": "Content",
            "type": "note",
            "tags": [],
            "metadata": {},
            "created_at": "2026-03-02T10:00:00Z"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.create_memory(
                title="Simple Note",
                content="Content",
                type="note",
                tags=[],
                metadata={}
            )

        assert result["tags"] == []

    @pytest.mark.asyncio
    async def test_create_memory_api_error(self, zerodb_client, mock_httpx_client):
        """Test memory creation with API error."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Internal Server Error", request=Mock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBAPIError) as exc_info:
                await zerodb_client.create_memory(
                    title="Test",
                    content="Content",
                    type="note",
                    tags=[],
                    metadata={}
                )

        assert "500" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_create_memory_connection_error(self, zerodb_client, mock_httpx_client):
        """Test memory creation with connection error."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        mock_httpx_client.post.side_effect = httpx.ConnectError("Connection timeout")

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBConnectionError) as exc_info:
                await zerodb_client.create_memory(
                    title="Test",
                    content="Content",
                    type="note",
                    tags=[],
                    metadata={}
                )

        assert "Connection timeout" in str(exc_info.value)


class TestSearchMemories:
    """Test search_memories method."""

    @pytest.mark.asyncio
    async def test_search_memories_success(self, zerodb_client, mock_httpx_client):
        """Test successful memory search."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [
                {
                    "id": "mem_1",
                    "title": "Test Memory 1",
                    "content": "Content 1",
                    "type": "note",
                    "score": 0.95
                },
                {
                    "id": "mem_2",
                    "title": "Test Memory 2",
                    "content": "Content 2",
                    "type": "note",
                    "score": 0.87
                }
            ],
            "total": 2,
            "query": "test"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.search_memories(
                query="test",
                limit=10,
                type="note"
            )

        assert result["total"] == 2
        assert len(result["results"]) == 2
        assert result["results"][0]["score"] == 0.95

    @pytest.mark.asyncio
    async def test_search_memories_with_optional_type(self, zerodb_client, mock_httpx_client):
        """Test memory search without type filter."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": [],
            "total": 0,
            "query": "test"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.search_memories(
                query="test",
                limit=5
            )

        assert result["total"] == 0
        assert result["results"] == []

    @pytest.mark.asyncio
    async def test_search_memories_api_error(self, zerodb_client, mock_httpx_client):
        """Test memory search with API error."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        mock_response = Mock()
        mock_response.status_code = 503
        mock_response.text = "Service Unavailable"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Service Unavailable", request=Mock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBAPIError) as exc_info:
                await zerodb_client.search_memories(
                    query="test",
                    limit=10
                )

        assert "503" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_search_memories_connection_error(self, zerodb_client, mock_httpx_client):
        """Test memory search with connection error."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        mock_httpx_client.post.side_effect = httpx.ConnectError("Network unreachable")

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBConnectionError) as exc_info:
                await zerodb_client.search_memories(
                    query="test",
                    limit=10
                )

        assert "Network unreachable" in str(exc_info.value)


class TestCustomExceptions:
    """Test custom exception classes."""

    def test_zerodb_connection_error(self):
        """Test ZeroDBConnectionError exception."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        error = ZeroDBConnectionError("Connection failed")
        assert str(error) == "Connection failed"
        assert isinstance(error, Exception)

    def test_zerodb_api_error(self):
        """Test ZeroDBAPIError exception."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        error = ZeroDBAPIError("API request failed", status_code=400)
        assert "API request failed" in str(error)
        assert error.status_code == 400

    def test_zerodb_api_error_without_status(self):
        """Test ZeroDBAPIError without status code."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        error = ZeroDBAPIError("Generic API error")
        assert str(error) == "Generic API error"
        assert error.status_code is None


class TestContextManager:
    """Test async context manager support."""

    @pytest.mark.asyncio
    async def test_context_manager_entry_and_exit(self, mock_httpx_client):
        """Test that client works as async context manager."""
        from backend.integrations.zerodb_client import ZeroDBClient

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            async with ZeroDBClient(api_key="test-key") as client:
                assert client.api_key == "test-key"
                assert client.api_url == "https://api.ainative.studio"

    @pytest.mark.asyncio
    async def test_context_manager_closes_client(self):
        """Test that async context manager properly closes HTTP client."""
        from backend.integrations.zerodb_client import ZeroDBClient

        mock_client = AsyncMock()

        with patch('httpx.AsyncClient', return_value=mock_client):
            async with ZeroDBClient(api_key="test-key") as client:
                pass

        mock_client.aclose.assert_called_once()


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_create_project_with_special_characters(self, zerodb_client, mock_httpx_client):
        """Test project creation with special characters in name."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "proj_special",
            "name": "Project: Test & Development (2026)",
            "description": "Special chars: <>\"|?*",
            "created_at": "2026-03-02T10:00:00Z"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.create_project(
                name="Project: Test & Development (2026)",
                description="Special chars: <>\"|?*"
            )

        assert "Special chars" in result["description"]

    @pytest.mark.asyncio
    async def test_query_table_with_zero_limit(self, zerodb_client, mock_httpx_client):
        """Test query with limit=0."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [],
            "total": 100,
            "limit": 0,
            "skip": 0
        }
        mock_httpx_client.get.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.query_table(
                project_id="proj_123",
                table_name="users",
                limit=0,
                skip=0
            )

        assert result == []

    @pytest.mark.asyncio
    async def test_create_memory_with_large_metadata(self, zerodb_client, mock_httpx_client):
        """Test memory creation with large metadata object."""
        large_metadata = {f"key_{i}": f"value_{i}" for i in range(100)}

        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "mem_large",
            "title": "Large Metadata",
            "content": "Content",
            "type": "note",
            "tags": [],
            "metadata": large_metadata,
            "created_at": "2026-03-02T10:00:00Z"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.create_memory(
                title="Large Metadata",
                content="Content",
                type="note",
                tags=[],
                metadata=large_metadata
            )

        assert len(result["metadata"]) == 100


class TestRetryLogic:
    """Test retry logic with exponential backoff."""

    @pytest.mark.asyncio
    async def test_retry_on_transient_error(self, zerodb_client, mock_httpx_client):
        """Test that transient errors trigger retry."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        # First call fails, second succeeds
        mock_httpx_client.post.side_effect = [
            httpx.ConnectError("Temporary network error"),
            Mock(status_code=201, json=lambda: {"id": "proj_retry"})
        ]

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with patch('asyncio.sleep', return_value=None):  # Skip sleep delay
                result = await zerodb_client.create_project_with_retry(
                    name="Test",
                    description="Test",
                    max_retries=3
                )

        assert result["id"] == "proj_retry"
        assert mock_httpx_client.post.call_count == 2

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises_error(self, zerodb_client, mock_httpx_client):
        """Test that exhausted retries raise final error."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        mock_httpx_client.post.side_effect = httpx.ConnectError("Persistent error")

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with patch('asyncio.sleep', return_value=None):
                with pytest.raises(ZeroDBConnectionError):
                    await zerodb_client.create_project_with_retry(
                        name="Test",
                        description="Test",
                        max_retries=2
                    )

        assert mock_httpx_client.post.call_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff(self, zerodb_client, mock_httpx_client):
        """Test exponential backoff delay calculation."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        mock_httpx_client.post.side_effect = httpx.ConnectError("Error")
        sleep_delays = []

        async def mock_sleep(delay):
            sleep_delays.append(delay)

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with patch('asyncio.sleep', side_effect=mock_sleep):
                with pytest.raises(ZeroDBConnectionError):
                    await zerodb_client.create_project_with_retry(
                        name="Test",
                        description="Test",
                        max_retries=3,
                        base_delay=1.0
                    )

        # Verify exponential backoff: 1s, 2s, 4s
        assert len(sleep_delays) == 3
        assert sleep_delays[0] >= 1.0 and sleep_delays[0] <= 1.2  # With jitter
        assert sleep_delays[1] >= 2.0 and sleep_delays[1] <= 2.4
        assert sleep_delays[2] >= 4.0 and sleep_delays[2] <= 4.8

    @pytest.mark.asyncio
    async def test_no_retry_on_client_error(self, zerodb_client, mock_httpx_client):
        """Test that 4xx errors don't trigger retry."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        mock_response = Mock()
        mock_response.status_code = 400
        mock_response.text = "Bad Request"
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=Mock(), response=mock_response
        )
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBAPIError):
                await zerodb_client.create_project_with_retry(
                    name="Test",
                    description="Test",
                    max_retries=3
                )

        # Should NOT retry on 4xx errors
        assert mock_httpx_client.post.call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_server_error(self, zerodb_client, mock_httpx_client):
        """Test that 5xx errors trigger retry."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        mock_error_response = Mock()
        mock_error_response.status_code = 503
        mock_error_response.text = "Service Unavailable"
        mock_error_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Service Unavailable", request=Mock(), response=mock_error_response
        )

        mock_success_response = Mock()
        mock_success_response.status_code = 201
        mock_success_response.json.return_value = {"id": "proj_recovered"}

        # First two calls fail with 503, third succeeds
        mock_httpx_client.post.side_effect = [
            mock_error_response,
            mock_error_response,
            mock_success_response
        ]

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with patch('asyncio.sleep', return_value=None):
                result = await zerodb_client.create_project_with_retry(
                    name="Test",
                    description="Test",
                    max_retries=3
                )

        assert result["id"] == "proj_recovered"
        assert mock_httpx_client.post.call_count == 3


class TestConnectionPooling:
    """Test connection pooling and reuse."""

    @pytest.mark.asyncio
    async def test_client_uses_persistent_connection(self, mock_httpx_client):
        """Test that client reuses persistent HTTP connection."""
        from backend.integrations.zerodb_client import ZeroDBClient

        mock_httpx_client.post.return_value = Mock(
            status_code=201,
            json=lambda: {"id": "proj_1"}
        )

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            async with ZeroDBClient(api_key="test-key") as client:
                # Multiple calls should reuse same client
                await client.create_project("Test 1", "Desc 1")
                await client.create_project("Test 2", "Desc 2")
                await client.create_project("Test 3", "Desc 3")

        # Verify client was created once and closed once
        assert mock_httpx_client.aclose.call_count == 1
        assert mock_httpx_client.post.call_count == 3

    @pytest.mark.asyncio
    async def test_connection_pool_limits(self):
        """Test configurable connection pool limits."""
        from backend.integrations.zerodb_client import ZeroDBClient

        client = ZeroDBClient(
            api_key="test-key",
            pool_max_connections=20,
            pool_max_keepalive_connections=10
        )

        assert client.pool_max_connections == 20
        assert client.pool_max_keepalive_connections == 10

    @pytest.mark.asyncio
    async def test_timeout_configuration(self):
        """Test configurable request timeouts."""
        from backend.integrations.zerodb_client import ZeroDBClient

        client = ZeroDBClient(
            api_key="test-key",
            timeout=30.0,
            connect_timeout=5.0
        )

        assert client.timeout == 30.0
        assert client.connect_timeout == 5.0

    @pytest.mark.asyncio
    async def test_timeout_enforcement(self, zerodb_client, mock_httpx_client):
        """Test that timeout is enforced on requests."""
        from backend.integrations.zerodb_client import ZeroDBConnectionError

        mock_httpx_client.post.side_effect = httpx.TimeoutException("Request timeout")

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBConnectionError) as exc_info:
                await zerodb_client.create_project("Test", "Test")

        assert "timeout" in str(exc_info.value).lower()


class TestQueryBuilder:
    """Test query builder helpers for complex filters."""

    def test_eq_filter_builder(self, zerodb_client):
        """Test equality filter builder."""
        query = zerodb_client.build_filter().eq("status", "active").build()
        assert query == {"status": {"$eq": "active"}}

    def test_ne_filter_builder(self, zerodb_client):
        """Test not-equal filter builder."""
        query = zerodb_client.build_filter().ne("status", "deleted").build()
        assert query == {"status": {"$ne": "deleted"}}

    def test_gt_filter_builder(self, zerodb_client):
        """Test greater-than filter builder."""
        query = zerodb_client.build_filter().gt("age", 18).build()
        assert query == {"age": {"$gt": 18}}

    def test_gte_filter_builder(self, zerodb_client):
        """Test greater-than-or-equal filter builder."""
        query = zerodb_client.build_filter().gte("score", 50).build()
        assert query == {"score": {"$gte": 50}}

    def test_lt_filter_builder(self, zerodb_client):
        """Test less-than filter builder."""
        query = zerodb_client.build_filter().lt("price", 100).build()
        assert query == {"price": {"$lt": 100}}

    def test_lte_filter_builder(self, zerodb_client):
        """Test less-than-or-equal filter builder."""
        query = zerodb_client.build_filter().lte("quantity", 10).build()
        assert query == {"quantity": {"$lte": 10}}

    def test_in_filter_builder(self, zerodb_client):
        """Test in-array filter builder."""
        query = zerodb_client.build_filter().in_("category", ["tech", "science"]).build()
        assert query == {"category": {"$in": ["tech", "science"]}}

    def test_nin_filter_builder(self, zerodb_client):
        """Test not-in-array filter builder."""
        query = zerodb_client.build_filter().nin("status", ["deleted", "archived"]).build()
        assert query == {"status": {"$nin": ["deleted", "archived"]}}

    def test_and_filter_builder(self, zerodb_client):
        """Test AND condition builder."""
        query = (
            zerodb_client.build_filter()
            .and_(
                {"status": {"$eq": "active"}},
                {"age": {"$gte": 18}}
            )
            .build()
        )
        assert query == {
            "$and": [
                {"status": {"$eq": "active"}},
                {"age": {"$gte": 18}}
            ]
        }

    def test_or_filter_builder(self, zerodb_client):
        """Test OR condition builder."""
        query = (
            zerodb_client.build_filter()
            .or_(
                {"status": {"$eq": "active"}},
                {"status": {"$eq": "pending"}}
            )
            .build()
        )
        assert query == {
            "$or": [
                {"status": {"$eq": "active"}},
                {"status": {"$eq": "pending"}}
            ]
        }

    def test_chained_filter_builder(self, zerodb_client):
        """Test chaining multiple filter conditions."""
        query = (
            zerodb_client.build_filter()
            .eq("workspace_id", "ws_123")
            .gte("created_at", 1234567890)
            .in_("status", ["active", "pending"])
            .build()
        )
        assert query == {
            "workspace_id": {"$eq": "ws_123"},
            "created_at": {"$gte": 1234567890},
            "status": {"$in": ["active", "pending"]}
        }

    def test_complex_nested_filter(self, zerodb_client):
        """Test complex nested filter with AND/OR."""
        query = (
            zerodb_client.build_filter()
            .and_(
                {"workspace_id": {"$eq": "ws_123"}},
                {
                    "$or": [
                        {"status": {"$eq": "active"}},
                        {"expires_at": {"$gt": 1234567890}}
                    ]
                }
            )
            .build()
        )
        assert "$and" in query
        assert "$or" in query["$and"][1]


class TestTransactionSupport:
    """Test transaction support for batch operations."""

    @pytest.mark.asyncio
    async def test_batch_insert_with_transaction(self, zerodb_client, mock_httpx_client):
        """Test batch insert within transaction."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "inserted_count": 3,
            "inserted_ids": ["row_1", "row_2", "row_3"]
        }
        mock_httpx_client.post.return_value = mock_response

        rows = [
            {"name": "Alice", "age": 25},
            {"name": "Bob", "age": 30},
            {"name": "Charlie", "age": 35}
        ]

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            async with zerodb_client.transaction() as txn:
                result = await txn.insert_rows(
                    table_name="users",
                    rows=rows,
                    project_id="proj_123"
                )

        assert result["inserted_count"] == 3
        assert len(result["inserted_ids"]) == 3

    @pytest.mark.asyncio
    async def test_transaction_rollback_on_error(self, zerodb_client, mock_httpx_client):
        """Test transaction rollback on error."""
        from backend.integrations.zerodb_client import ZeroDBAPIError

        mock_httpx_client.post.side_effect = httpx.HTTPStatusError(
            "Error", request=Mock(), response=Mock(status_code=500, text="Error")
        )

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with pytest.raises(ZeroDBAPIError):
                async with zerodb_client.transaction() as txn:
                    await txn.insert_rows(
                        table_name="users",
                        rows=[{"name": "Test"}],
                        project_id="proj_123"
                    )

        # Verify rollback was called
        # (In actual implementation, this would verify cleanup operations)

    @pytest.mark.asyncio
    async def test_transaction_commit(self, zerodb_client, mock_httpx_client):
        """Test explicit transaction commit."""
        mock_httpx_client.post.return_value = Mock(
            status_code=201,
            json=lambda: {"inserted_count": 1}
        )

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            async with zerodb_client.transaction() as txn:
                await txn.insert_rows(
                    table_name="users",
                    rows=[{"name": "Test"}],
                    project_id="proj_123"
                )
                await txn.commit()

        # Verify commit was successful


class TestCircuitBreaker:
    """Test circuit breaker pattern for fault tolerance."""

    @pytest.mark.asyncio
    async def test_circuit_breaker_opens_after_failures(self, zerodb_client, mock_httpx_client):
        """Test circuit breaker opens after threshold failures."""
        from backend.integrations.zerodb_client import CircuitBreakerOpenError

        mock_httpx_client.post.side_effect = httpx.ConnectError("Connection failed")

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            # Trigger failures to open circuit
            for _ in range(5):
                try:
                    await zerodb_client.create_project("Test", "Test")
                except Exception:
                    pass

            # Circuit should be open now
            with pytest.raises(CircuitBreakerOpenError):
                await zerodb_client.create_project("Test", "Test")

    @pytest.mark.asyncio
    async def test_circuit_breaker_half_open_after_timeout(self, zerodb_client, mock_httpx_client):
        """Test circuit breaker transitions to half-open after timeout."""
        from backend.integrations.zerodb_client import CircuitBreakerOpenError

        mock_httpx_client.post.side_effect = [
            httpx.ConnectError("Error"),  # Fail to open circuit
            Mock(status_code=201, json=lambda: {"id": "proj_recovered"})  # Success in half-open
        ]

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            with patch('asyncio.sleep', return_value=None):
                # Open circuit
                try:
                    await zerodb_client.create_project("Test", "Test")
                except Exception:
                    pass

                # Wait for recovery timeout
                zerodb_client._circuit_breaker_state = "half_open"

                # Should allow retry in half-open state
                result = await zerodb_client.create_project("Test", "Test")
                assert result["id"] == "proj_recovered"

    @pytest.mark.asyncio
    async def test_circuit_breaker_closes_on_success(self, zerodb_client, mock_httpx_client):
        """Test circuit breaker closes after successful request."""
        mock_httpx_client.post.return_value = Mock(
            status_code=201,
            json=lambda: {"id": "proj_success"}
        )

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            zerodb_client._circuit_breaker_state = "half_open"

            result = await zerodb_client.create_project("Test", "Test")

            assert result["id"] == "proj_success"
            assert zerodb_client._circuit_breaker_state == "closed"


class TestBulkOperations:
    """Test enhanced bulk operations for Epic E9."""

    @pytest.mark.asyncio
    async def test_bulk_upsert(self, zerodb_client, mock_httpx_client):
        """Test bulk upsert operation."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "upserted_count": 5,
            "inserted_count": 3,
            "updated_count": 2
        }
        mock_httpx_client.post.return_value = mock_response

        rows = [
            {"id": "msg_1", "content": "Message 1"},
            {"id": "msg_2", "content": "Message 2"},
            {"id": "msg_3", "content": "Message 3"},
            {"id": "msg_4", "content": "Message 4"},
            {"id": "msg_5", "content": "Message 5"}
        ]

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.bulk_upsert(
                table_name="messages",
                rows=rows,
                unique_key="id",
                project_id="proj_123"
            )

        assert result["upserted_count"] == 5
        assert result["inserted_count"] == 3
        assert result["updated_count"] == 2

    @pytest.mark.asyncio
    async def test_paginated_query_all(self, zerodb_client, mock_httpx_client):
        """Test paginated query that fetches all results."""
        # Mock multiple pages of results
        mock_httpx_client.get.side_effect = [
            Mock(status_code=200, json=lambda: {
                "data": [{"id": f"row_{i}"} for i in range(1, 101)],
                "total": 250
            }),
            Mock(status_code=200, json=lambda: {
                "data": [{"id": f"row_{i}"} for i in range(101, 201)],
                "total": 250
            }),
            Mock(status_code=200, json=lambda: {
                "data": [{"id": f"row_{i}"} for i in range(201, 251)],
                "total": 250
            })
        ]

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            all_rows = await zerodb_client.query_all(
                table_name="messages",
                project_id="proj_123",
                page_size=100
            )

        assert len(all_rows) == 250
        assert all_rows[0]["id"] == "row_1"
        assert all_rows[-1]["id"] == "row_250"

    @pytest.mark.asyncio
    async def test_batch_delete_by_ids(self, zerodb_client, mock_httpx_client):
        """Test batch delete by list of IDs."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "deleted_count": 10,
            "deleted_ids": [f"msg_{i}" for i in range(1, 11)]
        }
        mock_httpx_client.request.return_value = mock_response

        ids_to_delete = [f"msg_{i}" for i in range(1, 11)]

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.delete_by_ids(
                table_name="messages",
                ids=ids_to_delete,
                project_id="proj_123"
            )

        assert result["deleted_count"] == 10
        assert len(result["deleted_ids"]) == 10


class TestCacheIntegration:
    """Test caching layer for frequently accessed data."""

    @pytest.mark.asyncio
    async def test_query_with_cache_miss(self, zerodb_client, mock_httpx_client):
        """Test query with cache miss fetches from API."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"id": "row_1", "name": "Test"}]
        }
        mock_httpx_client.get.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.query_with_cache(
                table_name="users",
                project_id="proj_123",
                cache_key="users_active",
                cache_ttl=300
            )

        assert len(result) == 1
        assert mock_httpx_client.get.call_count == 1

    @pytest.mark.asyncio
    async def test_query_with_cache_hit(self, zerodb_client, mock_httpx_client):
        """Test query with cache hit skips API call."""
        # Prime the cache
        zerodb_client._cache["users_active"] = {
            "data": [{"id": "row_1", "name": "Cached"}],
            "expires_at": 9999999999
        }

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.query_with_cache(
                table_name="users",
                project_id="proj_123",
                cache_key="users_active",
                cache_ttl=300
            )

        assert result[0]["name"] == "Cached"
        assert mock_httpx_client.get.call_count == 0  # No API call

    @pytest.mark.asyncio
    async def test_cache_invalidation(self, zerodb_client):
        """Test manual cache invalidation."""
        # Prime the cache
        zerodb_client._cache["test_key"] = {
            "data": [{"id": "row_1"}],
            "expires_at": 9999999999
        }

        # Invalidate cache
        zerodb_client.invalidate_cache("test_key")

        assert "test_key" not in zerodb_client._cache

    @pytest.mark.asyncio
    async def test_cache_expiration(self, zerodb_client, mock_httpx_client):
        """Test expired cache entries are refreshed."""
        # Prime cache with expired entry
        zerodb_client._cache["users_active"] = {
            "data": [{"id": "row_1", "name": "Old"}],
            "expires_at": 1234567890  # Expired timestamp
        }

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"id": "row_1", "name": "Fresh"}]
        }
        mock_httpx_client.get.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.query_with_cache(
                table_name="users",
                project_id="proj_123",
                cache_key="users_active",
                cache_ttl=300
            )

        assert result[0]["name"] == "Fresh"
        assert mock_httpx_client.get.call_count == 1  # API was called


class TestWorkspaceAndConversationSupport:
    """Test Workspace and Conversation-specific helpers for Epic E9."""

    @pytest.mark.asyncio
    async def test_create_workspace_table(self, zerodb_client, mock_httpx_client):
        """Test helper to create workspace-scoped table."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "id": "table_ws_messages",
            "table_name": "workspace_123_messages"
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.create_workspace_table(
                workspace_id="workspace_123",
                table_type="messages",
                project_id="proj_123"
            )

        assert "workspace_123" in result["table_name"]
        assert "messages" in result["table_name"]

    @pytest.mark.asyncio
    async def test_query_conversation_messages(self, zerodb_client, mock_httpx_client):
        """Test helper to query conversation messages."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "rows": [
                {"id": "msg_1", "role": "user", "content": "Hello"},
                {"id": "msg_2", "role": "assistant", "content": "Hi there"}
            ],
            "total": 2
        }
        mock_httpx_client.post.return_value = mock_response

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.query_conversation_messages(
                conversation_id="conv_123",
                workspace_id="ws_123",
                limit=50,
                project_id="proj_123"
            )

        assert len(result["rows"]) == 2
        assert result["rows"][0]["role"] == "user"
        assert result["rows"][1]["role"] == "assistant"

    @pytest.mark.asyncio
    async def test_store_conversation_message(self, zerodb_client, mock_httpx_client):
        """Test helper to store a single conversation message."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            "inserted_count": 1,
            "inserted_ids": ["msg_new"]
        }
        mock_httpx_client.post.return_value = mock_response

        message_data = {
            "conversation_id": "conv_123",
            "role": "user",
            "content": "Test message",
            "timestamp": 1234567890
        }

        with patch('httpx.AsyncClient', return_value=mock_httpx_client):
            result = await zerodb_client.store_conversation_message(
                workspace_id="ws_123",
                message_data=message_data,
                project_id="proj_123"
            )

        assert result["inserted_count"] == 1
        assert len(result["inserted_ids"]) == 1
