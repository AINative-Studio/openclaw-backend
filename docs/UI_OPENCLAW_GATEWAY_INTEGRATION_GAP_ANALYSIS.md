# UI ↔ OpenClaw Gateway Integration Gap Analysis

**Date**: 2026-02-27
**Status**: Comprehensive Analysis (Corrected)

## Executive Summary

This document provides a **correct and comprehensive** analysis of the integration between the `agent-swarm-monitor` UI frontend and the OpenClaw Gateway system. Unlike previous incorrect analyses, this properly recognizes that **OpenClaw Gateway is a separate Node.js application** with extensive built-in capabilities (22 channel plugins, agent execution, WebSocket protocol) that the Python backend integrates WITH via `openclaw_bridge.py`.

## Critical Architecture Understanding

```
┌─────────────────────────────────────────────────────────────┐
│         Frontend: agent-swarm-monitor (Next.js 15)          │
│         Port: 3002, React Query for state management        │
└────────────────────┬────────────────────────────────────────┘
                     │ REST API (http://localhost:8000/api/v1)
┌────────────────────▼────────────────────────────────────────┐
│         Backend: openclaw-backend (FastAPI/Python)           │
│     Agent CRUD, OpenClaw Bridge, Monitoring Endpoints       │
└────────────────────┬────────────────────────────────────────┘
                     │ WebSocket (openclaw_bridge.py)
                     │ ws://127.0.0.1:18789
┌────────────────────▼────────────────────────────────────────┐
│             OpenClaw Gateway (Node.js v2026.2.1)             │
│    - 22 Channel Plugins (WhatsApp, Telegram, Discord, etc.) │
│    - Agent Execution with Streaming                          │
│    - DBOS Durable Workflows                                  │
│    - Device Pairing & Authentication                         │
│    - WebSocket Protocol v3                                   │
└─────────────────────────────────────────────────────────────┘
```

## Part 1: UI Features and Expectations

### 1.1 Mock Data Analysis

The UI currently uses the following mock data (from `lib/openclaw-mock-data.ts`):

| Category | Count | Mock Data Types | Usage |
|----------|-------|-----------------|-------|
| **Agents** | 5 | `MOCK_AGENTS[]` | Agent list, detail pages, selection pickers |
| **Templates** | 10 | `MOCK_TEMPLATES[]` | Template library, agent creation wizard |
| **Channels** | 5 | `MOCK_CHANNELS[]` | Channel connection UI |
| **Integrations** | 2 | `MOCK_INTEGRATIONS[]` | Integration setup UI |
| **Team Members** | 1 | `MOCK_TEAM_MEMBERS[]` | Team management |
| **API Key Providers** | 11 | `MOCK_API_KEY_PROVIDERS[]` | Settings page API key management |

### 1.2 UI Pages and Features

#### Agents Page (`/agents`)
- **Status**: ✅ Fully Integrated with Backend
- **Backend Endpoint**: `GET /api/v1/agents`
- **Features**:
  - List agents with status, model, heartbeat info
  - Create agent from template or custom configuration
  - Filter by status (running, paused, stopped)
  - Pagination (limit/offset)

#### Agent Detail Page (`/agents/[id]`)
- **Status**: ✅ Fully Integrated with Backend
- **Backend Endpoints**:
  - `GET /api/v1/agents/{id}` - Detail
  - `PATCH /api/v1/agents/{id}/settings` - Update settings
  - `POST /api/v1/agents/{id}/pause` - Pause
  - `POST /api/v1/agents/{id}/resume` - Resume
  - `DELETE /api/v1/agents/{id}` - Soft delete

#### Templates Page (`/templates`)
- **Status**: ✅ Has Backend Endpoint
- **Backend Endpoint**: `GET /api/v1/templates`
- **Features**: Browse and select agent templates

#### Channels Page (`/channels`)
- **Status**: ⚠️ **CRITICAL ARCHITECTURAL ISSUE**
- **Current Implementation**: Stores channel config in `agent.configuration.channels` object per-agent
- **Problem**: OpenClaw manages channels **globally** at gateway level, not per-agent
- **What UI Does**:
  - Shows 5 channels: WhatsApp, Telegram, Slack, Discord, MS Teams
  - Connection modals collect tokens/credentials
  - Saves to `agent.configuration.channels.{channelId}` via `PATCH /agents/{id}/settings`
  - Shows connection status per agent

