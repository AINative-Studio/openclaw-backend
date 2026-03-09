# Skills & OAuth Implementation Plan

**Date**: 2026-03-05
**Status**: Analysis Complete - Implementation Pending

## Executive Summary

Investigation reveals 4 critical gaps in our skills implementation:

1. **Missing Install Infrastructure** - No backend endpoints or UI for installing CLI-based skills
2. **Missing API Key Management** - No per-agent storage/configuration for skill credentials
3. **.claude Skills Not Integrated** - 22 project-specific skills from `.claude/skills/` not exposed in skills catalog
4. **Missing OAuth Flow** - Email/channel authentication doesn't trigger OAuth like OpenClaw does

---

## Issue #1: Missing CLI Tools (27 skills)

### Current Status
- **27 skills** show as "missing" but have `eligibility_errors: null`
- OpenClaw's `skills info` command reveals each has specific binary requirements
- Example: `bear-notes` requires `grizzly` CLI (installable via `go install`)

### OpenClaw's Approach
```bash
$ openclaw skills info bear-notes
Requirements:
  Binaries: ✗ grizzly
  OS: ✓ darwin

Install options:
  → Install grizzly (go)
```

### Skills Breakdown by Install Method

**Go Install (8 skills)**:
- `bear-notes` → `go install github.com/user/grizzly@latest`
- `bird` → `go install github.com/user/bird@latest`
- `blogwatcher` → `go install github.com/user/blogwatcher@latest`
- `camsnap` → RTSP/ONVIF tool
- `gifgrep` → GIF search tool
- `imsg` → iMessage CLI
- `peekaboo` → Camera tool
- `songsee` → Music recognition

**NPM Install (5 skills)**:
- `blucli` → `npm install -g blu`
- `eightctl` → Home automation
- `openhue` → Philips Hue CLI
- `sonoscli` → Sonos CLI
- `ordercli` → Order management

**Manual/Complex (14 skills)**:
- `goplaces` → Needs Google Places API key **AND** binary
- `local-places` → Needs Google Places API key
- `nano-banana-pro` → Needs Gemini API key
- `nano-pdf` → PDF processing
- `notion` → Needs Notion API key
- `obsidian` → Obsidian.md integration
- `oracle` → Database CLI
- `sag` → Needs ElevenLabs API key
- `sherpa-onnx-tts` → TTS with model files
- `summarize` → Summarization tool
- `gog` → GOG gaming
- `model-usage` → Model analytics

---

## Issue #2: No API Key Management

### What's Missing

**Backend**:
- No `AgentSkillConfiguration` model to store per-agent skill credentials
- No `/api/v1/agents/{id}/skills/{skill}/config` endpoint
- No encrypted credential storage

**Frontend**:
- No API key input fields in skill cards
- No "Configure" button for skills requiring credentials
- No validation of required credentials before enabling

### Proposed Schema

```python
# backend/models/agent_skill_config.py
class AgentSkillConfiguration(Base):
    """Per-agent skill configuration storage"""
    __tablename__ = "agent_skill_configurations"

    id = Column(UUID(), primary_key=True, default=uuid4)
    agent_id = Column(UUID(), ForeignKey("agent_swarm_instances.id"))
    skill_name = Column(String(255), nullable=False)  # e.g., "notion"

    # Encrypted JSON blob for credentials
    credentials = Column(Text, nullable=True)  # Fernet encrypted

    # Additional config (not encrypted)
    config = Column(JSON, nullable=True)
    enabled = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint('agent_id', 'skill_name'),
        Index('idx_agent_skill', 'agent_id', 'skill_name'),
    )
```

### Required Endpoints

```python
# GET /api/v1/agents/{agent_id}/skills
# List all skills with per-agent configuration status

# POST /api/v1/agents/{agent_id}/skills/{skill_name}/configure
# Body: { "api_key": "...", "config": {...} }
# Stores encrypted credentials

# POST /api/v1/agents/{agent_id}/skills/{skill_name}/install
# Triggers backend subprocess to install CLI binary

# DELETE /api/v1/agents/{agent_id}/skills/{skill_name}
# Removes configuration (not the binary)
```

---

## Issue #3: .claude Skills Not Integrated

### Current Status
- **22 skills** exist in `/Users/aideveloper/openclaw-backend/.claude/skills/`
- These are **project-specific context files** (SKILL.md format)
- They're **NOT** showing in the `/api/v1/skills` endpoint

### .claude Skills Inventory

