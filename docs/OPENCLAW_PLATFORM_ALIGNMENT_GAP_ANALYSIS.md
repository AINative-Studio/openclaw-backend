# OpenClaw Platform Alignment & Integration Gap Analysis

**Date**: 2026-03-02
**Status**: CRITICAL - Architecture Misalignment Identified
**Priority**: P0 (Blocking)

---

## Executive Summary

**Critical Finding**: Our backend and frontend are **NOT aligned with the actual OpenClaw platform architecture**. We've built a custom integration layer but haven't exposed the core OpenClaw features that define agent identity, behavior, and capabilities.

**Impact**:
- Agents have NO workspace with identity/soul/memory files
- NO cron job support (automation gap)
- NO logs exposure (observability gap)
- NO nodes visualization (P2P network blind spot)
- NO config management UI
- NO skills system integration
- NO channel bindings
- Chat history NOT persisted (volatile state)

---

## Part 1: OpenClaw Platform Architecture (Actual Structure)

### 1.1 Agent Workspace Structure

Every OpenClaw agent has a **workspace directory** (`~/.openclaw/workspace` or custom path) containing:

```
~/.openclaw/workspace/
├── AGENTS.md          # Operating instructions, memory usage rules
├── SOUL.md            # Persona, tone, boundaries
├── USER.md            # Who the user is, how to address them
├── IDENTITY.md        # Agent name, vibe, emoji, avatar
├── TOOLS.md           # Local tools and conventions
├── HEARTBEAT.md       # Periodic check-in checklist (runs every N minutes)
├── BOOT.md            # Startup checklist on gateway restart
├── BOOTSTRAP.md       # One-time first-run ritual
├── MEMORY.md          # Curated long-term memory (private session only)
├── memory/
│   ├── 2026-03-01.md  # Daily log (append-only)
│   ├── 2026-03-02.md
│   └── ...
├── skills/            # Workspace-specific skills (override managed)
└── canvas/            # Canvas UI files for node displays
    └── index.html
```

**Purpose of Each File**:

| File | Loaded When | Purpose |
|------|-------------|---------|
| `AGENTS.md` | Every session start | How agent should use memory, priorities, rules |
| `SOUL.md` | Every session start | Personality, tone, emotional boundaries |
| `USER.md` | Every session start | User context, preferences, how to address |
| `IDENTITY.md` | Bootstrap/setup | Agent name, theme, emoji, avatar (name/theme/emoji/avatar) |
| `TOOLS.md` | Every session start | Local tool notes (does NOT control availability) |
| `HEARTBEAT.md` | Every heartbeat run | Tiny checklist for periodic checks |
| `BOOT.md` | Gateway restart | Startup actions (when internal hooks enabled) |
| `BOOTSTRAP.md` | First workspace init | One-time ritual, deleted after completion |
| `MEMORY.md` | Main session only | Long-term curated memory |
| `memory/YYYY-MM-DD.md` | Session start (today + yesterday) | Daily log |

**Key Insight**: The workspace IS the agent's identity and memory. Files are the source of truth; the model only "remembers" what's written to disk.

### 1.2 Automation: Cron Jobs

OpenClaw has **TWO** automation mechanisms:

1. **Heartbeat** (periodic awareness):
   - Runs in main session every N minutes (default: 30min)
   - Batches multiple checks (inbox, calendar, notifications)
   - Context-aware with session history
   - Reads `HEARTBEAT.md` checklist
   - Smart suppression (`HEARTBEAT_OK` = no notification)

2. **Cron Jobs** (precise scheduling):
   - Runs at exact times (5-field or 6-field cron expressions)
   - Session isolation option (`main` vs `isolated`)
   - Per-job model overrides
   - One-shot support (`--at "20m"`)
   - Delivery control (`announce` = immediate, `none` = silent)

**Cron Job CLI**:
```bash
# Daily briefing at 7 AM
openclaw cron add \
  --name "Morning brief" \
  --cron "0 7 * * *" \
  --tz "America/New_York" \
  --session isolated \
  --model opus \
  --announce

# One-shot reminder
openclaw cron add \
  --name "Meeting reminder" \
  --at "20m" \
  --session main \
  --system-event "Reminder: standup in 10 min" \
  --delete-after-run
```