#### Integrations Page (`/integrations`)
- **Status**: ❌ No Backend Integration
- **Mock Data**: Gmail, LinkedIn (coming soon)
- **Code Comment**: `// Connection logic would go here`

#### Settings Page (`/settings`)
- **Status**: ⚠️ Partially Integrated
- **Backend Endpoint**: `GET/PATCH /settings` (NEW! Created Feb 24)
- **Integrated Features**:
  - ✅ Workspace name, slug, timezone
  - ✅ Default model selection
  - ✅ Notification preferences (email, error alerts, heartbeat fail alerts, weekly digest)
- **Missing Features**:
  - ❌ API Key Management (UI has local state only)

#### Team Page (`/team`)
- **Status**: ❌ No Backend Integration
- **Mock Data**: 1 team member (owner)

## Part 2: OpenClaw Gateway Capabilities

### 2.1 Channel Plugins (22 Total)

OpenClaw Gateway has **22 built-in channel plugins** (source: `openclaw plugins list`):

| Category | Channels | Status |
|----------|----------|--------|
| **Messaging Apps** | WhatsApp, Telegram, Discord, Slack, Microsoft Teams, Signal, Matrix | ✅ Built-in |
| **Enterprise** | Google Chat, Mattermost, Nextcloud Talk | ✅ Built-in |
| **Apple Ecosystem** | iMessage, BlueBubbles | ✅ Built-in |
| **International** | LINE, Zalo, Zalo Personal | ✅ Built-in |
| **Decentralized** | Nostr, Tlon/Urbit | ✅ Built-in |
| **Other** | Twitch | ✅ Built-in |

**Currently Enabled**: WhatsApp only (per `~/.openclaw/openclaw.json`)

### 2.2 Gateway WebSocket Protocol

OpenClaw Gateway exposes a WebSocket API (`ws://127.0.0.1:18789`) with Protocol v3:

**Core Methods**:
- `connect` - Authentication handshake with device identity
- `health` - Full health snapshot
- `status` - Short summary
- `send` - Send message via active channels
- `agent` - Run agent turn (streams events back)
- `system-presence` - Current presence list
- `system-event` - Post presence/system note

**Events**:
- `agent` - Streamed tool/output from agent runs
- `presence` - Presence updates (deltas)
- `tick` - Periodic keepalive
- `shutdown` - Gateway exiting notification

**Authentication**:
- Token-based auth via `connect.params.auth.token`
- Device pairing with Ed25519 keypairs
- Role-based access: `operator` (control plane) or `node` (capability host)

### 2.3 Agent Execution

- **Method**: `agent` (WebSocket)
- **Streaming**: Events streamed back in real-time
- **Two-stage Response**:
  1. Immediate `res` ack with `{runId, status: "accepted"}`
  2. Final `res` with `{runId, status: "ok"|"error", summary}` after completion

### 2.4 Channel Management

OpenClaw Gateway manages channels via:
- **CLI**: `openclaw channels list`, `openclaw channels login`
- **Config File**: `~/.openclaw/openclaw.json` (`channels` section)
- **WebSocket API**: Channel operations via protocol methods

**Channel Configuration Example** (WhatsApp):
```json
{
  "channels": {
    "whatsapp": {
      "enabled": true,
      "sendReadReceipts": true,
      "dmPolicy": "allowlist",
      "selfChatMode": true,
      "allowFrom": ["+18312950562"],
      "groups": {
        "120363401780756402@g.us": {
          "requireMention": true
        }
      }
    }
  },
  "plugins": {
    "allow": ["whatsapp"],
    "entries": {
      "whatsapp": { "enabled": true }
    }
  }
}
```

## Part 3: Python Backend Current State

### 3.1 Existing Endpoints

