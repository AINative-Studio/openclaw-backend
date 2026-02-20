# OpenClaw Bridge Interface Specification

**Version**: 1.0.0
**Status**: Production-Ready
**Refs**: #1094

---

## Overview

This document defines the production-ready interface specification for the OpenClaw bridge that enables bidirectional WhatsApp communication in the Claude orchestration system.

The bridge serves as the communication layer between the orchestrator and OpenClaw Gateway, providing reliable message delivery with proper error handling, retry logic, and session management.

---

## Architecture Context

```
Orchestrator → Bridge Interface → OpenClaw Bridge → OpenClaw Gateway → WhatsApp
     ↑                                                                      ↓
     └──────────────────────────────────────────────────────────────────────┘
```

**Message Flow**:
1. Orchestrator sends status update via bridge interface
2. Bridge validates connection and session
3. Message sent to OpenClaw Gateway via WebSocket
4. Gateway routes message to WhatsApp agent
5. WhatsApp delivers message to user/group

---

## Interface Definition

### 1. Protocol-Based Interface (Recommended)

Using Python's `typing.Protocol` for structural typing:

```python
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
```

### 2. Abstract Base Class (Alternative)

For stricter inheritance-based typing:

```python
"""
OpenClaw Bridge ABC - Abstract base class for OpenClaw bridge implementations

Refs #1094
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Callable


class AbstractOpenClawBridge(ABC):
    """
    Abstract base class for OpenClaw bridge implementations

    Enforces implementation of all required methods through ABC mechanism.
    Use this if you prefer inheritance over structural typing.
    """

    @property
    @abstractmethod
    def is_connected(self) -> bool:
        """Check if bridge is connected to OpenClaw Gateway"""
        pass

    @property
    @abstractmethod
    def connection_state(self) -> BridgeConnectionState:
        """Get current connection state"""
        pass

    @abstractmethod
    async def connect(self) -> None:
        """Connect to OpenClaw Gateway and authenticate"""
        pass

    @abstractmethod
    async def send_to_agent(
        self,
        session_key: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send message to specific agent session"""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close WebSocket connection gracefully"""
        pass

    @abstractmethod
    def on_event(self, event_name: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Register event handler for incoming events"""
        pass
```

---

## Error Handling Strategy

### 1. Error Hierarchy

```
BridgeError (base)
├── ConnectionError
│   ├── AuthenticationError
│   ├── NetworkError
│   └── TimeoutError
├── SendError
│   ├── MessageRejectedError
│   └── RateLimitError
└── SessionError
    ├── InvalidSessionKeyError
    └── SessionNotFoundError
```

### 2. Retry Strategy

**Exponential Backoff with Jitter**:

```python
class RetryConfig:
    """Configuration for retry behavior"""
    max_retries: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 30.0     # seconds
    exponential_base: float = 2.0
    jitter: bool = True
```

**Retry Logic**:
- Initial delay: 1 second
- Exponential backoff: delay = initial_delay * (base ^ attempt)
- Max delay cap: 30 seconds
- Jitter: Add random 0-100ms to prevent thundering herd

**Retryable Errors**:
- Network errors
- Temporary connection loss
- Rate limit errors (with longer delay)

**Non-Retryable Errors**:
- Authentication failures
- Invalid session keys
- Malformed message content

### 3. Circuit Breaker Pattern

Prevent cascading failures when OpenClaw Gateway is down:

```python
class CircuitBreakerState(Enum):
    CLOSED = "closed"     # Normal operation
    OPEN = "open"         # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery

class CircuitBreaker:
    """Circuit breaker for OpenClaw bridge"""
    failure_threshold: int = 5      # Open after 5 failures
    success_threshold: int = 2      # Close after 2 successes
    timeout: float = 60.0           # Reset after 60s
```

---

## Implementation Examples

### 1. Production Implementation