### 1.3 Tools & Skills

**Tools** (25 default):
- Built-in tools provided by plugins
- Examples: `exec`, `browser`, `memory_search`, `memory_get`, `read_file`, `write_file`, etc.
- Controlled via `tools.allow`, `tools.deny`, `tools.alsoAllow`

**Skills** (workspace-specific):
- Reusable agent scripts/prompts
- Located in `workspace/skills/`
- Override managed skills when names collide
- Created via CLI: `openclaw skills create <name>`

### 1.4 Channels

**What are Channels?**:
- Communication platforms (WhatsApp, Discord, Telegram, Slack, iMessage, etc.)
- 20+ channel plugins available
- Each channel has routing bindings

**Routing Bindings**:
```bash
# List bindings
openclaw agents bindings

# Bind agent to specific channel
openclaw agents bind --agent work --bind telegram:ops --bind discord:guild-a

# Unbind
openclaw agents unbind --agent work --bind telegram:ops
```

**Binding Scope Behavior**:
- Without `accountId`: matches channel default account only
- `accountId: "*"`: channel-wide fallback
- Explicit account binding: most specific

### 1.5 Memory System

**Two Layers**:

1. **Daily Logs** (`memory/YYYY-MM-DD.md`):
   - Append-only daily log
   - Read today + yesterday at session start
   - Day-to-day notes and running context

2. **Long-term Memory** (`MEMORY.md`):
   - Curated persistent facts
   - Decisions, preferences, durable knowledge
   - Only loaded in main, private session (NOT group chats)

**Memory Tools**:
- `memory_search` - Semantic recall over indexed snippets
- `memory_get` - Targeted read of specific file/line range

**Automatic Memory Flush**:
- When session nears compaction, OpenClaw triggers silent turn
- Agent writes durable memories BEFORE context is compacted
- Controlled by `agents.defaults.compaction.memoryFlush`

### 1.6 Session Management

**Session Types**:
- **Main session**: Primary conversation, full context
- **Isolated session**: Clean slate per run (cron jobs)
- **Group sessions**: Multi-user contexts

**Session Storage**:
- Stored in `~/.openclaw/agents/<agentId>/sessions/`
- Transcripts + metadata
- NOT in workspace (keep separate from version control)

### 1.7 Multi-Agent Routing

**Config Structure**:
```json5
{
  agents: {
    list: [
      {
        id: "main",
        workspace: "~/.openclaw/workspace-main",
        identity: {
          name: "OpenClaw",
          theme: "space lobster",
          emoji: "🦞",
          avatar: "avatars/openclaw.png"
        }
      },
      {
        id: "work",
        workspace: "~/.openclaw/workspace-work",
        identity: { ... }
      }
    ],
    defaults: {
      workspace: "~/.openclaw/workspace",
      heartbeat: {
        every: "30m",
        target: "last",
        activeHours: { start: "08:00", end: "22:00" }
      }
    }
  }
}
```

---

## Part 2: Our Current Implementation

### 2.1 What We Built

**Backend Models** (`backend/models/`):

```python
# agent_swarm_lifecycle.py
class AgentSwarmInstance(Base):
    id = UUID
    name = String
    persona = Text  # ✅ Exists
    model = String
    user_id = UUID
    status = AgentSwarmStatus  # PROVISIONING/RUNNING/PAUSED/STOPPED/FAILED

    # OpenClaw integration
    openclaw_session_key = String
    openclaw_agent_id = String

    # Heartbeat
    heartbeat_enabled = Boolean  # ✅ Basic support
    heartbeat_interval = HeartbeatInterval
    heartbeat_checklist = ARRAY(String)
    last_heartbeat_at = DateTime
    next_heartbeat_at = DateTime

    # ❌ MISSING: workspace_path
    # ❌ MISSING: soul (personality/tone)
    # ❌ MISSING: tools configuration
    # ❌ MISSING: skills list
    # ❌ MISSING: channel_bindings
    # ❌ MISSING: cron_jobs relationship
    # ❌ MISSING: identity (name/theme/emoji/avatar)
    # ❌ MISSING: memory_files_metadata
```

