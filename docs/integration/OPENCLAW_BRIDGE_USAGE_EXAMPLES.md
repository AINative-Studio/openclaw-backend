# OpenClaw Bridge Usage Examples

Comprehensive examples demonstrating how to use the OpenClaw bridge interface in various scenarios.

**Refs**: #1094

---

## Table of Contents

1. [Basic Usage](#basic-usage)
2. [Orchestrator Integration](#orchestrator-integration)
3. [Notification Service Integration](#notification-service-integration)
4. [Error Handling](#error-handling)
5. [Testing Examples](#testing-examples)
6. [Advanced Patterns](#advanced-patterns)

---

## Basic Usage

### Simple Message Sending

```python
"""
Simple example of sending a WhatsApp message via OpenClaw bridge
"""

import asyncio
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory


async def send_simple_message():
    """Send a simple WhatsApp message"""

    # Create bridge using factory
    bridge = OpenClawBridgeFactory.create_bridge()

    try:
        # Connect to OpenClaw Gateway
        await bridge.connect()

        # Send message
        result = await bridge.send_to_agent(
            session_key="whatsapp:self:main",
            message="Hello from AINative orchestrator!"
        )

        print(f"Message sent: {result['message_id']}")

    finally:
        # Always close connection
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(send_simple_message())
```

### With Metadata

```python
"""
Sending messages with metadata for tracking
"""

import asyncio
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory


async def send_with_metadata():
    """Send message with tracking metadata"""

    bridge = OpenClawBridgeFactory.create_bridge()

    try:
        await bridge.connect()

        result = await bridge.send_to_agent(
            session_key="whatsapp:group:120363401780756402@g.us",
            message="Agent spawned for issue #1234",
            metadata={
                "issue_number": 1234,
                "agent_id": "nouscoder_abc123",
                "notification_type": "agent_spawned",
                "timestamp": "2026-02-06T12:00:00Z"
            }
        )

        print(f"Message sent with metadata: {result}")

    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(send_with_metadata())
```

---

## Orchestrator Integration

### Complete Orchestrator Setup

```python
"""
Complete orchestrator setup with OpenClaw bridge integration
"""

import os
from app.agents.orchestration.claude_orchestrator import ClaudeOrchestrator
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory
from app.agents.orchestration.notification_service import NotificationService
from app.agents.swarm.nouscoder_agent_spawner import NousCoderAgentSpawner


async def setup_orchestrator():
    """Setup orchestrator with OpenClaw bridge"""

    # Create bridge using factory
    bridge = OpenClawBridgeFactory.create_bridge(
        environment=os.getenv("ENVIRONMENT", "development")
    )

    # Connect bridge
    await bridge.connect()

    # Create notification service with bridge
    notification_service = NotificationService(
        openclaw_bridge=bridge,
        whatsapp_session_key=os.getenv(
            "OPENCLAW_WHATSAPP_SESSION_KEY",
            "whatsapp:group:120363401780756402@g.us"
        )
    )

    # Create agent spawner
    spawner = NousCoderAgentSpawner()

    # Create orchestrator
    orchestrator = ClaudeOrchestrator(
        spawner=spawner,
        notification_service=notification_service
    )

    return orchestrator, bridge


async def main():
    """Run orchestrator"""

    orchestrator, bridge = await setup_orchestrator()

    try:
        # Handle WhatsApp command
        result = await orchestrator.handle_whatsapp_command(
            "work on issue #1234"
        )

        print(f"Command result: {result}")

    finally:
        await bridge.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
```

### Lifecycle Management

```python
"""
Proper lifecycle management for long-running orchestrator
"""

import asyncio
import signal
from contextlib import asynccontextmanager


@asynccontextmanager
async def orchestrator_lifecycle():
    """Context manager for orchestrator lifecycle"""

    bridge = OpenClawBridgeFactory.create_bridge()
    await bridge.connect()

    notification_service = NotificationService(openclaw_bridge=bridge)
    spawner = NousCoderAgentSpawner()
    orchestrator = ClaudeOrchestrator(
        spawner=spawner,
        notification_service=notification_service
    )

    try:
        yield orchestrator
    finally:
        # Cleanup
        await bridge.close()


async def run_orchestrator():
    """Run orchestrator with proper lifecycle management"""

    async with orchestrator_lifecycle() as orchestrator:
        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_running_loop()
        stop_event = asyncio.Event()

        def signal_handler():
            stop_event.set()

        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, signal_handler)

        # Process commands until shutdown
        while not stop_event.is_set():
            try:
                # Wait for commands (pseudo-code)
                command = await get_next_command()
                result = await orchestrator.handle_whatsapp_command(command)
                print(f"Processed: {result}")

            except asyncio.CancelledError:
                break

        print("Orchestrator shutting down gracefully...")


if __name__ == "__main__":
    asyncio.run(run_orchestrator())
```

---

## Notification Service Integration

### Basic Notifications

```python
"""
Sending notifications at different workflow stages
"""

import asyncio
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory
from app.agents.orchestration.notification_service import NotificationService


async def workflow_notifications():
    """Send notifications during workflow"""

    bridge = OpenClawBridgeFactory.create_bridge()
    await bridge.connect()

    notification_service = NotificationService(
        openclaw_bridge=bridge,
        whatsapp_session_key="whatsapp:group:120363401780756402@g.us"
    )

    try:
        # Agent spawned
        await notification_service.notify_agent_spawned(
            issue_number=1234,
            agent_id="nouscoder_abc123"
        )

        # Work started
        await notification_service.notify_work_started(
            issue_number=1234,
            agent_id="nouscoder_abc123",
            task_description="Fix authentication bug"
        )

        # PR created
        await notification_service.notify_pr_created(
            issue_number=1234,
            pr_number=5678,
            pr_url="https://github.com/org/repo/pull/5678"
        )

        # Tests passing
        await notification_service.notify_tests_status(
            issue_number=1234,
            tests_passing=True,
            coverage_percent=85
        )

        # Work completed
        await notification_service.notify_work_completed(
            issue_number=1234,
            pr_number=5678,
            pr_url="https://github.com/org/repo/pull/5678"
        )

    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(workflow_notifications())
```

### Error Notifications

```python
"""
Sending error notifications with proper context
"""

import asyncio
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory
from app.agents.orchestration.notification_service import NotificationService


async def error_notification_example():
    """Send error notification"""

    bridge = OpenClawBridgeFactory.create_bridge()
    await bridge.connect()

    notification_service = NotificationService(openclaw_bridge=bridge)

    try:
        # Simulate error
        try:
            # Some operation that fails
            raise ValueError("Database connection timeout")

        except Exception as e:
            # Send error notification
            await notification_service.notify_error(
                issue_number=1234,
                error_message=f"{type(e).__name__}: {str(e)}"
            )

    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(error_notification_example())
```

---

## Error Handling

### Handling Connection Errors

```python
"""
Robust error handling for connection failures
"""

import asyncio
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory
from app.agents.orchestration.openclaw_bridge_protocol import (
    ConnectionError,
    SendError,
    SessionError
)


async def handle_connection_errors():
    """Handle connection errors gracefully"""

    bridge = OpenClawBridgeFactory.create_bridge()

    try:
        await bridge.connect()

    except ConnectionError as e:
        print(f"Failed to connect to OpenClaw Gateway: {e}")
        print("Is OpenClaw Gateway running? Check: openclaw gateway status")
        return

    try:
        result = await bridge.send_to_agent(
            session_key="whatsapp:self:main",
            message="Test message"
        )
        print(f"Success: {result}")

    except SessionError as e:
        print(f"Invalid session key: {e}")

    except SendError as e:
        print(f"Failed to send message: {e}")

    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(handle_connection_errors())
```

### Retry with Custom Logic

```python
"""
Custom retry logic for critical messages
"""

import asyncio
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory
from app.agents.orchestration.openclaw_bridge_protocol import SendError


async def send_with_custom_retry(
    bridge,
    session_key: str,
    message: str,
    max_attempts: int = 5
):
    """Send message with custom retry logic"""

    for attempt in range(max_attempts):
        try:
            result = await bridge.send_to_agent(
                session_key=session_key,
                message=message
            )
            print(f"Message sent on attempt {attempt + 1}")
            return result

        except SendError as e:
            if attempt < max_attempts - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"Attempt {attempt + 1} failed, retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                print(f"All {max_attempts} attempts failed")
                raise


async def main():
    bridge = OpenClawBridgeFactory.create_bridge()
    await bridge.connect()

    try:
        await send_with_custom_retry(
            bridge,
            "whatsapp:self:main",
            "Critical notification"
        )
    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
```

---

## Testing Examples

### Unit Test with Mock Bridge

```python
"""
Unit test using mock bridge
"""

import pytest
from app.agents.orchestration.mock_openclaw_bridge import MockOpenClawBridge
from app.agents.orchestration.notification_service import NotificationService


@pytest.mark.asyncio
async def test_notification_service_sends_message():
    """
    Given: Notification service with mock bridge
    When: Agent spawned notification sent
    Then: Message should be recorded in mock bridge
    """
    # Arrange
    mock_bridge = MockOpenClawBridge()
    await mock_bridge.connect()

    notification_service = NotificationService(
        openclaw_bridge=mock_bridge,
        whatsapp_session_key="whatsapp:test:session"
    )

    # Act
    await notification_service.notify_agent_spawned(
        issue_number=1234,
        agent_id="nouscoder_abc123"
    )

    # Assert
    messages = mock_bridge.get_sent_messages()
    assert len(messages) == 1

    last_message = mock_bridge.get_last_message()
    assert "Agent spawned" in last_message["message"]
    assert "#1234" in last_message["message"]
    assert last_message["session_key"] == "whatsapp:test:session"


@pytest.mark.asyncio
async def test_multiple_notifications():
    """Test sending multiple notifications"""
    # Arrange
    mock_bridge = MockOpenClawBridge()
    await mock_bridge.connect()

    notification_service = NotificationService(openclaw_bridge=mock_bridge)

    # Act
    await notification_service.notify_agent_spawned(1234, "agent_1")
    await notification_service.notify_work_started(1234, "agent_1", "Fix bug")
    await notification_service.notify_pr_created(1234, 5678, "https://github.com/...")

    # Assert
    assert mock_bridge.get_message_count() == 3

    # Verify order
    messages = mock_bridge.get_sent_messages()
    assert "Agent spawned" in messages[0]["message"]
    assert "Work started" in messages[1]["message"]
    assert "PR" in messages[2]["message"]
```

### Testing Error Scenarios

```python
"""
Testing error scenarios with mock bridge
"""

import pytest
from app.agents.orchestration.mock_openclaw_bridge import MockOpenClawBridge
from app.agents.orchestration.openclaw_bridge_protocol import ConnectionError, SendError


@pytest.mark.asyncio
async def test_connection_failure():
    """
    Given: Mock bridge configured to fail
    When: Connect attempted
    Then: Should raise ConnectionError
    """
    # Arrange
    mock_bridge = MockOpenClawBridge(
        simulate_failures=True,
        failure_rate=1.0  # Always fail
    )

    # Act & Assert
    with pytest.raises(ConnectionError):
        await mock_bridge.connect()


@pytest.mark.asyncio
async def test_send_failure():
    """
    Given: Mock bridge connected but configured to fail sends
    When: Send message attempted
    Then: Should raise SendError
    """
    # Arrange
    mock_bridge = MockOpenClawBridge(
        simulate_failures=True,
        failure_rate=1.0
    )
    mock_bridge._connected = True  # Bypass connection for this test

    # Act & Assert
    with pytest.raises(SendError):
        await mock_bridge.send_to_agent(
            session_key="whatsapp:test:session",
            message="Test message"
        )
```

### Integration Test with Real Bridge

```python
"""
Integration test with real OpenClaw Gateway
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
    When: Bridge connects and sends message
    Then: Should succeed without errors
    """
    from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory

    # Arrange
    bridge = OpenClawBridgeFactory.create_bridge()

    try:
        # Act
        await bridge.connect()
        assert bridge.is_connected

        result = await bridge.send_to_agent(
            session_key="whatsapp:self:main",
            message="Integration test message"
        )

        # Assert
        assert result["status"] == "sent"
        assert "message_id" in result
        assert result["session_key"] == "whatsapp:self:main"

    finally:
        await bridge.close()
```

---

## Advanced Patterns

### Event Handling

```python
"""
Handling incoming events from OpenClaw Gateway
"""

import asyncio
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory


async def handle_whatsapp_events():
    """Listen for and handle WhatsApp events"""

    bridge = OpenClawBridgeFactory.create_bridge()
    await bridge.connect()

    # Define event handler
    async def on_message_received(payload: dict):
        """Handle incoming WhatsApp message"""
        sender = payload.get("sender")
        message = payload.get("message")
        print(f"Received from {sender}: {message}")

        # Process command
        if message.startswith("@claude"):
            command = message.replace("@claude", "").strip()
            print(f"Processing command: {command}")
            # Handle command...

    # Register event handler
    bridge.on_event("message.received", on_message_received)

    # Keep running
    print("Listening for events... Press Ctrl+C to stop")
    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")
    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(handle_whatsapp_events())
```

### Multiple Sessions

```python
"""
Managing multiple WhatsApp sessions
"""

import asyncio
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory


async def broadcast_to_multiple_sessions():
    """Send message to multiple WhatsApp sessions"""

    bridge = OpenClawBridgeFactory.create_bridge()
    await bridge.connect()

    sessions = [
        "whatsapp:self:main",
        "whatsapp:group:120363401780756402@g.us",
        "whatsapp:dm:18312950562"
    ]

    message = "Deployment successful! All systems operational."

    try:
        # Send to all sessions concurrently
        tasks = [
            bridge.send_to_agent(session, message)
            for session in sessions
        ]

        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Check results
        for session, result in zip(sessions, results):
            if isinstance(result, Exception):
                print(f"Failed to send to {session}: {result}")
            else:
                print(f"Sent to {session}: {result['message_id']}")

    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(broadcast_to_multiple_sessions())
```

### Connection Pool Pattern

```python
"""
Connection pool pattern for high-throughput scenarios
"""

import asyncio
from typing import List
from contextlib import asynccontextmanager
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory


class BridgePool:
    """Pool of OpenClaw bridge connections"""

    def __init__(self, size: int = 5):
        self.size = size
        self.pool: List = []
        self.available: asyncio.Queue = asyncio.Queue()

    async def initialize(self):
        """Initialize connection pool"""
        for i in range(self.size):
            bridge = OpenClawBridgeFactory.create_bridge()
            await bridge.connect()
            self.pool.append(bridge)
            await self.available.put(bridge)
        print(f"Connection pool initialized with {self.size} connections")

    @asynccontextmanager
    async def acquire(self):
        """Acquire connection from pool"""
        bridge = await self.available.get()
        try:
            yield bridge
        finally:
            await self.available.put(bridge)

    async def close_all(self):
        """Close all connections in pool"""
        for bridge in self.pool:
            await bridge.close()


async def use_connection_pool():
    """Example using connection pool"""

    pool = BridgePool(size=3)
    await pool.initialize()

    try:
        # Send multiple messages concurrently
        async def send_message(i: int):
            async with pool.acquire() as bridge:
                result = await bridge.send_to_agent(
                    session_key="whatsapp:self:main",
                    message=f"Message {i}"
                )
                print(f"Sent message {i}: {result['message_id']}")

        # Send 10 messages using pool of 3 connections
        await asyncio.gather(*[send_message(i) for i in range(10)])

    finally:
        await pool.close_all()


if __name__ == "__main__":
    asyncio.run(use_connection_pool())
```

---

## Best Practices

### 1. Always Close Connections

```python
# Bad
bridge = OpenClawBridgeFactory.create_bridge()
await bridge.connect()
await bridge.send_to_agent("session", "message")
# Connection left open!

# Good
bridge = OpenClawBridgeFactory.create_bridge()
try:
    await bridge.connect()
    await bridge.send_to_agent("session", "message")
finally:
    await bridge.close()
```

### 2. Use Context Managers

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def bridge_context():
    bridge = OpenClawBridgeFactory.create_bridge()
    await bridge.connect()
    try:
        yield bridge
    finally:
        await bridge.close()

# Usage
async with bridge_context() as bridge:
    await bridge.send_to_agent("session", "message")
```

### 3. Don't Block on Notification Failures

```python
# Notifications should not break main workflow
try:
    await notification_service.notify_agent_spawned(issue_number, agent_id)
except Exception as e:
    logger.error(f"Notification failed: {e}")
    # Continue with workflow
```

### 4. Validate Session Keys

```python
def validate_session_key(session_key: str) -> bool:
    """Validate before sending"""
    if not session_key or ":" not in session_key:
        return False
    parts = session_key.split(":")
    return len(parts) >= 2 and parts[0] in {"whatsapp", "agent", "slack"}

if validate_session_key(session_key):
    await bridge.send_to_agent(session_key, message)
```

---

**Maintained by**: AINative Backend Team
**Last Updated**: 2026-02-06
**Refs**: #1094
