# OpenClaw Bridge Quick Reference

One-page reference for developers using the OpenClaw bridge.

**Refs**: #1094

---

## Quick Start

```python
from app.agents.orchestration.openclaw_bridge_factory import OpenClawBridgeFactory

# Create and connect
bridge = OpenClawBridgeFactory.create_bridge()
await bridge.connect()

# Send message
result = await bridge.send_to_agent(
    session_key="whatsapp:group:120363401780756402@g.us",
    message="Agent spawned for issue #1234"
)

# Close connection
await bridge.close()
```

---

## Session Key Format

`{channel}:{type}:{identifier}`

| Session Key | Description |
|------------|-------------|
| `whatsapp:group:120363401780756402@g.us` | WhatsApp group |
| `whatsapp:dm:18312950562` | WhatsApp DM |
| `whatsapp:self:main` | WhatsApp self-chat |
| `agent:whatsapp:main` | Agent session |

---

## Environment Variables

```bash
OPENCLAW_GATEWAY_URL="ws://127.0.0.1:18789"
OPENCLAW_GATEWAY_TOKEN="your-token-here"
OPENCLAW_WHATSAPP_SESSION_KEY="whatsapp:group:..."
ENVIRONMENT="development|testing|staging|production"
```

---

## Error Handling

```python
from app.agents.orchestration.openclaw_bridge_protocol import (
    ConnectionError,
    SendError,
    SessionError
)

try:
    await bridge.connect()
    await bridge.send_to_agent(session_key, message)
except ConnectionError as e:
    logger.error(f"Connection failed: {e}")
except SessionError as e:
    logger.error(f"Invalid session: {e}")
except SendError as e:
    logger.error(f"Send failed: {e}")
finally:
    await bridge.close()
```

---

## Testing

```python
from app.agents.orchestration.mock_openclaw_bridge import MockOpenClawBridge

# Create mock bridge
mock_bridge = MockOpenClawBridge()
await mock_bridge.connect()

# Send test message
await mock_bridge.send_to_agent("session", "message")

# Assert
messages = mock_bridge.get_sent_messages()
assert len(messages) == 1
assert "message" in messages[0]["message"]
```

---

## Notification Service Integration

```python
from app.agents.orchestration.notification_service import NotificationService

# Create notification service
notification_service = NotificationService(
    openclaw_bridge=bridge,
    whatsapp_session_key="whatsapp:group:..."
)

# Send notifications
await notification_service.notify_agent_spawned(1234, "agent_id")
await notification_service.notify_work_started(1234, "agent_id", "Fix bug")
await notification_service.notify_pr_created(1234, 5678, "https://...")
await notification_service.notify_error(1234, "Error message")
```

---

## Files

| File | Purpose |
|------|---------|
| `openclaw_bridge_protocol.py` | Protocol interface |
| `production_openclaw_bridge.py` | Production implementation |
| `mock_openclaw_bridge.py` | Test mock |
| `openclaw_bridge_factory.py` | Factory pattern |
| `test_openclaw_bridge_integration.py` | BDD tests |

---

## Common Commands

```bash
# Check OpenClaw Gateway status
openclaw gateway status

# View logs
tail -f ~/.openclaw/logs/gateway.log

# Run tests
cd src/backend
python3 -m pytest tests/agents/orchestration/test_openclaw_bridge_integration.py -v

# Check WhatsApp connection
openclaw status
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection failed | Check `openclaw gateway status` |
| Send failed | Verify session key format |
| No messages | Check WhatsApp connection: `openclaw status` |
| Tests failing | Check OPENCLAW env vars are set |

---

## Best Practices

1. **Always close connections**: Use try/finally or context managers
2. **Don't block on notifications**: Catch exceptions, log, continue
3. **Validate session keys**: Check format before sending
4. **Use factory in production**: Let factory handle environment
5. **Use mock in tests**: Never use real bridge in unit tests

---

## More Information

- **Full Specification**: `docs/integration/OPENCLAW_BRIDGE_INTERFACE_SPECIFICATION.md`
- **Usage Examples**: `docs/integration/OPENCLAW_BRIDGE_USAGE_EXAMPLES.md`
- **Implementation Summary**: `docs/integration/OPENCLAW_BRIDGE_IMPLEMENTATION_SUMMARY.md`
- **OpenClaw Docs**: https://docs.openclaw.ai/

---

**Last Updated**: 2026-02-06 | **Refs**: #1094
