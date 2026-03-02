# UI Integration Issues - Investigation Summary

**Date**: March 1, 2026
**Reporter**: User Investigation
**Repositories**: openclaw-backend, agent-swarm-monitor

## Overview

Comprehensive investigation of UI integration issues between the frontend dashboard and OpenClaw backend/gateway services. This document tracks all identified issues and their resolution status.

---

## Issue 1: Chat Returns Simulated Response Instead of Real LLM

**Severity**: HIGH
**Status**: Identified
**Repository**: agent-swarm-monitor
**Related Issue**: agent-swarm-monitor #27

### Problem
The chat interface returns hardcoded simulated responses instead of calling the real LLM API.

**Location**: `/Users/aideveloper/agent-swarm-monitor/components/openclaw/AgentChatTab.tsx:46-54`

```typescript
// Current implementation:
const assistantMessage: ChatMessage = {
  id: `msg-${Date.now()}-reply`,
  role: 'assistant',
  content: `This is a simulated response from ${agent.name}. In production, this would connect to the OpenClaw agent API.`,
  timestamp: new Date().toISOString(),
};
```

### Root Cause
- Frontend uses setTimeout with hardcoded mock response
- Real API endpoint exists in backend: `POST /api/v1/agents/{agent_id}/message` (agent_lifecycle.py:364-396)
- Service method exists: `openClawService.sendMessage()` (lib/openclaw-service.ts:59-61)
- Just needs to be connected

### Solution
Replace the setTimeout mock with real API call:

```typescript
// Replace lines 45-54 with:
try {
  const response = await openClawService.sendMessage(agent.id, {
    message: trimmed
  });
  const assistantMessage: ChatMessage = {
    id: response.message_id || `msg-${Date.now()}-reply`,
    role: 'assistant',
    content: response.response || 'No response received',
    timestamp: new Date().toISOString(),
  };
  setMessages((prev) => [...prev, assistantMessage]);
} catch (error) {
  // Handle error
}
```

### Prerequisites
- Agent must be provisioned (have `openclaw_session_key`)
- OpenClaw Gateway must be running on port 18789

### Related Files
- Frontend: `components/openclaw/AgentChatTab.tsx`
- Service: `lib/openclaw-service.ts`
- Backend: `backend/api/v1/endpoints/agent_lifecycle.py`
- Backend: `backend/services/agent_lifecycle_api_service.py`

---

## Issue 2: Channel Connect Buttons Non-Functional

**Severity**: MEDIUM
**Status**: Identified
**Repository**: Both (openclaw-backend, agent-swarm-monitor)
**Related Issue**: openclaw-backend #98, agent-swarm-monitor #28

### Problem
Channel connect buttons exist but don't actually connect channels. No backend implementation for channel connection flows.

**Location**: `/Users/aideveloper/agent-swarm-monitor/components/openclaw/ChannelRow.tsx`

### CRITICAL DISCOVERY: OpenClaw Has Built-In Channel Plugins

**OpenClaw already has 30 channel plugins** - we should NOT build custom backends!

**Available Plugins** (via `openclaw plugins list`):
- @openclaw/whatsapp (currently LOADED ✅)
- @openclaw/telegram (disabled)
- @openclaw/discord (disabled)
- @openclaw/slack (disabled)
- @openclaw/msteams (Microsoft Teams, disabled)
- @openclaw/signal, @openclaw/matrix, @openclaw/googlechat, etc.

**Plugin Locations**:
```
~/.local/share/fnm/node-versions/v22.21.0/installation/lib/node_modules/openclaw/extensions/
├── whatsapp/index.ts (loaded)
├── telegram/index.ts (disabled)
├── discord/index.ts (disabled)
├── slack/index.ts (disabled)
├── msteams/index.ts (disabled)
└── ... (25 more plugins)
```

**CLI Commands**:
```bash
openclaw plugins list                    # List all 30 plugins
openclaw plugins enable telegram         # Enable a plugin
openclaw plugins disable telegram        # Disable a plugin
openclaw plugins info telegram           # Get plugin details
```

