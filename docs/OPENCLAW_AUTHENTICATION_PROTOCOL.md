# OpenClaw Gateway Authentication Protocol Implementation

**Last Updated**: February 24, 2026
**Status**: ✅ PRODUCTION READY
**Protocol Version**: 3

## Overview

This document describes the production-ready implementation of OpenClaw Gateway Protocol v3 for agent-to-agent communication in the AINative platform. The implementation replaces simulated responses with proper WebSocket authentication and message routing.

## What Changed

### Before (Bandaid Fix - REJECTED)
- ❌ Fake responses based on agent names
- ❌ No real communication with OpenClaw Gateway
- ❌ Not production-ready
- ❌ Unsuitable for customer-facing applications

### After (Proper Fix - IMPLEMENTED)
- ✅ Full OpenClaw Gateway Protocol v3 implementation
- ✅ Proper authentication handshake with token validation
- ✅ Production-ready error handling and logging
- ✅ Uses official `agent` method for sending messages
- ✅ Connection lifecycle management
- ✅ Validated against official OpenClaw Gateway

## Architecture

### Components

```
┌─────────────────────┐
│   Frontend (React)  │
│   AgentChatTab.tsx  │
└──────────┬──────────┘
           │ POST /api/v1/agents/{id}/message
           ▼
┌─────────────────────┐
│   FastAPI Backend   │
│ agent_lifecycle.py  │
└──────────┬──────────┘
           │ await send_message_to_agent()
           ▼
┌─────────────────────┐
│ OpenClawBridge.py   │
│ Protocol v3 Client  │
└──────────┬──────────┘
           │ WebSocket (ws://)
           ▼
┌─────────────────────┐
│  OpenClaw Gateway   │
│  Port 18789         │
└─────────────────────┘
```

## OpenClaw Gateway Protocol v3 Handshake

### Step-by-Step Authentication Flow

```
1. Client connects to ws://127.0.0.1:18789
   └─> WebSocket connection established

2. Gateway → Client: connect.challenge event
   {
     "type": "event",
     "event": "connect.challenge",
     "payload": {
       "nonce": "bb374aae-e1e7-4e1f-8845-44f58c1222ab",
       "ts": 1771963182820
     }
   }

3. Client → Gateway: connect request
   {
     "type": "req",
     "id": "unique-uuid",
     "method": "connect",
     "params": {
       "minProtocol": 3,
       "maxProtocol": 3,
       "client": {
         "id": "gateway-client",         // Must be from GATEWAY_CLIENT_IDS
         "version": "1.0.0",
         "platform": "darwin|linux|windows",
         "mode": "backend"                // Must be from GATEWAY_CLIENT_MODES
       },
       "role": "operator",
       "scopes": ["operator.read", "operator.write"],
       "auth": {
         "token": "7ae5aa8730848791e5a017fe95b80ad26f8c31d90e7b9ab60f5f8974d6519fc1"
       }
     }
   }

4. Gateway → Client: hello-ok response
   {
     "type": "res",
     "id": "matching-uuid",
     "ok": true,
     "payload": {
       "type": "hello-ok",
       "protocol": 3,
       "policy": {"tickIntervalMs": 15000}
     }
   }

5. Connection established ✅
   └─> Client can now send agent messages
```

### Valid Client IDs (from GATEWAY_CLIENT_IDS)

```javascript
GATEWAY_CLIENT_IDS = {
    WEBCHAT_UI: "webchat-ui",
    CONTROL_UI: "openclaw-control-ui",
    WEBCHAT: "webchat",
    CLI: "cli",
    GATEWAY_CLIENT: "gateway-client",    // ← We use this
    MACOS_APP: "openclaw-macos",
    IOS_APP: "openclaw-ios",
    ANDROID_APP: "openclaw-android",
    NODE_HOST: "node-host",
    TEST: "test",
    FINGERPRINT: "fingerprint",
    PROBE: "openclaw-probe"
}
```

### Valid Client Modes (from GATEWAY_CLIENT_MODES)

