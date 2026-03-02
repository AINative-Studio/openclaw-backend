# OpenClaw Production Remediation Roadmap

**Version**: 1.0
**Date**: 2026-03-02
**Status**: DRAFT - Awaiting ZeroDB Architecture Decision

## Executive Summary

This roadmap consolidates remediation for **16 critical gaps** identified across two comprehensive analyses:

- **7 Production Infrastructure Gaps** (docs/PRODUCTION_GAPS.md)
- **9 Agent Identity Schema Gaps** (docs/AGENT_IDENTITY_GAP_ANALYSIS.md)

**Total Estimated Timeline**: 14-16 weeks (3.5-4 months)
**Critical Path Blocker**: ZeroDB integration decision (affects 4 weeks of timeline)

### Priority Classification

| Priority | Count | Examples |
|----------|-------|----------|
| **P0 (Blocking)** | 4 | Agent-hardware link, database schema conflicts, capability validation, agent identity model |
| **P1 (Critical)** | 6 | Agent identity in tasks, tool permissions, token rotation, approval workflows |
| **P2 (High)** | 4 | SQLite replacement, monitoring, ZeroDB integration, API credential management |
| **P3 (Medium)** | 2 | Documentation updates, test coverage |

---

## Phase 1: Foundation (Weeks 1-4)

**Goal**: Establish core data model integrity and resolve critical blocking issues.

### Sprint 1.1: Database Schema Unification (Week 1-2)

**Addresses**:
- PRODUCTION_GAPS.md → Gap 2 (Database Schema Conflicts)
- PRODUCTION_GAPS.md → Gap 3 (SQLite in Production)

**Blocker**: THREE incompatible model files define overlapping schemas:
- `backend/models/task_models.py` (Integer PKs, SQLite, 5 TaskStatus values)
- `backend/models/task_queue.py` (UUID PKs, PostgreSQL, 7 TaskStatus values)
- `backend/models/task_lease_models.py` (UUID PKs, PostgreSQL, TaskComplexity enum)

**Tasks**:

1. **Audit all service dependencies** (Day 1-2)
   ```bash
   # Identify which services import which model files
   grep -r "from backend.models.task" backend/services/
   grep -r "from backend.models.task_queue" backend/services/
   grep -r "from backend.models.task_lease" backend/services/
   ```

2. **Design unified schema** (Day 3-4)
   ```python
   # Proposed: backend/models/unified_task.py

   class TaskStatus(str, Enum):
       QUEUED = "queued"
       LEASED = "leased"
       RUNNING = "running"
       COMPLETED = "completed"
       FAILED = "failed"
       EXPIRED = "expired"
       PERMANENTLY_FAILED = "permanently_failed"

   class TaskComplexity(str, Enum):
       LOW = "low"          # 5 min lease
       MEDIUM = "medium"    # 10 min lease
       HIGH = "high"        # 15 min lease

   class Task(Base):
       __tablename__ = "tasks"

       id = Column(UUID(), primary_key=True, default=uuid4)
       task_id = Column(String(255), unique=True, nullable=False, index=True)
       task_type = Column(String(100), nullable=False, index=True)

       status = Column(SQLEnum(TaskStatus), default=TaskStatus.QUEUED, index=True)
       priority = Column(Integer, default=5, nullable=False)

       payload = Column(JSON, default=dict)
       result = Column(JSON, nullable=True)
       error_message = Column(Text, nullable=True)

       # Idempotency
       idempotency_key = Column(String(255), unique=True, nullable=True, index=True)

       # Retry logic
       retry_count = Column(Integer, default=0)
       max_retries = Column(Integer, default=3)

       # Capability requirements
       required_capabilities = Column(JSON, default=dict)
       complexity = Column(SQLEnum(TaskComplexity), default=TaskComplexity.MEDIUM)

       # Assignment tracking
       assigned_peer_id = Column(String(255), nullable=True, index=True)
       assigned_at = Column(DateTime(timezone=True), nullable=True)

       created_at = Column(DateTime(timezone=True), server_default=func.now())
       updated_at = Column(DateTime(timezone=True), onupdate=func.now())
       completed_at = Column(DateTime(timezone=True), nullable=True)

   class TaskLease(Base):
       __tablename__ = "task_leases"

       id = Column(UUID(), primary_key=True, default=uuid4)
       task_id = Column(UUID(), ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True)

       peer_id = Column(String(255), ForeignKey("node_capabilities.peer_id"), nullable=False, index=True)
       lease_token = Column(Text, nullable=False)  # JWT

       issued_at = Column(DateTime(timezone=True), server_default=func.now())
       expires_at = Column(DateTime(timezone=True), nullable=False, index=True)

       is_active = Column(Boolean, default=True, index=True)
       is_revoked = Column(Boolean, default=False)
       revoked_at = Column(DateTime(timezone=True), nullable=True)
       revoke_reason = Column(String(500), nullable=True)

       heartbeat_count = Column(Integer, default=0)
       last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)

       # Snapshot node capabilities at lease time
       node_capabilities = Column(JSON, default=dict)
   ```

3. **Create Alembic migration** (Day 5)
   ```bash
   alembic revision --autogenerate -m "Unify task and lease schemas"
   ```

4. **Write data migration script** (Day 6-7)
   ```python
   # scripts/migrate_task_models.py
   # - Copy data from old tables to unified schema
   # - Validate UUID conversion (Integer → UUID)
   # - Handle TaskStatus value mapping (5-value → 7-value enum)
   # - Verify foreign key integrity
   ```

5. **Update all service imports** (Day 8-9)
   - TaskAssignmentOrchestrator
   - TaskRequeueService
   - LeaseIssuanceService
   - LeaseExpirationService
   - LeaseRevocationService
   - TaskResultProtocol
   - 15+ other services

6. **Run migration on staging** (Day 10)
   ```bash
   # Staging Railway database
   alembic upgrade head
   python scripts/migrate_task_models.py --verify-only
   python scripts/migrate_task_models.py --execute
   ```

**Success Criteria**:
- [ ] All services use single `unified_task.py` model
- [ ] Migration runs without data loss
- [ ] All 690 tests pass with new schema
- [ ] Zero import errors in codebase

**Risk**: HIGH - touches 30+ files, requires data migration

---

### Sprint 1.2: Agent-Hardware Capability Link (Week 3-4)

**Addresses**:
- PRODUCTION_GAPS.md → Gap 1 (Broken Agent-to-Hardware Link)
- PRODUCTION_GAPS.md → Gap 7 (No Agent Identity in Task Payloads)

**Critical Bug**: AgentSwarmInstance has no `peer_id`, NodeCapability has no `agent_id`. Tasks can be assigned to wrong agent persona.

**Tasks**:

1. **Extend AgentSwarmInstance model** (Day 1)
   ```python
   # backend/models/agent_swarm_lifecycle.py

   class AgentSwarmInstance(Base):
       # ... existing fields ...

       # NEW: Link to hardware node
       peer_id = Column(
           String(255),
           ForeignKey("node_capabilities.peer_id", ondelete="SET NULL"),
           nullable=True,
           index=True
       )
       node = relationship("NodeCapability", backref="agents")
   ```

2. **Extend NodeCapability model** (Day 1)
   ```python
   # backend/models/task_lease_models.py

   class NodeCapability(Base):
       # ... existing fields ...

       # NEW: Link to agent identity
       agent_id = Column(
           UUID(),
           ForeignKey("agent_swarm_instances.id", ondelete="SET NULL"),
           nullable=True,
           index=True
       )
   ```

3. **Create Alembic migration** (Day 2)
   ```bash
   alembic revision --autogenerate -m "Add agent-hardware bidirectional link"
   ```

4. **Update TaskAssignmentOrchestrator** (Day 3-5)
   ```python
   # backend/services/task_assignment_orchestrator.py

   def _match_node_to_task(self, requirements, available_nodes):
       """Match task to node based on BOTH hardware AND agent identity"""

       required_agent_id = requirements.get("agent_id")
       required_persona = requirements.get("persona")
       required_model = requirements.get("model")

       for node in available_nodes:
           # 1. Check hardware capabilities (existing logic)
           if not self._node_matches_hardware_requirements(node, requirements):
               continue

           # 2. NEW: Check agent identity match
           if required_agent_id:
               if node.get("agent_id") != required_agent_id:
                   logger.warning(
                       f"Node {node['peer_id']} agent mismatch: "
                       f"required={required_agent_id}, actual={node.get('agent_id')}"
                   )
                   continue

           # 3. NEW: Check persona match
           if required_persona:
               if node.get("agent_persona") != required_persona:
                   logger.warning(
                       f"Node {node['peer_id']} persona mismatch: "
                       f"required={required_persona}, actual={node.get('agent_persona')}"
                   )
                   continue

           # 4. NEW: Check model compatibility
           if required_model:
               if node.get("agent_model") != required_model:
                   logger.warning(
                       f"Node {node['peer_id']} model mismatch: "
                       f"required={required_model}, actual={node.get('agent_model')}"
                   )
                   continue

           return node

       return None
   ```