```python
"""
Production OpenClaw Bridge Implementation

Refs #1094
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from datetime import datetime
import random

from integrations.openclaw_bridge import OpenClawBridge as BaseOpenClawBridge
from app.agents.orchestration.openclaw_bridge_protocol import (
    IOpenClawBridge,
    BridgeConnectionState,
    ConnectionError,
    SendError,
    SessionError
)

logger = logging.getLogger(__name__)


class ProductionOpenClawBridge(IOpenClawBridge):
    """
    Production implementation of OpenClaw bridge with robust error handling
    """

    def __init__(
        self,
        url: str,
        token: str,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0
    ):
        self._base_bridge = BaseOpenClawBridge(url=url, token=token)
        self._connection_state = BridgeConnectionState.DISCONNECTED
        self._max_retries = max_retries
        self._initial_delay = initial_delay
        self._max_delay = max_delay

    @property
    def is_connected(self) -> bool:
        return self._base_bridge.is_connected

    @property
    def connection_state(self) -> BridgeConnectionState:
        return self._connection_state

    async def connect(self) -> None:
        """Connect with automatic retry"""
        self._connection_state = BridgeConnectionState.CONNECTING

        for attempt in range(self._max_retries):
            try:
                await self._base_bridge.connect()
                self._connection_state = BridgeConnectionState.CONNECTED
                logger.info("Connected to OpenClaw Gateway")
                return

            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")

                if attempt < self._max_retries - 1:
                    delay = self._calculate_backoff(attempt)
                    await asyncio.sleep(delay)
                else:
                    self._connection_state = BridgeConnectionState.FAILED
                    raise ConnectionError(
                        f"Failed to connect after {self._max_retries} attempts"
                    ) from e

    async def send_to_agent(
        self,
        session_key: str,
        message: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send message with retry and validation"""

        # Validate connection
        if not self.is_connected:
            raise ConnectionError("Bridge is not connected")

        # Validate session key format
        if not self._validate_session_key(session_key):
            raise SessionError(f"Invalid session key format: {session_key}")

        # Retry loop with exponential backoff
        last_error = None
        for attempt in range(self._max_retries):
            try:
                # Send message via base bridge
                result = await self._base_bridge.send_to_agent(
                    session_key=session_key,
                    message=message
                )

                # Enrich response with metadata
                return {
                    "status": "sent",
                    "message_id": result.get("id", f"msg_{datetime.utcnow().timestamp()}"),
                    "timestamp": datetime.utcnow().isoformat(),
                    "session_key": session_key,
                    "metadata": metadata or {}
                }

            except Exception as e:
                last_error = e
                logger.warning(
                    f"Send attempt {attempt + 1} failed for session {session_key}: {e}"
                )

                if attempt < self._max_retries - 1:
                    delay = self._calculate_backoff(attempt)
                    await asyncio.sleep(delay)

        # All retries exhausted
        raise SendError(
            f"Failed to send message after {self._max_retries} retries. "
            f"Last error: {last_error}"
        )

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
        """Register event handler"""
        self._base_bridge.on_event(event_name, handler)

    def _calculate_backoff(self, attempt: int) -> float:
        """Calculate exponential backoff with jitter"""
        delay = min(
            self._initial_delay * (2 ** attempt),
            self._max_delay
        )
        # Add jitter (0-100ms)
        jitter = random.uniform(0, 0.1)
        return delay + jitter

    def _validate_session_key(self, session_key: str) -> bool:
        """Validate session key format"""
        # Session keys should be in format: "channel:type:identifier"
        # Examples:
        # - "whatsapp:group:120363401780756402@g.us"
        # - "whatsapp:dm:18312950562"
        # - "agent:whatsapp:main"

        if not session_key or not isinstance(session_key, str):
            return False

        parts = session_key.split(":")
        if len(parts) < 2:
            return False

        # Valid channel prefixes
        valid_channels = {"whatsapp", "agent", "slack", "discord", "telegram"}
        if parts[0] not in valid_channels:
            return False

        return True
```

### 2. Mock Implementation for Testing