| Endpoint | Methods | Purpose | Status |
|----------|---------|---------|--------|
| `/agents` | GET, POST | List, create agents | ✅ Working |
| `/agents/{id}` | GET, PATCH, DELETE | Agent detail, update, delete | ✅ Working |
| `/agents/{id}/provision` | POST | Provision agent via DBOS | ✅ Working |
| `/agents/{id}/pause` | POST | Pause agent | ✅ Working |
| `/agents/{id}/resume` | POST | Resume agent | ✅ Working |
| `/agents/{id}/heartbeat` | POST | Execute heartbeat | ✅ Working |
| `/agents/{id}/message` | POST | Send message to agent | ✅ Working |
| `/openclaw/status` | GET | Gateway connection status | ✅ Working |
| `/templates` | GET, POST | Template management | ✅ Working |
| `/swarms` | GET, POST | Swarm management | ✅ Working |
| `/metrics` | GET | Prometheus metrics | ✅ Working |
| `/swarm/health` | GET | Health snapshot | ✅ Working |
| `/swarm/timeline` | GET | Task timeline events | ✅ Working |
| `/swarm/alerts/thresholds` | GET, PUT | Alert configuration | ✅ Working |
| `/settings` | GET, PATCH | Workspace settings | ✅ NEW (Feb 24) |

### 3.2 OpenClaw Bridge Integration

File: `integrations/openclaw_bridge.py`

**Purpose**: WebSocket client implementing OpenClaw Gateway Protocol v3

**Features**:
- Connection with authentication handshake
- Send messages to agent sessions
- Handles `connect.challenge` nonce verification
- Exponential backoff reconnection
- Error handling and logging

**Key Methods**:
- `async def connect()` - Establish WebSocket connection
- `async def send_to_agent(session_key, message, metadata)` - Send message to agent
- Auto-retry with backoff on connection failures

## Part 4: Integration Gaps

### 4.1 CRITICAL: Channel Management Architecture Issue

**Problem**: The UI stores channel configuration in `agent.configuration.channels` per-agent, but OpenClaw Gateway manages channels **globally** at the gateway level, not per-agent.

**Current UI Flow (INCORRECT)**:
1. User clicks "Connect WhatsApp" for Agent A
2. Modal collects phone number
3. Saves to `agent.configuration.channels.whatsapp = {enabled: true, phoneNumber: "..."}`
4. Calls `PATCH /agents/{agent-a-id}/settings` with updated configuration

**Correct Flow Should Be**:
1. User clicks "Connect WhatsApp" (global action, not per-agent)
2. Backend calls OpenClaw Gateway to enable WhatsApp channel
3. WhatsApp channel becomes available to ALL agents
4. Agents can reference the channel, not store credentials

**Why This Matters**:
- Multiple agents can't have separate WhatsApp connections (one phone number = one connection)
- Channel state lives in OpenClaw Gateway (`~/.openclaw/openclaw.json`), not agent DB
- Credentials (bot tokens, phone numbers) should not be in agent configuration

**Required Architecture Change**:
- Channels should be managed globally in workspace settings, not per-agent
- UI should show "Available Channels" list (from Gateway) that agents can use
- Channel connection flow should call OpenClaw Gateway API, not agent settings API

### 4.2 Missing Backend Endpoints

#### 4.2.1 Global Channel Management

**Needed**:
- `GET /channels` - List all available channels from OpenClaw Gateway
  - Returns: Channel ID, name, description, connected status, plugin enabled/disabled
  - Source: `openclaw plugins list` + `openclaw channels list`

- `POST /channels/{channelId}/enable` - Enable and configure channel
  - For WhatsApp: Trigger QR code generation, return QR data
  - For Token-based (Telegram, Discord, Slack): Accept bot token, call OpenClaw to configure
  - Updates `~/.openclaw/openclaw.json` via OpenClaw CLI or Gateway API

- `DELETE /channels/{channelId}` - Disable channel
  - Calls OpenClaw to disable channel

- `GET /channels/{channelId}/status` - Get channel connection status
  - Returns: Connected, last activity, error state