5. **Update task payload schema** (Day 6)
   ```python
   # backend/schemas/task_schemas.py

   class TaskCreateRequest(BaseModel):
       task_id: str
       task_type: str
       payload: dict

       # NEW: Agent identity requirements
       required_agent_id: Optional[UUID] = None
       required_persona: Optional[str] = None
       required_model: Optional[str] = None

       # Existing hardware requirements
       required_capabilities: dict = {}
   ```

6. **Update WireGuard provisioning** (Day 7-8)
   ```python
   # backend/api/v1/endpoints/wireguard_provisioning.py

   @router.post("/provision")
   async def provision_peer(request: ProvisioningRequest):
       # ... existing WireGuard setup ...

       # NEW: Link agent to node capability
       agent = await db.query(AgentSwarmInstance).filter_by(
           id=request.agent_id
       ).first()

       if agent:
           node_capability.agent_id = agent.id
           agent.peer_id = node_capability.peer_id
           await db.commit()
   ```

7. **Write integration tests** (Day 9-10)
   ```python
   # tests/integration/test_agent_capability_link.py

   def test_task_assigned_to_correct_agent_persona():
       """Task requiring 'Atlas Redwood' SEO agent goes to SEO-capable node"""

   def test_task_rejected_for_wrong_persona():
       """Task requiring 'Lyra Chen-Sato' content agent rejects hardware with 'Atlas' agent"""

   def test_hardware_capability_still_enforced():
       """GPU task still requires GPU-capable node even if agent persona matches"""
   ```

**Success Criteria**:
- [ ] AgentSwarmInstance.peer_id and NodeCapability.agent_id populated
- [ ] TaskAssignmentOrchestrator validates both hardware + identity
- [ ] Tasks include agent_id/persona/model in payload
- [ ] WireGuard provisioning links agent to node
- [ ] Integration tests pass (hardware + identity validation)

**Risk**: MEDIUM - changes core task assignment logic, requires coordination with provisioning

---

## Phase 2: Agent Identity System (Weeks 5-8)

**Goal**: Implement comprehensive agent identity model with role-based access control.

### Sprint 2.1: Agent Identity Core Model (Week 5-6)

**Addresses**:
- AGENT_IDENTITY_GAP_ANALYSIS.md → Gap 1 (Agent Identity Model)
- AGENT_IDENTITY_GAP_ANALYSIS.md → Gap 2 (Tool Permission Model)

**Tasks**:

1. **Create AgentRole enum** (Day 1)
   ```python
   # backend/models/agent_identity.py

   class AgentRole(str, Enum):
       SEARCH_DISCOVERABILITY = "search-discoverability"     # Atlas Redwood
       CONTENT_BRAND = "content-brand"                       # Lyra Chen-Sato
       ANALYTICS_INSIGHTS = "analytics-insights"             # Sage Okafor
       SALES_CONVERSION = "sales-conversion"                 # Vega Martinez
       GROWTH_FUNNEL = "growth-funnel"                       # Nova Sinclair
       EVENTS_COMMUNITY = "events-community"                 # Luma Harrington
       ORCHESTRATION = "orchestration"                       # Helios Mercer

   class ToolType(str, Enum):
       CMS = "cms"
       SOCIAL_MEDIA = "social_media"
       ANALYTICS = "analytics"
       CRM = "crm"
       EMAIL_MARKETING = "email_marketing"
       AB_TESTING = "ab_testing"
       EVENTS = "events"
       PAYMENTS = "payments"
       DOCUMENT_SIGNING = "document_signing"
       CALENDAR = "calendar"
   ```

2. **Create AgentIdentity model** (Day 2-3)
   ```python
   class AgentIdentity(Base):
       __tablename__ = "agent_identities"

       id = Column(UUID(), primary_key=True, default=uuid4)

       # Identity
       name = Column(String(255), nullable=False, unique=True, index=True)
       email = Column(String(255), nullable=False, unique=True, index=True)
       role = Column(SQLEnum(AgentRole), nullable=False, index=True)

       # Link to runtime instance
       agent_swarm_instance_id = Column(
           UUID(),
           ForeignKey("agent_swarm_instances.id", ondelete="SET NULL"),
           nullable=True
       )
       agent_swarm_instance = relationship("AgentSwarmInstance", backref="identity")

       # Tool permissions (JSON array of ToolType enum values)
       tool_permissions = Column(JSON, default=list, nullable=False)

       # Orchestration capabilities
       is_orchestrator = Column(Boolean, default=False, index=True)
       can_assign_tasks = Column(Boolean, default=False)
       can_approve_publish = Column(Boolean, default=False)
       can_approve_revenue = Column(Boolean, default=False)

       # Metadata
       created_at = Column(DateTime(timezone=True), server_default=func.now())
       updated_at = Column(DateTime(timezone=True), onupdate=func.now())
       is_active = Column(Boolean, default=True, index=True)
   ```

3. **Create ToolPermission model** (Day 4)
   ```python
   class ToolPermission(Base):
       __tablename__ = "tool_permissions"

       id = Column(UUID(), primary_key=True, default=uuid4)
       agent_identity_id = Column(
           UUID(),
           ForeignKey("agent_identities.id", ondelete="CASCADE"),
           nullable=False,
           index=True
       )

       tool_type = Column(SQLEnum(ToolType), nullable=False)

       # Granular permissions
       can_read = Column(Boolean, default=True)
       can_write = Column(Boolean, default=False)
       can_delete = Column(Boolean, default=False)
       can_publish = Column(Boolean, default=False)

       # Constraints (e.g., "only draft posts", "only test campaigns")
       constraints = Column(JSON, default=dict)

       granted_at = Column(DateTime(timezone=True), server_default=func.now())
       expires_at = Column(DateTime(timezone=True), nullable=True)

       __table_args__ = (
           UniqueConstraint('agent_identity_id', 'tool_type', name='uix_agent_tool'),
       )
   ```

4. **Create Pydantic schemas** (Day 5)
   ```python
   # backend/schemas/agent_identity.py

   class AgentIdentityCreate(BaseModel):
       name: str = Field(..., min_length=1, max_length=255)
       email: EmailStr
       role: AgentRole
       tool_permissions: List[ToolType] = []
       is_orchestrator: bool = False

   class AgentIdentityResponse(BaseModel):
       id: UUID
       name: str
       email: str
       role: AgentRole
       tool_permissions: List[ToolType]
       is_orchestrator: bool
       can_assign_tasks: bool
       is_active: bool
       created_at: datetime

       class Config:
           from_attributes = True

   class ToolPermissionCreate(BaseModel):
       tool_type: ToolType
       can_read: bool = True
       can_write: bool = False
       can_delete: bool = False
       can_publish: bool = False
       constraints: dict = {}
   ```

5. **Create Alembic migration** (Day 6)
   ```bash
   alembic revision --autogenerate -m "Add agent identity and tool permission models"
   ```

6. **Seed production agent identities** (Day 7-8)
   ```python
   # scripts/seed_agent_identities.py

   PRODUCTION_AGENTS = [
       {
           "name": "Atlas Redwood",
           "email": "atlas.redwood@ainative.studio",
           "role": AgentRole.SEARCH_DISCOVERABILITY,
           "tool_permissions": [ToolType.CMS, ToolType.ANALYTICS, ToolType.AB_TESTING],
           "is_orchestrator": False,
       },
       {
           "name": "Lyra Chen-Sato",
           "email": "lyra.chen-sato@ainative.studio",
           "role": AgentRole.CONTENT_BRAND,
           "tool_permissions": [ToolType.CMS, ToolType.SOCIAL_MEDIA, ToolType.ANALYTICS],
           "is_orchestrator": False,
       },
       # ... 5 more agents ...
       {
           "name": "Helios Mercer",
           "email": "helios.mercer@ainative.studio",
           "role": AgentRole.ORCHESTRATION,
           "tool_permissions": list(ToolType),  # All tools
           "is_orchestrator": True,
           "can_assign_tasks": True,
           "can_approve_publish": True,
           "can_approve_revenue": True,
       },
   ]
   ```

