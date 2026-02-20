"""
Mock OpenClaw Bridge for Testing

Simulates OpenClaw bridge behavior without actual WebSocket connection.
Useful for unit tests and integration tests.

Refs #1094
"""

from typing import Dict, Any, Optional, Callable, List
from datetime import datetime, timezone
import random

from app.agents.orchestration.openclaw_bridge_protocol import (
    IOpenClawBridge,
    BridgeConnectionState,
    ConnectionError,
    SendError,
    SessionError
)


class MockOpenClawBridge:
    """
    Mock implementation for testing

    Features:
    - Simulates connection/disconnection
    - Records all sent messages for assertions
    - Can simulate failures for error testing
    - Supports event handler registration
    - Provides testing utilities

    Usage:
        mock_bridge = MockOpenClawBridge()
        await mock_bridge.connect()
        result = await mock_bridge.send_to_agent("session_key", "message")

        # Assert in tests
        messages = mock_bridge.get_sent_messages()
        assert len(messages) == 1
    """

    def __init__(
        self,
        simulate_failures: bool = False,
        failure_rate: float = 0.0
    ):
        """
        Initialize mock bridge

        Args:
            simulate_failures: If True, operations may fail randomly
            failure_rate: Probability of failure (0.0 to 1.0)
        """
        self._connected = False
        self._connection_state = BridgeConnectionState.DISCONNECTED
        self._sent_messages: List[Dict[str, Any]] = []
        self._event_handlers: Dict[str, Callable] = {}
        self._simulate_failures = simulate_failures
        self._failure_rate = failure_rate
        self._call_count = 0

    @property
    def is_connected(self) -> bool:
        """Check if bridge is connected"""
        return self._connected

    @property
    def connection_state(self) -> BridgeConnectionState:
        """Get current connection state"""
        return self._connection_state

    async def connect(self) -> None:
        """
        Simulate connection to OpenClaw Gateway

        Raises:
            ConnectionError: If simulate_failures=True and random check fails
        """
        if self._simulate_failures and self._should_fail():
            raise ConnectionError("Simulated connection failure")

        self._connected = True
        self._connection_state = BridgeConnectionState.CONNECTED

    async def send_to_agent(
        self,
        session_key: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Simulate sending message to agent

        Args:
            session_key: Target session identifier
            message: Message content to send
            metadata: Optional metadata for routing/tracking

        Returns:
            Response dictionary with message details

        Raises:
            ConnectionError: If bridge is not connected
            SendError: If simulate_failures=True and random check fails
        """
        if not self._connected:
            raise ConnectionError("Bridge is not connected")

        if self._simulate_failures and self._should_fail():
            raise SendError("Simulated send failure")

        # Create message record
        sent_message = {
            "status": "sent",
            "message_id": f"mock_msg_{len(self._sent_messages) + 1}",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_key": session_key,
            "message": message,
            "metadata": metadata or {}
        }

        # Record message
        self._sent_messages.append(sent_message)

        return sent_message

    async def close(self) -> None:
        """Simulate disconnection from OpenClaw Gateway"""
        self._connected = False
        self._connection_state = BridgeConnectionState.DISCONNECTED

    def on_event(self, event_name: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """
        Register event handler

        Args:
            event_name: Name of event to subscribe to
            handler: Async callback function to handle event payload
        """
        self._event_handlers[event_name] = handler

    def _should_fail(self) -> bool:
        """
        Determine if operation should fail (for testing)

        Returns:
            True if operation should fail based on failure_rate
        """
        self._call_count += 1
        return random.random() < self._failure_rate

    # Testing utilities

    def get_sent_messages(self) -> List[Dict[str, Any]]:
        """
        Get all sent messages (for test assertions)

        Returns:
            List of message dictionaries in order sent
        """
        return self._sent_messages.copy()

    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """
        Get last sent message (for test assertions)

        Returns:
            Last message dictionary or None if no messages sent
        """
        return self._sent_messages[-1] if self._sent_messages else None

    def get_messages_for_session(self, session_key: str) -> List[Dict[str, Any]]:
        """
        Get all messages sent to specific session

        Args:
            session_key: Session key to filter by

        Returns:
            List of messages sent to the session
        """
        return [
            msg for msg in self._sent_messages
            if msg["session_key"] == session_key
        ]

    def clear_messages(self) -> None:
        """Clear sent messages history"""
        self._sent_messages.clear()

    def get_message_count(self) -> int:
        """Get total number of messages sent"""
        return len(self._sent_messages)

    async def simulate_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        """
        Simulate incoming event (for testing event handlers)

        Args:
            event_name: Name of event to trigger
            payload: Event payload data
        """
        if event_name in self._event_handlers:
            handler = self._event_handlers[event_name]
            await handler(payload)

    def assert_message_sent(self, session_key: str, message_substring: str) -> bool:
        """
        Assert that a message containing substring was sent to session

        Args:
            session_key: Session key to check
            message_substring: Substring to search for in message

        Returns:
            True if matching message found
        """
        for msg in self._sent_messages:
            if msg["session_key"] == session_key and message_substring in msg["message"]:
                return True
        return False

    def get_event_handlers(self) -> Dict[str, Callable]:
        """Get registered event handlers (for testing)"""
        return self._event_handlers.copy()