**API Endpoints** (`backend/api/v1/endpoints/`):

```
✅ GET  /agents                    # List agents
✅ GET  /agents/{id}               # Get agent
✅ POST /agents                    # Create agent
✅ POST /agents/{id}/provision     # Provision in OpenClaw
✅ POST /agents/{id}/pause         # Pause agent
✅ POST /agents/{id}/resume        # Resume agent
✅ POST /agents/{id}/heartbeat     # Execute heartbeat
✅ PUT  /agents/{id}/settings      # Update settings
✅ DELETE /agents/{id}             # Delete agent

❌ GET  /agents/{id}/workspace     # Get workspace files
❌ GET  /agents/{id}/memory        # Get memory logs
❌ POST /agents/{id}/cron-jobs     # Create cron job
❌ GET  /agents/{id}/cron-jobs     # List cron jobs
❌ DELETE /agents/{id}/cron-jobs/{job_id}  # Delete cron job
❌ GET  /agents/{id}/skills        # List skills
❌ POST /agents/{id}/skills        # Add skill
❌ GET  /agents/{id}/channels      # Get channel bindings
❌ POST /agents/{id}/channels/bind # Bind channel
❌ GET  /agents/{id}/logs          # Get agent logs
❌ GET  /agents/{id}/sessions      # List sessions
❌ GET  /agents/{id}/sessions/{session_id}  # Get session transcript
```

**OpenClaw Gateway** (`openclaw-gateway/src/`):

```typescript
// ✅ IMPLEMENTED
- WebSocket server (port 18789)
- /health endpoint
- /workflows/:uuid endpoint
- POST /messages endpoint
- POST /workflows/provision-agent
- POST /workflows/heartbeat
- POST /workflows/pause-resume

// ❌ NOT IMPLEMENTED
- Workspace file access endpoints
- Cron job management endpoints
- Skills management endpoints
- Channel routing configuration
- Logs streaming endpoint
- Nodes status endpoint
- Config management endpoint
```

### 2.2 Frontend (Agent Swarm Monitor)

**What We Show**:
```
✅ Agent list (name, status, model)
✅ Agent details (persona, heartbeat config)
✅ Basic metrics (active agents, completed tasks)
✅ OpenClaw connection status
✅ Real-time log streaming (from OUR logs, not OpenClaw logs)

❌ Workspace files view (AGENTS.md, SOUL.md, etc.)
❌ Memory browser (daily logs, MEMORY.md)
❌ Cron jobs panel
❌ Skills manager
❌ Channel bindings editor
❌ Nodes graph (P2P network visualization)
❌ OpenClaw gateway config editor
❌ Session history viewer
```

---

## Part 3: Gap Analysis

### 3.1 CRITICAL Gaps (Blocking Production)

| Gap # | Feature | OpenClaw Has | We Have | Impact | Severity |
|-------|---------|--------------|---------|--------|----------|
| 1 | Workspace Files | ✅ All .md files | ❌ None | Agents have NO identity/personality/memory persistence | P0 |
| 2 | Cron Jobs | ✅ Full cron + `--at` support | ❌ None | NO automation, NO scheduled tasks | P0 |
| 3 | Memory Persistence | ✅ Daily logs + MEMORY.md | ❌ None | Conversations NOT saved, volatile state | P0 |
| 4 | Logs | ✅ Session transcripts + agent logs | ❌ Only our backend logs | NO agent behavior visibility | P0 |
| 5 | Skills | ✅ Workspace skills + managed skills | ❌ None | NO reusable agent scripts | P1 |
| 6 | Channel Bindings | ✅ Multi-channel routing | ❌ None | NO channel-specific routing | P1 |
| 7 | Nodes Visualization | ✅ P2P network nodes | ❌ None | NO network topology visibility | P1 |
| 8 | Config Management | ✅ `openclaw.json` + agents config | ❌ None | NO runtime config changes | P1 |
| 9 | Session History | ✅ All session transcripts stored | ❌ None | NO conversation history | P0 |
| 10 | Tools Management | ✅ allow/deny/alsoAllow | ❌ None | NO tool access control | P1 |

### 3.2 Data Model Gaps

**AgentSwarmInstance Missing Fields**:

```python
# REQUIRED ADDITIONS
workspace_path = Column(String(500), nullable=False)  # Path to workspace dir
soul = Column(Text, nullable=True)  # Personality/tone (from SOUL.md)
identity_name = Column(String(255), nullable=True)  # From IDENTITY.md
identity_emoji = Column(String(10), nullable=True)
identity_avatar = Column(String(500), nullable=True)
identity_theme = Column(String(255), nullable=True)

tools_allow = Column(ARRAY(String), default=list)  # Allowed tools
tools_deny = Column(ARRAY(String), default=list)   # Denied tools
tools_also_allow = Column(ARRAY(String), default=list)  # Additional tools

channel_bindings = Column(JSON, default=dict)  # {channel: accountId}

# Relationships
cron_jobs = relationship("AgentCronJob", back_populates="agent")
skills = relationship("AgentSkill", back_populates="agent")
workspace_files = relationship("AgentWorkspaceFile", back_populates="agent")
sessions = relationship("AgentSession", back_populates="agent")
```

**New Models Required**:

```python
class AgentCronJob(Base):
    """Scheduled automation tasks"""
    __tablename__ = "agent_cron_jobs"

    id = Column(UUID(), primary_key=True)
    agent_id = Column(UUID(), ForeignKey("agent_swarm_instances.id"))
    name = Column(String(255), nullable=False)
    cron_expression = Column(String(100), nullable=False)  # 5 or 6 fields
    timezone = Column(String(50), default="UTC")
    session_type = Column(String(20), default="isolated")  # main or isolated
    message = Column(Text, nullable=True)
    system_event = Column(Text, nullable=True)
    model_override = Column(String(100), nullable=True)
    announce = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    next_run_at = Column(DateTime(timezone=True), nullable=True)
    last_run_at = Column(DateTime(timezone=True), nullable=True)
    delete_after_run = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AgentSkill(Base):
    """Workspace-specific skills"""
    __tablename__ = "agent_skills"

    id = Column(UUID(), primary_key=True)
    agent_id = Column(UUID(), ForeignKey("agent_swarm_instances.id"))
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    script_content = Column(Text, nullable=False)
    is_managed = Column(Boolean, default=False)  # False = workspace, True = managed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class AgentWorkspaceFile(Base):
    """Workspace .md files metadata + content"""
    __tablename__ = "agent_workspace_files"

    id = Column(UUID(), primary_key=True)
    agent_id = Column(UUID(), ForeignKey("agent_swarm_instances.id"))
    file_type = Column(String(50), nullable=False)  # AGENTS, SOUL, USER, etc.
    file_path = Column(String(500), nullable=False)  # Relative to workspace
    content = Column(Text, nullable=True)  # File content (OR store in ZeroDB)
    last_modified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class AgentSession(Base):
    """Conversation session tracking"""
    __tablename__ = "agent_sessions"

    id = Column(UUID(), primary_key=True)
    agent_id = Column(UUID(), ForeignKey("agent_swarm_instances.id"))
    session_type = Column(String(20), default="main")  # main, isolated, group
    channel = Column(String(50), nullable=True)  # whatsapp, discord, etc.
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    message_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    # Store in ZeroDB for messages (not here)
    zerodb_conversation_id = Column(String(255), nullable=True)
```

---

## Part 4: ZeroDB Integration Strategy

### 4.1 Mapping OpenClaw → ZeroDB → Our Backend

**Decision Recap** (from earlier discussion):
- 1 = Option A (full hierarchy: Workspace + User + Conversation models)
- 2 = Option A (one ZeroDB project per workspace)
- 3 = Both (ZeroDB tables AND Memory API)
- 4 = Start fresh (dev mode, no retroactive history)

**Proposed Architecture**:

```
PostgreSQL (Structure)           ZeroDB (Content + Search)
    ↓                                  ↓
Workspace                      →  ZeroDB Project
    ├── workspace_id           →  project_id
    ├── name
    └── zerodb_project_id

AgentSwarmInstance             →  ZeroDB Project
    ├── workspace_path         →  /workspace files/
    ├── AGENTS.md              →  file or memory
    ├── SOUL.md                →  file or memory
    ├── MEMORY.md              →  file or memory
    └── memory/2026-03-02.md   →  file or memory

AgentSession                   →  ZeroDB Table: conversations
    ├── session_id             →  row_id
    ├── channel
    ├── started_at
    └── message_count

[Messages]                     →  ZeroDB Table: messages
    ├── conversation_id        →  conversation_id (FK)
    ├── role (user/assistant)
    ├── content
    ├── timestamp
    └── metadata (model, tokens)

[Messages ALSO stored as]      →  ZeroDB Memory API
    └── type="conversation"    →  Automatic embeddings for semantic search
```

### 4.2 Workspace File Storage Options

**Option A: Store in ZeroDB Files API** (S3-compatible)

```python
# On workspace initialization
await zerodb_client.upload_file(
    project_id=workspace.zerodb_project_id,
    file_key=f"{agent.id}/AGENTS.md",
    file_name="AGENTS.md",
    content=agents_md_content,
    mime_type="text/markdown"
)

# Read workspace file
file_url = await zerodb_client.get_file_url(
    project_id=workspace.zerodb_project_id,
    file_key=f"{agent.id}/AGENTS.md"
)
content = await httpx.get(file_url)
```

**Option B: Store in PostgreSQL AgentWorkspaceFile table**

```python
# Store in database
workspace_file = AgentWorkspaceFile(
    agent_id=agent.id,
    file_type="AGENTS",
    file_path="AGENTS.md",
    content=agents_md_content,
    last_modified_at=datetime.now(timezone.utc)
)
db.add(workspace_file)
await db.commit()
```

**Option C: Hybrid (PostgreSQL metadata + ZeroDB content)**

```python
# Metadata in PostgreSQL
workspace_file = AgentWorkspaceFile(
    agent_id=agent.id,
    file_type="AGENTS",
    file_path="AGENTS.md",
    zerodb_file_key=f"{agent.id}/AGENTS.md",
    last_modified_at=datetime.now(timezone.utc)
)

# Content in ZeroDB
await zerodb_client.upload_file(
    project_id=workspace.zerodb_project_id,
    file_key=workspace_file.zerodb_file_key,
    content=agents_md_content
)
```

**Recommendation**: **Option C (Hybrid)** - metadata in PostgreSQL for fast queries, content in ZeroDB for scalability.

### 4.3 Memory/Chat Storage

**Daily Logs** (`memory/YYYY-MM-DD.md`):

```python
# Store as ZeroDB Memory
await zerodb_client.create_memory(
    title=f"{agent.name} - Daily Log - {date.today()}",
    content=daily_log_content,
    type="note",  # or "conversation"
    priority="medium",
    tags=[
        f"agent:{agent.id}",
        f"workspace:{workspace.id}",
        f"date:{date.today()}"
    ],
    metadata={
        "agent_id": str(agent.id),
        "file_path": f"memory/{date.today()}.md"
    }
)
```

**Chat Messages**:

```python
# 1. Store in ZeroDB Table (structured)
await zerodb_client.create_table_row(
    project_id=workspace.zerodb_project_id,
    table_name="messages",
    row_data={
        "conversation_id": str(session.id),
        "role": "assistant",
        "content": message_content,
        "agent_id": str(agent.id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": agent.model
    }
)

# 2. ALSO store as Memory (semantic search)
await zerodb_client.create_memory(
    title=f"Chat with {agent.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
    content=message_content,
    type="conversation",
    priority="medium",
    tags=[f"agent:{agent.name}", f"session:{session.id}"],
    metadata={"conversation_id": str(session.id)}
)
```

---

## Part 5: Frontend UI Updates Required

### 5.1 Agent Detail Page - New Sections

**Current**:
```
- Basic Info (name, persona, model)
- Heartbeat Config
- Status
```