7. **Write unit tests** (Day 9-10)
   ```python
   # tests/models/test_agent_identity.py

   def test_agent_identity_unique_email():
       """Cannot create two agents with same email"""

   def test_tool_permission_granularity():
       """Can grant read-only CMS access"""

   def test_orchestrator_has_all_permissions():
       """Helios Mercer can access all tools"""
   ```

**Success Criteria**:
- [ ] AgentIdentity and ToolPermission models created
- [ ] Pydantic schemas for API endpoints
- [ ] Migration runs successfully
- [ ] 7 production agents seeded with correct permissions
- [ ] Unit tests pass (100% coverage)

**Risk**: LOW - net new models, no existing code changes

---

### Sprint 2.2: Tool Permission Enforcement (Week 7-8)

**Addresses**:
- AGENT_IDENTITY_GAP_ANALYSIS.md → Gap 2 (Tool Permission Model)
- AGENT_IDENTITY_GAP_ANALYSIS.md → Gap 5 (Approval Workflows)

**Tasks**:

1. **Create ToolPermissionService** (Day 1-2)
   ```python
   # backend/services/tool_permission_service.py

   class ToolPermissionService:
       def __init__(self, db: AsyncSession):
           self.db = db

       async def check_permission(
           self,
           agent_identity_id: UUID,
           tool_type: ToolType,
           action: str,  # "read", "write", "delete", "publish"
       ) -> bool:
           """Check if agent has permission for action on tool"""

           permission = await self.db.query(ToolPermission).filter_by(
               agent_identity_id=agent_identity_id,
               tool_type=tool_type
           ).first()

           if not permission:
               return False

           # Check expiration
           if permission.expires_at and permission.expires_at < datetime.now(timezone.utc):
               return False

           # Check action-specific permission
           if action == "read" and not permission.can_read:
               return False
           if action == "write" and not permission.can_write:
               return False
           if action == "delete" and not permission.can_delete:
               return False
           if action == "publish" and not permission.can_publish:
               return False

           return True

       async def require_permission(
           self,
           agent_identity_id: UUID,
           tool_type: ToolType,
           action: str
       ):
           """Raise PermissionDeniedError if agent lacks permission"""

           has_permission = await self.check_permission(
               agent_identity_id, tool_type, action
           )

           if not has_permission:
               raise PermissionDeniedError(
                   f"Agent {agent_identity_id} lacks '{action}' permission for {tool_type}"
               )
   ```

2. **Create approval workflow model** (Day 3-4)
   ```python
   # backend/models/approval_workflow.py

   class ApprovalType(str, Enum):
       PUBLISH_CONTENT = "publish_content"
       REVENUE_TRANSACTION = "revenue_transaction"
       EXTERNAL_API_CALL = "external_api_call"
       SCHEMA_CHANGE = "schema_change"

   class ApprovalStatus(str, Enum):
       PENDING = "pending"
       APPROVED = "approved"
       REJECTED = "rejected"
       EXPIRED = "expired"

   class ApprovalRequest(Base):
       __tablename__ = "approval_requests"

       id = Column(UUID(), primary_key=True, default=uuid4)
       approval_type = Column(SQLEnum(ApprovalType), nullable=False, index=True)

       # Requester
       requester_agent_id = Column(
           UUID(),
           ForeignKey("agent_identities.id"),
           nullable=False
       )
       requester = relationship("AgentIdentity", foreign_keys=[requester_agent_id])

       # Approver
       approver_agent_id = Column(
           UUID(),
           ForeignKey("agent_identities.id"),
           nullable=True
       )
       approver = relationship("AgentIdentity", foreign_keys=[approver_agent_id])

       status = Column(SQLEnum(ApprovalStatus), default=ApprovalStatus.PENDING, index=True)

       # Request details
       resource_type = Column(String(100), nullable=False)  # "blog_post", "email_campaign"
       resource_id = Column(String(255), nullable=False)
       action_payload = Column(JSON, default=dict)

       # Metadata
       requested_at = Column(DateTime(timezone=True), server_default=func.now())
       reviewed_at = Column(DateTime(timezone=True), nullable=True)
       expires_at = Column(DateTime(timezone=True), nullable=False)  # 24h default

       rejection_reason = Column(Text, nullable=True)
   ```

3. **Create ApprovalWorkflowService** (Day 5-6)
   ```python
   # backend/services/approval_workflow_service.py

   class ApprovalWorkflowService:
       async def request_approval(
           self,
           requester_agent_id: UUID,
           approval_type: ApprovalType,
           resource_type: str,
           resource_id: str,
           action_payload: dict
       ) -> ApprovalRequest:
           """Create approval request for high-risk action"""

           # Find eligible approver (must be orchestrator)
           approver = await self.db.query(AgentIdentity).filter_by(
               is_orchestrator=True,
               is_active=True
           ).first()

           if not approver:
               raise NoApproverAvailableError()

           expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

           request = ApprovalRequest(
               approval_type=approval_type,
               requester_agent_id=requester_agent_id,
               approver_agent_id=approver.id,
               resource_type=resource_type,
               resource_id=resource_id,
               action_payload=action_payload,
               expires_at=expires_at
           )

           self.db.add(request)
           await self.db.commit()

           # Send notification to approver (Helios)
           await self._notify_approver(approver, request)

           return request

       async def approve(
           self,
           request_id: UUID,
           approver_agent_id: UUID
       ) -> ApprovalRequest:
           """Approve pending request"""

           request = await self.db.get(ApprovalRequest, request_id)

           if request.status != ApprovalStatus.PENDING:
               raise InvalidApprovalStateError()

           if request.approver_agent_id != approver_agent_id:
               raise UnauthorizedApproverError()

           request.status = ApprovalStatus.APPROVED
           request.reviewed_at = datetime.now(timezone.utc)

           await self.db.commit()

           # Execute approved action
           await self._execute_approved_action(request)

           return request
   ```

4. **Add permission checks to endpoints** (Day 7-8)
   ```python
   # Example: backend/api/v1/endpoints/content_management.py

   @router.post("/blog-posts/{post_id}/publish")
   async def publish_blog_post(
       post_id: str,
       agent_identity_id: UUID = Depends(get_current_agent_identity),
       db: AsyncSession = Depends(get_db)
   ):
       tool_permission_service = ToolPermissionService(db)
       approval_service = ApprovalWorkflowService(db)

       # 1. Check if agent has CMS publish permission
       try:
           await tool_permission_service.require_permission(
               agent_identity_id,
               ToolType.CMS,
               "publish"
           )
       except PermissionDeniedError:
           # 2. If not, request approval from orchestrator
           approval_request = await approval_service.request_approval(
               requester_agent_id=agent_identity_id,
               approval_type=ApprovalType.PUBLISH_CONTENT,
               resource_type="blog_post",
               resource_id=post_id,
               action_payload={"action": "publish"}
           )

           return {
               "status": "pending_approval",
               "approval_request_id": str(approval_request.id),
               "message": "Publish action requires approval from orchestrator"
           }

       # 3. Agent has permission, publish directly
       await cms_service.publish_post(post_id)

       return {"status": "published"}
   ```

5. **Write integration tests** (Day 9-10)
   ```python
   # tests/integration/test_tool_permissions.py

   @pytest.mark.asyncio
   async def test_atlas_can_read_cms_but_not_publish():
       """Atlas Redwood (SEO) can read CMS but publish requires approval"""

   @pytest.mark.asyncio
   async def test_helios_can_approve_publish_request():
       """Helios Mercer (orchestrator) can approve Lyra's publish request"""

   @pytest.mark.asyncio
   async def test_vega_cannot_access_events_tool():
       """Vega Martinez (Sales) has no permission for Events tool"""
   ```

**Success Criteria**:
- [ ] ToolPermissionService validates all tool access
- [ ] ApprovalWorkflowService handles publish/revenue actions
- [ ] High-risk actions require orchestrator approval
- [ ] Integration tests pass (permission enforcement)
- [ ] Audit logs capture all permission checks

**Risk**: MEDIUM - requires retrofitting permission checks into existing endpoints

---