**Implementation Approach**:
Python backend should proxy OpenClaw CLI commands:
```python
# Example: Enable Telegram channel
async def enable_telegram_channel(bot_token: str):
    # Option 1: Use OpenClaw CLI via subprocess
    result = subprocess.run([
        'openclaw', 'config', 'set',
        'channels.telegram.botToken', bot_token
    ], capture_output=True)

    # Option 2: Directly modify ~/.openclaw/openclaw.json
    config_path = Path.home() / '.openclaw' / 'openclaw.json'
    config = json.loads(config_path.read_text())
    config['channels']['telegram'] = {
        'enabled': True,
        'botToken': bot_token
    }
    config['plugins']['entries']['telegram'] = {'enabled': True}
    config_path.write_text(json.dumps(config, indent=2))

    # Option 3: Call Gateway WebSocket API (if method exists)
    await gateway_client.call('config.update', {
        'channels.telegram.enabled': True,
        'channels.telegram.botToken': bot_token
    })
```

#### 4.2.2 API Key Management

**Needed**:
- `GET /api-keys` - List configured API key providers
- `POST /api-keys` - Add API key for provider
- `DELETE /api-keys/{provider}` - Remove API key

**Storage**: Could be in workspace settings table or separate `api_keys` table

#### 4.2.3 Team Management

**Needed**:
- `GET /team/members` - List team members
- `POST /team/members` - Invite member
- `DELETE /team/members/{id}` - Remove member
- `PATCH /team/members/{id}/role` - Update member role

**Storage**: New `team_members` table

#### 4.2.4 Integrations (Gmail, LinkedIn)

**Status**: Marked as "Coming Soon" in UI mock data. No immediate implementation needed.

### 4.3 UI Changes Required

#### 4.3.1 Channels Page Refactor

**Current**: Channels stored per-agent in `agent.configuration.channels`

**Required**:
1. Remove agent selection from channels page (channels are global)
2. Call `GET /channels` to list available channels with status
3. Connection modals should call `POST /channels/{channelId}/enable`
4. Show global channel status (not per-agent)
5. Remove channel config from agent settings update

**Migration Path**:
- Check if any agents have `configuration.channels` data
- Warn user that channel config will move to workspace level
- Provide migration tool to extract credentials and configure globally

#### 4.3.2 Settings Page Integration

**Current**: API keys stored in local React state only

**Required**:
1. Fetch API keys from `GET /api-keys` on page load
2. Add API key → call `POST /api-keys`
3. Remove API key → call `DELETE /api-keys/{provider}`
4. Show configured status from backend, not local state

#### 4.3.3 Team Page Integration

**Current**: Hardcoded mock data

**Required**:
1. Fetch team members from `GET /team/members`
2. Invite member → call `POST /team/members`
3. Remove member → call `DELETE /team/members/{id}`

## Part 5: Frontend Gap Analysis

### 5.1 UI Elements Needed for Backend Features

The backend has several features that the UI doesn't expose:

#### 5.1.1 WireGuard P2P Networking

**Backend Endpoints**:
- `GET /wireguard/health` - Network health metrics
- `GET /wireguard/quality` - Network quality
- `POST /wireguard/provision` - Provision peer
- `GET /wireguard/peers` - List peers
- `DELETE /wireguard/peers/{node_id}` - Remove peer
- `GET /wireguard/pool/stats` - IP pool statistics

**UI Gap**: No page or component for P2P network management

**Recommendation**: Create `/network` page showing:
- Peer list with connection status
- Network quality metrics
- Provision new peer form

#### 5.1.2 Task Queue and Lease Management

**Backend Features** (from P2P protocols):
- Task assignment with leases
- Task progress tracking
- Task failure handling
- Lease expiration monitoring
- Result buffering during partitions

**UI Gap**: No visibility into task queue, leases, or P2P task distribution

**Recommendation**: Create `/tasks` page showing:
- Active tasks and their assigned peers
- Task history (completed, failed, expired)
- Lease status and expiration times
- Buffered results (during partition)

#### 5.1.3 Security and Capability Tokens

**Backend Features** (Epic E7):
- Capability token issuance
- Message signing/verification with Ed25519
- Peer key store
- Token rotation and revocation
- Security audit logging

**UI Gap**: No security management interface

**Recommendation**: Create `/security` page showing:
- Active capability tokens
- Token rotation controls
- Audit log viewer
- Peer public keys management

#### 5.1.4 Monitoring and Observability