**Configuration**: `~/.openclaw/openclaw.json`
```json
{
  "plugins": {
    "allow": ["whatsapp"],
    "entries": {
      "whatsapp": {
        "enabled": true
      }
    }
  }
}
```

### Current State
- Buttons have proper onClick handlers ✅
- `onConnect` prop is passed correctly ✅
- Backend lists channels via `GET /api/v1/channels` ✅
- OpenClaw has 30 built-in channel plugins ✅
- **BUT**: No backend integration with OpenClaw plugin system ❌

### Channels Listed
1. WhatsApp
2. Telegram
3. Discord
4. Slack
5. Email
6. SMS
7. Microsoft Teams

### Missing Backend Implementation

Each channel needs:

#### WhatsApp
- QR code generation endpoint
- WebSocket for QR code updates
- Session persistence
- Multi-device support

#### Telegram
- Bot token validation endpoint
- Webhook configuration
- Bot info retrieval

#### Slack
- OAuth flow endpoints
- Workspace selection
- Socket mode or Events API setup

#### Discord
- Bot token validation
- Server/channel selection
- Permissions setup

#### Email (SMTP/IMAP)
- Credential validation
- Connection testing
- Folder mapping

#### SMS
- Provider selection (Twilio, Vonage, etc.)
- API key validation
- Phone number verification

#### Microsoft Teams
- OAuth flow
- Tenant selection
- Bot Framework integration

### Solution Approach

**UPDATED APPROACH**: Use OpenClaw CLI plugin system instead of building custom backends.

1. **Backend Service** (openclaw-backend):
   ```python
   # backend/services/openclaw_plugin_service.py

   class OpenClawPluginService:
       """Interface to OpenClaw CLI plugin system"""

       async def enable_plugin(self, plugin_id: str, config: dict):
           # Execute: openclaw plugins enable {plugin_id}
           # Update ~/.openclaw/openclaw.json with config

       async def disable_plugin(self, plugin_id: str):
           # Execute: openclaw plugins disable {plugin_id}

       async def get_plugin_info(self, plugin_id: str):
           # Execute: openclaw plugins info {plugin_id}
   ```

2. **Backend APIs** (openclaw-backend):
   ```python
   # backend/api/v1/endpoints/channels.py

   POST /api/v1/channels/{channel_id}/connect
   DELETE /api/v1/channels/{channel_id}/disconnect
   GET /api/v1/channels/{channel_id}/status
   ```

3. **Frontend Modals** (agent-swarm-monitor):
   - WhatsAppConnectModal.tsx (QR code display via plugin)
   - TelegramConnectModal.tsx (bot token input)
   - SlackConnectModal.tsx (OAuth redirect)
   - DiscordConnectModal.tsx (bot token + server selection)
   - EmailConnectModal.tsx (SMTP/IMAP credentials)
   - SMSConnectModal.tsx (provider selection + API key)
   - TeamsConnectModal.tsx (OAuth redirect via plugin)

### Related Files
- **OpenClaw Plugins**: `~/.local/share/fnm/node-versions/v22.21.0/installation/lib/node_modules/openclaw/extensions/`
- **OpenClaw Config**: `~/.openclaw/openclaw.json`
- **OpenClaw CLI**: `openclaw plugins --help`
- Frontend: `components/openclaw/ChannelRow.tsx`
- Frontend: `components/openclaw/AgentChannelsTab.tsx`
- Backend: `backend/api/v1/endpoints/channels.py`
- Backend: New file `backend/services/openclaw_plugin_service.py`

---

## Issue 3: OpenClaw Gateway Not Running

**Severity**: HIGH
**Status**: Identified
**Repository**: openclaw-backend
**Related Issue**: openclaw-backend #97

### Problem
OpenClaw Gateway is not running on port 18789, causing:
- Chat API calls to fail
- Heartbeat execution to fail
- Agent control to fail
- "Open Control UI" button to fail