```python
"""
Mock OpenClaw Bridge for Testing

Refs #1094
"""

from typing import Dict, Any, Optional, Callable
from datetime import datetime

from app.agents.orchestration.openclaw_bridge_protocol import (
    IOpenClawBridge,
    BridgeConnectionState,
    ConnectionError,
    SendError,
    SessionError
)


class MockOpenClawBridge(IOpenClawBridge):
    """
    Mock implementation for testing

    Simulates OpenClaw bridge behavior without actual WebSocket connection.
    Useful for unit tests and integration tests.
    """

    def __init__(
        self,
        simulate_failures: bool = False,
        failure_rate: float = 0.0
    ):
        self._connected = False
        self._connection_state = BridgeConnectionState.DISCONNECTED
        self._sent_messages: list[Dict[str, Any]] = []
        self._event_handlers: Dict[str, Callable] = {}
        self._simulate_failures = simulate_failures
        self._failure_rate = failure_rate
        self._call_count = 0

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def connection_state(self) -> BridgeConnectionState:
        return self._connection_state

    async def connect(self) -> None:
        """Simulate connection"""
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
        """Simulate message sending"""

        if not self._connected:
            raise ConnectionError("Bridge is not connected")

        if self._simulate_failures and self._should_fail():
            raise SendError("Simulated send failure")

        # Record message
        sent_message = {
            "status": "sent",
            "message_id": f"mock_msg_{len(self._sent_messages) + 1}",
            "timestamp": datetime.utcnow().isoformat(),
            "session_key": session_key,
            "message": message,
            "metadata": metadata or {}
        }
        self._sent_messages.append(sent_message)

        return sent_message

    async def close(self) -> None:
        """Simulate disconnection"""
        self._connected = False
        self._connection_state = BridgeConnectionState.DISCONNECTED

    def on_event(self, event_name: str, handler: Callable[[Dict[str, Any]], None]) -> None:
        """Register event handler"""
        self._event_handlers[event_name] = handler

    def _should_fail(self) -> bool:
        """Determine if operation should fail (for testing)"""
        import random
        self._call_count += 1
        return random.random() < self._failure_rate

    # Testing utilities

    def get_sent_messages(self) -> list[Dict[str, Any]]:
        """Get all sent messages (for test assertions)"""
        return self._sent_messages.copy()

    def get_last_message(self) -> Optional[Dict[str, Any]]:
        """Get last sent message (for test assertions)"""
        return self._sent_messages[-1] if self._sent_messages else None

    def clear_messages(self) -> None:
        """Clear sent messages history"""
        self._sent_messages.clear()

    async def simulate_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        """Simulate incoming event (for testing event handlers)"""
        if event_name in self._event_handlers:
            handler = self._event_handlers[event_name]
            await handler(payload)
```

---

## Integration with Orchestrator

### 1. Dependency Injection

```python
"""
Orchestrator with Bridge Integration

Refs #1094
"""

from app.agents.orchestration.openclaw_bridge_protocol import IOpenClawBridge
from app.agents.orchestration.notification_service import NotificationService


class ClaudeOrchestrator:
    """Orchestrator with bridge integration"""

    def __init__(
        self,
        spawner: NousCoderAgentSpawner,
        openclaw_bridge: IOpenClawBridge,  # Protocol-based dependency
        whatsapp_session_key: str = "agent:whatsapp:main"
    ):
        self.spawner = spawner

        # Create notification service with bridge
        self.notification_service = NotificationService(
            openclaw_bridge=openclaw_bridge,
            whatsapp_session_key=whatsapp_session_key
        )

        self.command_parser = CommandParser()
        self.active_workflows: Dict[int, WorkflowTracker] = {}
```

### 2. Notification Service Integration

```python
"""
Notification Service with Bridge Protocol

Refs #1094
"""

from app.agents.orchestration.openclaw_bridge_protocol import (
    IOpenClawBridge,
    ConnectionError,
    SendError
)


class NotificationService:
    """Notification service using bridge protocol"""

    def __init__(
        self,
        openclaw_bridge: IOpenClawBridge,
        whatsapp_session_key: str = "agent:whatsapp:main",
        max_retries: int = 3,
        retry_delay: float = 1.0
    ):
        self.openclaw_bridge = openclaw_bridge
        self.whatsapp_session_key = whatsapp_session_key
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def notify_agent_spawned(
        self,
        issue_number: int,
        agent_id: str
    ) -> None:
        """Send agent spawned notification"""
        message = f"✓ Agent spawned for issue #{issue_number}\n\nAgent ID: {agent_id}"

        try:
            await self.openclaw_bridge.send_to_agent(
                session_key=self.whatsapp_session_key,
                message=message,
                metadata={
                    "notification_type": "agent_spawned",
                    "issue_number": issue_number,
                    "agent_id": agent_id
                }
            )
        except (ConnectionError, SendError) as e:
            logger.error(f"Failed to send notification: {e}")
            # Don't propagate - notification failure shouldn't break workflow
```

### 3. Factory Pattern for Bridge Creation

