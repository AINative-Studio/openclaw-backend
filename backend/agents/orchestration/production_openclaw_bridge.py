"""
Production OpenClaw Bridge Implementation

Implements IOpenClawBridge with robust error handling, retry logic, and monitoring.

Refs #1094
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime, timezone
import random
import sys
import os

# Add integrations directory to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), 'integrations'))

from openclaw_bridge import OpenClawBridge as BaseOpenClawBridge
from app.agents.orchestration.openclaw_bridge_protocol import (
    IOpenClawBridge,
    BridgeConnectionState,
    ConnectionError,
    SendError,
    SessionError
)

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
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0
    ):
        """
        Initialize production bridge

        Args:
            url: OpenClaw Gateway WebSocket URL
            token: Authentication token
            max_retries: Maximum retry attempts
            initial_delay: Initial retry delay in seconds
            max_delay: Maximum retry delay in seconds
        """
        self._base_bridge = BaseOpenClawBridge(url=url, token=token)
        self._connection_state = BridgeConnectionState.DISCONNECTED
        self._max_retries = max_retries
        self._initial_delay = initial_delay
        self._max_delay = max_delay

        logger.info(
            "ProductionOpenClawBridge initialized",
            extra={
                "url": url,
                "max_retries": max_retries
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
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send message to agent with retry and validation

        Args:
            session_key: Target session identifier
            message: Message content to send
            metadata: Optional metadata for routing/tracking

        Returns:
            Response dictionary with status and message details

        Raises:
            ConnectionError: If bridge is not connected
            SessionError: If session key is invalid
            SendError: If message delivery fails after retries
        """
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
                    "metadata": metadata or {}
                }

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