### Current State
- Gateway code exists: `/Users/aideveloper/openclaw-backend/openclaw-gateway/dist/server.js`
- Configuration exists: `.env` and `dbos-config.yaml`
- But service is not running: `curl http://localhost:18789/health` → Connection refused

### Expected Endpoints
- `GET /health` - Health check
- `GET /workflows/:uuid` - Workflow status
- `POST /messages` - Send agent messages
- `WS /` - WebSocket connection

### Solution
Start the Gateway service:

```bash
# Option 1: Manual start
cd /Users/aideveloper/openclaw-backend/openclaw-gateway
PORT=18789 node dist/server.js

# Option 2: Use startup script
cd /Users/aideveloper/openclaw-backend
./scripts/start-all-local.sh
```

### Prerequisites
- PostgreSQL connection configured in `.env`:
  ```
  PGHOST=...
  PGPORT=6432
  PGUSER=...
  PGPASSWORD=...
  PGDATABASE=ainative_app
  ```
- DBOS migrations run: `npm run dbos:migrate`

### Long-term Solution
- Add Gateway to systemd/launchd for auto-start
- Add health monitoring
- Add auto-restart on crash
- Document startup procedures

### Related Files
- Gateway: `openclaw-gateway/dist/server.js`
- Config: `openclaw-gateway/.env`
- Config: `openclaw-gateway/dbos-config.yaml`
- Startup: `scripts/start-all-local.sh`
- README: `openclaw-gateway/README.md`

---

## Issue 4: Skills Feature Not Implemented

**Severity**: LOW (Future Feature)
**Status**: Correctly Marked "Coming Soon"
**Repository**: Both (openclaw-backend, agent-swarm-monitor)
**Related Issue**: openclaw-backend #99, agent-swarm-monitor #30

### Problem
Skills UI shows "coming soon" because the feature is not implemented. However, OpenClaw CLI has a complete skills system that we're not integrating with.

### OpenClaw Skills System

**Discovery**:
- OpenClaw has **49 bundled skills** available via `openclaw skills list`
- Skills are npm packages in `~/.openclaw/skills/` or bundled with OpenClaw binary
- Configuration stored in `~/.openclaw/openclaw.json`:
  ```json
  "skills": {
    "install": { "nodeManager": "npm" },
    "entries": {
      "1password": { "enabled": true },
      "openai-image-gen": { "apiKey": "sk-..." }
    }
  }
  ```

**Available Skills** (14/49 ready):
- 🐙 github - GitHub CLI integration
- 📝 apple-notes - Apple Notes management
- ⏰ apple-reminders - Apple Reminders
- 📱 wacli - WhatsApp CLI
- 🌤️ weather - Weather forecasts
- 🎙️ openai-whisper-api - Speech-to-text
- 🖼️ openai-image-gen - Image generation
- 💬 slack - Slack control
- ...and 41 more!

**Skill Status**:
- ✓ **ready** - All dependencies installed
- ✗ **missing** - Missing binaries/dependencies
- **disabled** - Explicitly turned off
- **blockedByAllowlist** - Not in allow list

**CLI Commands**:
```bash
openclaw skills list                    # List all skills with status
openclaw skills list --json             # Get skill data as JSON
openclaw skills info <skill-name>       # Get detailed info
openclaw skills check                   # Check requirements
```

### What Needs to Be Built

#### 1. Backend API (openclaw-backend)

New endpoint: `/api/v1/skills`

