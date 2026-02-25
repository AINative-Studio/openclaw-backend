# P2P and Security Features Integration Plan

**Epic**: Production Integration of P2P Communication and Security Layers
**Status**: Planning Phase
**Created**: 2026-02-24
**Priority**: High

## Executive Summary

The OpenClaw backend contains comprehensive P2P communication and security infrastructure (Epic E5 & Epic E7) that is currently dormant. All components are fully tested with 690+ passing tests, but they are not wired into the production API endpoints and services.

This integration plan provides a phased approach to activate these features in production with minimal risk and maximum observability.

---

## Current State Analysis

### P2P Features (Epic E5) - Status: DORMANT

**What Exists**:
- `backend/p2p/libp2p_identity.py` - Ed25519 keypair generation and management
- `backend/p2p/libp2p_bootstrap.py` - Kademlia DHT bootstrap client
- `backend/p2p/protocols/task_request.py` - Task assignment protocol
- `backend/p2p/protocols/task_result.py` - Result submission protocol
- `backend/p2p/protocols/task_progress.py` - Progress heartbeat protocol
- `backend/p2p/protocols/task_failure.py` - Failure reporting protocol

**Where They're Referenced**:
- `backend/services/task_assignment_orchestrator.py:110` - Accepts `libp2p_client` parameter
- `backend/services/task_assignment_orchestrator.py:196` - Calls `libp2p_client.send_task_request()`
- **BUT**: No imports, no instantiation, no API endpoint wiring

**Test Coverage**: 14 test files, all passing

---

### Security Features (Epic E7) - Status: DORMANT

**What Exists**:
- `backend/security/message_signing_service.py` - Ed25519 message signing
- `backend/security/message_verification_service.py` - Signature verification with timestamp validation
- `backend/security/token_service.py` - JWT capability token issuance
- `backend/security/peer_key_store.py` - In-memory Ed25519 public key storage
- `backend/services/capability_validation_service.py` - Resource limit + capability validation
- `backend/services/token_rotation_service.py` - Token renewal with grace periods
- `backend/services/security_audit_logger.py` - File/database audit logging

**Where They Should Be Used**:
- Task assignment: validate capabilities before leasing tasks
- Task result submission: verify Ed25519 message signatures
- P2P protocols: sign/verify all messages
- API authentication: enforce capability tokens

**Test Coverage**: 8 test files, all passing

---

## Integration Challenges

### 1. Missing Model Files
**Issue**: `backend/models/task_request_message.py` doesn't exist
**Impact**: TaskRequestProtocol imports fail
**Solution**: Create Pydantic models for TaskRequestMessage and TaskAckMessage

### 2. Orchestrator Expects Generic Client
**Issue**: TaskAssignmentOrchestrator expects `libp2p_client` with `send_task_request()` method
**Reality**: P2P protocols are separate classes (TaskRequestProtocol, TaskResultProtocol)
**Solution**: Create LibP2PClient wrapper that aggregates all protocols

### 3. No libp2p Host Setup
**Issue**: P2P protocols require a libp2p host instance (from py-libp2p)
**Reality**: No libp2p host initialization in startup
**Solution**: Add libp2p host setup to `backend/main.py` startup event

### 4. Three Conflicting ORM Models
**Issue**: `task_models.py`, `task_queue.py`, and `task_lease_models.py` define overlapping schemas
**Impact**: Cannot use all three simultaneously
**Solution**: Consolidate to single unified model file (separate integration)

### 5. In-Memory Stores Not Persistent
**Issue**: LeaseValidationService and PeerKeyStore use Python dicts
**Impact**: All state lost on restart
**Solution**: Back by PostgreSQL tables

---

## Phase 1: Foundation (Week 1)

### Story 1.1: Create Missing P2P Models
**File**: `backend/models/task_request_message.py`

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime

class TaskRequestMessage(BaseModel):
    """Task assignment request from coordinator to node"""
    task_id: str = Field(..., description="Unique task identifier")
    lease_token: str = Field(..., description="JWT lease token")
    task_payload: Dict[str, Any] = Field(..., description="Task execution data")
    coordinator_peer_id: str = Field(..., description="Coordinator's peer ID")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    signature: Optional[str] = Field(None, description="Ed25519 signature")

class TaskAckMessage(BaseModel):
    """Acknowledgment from node to coordinator"""
    task_id: str
    accepted: bool
    reason: Optional[str] = None
    node_peer_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