## Phase 3: Security & Data Management (Weeks 9-11)

**Goal**: Implement token rotation, API credential management, and ZeroDB integration (pending decision).

### Sprint 3.1: Token Rotation & API Credentials (Week 9-10)

**Addresses**:
- AGENT_IDENTITY_GAP_ANALYSIS.md → Gap 4 (Token Rotation)
- AGENT_IDENTITY_GAP_ANALYSIS.md → Gap 6 (API Credential Management)

**Tasks**:

1. **Extend AgentIdentity for token rotation** (Day 1)
   ```python
   # backend/models/agent_identity.py (add fields)

   class AgentIdentity(Base):
       # ... existing fields ...

       # Token rotation
       token_rotation_days = Column(Integer, default=90, nullable=False)
       last_token_rotation = Column(DateTime(timezone=True), nullable=True)
       next_token_rotation = Column(DateTime(timezone=True), nullable=True, index=True)
   ```

2. **Create APICredential model** (Day 2-3)
   ```python
   # backend/models/api_credential.py

   class APIProvider(str, Enum):
       STRAPI_CMS = "strapi_cms"
       GOOGLE_ANALYTICS = "google_analytics"
       HUBSPOT_CRM = "hubspot_crm"
       SENDGRID_EMAIL = "sendgrid_email"
       STRIPE_PAYMENTS = "stripe_payments"
       DOCUSIGN = "docusign"
       GOOGLE_CALENDAR = "google_calendar"

   class APICredential(Base):
       __tablename__ = "api_credentials"

       id = Column(UUID(), primary_key=True, default=uuid4)

       agent_identity_id = Column(
           UUID(),
           ForeignKey("agent_identities.id", ondelete="CASCADE"),
           nullable=False,
           index=True
       )

       provider = Column(SQLEnum(APIProvider), nullable=False)

       # Encrypted credentials (Fernet encrypted)
       encrypted_api_key = Column(Text, nullable=True)
       encrypted_api_secret = Column(Text, nullable=True)
       encrypted_refresh_token = Column(Text, nullable=True)

       # Metadata
       created_at = Column(DateTime(timezone=True), server_default=func.now())
       last_used_at = Column(DateTime(timezone=True), nullable=True)
       expires_at = Column(DateTime(timezone=True), nullable=True)

       is_active = Column(Boolean, default=True, index=True)

       __table_args__ = (
           UniqueConstraint('agent_identity_id', 'provider', name='uix_agent_provider'),
       )
   ```

3. **Create TokenRotationService** (Day 4-5)
   ```python
   # backend/services/token_rotation_service.py

   class TokenRotationService:
       async def rotate_agent_token(self, agent_identity_id: UUID) -> str:
           """Rotate agent's JWT capability token"""

           agent = await self.db.get(AgentIdentity, agent_identity_id)

           # Generate new capability token via existing TokenService
           from backend.security.token_service import TokenService
           token_service = TokenService()

           # Get agent's current capabilities
           capabilities = await self._get_agent_capabilities(agent)

           new_token = token_service.encode_token(capabilities)

           # Update rotation tracking
           now = datetime.now(timezone.utc)
           agent.last_token_rotation = now
           agent.next_token_rotation = now + timedelta(days=agent.token_rotation_days)

           await self.db.commit()

           # Audit log
           await self._log_token_rotation(agent_identity_id)

           return new_token

       async def check_rotation_due(self) -> List[UUID]:
           """Find agents with tokens expiring in next 7 days"""

           threshold = datetime.now(timezone.utc) + timedelta(days=7)

           agents = await self.db.query(AgentIdentity).filter(
               AgentIdentity.next_token_rotation <= threshold,
               AgentIdentity.is_active == True
           ).all()

           return [agent.id for agent in agents]
   ```

4. **Create APICredentialService** (Day 6-7)
   ```python
   # backend/services/api_credential_service.py

   from cryptography.fernet import Fernet

   class APICredentialService:
       def __init__(self, encryption_key: str):
           self.fernet = Fernet(encryption_key.encode())

       async def store_credential(
           self,
           agent_identity_id: UUID,
           provider: APIProvider,
           api_key: str,
           api_secret: Optional[str] = None,
           refresh_token: Optional[str] = None
       ) -> APICredential:
           """Encrypt and store API credentials"""

           credential = APICredential(
               agent_identity_id=agent_identity_id,
               provider=provider,
               encrypted_api_key=self._encrypt(api_key),
               encrypted_api_secret=self._encrypt(api_secret) if api_secret else None,
               encrypted_refresh_token=self._encrypt(refresh_token) if refresh_token else None
           )

           self.db.add(credential)
           await self.db.commit()

           return credential

       async def get_credential(
           self,
           agent_identity_id: UUID,
           provider: APIProvider
       ) -> Dict[str, str]:
           """Retrieve and decrypt API credentials"""

           credential = await self.db.query(APICredential).filter_by(
               agent_identity_id=agent_identity_id,
               provider=provider,
               is_active=True
           ).first()

           if not credential:
               raise CredentialNotFoundError()

           if credential.expires_at and credential.expires_at < datetime.now(timezone.utc):
               raise CredentialExpiredError()

           # Update last_used_at
           credential.last_used_at = datetime.now(timezone.utc)
           await self.db.commit()

           return {
               "api_key": self._decrypt(credential.encrypted_api_key),
               "api_secret": self._decrypt(credential.encrypted_api_secret) if credential.encrypted_api_secret else None,
               "refresh_token": self._decrypt(credential.encrypted_refresh_token) if credential.encrypted_refresh_token else None
           }
   ```

5. **Create background rotation job** (Day 8)
   ```python
   # backend/jobs/token_rotation_job.py

   import asyncio
   from apscheduler.schedulers.asyncio import AsyncIOScheduler

   class TokenRotationJob:
       def __init__(self):
           self.scheduler = AsyncIOScheduler()

       async def check_and_rotate_tokens(self):
           """Check for tokens due for rotation (runs daily)"""

           token_service = TokenRotationService(db)

           agents_due = await token_service.check_rotation_due()

           for agent_id in agents_due:
               try:
                   new_token = await token_service.rotate_agent_token(agent_id)
                   logger.info(f"Rotated token for agent {agent_id}")
               except Exception as e:
                   logger.error(f"Token rotation failed for {agent_id}: {e}")

       def start(self):
           # Run daily at 2 AM UTC
           self.scheduler.add_job(
               self.check_and_rotate_tokens,
               'cron',
               hour=2,
               minute=0
           )
           self.scheduler.start()
   ```

6. **Write unit and integration tests** (Day 9-10)
   ```python
   # tests/services/test_token_rotation.py

   @pytest.mark.asyncio
   async def test_token_rotation_creates_new_token():
       """Rotating token updates last_token_rotation and next_token_rotation"""

   @pytest.mark.asyncio
   async def test_rotation_due_returns_expiring_agents():
       """Agents with tokens expiring in 7 days are flagged"""

   # tests/services/test_api_credential.py

   @pytest.mark.asyncio
   async def test_api_credential_encryption():
       """Stored credentials are encrypted with Fernet"""

   @pytest.mark.asyncio
   async def test_credential_retrieval_updates_last_used():
       """Getting credential updates last_used_at timestamp"""
   ```

**Success Criteria**:
- [ ] TokenRotationService rotates capability tokens on 90-day schedule
- [ ] APICredentialService encrypts/decrypts credentials with Fernet
- [ ] Background job checks for rotation daily
- [ ] Unit tests pass (encryption, rotation logic)
- [ ] Integration tests pass (end-to-end rotation)

**Risk**: MEDIUM - requires coordination with existing TokenService (E7-S1)

---

### Sprint 3.2: ZeroDB Integration (Week 11) **[CONDITIONAL]**

**Addresses**:
- AGENT_IDENTITY_GAP_ANALYSIS.md → Gap 3 (ZeroDB Integration)
- PRODUCTION_GAPS.md → Gap 4 (No ZeroDB Integration)

**BLOCKER**: This sprint depends on architectural decision. Two paths:

#### Option A: Implement ZeroDB (if decision: YES)

**Tasks**:

1. **Install ZeroDB MCP server** (Day 1)
   ```bash
   # Add to .claude/mcp_servers.json
   {
     "zerodb": {
       "command": "npx",
       "args": ["-y", "@ainative/zerodb-mcp-server"],
       "env": {
         "ZERODB_API_KEY": "${ZERODB_API_KEY}",
         "ZERODB_PROJECT_ID": "${ZERODB_PROJECT_ID}"
       }
     }
   }
   ```

