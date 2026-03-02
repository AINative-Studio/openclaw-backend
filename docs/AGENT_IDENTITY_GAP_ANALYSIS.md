# Agent Identity Schema Gap Analysis

**Date**: 2026-03-02
**Spec Version**: v1.0
**Current Implementation**: OpenClaw Backend v0.1
**Status**: **MAJOR GAPS - Requires New Schema Design**

---

## Executive Summary

The agent identities specification defines a sophisticated multi-agent architecture with:
- 6 specialized agents + 1 orchestrator
- Official email identities (@ainative.studio)
- Tool-based permissions (CMS, CRM, Analytics, etc.)
- ZeroDB collection scopes
- Token rotation every 90 days

**Current OpenClaw Reality**: **NONE of this exists**

The current schema has basic agent lifecycle management but **NO support for**:
1. ❌ Named agent identities (Atlas, Lyra, Sage, etc.)
2. ❌ Email-based agent addressing
3. ❌ Tool access permissions
4. ❌ ZeroDB integration (zero code found)
5. ❌ Scoped collection access
6. ❌ Token rotation policies
7. ❌ Role-based capabilities per agent

---

## Current Schema vs Required Schema

### Table 1: Agent Identity Fields

| Field | Required (Spec) | Current (AgentSwarmInstance) | Gap |
|-------|----------------|------------------------------|-----|
| **Identity** |
| `id` | UUID | ✅ UUID | ✅ Exists |
| `name` | Human-readable (e.g., "Atlas Redwood") | ✅ String(255) | ✅ Exists |
| `email` | Official (@ainative.studio) | ❌ **MISSING** | 🚨 **Critical** |
| `role` | Functional role (Search, Content, etc.) | ❌ **MISSING** | 🚨 **Critical** |
| **Configuration** |
| `persona` | System prompt/personality | ✅ Text | ✅ Exists |
| `model` | LLM model name | ✅ String(255) | ✅ Exists |
| **Tool Access** |
| `tool_permissions` | Array of tool configs | ❌ **MISSING** | 🚨 **Critical** |
| `api_credentials` | Map of service → token refs | ❌ **MISSING** | 🚨 **Critical** |
| **ZeroDB** |
| `zerodb_collections` | Scoped write access | ❌ **MISSING** | 🚨 **Critical** |
| **Security** |
| `token_rotation_policy` | Days until rotation | ❌ **MISSING** | 🚨 **Critical** |
| `last_token_rotation` | Timestamp | ❌ **MISSING** | 🚨 **Critical** |
| **Orchestration** |
| `orchestrator_role` | Boolean (is this Helios?) | ❌ **MISSING** | ⚠️ Medium |
| `can_assign_tasks` | Permission flag | ❌ **MISSING** | ⚠️ Medium |

**Gap Score**: **2/13 fields exist (15%)**

---

### Table 2: Tool Access Permissions

| Tool Type | Example from Spec | Current Support | Gap |
|-----------|-------------------|-----------------|-----|
| **CMS** | Strapi Draft+Publish | ❌ No tool model | 🚨 **Missing** |
| **Social Media** | Buffer API scheduling | ❌ No integration | 🚨 **Missing** |
| **Analytics** | GA4 Read token | ❌ No scoped access | 🚨 **Missing** |
| **CRM** | HubSpot Write access | ❌ No tool permissions | 🚨 **Missing** |
| **Email Marketing** | Resend API token | ❌ No credential linking | 🚨 **Missing** |
| **A/B Testing** | Experiment write access | ❌ No tool model | 🚨 **Missing** |
| **Events Platform** | Luma Admin API | ❌ No integration | 🚨 **Missing** |
| **Payment** | Stripe Limited Write | ❌ No scoped payments | 🚨 **Missing** |
| **Document Signing** | DocuSign Draft | ❌ No integration | 🚨 **Missing** |
| **Calendar** | Scheduling API | ❌ No calendar model | 🚨 **Missing** |

**Current**: Only workspace-level API keys exist (`UserAPIKey` for anthropic/openai/cohere)
**Required**: Per-agent, per-tool permission model with access levels (Read/Write/Admin)

---

### Table 3: ZeroDB Collections