```
1. api-catalog.md - API documentation catalog
2. api-key-management.md - API key management procedures
3. api-testing-requirements.md - Testing standards
4. audio-transcribe.md - Audio transcription workflows
5. ci-cd-compliance - CI/CD requirements
6. code-quality - Coding standards
7. daily-report.md - Daily reporting format
8. database-query-best-practices - DB query guidelines
9. database-schema-sync - Schema sync procedures
10. delivery-checklist - Pre-delivery checklist
11. email-campaign-management - Email campaigns
12. file-placement - File organization rules
13. git-workflow - Git commit/PR standards
14. huggingface-deployment - HF model deployment
15. local-environment-check - Environment verification
16. local-startup - Local dev startup
17. mandatory-tdd - TDD requirements
18. port-management - Port conflict handling
19. story-workflow - Issue tracking workflow
20. strapi-blog-image-unique - Blog image rules
21. strapi-blog-slug-mandatory - Blog slug requirements
22. weekly-report - Weekly reporting format
```

### Why They're Different

| OpenClaw CLI Skills | .claude Project Skills |
|---------------------|------------------------|
| Executable tools (binaries) | Knowledge base / procedures |
| Require installation | Always available (just files) |
| Called via CLI commands | Read as context/prompts |
| Need API keys/auth | No auth needed |
| Package type: `openclaw-bundled` | Package type: `project` |

### Integration Strategy

**Option A: Merge into Single Catalog** (Recommended)
```typescript
interface Skill {
  name: string;
  type: 'cli' | 'project';  // NEW FIELD
  eligible: boolean;
  requirements?: {
    binaries?: string[];
    apiKeys?: string[];
  };
  source: 'openclaw-bundled' | 'project';
  path?: string;  // For project skills
}
```

**Option B: Separate APIs**
- `/api/v1/skills` → OpenClaw CLI skills only
- `/api/v1/project-skills` → .claude folder skills
- Frontend shows two tabs

**Recommended**: Option A with unified UI showing filters/tags

---

## Issue #4: Missing OAuth Flow for Email

### Current Behavior
1. User adds email to agent configuration
2. Email is **stored in database**
3. **Nothing happens** - no OAuth prompt
4. Agent can't actually send/receive emails

### How OpenClaw Does It

When you add a channel (email, Slack, etc.), OpenClaw:
1. Detects missing OAuth credentials
2. Starts local OAuth server on `http://localhost:3000/callback`
3. Opens browser to provider's OAuth consent screen
4. Receives authorization code via redirect
5. Exchanges code for access/refresh tokens
6. Stores tokens in `~/.openclaw/config.json`

**Example from OpenClaw docs**:
```javascript
// When email is added
await openclawConfig.startOAuthFlow({
  provider: 'google',
  scopes: ['gmail.send', 'gmail.readonly'],
  redirectUri: 'http://localhost:3000/callback'
});
```

### Our Implementation Needs

**Backend** (`/api/v1/agents/{id}/channels/email/authorize`):
```python
@router.post("/{agent_id}/channels/email/authorize")
async def start_email_oauth(agent_id: UUID):
    """
    1. Generate OAuth state token
    2. Build Google OAuth URL with scopes
    3. Return URL + state token to frontend
    4. Frontend opens popup/redirect
    """
    state = secrets.token_urlsafe(32)

    # Store state in Redis/DB with agent_id
    await store_oauth_state(state, agent_id)

    oauth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?"
        f"client_id={GOOGLE_CLIENT_ID}&"
        f"redirect_uri={BACKEND_URL}/api/v1/oauth/callback&"
        f"response_type=code&"
        f"scope=gmail.send gmail.readonly&"
        f"state={state}"
    )

    return {"oauth_url": oauth_url, "state": state}
```

**OAuth Callback** (`/api/v1/oauth/callback`):
```python
@router.get("/oauth/callback")
async def oauth_callback(code: str, state: str):
    """
    1. Validate state token
    2. Exchange code for access token
    3. Store encrypted tokens in AgentChannelCredentials
    4. Redirect to success page
    """
    agent_id = await get_agent_from_state(state)

    # Exchange code for tokens
    token_response = await exchange_code_for_tokens(code)

    # Store encrypted
    await store_channel_credentials(
        agent_id=agent_id,
        channel_type="email",
        credentials={
            "access_token": token_response["access_token"],
            "refresh_token": token_response["refresh_token"],
            "expires_at": time.time() + token_response["expires_in"]
        }
    )

    return RedirectResponse(url="/agents/{agent_id}?oauth=success")
```

**Frontend**:
```typescript
// When user adds email
const startOAuth = async () => {
  const { oauth_url } = await api.post(`/agents/${agentId}/channels/email/authorize`);

  // Open popup
  const popup = window.open(oauth_url, 'OAuth', 'width=500,height=600');

  // Wait for OAuth callback
  const handleMessage = (event) => {
    if (event.data.type === 'oauth_success') {
      setEmailConfigured(true);
      popup?.close();
    }
  };

  window.addEventListener('message', handleMessage);
};
```

