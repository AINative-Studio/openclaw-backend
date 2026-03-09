"""
Conversation API Endpoints (Issue #108)

REST API for managing conversations and retrieving messages.
Integrates with ConversationService for business logic and ZeroDB for message storage.

Endpoints:
    GET    /conversations                           - List conversations with filters
    GET    /conversations/{conversation_id}         - Retrieve single conversation
    GET    /conversations/{conversation_id}/messages - Retrieve conversation messages
    POST   /conversations/{conversation_id}/search   - Semantic search in conversation
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from typing import Optional
from datetime import datetime, timezone
import os

from backend.db.base import get_async_db
from backend.schemas.conversation import (
    ConversationListResponse,
    ConversationResponse,
    MessageListResponse,
    MessageResponse,
    SearchRequest,
    SearchResultsResponse,
    CreateConversationRequest,
    AddMessageRequest,
    ConversationContextResponse,
    AttachAgentRequest,
)


router = APIRouter(prefix="/conversations", tags=["Conversations"])


async def get_conversation_service(db: AsyncSession = Depends(get_async_db)):
    """
    Dependency to create ConversationService instance.

    Initializes ConversationService with database session.
    Uses PostgreSQL for message storage (ZeroDB integration optional).

    Args:
        db: Async SQLAlchemy database session

    Returns:
        ConversationService instance

    Raises:
        HTTPException: If service cannot be initialized
    """
    try:
        from backend.services.conversation_service_pg import ConversationServicePG

        service = ConversationServicePG(db=db)
        yield service
    except ImportError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"ConversationService dependencies not available: {str(e)}"
        )


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    agent_id: Optional[UUID] = Query(None, description="Filter by agent ID"),
    workspace_id: Optional[UUID] = Query(None, description="Filter by workspace ID"),
    status: Optional[str] = Query(None, description="Filter by conversation status"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of results"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    service = Depends(get_conversation_service)
):
    """
    List conversations with optional filters and pagination.

    Supports filtering by:
    - agent_id: Show conversations for specific agent
    - workspace_id: Show conversations for specific workspace
    - status: Filter by conversation status (active, archived, etc.)

    Pagination:
    - limit: Number of results per page (1-200, default 50)
    - offset: Number of results to skip (default 0)

    Args:
        agent_id: Optional agent UUID filter
        workspace_id: Optional workspace UUID filter
        status: Optional status filter
        limit: Results per page
        offset: Results to skip
        service: ConversationService dependency

    Returns:
        ConversationListResponse with conversations, total count, and pagination info

    Example:
        GET /conversations?workspace_id=123e4567-e89b-12d3-a456-426614174000&limit=10&offset=0
    """
    conversations, total = await service.list_conversations(
        agent_id=agent_id,
        workspace_id=workspace_id,
        status=status,
        limit=limit,
        offset=offset
    )

    return ConversationListResponse(
        conversations=[ConversationResponse.model_validate(conv) for conv in conversations],
        total=total,
        limit=limit,
        offset=offset
    )


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    service = Depends(get_conversation_service)
):
    """
    Retrieve a single conversation by ID.

    Args:
        conversation_id: UUID of the conversation
        service: ConversationService dependency

    Returns:
        ConversationResponse with conversation details

    Raises:
        404: If conversation not found

    Example:
        GET /conversations/123e4567-e89b-12d3-a456-426614174000
    """
    conversation = await service.get_conversation(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID '{conversation_id}' not found"
        )

    return ConversationResponse.model_validate(conversation)


@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="Maximum number of messages"),
    offset: int = Query(0, ge=0, description="Number of messages to skip"),
    service = Depends(get_conversation_service)
):
    """
    Retrieve messages from a conversation with pagination.

    Messages are retrieved from ZeroDB and returned in chronological order.

    Pagination:
    - limit: Number of messages per page (1-200, default 50)
    - offset: Number of messages to skip (default 0)

    Args:
        conversation_id: UUID of the conversation
        limit: Messages per page
        offset: Messages to skip
        service: ConversationService dependency

    Returns:
        MessageListResponse with messages and total count

    Example:
        GET /conversations/123e4567-e89b-12d3-a456-426614174000/messages?limit=20&offset=0
    """
    messages = await service.get_messages(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset
    )

    # Get total message count (message_count field removed in Issue #103 migration)
    total = await service.get_message_count(conversation_id)

    return MessageListResponse(
        messages=messages,
        total=total
    )


@router.post("/{conversation_id}/search", response_model=SearchResultsResponse)
async def search_conversation(
    conversation_id: UUID,
    request: SearchRequest,
    service = Depends(get_conversation_service)
):
    """
    Perform semantic search within a conversation.

    Uses ZeroDB vector search to find relevant messages based on semantic similarity.

    Args:
        conversation_id: UUID of the conversation
        request: SearchRequest with query and optional limit
        service: ConversationService dependency

    Returns:
        SearchResultsResponse with matching messages and relevance scores

    Example:
        POST /conversations/123e4567-e89b-12d3-a456-426614174000/search
        {
            "query": "machine learning concepts",
            "limit": 5
        }
    """
    result = await service.search_conversation_semantic(
        conversation_id=conversation_id,
        query=request.query,
        limit=request.limit or 5
    )

    return SearchResultsResponse(results=result)


@router.post("", response_model=ConversationResponse, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    request: CreateConversationRequest,
    service = Depends(get_conversation_service)
):
    """
    Create a new conversation.

    Args:
        request: CreateConversationRequest with agent_id, workspace_id, and optional user_id
        service: ConversationService dependency

    Returns:
        ConversationResponse with newly created conversation

    Example:
        POST /conversations
        {
            "agent_id": "456e4567-e89b-12d3-a456-426614174222",
            "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
            "user_id": "987e4567-e89b-12d3-a456-426614174333"
        }
    """
    conversation = await service.create_conversation(
        workspace_id=request.workspace_id,
        agent_id=request.agent_id,
        user_id=request.user_id
    )

    return ConversationResponse.model_validate(conversation)


@router.post("/{conversation_id}/messages", response_model=MessageResponse, status_code=status.HTTP_201_CREATED)
async def add_message(
    conversation_id: UUID,
    request: AddMessageRequest,
    service = Depends(get_conversation_service)
):
    """
    Add a message to a conversation.

    Stores the message in ZeroDB and updates conversation metadata.

    Args:
        conversation_id: UUID of the conversation
        request: AddMessageRequest with role, content, and optional metadata
        service: ConversationService dependency

    Returns:
        MessageResponse with the added message

    Example:
        POST /conversations/123e4567-e89b-12d3-a456-426614174000/messages
        {
            "role": "user",
            "content": "Hello, AI!",
            "metadata": {}
        }
    """
    # Verify conversation exists
    conversation = await service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID '{conversation_id}' not found"
        )

    # Add message to ZeroDB
    await service.add_message(
        conversation_id=conversation_id,
        role=request.role,
        content=request.content,
        metadata=request.metadata
    )

    # Return the message that was added
    return MessageResponse(
        role=request.role,
        content=request.content,
        timestamp=datetime.now(timezone.utc).isoformat(),
        metadata=request.metadata
    )


@router.post("/{conversation_id}/archive", response_model=ConversationResponse)
async def archive_conversation(
    conversation_id: UUID,
    service = Depends(get_conversation_service)
):
    """
    Archive a conversation.

    Sets the conversation status to 'archived'. This is an idempotent operation -
    archiving an already archived conversation succeeds without error.

    Args:
        conversation_id: UUID of the conversation to archive
        service: ConversationService dependency

    Returns:
        ConversationResponse with updated status

    Raises:
        404: If conversation not found

    Example:
        POST /conversations/123e4567-e89b-12d3-a456-426614174000/archive
    """
    conversation = await service.archive_conversation(conversation_id)

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID '{conversation_id}' not found"
        )

    return ConversationResponse.model_validate(conversation)


@router.get("/{conversation_id}/context", response_model=ConversationContextResponse)
async def get_conversation_context(
    conversation_id: UUID,
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of messages to include"),
    service = Depends(get_conversation_service)
):
    """
    Get conversation context formatted for LLM consumption.

    Returns the conversation's message history formatted for use as context
    in LLM API calls. Includes conversation metadata and agent information.

    Args:
        conversation_id: UUID of the conversation
        limit: Maximum number of recent messages to include (1-1000, default 100)
        service: ConversationService dependency

    Returns:
        ConversationContextResponse with messages and metadata

    Raises:
        404: If conversation not found

    Example:
        GET /conversations/123e4567-e89b-12d3-a456-426614174000/context?limit=50
    """
    context = await service.get_conversation_context(
        conversation_id=conversation_id,
        limit=limit
    )

    if not context:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID '{conversation_id}' not found"
        )

    return ConversationContextResponse(**context)


@router.post("/{conversation_id}/attach-agent", response_model=ConversationResponse)
async def attach_agent_to_conversation(
    conversation_id: UUID,
    request: AttachAgentRequest,
    service = Depends(get_conversation_service)
):
    """
    Attach (or replace) an agent for a conversation.

    Updates the conversation's agent_id. This allows reassigning conversations
    to different agents or recovering from agent failures.

    Args:
        conversation_id: UUID of the conversation
        request: AttachAgentRequest with new agent_id
        service: ConversationService dependency

    Returns:
        ConversationResponse with updated agent_id

    Raises:
        404: If conversation not found

    Example:
        POST /conversations/123e4567-e89b-12d3-a456-426614174000/attach-agent
        {
            "agent_id": "456e4567-e89b-12d3-a456-426614174222"
        }
    """
    conversation = await service.attach_agent(
        conversation_id=conversation_id,
        agent_id=request.agent_id
    )

    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation with ID '{conversation_id}' not found"
        )

    return ConversationResponse.model_validate(conversation)