```python
# backend/api/v1/endpoints/skills.py

@router.get("/skills")
async def list_skills():
    """List all OpenClaw skills with their status"""
    # Execute: openclaw skills list --json
    # Parse and return to frontend

@router.get("/skills/{skill_name}")
async def get_skill(skill_name: str):
    """Get detailed info about a specific skill"""
    # Execute: openclaw skills info {skill_name}

@router.post("/skills/{skill_name}/enable")
async def enable_skill(skill_name: str, config: dict):
    """Enable a skill with configuration"""
    # Update ~/.openclaw/openclaw.json
    # Add to skills.entries with enabled: true
    # Include API keys, config, etc.

@router.post("/skills/{skill_name}/disable")
async def disable_skill(skill_name: str):
    """Disable a skill"""
    # Update config to disabled: true

@router.post("/skills/{skill_name}/install")
async def install_skill(skill_name: str):
    """Install missing dependencies for a skill"""
    # Execute installation commands
    # Update skill status
```

#### 2. Backend Service (openclaw-backend)

```python
# backend/services/openclaw_skills_service.py

class OpenClawSkillsService:
    """Interface to OpenClaw CLI skills system"""

    async def list_skills(self) -> List[Skill]:
        """Execute: openclaw skills list --json"""

    async def get_skill_info(self, skill_name: str) -> SkillInfo:
        """Execute: openclaw skills info {skill_name}"""

    async def enable_skill(self, skill_name: str, config: dict):
        """Update openclaw.json to enable skill"""

    async def disable_skill(self, skill_name: str):
        """Update openclaw.json to disable skill"""

    async def update_skill_config(self, skill_name: str, config: dict):
        """Update skill configuration (API keys, etc.)"""
```

#### 3. Frontend Components (agent-swarm-monitor)

**Replace**: `components/openclaw/AgentSkillsTab.tsx`

```typescript
// New implementation:

export default function AgentSkillsTab() {
  const { data: skills, isLoading } = useSkills();
  const [filter, setFilter] = useState<'all' | 'ready' | 'missing'>('all');
  const [search, setSearch] = useState('');

  return (
    <div className="space-y-6">
      {/* Search and filters */}
      <div className="flex gap-4">
        <SearchInput value={search} onChange={setSearch} />
        <FilterButtons value={filter} onChange={setFilter} />
      </div>

      {/* Skills grid */}
      <div className="grid gap-4">
        {filteredSkills.map(skill => (
          <SkillCard
            key={skill.name}
            skill={skill}
            onEnable={handleEnable}
            onDisable={handleDisable}
            onConfigure={handleConfigure}
          />
        ))}
      </div>
    </div>
  );
}
```

**New Components**:
- `SkillCard.tsx` - Display skill with status, toggle, configure button
- `SkillConfigModal.tsx` - Configure skill (API keys, settings)
- `SkillInstallModal.tsx` - Install missing dependencies
- `hooks/useSkills.ts` - React Query hook for skills data
- `lib/skills-service.ts` - API client for skills endpoints

#### 4. Schemas (openclaw-backend)

```python
# backend/schemas/openclaw_skills.py

class SkillStatus(str, Enum):
    READY = "ready"
    MISSING = "missing"
    DISABLED = "disabled"
    BLOCKED = "blocked"

class Skill(BaseModel):
    name: str
    description: str
    emoji: str
    status: SkillStatus
    eligible: bool
    disabled: bool
    source: str
    homepage: Optional[str]
    missing: Dict[str, List[str]]
    config: Optional[Dict[str, Any]]

class SkillListResponse(BaseModel):
    skills: List[Skill]
    total: int
    ready_count: int
    missing_count: int
```

### Design Decisions

**Question 1**: Should skills be global or per-agent?
- **Current OpenClaw**: Skills are global (all agents share)
- **Possible Enhancement**: Add per-agent skill allowlists
  ```json
  {
    "agents": {
      "list": [
        {
          "id": "sales-agent",
          "allowedSkills": ["slack", "gmail", "notion"]
        }
      ]
    }
  }
  ```

**Question 2**: How to handle skill configuration?
- API keys stored in `openclaw.json`
- Backend should read/write this file securely
- Encrypt sensitive values?

**Question 3**: Skill installation?
- Some skills require binary installations (e.g., `gh`, `op`, etc.)
- Should we auto-install or show instructions?
- Use `npx clawhub` for marketplace skills?