---

## Implementation Roadmap

### Phase 1: API Key Management (Critical)
**Effort**: 2 days
**Priority**: P0

- [ ] Create `AgentSkillConfiguration` model
- [ ] Add Fernet encryption for credentials
- [ ] Create `/agents/{id}/skills/{skill}/configure` endpoint
- [ ] Add frontend "Configure Skill" modal with API key input
- [ ] Test with Notion, Google Places, Gemini skills

### Phase 2: CLI Skill Installation
**Effort**: 3 days
**Priority**: P1

- [ ] Create `/agents/{id}/skills/{skill}/install` endpoint
- [ ] Implement subprocess installers for `go install`, `npm install -g`
- [ ] Add frontend "Install" button with progress indicator
- [ ] Show installation logs in real-time
- [ ] Test with `bear-notes`, `blucli`, `blogwatcher`

### Phase 3: .claude Skills Integration
**Effort**: 1 day
**Priority**: P1

- [ ] Create `ClaudeSkillsService` to read SKILL.md files
- [ ] Merge with OpenClaw skills in unified API
- [ ] Add `type: 'cli' | 'project'` field to Skill interface
- [ ] Add frontend filters (All / CLI Tools / Project Skills)
- [ ] Show "Always Available" badge for project skills

### Phase 4: OAuth Flow for Email
**Effort**: 4 days
**Priority**: P0

- [ ] Register OAuth app with Google
- [ ] Create `AgentChannelCredentials` model
- [ ] Implement `/channels/email/authorize` endpoint
- [ ] Implement `/oauth/callback` endpoint
- [ ] Add frontend OAuth popup flow
- [ ] Test token refresh logic
- [ ] Add support for other providers (Microsoft, etc.)

### Phase 5: UI Polish
**Effort**: 2 days
**Priority**: P2

- [ ] Add skill categories/tags
- [ ] Implement skill search
- [ ] Show skill usage metrics
- [ ] Add "What's This?" tooltips
- [ ] Create skill installation wizard

---

## Database Migrations Required

### Migration 1: Agent Skill Configurations
```sql
CREATE TABLE agent_skill_configurations (
    id UUID PRIMARY KEY,
    agent_id UUID REFERENCES agent_swarm_instances(id) ON DELETE CASCADE,
    skill_name VARCHAR(255) NOT NULL,
    credentials TEXT,  -- Fernet encrypted JSON
    config JSONB,
    enabled BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    UNIQUE(agent_id, skill_name)
);

CREATE INDEX idx_agent_skill_config ON agent_skill_configurations(agent_id, skill_name);
```

### Migration 2: Agent Channel Credentials
```sql
CREATE TABLE agent_channel_credentials (
    id UUID PRIMARY KEY,
    agent_id UUID REFERENCES agent_swarm_instances(id) ON DELETE CASCADE,
    channel_type VARCHAR(50) NOT NULL,  -- 'email', 'slack', etc.
    provider VARCHAR(50),  -- 'google', 'microsoft', etc.
    credentials TEXT NOT NULL,  -- Fernet encrypted
    metadata JSONB,  -- Email address, workspace ID, etc.
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    UNIQUE(agent_id, channel_type, provider)
);

CREATE INDEX idx_agent_channel ON agent_channel_credentials(agent_id, channel_type);
```

---

## Security Considerations

### Credential Encryption
- Use `cryptography.fernet` with key from `SECRET_KEY` env var
- Rotate encryption keys periodically
- Never log decrypted credentials

### OAuth Security
- Use PKCE for mobile/desktop apps
- Validate state tokens to prevent CSRF
- Store refresh tokens separately from access tokens
- Implement token rotation

### API Key Validation
- Validate API keys before storing
- Check rate limits/quotas
- Provide clear error messages for invalid keys

---

## Next Steps

1. **Review this plan** with stakeholders
2. **Prioritize phases** based on user needs
3. **Create JIRA tickets** for each phase
4. **Set up Google OAuth** credentials
5. **Start with Phase 1** (API Key Management)

---

## References

- OpenClaw Skills: `~/.local/share/fnm/node-versions/v22.21.0/installation/lib/node_modules/openclaw/skills/`
- .claude Skills: `/Users/aideveloper/openclaw-backend/.claude/skills/`
- Google OAuth Docs: https://developers.google.com/identity/protocols/oauth2
- Fernet Encryption: https://cryptography.io/en/latest/fernet/
