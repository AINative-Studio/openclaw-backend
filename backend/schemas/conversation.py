"""
Pydantic schemas for Conversation API (Issue #108)

Request/response models for conversation management and message retrieval.

Security: Issue #131 - Comprehensive input validation and XSS prevention
"""

from pydantic import BaseModel, Field, ConfigDict, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional, List, Literal
import re
from backend.validators import sanitize_html, validate_safe_json_metadata


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
    channel: Literal["whatsapp", "telegram", "slack", "email", "zalo", "discord"] = Field(
        ...,
        description="Channel type (enforced enum for security)"
    )
    channel_conversation_id: str = Field(
        ...,
        max_length=255,
        description="External conversation ID"
    )
    title: Optional[str] = Field(None, max_length=500)
    created_at: datetime
    updated_at: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    status: Literal["ACTIVE", "ARCHIVED", "DELETED"] = Field(
        ...,
        description="Conversation status (enforced enum)"
    )
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
    """
    Request schema for semantic search with SQL injection protection (Issue #128).

    Security Features:
        - Maximum query length of 200 characters
        - Blocks dangerous SQL keywords (UNION, SELECT, INSERT, etc.)
        - Blocks SQL comment sequences (--, /*, */)
        - Blocks semicolons to prevent query chaining
        - Strips leading/trailing whitespace
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "machine learning concepts",
                "limit": 5
            }
        }
    )

    query: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Search query string (max 200 chars, SQL keywords blocked)"
    )
    limit: Optional[int] = Field(
        5,
        ge=1,
        le=50,
        description="Maximum number of results"
    )

    @field_validator('query')
    @classmethod
    def validate_query_safety(cls, v: str) -> str:
        """
        Validate search query to prevent SQL injection attacks (Issue #128).

        Blocks:
            - SQL keywords: UNION, SELECT, INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, EXEC, EXECUTE
            - SQL comment sequences: --, /*, */
            - Semicolons (query chaining)
            - Control characters

        Args:
            v: Raw query string

        Returns:
            Sanitized query string (stripped whitespace)

        Raises:
            ValueError: If query contains forbidden SQL keywords or patterns
        """
        # Strip leading/trailing whitespace
        v = v.strip()

        # Check for dangerous SQL keywords (case-insensitive)
        dangerous_keywords = [
            'UNION', 'SELECT', 'INSERT', 'UPDATE', 'DELETE',
            'DROP', 'CREATE', 'ALTER', 'EXEC', 'EXECUTE',
            'SCRIPT', 'JAVASCRIPT', 'EVAL', 'EXPRESSION'
        ]

        query_upper = v.upper()
        for keyword in dangerous_keywords:
            if keyword in query_upper:
                raise ValueError(
                    f"Query contains forbidden SQL keyword: {keyword}. "
                    f"Please use plain text search terms only."
                )

        # Block SQL comment sequences
        if '--' in v or '/*' in v or '*/' in v:
            raise ValueError(
                "Query contains SQL comment sequences (-- or /* */). "
                "Please use plain text search terms only."
            )

        # Block semicolons (query chaining)
        if ';' in v:
            raise ValueError(
                "Query contains semicolon which is not allowed. "
                "Please use plain text search terms only."
            )

        # Block null bytes and control characters (except newline, tab, space)
        if re.search(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', v):
            raise ValueError(
                "Query contains invalid control characters. "
                "Please use plain text search terms only."
            )

        return v


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
    """
    Request schema for adding a message to a conversation.

    Security: Issue #131 - Sanitizes HTML/XSS from content, validates metadata depth
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "role": "user",
                "content": "Hello, AI!",
                "metadata": {}
            }
        }
    )

    role: Literal["user", "assistant", "system"] = Field(
        ...,
        description="Message role (enforced enum for security)"
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=50000,
        description="Message content (XSS sanitized)"
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Optional message metadata (validated depth/size)"
    )

    @field_validator('content')
    @classmethod
    def sanitize_content(cls, v: str) -> str:
        """Sanitize message content to prevent XSS attacks (Issue #131)."""
        return sanitize_html(v)

    @field_validator('metadata')
    @classmethod
    def validate_metadata(cls, v: dict) -> dict:
        """
        Validate metadata structure to prevent DoS attacks (Issue #131).

        Enforces:
            - Max depth: 3 levels
            - Max keys: 50 total
            - Max string length: 1000 chars
            - No dangerous keys (__proto__, eval, etc.)
        """
        return validate_safe_json_metadata(v, max_depth=3, max_keys=50, max_value_length=1000)


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
