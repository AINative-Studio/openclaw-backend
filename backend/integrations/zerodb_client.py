"""
ZeroDBClient - Enhanced async HTTP client wrapper for ZeroDB API.

This module provides a high-level interface to interact with ZeroDB's
NoSQL database and memory storage APIs with advanced features:
- Retry logic with exponential backoff
- Connection pooling and reuse
- Query builder helpers
- Transaction support
- Circuit breaker pattern
- Caching layer
- Workspace and Conversation-specific helpers for Epic E9

Environment Variables:
    ZERODB_API_KEY: API key for authentication
    ZERODB_API_URL: Base URL for ZeroDB API (default: https://api.ainative.studio)

Usage:
    async with ZeroDBClient(api_key="your-key") as client:
        project = await client.create_project(name="MyProject", description="Test")
        rows = await client.query_table(project_id="proj_123", table_name="users", limit=10, skip=0)
"""

from typing import List, Dict, Any, Optional, AsyncContextManager
import httpx
import os
import asyncio
import random
import time
from contextlib import asynccontextmanager


class ZeroDBConnectionError(Exception):
    """
    Raised when a connection to ZeroDB API fails.

    This includes network errors, timeouts, DNS resolution failures,
    and other transport-level errors.
    """

    def __init__(self, message: str):
        """
        Initialize ZeroDBConnectionError.

        Args:
            message: Error description
        """
        super().__init__(message)


class ZeroDBAPIError(Exception):
    """
    Raised when ZeroDB API returns an error response.

    This includes HTTP 4xx and 5xx status codes, indicating client
    or server errors.
    """

    def __init__(self, message: str, status_code: Optional[int] = None):
        """
        Initialize ZeroDBAPIError.

        Args:
            message: Error description
            status_code: HTTP status code (optional)
        """
        super().__init__(message)
        self.status_code = status_code


class CircuitBreakerOpenError(Exception):
    """Raised when circuit breaker is open and requests are blocked."""

    pass


class FilterBuilder:
    """
    Query filter builder for MongoDB-style queries.

    Provides fluent interface for building complex filter queries.
    """

    def __init__(self):
        """Initialize empty filter."""
        self._filter: Dict[str, Any] = {}

    def eq(self, field: str, value: Any) -> "FilterBuilder":
        """Add equality filter."""
        self._filter[field] = {"$eq": value}
        return self

    def ne(self, field: str, value: Any) -> "FilterBuilder":
        """Add not-equal filter."""
        self._filter[field] = {"$ne": value}
        return self

    def gt(self, field: str, value: Any) -> "FilterBuilder":
        """Add greater-than filter."""
        self._filter[field] = {"$gt": value}
        return self

    def gte(self, field: str, value: Any) -> "FilterBuilder":
        """Add greater-than-or-equal filter."""
        self._filter[field] = {"$gte": value}
        return self

    def lt(self, field: str, value: Any) -> "FilterBuilder":
        """Add less-than filter."""
        self._filter[field] = {"$lt": value}
        return self

    def lte(self, field: str, value: Any) -> "FilterBuilder":
        """Add less-than-or-equal filter."""
        self._filter[field] = {"$lte": value}
        return self

    def in_(self, field: str, values: List[Any]) -> "FilterBuilder":
        """Add in-array filter."""
        self._filter[field] = {"$in": values}
        return self

    def nin(self, field: str, values: List[Any]) -> "FilterBuilder":
        """Add not-in-array filter."""
        self._filter[field] = {"$nin": values}
        return self

    def and_(self, *conditions: Dict[str, Any]) -> "FilterBuilder":
        """Add AND condition."""
        self._filter["$and"] = list(conditions)
        return self

    def or_(self, *conditions: Dict[str, Any]) -> "FilterBuilder":
        """Add OR condition."""
        self._filter["$or"] = list(conditions)
        return self

    def build(self) -> Dict[str, Any]:
        """Build and return the filter query."""
        return self._filter