```python
"""
Bridge Factory for Environment-Specific Instances

Refs #1094
"""

import os
from typing import Optional

from app.agents.orchestration.openclaw_bridge_protocol import IOpenClawBridge
from app.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge
from app.agents.orchestration.mock_openclaw_bridge import MockOpenClawBridge


class OpenClawBridgeFactory:
    """Factory for creating environment-appropriate bridge instances"""

    @staticmethod
    def create_bridge(
        environment: Optional[str] = None,
        url: Optional[str] = None,
        token: Optional[str] = None
    ) -> IOpenClawBridge:
        """
        Create bridge instance based on environment

        Args:
            environment: Environment name (production, staging, testing, development)
            url: Gateway URL (defaults to OPENCLAW_GATEWAY_URL env var)
            token: Auth token (defaults to OPENCLAW_GATEWAY_TOKEN env var)

        Returns:
            IOpenClawBridge instance
        """
        env = environment or os.getenv("ENVIRONMENT", "development")

        if env in ("testing", "test"):
            return MockOpenClawBridge()

        # Production/staging/development use real bridge
        gateway_url = url or os.getenv(
            "OPENCLAW_GATEWAY_URL",
            "ws://127.0.0.1:18789"
        )
        gateway_token = token or os.getenv("OPENCLAW_GATEWAY_TOKEN")

        if not gateway_token:
            raise ValueError("OPENCLAW_GATEWAY_TOKEN must be set")

        return ProductionOpenClawBridge(
            url=gateway_url,
            token=gateway_token,
            max_retries=3,
            initial_delay=1.0,
            max_delay=30.0
        )
```

---

## Testing Strategy

### 1. Unit Tests with Mock Bridge

```python
"""
Unit tests for orchestrator with mock bridge

Refs #1094
"""

import pytest
from app.agents.orchestration.claude_orchestrator import ClaudeOrchestrator
from app.agents.orchestration.mock_openclaw_bridge import MockOpenClawBridge


@pytest.mark.asyncio
async def test_orchestrator_sends_notification_on_agent_spawn():
    """
    Given: Orchestrator with mock bridge
    When: Agent spawned for issue
    Then: Should send WhatsApp notification
    """
    # Arrange
    mock_bridge = MockOpenClawBridge()
    await mock_bridge.connect()

    orchestrator = ClaudeOrchestrator(
        spawner=mock_spawner,
        openclaw_bridge=mock_bridge
    )

    # Act
    result = await orchestrator.handle_whatsapp_command("work on issue #1234")

    # Assert
    assert result["success"] is True

    # Verify notification sent
    messages = mock_bridge.get_sent_messages()
    assert len(messages) == 1
    assert "Agent spawned" in messages[0]["message"]
    assert "#1234" in messages[0]["message"]
```

### 2. Integration Tests

```python
"""
Integration tests with real OpenClaw Gateway

Refs #1094
"""

import pytest
import os


@pytest.mark.integration
@pytest.mark.skipif(
    not os.getenv("OPENCLAW_GATEWAY_URL"),
    reason="OpenClaw Gateway not configured"
)
@pytest.mark.asyncio
async def test_real_bridge_connection():
    """
    Given: Real OpenClaw Gateway running
    When: Bridge connects
    Then: Should authenticate and be ready
    """
    from app.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

    bridge = ProductionOpenClawBridge(
        url=os.getenv("OPENCLAW_GATEWAY_URL"),
        token=os.getenv("OPENCLAW_GATEWAY_TOKEN")
    )

    try:
        await bridge.connect()
        assert bridge.is_connected

        # Send test message
        result = await bridge.send_to_agent(
            session_key="whatsapp:self:main",
            message="Test message from integration test"
        )

        assert result["status"] == "sent"
        assert "message_id" in result

    finally:
        await bridge.close()
```

---

## Session Key Reference

### Format

`{channel}:{type}:{identifier}`

### Examples

| Session Key | Description |
|------------|-------------|
| `whatsapp:group:120363401780756402@g.us` | WhatsApp group |
| `whatsapp:dm:18312950562` | WhatsApp DM to specific number |
| `whatsapp:self:main` | WhatsApp self-chat |
| `agent:whatsapp:main` | Agent session for WhatsApp |
| `slack:channel:C01234567` | Slack channel |
| `discord:guild:987654321` | Discord server |

### Validation Rules