**Backend Endpoints**:
- `GET /metrics` - Prometheus metrics
- `GET /swarm/health` - Health snapshot
- `GET /swarm/timeline` - Task timeline
- `GET /swarm/alerts/thresholds` - Alert thresholds
- `GET /swarm/monitoring/status` - Monitoring infrastructure health

**UI Gap**: Monitoring page exists (`/monitoring`) but may not utilize all available endpoints

**Recommendation**: Enhance `/monitoring` page to show:
- Prometheus metrics visualization
- Real-time health status dashboard
- Task timeline with filters
- Alert threshold configuration UI

## Part 6: Implementation Priority

### Phase 1: Critical Fixes (Week 1-2)

1. **Fix Channels Architecture** (CRITICAL)
   - Create `/channels` backend endpoints (list, enable, disable, status)
   - Refactor UI channels page to use global channel API
   - Migrate any existing per-agent channel configs

2. **Integrate Settings API**
   - Connect UI settings page to existing `/settings` endpoints
   - Implement API key management backend + UI integration

### Phase 2: Core Features (Week 3-4)

3. **Team Management**
   - Create `/team/members` backend endpoints
   - Integrate UI team page

4. **Enhanced Monitoring**
   - Enhance `/monitoring` page to show Prometheus metrics
   - Add task timeline visualization

### Phase 3: Advanced Features (Week 5-6)

5. **P2P Network Management**
   - Create `/network` UI page for WireGuard peer management
   - Expose network health and quality metrics

6. **Task Queue Visibility**
   - Create `/tasks` UI page
   - Show task distribution, leases, and history

### Phase 4: Security (Week 7-8)

7. **Security Management**
   - Create `/security` UI page
   - Token management, audit log viewer

## Part 7: Technical Recommendations

### 7.1 OpenClaw Gateway Proxy Pattern

Instead of directly calling OpenClaw CLI or modifying config files, create a **Gateway Proxy Service** in Python backend:

**File**: `backend/services/openclaw_gateway_proxy.py`

```python
class OpenClawGatewayProxy:
    """
    Proxy service for OpenClaw Gateway operations.
    Provides high-level methods that abstract OpenClaw CLI/config management.
    """

    def __init__(self, config_path: Path = Path.home() / '.openclaw' / 'openclaw.json'):
        self.config_path = config_path
        self.gateway_url = os.getenv('OPENCLAW_GATEWAY_URL', 'ws://127.0.0.1:18789')

    async def list_channels(self) -> List[ChannelInfo]:
        """List all available channels from OpenClaw"""

    async def enable_channel(self, channel_id: str, config: Dict[str, Any]):
        """Enable and configure a channel"""

    async def disable_channel(self, channel_id: str):
        """Disable a channel"""

    async def get_channel_status(self, channel_id: str) -> ChannelStatus:
        """Get channel connection status"""
```

### 7.2 Channel Configuration Storage

**Do NOT** store channel credentials in agent configuration. Instead:

1. **Option A**: Store in workspace settings table
   - Add `channel_configs` JSON column to `workspace_settings` table
   - Encrypted at rest (use `cryptography` library)

2. **Option B**: Manage via OpenClaw Gateway directly
   - OpenClaw stores in `~/.openclaw/openclaw.json`
   - Backend reads/writes this file with proper permissions
   - Backend triggers Gateway config reload after changes

**Recommendation**: Option B (let OpenClaw be source of truth)

### 7.3 WebSocket vs REST for Gateway

For real-time operations (agent execution, channel messaging), use the existing `openclaw_bridge.py` WebSocket client.

For configuration operations (enable/disable channels), either:
- Use WebSocket if Gateway exposes config methods
- Use CLI commands via subprocess
- Directly modify `openclaw.json` file

**Recommendation**: Start with CLI/file approach, migrate to WebSocket if Gateway adds config methods

## Appendix A: OpenClaw Gateway Installed Plugins

Output from `openclaw plugins list`:

