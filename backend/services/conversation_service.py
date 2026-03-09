"""
ConversationService - Manage conversations with dual ZeroDB storage

This service handles conversation lifecycle and message management with
integrated ZeroDB storage for both structured queries and semantic search.

Key Features:
- Dual storage: ZeroDB tables (pagination) + Memory API (semantic search)
- Workspace-level isolation with ZeroDB project mapping
- Message metadata tracking (count, timestamps)
- Conversation archival and listing with filters
- Graceful degradation on memory storage failures

Architecture:
- PostgreSQL: Conversation metadata (workspace, agent, user, status, counts)
- ZeroDB Table: Message rows for pagination and retrieval
- ZeroDB Memory: Message embeddings for semantic search

Usage:
    async with AsyncSession() as db:
        async with ZeroDBClient(api_key="...") as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)
            conv = await service.create_conversation(
                workspace_id=workspace_id,
                agent_id=agent_id,
                user_id=user_id,
                openclaw_session_key="session_abc"
            )
            msg = await service.add_message(
                conversation_id=conv.id,
                role="user",
                content="Hello"
            )
"""

from typing import List, Dict, Any, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.models.conversation import Conversation
from backend.models.workspace import Workspace
from backend.integrations.zerodb_client import (
    ZeroDBClient,
    ZeroDBConnectionError,
    ZeroDBAPIError
)