1. Must have at least 2 parts separated by `:`
2. First part must be valid channel: `whatsapp`, `agent`, `slack`, `discord`, `telegram`
3. Second part indicates type: `group`, `dm`, `self`, `channel`, `guild`
4. Third part is channel-specific identifier

---

## Configuration

### Environment Variables

```bash
# OpenClaw Gateway Configuration
OPENCLAW_GATEWAY_URL="ws://127.0.0.1:18789"
OPENCLAW_GATEWAY_TOKEN="your-token-here"

# Session Configuration
OPENCLAW_WHATSAPP_SESSION_KEY="whatsapp:group:120363401780756402@g.us"

# Retry Configuration
OPENCLAW_MAX_RETRIES=3
OPENCLAW_INITIAL_DELAY=1.0
OPENCLAW_MAX_DELAY=30.0

# Circuit Breaker Configuration
OPENCLAW_CIRCUIT_BREAKER_THRESHOLD=5
OPENCLAW_CIRCUIT_BREAKER_TIMEOUT=60
```

### Production Settings

```python
# Production configuration in settings.py

from pydantic import BaseSettings


class OpenClawSettings(BaseSettings):
    """OpenClaw bridge settings"""

    gateway_url: str = "ws://127.0.0.1:18789"
    gateway_token: str
    whatsapp_session_key: str = "agent:whatsapp:main"

    max_retries: int = 3
    initial_delay: float = 1.0
    max_delay: float = 30.0

    circuit_breaker_threshold: int = 5
    circuit_breaker_timeout: float = 60.0

    class Config:
        env_prefix = "OPENCLAW_"
```

---

## Monitoring and Observability

### Metrics to Track

1. **Connection Metrics**:
   - Connection attempts
   - Connection failures
   - Connection duration
   - Reconnection count

2. **Message Metrics**:
   - Messages sent (count)
   - Messages failed (count)
   - Retry attempts
   - Success rate

3. **Performance Metrics**:
   - Message send latency (p50, p95, p99)
   - Queue depth
   - Throughput (messages/second)

4. **Error Metrics**:
   - Error rate by type
   - Circuit breaker trips
   - Timeout count

### Logging

```python
logger.info(
    "Message sent successfully",
    extra={
        "session_key": session_key,
        "message_id": message_id,
        "latency_ms": latency,
        "attempt": attempt
    }
)

logger.error(
    "Message send failed",
    extra={
        "session_key": session_key,
        "error_type": type(error).__name__,
        "error_message": str(error),
        "attempt": attempt,
        "max_retries": max_retries
    }
)
```

---

## Migration Guide

### From Current Implementation

**Step 1**: Create protocol file
```bash
touch src/backend/app/agents/orchestration/openclaw_bridge_protocol.py
```

**Step 2**: Update NotificationService to accept protocol
```python
# Before
def __init__(self, openclaw_bridge):
    self.openclaw_bridge = openclaw_bridge

# After
def __init__(self, openclaw_bridge: IOpenClawBridge):
    self.openclaw_bridge = openclaw_bridge
```

**Step 3**: Update tests to use MockOpenClawBridge
```python
# Before
mock_bridge = Mock()
mock_bridge.send_to_agent = AsyncMock()

# After
mock_bridge = MockOpenClawBridge()
await mock_bridge.connect()
```

**Step 4**: Update orchestrator initialization
```python
# Before
bridge = OpenClawBridge(url=url, token=token)

# After
bridge = OpenClawBridgeFactory.create_bridge()
```

---

## Security Considerations

1. **Token Storage**: Never log or expose gateway token
2. **Message Validation**: Validate message content before sending
3. **Rate Limiting**: Respect OpenClaw Gateway rate limits
4. **Session Isolation**: Each session should be isolated
5. **Error Messages**: Don't leak sensitive info in error messages

---

## Future Enhancements

1. **Message Queue**: Add persistent queue for offline messages
2. **Delivery Confirmation**: Track message delivery status
3. **Multi-Channel Support**: Abstract beyond WhatsApp
4. **Message Templates**: Pre-defined message templates
5. **Analytics**: Advanced message analytics and insights

---

## References

- OpenClaw Gateway Documentation: https://docs.openclaw.ai/
- WebSocket Protocol: RFC 6455
- Circuit Breaker Pattern: Martin Fowler
- Retry Patterns: AWS Architecture Blog

---

**Maintained by**: AINative Backend Team
**Last Updated**: 2026-02-06
**Refs**: #1094
