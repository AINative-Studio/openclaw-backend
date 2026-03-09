"""
Production OpenClaw Bridge Implementation

Implements IOpenClawBridge with robust error handling, retry logic, and monitoring.

Refs #1094
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
from uuid import UUID
import random
import sys
import os

# Add integrations directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'integrations'))

from openclaw_bridge import OpenClawBridge as BaseOpenClawBridge
from backend.agents.orchestration.openclaw_bridge_protocol import (
    IOpenClawBridge,
    BridgeConnectionState,
    ConnectionError,
    SendError,
    SessionError
)

# Optional imports for conversation persistence
try:
    from sqlalchemy.ext.asyncio import AsyncSession
    from backend.services.conversation_service import ConversationService
    from backend.integrations.zerodb_client import ZeroDBClient
    PERSISTENCE_AVAILABLE = True
except ImportError:
    PERSISTENCE_AVAILABLE = False
    AsyncSession = None
    ConversationService = None
    ZeroDBClient = None

logger = logging.getLogger(__name__)


class ProductionOpenClawBridge:
    """
    Production implementation of OpenClaw bridge with robust error handling

    Features:
    - Automatic retry with exponential backoff
    - Connection state management
    - Session key validation
    - Detailed logging and error handling
    - Message metadata support
    """

    def __init__(
        self,
        url: str,
        token: str,
        db: Optional['AsyncSession'] = None,
        zerodb_client: Optional['ZeroDBClient'] = None,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0
    ):
        """
        Initialize production bridge

        Args:
            url: OpenClaw Gateway WebSocket URL
            token: Authentication token
            db: Optional async database session for conversation persistence
            zerodb_client: Optional ZeroDB client for message storage
            max_retries: Maximum retry attempts
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
        """
        self._base_bridge = BaseOpenClawBridge(url=url, token=token)
        self._connection_state = BridgeConnectionState.DISCONNECTED
        self._max_retries = max_retries
        self._initial_delay = initial_delay
        self._max_delay = max_delay

        # Conversation persistence (optional)
        self._db = db
        self._zerodb = zerodb_client
        self._conversation_service = None

        # Initialize ConversationService if both dependencies provided
        if PERSISTENCE_AVAILABLE and db is not None and zerodb_client is not None:
            self._conversation_service = ConversationService(db=db, zerodb_client=zerodb_client)
            logger.info("ProductionOpenClawBridge initialized with conversation persistence enabled")
        else:
            logger.info("ProductionOpenClawBridge initialized without conversation persistence")

        logger.info(
            "ProductionOpenClawBridge initialized",
            extra={
                "url": url,
                "max_retries": max_retries,
                "persistence_enabled": self._conversation_service is not None
            }
        )

    @property
    def is_connected(self) -> bool:
        """Check if bridge is connected"""
        return self._base_bridge.is_connected

    @property
    def connection_state(self) -> BridgeConnectionState:
        """Get current connection state"""
        return self._connection_state

    async def connect(self) -> None:
        """Connect to OpenClaw Gateway with automatic retry"""
        self._connection_state = BridgeConnectionState.CONNECTING
        logger.info("Connecting to OpenClaw Gateway...")

        for attempt in range(self._max_retries):
            try:
                await self._base_bridge.connect()
                self._connection_state = BridgeConnectionState.CONNECTED
                logger.info(
                    "Connected to OpenClaw Gateway",
                    extra={"attempt": attempt + 1}
                )
                return

            except Exception as e:
                logger.warning(
                    f"Connection attempt {attempt + 1} failed: {e}",
                    extra={
                        "attempt": attempt + 1,
                        "max_retries": self._max_retries,
                        "error_type": type(e).__name__
                    }
                )

                if attempt < self._max_retries - 1:
                    delay = self._calculate_backoff(attempt)
                    logger.info(f"Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)
                else:
                    self._connection_state = BridgeConnectionState.FAILED
                    error_msg = f"Failed to connect after {self._max_retries} attempts"
                    logger.error(error_msg)
                    raise ConnectionError(error_msg) from e

    async def send_to_agent(
        self,
        session_key: str,
        message: str,
        agent_id: Optional[UUID] = None,
        user_id: Optional[UUID] = None,
        workspace_id: Optional[UUID] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send message to agent with retry and validation

        Optionally persists conversation to ZeroDB when agent_id, user_id, and workspace_id are provided.

        Args:
            session_key: Target session identifier
            message: Message content to send
            agent_id: Optional agent UUID for conversation tracking
            user_id: Optional user UUID for conversation tracking
            workspace_id: Optional workspace UUID for conversation context
            metadata: Optional metadata for routing/tracking

        Returns:
            Response dictionary with status and message details

        Raises:
            ConnectionError: If bridge is not connected
            SessionError: If session key is invalid
            SendError: If message delivery fails after retries
        """
        # Step 1: Get or create conversation (if IDs provided)
        conversation = None
        if self._conversation_service and agent_id and user_id and workspace_id:
            try:
                conversation = await self._conversation_service.get_conversation_by_session_key(session_key)
                if not conversation:
                    conversation = await self._conversation_service.create_conversation(
                        workspace_id=workspace_id,
                        agent_id=agent_id,
                        user_id=user_id,
                        openclaw_session_key=session_key
                    )
                    logger.info(f"Created new conversation {conversation.id} for session {session_key}")
            except Exception as e:
                # Graceful degradation - log error but continue
                logger.warning(
                    f"Failed to create/retrieve conversation: {e}",
                    extra={"session_key": session_key, "error": str(e)}
                )

        # Step 2: Store user message in ZeroDB (if conversation exists)
        if conversation:
            try:
                await self._conversation_service.add_message(
                    conversation_id=conversation.id,
                    role="user",
                    content=message
                )
                logger.debug(f"Stored user message in conversation {conversation.id}")
            except Exception as e:
                # Graceful degradation - log error but continue
                logger.warning(
                    f"Failed to store user message: {e}",
                    extra={"conversation_id": str(conversation.id), "error": str(e)}
                )
        # Validate connection
        if not self.is_connected:
            raise ConnectionError("Bridge is not connected. Call connect() first.")

        # Validate session key format
        if not self._validate_session_key(session_key):
            raise SessionError(f"Invalid session key format: {session_key}")

        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(self._max_retries):
            try:
                start_time = datetime.now(timezone.utc)

                # Send message via base bridge
                result = await self._base_bridge.send_to_agent(
                    session_key=session_key,
                    message=message
                )

                # Calculate latency
                latency_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000

                # Enrich response with metadata
                response = {
                    "status": "sent",
                    "message_id": result.get("id", f"msg_{datetime.now(timezone.utc).timestamp()}"),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "session_key": session_key,
                    "metadata": metadata or {},
                    "result": result  # Include full result for assistant response extraction
                }

                # Include conversation_id if conversation was tracked
                if conversation:
                    response["conversation_id"] = str(conversation.id)

                # Step 4: Store assistant response in ZeroDB (if conversation exists and response has content)
                if conversation and result.get("result") and result["result"].get("response"):
                    try:
                        assistant_metadata = {}
                        if result["result"].get("model"):
                            assistant_metadata["model"] = result["result"]["model"]
                        if result["result"].get("tokens_used"):
                            assistant_metadata["tokens_used"] = result["result"]["tokens_used"]

                        await self._conversation_service.add_message(
                            conversation_id=conversation.id,
                            role="assistant",
                            content=result["result"]["response"],
                            metadata=assistant_metadata if assistant_metadata else None
                        )
                        logger.debug(f"Stored assistant response in conversation {conversation.id}")
                    except Exception as e:
                        # Graceful degradation - log error but continue
                        logger.warning(
                            f"Failed to store assistant response: {e}",
                            extra={"conversation_id": str(conversation.id), "error": str(e)}
                        )

                logger.info(
                    "Message sent successfully",
                    extra={
                        "session_key": session_key,
                        "message_id": response["message_id"],
                        "latency_ms": latency_ms,
                        "attempt": attempt + 1,
                        "message_length": len(message)
                    }
                )

                return response

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Send attempt {attempt + 1} failed for session {session_key}: {e}",
                    extra={
                        "session_key": session_key,
                        "attempt": attempt + 1,
                        "max_retries": self._max_retries,
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                )

                if attempt < self._max_retries - 1:
                    delay = self._calculate_backoff(attempt)
                    logger.info(f"Retrying in {delay:.2f}s...")
                    await asyncio.sleep(delay)

        # All retries exhausted
        error_msg = (
            f"Failed to send message after {self._max_retries} retries. "
            f"Last error: {last_error}"
        )
        logger.error(
            error_msg,
            extra={
                "session_key": session_key,
                "max_retries": self._max_retries,
                "last_error_type": type(last_error).__name__
            }
        )
        raise SendError(error_msg)

    async def close(self) -> None:
        """Close connection gracefully"""
        try:
            await self._base_bridge.close()
            self._connection_state = BridgeConnectionState.DISCONNECTED
            logger.info("Disconnected from OpenClaw Gateway")
        except Exception as e:
            logger.error(f"Error during disconnect: {e}")
            raise

    def on_event(self, event_name: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register event handler

        Args:
            event_name: Name of event to subscribe to
            handler: Async callback function to handle event payload
        """
        self._base_bridge.on_event(event_name, handler)
        logger.info(f"Registered event handler for '{event_name}'")

    def _calculate_backoff(self, attempt: int) -> float:
        """
        Calculate exponential backoff with jitter

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        # Exponential backoff: delay = initial_delay * (2 ^ attempt)
        delay = min(
            self._initial_delay * (2 ** attempt),
            self._max_delay
        )

        # Add jitter (0-100ms) to prevent thundering herd
        jitter = random.uniform(0, 0.1)

        return delay + jitter

    def _validate_session_key(self, session_key: str) -> bool:
        """
        Validate session key format

        Session keys should be in format: "channel:type:identifier"

        Examples:
        - "whatsapp:group:120363401780756402@g.us"
        - "whatsapp:dm:18312950562"
        - "whatsapp:self:main"
        - "agent:whatsapp:main"

        Args:
            session_key: Session key to validate

        Returns:
            True if valid, False otherwise
        """
        if not session_key or not isinstance(session_key, str):
            return False

        parts = session_key.split(":")
        if len(parts) < 2:
            return False

        # Valid channel prefixes
        valid_channels = {"whatsapp", "agent", "slack", "discord", "telegram"}
        if parts[0] not in valid_channels:
            logger.warning(
                f"Invalid channel in session key: {parts[0]}",
                extra={"session_key": session_key}
            )
            return False

        return True

    async def _load_conversation_context(
        self,
        conversation_id: UUID,
        max_messages: int = 10
    ) -> list:
        """
        Load recent conversation context for message handlers.

        Retrieves the last N messages from a conversation to provide context
        for agent responses. Used by message handlers to maintain conversation
        continuity.

        Args:
            conversation_id: UUID of conversation to load context from
            max_messages: Maximum number of recent messages to retrieve (default: 10)

        Returns:
            List of message dictionaries with role, content, timestamp.
            Returns empty list if conversation service unavailable or on error
            (graceful degradation).

        Example:
            context = await bridge._load_conversation_context(
                conversation_id=UUID("..."),
                max_messages=10
            )
            # Returns: [
            #     {"id": "msg_1", "role": "user", "content": "Hello", "timestamp": "..."},
            #     {"id": "msg_2", "role": "assistant", "content": "Hi!", "timestamp": "..."}
            # ]
        """
        # Graceful degradation if conversation service not available
        if not self._conversation_service:
            logger.debug("ConversationService not available - returning empty context")
            return []

        try:
            # Retrieve messages from ZeroDB via conversation service
            messages = await self._conversation_service.get_messages(
                conversation_id=conversation_id,
                limit=max_messages,
                offset=0
            )

            logger.debug(
                f"Loaded {len(messages)} messages for conversation context",
                extra={
                    "conversation_id": str(conversation_id),
                    "message_count": len(messages)
                }
            )

            return messages

        except Exception as e:
            # Graceful degradation on error - log and return empty context
            logger.warning(
                f"Failed to load conversation context: {e}",
                extra={
                    "conversation_id": str(conversation_id),
                    "error": str(e)
                }
            )
            return []