### Implementation Phases

**Phase 1**: Read-only (List skills, show status)
- Backend: GET /api/v1/skills
- Frontend: Display skills with status badges
- No modification, just visibility

**Phase 2**: Enable/Disable
- Backend: POST /api/v1/skills/{name}/enable
- Backend: POST /api/v1/skills/{name}/disable
- Frontend: Toggle switches on skill cards

**Phase 3**: Configuration
- Backend: PUT /api/v1/skills/{name}/config
- Frontend: SkillConfigModal for API keys, settings
- Secure storage of credentials

**Phase 4**: Installation
- Backend: POST /api/v1/skills/{name}/install
- Execute installation commands
- Show installation progress

**Phase 5**: Per-Agent Skills (Future)
- Agent-specific skill allowlists
- Skill usage tracking per agent
- Skill execution logs

### Related Files
- Frontend: `components/openclaw/AgentSkillsTab.tsx` (needs complete rewrite)
- Backend: New file `backend/api/v1/endpoints/skills.py`
- Backend: New file `backend/services/openclaw_skills_service.py`
- Backend: New file `backend/schemas/openclaw_skills.py`
- OpenClaw Config: `~/.openclaw/openclaw.json`
- OpenClaw Skills: `~/.openclaw/skills/`
- OpenClaw Binary: `/usr/local/bin/openclaw` or similar

---

## Issue 5: Agent Settings Differences (FALSE ALARM)

**Severity**: N/A
**Status**: Not an Issue
**Repository**: N/A

### Investigation Result
Both DBOS Test Agent and Main Agent have identical settings structure in the database and UI. The `AgentSettingsTab.tsx` component shows the same options for all agents without conditional logic. If different options appear, it's likely a caching issue.

**Recommendation**: No action needed. User should refresh page if experiencing inconsistencies.

---

## Next Steps

### Immediate Actions
1. ✅ Create this documentation file
2. ✅ Create GitHub issues in both repos
   - openclaw-backend #97, #98, #99
   - agent-swarm-monitor #27, #28, #30
3. ⏳ Start OpenClaw Gateway (Issue #3 / openclaw-backend #97)
4. ⏳ Fix chat integration (Issue #1 / agent-swarm-monitor #27)

### Short-term (This Week)
1. Implement channel connection backends (Issue #2)
2. Create channel connection modals (Issue #2)
3. Document Gateway startup procedures (Issue #3)

### Medium-term (This Month)
1. Implement skills Phase 1 (read-only) (Issue #4)
2. Implement skills Phase 2 (enable/disable) (Issue #4)
3. Add tests for all new endpoints

### Long-term (Future)
1. Skills Phase 3-5 (configuration, installation, per-agent) (Issue #4)
2. Add skill usage analytics
3. Marketplace integration via `npx clawhub`

---

## References

### Documentation
- OpenClaw Gateway: `/Users/aideveloper/openclaw-backend/openclaw-gateway/README.md`
- DBOS Phase 1: `/Users/aideveloper/openclaw-backend/docs/guides/DBOS_PHASE1_OPENCLAW_GATEWAY.md`
- Skills CLI: `openclaw skills --help`

### Related Issues
- agent-swarm-monitor #27: Chat returns simulated response
- openclaw-backend #98: Implement channel connection backends
- agent-swarm-monitor #28: Create channel connection modals
- openclaw-backend #97: OpenClaw Gateway not running
- openclaw-backend #99: Implement OpenClaw Skills backend API
- agent-swarm-monitor #30: Implement OpenClaw Skills management UI

### External Links
- OpenClaw Skills Docs: https://docs.openclaw.ai/cli/skills
- OpenClaw CLI Docs: https://docs.openclaw.ai/cli
- ClawHub Marketplace: https://clawhub.com

---

**Last Updated**: March 1, 2026
**Status**: Active Investigation
**Next Review**: After GitHub issues created