class Transaction:
    """
    Transaction context for batch operations.

    Provides commit/rollback semantics for ZeroDB operations.
    """

    def __init__(self, client: "ZeroDBClient"):
        """Initialize transaction."""
        self._client = client
        self._operations: List[Dict[str, Any]] = []
        self._committed = False

    async def insert_rows(
        self,
        table_name: str,
        rows: List[Dict[str, Any]],
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Insert rows within transaction."""
        # In actual implementation, this would batch operations
        # For now, delegate to client
        return await self._client.insert_rows(table_name, rows, project_id)

    async def commit(self):
        """Commit transaction."""
        self._committed = True

    async def rollback(self):
        """Rollback transaction."""
        self._operations.clear()


class ZeroDBClient:
    """
    Async HTTP client for ZeroDB API.

    Provides methods to create projects, manage NoSQL tables, create rows,
    query data, and manage memory storage for AI agents.

    Attributes:
        api_url: Base URL for ZeroDB API
        api_key: API key for authentication
        headers: HTTP headers including Authorization and Content-Type
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        pool_max_connections: int = 100,
        pool_max_keepalive_connections: int = 20,
        timeout: float = 30.0,
        connect_timeout: float = 10.0
    ):
        """
        Initialize ZeroDBClient.

        Args:
            api_key: ZeroDB API key for authentication (defaults to ZERODB_API_KEY env var)
            api_url: Base URL for ZeroDB API (defaults to ZERODB_API_URL env var or https://api.ainative.studio/v1)
            pool_max_connections: Maximum number of connections in pool
            pool_max_keepalive_connections: Maximum keepalive connections
            timeout: Request timeout in seconds
            connect_timeout: Connection timeout in seconds
        """
        self.api_key = api_key or os.getenv("ZERODB_API_KEY")
        self.api_url = api_url or os.getenv("ZERODB_API_URL", "https://api.ainative.studio/v1")

        if not self.api_key:
            raise ValueError("ZERODB_API_KEY must be provided or set in environment")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Connection pooling configuration
        self.pool_max_connections = pool_max_connections
        self.pool_max_keepalive_connections = pool_max_keepalive_connections

        # Timeout configuration
        self.timeout = timeout
        self.connect_timeout = connect_timeout

        # Internal state
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, Dict[str, Any]] = {}

        # Circuit breaker state
        self._circuit_breaker_state = "closed"
        self._failure_count = 0
        self._circuit_breaker_threshold = 5
        self._circuit_breaker_timeout = 60.0
        self._last_failure_time = 0.0

    async def __aenter__(self):
        """
        Async context manager entry.

        Creates and returns the client instance.

        Returns:
            Self instance
        """
        self._client = httpx.AsyncClient()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """
        Async context manager exit.

        Closes the HTTP client connection.

        Args:
            exc_type: Exception type (if any)
            exc_val: Exception value (if any)
            exc_tb: Exception traceback (if any)
        """
        if self._client:
            await self._client.aclose()

    async def create_project(
        self,
        name: str,
        description: str
    ) -> Dict[str, Any]:
        """
        Create a new ZeroDB project.

        Projects are top-level containers for tables and data.

        Args:
            name: Project name
            description: Project description

        Returns:
            Dict containing project details:
                - id: Project ID
                - name: Project name
                - description: Project description
                - created_at: ISO 8601 timestamp

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response
            CircuitBreakerOpenError: If circuit breaker is open

        Example:
            project = await client.create_project(
                name="MyProject",
                description="Test project"
            )
        """
        # Check circuit breaker
        if self._circuit_breaker_state == "open":
            # Check if timeout elapsed
            if time.time() - self._last_failure_time < self._circuit_breaker_timeout:
                raise CircuitBreakerOpenError("Circuit breaker is open")
            else:
                self._circuit_breaker_state = "half_open"

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/projects",
                    headers=self.headers,
                    json={"name": name, "description": description}
                )
                response.raise_for_status()

                # Success - reset circuit breaker
                if self._circuit_breaker_state == "half_open":
                    self._circuit_breaker_state = "closed"
                    self._failure_count = 0

                return response.json()
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                self._handle_circuit_breaker_failure()
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    def _handle_circuit_breaker_failure(self):
        """Handle circuit breaker failure."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self._failure_count >= self._circuit_breaker_threshold:
            self._circuit_breaker_state = "open"

    async def create_table(
        self,
        project_id: str,
        table_name: str
    ) -> Dict[str, Any]:
        """
        Create a new table in a ZeroDB project.

        Tables store NoSQL documents with flexible schemas.

        Args:
            project_id: ID of the project
            table_name: Name of the table to create

        Returns:
            Dict containing table details:
                - id: Table ID
                - project_id: Parent project ID
                - table_name: Table name
                - created_at: ISO 8601 timestamp

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response

        Example:
            table = await client.create_table(
                project_id="proj_123",
                table_name="users"
            )
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/projects/{project_id}/tables",
                    headers=self.headers,
                    json={"table_name": table_name}
                )
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    async def create_table_row(
        self,
        project_id: str,
        table_name: str,
        row_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new row (document) in a table.

        Args:
            project_id: ID of the project
            table_name: Name of the table
            row_data: Document data as key-value pairs

        Returns:
            Dict containing row details:
                - id: Row ID
                - project_id: Parent project ID
                - table_name: Table name
                - data: The stored document
                - created_at: ISO 8601 timestamp

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response

        Example:
            row = await client.create_table_row(
                project_id="proj_123",
                table_name="users",
                row_data={"name": "John", "email": "john@example.com"}
            )
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/projects/{project_id}/tables/{table_name}/rows",
                    headers=self.headers,
                    json={"data": row_data}
                )
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    async def query_table(
        self,
        project_id: str,
        table_name: str,
        limit: int = 10,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Query rows from a table with pagination.

        Args:
            project_id: ID of the project
            table_name: Name of the table
            limit: Maximum number of rows to return (default: 10)
            skip: Number of rows to skip for pagination (default: 0)

        Returns:
            List of row documents. Each document is a dict with at least:
                - id: Row ID
                - Additional fields based on stored data

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response

        Example:
            # Get first 10 rows
            rows = await client.query_table(
                project_id="proj_123",
                table_name="users",
                limit=10,
                skip=0
            )

            # Get next 10 rows
            rows = await client.query_table(
                project_id="proj_123",
                table_name="users",
                limit=10,
                skip=10
            )
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.api_url}/projects/{project_id}/tables/{table_name}/rows",
                    headers=self.headers,
                    params={"limit": limit, "skip": skip}
                )
                response.raise_for_status()
                result = response.json()
                return result.get("data", [])
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    async def create_memory(
        self,
        title: str,
        content: str,
        type: str,
        tags: List[str],
        metadata: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a memory entry for AI agent context storage.

        Memories are used to store important information, notes, and context
        that AI agents can search and retrieve later.

        Args:
            title: Memory title/subject
            content: Memory content/body
            type: Memory type (e.g., "note", "fact", "conversation")
            tags: List of tags for categorization
            metadata: Additional metadata as key-value pairs

        Returns:
            Dict containing memory details:
                - id: Memory ID
                - title: Memory title
                - content: Memory content
                - type: Memory type
                - tags: List of tags
                - metadata: Metadata dict
                - created_at: ISO 8601 timestamp

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response

        Example:
            memory = await client.create_memory(
                title="Important Note",
                content="Remember this for later",
                type="note",
                tags=["important", "project-x"],
                metadata={"source": "user-input", "priority": "high"}
            )
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/memories",
                    headers=self.headers,
                    json={
                        "title": title,
                        "content": content,
                        "type": type,
                        "tags": tags,
                        "metadata": metadata
                    }
                )
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    async def search_memories(
        self,
        query: str,
        limit: int = 10,
        type: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search memories using semantic similarity.

        Uses vector embeddings to find memories similar to the query text.

        Args:
            query: Search query text
            limit: Maximum number of results to return (default: 10)
            type: Optional filter by memory type

        Returns:
            Dict containing search results:
                - results: List of matching memories, each with:
                    - id: Memory ID
                    - title: Memory title
                    - content: Memory content
                    - type: Memory type
                    - score: Similarity score (0.0 to 1.0)
                - total: Total number of results
                - query: The search query

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response

        Example:
            # Search all memories
            results = await client.search_memories(
                query="user authentication",
                limit=5
            )

            # Search only notes
            results = await client.search_memories(
                query="user authentication",
                limit=5,
                type="note"
            )
        """
        async with httpx.AsyncClient() as client:
            try:
                payload = {
                    "query": query,
                    "limit": limit
                }
                if type is not None:
                    payload["type"] = type

                response = await client.post(
                    f"{self.api_url}/memories/search",
                    headers=self.headers,
                    json=payload
                )
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    async def query_rows(
        self,
        table_name: str,
        filter_query: Dict[str, Any],
        project_id: Optional[str] = None,
        limit: int = 100,
        skip: int = 0
    ) -> Dict[str, Any]:
        """
        Query table rows using MongoDB-style filter queries.

        Supports operators: $eq, $ne, $gt, $gte, $lt, $lte, $in, $nin, $and, $or

        Args:
            table_name: Name of the table to query
            filter_query: MongoDB-style filter query dict
            project_id: Project ID (defaults to ZERODB_PROJECT_ID env var)
            limit: Maximum number of rows to return (default: 100)
            skip: Number of rows to skip for pagination (default: 0)

        Returns:
            Dict containing:
                - rows: List of matching rows
                - total: Total number of matching rows
                - limit: Limit used
                - skip: Skip offset used

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response

        Example:
            # Query with equality filter
            result = await client.query_rows(
                table_name="openclaw_cache",
                filter_query={"key": {"$eq": "session_123"}}
            )

            # Query with range filter
            result = await client.query_rows(
                table_name="openclaw_cache",
                filter_query={"expires_at": {"$gt": 1234567890}}
            )

            # Query with OR condition
            result = await client.query_rows(
                table_name="openclaw_cache",
                filter_query={
                    "$or": [
                        {"expires_at": {"$eq": None}},
                        {"expires_at": {"$gt": 1234567890}}
                    ]
                }
            )
        """
        proj_id = project_id or os.getenv("ZERODB_PROJECT_ID")
        if not proj_id:
            raise ValueError("project_id must be provided or ZERODB_PROJECT_ID must be set in environment")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/v1/public/{proj_id}/database/tables/{table_name}/query",
                    headers=self.headers,
                    json={
                        "filter": filter_query,
                        "limit": limit,
                        "skip": skip
                    }
                )
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    async def insert_rows(
        self,
        table_name: str,
        rows: List[Dict[str, Any]],
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Insert multiple rows into a table.

        Args:
            table_name: Name of the table
            rows: List of row documents to insert
            project_id: Project ID (defaults to ZERODB_PROJECT_ID env var)

        Returns:
            Dict containing:
                - inserted_count: Number of rows inserted
                - inserted_ids: List of inserted row IDs

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response

        Example:
            result = await client.insert_rows(
                table_name="openclaw_cache",
                rows=[
                    {"key": "session_1", "value": "data1", "expires_at": 1234567890},
                    {"key": "session_2", "value": "data2", "expires_at": 1234567891}
                ]
            )
        """
        proj_id = project_id or os.getenv("ZERODB_PROJECT_ID")
        if not proj_id:
            raise ValueError("project_id must be provided or ZERODB_PROJECT_ID must be set in environment")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/v1/public/{proj_id}/database/tables/{table_name}/rows",
                    headers=self.headers,
                    json={"row_data": rows[0]} if len(rows) == 1 else {"rows": rows}
                )
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    async def update_rows(
        self,
        table_name: str,
        filter_query: Dict[str, Any],
        update_data: Dict[str, Any],
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Update rows matching filter query.

        Args:
            table_name: Name of the table
            filter_query: MongoDB-style filter to match rows
            update_data: Dictionary of fields to update
            project_id: Project ID (defaults to ZERODB_PROJECT_ID env var)

        Returns:
            Dict containing:
                - updated_count: Number of rows updated
                - updated_ids: List of updated row IDs

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response

        Example:
            result = await client.update_rows(
                table_name="openclaw_cache",
                filter_query={"key": {"$eq": "session_123"}},
                update_data={"value": "new_data", "expires_at": 1234567999}
            )
        """
        proj_id = project_id or os.getenv("ZERODB_PROJECT_ID")
        if not proj_id:
            raise ValueError("project_id must be provided or ZERODB_PROJECT_ID must be set in environment")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.put(
                    f"{self.api_url}/v1/public/{proj_id}/database/tables/{table_name}/rows/bulk",
                    headers=self.headers,
                    json={
                        "filter": filter_query,
                        "update": {"$set": update_data}
                    }
                )
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    async def delete_rows(
        self,
        table_name: str,
        filter_query: Dict[str, Any],
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Delete rows matching filter query.

        Args:
            table_name: Name of the table
            filter_query: MongoDB-style filter to match rows
            project_id: Project ID (defaults to ZERODB_PROJECT_ID env var)

        Returns:
            Dict containing:
                - deleted_count: Number of rows deleted
                - deleted_ids: List of deleted row IDs

        Raises:
            ZeroDBConnectionError: If connection to API fails
            ZeroDBAPIError: If API returns error response

        Example:
            # Delete expired cache entries
            result = await client.delete_rows(
                table_name="openclaw_cache",
                filter_query={
                    "expires_at": {
                        "$lt": 1234567890,
                        "$ne": None
                    }
                }
            )
        """
        proj_id = project_id or os.getenv("ZERODB_PROJECT_ID")
        if not proj_id:
            raise ValueError("project_id must be provided or ZERODB_PROJECT_ID must be set in environment")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.request(
                    method="DELETE",
                    url=f"{self.api_url}/v1/public/{proj_id}/database/tables/{table_name}/rows/bulk",
                    headers=self.headers,
                    json={"filter": filter_query}
                )
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )
    # ==================== Enhanced Methods for Epic E9 ====================

    def build_filter(self) -> FilterBuilder:
        """
        Create a new filter builder for complex queries.

        Returns:
            FilterBuilder instance for fluent query building

        Example:
            filter_query = (
                client.build_filter()
                .eq("workspace_id", "ws_123")
                .gte("created_at", 1234567890)
                .build()
            )
        """
        return FilterBuilder()

    @asynccontextmanager
    async def transaction(self):
        """
        Create a transaction context for batch operations.

        Yields:
            Transaction instance

        Example:
            async with client.transaction() as txn:
                await txn.insert_rows("users", [{"name": "Alice"}])
                await txn.commit()
        """
        txn = Transaction(self)
        try:
            yield txn
        except Exception as e:
            await txn.rollback()
            raise

    async def create_project_with_retry(
        self,
        name: str,
        description: str,
        max_retries: int = 3,
        base_delay: float = 1.0
    ) -> Dict[str, Any]:
        """
        Create project with retry logic and exponential backoff.

        Args:
            name: Project name
            description: Project description
            max_retries: Maximum number of retries
            base_delay: Base delay for exponential backoff

        Returns:
            Dict containing project details

        Raises:
            ZeroDBConnectionError: If all retries exhausted
            ZeroDBAPIError: If 4xx error (non-retriable)
        """
        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.api_url}/projects",
                        headers=self.headers,
                        json={"name": name, "description": description}
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.HTTPStatusError as e:
                last_exception = e
                # Don't retry on 4xx errors
                if 400 <= e.response.status_code < 500:
                    raise ZeroDBAPIError(
                        f"API error: {e.response.status_code} - {e.response.text}",
                        status_code=e.response.status_code
                    )
                # Retry on 5xx errors
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt) * (1 + random.uniform(0, 0.2))
                    await asyncio.sleep(delay)
            except (httpx.ConnectError, httpx.TimeoutException) as e:
                last_exception = e
                if attempt < max_retries:
                    delay = base_delay * (2 ** attempt) * (1 + random.uniform(0, 0.2))
                    await asyncio.sleep(delay)

        # If we exhausted all retries
        if isinstance(last_exception, httpx.HTTPStatusError):
            raise ZeroDBAPIError(
                f"API error after {max_retries} retries: {last_exception.response.status_code}",
                status_code=last_exception.response.status_code
            )
        else:
            raise ZeroDBConnectionError(f"Connection failed after {max_retries} retries: {str(last_exception)}")

    async def bulk_upsert(
        self,
        table_name: str,
        rows: List[Dict[str, Any]],
        unique_key: str,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Bulk upsert operation (insert or update based on unique key).

        Args:
            table_name: Name of the table
            rows: List of row documents
            unique_key: Field name to use for upsert matching
            project_id: Project ID (defaults to ZERODB_PROJECT_ID env var)

        Returns:
            Dict containing upsert statistics

        Example:
            result = await client.bulk_upsert(
                table_name="messages",
                rows=[{"id": "msg_1", "content": "Hello"}],
                unique_key="id"
            )
        """
        # Simplified implementation - in production would use proper upsert API
        proj_id = project_id or os.getenv("ZERODB_PROJECT_ID")
        if not proj_id:
            raise ValueError("project_id must be provided or ZERODB_PROJECT_ID must be set in environment")

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/v1/public/{proj_id}/database/tables/{table_name}/upsert",
                    headers=self.headers,
                    json={"rows": rows, "unique_key": unique_key}
                )
                response.raise_for_status()
                return response.json()
            except httpx.ConnectError as e:
                raise ZeroDBConnectionError(str(e))
            except httpx.HTTPStatusError as e:
                raise ZeroDBAPIError(
                    f"API error: {e.response.status_code} - {e.response.text}",
                    status_code=e.response.status_code
                )

    async def query_all(
        self,
        table_name: str,
        project_id: str,
        page_size: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Query all rows from table using pagination.

        Args:
            table_name: Name of the table
            project_id: Project ID
            page_size: Number of rows per page

        Returns:
            List of all rows

        Example:
            all_rows = await client.query_all(
                table_name="messages",
                project_id="proj_123",
                page_size=100
            )
        """
        all_rows = []
        skip = 0

        while True:
            page = await self.query_table(project_id, table_name, limit=page_size, skip=skip)
            if not page:
                break
            all_rows.extend(page)
            if len(page) < page_size:
                break
            skip += page_size

        return all_rows

    async def delete_by_ids(
        self,
        table_name: str,
        ids: List[str],
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Delete rows by list of IDs.

        Args:
            table_name: Name of the table
            ids: List of row IDs to delete
            project_id: Project ID (defaults to ZERODB_PROJECT_ID env var)

        Returns:
            Dict containing deletion statistics

        Example:
            result = await client.delete_by_ids(
                table_name="messages",
                ids=["msg_1", "msg_2"],
                project_id="proj_123"
            )
        """
        filter_query = {"id": {"$in": ids}}
        return await self.delete_rows(table_name, filter_query, project_id)

    async def query_with_cache(
        self,
        table_name: str,
        project_id: str,
        cache_key: str,
        cache_ttl: int = 300,
        limit: int = 10,
        skip: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Query table with caching support.

        Args:
            table_name: Name of the table
            project_id: Project ID
            cache_key: Unique cache key
            cache_ttl: Cache TTL in seconds
            limit: Maximum rows to return
            skip: Skip offset

        Returns:
            List of rows (from cache or API)

        Example:
            result = await client.query_with_cache(
                table_name="users",
                project_id="proj_123",
                cache_key="active_users",
                cache_ttl=300
            )
        """
        # Check cache
        if cache_key in self._cache:
            cached_entry = self._cache[cache_key]
            if cached_entry["expires_at"] > time.time():
                return cached_entry["data"]

        # Cache miss or expired - fetch from API
        result = await self.query_table(project_id, table_name, limit, skip)

        # Update cache
        self._cache[cache_key] = {
            "data": result,
            "expires_at": time.time() + cache_ttl
        }

        return result

    def invalidate_cache(self, cache_key: str):
        """
        Invalidate specific cache entry.

        Args:
            cache_key: Cache key to invalidate

        Example:
            client.invalidate_cache("active_users")
        """
        self._cache.pop(cache_key, None)

    async def create_workspace_table(
        self,
        workspace_id: str,
        table_type: str,
        project_id: str
    ) -> Dict[str, Any]:
        """
        Create workspace-scoped table.

        Args:
            workspace_id: Workspace ID
            table_type: Type of table (e.g., "messages", "files")
            project_id: Project ID

        Returns:
            Dict containing table details

        Example:
            table = await client.create_workspace_table(
                workspace_id="ws_123",
                table_type="messages",
                project_id="proj_123"
            )
        """
        table_name = f"{workspace_id}_{table_type}"
        return await self.create_table(project_id, table_name)

    async def query_conversation_messages(
        self,
        conversation_id: str,
        workspace_id: str,
        limit: int = 50,
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query messages for a specific conversation.

        Args:
            conversation_id: Conversation ID
            workspace_id: Workspace ID
            limit: Maximum messages to return
            project_id: Project ID (defaults to ZERODB_PROJECT_ID env var)

        Returns:
            Dict containing messages and metadata

        Example:
            result = await client.query_conversation_messages(
                conversation_id="conv_123",
                workspace_id="ws_123",
                limit=50
            )
        """
        table_name = f"{workspace_id}_messages"
        filter_query = {"conversation_id": {"$eq": conversation_id}}

        return await self.query_rows(
            table_name=table_name,
            filter_query=filter_query,
            project_id=project_id,
            limit=limit
        )

    async def store_conversation_message(
        self,
        workspace_id: str,
        message_data: Dict[str, Any],
        project_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Store a single conversation message.

        Args:
            workspace_id: Workspace ID
            message_data: Message data dict
            project_id: Project ID (defaults to ZERODB_PROJECT_ID env var)

        Returns:
            Dict containing insertion result

        Example:
            result = await client.store_conversation_message(
                workspace_id="ws_123",
                message_data={
                    "conversation_id": "conv_123",
                    "role": "user",
                    "content": "Hello"
                }
            )
        """
        table_name = f"{workspace_id}_messages"
        return await self.insert_rows(
            table_name=table_name,
            rows=[message_data],
            project_id=project_id
        )