**Required**:
```
✅ Basic Info
✅ Heartbeat Config
NEW: Workspace Tab
  ├── AGENTS.md editor
  ├── SOUL.md editor
  ├── USER.md editor
  ├── IDENTITY.md editor
  ├── TOOLS.md editor
  ├── HEARTBEAT.md editor
  └── MEMORY.md viewer

NEW: Memory Tab
  ├── Daily logs list (memory/2026-03-01.md, ...)
  ├── Daily log viewer/editor
  └── Semantic search (powered by ZeroDB)

NEW: Cron Jobs Tab
  ├── Job list (name, schedule, next run)
  ├── Add job form (cron expression, message, settings)
  └── Job logs/history

NEW: Skills Tab
  ├── Workspace skills list
  ├── Managed skills list
  ├── Add/edit skill form

NEW: Channels Tab
  ├── Current bindings (channel:accountId)
  ├── Bind/unbind controls

NEW: Sessions Tab
  ├── Session history list
  ├── Session detail (full transcript from ZeroDB)
  ├── Export conversation

NEW: Logs Tab
  ├── Real-time OpenClaw agent logs (NOT our backend logs)
  ├── Filter by level/timestamp
  └── Download logs

NEW: Tools Tab
  ├── Allowed tools list
  ├── Denied tools list
  ├── Also-allow overrides
```

### 5.2 New Dashboard Sections

**Config Manager** (NEW page):
```
- OpenClaw Gateway config editor
- Agent defaults (workspace, heartbeat)
- Model providers settings
- Timezone settings
```

**Nodes Viewer** (NEW page):
```
- P2P network graph visualization
- Node status (online/offline)
- WireGuard peer status
- Peer capabilities
```

---

## Part 6: Implementation Roadmap

### Phase 1: Data Model + ZeroDB Foundation (Week 1-2)

**Tasks**:

1. **Create new models**:
   - `AgentCronJob`
   - `AgentSkill`
   - `AgentWorkspaceFile`
   - `AgentSession`
   - `Workspace` (if using full hierarchy)
   - `User` (if using full hierarchy)
   - `Conversation` (link to `AgentSession`)

2. **Extend AgentSwarmInstance**:
   - Add `workspace_path`, `soul`, `identity_*` fields
   - Add `tools_*`, `channel_bindings` fields
   - Add relationships

3. **Alembic migration**:
   ```bash
   alembic revision --autogenerate -m "Add OpenClaw platform alignment models"
   ```

4. **ZeroDB integration**:
   - Create ZeroDBClient wrapper (from earlier design)
   - Implement workspace file storage (Option C - hybrid)
   - Implement chat/memory storage (dual: Table + Memory API)

**Success Criteria**:
- [ ] All new models created
- [ ] Migration runs successfully
- [ ] ZeroDBClient can create projects/tables
- [ ] Can store/retrieve workspace files

---

### Phase 2: Workspace File Management (Week 3)

**Tasks**:

1. **Workspace initialization service**:
   ```python
   # backend/services/workspace_initialization_service.py

   async def initialize_workspace(agent: AgentSwarmInstance):
       # 1. Create workspace directory (or ZeroDB project)
       # 2. Create all .md files (AGENTS, SOUL, USER, etc.)
       # 3. Seed with templates
       # 4. Store metadata in database
   ```

2. **API endpoints**:
   ```
   GET    /agents/{id}/workspace/files
   GET    /agents/{id}/workspace/files/{file_type}
   PUT    /agents/{id}/workspace/files/{file_type}
   DELETE /agents/{id}/workspace/files/{file_type}
   ```

3. **Frontend components**:
   - `WorkspaceFilesTab.tsx` (file list)
   - `WorkspaceFileEditor.tsx` (Markdown editor with preview)

**Success Criteria**:
- [ ] Can create workspace files via API
- [ ] Can edit AGENTS.md, SOUL.md, etc. from UI
- [ ] Changes persisted in ZeroDB
- [ ] File content loads correctly in editor

---

### Phase 3: Cron Jobs (Week 4)

**Tasks**:

1. **Cron job service**:
   ```python
   # backend/services/agent_cron_job_service.py

   async def create_cron_job(agent_id, name, cron_expression, **kwargs):
       # 1. Validate cron expression
       # 2. Calculate next_run_at
       # 3. Create AgentCronJob record
       # 4. Schedule with OpenClaw gateway (if running)

   async def execute_cron_job(job_id):
       # 1. Send message to OpenClaw gateway
       # 2. Update last_run_at
       # 3. Calculate next_run_at
       # 4. Delete if delete_after_run=True
   ```