2. **Create ZeroDBClient wrapper** (Day 2-3)
   ```python
   # backend/integrations/zerodb_client.py

   import httpx

   class ZeroDBClient:
       def __init__(self, api_key: str, project_id: str):
           self.api_key = api_key
           self.project_id = project_id
           self.base_url = "https://api.zerodb.io/v1"

       async def store_agent_memory(
           self,
           agent_identity_id: UUID,
           collection: str,
           data: dict
       ) -> str:
           """Store agent memory in ZeroDB collection"""

           async with httpx.AsyncClient() as client:
               response = await client.post(
                   f"{self.base_url}/projects/{self.project_id}/collections/{collection}/documents",
                   headers={"Authorization": f"Bearer {self.api_key}"},
                   json=data
               )
               response.raise_for_status()
               return response.json()["document_id"]

       async def query_agent_memory(
           self,
           agent_identity_id: UUID,
           collection: str,
           query: str,
           limit: int = 10
       ) -> List[dict]:
           """Semantic search in agent's memory"""

           async with httpx.AsyncClient() as client:
               response = await client.post(
                   f"{self.base_url}/projects/{self.project_id}/collections/{collection}/search",
                   headers={"Authorization": f"Bearer {self.api_key}"},
                   json={
                       "query": query,
                       "limit": limit,
                       "filter": {"agent_identity_id": str(agent_identity_id)}
                   }
               )
               response.raise_for_status()
               return response.json()["results"]
   ```

3. **Map agent roles to ZeroDB collections** (Day 4)
   ```python
   # backend/config/zerodb_collections.py

   AGENT_COLLECTION_MAPPING = {
       AgentRole.SEARCH_DISCOVERABILITY: [
           "seo/keywords",
           "seo/rankings",
           "seo/backlinks",
           "seo/performance"
       ],
       AgentRole.CONTENT_BRAND: [
           "content/drafts",
           "content/published",
           "content/engagement",
           "content/brand_voice"
       ],
       AgentRole.ANALYTICS_INSIGHTS: [
           "analytics/traffic",
           "analytics/conversions",
           "analytics/cohorts",
           "analytics/reports"
       ],
       # ... 4 more agents ...
   }
   ```

4. **Extend AgentIdentity model** (Day 5)
   ```python
   # backend/models/agent_identity.py (add field)

   class AgentIdentity(Base):
       # ... existing fields ...

       # ZeroDB collections (PostgreSQL ARRAY type)
       zerodb_collections = Column(ARRAY(String), default=list, nullable=False)
   ```

5. **Create data migration script** (Day 6)
   ```python
   # scripts/populate_zerodb_collections.py

   async def populate_zerodb_collections():
       """Populate zerodb_collections field for existing agents"""

       for agent in await db.query(AgentIdentity).all():
           collections = AGENT_COLLECTION_MAPPING.get(agent.role, [])
           agent.zerodb_collections = collections
           await db.commit()
   ```

6. **Write integration tests** (Day 7-10)
   ```python
   # tests/integration/test_zerodb_integration.py

   @pytest.mark.asyncio
   async def test_atlas_can_access_seo_collections():
       """Atlas Redwood can read/write seo/* collections"""

   @pytest.mark.asyncio
   async def test_lyra_cannot_access_sales_collections():
       """Lyra Chen-Sato has no access to sales/* collections"""

   @pytest.mark.asyncio
   async def test_semantic_memory_search():
       """Agent can search their memory via semantic similarity"""
   ```

**Estimated Effort**: 3-4 weeks (1 week for basic integration, 3 weeks for comprehensive collection scoping + testing)

#### Option B: Update Documentation (if decision: NO, use Railway PostgreSQL)

**Tasks**:

1. **Update CLAUDE.md** (Day 1)
   - Remove all ZeroDB references
   - Clarify Railway PostgreSQL as production database
   - Document one-way result buffer flush (not bidirectional sync)

2. **Update architecture diagrams** (Day 1)
   - Replace "ZeroDB" with "Railway PostgreSQL" in all docs

3. **Remove ZeroDB from agent identities spec** (Day 2)
   - Remove `zerodb_collections` field requirement
   - Use PostgreSQL JSON columns for agent memory instead

**Estimated Effort**: 2 days

**DECISION REQUIRED**: User must choose Option A or Option B before Sprint 3.2 can begin.

---

## Phase 4: Monitoring & Production Hardening (Weeks 12-14)

**Goal**: Production-grade monitoring, edge node supervision, and capability validation integration.

### Sprint 4.1: Capability Validation Integration (Week 12)

**Addresses**:
- PRODUCTION_GAPS.md → Gap 5 (Missing Capability Validation)

**Critical Bug**: `CapabilityValidationService` EXISTS but is NEVER CALLED by `TaskAssignmentOrchestrator`.

**Tasks**:

1. **Integrate CapabilityValidationService into orchestrator** (Day 1-3)
   ```python
   # backend/services/task_assignment_orchestrator.py

   from backend.security.capability_validation_service import CapabilityValidationService
   from backend.schemas.task_requirements import TaskRequirements, ValidationResult

   class TaskAssignmentOrchestrator:
       def __init__(self):
           # ... existing init ...
           self.capability_validator = CapabilityValidationService()

       async def assign_task(self, task_id: str):
           task = await self._get_task(task_id)

           # 1. Extract requirements from task payload
           requirements = TaskRequirements(
               task_id=task_id,
               model_name=task.payload.get("model"),
               capabilities=task.required_capabilities.get("capabilities", []),
               resource_limits=task.required_capabilities.get("resource_limits", []),
               data_scope=task.payload.get("data_scope"),
               estimated_duration_minutes=task.payload.get("duration", 10),
               max_concurrent_tasks=1
           )

           # 2. Find available nodes
           available_nodes = await self._get_available_nodes()

           for node in available_nodes:
               # 3. Get node's capability token
               capability_token = await self._get_node_capability_token(node.peer_id)

               # 4. Get node's current usage
               node_usage = await self._get_node_usage(node.peer_id)

               # 5. VALIDATE via CapabilityValidationService
               validation_result: ValidationResult = self.capability_validator.validate(
                   requirements,
                   capability_token,
                   node_usage
               )

               if not validation_result.is_valid:
                   logger.warning(
                       f"Node {node.peer_id} validation failed: "
                       f"{validation_result.error_message}"
                   )
                   continue

               # 6. Node is valid, issue lease
               lease = await self.lease_service.issue_lease(task_id, node.peer_id)

               return lease

           raise NoCapableNodeAvailableError()
   ```

2. **Extend NodeCapability to store capability tokens** (Day 4)
   ```python
   # backend/models/task_lease_models.py

   class NodeCapability(Base):
       # ... existing fields ...

       # NEW: Store capability token
       capability_token_jwt = Column(Text, nullable=True)
       capability_token_issued_at = Column(DateTime(timezone=True), nullable=True)
       capability_token_expires_at = Column(DateTime(timezone=True), nullable=True)
   ```

3. **Create capability token issuance on provisioning** (Day 5-6)
   ```python
   # backend/api/v1/endpoints/wireguard_provisioning.py

   from backend.security.token_service import TokenService
   from backend.models.capability_token import CapabilityToken, TokenLimits

   @router.post("/provision")
   async def provision_peer(request: ProvisioningRequest):
       # ... existing WireGuard provisioning ...

       # NEW: Issue capability token
       token_service = TokenService()

       capability_token = CapabilityToken.create(
           peer_id=node_capability.peer_id,
           capabilities=request.capabilities,
           limits=TokenLimits(
               max_gpu_minutes=1000,  # Example: 1000 GPU minutes/month
               max_concurrent_tasks=5
           ),
           data_scope=["openclaw/*"],  # Default data scope
           expires_in_seconds=90 * 24 * 60 * 60  # 90 days
       )

       jwt_token = token_service.encode_token(capability_token)

       # Store token in NodeCapability
       node_capability.capability_token_jwt = jwt_token
       node_capability.capability_token_issued_at = datetime.now(timezone.utc)
       node_capability.capability_token_expires_at = capability_token.expires_at

       await db.commit()

       return {
           "peer_id": node_capability.peer_id,
           "wireguard_config": wireguard_config,
           "capability_token": jwt_token  # Return to node
       }
   ```