| Agent | Required Collections | Current Support | Gap |
|-------|---------------------|-----------------|-----|
| **Atlas (SEO)** | `seo/keywords`, `seo/keyword_clusters`, `seo/pages`, `seo/serp_snapshots`, `seo/ranking_history` | ❌ No ZeroDB | 🚨 **Blocker** |
| **Lyra (Content)** | `content/blogs`, `content/social_posts`, `content/newsletters`, `brand/voice_memory`, `brand/style_guidelines` | ❌ No ZeroDB | 🚨 **Blocker** |
| **Sage (Analytics)** | `analytics/events`, `analytics/reports`, `analytics/funnels`, `analytics/experiments` | ❌ No ZeroDB | 🚨 **Blocker** |
| **Vega (Sales)** | `sales/leads`, `sales/conversations`, `sales/objections`, `sales/deals`, `sales/playbooks` | ❌ No ZeroDB | 🚨 **Blocker** |
| **Nova (Growth)** | `growth/experiments`, `growth/offers`, `growth/results`, `growth/funnels` | ❌ No ZeroDB | 🚨 **Blocker** |
| **Luma (Events)** | `events/calendar`, `events/attendees`, `events/sponsors`, `events/speakers`, `events/metrics` | ❌ No ZeroDB | 🚨 **Blocker** |

**ZeroDB Search Results**: `grep -r "ZeroDB\|zerodb" backend/ openclaw-gateway/` → **0 matches**

**Impact**: Agents have **NO persistent memory layer** - cannot learn from past interactions or maintain context across sessions.

---

### Table 4: Security & Governance

| Security Feature | Required (Spec) | Current Implementation | Gap |
|------------------|----------------|------------------------|-----|
| **Token Management** |
| Token rotation | Every 90 days | ❌ No rotation policy | 🚨 **Critical** |
| Encrypted storage | Required | ✅ Fernet encryption (UserAPIKey) | ✅ Partial |
| No hard-coded creds | Required | ⚠️ `.env` files committed | 🔥 **SECURITY RISK** |
| Immediate revocation | Required | ❌ No revocation API | 🚨 **Critical** |
| **Permission Model** |
| Read-only by default | Required | ❌ No permission model | 🚨 **Critical** |
| Publish rights gated | Required | ❌ No approval workflow | 🚨 **Critical** |
| Revenue access limited | Required | ❌ No scoped access | 🚨 **Critical** |
| CRM write restricted | Required | ❌ No restrictions | 🚨 **Critical** |
| **Logging** |
| Every action logged | Required | ⚠️ Audit logs exist (`AuditEvent`) | ✅ Partial |
| Publish audit trail | Required | ❌ No publish logs | 🚨 **Critical** |
| Revenue action approval | Required | ❌ No approval workflow | 🚨 **Critical** |

