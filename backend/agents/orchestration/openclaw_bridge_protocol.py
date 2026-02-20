"""
OpenClaw Bridge Protocol - Interface specification for WhatsApp communication

This protocol defines the contract that any OpenClaw bridge implementation must follow.
Using Protocol allows for both concrete implementations and test mocks without inheritance.

Refs #1094
"""

from typing import Protocol, Dict, Any, Optional, Callable, runtime_checkable
from enum import Enum


class BridgeConnectionState(Enum):
    """Connection states for OpenClaw bridge"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class BridgeError(Exception):
    """Base exception for bridge errors"""
    pass


class ConnectionError(BridgeError):
    """Raised when connection to OpenClaw Gateway fails"""
    pass


class SendError(BridgeError):
    """Raised when message sending fails"""
    pass


class SessionError(BridgeError):
    """Raised when session key is invalid or session doesn't exist"""
    pass


@runtime_checkable
class IOpenClawBridge(Protocol):
    """
    Protocol defining the OpenClaw bridge interface

    This interface abstracts the OpenClaw Gateway communication layer,
    allowing for multiple implementations (production, testing, mocking).

    All methods are async to support non-blocking I/O operations.
    """

    @property
    def is_connected(self) -> bool:
        """
        Check if bridge is connected to OpenClaw Gateway

        Returns:
            True if connected and ready to send messages
        """
        ...

    @property
    def connection_state(self) -> BridgeConnectionState:
        """
        Get current connection state

        Returns:
            Current BridgeConnectionState
        """
        ...

    async def connect(self) -> None:
        """
        Connect to OpenClaw Gateway and authenticate

        Establishes WebSocket connection, sends authentication frame,
        and starts event loop for receiving messages.

        Raises:
            ConnectionError: If connection or authentication fails
        """
        ...

    async def send_to_agent(
        self,
        session_key: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Send message to specific agent session

        Args:
            session_key: Target session identifier (e.g., "whatsapp:group:123@g.us")
            message: Message content to send
            metadata: Optional metadata for routing/tracking

        Returns:
            Response dictionary containing:
            - status: "sent" | "queued" | "failed"
            - message_id: Unique identifier for the message
            - timestamp: ISO 8601 timestamp
            - session_key: Echo of target session

        Raises:
            ConnectionError: If bridge is not connected
            SessionError: If session_key is invalid
            SendError: If message delivery fails after retries
        """
        ...

    async def close(self) -> None:
        """
        Close WebSocket connection gracefully

        Sends disconnect frame, waits for acknowledgment,
        and cleans up resources.
        """
        ...

    def on_event(self, event_name: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register event handler for incoming events

        Args:
            event_name: Name of event to subscribe to
            handler: Async callback function to handle event payload
        """
        ...