4. **Write integration tests** (Day 7-10)
   ```python
   # tests/integration/test_capability_validation.py

   @pytest.mark.asyncio
   async def test_task_assignment_validates_capabilities():
       """TaskAssignmentOrchestrator calls CapabilityValidationService"""

   @pytest.mark.asyncio
   async def test_node_without_gpu_rejects_gpu_task():
       """Node lacking GPU capability cannot receive GPU task"""

   @pytest.mark.asyncio
   async def test_node_at_concurrent_task_limit_rejects_task():
       """Node at max_concurrent_tasks cannot receive new task"""

   @pytest.mark.asyncio
   async def test_expired_capability_token_rejects_task():
       """Node with expired capability token cannot receive tasks"""
   ```

**Success Criteria**:
- [ ] TaskAssignmentOrchestrator calls CapabilityValidationService for every assignment
- [ ] NodeCapability stores capability tokens
- [ ] WireGuard provisioning issues capability tokens
- [ ] Integration tests pass (validation enforcement)
- [ ] Unauthorized nodes cannot receive tasks

**Risk**: MEDIUM - changes core task assignment flow, requires provisioning updates

---

### Sprint 4.2: Production Monitoring (Week 13-14)

**Addresses**:
- PRODUCTION_GAPS.md → Gap 6 (No Production Monitoring)

**Critical Gap**: Edge nodes have NO monitoring infrastructure. Only gateway monitored.

**Tasks**:

1. **Deploy Prometheus Node Exporter on edge nodes** (Day 1-2)
   ```bash
   # scripts/deploy_node_exporter.sh

   #!/bin/bash
   # Runs on each edge node during provisioning

   # Download Prometheus Node Exporter
   wget https://github.com/prometheus/node_exporter/releases/download/v1.7.0/node_exporter-1.7.0.linux-amd64.tar.gz
   tar xvfz node_exporter-1.7.0.linux-amd64.tar.gz

   # Install as systemd service
   sudo cp node_exporter-1.7.0.linux-amd64/node_exporter /usr/local/bin/

   sudo tee /etc/systemd/system/node_exporter.service > /dev/null <<EOF
   [Unit]
   Description=Prometheus Node Exporter
   After=network.target

   [Service]
   Type=simple
   ExecStart=/usr/local/bin/node_exporter

   [Install]
   WantedBy=multi-user.target
   EOF

   sudo systemctl daemon-reload
   sudo systemctl enable node_exporter
   sudo systemctl start node_exporter
   ```

2. **Extend PrometheusMetricsService for edge nodes** (Day 3-4)
   ```python
   # backend/services/prometheus_metrics_service.py

   class PrometheusMetricsService:
       # ... existing metrics ...

       # NEW: Edge node metrics
       def record_edge_node_heartbeat(self, peer_id: str):
           """Record heartbeat from edge node"""
           self.edge_node_heartbeats.labels(peer_id=peer_id).inc()

       def record_edge_node_task_start(self, peer_id: str, task_id: str):
           """Record task start on edge node"""
           self.edge_node_tasks_active.labels(peer_id=peer_id).inc()

       def record_edge_node_task_complete(self, peer_id: str, task_id: str, duration_seconds: float):
           """Record task completion on edge node"""
           self.edge_node_tasks_active.labels(peer_id=peer_id).dec()
           self.edge_node_task_duration.labels(peer_id=peer_id).observe(duration_seconds)

       def record_edge_node_resource_usage(self, peer_id: str, cpu_percent: float, memory_percent: float):
           """Record resource usage from edge node"""
           self.edge_node_cpu_usage.labels(peer_id=peer_id).set(cpu_percent)
           self.edge_node_memory_usage.labels(peer_id=peer_id).set(memory_percent)
   ```

3. **Create edge node monitoring agent** (Day 5-7)
   ```python
   # backend/agents/edge_node_monitor.py

   import psutil
   import asyncio
   from backend.services.prometheus_metrics_service import get_metrics_service

   class EdgeNodeMonitor:
       """Runs on each edge node to report metrics to gateway"""

       def __init__(self, peer_id: str, gateway_url: str):
           self.peer_id = peer_id
           self.gateway_url = gateway_url
           self.metrics_service = get_metrics_service()

       async def start_monitoring(self):
           """Start background monitoring loop"""
           while True:
               try:
                   # Collect system metrics
                   cpu_percent = psutil.cpu_percent(interval=1)
                   memory = psutil.virtual_memory()

                   # Report to gateway
                   await self._report_metrics({
                       "peer_id": self.peer_id,
                       "cpu_percent": cpu_percent,
                       "memory_percent": memory.percent,
                       "disk_percent": psutil.disk_usage('/').percent,
                       "timestamp": datetime.now(timezone.utc).isoformat()
                   })

                   # Send heartbeat
                   self.metrics_service.record_edge_node_heartbeat(self.peer_id)

               except Exception as e:
                   logger.error(f"Edge node monitoring error: {e}")

               await asyncio.sleep(30)  # Report every 30 seconds

       async def _report_metrics(self, metrics: dict):
           """Send metrics to gateway via HTTP"""
           async with httpx.AsyncClient() as client:
               await client.post(
                   f"{self.gateway_url}/metrics/edge-node",
                   json=metrics,
                   timeout=5.0
               )
   ```

4. **Create gateway endpoint to receive edge metrics** (Day 8)
   ```python
   # backend/api/v1/endpoints/edge_node_metrics.py

   from fastapi import APIRouter, Depends
   from backend.services.prometheus_metrics_service import get_metrics_service

   router = APIRouter(prefix="/metrics", tags=["monitoring"])

   @router.post("/edge-node")
   async def receive_edge_node_metrics(
       metrics: dict,
       metrics_service = Depends(get_metrics_service)
   ):
       """Receive metrics from edge node"""

       peer_id = metrics["peer_id"]

       metrics_service.record_edge_node_resource_usage(
           peer_id,
           metrics["cpu_percent"],
           metrics["memory_percent"]
       )

       return {"status": "received"}
   ```

5. **Create Grafana dashboard** (Day 9-10)
   ```json
   // dashboards/edge_node_monitoring.json
   {
     "dashboard": {
       "title": "OpenClaw Edge Node Monitoring",
       "panels": [
         {
           "title": "Edge Node Heartbeats",
           "targets": [
             {
               "expr": "rate(edge_node_heartbeats_total[5m])"
             }
           ]
         },
         {
           "title": "Active Tasks by Node",
           "targets": [
             {
               "expr": "edge_node_tasks_active"
             }
           ]
         },
         {
           "title": "CPU Usage by Node",
           "targets": [
             {
               "expr": "edge_node_cpu_usage"
             }
           ]
         }
       ]
     }
   }
   ```

**Success Criteria**:
- [ ] Node Exporter running on all edge nodes
- [ ] EdgeNodeMonitor reports metrics every 30s
- [ ] PrometheusMetricsService exposes edge node metrics at `/metrics`
- [ ] Grafana dashboard visualizes edge node health
- [ ] Alerts configured for node downtime/high resource usage

**Risk**: MEDIUM - requires coordination with edge node deployment, new service integration

---

## Phase 5: Testing & Documentation (Weeks 15-16)

**Goal**: Comprehensive testing, documentation updates, and production deployment prep.

### Sprint 5.1: Integration Testing & Load Testing (Week 15)

**Tasks**:

1. **End-to-end agent identity flow tests** (Day 1-3)
   ```python
   # tests/e2e/test_agent_identity_flow.py

   @pytest.mark.e2e
   async def test_complete_agent_lifecycle():
       """
       1. Create agent identity (Atlas Redwood)
       2. Provision WireGuard peer with capability token
       3. Link agent to hardware node
       4. Assign SEO task requiring CMS read permission
       5. Agent executes task
       6. Task completes successfully
       """

   @pytest.mark.e2e
   async def test_permission_denied_flow():
       """
       1. Create agent identity (Vega Martinez - Sales)
       2. Attempt to publish blog post (requires CMS publish permission)
       3. Verify permission denied
       4. Request approval from Helios
       5. Helios approves
       6. Publish succeeds
       """
   ```

