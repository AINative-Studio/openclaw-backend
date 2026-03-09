"""
Pydantic schemas for Conversation API (Issue #108)

Request/response models for conversation management and message retrieval.
"""

from pydantic import BaseModel, Field, ConfigDict
from uuid import UUID
from datetime import datetime
from typing import Optional, List


class ConversationResponse(BaseModel):
    """Response schema for a single conversation (Issue #103 multi-channel support)."""

    model_config = ConfigDict(
        from_attributes=True,
        json_schema_extra={
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
                "agent_swarm_instance_id": "456e4567-e89b-12d3-a456-426614174222",
                "user_id": "987e4567-e89b-12d3-a456-426614174333",
                "channel": "whatsapp",
                "channel_conversation_id": "whatsapp_123456",
                "title": "Customer Support Chat",
                "created_at": "2024-01-15T10:00:00Z",
                "updated_at": "2024-01-15T10:30:00Z",
                "archived_at": None,
                "status": "ACTIVE",
                "conversation_metadata": {}
            }
        }
    )

    id: UUID
    workspace_id: UUID
    agent_swarm_instance_id: Optional[UUID] = None  # Nullable as per Issue #103
    user_id: UUID  # Required as per Issue #103
    channel: str  # Multi-channel support (whatsapp, telegram, slack, etc.)
    channel_conversation_id: str  # External conversation ID
    title: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    status: str  # ACTIVE, ARCHIVED, DELETED
    conversation_metadata: dict = Field(default_factory=dict)  # Replaces old metadata pattern


class ConversationListResponse(BaseModel):
    """Response schema for listing conversations with pagination."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversations": [
                    {
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
                        "agent_id": "456e4567-e89b-12d3-a456-426614174222",
                        "user_id": "987e4567-e89b-12d3-a456-426614174333",
                        "openclaw_session_key": "session_abc123",
                        "started_at": "2024-01-15T10:00:00Z",
                        "last_message_at": "2024-01-15T10:30:00Z",
                        "message_count": 5,
                        "status": "active"
                    }
                ],
                "total": 1,
                "limit": 50,
                "offset": 0
            }
        }
    )

    conversations: List[ConversationResponse]
    total: int
    limit: int
    offset: int


class MessageResponse(BaseModel):
    """Response schema for a single message."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "user",
                "content": "Hello, AI!",
                "timestamp": "2024-01-15T10:00:00Z",
                "metadata": {}
            }
        }
    )

    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., description="Message content")
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    metadata: dict = Field(default_factory=dict, description="Additional message metadata")


class MessageListResponse(BaseModel):
    """Response schema for listing messages."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "messages": [
                    {
                        "role": "user",
                        "content": "Hello, AI!",
                        "timestamp": "2024-01-15T10:00:00Z",
                        "metadata": {}
                    },
                    {
                        "role": "assistant",
                        "content": "Hello! How can I help you?",
                        "timestamp": "2024-01-15T10:00:05Z",
                        "metadata": {}
                    }
                ],
                "total": 2
            }
        }
    )

    messages: List[MessageResponse]
    total: int


class SearchRequest(BaseModel):
    """Request schema for semantic search."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "machine learning concepts",
                "limit": 5
            }
        }
    )

    query: str = Field(..., min_length=1, description="Search query string")
    limit: Optional[int] = Field(5, ge=1, le=50, description="Maximum number of results")


class SearchResultsResponse(BaseModel):
    """Response schema for search results."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "results": {
                    "matches": [
                        {
                            "content": "Machine learning is a subset of AI...",
                            "score": 0.95,
                            "timestamp": "2024-01-15T10:00:00Z"
                        }
                    ],
                    "query": "machine learning concepts",
                    "total_matches": 1
                }
            }
        }
    )

    results: dict = Field(..., description="Search results with matches and metadata")


class CreateConversationRequest(BaseModel):
    """Request schema for creating a new conversation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "456e4567-e89b-12d3-a456-426614174222",
                "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
                "user_id": "987e4567-e89b-12d3-a456-426614174333"
            }
        }
    )

    agent_id: UUID = Field(..., description="ID of the agent for this conversation")
    workspace_id: UUID = Field(..., description="ID of the workspace")
    user_id: Optional[UUID] = Field(None, description="Optional user ID")


class AddMessageRequest(BaseModel):
    """Request schema for adding a message to a conversation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "user",
                "content": "Hello, AI!",
                "metadata": {}
            }
        }
    )

    role: str = Field(..., description="Message role (user, assistant, system)")
    content: str = Field(..., min_length=1, description="Message content")
    metadata: dict = Field(default_factory=dict, description="Optional message metadata")


class ConversationContextResponse(BaseModel):
    """Response schema for conversation context (formatted for LLM)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
                "messages": [
                    {"role": "user", "content": "Hello"},
                    {"role": "assistant", "content": "Hi there!"}
                ],
                "total_messages": 2,
                "agent_id": "456e4567-e89b-12d3-a456-426614174222",
                "metadata": {"model": "claude-3-opus"}
            }
        }
    )

    conversation_id: str = Field(..., description="Conversation UUID as string")
    messages: List[dict] = Field(..., description="List of messages in conversation")
    total_messages: int = Field(..., description="Total number of messages")
    agent_id: Optional[str] = Field(None, description="Agent UUID as string")
    metadata: dict = Field(default_factory=dict, description="Additional conversation metadata")


class AttachAgentRequest(BaseModel):
    """Request schema for attaching an agent to a conversation."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "agent_id": "456e4567-e89b-12d3-a456-426614174222"
            }
        }
    )

    agent_id: UUID = Field(..., description="UUID of the agent to attach")