```javascript
GATEWAY_CLIENT_MODES = {
    WEBCHAT: "webchat",
    CLI: "cli",
    UI: "ui",
    BACKEND: "backend",                  // ← We use this
    NODE: "node",
    PROBE: "probe",
    TEST: "test"
}
```

## Implementation Details

### File: `integrations/openclaw_bridge.py`

**Key Classes:**
```python
class OpenClawBridge:
    """Production-ready WebSocket bridge to OpenClaw Gateway"""

    PROTOCOL_VERSION = 3
    CLIENT_ID = "gateway-client"
    CLIENT_MODE = "backend"

    async def connect(self) -> None:
        """Performs full authentication handshake"""
        # 1. Connect WebSocket
        # 2. Wait for connect.challenge event (10s timeout)
        # 3. Send connect request with token
        # 4. Wait for hello-ok response (10s timeout)
        # 5. Mark connected

    async def send_to_agent(self, session_key: str, message: str) -> Dict:
        """Send message using agent method from protocol"""
        # Uses agent method, not raw message objects
```

**Custom Exceptions:**
- `OpenClawBridgeError` - Base exception
- `OpenClawAuthenticationError` - Handshake failures
- `OpenClawProtocolError` - Version mismatches

### File: `backend/services/agent_lifecycle_api_service.py`

**Method: `send_message_to_agent()`**
```python
async def send_message_to_agent(self, agent_id: str, message: str) -> dict:
    """Send message via OpenClaw Gateway with proper authentication"""

    # 1. Validate agent exists and is running
    # 2. Check agent has openclaw_session_key
    # 3. Convert http:// → ws:// if needed
    # 4. Create bridge client
    # 5. Connect with authentication
    # 6. Send message to agent
    # 7. Always close connection (stateless)

    return {
        "response": result.get("summary", ""),
        "status": result.get("status"),
        "runId": result.get("runId"),
        "messageId": result.get("messageId")
    }
```

### File: `backend/api/v1/endpoints/agent_lifecycle.py`

**Endpoint: `POST /api/v1/agents/{agent_id}/message`**
```python
@router.post("/{agent_id}/message")
async def send_message(agent_id: str, request: SendMessageRequest, db: Session):
    """Send message to agent via OpenClaw Gateway"""

    # Validates:
    # - Agent exists
    # - Agent is provisioned (has session key)
    # - Agent is running

    result = await service.send_message_to_agent(agent_id, request.message)

    return SendMessageResponse(
        response=result.get("response"),
        agent_id=agent_id,
        message_id=result.get("messageId")
    )
```

## Environment Configuration

### Required Environment Variables

```bash
# OpenClaw Gateway WebSocket URL
# Will be auto-converted: http:// → ws://, https:// → wss://
OPENCLAW_GATEWAY_URL="ws://127.0.0.1:18789"

# Authentication token (must match gateway configuration)
# Get from ~/.openclaw/openclaw.json under gateway.auth.token
OPENCLAW_GATEWAY_TOKEN="7ae5aa8730848791e5a017fe95b80ad26f8c31d90e7b9ab60f5f8974d6519fc1"
```

### Finding Your Gateway Token

```bash
# Extract token from OpenClaw config
cat ~/.openclaw/openclaw.json | \
  python3 -m json.tool | \
  grep -A 3 "gateway.*auth" | \
  grep token

# Output:
# "token": "7ae5aa8730848791e5a017fe95b80ad26f8c31d90e7b9ab60f5f8974d6519fc1"
```

## Testing

### 1. Start OpenClaw Gateway

```bash
# Check if running
lsof -i :18789

# If not running, start it
openclaw gateway --port 18789

# Or check status
openclaw gateway status
```

### 2. Start Backend with Correct Token

```bash
export SECRET_KEY="dev-secret-key-for-local-testing"
export OPENCLAW_GATEWAY_URL="http://localhost:18789"
export OPENCLAW_GATEWAY_TOKEN="7ae5aa8730848791e5a017fe95b80ad26f8c31d90e7b9ab60f5f8974d6519fc1"
export ENVIRONMENT="development"
export DATABASE_URL="sqlite:///./openclaw.db"

python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Test Message Endpoint

```bash
curl -X POST http://localhost:8000/api/v1/agents/{AGENT_ID}/message \
  -H "Content-Type: application/json" \
  -d '{"message": "Hello! Can you respond?"}'

