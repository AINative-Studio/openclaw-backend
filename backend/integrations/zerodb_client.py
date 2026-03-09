"""
ZeroDBClient - Async HTTP client wrapper for ZeroDB API.

This module provides a high-level interface to interact with ZeroDB's
NoSQL database and memory storage APIs. All methods are async and use
httpx for HTTP communication.

Environment Variables:
    ZERODB_API_KEY: API key for authentication
    ZERODB_API_URL: Base URL for ZeroDB API (default: https://api.ainative.studio)

Usage:
    async with ZeroDBClient(api_key="your-key") as client:
        project = await client.create_project(name="MyProject", description="Test")
        rows = await client.query_table(project_id="proj_123", table_name="users", limit=10, skip=0)
"""

from typing import List, Dict, Any, Optional
import httpx
import os


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
        api_url: Optional[str] = None
    ):
        """
        Initialize ZeroDBClient.

        Args:
            api_key: ZeroDB API key for authentication (defaults to ZERODB_API_KEY env var)
            api_url: Base URL for ZeroDB API (defaults to ZERODB_API_URL env var or https://api.ainative.studio/v1)
        """
        self.api_key = api_key or os.getenv("ZERODB_API_KEY")
        self.api_url = api_url or os.getenv("ZERODB_API_URL", "https://api.ainative.studio/v1")

        if not self.api_key:
            raise ValueError("ZERODB_API_KEY must be provided or set in environment")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        self._client: Optional[httpx.AsyncClient] = None

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

        Example:
            project = await client.create_project(
                name="MyProject",
                description="Test project"
            )
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/projects",
                    headers=self.headers,
                    json={"name": name, "description": description}
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
                    f"{self.api_url}/public/{proj_id}/database/tables/{table_name}/query",
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
                    f"{self.api_url}/public/{proj_id}/database/tables/{table_name}/rows",
                    headers=self.headers,
                    json={"rows": rows}
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
                response = await client.patch(
                    f"{self.api_url}/public/{proj_id}/database/tables/{table_name}/rows",
                    headers=self.headers,
                    json={
                        "filter": filter_query,
                        "update": update_data
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
                    url=f"{self.api_url}/public/{proj_id}/database/tables/{table_name}/rows",
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