class ConversationService:
    """
    Service for managing conversations with ZeroDB integration.

    Provides CRUD operations for conversations and dual-storage message management
    using both ZeroDB tables (for structured queries) and Memory API (for semantic search).
    """

    def __init__(self, db: AsyncSession, zerodb_client: ZeroDBClient):
        """
        Initialize ConversationService.

        Args:
            db: Async SQLAlchemy database session
            zerodb_client: ZeroDB API client for message storage
        """
        self.db = db
        self.zerodb = zerodb_client

    async def create_conversation(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        user_id: UUID,
        openclaw_session_key: str
    ) -> Conversation:
        """
        Create a new conversation.

        Validates workspace has ZeroDB project before creating conversation.

        Args:
            workspace_id: Workspace UUID
            agent_id: Agent UUID
            user_id: User UUID
            openclaw_session_key: OpenClaw session identifier

        Returns:
            Created Conversation instance

        Raises:
            ValueError: If workspace not found or missing zerodb_project_id
        """
        try:
            # Validate workspace exists and has ZeroDB project
            stmt = select(Workspace).where(Workspace.id == workspace_id)
            result = await self.db.execute(stmt)
            workspace = result.scalar_one_or_none()

            if not workspace:
                raise ValueError(f"Workspace {workspace_id} not found")

            if not workspace.zerodb_project_id:
                raise ValueError(
                    f"Workspace {workspace_id} does not have a ZeroDB project configured"
                )

            # Create conversation
            conversation = Conversation(
                workspace_id=workspace_id,
                agent_id=agent_id,
                user_id=user_id,
                openclaw_session_key=openclaw_session_key,
                status="active",
                message_count=0
            )

            self.db.add(conversation)
            await self.db.commit()
            await self.db.refresh(conversation)

            return conversation

        except Exception as e:
            await self.db.rollback()
            raise

    async def get_conversation(
        self,
        conversation_id: UUID
    ) -> Optional[Conversation]:
        """
        Retrieve conversation by ID.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Conversation if found, None otherwise
        """
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_conversation_by_session_key(
        self,
        session_key: str
    ) -> Optional[Conversation]:
        """
        Retrieve conversation by OpenClaw session key.

        Args:
            session_key: OpenClaw session identifier

        Returns:
            Conversation if found, None otherwise
        """
        stmt = select(Conversation).where(
            Conversation.openclaw_session_key == session_key
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def add_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Add a message to conversation with dual storage.

        Stores message in both:
        1. ZeroDB table row (for pagination/retrieval)
        2. ZeroDB Memory API (for semantic search)

        Updates conversation metadata (message_count, last_message_at).

        Args:
            conversation_id: Conversation UUID
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional additional metadata

        Returns:
            Dict with message details:
                - id: Table row ID
                - memory_id: Memory API ID (or None if memory storage failed)
                - conversation_id: Conversation UUID
                - role: Message role
                - content: Message content
                - timestamp: ISO 8601 timestamp

        Raises:
            ValueError: If conversation not found
            ZeroDBConnectionError: If ZeroDB connection fails
            ZeroDBAPIError: If table storage fails (memory failure is graceful)
        """
        # Fetch conversation with workspace
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Prepare message data
        timestamp = datetime.now(timezone.utc).isoformat()
        message_data = {
            "conversation_id": str(conversation_id),
            "role": role,
            "content": content,
            "timestamp": timestamp
        }

        if metadata:
            message_data["metadata"] = metadata

        # Storage 1: ZeroDB table row (required - fail if this fails)
        table_row = await self.zerodb.create_table_row(
            project_id=conversation.workspace.zerodb_project_id,
            table_name="messages",
            row_data=message_data
        )

        # Storage 2: ZeroDB Memory API (optional - graceful degradation)
        memory_id = None
        try:
            memory = await self.zerodb.create_memory(
                title=f"Message in conversation {conversation_id}",
                content=content,
                type="conversation",
                tags=[str(conversation_id), role],
                metadata={
                    "conversation_id": str(conversation_id),
                    "role": role,
                    "timestamp": timestamp,
                    **(metadata or {})
                }
            )
            memory_id = memory.get("id")
        except (ZeroDBConnectionError, ZeroDBAPIError):
            # Graceful degradation - continue without semantic search capability
            pass

        # Update conversation metadata
        conversation.message_count += 1
        conversation.last_message_at = datetime.now(timezone.utc)
        await self.db.commit()

        return {
            "id": table_row.get("id"),
            "memory_id": memory_id,
            "conversation_id": str(conversation_id),
            "role": role,
            "content": content,
            "timestamp": timestamp
        }

    async def get_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Retrieve messages from conversation with pagination.

        Queries ZeroDB table for message rows.

        Args:
            conversation_id: Conversation UUID
            limit: Maximum messages to return (default: 50)
            offset: Number of messages to skip (default: 0)

        Returns:
            List of message dictionaries with fields:
                - id: Message ID
                - role: Message role
                - content: Message content
                - timestamp: ISO 8601 timestamp
                - metadata: Optional metadata

        Raises:
            ValueError: If conversation not found
            ZeroDBConnectionError: If ZeroDB connection fails
            ZeroDBAPIError: If query fails
        """
        # Fetch conversation with workspace
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Query ZeroDB table
        messages = await self.zerodb.query_table(
            project_id=conversation.workspace.zerodb_project_id,
            table_name="messages",
            limit=limit,
            skip=offset
        )

        return messages

    async def search_conversation_semantic(
        self,
        conversation_id: UUID,
        query: str,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Search conversation messages using semantic similarity.

        Uses ZeroDB Memory API for vector-based semantic search.
        Filters results to only include messages from this conversation.

        Args:
            conversation_id: Conversation UUID
            query: Search query text
            limit: Maximum results to return (default: 5)

        Returns:
            Dict with search results:
                - results: List of matching messages with scores
                - total: Number of results after filtering
                - query: Original search query

        Raises:
            ValueError: If conversation not found
            ZeroDBConnectionError: If ZeroDB connection fails
            ZeroDBAPIError: If search fails
        """
        # Validate conversation exists
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Search memories
        search_results = await self.zerodb.search_memories(
            query=query,
            limit=limit,
            type="conversation"
        )

        # Filter results to only this conversation
        conversation_id_str = str(conversation_id)
        filtered_results = [
            result for result in search_results.get("results", [])
            if result.get("metadata", {}).get("conversation_id") == conversation_id_str
        ]

        return {
            "results": filtered_results,
            "total": len(filtered_results),
            "query": query
        }

    async def archive_conversation(
        self,
        conversation_id: UUID
    ) -> Conversation:
        """
        Archive a conversation.

        Sets status to 'archived' and records archive timestamp.
        Idempotent - archiving already archived conversation has no effect.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Updated Conversation instance

        Raises:
            ValueError: If conversation not found
        """
        stmt = select(Conversation).where(Conversation.id == conversation_id)
        result = await self.db.execute(stmt)
        conversation = result.scalar_one_or_none()

        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        # Idempotent - only update if not already archived
        if conversation.status != "archived":
            conversation.status = "archived"
            conversation.archived_at = datetime.now(timezone.utc)
            await self.db.commit()

        return conversation

    async def list_conversations(
        self,
        workspace_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Conversation], int]:
        """
        List conversations with optional filters and pagination.

        Args:
            workspace_id: Optional workspace filter
            agent_id: Optional agent filter
            status: Optional status filter (active, archived)
            limit: Maximum conversations to return (default: 50)
            offset: Number of conversations to skip (default: 0)

        Returns:
            Tuple of (conversations list, total count)
        """
        # Build base query
        stmt = select(Conversation)

        # Apply filters
        if workspace_id:
            stmt = stmt.where(Conversation.workspace_id == workspace_id)
        if agent_id:
            stmt = stmt.where(Conversation.agent_id == agent_id)
        if status:
            stmt = stmt.where(Conversation.status == status)

        # Order by most recent first
        stmt = stmt.order_by(Conversation.started_at.desc())

        # Count query (before pagination)
        count_stmt = select(func.count()).select_from(stmt.subquery())
        count_result = await self.db.execute(count_stmt)
        total = count_result.scalar()

        # Apply pagination
        stmt = stmt.limit(limit).offset(offset)

        # Execute query
        result = await self.db.execute(stmt)
        conversations = result.scalars().all()

        return list(conversations), total