2. **Background scheduler**:
   ```python
   # Use APScheduler or similar
   from apscheduler.schedulers.asyncio import AsyncIOScheduler

   scheduler = AsyncIOScheduler()
   scheduler.add_job(
       execute_cron_job,
       'cron',
       hour=job.hour,
       minute=job.minute,
       ...
   )
   ```

3. **API endpoints**:
   ```
   POST   /agents/{id}/cron-jobs
   GET    /agents/{id}/cron-jobs
   GET    /agents/{id}/cron-jobs/{job_id}
   PUT    /agents/{id}/cron-jobs/{job_id}
   DELETE /agents/{id}/cron-jobs/{job_id}
   POST   /agents/{id}/cron-jobs/{job_id}/execute  # Manual trigger
   ```

4. **Frontend**:
   - `CronJobsTab.tsx`
   - `CronJobForm.tsx` (cron expression builder)
   - `CronJobLogs.tsx`

**Success Criteria**:
- [ ] Can create cron jobs via UI
- [ ] Jobs execute at scheduled times
- [ ] Can trigger manual execution
- [ ] Job logs visible in UI

---

### Phase 4: Memory & Chat Persistence (Week 5-6)

**Tasks**:

1. **Memory service**:
   ```python
   # backend/services/agent_memory_service.py

   async def store_daily_log(agent_id, date, content):
       # Store in ZeroDB Memory API
       # Tag with agent_id, date

   async def get_daily_logs(agent_id, start_date, end_date):
       # Query ZeroDB Memory API
       # Filter by date range

   async def search_memory(agent_id, query, limit=5):
       # Semantic search via ZeroDB
   ```

2. **Session + message tracking**:
   ```python
   # backend/services/agent_session_service.py

   async def create_session(agent_id, channel, session_type="main"):
       # 1. Create AgentSession
       # 2. Create ZeroDB conversation entry
       # 3. Link via zerodb_conversation_id

   async def add_message(session_id, role, content, metadata=None):
       # 1. Store in ZeroDB Table (messages)
       # 2. ALSO store in ZeroDB Memory (semantic search)
       # 3. Update session.message_count

   async def get_session_transcript(session_id):
       # Query ZeroDB messages table
       # Return chronological list
   ```

3. **OpenClaw bridge integration**:
   ```python
   # backend/agents/orchestration/production_openclaw_bridge.py

   async def send_message(self, session_key, message):
       # ... existing send logic ...

       # NEW: Store message in ZeroDB
       session = await get_session_by_key(session_key)
       await agent_session_service.add_message(
           session.id,
           role="user",
           content=message
       )

   async def on_message_received(self, session_key, response):
       # ... existing handler ...

       # NEW: Store assistant response in ZeroDB
       session = await get_session_by_key(session_key)
       await agent_session_service.add_message(
           session.id,
           role="assistant",
           content=response
       )
   ```

4. **API endpoints**:
   ```
   GET /agents/{id}/memory/daily-logs
   GET /agents/{id}/memory/daily-logs/{date}
   POST /agents/{id}/memory/search
   GET /agents/{id}/sessions
   GET /agents/{id}/sessions/{session_id}/transcript
   POST /agents/{id}/sessions/{session_id}/export
   ```

5. **Frontend**:
   - `MemoryTab.tsx` (daily logs list + viewer)
   - `MemorySearch.tsx` (semantic search UI)
   - `SessionsTab.tsx` (session history)
   - `SessionTranscript.tsx` (message list with timestamps)

**Success Criteria**:
- [ ] All chat messages stored in ZeroDB
- [ ] Daily logs created automatically
- [ ] Can view session transcripts in UI
- [ ] Semantic memory search works
- [ ] Chat history persists across sessions

---

### Phase 5: Skills, Channels, Logs, Nodes (Week 7-8)

**Tasks**:

1. **Skills management**:
   - CRUD endpoints for `AgentSkill`
   - Workspace vs managed skills distinction
   - Frontend skill editor

2. **Channel bindings**:
   - Update `AgentSwarmInstance.channel_bindings` JSON
   - Bind/unbind endpoints
   - Frontend channel selector

