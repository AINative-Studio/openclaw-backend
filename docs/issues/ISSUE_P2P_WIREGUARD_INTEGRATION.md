# Align OpenClaw Gateway with P2P/WireGuard Infrastructure

## Overview

Integrate the now-functional OpenClaw Gateway WebSocket communication with our existing WireGuard VPN and P2P network infrastructure for distributed agent swarms running on employee machines.

## Current Architecture

### What's Working ✅
- **OpenClaw Gateway Integration**: WebSocket authentication, agent messaging, response streaming
- **WireGuard VPN**: Hub-and-spoke topology with central hub at cloud backend
- **P2P Network**: libp2p-based direct agent-to-agent communication with Ed25519 identity
- **Task Assignment**: Capability-based matching and lease-based ownership
- **Fault Tolerance**: Node crash detection, lease revocation, result buffering during partitions

### Current Flow
```
Cloud Backend (Railway)
    ↓ REST API
Frontend (React)
    ↓ WebSocket
OpenClaw Gateway (localhost:18789)
    ↓ agent method
Agent Runtime (local process)
```

## Target Architecture

### Distributed Agent Swarm
```
                    ┌─────────────────────┐
                    │  Cloud Backend      │
                    │  (Railway)          │
                    │                     │
                    │  - FastAPI REST API │
                    │  - PostgreSQL DB    │
                    │  - Agent Lifecycle  │
                    └──────────┬──────────┘
                               │
                ┌──────────────┼──────────────┐
                │              │              │
         WireGuard VPN    OpenClaw      P2P Network
         (10.8.0.0/24)    WebSocket    (libp2p DHT)
                │              │              │
    ┌───────────┴──────────────┴──────────────┴───────────┐
    │                                                      │
┌───▼─────────────┐            ┌────────────────────┐
│ Employee Node 1 │            │ Employee Node 2    │
│ (10.8.0.2)      │◄──────────►│ (10.8.0.3)         │
│                 │   P2P      │                    │
│ - WireGuard     │  Direct    │ - WireGuard        │
│ - OpenClaw      │            │ - OpenClaw         │
│ - Agent Runtime │            │ - Agent Runtime    │
└─────────────────┘            └────────────────────┘
```

## Integration Requirements

### 1. OpenClaw Gateway Deployment Strategy

**Decision Point**: Where should OpenClaw Gateway run in distributed setup?

**Option A: Centralized Gateway** (Recommended for Phase 1)
```
Cloud Backend runs single Gateway instance
    → All employee nodes connect via wss://gateway.domain.com
    → Agents register with unique session keys (agent:node1-agent:main)
    → Gateway routes messages to correct node over persistent WebSocket
```

**Pros**:
- Single coordination point
- Simplified authentication (central token management)
- Works with existing Protocol v3 handshake
- No gateway port forwarding needed on employee machines

**Cons**:
- Single point of failure (mitigated by DBOS durable workflows)
- WebSocket latency for agent-to-agent communication

**Option B: Peer-to-Peer Gateway Mesh**
```
Each employee node runs local Gateway instance
    → Gateways discover each other via P2P network
    → Agent messages routed peer-to-peer over WireGuard
    → No central bottleneck
```

**Pros**:
- Low latency direct communication
- No single point of failure
- Better for high-volume agent collaboration

**Cons**:
- Complex gateway discovery mechanism needed
- Must implement gateway-to-gateway protocol
- Auth token synchronization challenge
- More operational complexity

### 2. Network Transport Integration

**WireGuard VPN Layer** (Already Built)
- All nodes have stable 10.8.0.x addresses
- Hub-and-spoke topology with cloud backend as hub
- Encrypted point-to-point tunnels

**P2P Discovery Layer** (Already Built)
- libp2p DHT for node discovery
- Ed25519 identity for signing
- Bootstrap node for initial peer connection

**WebSocket Layer** (Now Working)
- OpenClaw Gateway Protocol v3
- Token-based authentication
- agent/agent.wait/chat.history methods

