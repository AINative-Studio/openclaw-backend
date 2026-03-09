"""
ConversationServicePG - PostgreSQL-based conversation and message management

Simple, immediate persistence using PostgreSQL only.
No ZeroDB dependency - messages persist across page refreshes.
"""

from typing import List, Optional, Tuple
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc

from backend.models.conversation import Conversation, ConversationStatus
from backend.models.message import Message
from backend.schemas.conversation import MessageResponse


class ConversationServicePG:
    """
    Service for managing conversations with PostgreSQL message storage.

    Provides immediate persistence without ZeroDB dependency.
    """

    def __init__(self, db: AsyncSession):
        """
        Initialize ConversationServicePG.

        Args:
            db: Async SQLAlchemy database session
        """
        self.db = db

    async def create_conversation(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        user_id: Optional[UUID] = None
    ) -> Conversation:
        """
        Create a new conversation.

        Args:
            workspace_id: Workspace UUID
            agent_id: Agent UUID (renamed to agent_swarm_instance_id in database)
            user_id: Optional user UUID

        Returns:
            Created Conversation instance
        """
        try:
            conversation = Conversation(
                workspace_id=workspace_id,
                agent_swarm_instance_id=agent_id,
                user_id=user_id,
                status=ConversationStatus.ACTIVE
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

    async def get_conversation_by_agent(
        self,
        agent_id: UUID
    ) -> Optional[Conversation]:
        """
        Retrieve the most recent active conversation for an agent.

        Args:
            agent_id: Agent UUID

        Returns:
            Most recent Conversation if found, None otherwise
        """
        stmt = (
            select(Conversation)
            .where(Conversation.agent_swarm_instance_id == agent_id)
            .where(Conversation.status == ConversationStatus.ACTIVE)
            .order_by(desc(Conversation.created_at))
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_conversations(
        self,
        agent_id: Optional[UUID] = None,
        workspace_id: Optional[UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Conversation], int]:
        """
        List conversations with filters and pagination.

        Args:
            agent_id: Optional agent filter
            workspace_id: Optional workspace filter
            status: Optional status filter
            limit: Results per page
            offset: Results to skip

        Returns:
            Tuple of (conversations list, total count)
        """
        query = select(Conversation)

        if agent_id:
            query = query.where(Conversation.agent_swarm_instance_id == agent_id)
        if workspace_id:
            query = query.where(Conversation.workspace_id == workspace_id)
        if status:
            query = query.where(Conversation.status == status)

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar()

        # Get paginated results
        query = query.order_by(desc(Conversation.created_at)).offset(offset).limit(limit)
        result = await self.db.execute(query)
        conversations = result.scalars().all()

        return conversations, total

    async def add_message(
        self,
        conversation_id: UUID,
        role: str,
        content: str,
        metadata: Optional[dict] = None
    ) -> Message:
        """
        Add a message to conversation.

        Stores message in PostgreSQL and updates conversation metadata.

        Args:
            conversation_id: Conversation UUID
            role: Message role (user, assistant, system)
            content: Message content
            metadata: Optional additional metadata

        Returns:
            Created Message instance

        Raises:
            ValueError: If conversation not found
        """
        # Verify conversation exists
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        try:
            # Create message
            message = Message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                message_metadata=metadata or {}
            )

            self.db.add(message)

            # Update conversation metadata (message_count and last_message_at removed in Issue #103 migration)
            conversation.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(message)

            return message

        except Exception as e:
            await self.db.rollback()
            raise

    async def get_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[MessageResponse]:
        """
        Retrieve messages from a conversation.

        Args:
            conversation_id: Conversation UUID
            limit: Maximum messages to return
            offset: Number of messages to skip

        Returns:
            List of MessageResponse objects
        """
        query = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at)
            .offset(offset)
            .limit(limit)
        )

        result = await self.db.execute(query)
        messages = result.scalars().all()

        return [
            MessageResponse(
                role=msg.role,
                content=msg.content,
                timestamp=msg.created_at.isoformat(),
                metadata=msg.message_metadata or {}
            )
            for msg in messages
        ]

    async def get_message_count(
        self,
        conversation_id: UUID
    ) -> int:
        """
        Get total message count for a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Total number of messages in conversation
        """
        query = select(func.count()).where(Message.conversation_id == conversation_id)
        result = await self.db.execute(query)
        return result.scalar() or 0

    async def search_conversation_semantic(
        self,
        conversation_id: UUID,
        query: str,
        limit: int = 5
    ) -> dict:
        """
        Search for messages in a conversation.

        Note: This is a simple text search. Full semantic search would require ZeroDB.

        Args:
            conversation_id: Conversation UUID
            query: Search query string
            limit: Maximum results

        Returns:
            Dict with search results
        """
        # Simple text search (case-insensitive LIKE)
        stmt = (
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .where(Message.content.ilike(f"%{query}%"))
            .order_by(desc(Message.created_at))
            .limit(limit)
        )

        result = await self.db.execute(stmt)
        messages = result.scalars().all()

        return {
            "matches": [
                {
                    "content": msg.content,
                    "score": 1.0,  # Placeholder score
                    "timestamp": msg.created_at.isoformat()
                }
                for msg in messages
            ],
            "query": query,
            "total_matches": len(messages)
        }

    async def archive_conversation(
        self,
        conversation_id: UUID
    ) -> Optional[Conversation]:
        """
        Archive a conversation.

        Args:
            conversation_id: Conversation UUID

        Returns:
            Archived Conversation if found, None otherwise
        """
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            return None

        try:
            conversation.archive()  # Uses model method to set status and archived_at
            await self.db.commit()
            await self.db.refresh(conversation)
            return conversation

        except Exception as e:
            await self.db.rollback()
            raise

    async def get_conversation_context(
        self,
        conversation_id: UUID,
        limit: int = 100
    ) -> Optional[dict]:
        """
        Get conversation context formatted for LLM consumption.

        Args:
            conversation_id: Conversation UUID
            limit: Maximum number of recent messages to include

        Returns:
            Dict with messages and metadata, None if conversation not found
        """
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            return None

        messages = await self.get_messages(
            conversation_id=conversation_id,
            limit=limit,
            offset=0
        )

        return {
            "conversation_id": str(conversation.id),
            "agent_id": str(conversation.agent_swarm_instance_id) if conversation.agent_swarm_instance_id else None,
            "workspace_id": str(conversation.workspace_id),
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp
                }
                for msg in messages
            ],
            "metadata": conversation.conversation_metadata or {}
        }

    async def attach_agent(
        self,
        conversation_id: UUID,
        agent_id: UUID
    ) -> Optional[Conversation]:
        """
        Attach (or replace) an agent for a conversation.

        Args:
            conversation_id: Conversation UUID
            agent_id: Agent UUID to attach

        Returns:
            Updated Conversation if found, None otherwise
        """
        conversation = await self.get_conversation(conversation_id)
        if not conversation:
            return None

        try:
            conversation.agent_swarm_instance_id = agent_id
            conversation.updated_at = datetime.now(timezone.utc)
            await self.db.commit()
            await self.db.refresh(conversation)
            return conversation

        except Exception as e:
            await self.db.rollback()
            raise