```

**Acceptance Criteria**:
- [ ] Models pass validation tests
- [ ] TaskRequestProtocol imports succeed
- [ ] Backward compatible with existing tests

---

### Story 1.2: Create LibP2PClient Wrapper
**File**: `backend/clients/libp2p_client.py`

**Purpose**: Aggregate all P2P protocols into single client interface expected by orchestrator

```python
class LibP2PClient:
    """Unified libp2p client for all P2P protocols"""

    def __init__(self, host, identity: LibP2PIdentity):
        self.host = host
        self.identity = identity
        self.task_request_protocol = TaskRequestProtocol(host)
        self.task_result_protocol = TaskResultProtocol(host)
        self.task_progress_service = TaskProgressService(host)
        self.task_failure_handler = TaskFailureHandler(host)

    async def send_task_request(
        self, peer_id: str, task_id: str, lease_token: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Send task request to node (called by orchestrator)"""
        message = TaskRequestMessage(
            task_id=task_id,
            lease_token=lease_token,
            task_payload=payload,
            coordinator_peer_id=str(self.identity.peer_id)
        )
        return await self.task_request_protocol.send_task_request(
            node_peer_id=peer_id,
            message=message,
            coordinator_key=self.identity.private_key
        )
```

**Acceptance Criteria**:
- [ ] Implements all methods expected by TaskAssignmentOrchestrator
- [ ] Aggregates TaskRequestProtocol, TaskResultProtocol, TaskProgressService, TaskFailureHandler
- [ ] Unit tests with mocked protocols pass

---

### Story 1.3: Initialize libp2p Host on Startup
**File**: `backend/main.py`

**Changes**:
1. Add libp2p host initialization to startup event
2. Create global libp2p_client instance
3. Wire into dependency injection

```python
# Add to backend/main.py startup event
from backend.p2p.libp2p_identity import LibP2PIdentity
from backend.p2p.libp2p_bootstrap import LibP2PBootstrapClient
from backend.clients.libp2p_client import LibP2PClient

libp2p_client: Optional[LibP2PClient] = None

@app.on_event("startup")
async def startup():
    # ... existing startup code ...

    # Initialize libp2p for P2P task coordination
    try:
        identity = LibP2PIdentity.generate()
        bootstrap_client = LibP2PBootstrapClient(identity)
        await bootstrap_client.connect_to_bootstrap_node(
            bootstrap_addr=os.getenv("BOOTSTRAP_NODE_ADDR", "/ip4/127.0.0.1/tcp/4001")
        )

        global libp2p_client
        libp2p_client = LibP2PClient(
            host=bootstrap_client.host,
            identity=identity
        )
        logger.info(f"✓ libp2p initialized with peer ID: {identity.peer_id}")
    except Exception as e:
        logger.warning(f"libp2p initialization failed (non-critical): {e}")
```

**Acceptance Criteria**:
- [ ] Backend starts successfully with libp2p enabled
- [ ] Backend starts successfully if bootstrap node unavailable (graceful degradation)
- [ ] libp2p_client available via dependency injection

---

## Phase 2: Security Integration (Week 2)

### Story 2.1: Wire Capability Validation into Task Assignment
**File**: `backend/services/task_assignment_orchestrator.py`

**Changes**:
```python
from backend.services.capability_validation_service import CapabilityValidationService
from backend.models.task_requirements import TaskRequirements, CapabilityToken

class TaskAssignmentOrchestrator:
    def __init__(
        self,
        db_session: Session,
        libp2p_client,
        dbos_service,
        capability_validator: CapabilityValidationService,  # NEW
        lease_duration_minutes: int = 10
    ):
        self.capability_validator = capability_validator
        # ... existing code ...

    async def assign_task(self, task_id: str, ...) -> AssignmentResult:
        # ... existing validation ...

        # NEW: Validate node capabilities before assignment
        node_token = CapabilityToken(
            peer_id=matched_node["peer_id"],
            capabilities=matched_node.get("capabilities", []),
            limits=matched_node.get("limits", {}),
            data_scopes=matched_node.get("data_scopes", [])
        )

        validation_result = self.capability_validator.validate(
            task_requirements=required_capabilities,
            capability_token=node_token,
            node_usage=matched_node.get("current_usage", {})
        )

        if not validation_result.is_valid:
            raise CapabilityValidationError(
                f"Node {matched_node['peer_id']} failed capability validation: "
                f"{validation_result.error_message}"
            )

        # ... continue with existing lease issuance ...
```

**Acceptance Criteria**:
- [ ] Task assignment rejects nodes without required capabilities
- [ ] Task assignment enforces resource limits (GPU minutes, concurrent tasks)
- [ ] Validation errors logged to security audit log
- [ ] Integration tests pass

---

### Story 2.2: Add Message Signing to P2P Protocols
**Files**: All files in `backend/p2p/protocols/`

**Changes**: Integrate MessageSigningService into protocol handlers

```python
# In TaskRequestProtocol, TaskResultProtocol, etc.
from backend.security.message_signing_service import MessageSigningService

class TaskRequestProtocol:
    def __init__(self, host, identity: LibP2PIdentity):
        self.host = host
        self.signing_service = MessageSigningService(identity)  # NEW

    async def send_task_request(self, node_peer_id: str, message: TaskRequestMessage, ...):
        # NEW: Sign the message before sending
        envelope = self.signing_service.sign_message(message.dict())

        # Send envelope instead of raw message
        stream = await self.host.new_stream(node_peer_id, [self.PROTOCOL_ID])
        await stream.write(envelope.json().encode())
        # ... rest of protocol ...
```

**Acceptance Criteria**:
- [ ] All P2P messages signed with Ed25519
- [ ] Signature verification on receiving end
- [ ] Replay attack prevention (timestamp validation)
- [ ] Protocol tests updated with signing

---

### Story 2.3: Add Security Audit Logging to Critical Operations
**Files**: `backend/api/v1/endpoints/*.py`, `backend/services/*.py`

**Changes**: Log all security-relevant events

```python
from backend.services.security_audit_logger import SecurityAuditLogger, AuditEvent
from backend.models.audit_event import AuditEventType, AuditEventResult

# In task assignment endpoint
audit_logger = SecurityAuditLogger(storage=DatabaseAuditLogStorage(db))

# Log successful task assignment
audit_logger.log_event(AuditEvent(
    event_type=AuditEventType.AUTHORIZATION_SUCCESS,
    peer_id=assigned_peer_id,
    action="task_assignment",
    resource=f"task:{task_id}",
    result=AuditEventResult.SUCCESS,
    reason="Node capabilities validated",
    metadata={"lease_token": lease_token, "duration_minutes": duration}
))

# Log failed capability validation
audit_logger.log_event(AuditEvent(
    event_type=AuditEventType.AUTHORIZATION_FAILURE,
    peer_id=node_peer_id,
    action="task_assignment",
    resource=f"task:{task_id}",
    result=AuditEventResult.DENIED,
    reason=validation_result.error_message,
    metadata={"missing_capabilities": validation_result.missing_capabilities}
))
```

**Acceptance Criteria**:
- [ ] All task assignments logged
- [ ] All capability validation failures logged
- [ ] All message signature failures logged
- [ ] Audit log queryable via API endpoint

---

## Phase 3: P2P Protocol Activation (Week 3)

### Story 3.1: Wire TaskRequestProtocol into Orchestrator
**File**: `backend/services/task_assignment_orchestrator.py`

**Current State**: Line 196 calls `self.libp2p_client.send_task_request()` but libp2p_client is None

**Changes**:
1. Add libp2p_client to orchestrator initialization
2. Add fallback when libp2p unavailable (log warning, continue with DB-only assignment)

```python
# Step 6: Send TaskRequest via libp2p (with graceful fallback)
if self.libp2p_client:
    try:
        response = await self.libp2p_client.send_task_request(
            peer_id=peer_id,
            task_id=task_id,
            lease_token=lease_token,
            payload=task.payload
        )
        logger.info(f"Task request sent to {peer_id}: {response}")
    except Exception as e:
        logger.warning(f"libp2p task request failed (non-critical): {e}")
        # Continue - task is already assigned in DB, node will poll
else:
    logger.warning("libp2p_client not available, node must poll for task")
```

**Acceptance Criteria**:
- [ ] Task assignment works with libp2p enabled
- [ ] Task assignment works with libp2p disabled (graceful degradation)
- [ ] Integration tests pass with both modes

---

### Story 3.2: Create Task Result Submission API Endpoint
**File**: `backend/api/v1/endpoints/task_results.py` (NEW)

**Purpose**: HTTP endpoint for nodes to submit task results (alternative to P2P)

```python
from fastapi import APIRouter, Depends, HTTPException
from backend.schemas.task_schemas import TaskResult, TaskResultResponse
from backend.p2p.protocols.task_result import TaskResultProtocol
from backend.services.lease_validation_service import LeaseValidationService

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/{task_id}/result", response_model=TaskResultResponse)
async def submit_task_result(
    task_id: str,
    result: TaskResult,
    db: Session = Depends(get_db),
    verification_service: MessageVerificationService = Depends(get_verification_service)
):
    """Submit task result via HTTP (alternative to P2P)"""

    # Verify message signature
    if not verification_service.verify_message(
        sender_peer_id=result.peer_id,
        payload=result.dict(exclude={"signature"}),
        signature=result.signature,
        timestamp=result.timestamp
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Validate lease
    lease_validator = LeaseValidationService(db)
    validation = lease_validator.validate_lease(
        task_id=task_id,
        peer_id=result.peer_id,
        lease_token=result.lease_token
    )

    if not validation.is_valid:
        raise HTTPException(status_code=403, detail=validation.error_message)

    # Submit to DBOS
    # ... existing result submission logic ...

    return TaskResultResponse(status="accepted", task_id=task_id)
```

**Acceptance Criteria**:
- [ ] HTTP endpoint accepts task results
- [ ] Signature verification required
- [ ] Lease validation required
- [ ] Results submitted to DBOS
- [ ] API documentation generated

---

### Story 3.3: Add P2P Task Result Listener
**File**: `backend/services/task_result_listener.py` (NEW)

**Purpose**: Background service to receive task results via P2P

```python
class TaskResultListener:
    """Background service to listen for P2P task results"""

    def __init__(self, libp2p_client: LibP2PClient, db_session: Session):
        self.libp2p_client = libp2p_client
        self.db_session = db_session
        self.running = False

    async def start(self):
        """Start listening for task results"""
        self.running = True

        # Register handler with TaskResultProtocol
        self.libp2p_client.task_result_protocol.register_handler(
            self._handle_task_result
        )

        logger.info("Task result listener started")

    async def _handle_task_result(self, result: TaskResult) -> Dict[str, Any]:
        """Handle incoming task result from P2P"""
        # Validate, verify signature, submit to DBOS
        # ... same logic as HTTP endpoint ...
        return {"status": "accepted"}
```

**Integration**: Add to `backend/main.py` startup

```python
@app.on_event("startup")
async def startup():
    # ... existing startup ...

    if libp2p_client:
        result_listener = TaskResultListener(libp2p_client, SessionLocal())
        await result_listener.start()
```

**Acceptance Criteria**:
- [ ] Listener starts on backend startup
- [ ] Receives P2P task results
- [ ] Validates and submits to DBOS
- [ ] Gracefully degrades if libp2p unavailable

---

## Phase 4: Production Hardening (Week 4)

### Story 4.1: Persist PeerKeyStore to Database
**File**: `backend/models/peer_public_keys.py` (NEW)

**Current Issue**: PeerKeyStore is in-memory, keys lost on restart

**Solution**: Add PostgreSQL backing

```python
# SQLAlchemy model
class PeerPublicKey(Base):
    __tablename__ = "peer_public_keys"

    peer_id = Column(String(128), primary_key=True)
    public_key_bytes = Column(LargeBinary, nullable=False)  # 32 bytes Ed25519
    first_seen_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=False)
    trust_score = Column(Integer, default=100)  # Decrease on verification failures
```

**Update**: `backend/security/peer_key_store.py`

```python
class PeerKeyStore:
    def __init__(self, db_session: Optional[Session] = None):
        self._cache: Dict[str, ed25519.Ed25519PublicKey] = {}
        self.db_session = db_session  # NEW

    def store_public_key(self, peer_id: str, public_key: ed25519.Ed25519PublicKey):
        # Store in cache
        self._cache[peer_id] = public_key

        # NEW: Persist to database
        if self.db_session:
            key_record = PeerPublicKey(
                peer_id=peer_id,
                public_key_bytes=public_key.public_bytes_raw(),
                first_seen_at=datetime.now(timezone.utc),
                last_used_at=datetime.now(timezone.utc)
            )
            self.db_session.merge(key_record)
            self.db_session.commit()

    def get_public_key(self, peer_id: str) -> Optional[ed25519.Ed25519PublicKey]:
        # Check cache first
        if peer_id in self._cache:
            return self._cache[peer_id]

        # NEW: Load from database
        if self.db_session:
            record = self.db_session.query(PeerPublicKey).filter_by(peer_id=peer_id).first()
            if record:
                key = ed25519.Ed25519PublicKey.from_public_bytes(record.public_key_bytes)
                self._cache[peer_id] = key  # Populate cache
                return key

        return None
```

**Acceptance Criteria**:
- [ ] Peer keys survive backend restart
- [ ] Cache still used for performance
- [ ] Migration script created
- [ ] Tests updated

---

### Story 4.2: Add P2P Metrics to Prometheus
**File**: `backend/services/prometheus_metrics_service.py`

**New Metrics**:
```python
# Add to PrometheusMetricsService
def record_p2p_message_sent(self, protocol: str, peer_id: str):
    """Increment p2p_messages_sent counter"""
    pass

def record_p2p_message_received(self, protocol: str, peer_id: str):
    """Increment p2p_messages_received counter"""
    pass

def record_p2p_message_failed(self, protocol: str, peer_id: str, error_type: str):
    """Increment p2p_message_failures counter"""
    pass

def record_signature_verification(self, peer_id: str, success: bool):
    """Track signature verification success/failure"""
    pass

def record_capability_validation(self, peer_id: str, success: bool):
    """Track capability validation results"""
    pass
```

**Integration**: Wire into P2P protocols

```python
# In TaskRequestProtocol
async def send_task_request(self, ...):
    try:
        # ... send message ...
        metrics_service.record_p2p_message_sent("task_request", node_peer_id)
    except Exception as e:
        metrics_service.record_p2p_message_failed("task_request", node_peer_id, type(e).__name__)
        raise
```

**Acceptance Criteria**:
- [ ] All P2P messages counted
- [ ] Signature verification success rate tracked
- [ ] Capability validation success rate tracked
- [ ] Metrics exposed at `/metrics` endpoint

---

### Story 4.3: Add Security Audit Log Query Endpoint
**File**: `backend/api/v1/endpoints/audit_logs.py` (NEW)

**Purpose**: Query security audit logs via REST API

```python
@router.get("/audit/logs", response_model=List[AuditLogEntry])
async def query_audit_logs(
    peer_id: Optional[str] = None,
    event_type: Optional[AuditEventType] = None,
    result: Optional[AuditEventResult] = None,
    since: Optional[datetime] = None,
    until: Optional[datetime] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Query security audit logs with filters"""
    query = db.query(AuditLogEntry)

    if peer_id:
        query = query.filter(AuditLogEntry.peer_id == peer_id)
    if event_type:
        query = query.filter(AuditLogEntry.event_type == event_type)
    if result:
        query = query.filter(AuditLogEntry.result == result)
    if since:
        query = query.filter(AuditLogEntry.timestamp >= since)
    if until:
        query = query.filter(AuditLogEntry.timestamp <= until)

    return query.order_by(AuditLogEntry.timestamp.desc()).limit(limit).offset(offset).all()
```

**Acceptance Criteria**:
- [ ] Endpoint returns audit logs
- [ ] Filters work correctly
- [ ] Pagination supported
- [ ] API documentation generated

---

## Phase 5: Testing & Validation (Week 5)

### Story 5.1: Integration Test Suite
**File**: `tests/integration/test_p2p_security_integration.py` (NEW)

**Coverage**:
- [ ] End-to-end task assignment with capability validation
- [ ] P2P message signing and verification
- [ ] Task result submission via both HTTP and P2P
- [ ] Security audit log generation
- [ ] Token rotation and grace periods
- [ ] Graceful degradation when libp2p unavailable

---

### Story 5.2: Load Testing
**Tool**: Locust or k6

**Scenarios**:
- [ ] 100 concurrent task assignments with capability validation
- [ ] P2P message throughput (messages/sec)
- [ ] Signature verification performance
- [ ] Database audit log write throughput

---

### Story 5.3: Security Audit
**Checklist**:
- [ ] All messages signed with Ed25519
- [ ] Timestamp validation prevents replay attacks
- [ ] Capability tokens enforced on all task assignments
- [ ] Resource limits enforced (GPU minutes, concurrent tasks)
- [ ] Audit logs capture all security events
- [ ] PeerKeyStore resistant to key injection attacks
- [ ] No secrets in logs or audit trails

---

## Rollout Strategy

### Development Environment
1. Enable P2P + Security features via feature flags
2. Run parallel: old assignment flow + new P2P flow
3. Compare results for consistency

### Staging Environment
1. Deploy with P2P enabled
2. Monitor metrics for 48 hours
3. Validate audit logs
4. Load test at 2x production traffic

### Production Environment
1. Deploy with P2P **disabled** (feature flag OFF)
2. Enable for 10% of task assignments (canary)
3. Monitor error rates, latency, audit logs
4. Gradually increase to 50%, then 100%
5. Remove old code path after 2 weeks of stability

---

## Feature Flags

**Environment Variables**:
```bash
# Enable P2P task coordination
ENABLE_P2P_COORDINATION=false

# Enable capability validation (can be independent of P2P)
ENABLE_CAPABILITY_VALIDATION=false

# Enable message signing (should match P2P)
ENABLE_MESSAGE_SIGNING=false

# Enable security audit logging
ENABLE_SECURITY_AUDIT_LOGGING=true

# Bootstrap node address
BOOTSTRAP_NODE_ADDR=/ip4/127.0.0.1/tcp/4001
```

---

## Risk Mitigation

### High Risk: libp2p Host Initialization Failure
**Impact**: Backend fails to start
**Mitigation**: Wrap in try/except, log warning, continue without P2P
**Fallback**: HTTP-only task coordination

### Medium Risk: Message Signing Performance Overhead
**Impact**: Increased latency for task assignments
**Mitigation**: Benchmark Ed25519 signing (typically <1ms), cache identity keys
**Fallback**: Feature flag to disable signing

### Medium Risk: PeerKeyStore Database Contention
**Impact**: Slow key lookups under high load
**Mitigation**: In-memory cache with DB backing, connection pooling
**Fallback**: Increase cache size, add Redis layer

### Low Risk: Security Audit Log Write Failures
**Impact**: Missing audit entries
**Mitigation**: Use async writes, bounded queue, fallback to file logging
**Fallback**: FileAuditLogStorage instead of DatabaseAuditLogStorage

---

## Success Metrics

### Functional Metrics
- [ ] 100% of task assignments validate capabilities
- [ ] 100% of P2P messages signed and verified
- [ ] Zero task assignments to nodes lacking required capabilities
- [ ] All security events captured in audit log

### Performance Metrics
- [ ] P2P message latency <100ms (p95)
- [ ] Capability validation adds <10ms to task assignment (p95)
- [ ] Signature verification <5ms per message (p95)
- [ ] Audit log writes <20ms (p95)

### Reliability Metrics
- [ ] Backend continues operating if libp2p unavailable
- [ ] No data loss during P2P network partitions
- [ ] Graceful degradation to HTTP-only mode

---

## Dependencies

### External Libraries
- **py-libp2p**: Python libp2p implementation (install: `pip install libp2p`)
- **cryptography**: Ed25519 signing (already installed)
- **httpx**: Async HTTP (already installed)

### Infrastructure
- **Bootstrap Node**: Go libp2p DHT node (already implemented in `cmd/bootstrap-node/`)
- **PostgreSQL**: For peer key store and audit logs (already provisioned)

---

## Estimated Timeline

| Phase | Duration | Stories | Confidence |
|-------|----------|---------|------------|
| Phase 1: Foundation | 1 week | 3 stories | High |
| Phase 2: Security | 1 week | 3 stories | High |
| Phase 3: P2P Activation | 1 week | 3 stories | Medium |
| Phase 4: Hardening | 1 week | 3 stories | Medium |
| Phase 5: Testing | 1 week | 3 stories | Medium |
| **Total** | **5 weeks** | **15 stories** | **Medium** |

---

## Next Steps

1. **Review & Approve**: Get stakeholder sign-off on plan
2. **Create Stories**: Break down into Shortcut stories with acceptance criteria
3. **Assign**: Allocate to engineers (1-2 engineers recommended)
4. **Kickoff**: Sprint planning for Phase 1

---

## Related Documents

- [CLAUDE.md](/Users/aideveloper/openclaw-backend/CLAUDE.md) - Current system architecture
- [E5 Task Coordination Tests](tests/integration/test_task_coordination.py)
- [E7 Security Tests](tests/security/)
- [P2P Protocol Specs](backend/p2p/protocols/)
- [Security Services](backend/security/)

---

**Document Version**: 1.0
**Last Updated**: 2026-02-24
**Author**: System Architect
**Status**: Ready for Review