**Integration Strategy**:
```python
# Agent-to-agent communication decision tree:

if target_agent.is_local():
    # Same machine - direct Gateway call
    result = await openclaw_bridge.send_to_agent(session_key, msg)

elif target_agent.is_remote_wireguard():
    # Remote but on WireGuard network
    # Connect to their Gateway over WireGuard IP
    gateway_url = f"wss://{target_node.wireguard_ip}:18789"
    bridge = OpenClawBridge(url=gateway_url, token=...)
    result = await bridge.send_to_agent(session_key, msg)

elif target_agent.is_p2p_only():
    # Direct P2P message (bypass Gateway)
    # Use existing TaskRequestProtocol
    await p2p_client.send_task_request(target_peer_id, task)

else:
    # Route through cloud backend Gateway
    result = await cloud_openclaw_bridge.send_to_agent(session_key, msg)
```

### 3. Session Key Convention for Distributed Agents

**Current Format**: `agent:{name}:main`
**Problem**: No node identifier - can't distinguish `agent:sales-agent:main` on different machines

**Proposed Format**: `agent:{node_id}-{name}:main`

Examples:
```
agent:node-employee1-sales-agent:main      (Employee 1's sales agent)
agent:node-employee2-customer-support:main (Employee 2's support agent)
agent:cloud-coordinator:main               (Cloud backend coordinator agent)
```

**Database Changes**:
```sql
-- Add node_id column to agent_swarm_instances
ALTER TABLE agent_swarm_instances
ADD COLUMN node_id VARCHAR(64);

-- Add unique constraint on (node_id, name)
CREATE UNIQUE INDEX idx_agent_node_name
ON agent_swarm_instances(node_id, name);
```

### 4. Task Assignment with Node Affinity

**Current**: Tasks assigned based on capabilities (GPU, CPU, memory)
**Enhancement**: Add node location preferences

```python
class TaskRequirements(BaseModel):
    # Existing fields...
    capabilities: List[CapabilityRequirement]
    resource_limits: List[ResourceLimit]

    # New fields for distributed deployment
    node_affinity: Optional[NodeAffinity] = None
    network_requirements: Optional[NetworkRequirements] = None

class NodeAffinity(BaseModel):
    """Node location preferences for task assignment"""
    preferred_nodes: List[str] = []  # ["employee1", "employee2"]
    required_node: Optional[str] = None  # Must run on this specific node
    locality: str = "any"  # "local-only" | "wireguard" | "any"

class NetworkRequirements(BaseModel):
    """Network connectivity requirements"""
    requires_wireguard: bool = False
    max_latency_ms: Optional[int] = None
    min_bandwidth_mbps: Optional[int] = None
```

**Task Assignment Flow**:
```python
async def assign_task_to_node(task: Task) -> str:
    # 1. Filter nodes by capabilities (existing logic)
    capable_nodes = filter_by_capabilities(task.requirements)

    # 2. Filter by network requirements (new)
    if task.requirements.network_requirements:
        capable_nodes = filter_by_network(
            capable_nodes,
            task.requirements.network_requirements
        )

    # 3. Apply node affinity preferences (new)
    if task.requirements.node_affinity:
        capable_nodes = apply_affinity(
            capable_nodes,
            task.requirements.node_affinity
        )

    # 4. Select best node (existing + latency scoring)
    selected_node = score_and_select(capable_nodes)

    # 5. Issue lease and assign (existing)
    return await issue_lease(task, selected_node)
```

### 5. Gateway Health Monitoring

**Extend Existing Health Checks**:
```python
# backend/api/v1/endpoints/wireguard_health.py - add Gateway status

@router.get("/wireguard/health")
async def wireguard_health(
    include_gateway: bool = False,
    db: Session = Depends(get_db)
):
    result = {
        "wireguard_status": "...",
        "peers": [...]
    }

    if include_gateway:
        # Check local Gateway health
        gateway_health = await check_openclaw_gateway()
        result["gateway_status"] = gateway_health

        # Check remote node Gateways over WireGuard
        peer_gateways = await check_peer_gateways(result["peers"])
        result["peer_gateways"] = peer_gateways

    return result

async def check_openclaw_gateway() -> Dict:
    """Check local OpenClaw Gateway health"""
    try:
        bridge = OpenClawBridge()
        await bridge.connect()
        # Test ping-pong or lightweight request
        return {"status": "healthy", "latency_ms": ...}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}
```

### 6. Security Considerations

**Authentication Across Nodes**:
- Each node's Gateway has unique `OPENCLAW_GATEWAY_TOKEN`
- Cloud backend maintains registry of node tokens
- Token rotation via API endpoint (stored in PostgreSQL)

**Data Access Control**:
- Agents can only access data scoped to their node (existing CapabilityToken.data_scope)
- Cloud coordinator can access all nodes (special permission)