# Expected response:
# {
#   "response": "",
#   "agent_id": "...",
#   "message_id": "..."
# }
```

### 4. Test via Frontend

1. Navigate to agent detail page
2. Click "Chat" tab
3. Send message
4. Check browser DevTools Network tab for successful POST request
5. Check backend logs for connection flow

## Troubleshooting

### Error: "invalid connect params: client.id must match constant"

**Cause**: Using invalid client ID
**Fix**: Use `"gateway-client"` or another valid ID from `GATEWAY_CLIENT_IDS`

```python
CLIENT_ID = "gateway-client"  # ✅ Valid
CLIENT_ID = "ainative-backend"  # ❌ Invalid
```

### Error: "unauthorized: gateway token mismatch"

**Cause**: Wrong authentication token
**Fix**: Get actual token from OpenClaw config

```bash
# Get correct token
cat ~/.openclaw/openclaw.json | python3 -m json.tool | grep -A 3 "auth"

# Update environment variable
export OPENCLAW_GATEWAY_TOKEN="<actual-token-here>"
```

### Error: "No hello-ok response received from gateway"

**Possible Causes**:
1. Gateway not running on port 18789
2. Wrong client ID or mode
3. Token mismatch
4. Network connectivity issue

**Debug Steps**:
```bash
# 1. Check gateway is running
lsof -i :18789

# 2. Check gateway logs
openclaw logs --follow

# 3. Enable debug logging in bridge
logger.setLevel(logging.DEBUG)

# 4. Test with OpenClaw CLI first
openclaw gateway status
```

### Error: "http://localhost:18789 isn't a valid URI: scheme isn't ws or wss"

**Cause**: Environment variable uses `http://` instead of `ws://`
**Fix**: Auto-conversion is implemented in code, but can manually set:

```bash
export OPENCLAW_GATEWAY_URL="ws://localhost:18789"  # ✅ Correct
export OPENCLAW_GATEWAY_URL="http://localhost:18789"  # ⚠️ Will be auto-converted
```

## Production Deployment

### Railway/Cloud Deployment

```bash
# Set environment variables in Railway dashboard:
OPENCLAW_GATEWAY_URL=wss://your-gateway-domain.com
OPENCLAW_GATEWAY_TOKEN=<your-production-token>

# If using Tailscale for secure Gateway access:
OPENCLAW_GATEWAY_URL=ws://100.x.x.x:18789
```

### Security Considerations

1. **Token Storage**: Never commit tokens to git. Use environment variables or secret management.

2. **TLS/SSL**: Use `wss://` (WebSocket Secure) in production.

3. **Network Security**: Consider Tailscale VPN or firewall rules to restrict gateway access.

4. **Token Rotation**: Implement periodic token rotation in production.

## References

- **OpenClaw Gateway Protocol Docs**: `/Users/aideveloper/.local/share/fnm/node-versions/v22.21.0/installation/lib/node_modules/openclaw/docs/gateway/protocol.md`
- **OpenClaw Installation**: `/Users/aideveloper/.local/share/fnm/node-versions/v22.21.0/installation/lib/node_modules/openclaw/`
- **OpenClaw Version**: 2026.2.1
- **Protocol Version**: 3

## Changelog

### 2026-02-24 - Production Implementation
- ✅ Implemented proper Protocol v3 handshake
- ✅ Added authentication token validation
- ✅ Replaced simulated responses with real gateway communication
- ✅ Added structured logging and error handling
- ✅ Validated against OpenClaw Gateway v2026.2.1
- ✅ Tested end-to-end message flow
- ✅ Documented authentication protocol
- ✅ Updated environment configuration

### Before 2026-02-24 - Bandaid Fix (REMOVED)
- ❌ Used simulated responses
- ❌ No real gateway communication
- ❌ Not production-ready