3. **Logs integration**:
   - Fetch OpenClaw agent logs (from gateway or session files)
   - Real-time log streaming via SSE
   - Frontend log viewer with filters

4. **Nodes visualization**:
   - Query WireGuard peers (existing endpoint)
   - Query P2P libp2p nodes (new endpoint needed)
   - Frontend graph visualization (D3.js or similar)

**Success Criteria**:
- [ ] Can add/edit skills via UI
- [ ] Can bind agents to channels
- [ ] Real-time logs visible
- [ ] Nodes graph shows P2P network

---

### Phase 6: Config Management (Week 9)

**Tasks**:

1. **Config service**:
   - Read `~/.openclaw/openclaw.json` (if accessible)
   - OR expose OpenClaw gateway config via API
   - Update config sections (agents.defaults, heartbeat, etc.)

2. **API endpoints**:
   ```
   GET /openclaw/config
   PUT /openclaw/config/agents/defaults
   PUT /openclaw/config/heartbeat
   PUT /openclaw/config/models
   ```

3. **Frontend**:
   - `ConfigManagerPage.tsx`
   - JSON editor with schema validation

**Success Criteria**:
- [ ] Can view OpenClaw config
- [ ] Can update agent defaults
- [ ] Changes reflected in gateway

---

## Part 7: Decision Points

### Decision 1: Workspace File Storage

**Question**: Where to store workspace .md files?

**Options**:
- A: ZeroDB Files API (S3-compatible, separate from PostgreSQL)
- B: PostgreSQL AgentWorkspaceFile.content (simpler, but large blobs)
- C: Hybrid (metadata in PostgreSQL, content in ZeroDB)

**Recommendation**: **Option C** - best of both worlds

---

### Decision 2: OpenClaw Gateway Modification

**Question**: Do we modify the OpenClaw Gateway to expose new endpoints, or build a separate API layer?

**Options**:
- A: Extend `openclaw-gateway/src/server.ts` with workspace/cron/skills endpoints
- B: Keep gateway minimal, add endpoints to our FastAPI backend
- C: Build a separate Node.js service as middleware

**Recommendation**: **Option B** - keep gateway focused on DBOS workflows, expose features via our FastAPI backend

---

### Decision 3: Real OpenClaw vs Our Gateway

**Question**: Are we integrating with the ACTUAL OpenClaw platform (the one with the .md workspace structure), or are we just naming our custom gateway "OpenClaw"?

**Critical Clarification Needed**:
- If we're integrating with the real OpenClaw platform: We need to point to an actual OpenClaw gateway installation
- If we're building our own OpenClaw-inspired system: We need to implement workspace .md files ourselves

**My Understanding**: We're building our own OpenClaw-inspired system, so we need to:
1. Implement workspace file management in our backend
2. Create .md files as database records or ZeroDB files
3. Expose OpenClaw-like features via our API
4. Build UI to manage these features

---

## Part 8: Next Steps

**IMMEDIATE ACTIONS**:

1. ✅ **Confirm decisions** (you said: 1=A, 2=A, 3=Both, 4=Start Fresh)
   - Workspace file storage: Option C (hybrid)
   - Gateway modification: Option B (FastAPI backend)
   - Real OpenClaw integration: Need clarification

2. **Prioritize implementation**:
   - P0: Memory/chat persistence (Phase 4) - CRITICAL for conversations
   - P0: Workspace files (Phase 2) - CRITICAL for agent identity
   - P1: Cron jobs (Phase 3) - automation
   - P2: Skills/channels/logs/nodes (Phase 5)

3. **Update REMEDIATION_ROADMAP.md**:
   - Integrate this gap analysis
   - Revise timeline based on OpenClaw alignment
   - Add OpenClaw-specific sprints

**QUESTIONS FOR YOU**:

1. **Are we integrating with the actual OpenClaw platform** (the open-source one at `/Users/aideveloper/openclaw-source/`), or are we building our own OpenClaw-inspired system?

2. **Should workspace .md files be actual files on disk**, or can they be database/ZeroDB records?

3. **Priority**: Should we do Phase 4 (chat persistence) BEFORE Phase 2 (workspace files)?

---

**Status**: Ready to proceed once decisions confirmed.