**Message Signing** (Already Built):
- All P2P messages signed with Ed25519 keys
- Extend to Gateway messages for audit trail

```python
# Extend MessageEnvelope for Gateway messages
class GatewayMessageEnvelope(BaseModel):
    payload: Dict[str, Any]
    source_node_id: str
    target_session_key: str
    signature: str  # Ed25519 signature
    timestamp: int

# Sign Gateway messages
async def send_signed_message(session_key: str, message: str):
    payload = {"message": message, "to": session_key}
    signature = signing_service.sign_message(payload)

    envelope = GatewayMessageEnvelope(
        payload=payload,
        source_node_id=get_local_node_id(),
        target_session_key=session_key,
        signature=signature,
        timestamp=int(time.time())
    )

    result = await gateway_bridge.send_to_agent(
        session_key=session_key,
        message=json.dumps(envelope)
    )
```

### 7. Fault Tolerance for Distributed Agents

**Node Offline Scenarios**:
- Employee closes laptop → Node goes offline
- Network partition → Node temporarily unreachable
- Gateway crash → Restart via supervisor

**Recovery Strategy** (Extend E6 Epic):
```python
# New: Node Reconnection Detection
class NodeReconnectionService:
    """Detect when offline nodes come back online"""

    async def on_node_reconnect(self, node_id: str):
        # 1. Resume paused agents
        await resume_agents_on_node(node_id)

        # 2. Flush buffered messages
        await flush_queued_messages(node_id)

        # 3. Re-sync task leases
        await reconcile_leases(node_id)

        # 4. Notify dependent agents
        await notify_dependent_agents(node_id)
```

**Lease Extension for Long-Running Tasks**:
```python
# Current: Leases expire after 5/10/15 minutes
# Problem: Employee goes to lunch, laptop sleeps, lease expires

# Solution: Heartbeat-based lease extension
async def maintain_task_lease(task_id: str, peer_id: str):
    """Extend lease as long as task is actively running"""
    while task_is_running(task_id):
        await send_heartbeat(task_id, peer_id)
        await asyncio.sleep(30)  # Heartbeat every 30s
```

### 8. Observability (Extend E8 Epic)

**Distributed Tracing**:
```python
# Add trace_id to agent messages
class TracedAgentMessage(BaseModel):
    message: str
    to: str
    trace_id: str  # UUID linking request chain
    span_id: str   # Current operation ID
    parent_span_id: Optional[str]  # For nested operations

# Example flow:
# 1. User sends message to sales-agent on employee1
trace_id = str(uuid.uuid4())
span1 = create_span(trace_id, "user_to_sales_agent")

# 2. sales-agent delegates to research-agent on employee2
span2 = create_span(trace_id, "sales_to_research", parent=span1)

# 3. research-agent queries cloud database
span3 = create_span(trace_id, "research_db_query", parent=span2)

# All spans linked by trace_id → full request flow visible
```

**Metrics to Add**:
```python
# backend/services/prometheus_metrics_service.py

def record_gateway_message_sent(
    source_node: str,
    target_node: str,
    latency_ms: float
):
    """Track inter-node message latency"""
    histogram.labels(
        source=source_node,
        target=target_node
    ).observe(latency_ms)

def record_node_connectivity_status(
    node_id: str,
    status: str  # "connected" | "disconnected" | "degraded"
):
    """Track node availability"""
    gauge.labels(node_id=node_id).set(
        1 if status == "connected" else 0
    )
```

## Implementation Plan

### Phase 1: Centralized Gateway (2-3 weeks)
1. Deploy OpenClaw Gateway on cloud backend (Railway)
2. Add `node_id` field to database models
3. Update session key format: `agent:{node_id}-{name}:main`
4. Test multi-node communication over WireGuard
5. Add Gateway health checks to monitoring endpoints

### Phase 2: Enhanced Task Assignment (1-2 weeks)
1. Add `NodeAffinity` and `NetworkRequirements` to task models
2. Extend task assignment logic with network-aware scoring
3. Implement node capability registration (advertise WireGuard IP, Gateway URL)
4. Add node-specific task queues

### Phase 3: Fault Tolerance (2 weeks)
1. Node reconnection detection service
2. Heartbeat-based lease extension
3. Buffered message queue for offline nodes
4. Auto-resume agents on reconnect

### Phase 4: Observability (1 week)
1. Distributed tracing with trace_id propagation
2. Inter-node latency metrics
3. Node connectivity dashboard
4. Gateway performance metrics