**Current Security**: Basic encrypted API keys per workspace (Issue #96)
**Required**: Per-agent token rotation + approval workflows + scoped permissions

---

## Detailed Gap Analysis by Component

### 1. Agent Identity Model (MAJOR GAP)

**Current**: `AgentSwarmInstance` model
```python
class AgentSwarmInstance(Base):
    id = UUID()
    name = String(255)          # Generic name
    persona = Text              # ✅ Exists
    model = String(255)         # ✅ Exists
    user_id = UUID()            # Links to human user
    status = Enum(...)          # Lifecycle status
    openclaw_session_key        # OpenClaw integration
    openclaw_agent_id
    heartbeat_enabled
    # ... more lifecycle fields

    # ❌ MISSING:
    # - email (official @ainative.studio)
    # - role (Search, Content, Sales, etc.)
    # - tool_permissions
    # - api_credentials
    # - zerodb_collections
    # - token_rotation_policy
```

**Required**: `AgentIdentity` model (new)
```python
class AgentRole(str, Enum):
    SEARCH_DISCOVERABILITY = "search-discoverability"
    CONTENT_BRAND = "content-brand"
    ANALYTICS_INSIGHTS = "analytics-insights"
    SALES_CONVERSION = "sales-conversion"
    GROWTH_FUNNEL = "growth-funnel"
    EVENTS_COMMUNITY = "events-community"
    ORCHESTRATION = "orchestration"

class AgentIdentity(Base):
    """
    Official agent identity with email, role, and permissions.
    Links to AgentSwarmInstance for runtime execution.
    """
    __tablename__ = "agent_identities"

    id = Column(UUID(), primary_key=True, default=uuid4)

    # Official Identity
    name = Column(String(255), nullable=False, unique=True)  # "Atlas Redwood"
    email = Column(String(255), nullable=False, unique=True)  # "atlas.redwood@ainative.studio"
    role = Column(
        SQLEnum(AgentRole, ...),
        nullable=False,
        index=True
    )

    # Link to runtime instance
    agent_swarm_instance_id = Column(
        UUID(),
        ForeignKey("agent_swarm_instances.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # Tool Access Permissions (JSON array)
    tool_permissions = Column(JSON, default=list, nullable=False)
    # Format: [
    #   {"tool": "cms", "access_level": "draft+publish", "notes": "Controlled publishing"},
    #   {"tool": "social_scheduler", "access_level": "api", "provider": "buffer"},
    #   ...
    # ]

    # API Credential References (JSON map)
    api_credentials = Column(JSON, default=dict, nullable=False)
    # Format: {
    #   "CMS_TOKEN": "user_api_keys.id:<uuid>",
    #   "SOCIAL_SCHEDULER_TOKEN": "user_api_keys.id:<uuid>",
    #   ...
    # }

    # ZeroDB Collection Scopes (JSON array)
    zerodb_collections = Column(ARRAY(String), nullable=False, default=list)
    # Format: ["seo/keywords", "seo/keyword_clusters", "seo/pages", ...]

    # Token Rotation Policy
    token_rotation_days = Column(Integer, default=90, nullable=False)
    last_token_rotation = Column(DateTime(timezone=True), nullable=True)
    next_rotation_due = Column(DateTime(timezone=True), nullable=True)

    # Orchestration Permissions
    is_orchestrator = Column(Boolean, default=False, nullable=False)
    can_assign_tasks = Column(Boolean, default=False, nullable=False)
    can_pause_experiments = Column(Boolean, default=False, nullable=False)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    agent_instance = relationship("AgentSwarmInstance", backref="identity")
```

**Migration Required**: Yes - New table with foreign key to existing `agent_swarm_instances`

---

### 2. Tool Permission Model (MISSING ENTIRELY)

**Current**: No tool permission model exists

**Required**: `AgentToolPermission` model (new)
```python
class ToolAccessLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"
    API = "api"
    DRAFT = "draft"
    DRAFT_PUBLISH = "draft+publish"
    LIMITED_WRITE = "limited_write"

class AgentToolPermission(Base):
    """
    Fine-grained tool access permissions per agent.
    Enforces least-privilege security model.
    """
    __tablename__ = "agent_tool_permissions"

    id = Column(UUID(), primary_key=True, default=uuid4)

    # Agent reference
    agent_identity_id = Column(
        UUID(),
        ForeignKey("agent_identities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Tool identification
    tool_name = Column(String(100), nullable=False, index=True)  # "cms", "crm", "social_scheduler"
    tool_category = Column(String(50), nullable=False)  # "content", "sales", "analytics"

    # Access control
    access_level = Column(
        SQLEnum(ToolAccessLevel, ...),
        nullable=False
    )

    # Provider-specific config
    provider = Column(String(100), nullable=True)  # "strapi", "hubspot", "buffer"
    provider_config = Column(JSON, default=dict)

    # Access notes/restrictions
    notes = Column(Text, nullable=True)  # "Controlled publishing only"

    # Audit
    granted_at = Column(DateTime(timezone=True), server_default=func.now())
    granted_by = Column(UUID(), nullable=True)  # Admin who granted access
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    # Indexes
    __table_args__ = (
        Index('idx_agent_tool_permissions_agent_tool', 'agent_identity_id', 'tool_name'),
    )
```

**Integration Points**:
- Link to `AgentIdentity` via foreign key
- Reference `UserAPIKey` for encrypted credential storage
- Enforce at API endpoint level (middleware)

---

### 3. ZeroDB Integration (COMPLETELY MISSING)

**Current**: **ZERO ZeroDB code** - searched entire codebase, no matches

**Required**:
1. **ZeroDB MCP Server Integration**
2. **Per-Agent Collection Scopes**
3. **Persistent Memory Layer**

**Implementation Gap**:
```bash
# Expected directories:
backend/integrations/zerodb/
  - client.py           # ZeroDB client wrapper
  - collections.py      # Collection management
  - memory.py           # Agent memory interface

# Expected services:
backend/services/zerodb/
  - vector_search.py    # Semantic search
  - event_stream.py     # Audit logging
  - kv_store.py         # Distributed state
  - file_storage.py     # Task artifacts

# Expected models:
backend/models/zerodb/
  - collection.py       # Collection metadata
  - memory_entry.py     # Agent memory records
  - vector_embedding.py # Semantic embeddings
```

**Current**: **All missing** - No ZeroDB integration whatsoever

**Consequence**: Agents are **stateless** - cannot:
- Remember past interactions
- Learn from historical data
- Access semantic search
- Store long-term knowledge
- Maintain brand voice consistency
- Track sales objection patterns
- Analyze content performance over time

---

### 4. Token Rotation (NOT IMPLEMENTED)

**Current**: `UserAPIKey` model has `created_at` and `updated_at` but **NO rotation logic**

**Required**: `TokenRotationPolicy` model (new)
```python
class TokenRotationPolicy(Base):
    """
    Automated token rotation policies per agent.
    Ensures 90-day rotation as per security spec.
    """
    __tablename__ = "token_rotation_policies"

    id = Column(UUID(), primary_key=True, default=uuid4)

    # Agent reference
    agent_identity_id = Column(
        UUID(),
        ForeignKey("agent_identities.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,  # One policy per agent
        index=True
    )

    # Rotation schedule
    rotation_interval_days = Column(Integer, default=90, nullable=False)
    next_rotation_date = Column(DateTime(timezone=True), nullable=False)
    last_rotation_date = Column(DateTime(timezone=True), nullable=True)

    # Grace period
    grace_period_days = Column(Integer, default=7, nullable=False)  # Old token valid for 7 days

    # Automation
    auto_rotate_enabled = Column(Boolean, default=True, nullable=False)
    notify_admin_days_before = Column(Integer, default=14, nullable=False)

    # Status
    rotation_pending = Column(Boolean, default=False, nullable=False)
    rotation_status = Column(String(50), nullable=True)  # "pending", "in_progress", "completed"

    # Audit
    rotation_history = Column(JSON, default=list)
    # Format: [{"rotated_at": "2026-01-01T00:00:00Z", "old_key_id": "uuid", "new_key_id": "uuid"}, ...]

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
```

**Required Service**: `TokenRotationService` (new)
- Background job checks `next_rotation_date` daily
- Generates new API keys
- Notifies admin 14 days before rotation
- Maintains grace period (old + new valid for 7 days)
- Updates agent credential references

---

### 5. Approval Workflows (MISSING)

**Spec Requirement**: "Publish actions require audit trail", "Revenue-affecting changes require approval workflow"

**Current**: No approval workflow exists

**Required**: `ApprovalWorkflow` model (new)
```python
class ApprovalAction(str, Enum):
    PUBLISH_CONTENT = "publish_content"
    MODIFY_REVENUE = "modify_revenue"
    UPDATE_CRM = "update_crm"
    SEND_EMAIL_CAMPAIGN = "send_email_campaign"
    CREATE_EVENT = "create_event"
    SCHEDULE_SOCIAL = "schedule_social"

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"

class ApprovalWorkflow(Base):
    """
    Approval workflows for high-impact agent actions.
    Ensures human oversight for publishing, revenue, CRM changes.
    """
    __tablename__ = "approval_workflows"

    id = Column(UUID(), primary_key=True, default=uuid4)

    # Agent who initiated action
    agent_identity_id = Column(
        UUID(),
        ForeignKey("agent_identities.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    # Action details
    action_type = Column(SQLEnum(ApprovalAction, ...), nullable=False)
    action_description = Column(Text, nullable=False)
    action_payload = Column(JSON, nullable=False)  # Full action data

    # Approval state
    status = Column(
        SQLEnum(ApprovalStatus, ...),
        default=ApprovalStatus.PENDING,
        nullable=False,
        index=True
    )

    # Approval metadata
    requested_at = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by = Column(UUID(), ForeignKey("team_members.id"), nullable=True)  # Admin who reviewed
    review_notes = Column(Text, nullable=True)

    # Expiration (auto-reject after N hours)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    # Audit trail
    audit_log = Column(JSON, default=list)

    # Indexes
    __table_args__ = (
        Index('idx_approval_workflows_status_expires', 'status', 'expires_at'),
    )
```

**Integration**:
- Middleware intercepts publish/revenue actions
- Creates `ApprovalWorkflow` record
- Notifies admin via Slack/email
- Blocks action until approved
- Executes action on approval

---

## Architecture Gaps Summary

| Component | Required | Current | Gap Severity |
|-----------|----------|---------|--------------|
| **Agent Identity Model** | ✅ Required | ⚠️ Partial (AgentSwarmInstance exists but missing 11/13 fields) | 🚨 **CRITICAL** |
| **Email-Based Addressing** | ✅ Required | ❌ Missing | 🚨 **CRITICAL** |
| **Tool Permission Model** | ✅ Required | ❌ Missing entirely | 🚨 **CRITICAL** |
| **ZeroDB Integration** | ✅ Required | ❌ No code found | 🔥 **BLOCKER** |
| **ZeroDB Collections** | ✅ Required (30+ collections across 6 agents) | ❌ Missing | 🔥 **BLOCKER** |
| **Token Rotation** | ✅ Required (90 days) | ❌ No policy | 🚨 **CRITICAL** |
| **Approval Workflows** | ✅ Required (publish/revenue) | ❌ Missing | 🚨 **CRITICAL** |
| **Scoped API Credentials** | ✅ Required (per-agent) | ⚠️ Partial (workspace-level only) | 🚨 **CRITICAL** |
| **Orchestrator Permissions** | ✅ Required (Helios role) | ❌ Missing | ⚠️ Medium |

**Total Gaps**: **9 critical components missing or severely incomplete**

---

## Compatibility Assessment

### Can Current Schema Support Agent Identities? **NO**

**Reasons**:
1. **No email field** - Cannot address agents by email (@ainative.studio)
2. **No role field** - Cannot differentiate Atlas (SEO) from Vega (Sales)
3. **No tool permissions** - Cannot enforce "Lyra has CMS publish, Sage has read-only"
4. **No ZeroDB** - Cannot provide persistent memory or collection scopes
5. **No token rotation** - Cannot meet 90-day security requirement
6. **No approval workflows** - Cannot gate publish/revenue actions

### What Would Need to Change?

**Phase 1: Schema Extensions** (Can extend existing tables)
- ✅ Add `email` to `AgentSwarmInstance`
- ✅ Add `role` enum to `AgentSwarmInstance`
- ✅ Add `tool_permissions` JSON to `AgentSwarmInstance`
- ✅ Add `zerodb_collections` ARRAY to `AgentSwarmInstance`
- ✅ Add `token_rotation_days` to `AgentSwarmInstance`

**Phase 2: New Tables** (Must create)
- 🆕 `agent_identities` (official agent directory)
- 🆕 `agent_tool_permissions` (fine-grained access control)
- 🆕 `token_rotation_policies` (automated rotation)
- 🆕 `approval_workflows` (publish/revenue gating)

**Phase 3: ZeroDB Integration** (Completely new)
- 🆕 Install ZeroDB MCP server
- 🆕 Create 30+ ZeroDB collections (seo/*, content/*, sales/*, etc.)
- 🆕 Implement agent memory interface
- 🆕 Build vector search for semantic retrieval
- 🆕 Create collection scope enforcement middleware

---

## Migration Path

### Option A: Extend Existing Schema (Minimal Changes)

**Pros**:
- Keep `AgentSwarmInstance` as core table
- Add missing fields via Alembic migration
- Backward compatible

**Cons**:
- Mixes runtime state with identity data
- Single table gets bloated (20+ fields)
- Harder to enforce separation of concerns

**Alembic Migration**:
```python
def upgrade():
    # Add agent identity fields
    op.add_column('agent_swarm_instances', sa.Column('email', sa.String(255), nullable=True))
    op.add_column('agent_swarm_instances', sa.Column('role', sa.Enum(...), nullable=True))
    op.add_column('agent_swarm_instances', sa.Column('tool_permissions', JSON, default=list))
    op.add_column('agent_swarm_instances', sa.Column('zerodb_collections', ARRAY(String), default=list))
    op.add_column('agent_swarm_instances', sa.Column('token_rotation_days', sa.Integer, default=90))
    op.add_column('agent_swarm_instances', sa.Column('last_token_rotation', DateTime, nullable=True))

    # Create unique constraint on email
    op.create_unique_constraint('uq_agent_swarm_instances_email', 'agent_swarm_instances', ['email'])
```

### Option B: New `agent_identities` Table (Recommended)

**Pros**:
- Clean separation: Identity vs Runtime
- Easier to enforce security policies
- Follows single-responsibility principle
- Can have multiple runtime instances per identity

**Cons**:
- Requires foreign key changes
- More complex queries (JOIN)
- Migration impact on existing code

**Schema Design**:
```
agent_identities (new)
  ├─ id, name, email, role
  ├─ tool_permissions, api_credentials
  ├─ zerodb_collections
  └─ token_rotation_policy

agent_swarm_instances (existing)
  ├─ id, status, openclaw_session_key
  ├─ heartbeat_enabled, last_heartbeat_at
  ├─ agent_identity_id (FK → agent_identities)
  └─ configuration

Relationship: One Identity → Many Instances
(Same agent identity can have dev + prod instances)
```

---

## Recommended Implementation Order

### Sprint 1: Core Identity Model (2 weeks)
1. ✅ Create `agent_identities` table with email + role
2. ✅ Add FK from `agent_swarm_instances.agent_identity_id`
3. ✅ Seed 7 official agents (Atlas, Lyra, Sage, Vega, Nova, Luma, Helios)
4. ✅ Update task assignment to check `agent_identity.role`
5. ✅ API endpoints: `GET /agents/identities`, `POST /agents/identities`

### Sprint 2: Tool Permissions (2 weeks)
1. ✅ Create `agent_tool_permissions` table
2. ✅ Implement permission middleware (check before CMS/CRM/etc. actions)
3. ✅ Seed tool permissions per agent (from spec document)
4. ✅ API endpoints: `GET /agents/{id}/tools`, `POST /agents/{id}/tools/grant`
5. ✅ Test: Verify Lyra can publish, Sage cannot

### Sprint 3: ZeroDB Integration (3-4 weeks)
1. ✅ Install ZeroDB MCP server
2. ✅ Create 30+ collections (seo/*, content/*, sales/*, analytics/*, growth/*, events/*)
3. ✅ Implement `ZeroDBClient` wrapper service
4. ✅ Add collection scope enforcement (agent can only write to authorized collections)
5. ✅ Migrate existing agent data to ZeroDB memory layer
6. ✅ API endpoints: `GET /agents/{id}/memory`, `POST /agents/{id}/memory`

### Sprint 4: Token Rotation (1 week)
1. ✅ Create `token_rotation_policies` table
2. ✅ Implement `TokenRotationService` background job
3. ✅ Add admin notification 14 days before rotation
4. ✅ Implement grace period (old + new keys valid for 7 days)
5. ✅ API endpoints: `GET /agents/{id}/token-status`, `POST /agents/{id}/rotate-token`

### Sprint 5: Approval Workflows (2 weeks)
1. ✅ Create `approval_workflows` table
2. ✅ Implement approval middleware for publish/revenue actions
3. ✅ Slack/email notifications for pending approvals
4. ✅ Admin dashboard for approval queue
5. ✅ API endpoints: `GET /approvals/pending`, `POST /approvals/{id}/approve`

**Total Timeline**: **10-11 weeks** for full agent identity architecture

---

## Critical Decisions Required

### Decision 1: ZeroDB vs PostgreSQL

**Question**: Use ZeroDB for agent memory or stick with Railway PostgreSQL?

**Option A: ZeroDB** (As per spec)
- ✅ Semantic vector search
- ✅ Built-in event stream
- ✅ Collection-based scoping
- ❌ Requires new MCP integration
- ❌ Learning curve for team
- ❌ Additional infrastructure

**Option B: PostgreSQL** (Current)
- ✅ Already integrated
- ✅ Team knows it
- ✅ pgvector extension for semantic search
- ❌ Manual collection scope enforcement
- ❌ No built-in event stream
- ❌ Doesn't match spec document

**Recommendation**: **ZeroDB** - Required by spec, provides superior agent memory architecture

### Decision 2: Identity Table Structure

**Question**: Extend `agent_swarm_instances` or create new `agent_identities` table?

**Recommendation**: **New `agent_identities` table** - Cleaner separation of concerns

### Decision 3: Tool Permission Granularity

**Question**: JSON field or separate table for tool permissions?

**Option A: JSON field** (simpler, faster dev)
**Option B: `agent_tool_permissions` table** (more structured, easier auditing)

**Recommendation**: **Separate table** - Required for proper auditing and fine-grained control

---

## Testing Strategy

### Unit Tests Required (New)
- `test_agent_identity_creation()`
- `test_email_uniqueness_constraint()`
- `test_tool_permission_enforcement()`
- `test_zerodb_collection_scope()`
- `test_token_rotation_schedule()`
- `test_approval_workflow_gating()`

### Integration Tests Required (New)
- `test_agent_cannot_publish_without_permission()`
- `test_lyra_can_write_to_content_collections()`
- `test_sage_can_only_read_analytics()`
- `test_token_rotates_after_90_days()`
- `test_revenue_action_requires_approval()`

### E2E Tests Required (New)
- Atlas searches SEO keywords → writes to `seo/keywords` → triggers rank tracking
- Lyra drafts blog post → submits for approval → admin approves → publishes to CMS
- Vega creates sales lead → writes to `sales/leads` → schedules email sequence

---

## Security Considerations

### Current Risks (Without Agent Identities)
1. 🔥 **No email-based authentication** - Cannot verify agent origin
2. 🔥 **No tool access control** - Any agent can call any API
3. 🔥 **No token rotation** - Stale credentials never expire
4. 🔥 **No approval workflows** - Agents can publish/modify revenue unchecked
5. 🔥 **Hard-coded credentials** - `.env` files committed to git (found in openclaw-gateway/.env)

### Post-Implementation Security
1. ✅ Email-based agent verification
2. ✅ Least-privilege tool access (read-only by default)
3. ✅ Automated token rotation (90-day cycle)
4. ✅ Approval workflows for high-impact actions
5. ✅ Encrypted credential storage (existing `UserAPIKey` model)

---

## Cost Impact

### Infrastructure Costs (New)
- **ZeroDB MCP Server**: $XX/month (pricing TBD)
- **ZeroDB Collections**: Storage for 30+ collections with vector embeddings
- **Background Jobs**: Token rotation service + approval expiration checks

### Development Costs
- **10-11 weeks** of development time
- **4 major database migrations**
- **30+ new API endpoints**
- **50+ new unit/integration tests**

---

## Appendix: Example Agent Identity Records

```sql
-- Atlas Redwood (SEO Agent)
INSERT INTO agent_identities (id, name, email, role, tool_permissions, zerodb_collections, token_rotation_days)
VALUES (
  '550e8400-e29b-41d4-a716-446655440001',
  'Atlas Redwood',
  'atlas.redwood@ainative.studio',
  'search-discoverability',
  '[
    {"tool": "google_search_console", "access_level": "read+api"},
    {"tool": "ga4", "access_level": "read"},
    {"tool": "semrush", "access_level": "api"},
    {"tool": "serp_api", "access_level": "api"},
    {"tool": "cms", "access_level": "draft", "notes": "Cannot publish without approval"}
  ]',
  ARRAY['seo/keywords', 'seo/keyword_clusters', 'seo/pages', 'seo/serp_snapshots', 'seo/ranking_history'],
  90
);

-- Lyra Chen-Sato (Content Agent)
INSERT INTO agent_identities (id, name, email, role, tool_permissions, zerodb_collections, token_rotation_days)
VALUES (
  '550e8400-e29b-41d4-a716-446655440002',
  'Lyra Chen-Sato',
  'lyra.chen-sato@ainative.studio',
  'content-brand',
  '[
    {"tool": "cms", "access_level": "draft+publish", "provider": "strapi", "notes": "Controlled publishing"},
    {"tool": "social_scheduler", "access_level": "api", "provider": "buffer"},
    {"tool": "image_gen", "access_level": "api"},
    {"tool": "email_marketing", "access_level": "draft+schedule", "provider": "resend"}
  ]',
  ARRAY['content/blogs', 'content/social_posts', 'content/newsletters', 'brand/voice_memory', 'brand/style_guidelines'],
  90
);

-- Helios Mercer (Orchestrator)
INSERT INTO agent_identities (id, name, email, role, tool_permissions, zerodb_collections, is_orchestrator, can_assign_tasks)
VALUES (
  '550e8400-e29b-41d4-a716-446655440007',
  'Helios Mercer',
  'helios.mercer@ainative.studio',
  'orchestration',
  '[
    {"tool": "all_agents", "access_level": "read", "notes": "Read across all agents"},
    {"tool": "task_assignment", "access_level": "write", "notes": "Can assign tasks"},
    {"tool": "experiments", "access_level": "pause", "notes": "Can pause experiments"}
  ]',
  ARRAY[],  -- No direct collection access
  true,  -- is_orchestrator
  true   -- can_assign_tasks
);
```

---

*End of Analysis*

**Next Steps**: Review this gap analysis → Make architectural decisions → Proceed to remediation roadmap design.