| Plugin ID | Name | Status | Version |
|-----------|------|--------|---------|
| whatsapp | WhatsApp | ✅ loaded | 2026.2.1 |
| telegram | @openclaw/telegram | disabled | 2026.2.1 |
| discord | @openclaw/discord | disabled | 2026.2.1 |
| slack | @openclaw/slack | disabled | 2026.2.1 |
| googlechat | @openclaw/googlechat | disabled | 2026.2.1 |
| imessage | @openclaw/imessage | disabled | 2026.2.1 |
| bluebubbles | @openclaw/bluebubbles | disabled | 2026.2.1 |
| msteams | @openclaw/msteams | disabled | 2026.2.1 |
| signal | @openclaw/signal | disabled | 2026.2.1 |
| line | @openclaw/line | disabled | 2026.2.1 |
| matrix | @openclaw/matrix | disabled | 2026.2.1 |
| mattermost | @openclaw/mattermost | disabled | 2026.2.1 |
| nostr | @openclaw/nostr | disabled | 2026.2.1 |
| nextcloud-talk | @openclaw/nextcloud-talk | disabled | 2026.2.1 |
| tlon | @openclaw/tlon | disabled | 2026.2.1 |
| twitch | @openclaw/twitch | disabled | 2026.2.1 |
| zalo | @openclaw/zalo | disabled | 2026.2.1 |
| zalouser | @openclaw/zalouser | disabled | 2026.2.1 |
| voice-call | @openclaw/voice-call | disabled | 2026.2.1 |
| memory-core | @openclaw/memory-core | disabled | 2026.2.1 |
| memory-lancedb | @openclaw/memory-lancedb | disabled | 2026.2.1 |
| llm-task | LLM Task | disabled | 2026.2.1 |

## Appendix B: OpenClaw Gateway Configuration File

Location: `~/.openclaw/openclaw.json`

**Current Configuration** (WhatsApp enabled):
```json
{
  "gateway": {
    "port": 18789,
    "mode": "local",
    "bind": "loopback",
    "auth": {
      "mode": "token",
      "token": "7ae5aa8730848791e5a017fe95b80ad26f8c31d90e7b9ab60f5f8974d6519fc1"
    }
  },
  "channels": {
    "whatsapp": {
      "sendReadReceipts": true,
      "dmPolicy": "allowlist",
      "selfChatMode": true,
      "allowFrom": ["+18312950562", "+18312951482"],
      "groups": {
        "120363401780756402@g.us": {
          "requireMention": true
        }
      }
    }
  },
  "plugins": {
    "allow": ["whatsapp"],
    "entries": {
      "whatsapp": { "enabled": true }
    }
  }
}
```

## Appendix C: Existing Backend API Summary

**Agent Lifecycle** (`/agents`):
- ✅ Full CRUD operations
- ✅ Provision via OpenClaw DBOS
- ✅ Pause/Resume
- ✅ Heartbeat execution
- ✅ Message sending

**OpenClaw Status** (`/openclaw`):
- ✅ Connection monitoring
- ✅ Command history
- ✅ Gateway uptime

**Workspace Settings** (`/settings`):
- ✅ Workspace name, slug, timezone
- ✅ Default model
- ✅ Notification preferences

**Monitoring** (`/metrics`, `/swarm/*`):
- ✅ Prometheus metrics
- ✅ Health snapshot
- ✅ Task timeline
- ✅ Alert thresholds

**Templates** (`/templates`):
- ✅ Template CRUD

**Swarms** (`/swarms`):
- ✅ Swarm management

**WireGuard** (`/wireguard/*`):
- ✅ Peer provisioning
- ✅ Health monitoring
- ✅ Network quality metrics

## Conclusion

The primary integration gap is the **incorrect channel management architecture** where the UI treats channels as per-agent configuration instead of global workspace-level resources managed by OpenClaw Gateway. Fixing this requires:

1. Creating new `/channels` backend endpoints that proxy OpenClaw Gateway operations
2. Refactoring the UI channels page to remove per-agent channel configuration
3. Moving channel credentials to global workspace settings or OpenClaw config file

Secondary gaps include missing backend endpoints for API key management and team management, plus missing UI pages for advanced backend features (P2P networking, task queue, security management).

The good news: **OpenClaw Gateway already has all the channel capabilities the UI expects**. We just need to wire them up correctly through the Python backend instead of storing them in agent configuration.

---

**Next Steps**:
1. Review this analysis with team
2. Prioritize Phase 1 critical fixes (channels architecture)
3. Create GitHub issues for each endpoint/feature
4. Start implementation with channels refactor