### Phase 5: P2P Gateway Mesh (Optional - 3-4 weeks)
1. Gateway-to-gateway discovery protocol
2. Direct peer-to-peer Gateway routing
3. Distributed token registry with sync
4. Gateway mesh health monitoring

## Testing Strategy

### Local Multi-Node Simulation
```bash
# Terminal 1: Cloud backend
export NODE_ID="cloud"
python -m uvicorn backend.main:app --port 8000

# Terminal 2: Employee Node 1 (simulated)
export NODE_ID="employee1"
export WIREGUARD_IP="10.8.0.2"
openclaw gateway --port 18789

# Terminal 3: Employee Node 2 (simulated)
export NODE_ID="employee2"
export WIREGUARD_IP="10.8.0.3"
openclaw gateway --port 18790

# Test cross-node messaging
curl -X POST http://localhost:8000/api/v1/agents/{agent_id}/message \
  -d '{"message": "Delegate task to employee2-research-agent"}'
```

### Integration Tests
```python
# tests/integration/test_distributed_agents.py

async def test_cross_node_agent_messaging():
    """Test agent on node1 sending message to agent on node2"""
    # Setup: Create agents on different nodes
    agent1 = create_agent(node_id="employee1", name="sales")
    agent2 = create_agent(node_id="employee2", name="research")

    # Act: Send message from agent1 to agent2
    result = await send_agent_message(
        from_agent=agent1,
        to_session_key=f"agent:employee2-research:main",
        message="Research this product"
    )

    # Assert: Message delivered and response received
    assert result["status"] == "ok"
    assert result["response"] != ""

async def test_node_failure_recovery():
    """Test task reassignment when node goes offline"""
    # Setup: Assign task to employee1
    task = create_task(node_affinity=NodeAffinity(
        preferred_nodes=["employee1"]
    ))
    lease = await assign_task(task)

    # Act: Simulate node offline
    await simulate_node_offline("employee1")

    # Assert: Task reassigned to employee2
    await asyncio.sleep(65)  # Wait for crash detection (60s timeout)
    new_lease = await get_task_lease(task.id)
    assert new_lease.peer_id != lease.peer_id
    assert "employee2" in new_lease.peer_id
```

## Documentation Updates

### For Developers
- `docs/DISTRIBUTED_ARCHITECTURE.md` - Full architecture diagram
- `docs/AGENT_DEPLOYMENT_GUIDE.md` - How to run agents on employee machines
- `docs/TROUBLESHOOTING_DISTRIBUTED.md` - Common issues and fixes

### For Operations
- `docs/WIREGUARD_GATEWAY_SETUP.md` - WireGuard + Gateway installation
- `docs/MONITORING_DISTRIBUTED_SWARM.md` - Metrics and alerting
- `docs/DISASTER_RECOVERY.md` - Node failure scenarios

## Success Criteria

✅ Agents on different employee machines can communicate
✅ Tasks intelligently assigned based on node capabilities and network
✅ Node failures handled gracefully (no lost messages)
✅ Gateway health visible in monitoring dashboard
✅ End-to-end latency < 500ms for WireGuard agent-to-agent messages
✅ System recovers automatically from transient network partitions
✅ Comprehensive logs and traces for debugging distributed issues

## Open Questions

1. **Gateway Authentication**: Should employee nodes use device tokens or shared secrets?
2. **Message Persistence**: Should failed messages be stored in PostgreSQL or SQLite locally?
3. **Bandwidth Limits**: Do we need rate limiting for inter-node messages?
4. **Agent Mobility**: Should agents be able to migrate between nodes (e.g., laptop → desktop)?
5. **Multi-tenant Security**: If multiple employees, how to isolate their agent namespaces?

## References

- [OpenClaw Gateway Protocol](docs/OPENCLAW_AUTHENTICATION_PROTOCOL.md)
- [WireGuard Hub Manager](backend/networking/wireguard_hub_manager.py)
- [P2P Bootstrap Client](backend/p2p/libp2p_bootstrap_client.py)
- [Task Assignment Orchestrator](backend/services/task_assignment_orchestrator.py)
- [Fault Tolerance Epic (E6)](CLAUDE.md#fault-tolerance-epic-e6)

---

**Status**: Blocked on business requirements clarification
**Priority**: High
**Effort**: 8-12 weeks (all phases)
**Risk**: Medium (architectural complexity)