2. **Load testing task assignment** (Day 4-5)
   ```python
   # tests/load/test_task_assignment_load.py

   import locust

   class TaskAssignmentUser(locust.HttpUser):
       @locust.task
       def create_and_assign_task(self):
           # Create 100 tasks/second
           task_payload = {
               "task_type": "seo_analysis",
               "required_agent_id": "atlas-redwood-uuid",
               "required_capabilities": {"gpu_available": False}
           }

           self.client.post("/tasks", json=task_payload)

   # Target: 1000 tasks/second, <500ms p99 latency
   ```

3. **Database migration smoke tests** (Day 6-7)
   ```bash
   # tests/smoke/test_migrations.sh

   # Test upgrade path
   alembic upgrade head
   python -m pytest tests/ -m "smoke"

   # Test downgrade path
   alembic downgrade -1
   alembic upgrade head
   ```

4. **Security audit** (Day 8-10)
   - [ ] No secrets in environment variables (use AWS Secrets Manager)
   - [ ] All API credentials encrypted with Fernet
   - [ ] Capability tokens expire after 90 days
   - [ ] Tool permissions enforced on all endpoints
   - [ ] Approval workflows gate publish/revenue actions
   - [ ] SQL injection prevention (parameterized queries)
   - [ ] XSS prevention (output encoding)

**Success Criteria**:
- [ ] All 750+ tests pass (690 existing + 60 new)
- [ ] Load tests achieve 1000 tasks/sec with <500ms p99 latency
- [ ] Migration smoke tests pass
- [ ] Security audit finds zero critical vulnerabilities

**Risk**: LOW - validation phase, no new features

---

### Sprint 5.2: Documentation & Deployment (Week 16)

**Tasks**:

1. **Update CLAUDE.md** (Day 1-2)
   - Document new AgentIdentity model
   - Document tool permission system
   - Document approval workflow
   - Document token rotation schedule
   - Update database schema section
   - Clarify ZeroDB status (if integrated) or remove references (if not)

2. **Create runbook** (Day 3-4)
   ```markdown
   # docs/PRODUCTION_RUNBOOK.md

   ## Deployment Checklist
   - [ ] Run database migrations: `alembic upgrade head`
   - [ ] Seed agent identities: `python scripts/seed_agent_identities.py`
   - [ ] Verify WireGuard hub is running: `wg show wg0`
   - [ ] Start Gateway: `npm run start` in openclaw-gateway/
   - [ ] Start Backend: `uvicorn backend.main:app --host 0.0.0.0 --port 8000`
   - [ ] Verify Prometheus scraping: `curl http://localhost:8000/metrics`
   - [ ] Verify edge node heartbeats in Grafana

   ## Common Issues
   - **Edge node not receiving tasks**: Check capability token expiration
   - **Permission denied errors**: Verify agent has tool permission
   - **Approval requests stuck**: Check Helios orchestrator is active
   ```

3. **Create API documentation** (Day 5-6)
   ```python
   # Auto-generated via FastAPI
   # Add OpenAPI descriptions to all endpoints

   @router.post(
       "/agent-identities",
       response_model=AgentIdentityResponse,
       summary="Create new agent identity",
       description="""
       Create a new agent identity with specified role and tool permissions.

       **Required fields**:
       - name: Unique agent name (e.g., "Atlas Redwood")
       - email: Unique email (@ainative.studio domain)
       - role: Agent role (search-discoverability, content-brand, etc.)

       **Optional fields**:
       - tool_permissions: List of tools agent can access
       - is_orchestrator: Whether agent can approve requests
       """
   )
   async def create_agent_identity(...):
       ...
   ```

4. **Production deployment** (Day 7-10)
   ```bash
   # Deploy to Railway
   railway up

   # Run migrations
   railway run alembic upgrade head

   # Seed agent identities
   railway run python scripts/seed_agent_identities.py

   # Verify deployment
   curl https://openclaw-backend-production.up.railway.app/openclaw/status
   curl https://openclaw-backend-production.up.railway.app/swarm/health
   ```

**Success Criteria**:
- [ ] CLAUDE.md fully updated
- [ ] Production runbook complete
- [ ] API documentation generated
- [ ] Production deployment successful
- [ ] All health checks passing
- [ ] Zero critical alerts in first 24 hours

**Risk**: LOW - documentation and deployment validation

---

## Critical Decision Points

### Decision 1: ZeroDB Integration (BLOCKS Sprint 3.2)

**Question**: Should we integrate ZeroDB for agent memory/vector search, or use Railway PostgreSQL + pgvector?

**Option A: ZeroDB**
- **Pros**:
  - Matches agent identities spec v1.0
  - Built-in vector search
  - Event stream for audit logs
  - Collection-based isolation
- **Cons**:
  - 3-4 week integration effort
  - New dependency to maintain
  - Additional cost
  - No existing code to build on

**Option B: Railway PostgreSQL + pgvector**
- **Pros**:
  - Already deployed and working
  - pgvector extension provides vector search
  - JSONB columns can store agent memory
  - Zero new dependencies
- **Cons**:
  - Doesn't match spec exactly
  - Requires documentation updates
  - May need future migration if ZeroDB adopted later

**Recommendation**: **Option B (Railway + pgvector)** to unblock timeline. ZeroDB can be added later if needed.

**Impact on Timeline**:
- Option A: +3-4 weeks (Sprint 3.2 becomes 4 weeks)
- Option B: -1 week (Sprint 3.2 becomes 2 days of doc updates)

---

### Decision 2: Database Schema Migration Strategy (BLOCKS Sprint 1.1)

**Question**: How should we handle the three incompatible task model files?

**Option A: Unified Schema with Data Migration**
- Create new `unified_task.py` with best-of-all-three
- Write data migration script (Integer PK → UUID PK)
- Update all 30+ service imports
- **Effort**: 2 weeks

**Option B: Soft Deprecation**
- Keep all three files
- New code uses `task_lease_models.py` (most complete)
- Old code gradually migrated
- **Effort**: 4 weeks (spread over multiple sprints)

**Recommendation**: **Option A (Unified Schema)** - rip the band-aid off early. Technical debt compounds.

---

### Decision 3: Agent Identity Linking Strategy (Sprint 1.2)

**Question**: How to link AgentSwarmInstance (identity) to NodeCapability (hardware)?

**Option A: Bidirectional Foreign Keys**
- AgentSwarmInstance.peer_id → NodeCapability
- NodeCapability.agent_id → AgentSwarmInstance
- **Pros**: Can navigate in either direction
- **Cons**: Risk of orphaned records if not careful

**Option B: Join Table**
- New `agent_node_links` table
- Supports many-to-many (one agent, multiple nodes)
- **Pros**: More flexible, cleaner separation
- **Cons**: Extra join in queries, overkill for 1:1 relationship

**Recommendation**: **Option A (Bidirectional FKs)** - simpler, matches current 1:1 agent-to-node model.

---

## Risk Mitigation

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Database migration data loss | Medium | CRITICAL | Run dry-run migrations on staging, automated backup before prod migration |
| Task assignment regression | Medium | HIGH | Comprehensive integration tests, gradual rollout with feature flag |
| Token rotation breaks existing nodes | Low | HIGH | Grace period on token expiration (5 min), gradual rotation schedule |
| Edge node monitoring overload | Low | MEDIUM | Rate limiting on metrics reporting (30s interval), aggregation on gateway |
| ZeroDB integration timeline slippage | High | MEDIUM | Make it optional (Decision 1), use Railway PostgreSQL as fallback |
| Approval workflow deadlock | Low | HIGH | Timeout on approval requests (24h), fallback to auto-approve for low-risk actions |

---

## Success Metrics

### Phase 1 (Foundation)
- [ ] Zero database schema conflicts
- [ ] 100% agent-to-hardware linkage (no orphaned agents or nodes)
- [ ] Task assignment validates BOTH hardware AND identity
- [ ] All 690+ tests pass

### Phase 2 (Agent Identity)
- [ ] 7 production agents seeded with correct permissions
- [ ] Tool permission checks on all endpoints
- [ ] Approval workflow handles 100% of publish/revenue actions
- [ ] Zero unauthorized tool access in audit logs

### Phase 3 (Security & Data)
- [ ] 90-day token rotation automated
- [ ] API credentials encrypted at rest
- [ ] ZeroDB integrated (if Option A) or docs updated (if Option B)

### Phase 4 (Monitoring)
- [ ] CapabilityValidationService called on 100% of task assignments
- [ ] Edge node metrics visible in Grafana
- [ ] Prometheus scraping <1s latency
- [ ] Zero unauthorized task assignments

### Phase 5 (Testing & Deployment)
- [ ] 750+ tests pass (100% success rate)
- [ ] Load tests: 1000 tasks/sec @ <500ms p99
- [ ] Production deployment zero-downtime
- [ ] Zero critical alerts in first 7 days

---

## Estimated Resource Requirements

### Engineering Time

| Phase | Backend Dev | Frontend Dev | QA/Testing | DevOps | Total Person-Weeks |
|-------|-------------|--------------|------------|--------|---------------------|
| Phase 1 | 6 weeks | 0 | 2 weeks | 0 | 8 weeks |
| Phase 2 | 6 weeks | 2 weeks | 2 weeks | 0 | 10 weeks |
| Phase 3 | 4 weeks (Option B) or 8 weeks (Option A) | 0 | 1 week | 1 week | 6-10 weeks |
| Phase 4 | 4 weeks | 1 week | 1 week | 2 weeks | 8 weeks |
| Phase 5 | 2 weeks | 0 | 2 weeks | 1 week | 5 weeks |
| **TOTAL** | **22-26 weeks** | **3 weeks** | **8 weeks** | **4 weeks** | **37-41 weeks** |

**Note**: With 2 full-time backend engineers working in parallel, total calendar time can be reduced to **14-16 weeks** (3.5-4 months).

### Infrastructure Costs (Incremental)

| Component | Monthly Cost | Notes |
|-----------|-------------|-------|
| Railway PostgreSQL (existing) | $10 | Already deployed |
| ZeroDB (if Option A) | $50-200 | Depends on usage tier |
| Prometheus + Grafana (self-hosted) | $0 | Using open-source |
| Edge Node Monitoring (bandwidth) | $20 | Metrics reporting every 30s |
| Secrets Manager (AWS) | $5 | For API credentials |
| **TOTAL (Option A)** | **$85-235** | With ZeroDB |
| **TOTAL (Option B)** | **$35** | Without ZeroDB |

---

## Deployment Strategy

### Week 14: Pre-Deployment Checklist

1. **Staging Environment Validation** (Day 1-3)
   - [ ] Deploy all changes to staging
   - [ ] Run full test suite (750+ tests)
   - [ ] Run load tests (1000 tasks/sec)
   - [ ] Manual QA of critical flows (agent provisioning, task assignment, approval workflow)

2. **Database Backup** (Day 4)
   - [ ] Full backup of Railway PostgreSQL production database
   - [ ] Verify backup can be restored to staging
   - [ ] Document rollback procedure

3. **Migration Dry Run** (Day 5)
   - [ ] Run Alembic migrations on staging
   - [ ] Verify data integrity post-migration
   - [ ] Measure migration time (estimate for production downtime)

4. **Rollback Plan** (Day 6-7)
   ```bash
   # If deployment fails, rollback steps:
   1. Revert database: pg_restore production_backup.dump
   2. Revert git: git revert <commit-hash>
   3. Redeploy previous version: railway up
   4. Verify health checks: curl /openclaw/status
   ```

### Week 16: Production Deployment

**Maintenance Window**: Sunday 2:00 AM - 6:00 AM UTC (estimated 2-hour downtime)

1. **T-60min: Pre-deployment** (Day 1, 1:00 AM UTC)
   - [ ] Notify users of maintenance window
   - [ ] Pause agent task assignment (set `MAINTENANCE_MODE=true`)
   - [ ] Wait for in-flight tasks to complete (max 15 min)
   - [ ] Take final database backup

2. **T-0min: Deployment begins** (2:00 AM UTC)
   ```bash
   # Deploy new backend code
   railway up

   # Run database migrations
   railway run alembic upgrade head

   # Seed agent identities
   railway run python scripts/seed_agent_identities.py

   # Populate existing agents with peer_id linkage
   railway run python scripts/link_agents_to_nodes.py

   # Issue capability tokens to existing nodes
   railway run python scripts/issue_capability_tokens.py
   ```

3. **T+30min: Verification** (2:30 AM UTC)
   - [ ] Health check: `curl /openclaw/status` → {"status": "operational"}
   - [ ] Database check: `SELECT COUNT(*) FROM agent_identities` → 7 agents
   - [ ] Metrics check: `curl /metrics` → Prometheus data
   - [ ] Edge node check: `curl /swarm/health` → All nodes healthy

4. **T+60min: Resume operations** (3:00 AM UTC)
   - [ ] Set `MAINTENANCE_MODE=false`
   - [ ] Resume task assignment
   - [ ] Monitor for 1 hour (3:00 AM - 4:00 AM)
   - [ ] Check error rate: <0.1% expected

5. **T+120min: Post-deployment** (4:00 AM UTC)
   - [ ] Send all-clear notification to users
   - [ ] Update status page: "All systems operational"
   - [ ] Schedule 24-hour monitoring review

---

## Appendix A: Example Agent Identity Records

```python
# Production agent identities (seed data)

ATLAS_REDWOOD = {
    "id": "550e8400-e29b-41d4-a716-446655440001",
    "name": "Atlas Redwood",
    "email": "atlas.redwood@ainative.studio",
    "role": AgentRole.SEARCH_DISCOVERABILITY,
    "tool_permissions": [ToolType.CMS, ToolType.ANALYTICS, ToolType.AB_TESTING],
    "zerodb_collections": ["seo/keywords", "seo/rankings", "seo/backlinks", "seo/performance"],
    "is_orchestrator": False,
    "can_assign_tasks": False,
    "token_rotation_days": 90
}

HELIOS_MERCER = {
    "id": "550e8400-e29b-41d4-a716-446655440007",
    "name": "Helios Mercer",
    "email": "helios.mercer@ainative.studio",
    "role": AgentRole.ORCHESTRATION,
    "tool_permissions": list(ToolType),  # All tools
    "zerodb_collections": ["*"],  # All collections
    "is_orchestrator": True,
    "can_assign_tasks": True,
    "can_approve_publish": True,
    "can_approve_revenue": True,
    "token_rotation_days": 90
}
```

---

## Appendix B: Capability Token Example

```json
{
  "jti": "4Kx9Nz2Lp8QwRv3",
  "peer_id": "12D3KooWABCDEF...",
  "capabilities": [
    {"capability_id": "gpu:nvidia-a100", "required": true},
    {"capability_id": "cpu:16-cores", "required": false},
    {"capability_id": "memory:32gb", "required": true}
  ],
  "limits": {
    "max_gpu_minutes": 1000,
    "max_concurrent_tasks": 5
  },
  "data_scope": ["openclaw/*", "ainative/*"],
  "expires_at": 1735689600,
  "parent_jti": null
}
```

---

## Appendix C: Tool Permission Matrix

| Agent Role | CMS | Social | Analytics | CRM | Email | A/B | Events | Payments | DocuSign | Calendar |
|------------|-----|--------|-----------|-----|-------|-----|--------|----------|----------|----------|
| Atlas Redwood (SEO) | R | - | R | - | - | RW | - | - | - | - |
| Lyra Chen-Sato (Content) | RW | RW | R | - | R | - | - | - | - | - |
| Sage Okafor (Analytics) | R | R | RW | R | R | RW | R | - | - | - |
| Vega Martinez (Sales) | R | - | R | RW | RW | - | - | R | RW | RW |
| Nova Sinclair (Growth) | RW | RW | RW | RW | RW | RW | - | - | - | - |
| Luma Harrington (Events) | R | RW | R | R | RW | - | RW | R | R | RW |
| Helios Mercer (Orchestrator) | RWD | RWD | RWD | RWD | RWD | RWD | RWD | RWD | RWD | RWD |

**Legend**: R=Read, W=Write, D=Delete, P=Publish

---

## Next Steps

**IMMEDIATE ACTION REQUIRED**:

1. **User must decide on ZeroDB integration** (Decision 1)
   - Option A: ZeroDB (3-4 weeks) → Proceed to Sprint 3.2 with full integration
   - Option B: Railway PostgreSQL (2 days) → Update docs, skip ZeroDB

2. **Begin Phase 1 Sprint 1.1** (Database Schema Unification)
   - Audit service dependencies
   - Design unified schema
   - Create Alembic migration

**TIMELINE CONTINGENT ON DECISION 1**:
- If ZeroDB (Option A): 16 weeks total
- If Railway (Option B): 14 weeks total

---

**Document Status**: DRAFT - Awaiting ZeroDB Decision
**Owner**: OpenClaw Engineering Team
**Last Updated**: 2026-03-02
