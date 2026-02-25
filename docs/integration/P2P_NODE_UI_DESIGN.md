# P2P Peer Node UI/UX Design

**Epic**: UI for Employee Nodes to Join P2P Network
**Status**: Planning Phase
**Created**: 2026-02-24
**Priority**: Critical (Blocks P2P Integration)
**Related**: P2P_SECURITY_INTEGRATION_PLAN.md

## Executive Summary

The P2P integration plan identified a critical gap: **no UI for employee nodes to register, connect, and participate in the P2P task fabric**. This document defines the complete UI/UX flow, API endpoints, and frontend components needed for peer node management.

---

## Problem Statement

**Current Reality**:
- Backend has complete P2P protocols
- No way for employees to:
  - Register as a peer node
  - Generate libp2p identity
  - Discover other peers
  - Monitor their node health
  - Manage capabilities and tokens

**User Story**:
> "As an employee with a workstation (GPU/CPU), I want to join the OpenClaw P2P network so I can contribute compute resources and earn task assignments."

---

## User Personas

### 1. **Employee Node Operator**
- Has a workstation with GPU/CPU
- Wants to contribute to agent swarm
- Needs simple onboarding process
- Monitors node health and earnings

### 2. **Coordinator Admin**
- Manages the P2P network
- Views network topology
- Approves/revokes node capabilities
- Monitors network health

---

## User Flows

### Flow 1: New Node Onboarding

```
1. Employee clicks "Join Network" in UI
   ↓
2. System generates Ed25519 keypair + libp2p peer ID
   ↓
3. Employee enters node details:
   - Node name (e.g., "John's GPU Workstation")
   - Hardware capabilities (auto-detected + manual override)
     • CPU cores (detected: 16)
     • RAM (detected: 64GB)
     • GPU available? (Yes/No)
     • GPU model (detected: NVIDIA RTX 4090)
     • GPU memory (detected: 24GB)
     • Storage available (e.g., 500GB)
   ↓
4. System validates capabilities against minimum requirements
   ↓
5. System registers node with coordinator backend
   ↓
6. System connects to bootstrap node (DHT)
   ↓
7. System discovers peers via Kademlia DHT
   ↓
8. System issues capability token (JWT)
   ↓
9. Node dashboard displays:
   - ✅ Connected to network
   - Peer ID: 12D3KooW...
   - Connected peers: 5
   - Status: Ready for tasks
```

**Time to Complete**: <2 minutes

---

### Flow 2: View Network Topology

```
1. Employee navigates to "Network" tab
   ↓
2. UI displays:
   - Interactive network graph
   - My node (highlighted)
   - Connected peers (with connection strength)
   - Bootstrap node
   - Task coordinator
   ↓
3. Employee clicks on peer node
   ↓
4. Peer details modal:
   - Peer ID
   - Capabilities
   - Tasks completed
   - Reputation score
   - Last seen timestamp
```

---

### Flow 3: Manage Capabilities

```
1. Employee navigates to "Settings" → "Capabilities"
   ↓
2. UI displays current capabilities:
   - CPU: 16 cores ✓
   - RAM: 64GB ✓
   - GPU: RTX 4090 24GB ✓
   - Storage: 500GB ✓
   ↓
3. Employee adjusts limits:
   - Max concurrent tasks: 5 → 3
   - GPU hours per week: 40 → 20
   - Allow training jobs: Yes
   - Allow inference only: No
   ↓
4. System validates changes
   ↓
5. System rotates capability token with new limits
   ↓
6. Toast notification: "Capabilities updated successfully"
```

---

### Flow 4: Monitor Node Health

```
1. Employee views node dashboard
   ↓
2. Real-time metrics displayed:
   - Status: 🟢 Online
   - Uptime: 5 days 14 hours
   - Tasks completed: 127
   - Tasks running: 2
   - CPU usage: 45%
   - GPU usage: 78%
   - Network: Connected to 8 peers
   - Reputation: ⭐ 4.8/5.0
   ↓
3. Recent activity feed:
   - 2 mins ago: Task #5234 completed (image generation)
   - 15 mins ago: Task #5231 assigned
   - 1 hour ago: Peer 12D3KooW... connected
```

---

## UI Components

### 1. Node Registration Wizard
**File**: `app/nodes/register/page.tsx`

**Steps**:
1. Welcome screen
2. Hardware detection
3. Capability configuration
4. Identity generation
5. Network connection
6. Success confirmation

**Key Elements**:
- Auto-detect hardware button
- GPU memory slider
- Task limit inputs
- Progress stepper (1/6, 2/6, etc.)
- "Skip for now" option on optional steps

**Mockup**:
```
┌─────────────────────────────────────────┐
│  Join OpenClaw P2P Network              │
│  ─────────────────────────────────────  │
│                                         │
│  Step 2 of 6: Configure Hardware       │
│                                         │
│  [🖥️ Auto-Detect Hardware]              │
│                                         │
│  CPU Cores: [16 cores]     ✓ Detected  │
│  RAM:       [64 GB]        ✓ Detected  │
│  GPU:       [✓] NVIDIA RTX 4090        │
│  GPU Memory:[24 GB]        ✓ Detected  │
│  Storage:   [500 GB] available         │
│                                         │
│  Resource Limits:                       │
│  Max concurrent tasks: [5]             │
│  GPU hours/week:      [40] hours       │
│                                         │
│              [Back]  [Continue →]      │
└─────────────────────────────────────────┘
```

---

### 2. Node Dashboard
**File**: `app/nodes/dashboard/page.tsx`

**Layout**: 3-column grid

**Left Column** (Status Overview):
- Connection status badge
- Peer ID (with copy button)
- Uptime counter
- Quick stats cards (tasks, earnings, reputation)

**Center Column** (Activity Feed):
- Real-time task assignments
- Task completions
- Peer connections/disconnections
- Error/warning alerts

**Right Column** (Resource Usage):
- CPU usage chart
- GPU usage chart
- Memory usage chart
- Network bandwidth chart

**Mockup**:
```
┌─────────────────────────────────────────────────────────────┐
│  My Node Dashboard                                          │
│  ───────────────────────────────────────────────────────   │
│                                                             │
│  🟢 Online  Peer ID: 12D3KooW...4x7a [📋]                 │
│  Uptime: 5d 14h 23m                                        │
│                                                             │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐                     │
│  │ 127  │ │  2   │ │  8   │ │ 4.8  │                     │
│  │Tasks │ │Active│ │Peers │ │ ⭐   │                     │
│  └──────┘ └──────┘ └──────┘ └──────┘                     │
│                                                             │
│  Recent Activity:                                          │
│  ─────────────────                                         │
│  ✅ 2m ago  Task #5234 completed (reward: 0.5 credits)   │
│  📋 15m ago Task #5231 assigned (image generation)        │
│  🔗 1h ago  Peer 12D3KooW...xyz connected                 │
│                                                             │
│  [View All Activity →]                                     │
└─────────────────────────────────────────────────────────────┘
```

---

### 3. Peer Discovery / Network View
**File**: `app/nodes/network/page.tsx`

**Features**:
- Interactive force-directed graph (D3.js or React Flow)
- Node types:
  - My node (highlighted, larger)
  - Connected peers (green)
  - Indirect peers (gray)
  - Bootstrap node (blue, star icon)
  - Coordinator (orange, diamond icon)
- Connection lines (thickness = connection strength)
- Hover tooltips with peer details
- Click to view full peer info

**Mockup**:
```
┌─────────────────────────────────────────────────────────────┐
│  P2P Network Topology                                       │
│  ───────────────────────────────────────────────────────   │
│                                                             │
│  Connected Peers: 8      Discovered: 23      Health: 🟢   │
│                                                             │
│              ⭐ Bootstrap                                   │
│                 |                                           │
│        ┌────────┼────────┐                                 │
│        │        │        │                                 │
│       ●──●     💎      ●──●                               │
│       │   │  Coord     │   │                               │
│       ●   🔵(Me)───────●   ●                              │
│           │             \                                   │
│           ●              ●                                  │
│                                                             │
│  Legend: 🔵 My Node  ● Peer  ⭐ Bootstrap  💎 Coordinator │
│                                                             │
│  Selected: None                                            │
│  [Click on a node to view details]                         │
└─────────────────────────────────────────────────────────────┘
```

---

### 4. Peer Details Modal
**Triggered**: Click on peer in network view

**Content**:
```
┌────────────────────────────────────────┐
│  Peer Details                    [×]   │
│  ────────────────────────────────────  │
│                                        │
│  Name: Alice's GPU Rig                │
│  Peer ID: 12D3KooWj...xyz             │
│                                        │
│  Capabilities:                         │
│  • CPU: 32 cores                       │
│  • RAM: 128 GB                         │
│  • GPU: 2× RTX 4090 (48GB total)      │
│  • Max concurrent tasks: 10            │
│                                        │
│  Performance:                          │
│  • Tasks completed: 1,247              │
│  • Success rate: 98.5%                 │
│  • Avg completion time: 12 mins        │
│  • Reputation: ⭐ 4.9/5.0              │
│                                        │
│  Status: 🟢 Online                     │
│  Last seen: 2 minutes ago              │
│  Uptime: 23 days                       │
│                                        │
│          [Send Message] [Close]        │
└────────────────────────────────────────┘
```

---

### 5. Capability Management Settings
**File**: `app/nodes/settings/capabilities/page.tsx`

**Sections**:
1. **Hardware Limits**
   - Max concurrent tasks slider
   - GPU hours per week slider
   - Storage allocation slider

2. **Task Preferences**
   - Allow training jobs (toggle)
   - Allow inference only (toggle)
   - Max task duration (dropdown)

3. **Data Scopes** (Advanced)
   - Allowed projects (multi-select)
   - Data classification level (dropdown: Public, Internal, Confidential)

4. **Token Management**
   - Current token expiration
   - Renew token button
   - Revoke all tokens button

**Mockup**:
```
┌─────────────────────────────────────────┐
│  Capability Settings                    │
│  ─────────────────────────────────────  │
│                                         │
│  Hardware Limits:                       │
│  ┌─────────────────────────────────┐   │
│  │ Max Concurrent Tasks            │   │
│  │ [━━━━━━●─────────] 5 tasks     │   │
│  │                                 │   │
│  │ GPU Hours per Week              │   │
│  │ [━━━━━━━━●───────] 40 hours    │   │
│  │                                 │   │
│  │ Storage Allocation              │   │
│  │ [━━━━━●───────────] 500 GB     │   │
│  └─────────────────────────────────┘   │
│                                         │
│  Task Preferences:                      │
│  [✓] Allow training jobs                │
│  [✓] Allow inference jobs               │
│  [ ] Allow data preprocessing only      │
│                                         │
│  Max task duration: [2 hours ▾]        │
│                                         │
│  Token Status:                          │
│  Expires: 2026-03-24 (28 days)         │
│  [🔄 Renew Token Now]                  │
│                                         │
│           [Cancel]  [Save Changes]     │
└─────────────────────────────────────────┘
```

---

## API Endpoints

### Node Registration & Management

#### POST /api/v1/nodes/register
**Purpose**: Register new peer node with coordinator

**Request**:
```json
{
  "name": "John's GPU Workstation",
  "peer_id": "12D3KooWj4x7a...",
  "public_key": "base64-encoded-ed25519-public-key",
  "capabilities": {
    "cpu_cores": 16,
    "memory_gb": 64,
    "gpu_available": true,
    "gpu_model": "NVIDIA RTX 4090",
    "gpu_memory_gb": 24,
    "storage_gb": 500
  },
  "limits": {
    "max_concurrent_tasks": 5,
    "max_gpu_hours_per_week": 40
  },
  "preferences": {
    "allow_training": true,
    "allow_inference": true,
    "max_task_duration_hours": 2
  }
}
```

**Response**:
```json
{
  "node_id": "uuid-v4",
  "peer_id": "12D3KooWj4x7a...",
  "status": "registered",
  "capability_token": "eyJhbGciOi...",
  "bootstrap_node_address": "/ip4/35.123.45.67/tcp/4001/p2p/12D3KooW...",
  "coordinator_peer_id": "12D3KooWc...",
  "registered_at": "2026-02-24T23:45:00Z"
}
```

---

#### GET /api/v1/nodes/{node_id}
**Purpose**: Get node details

**Response**:
```json
{
  "node_id": "uuid-v4",
  "peer_id": "12D3KooWj4x7a...",
  "name": "John's GPU Workstation",
  "status": "online",
  "capabilities": {...},
  "limits": {...},
  "stats": {
    "tasks_completed": 127,
    "tasks_running": 2,
    "success_rate": 0.985,
    "reputation_score": 4.8,
    "uptime_seconds": 478800
  },
  "last_heartbeat_at": "2026-02-24T23:45:00Z",
  "registered_at": "2026-02-19T10:00:00Z"
}
```

---

#### PUT /api/v1/nodes/{node_id}/capabilities
**Purpose**: Update node capabilities and limits

**Request**:
```json
{
  "limits": {
    "max_concurrent_tasks": 3,
    "max_gpu_hours_per_week": 20
  },
  "preferences": {
    "allow_training": false
  }
}
```

**Response**:
```json
{
  "status": "updated",
  "new_capability_token": "eyJhbGciOi...",
  "token_expires_at": "2026-03-24T23:45:00Z"
}
```

---

#### GET /api/v1/nodes/{node_id}/peers
**Purpose**: List discovered peers from this node's perspective

**Response**:
```json
{
  "peers": [
    {
      "peer_id": "12D3KooWabc...",
      "name": "Alice's GPU Rig",
      "connection_quality": 0.95,
      "latency_ms": 12,
      "last_seen_at": "2026-02-24T23:44:00Z",
      "capabilities_summary": "32 cores, 128GB RAM, 2× RTX 4090"
    },
    {...}
  ],
  "total_peers": 8
}
```

---

#### GET /api/v1/nodes/{node_id}/network-topology
**Purpose**: Get network topology data for visualization

**Response**:
```json
{
  "nodes": [
    {
      "id": "12D3KooWj4x7a...",
      "type": "my_node",
      "name": "John's GPU Workstation",
      "x": 0,
      "y": 0
    },
    {
      "id": "12D3KooWabc...",
      "type": "peer",
      "name": "Alice's GPU Rig",
      "x": 100,
      "y": 50
    },
    {
      "id": "bootstrap-node",
      "type": "bootstrap",
      "name": "Bootstrap DHT",
      "x": 50,
      "y": -100
    },
    {
      "id": "coordinator",
      "type": "coordinator",
      "name": "Task Coordinator",
      "x": 50,
      "y": 100
    }
  ],
  "edges": [
    {
      "source": "12D3KooWj4x7a...",
      "target": "12D3KooWabc...",
      "strength": 0.95,
      "latency_ms": 12
    },
    {...}
  ]
}
```

---

#### POST /api/v1/nodes/{node_id}/connect
**Purpose**: Initiate connection to bootstrap node (trigger DHT discovery)

**Request**:
```json
{
  "bootstrap_address": "/ip4/35.123.45.67/tcp/4001/p2p/12D3KooW..."
}
```

**Response**:
```json
{
  "status": "connected",
  "discovered_peers": 23,
  "connected_peers": 8,
  "connection_duration_ms": 450
}
```

---

#### GET /api/v1/nodes/{node_id}/health
**Purpose**: Real-time node health metrics (for dashboard)

**Response**:
```json
{
  "status": "online",
  "uptime_seconds": 478800,
  "tasks_running": 2,
  "resource_usage": {
    "cpu_percent": 45,
    "memory_percent": 62,
    "gpu_percent": 78,
    "network_mbps": 125
  },
  "network": {
    "connected_peers": 8,
    "bootstrap_connected": true,
    "coordinator_connected": true
  },
  "last_heartbeat_at": "2026-02-24T23:45:00Z"
}
```

---

#### GET /api/v1/nodes/{node_id}/activity
**Purpose**: Activity feed for dashboard

**Query Params**: `?limit=20&offset=0`

**Response**:
```json
{
  "activities": [
    {
      "id": "act-123",
      "type": "task_completed",
      "timestamp": "2026-02-24T23:43:00Z",
      "data": {
        "task_id": "task-5234",
        "task_type": "image_generation",
        "reward_credits": 0.5
      }
    },
    {
      "id": "act-122",
      "type": "task_assigned",
      "timestamp": "2026-02-24T23:30:00Z",
      "data": {
        "task_id": "task-5231",
        "task_type": "image_generation",
        "estimated_duration_minutes": 15
      }
    },
    {
      "id": "act-121",
      "type": "peer_connected",
      "timestamp": "2026-02-24T22:45:00Z",
      "data": {
        "peer_id": "12D3KooWxyz...",
        "peer_name": "Bob's Inference Node"
      }
    }
  ],
  "total": 347
}
```

---

#### GET /api/v1/nodes/{node_id}/token
**Purpose**: Get current capability token

**Response**:
```json
{
  "token": "eyJhbGciOi...",
  "issued_at": "2026-02-24T00:00:00Z",
  "expires_at": "2026-03-24T00:00:00Z",
  "capabilities": ["gpu_inference", "cpu_training"],
  "limits": {
    "max_concurrent_tasks": 5,
    "max_gpu_hours_per_week": 40
  }
}
```

---

#### POST /api/v1/nodes/{node_id}/token/renew
**Purpose**: Renew capability token (token rotation)

**Response**:
```json
{
  "new_token": "eyJhbGciOi...",
  "issued_at": "2026-02-24T23:45:00Z",
  "expires_at": "2026-03-24T23:45:00Z",
  "old_token_valid_until": "2026-02-24T23:50:00Z"
}
```

---

## Backend Services

### NodeRegistrationService
**File**: `backend/services/node_registration_service.py`

**Responsibilities**:
- Validate node registration requests
- Store peer public keys in PeerKeyStore
- Generate and issue capability tokens
- Record node in database

**Methods**:
```python
async def register_node(
    name: str,
    peer_id: str,
    public_key: bytes,
    capabilities: Dict[str, Any],
    limits: Dict[str, Any],
    preferences: Dict[str, Any]
) -> NodeRegistration
```

---

### NodeDiscoveryService
**File**: `backend/services/node_discovery_service.py`

**Responsibilities**:
- Bootstrap node connection
- DHT peer discovery
- Network topology calculation
- Connection health monitoring

**Methods**:
```python
async def connect_to_bootstrap(node_id: str, bootstrap_addr: str) -> ConnectionResult
async def discover_peers(node_id: str) -> List[Peer]
async def get_network_topology(node_id: str) -> NetworkTopology
```

---

### NodeHealthMonitor
**File**: `backend/services/node_health_monitor.py`

**Responsibilities**:
- Collect real-time metrics
- Heartbeat tracking
- Resource usage monitoring
- Activity feed generation

**Methods**:
```python
async def get_health_metrics(node_id: str) -> HealthMetrics
async def record_activity(node_id: str, activity: Activity) -> None
async def get_activity_feed(node_id: str, limit: int, offset: int) -> List[Activity]
```

---

## Database Models

### PeerNode (New)
**File**: `backend/models/peer_node.py`

```python
class PeerNode(Base):
    __tablename__ = "peer_nodes"

    id = Column(UUID, primary_key=True, default=uuid4)
    peer_id = Column(String(128), unique=True, nullable=False, index=True)
    name = Column(String(256), nullable=False)
    status = Column(Enum(NodeStatus), default=NodeStatus.REGISTERED)

    # Capabilities
    capabilities = Column(JSON, nullable=False)  # cpu_cores, memory_gb, gpu_*
    limits = Column(JSON, nullable=False)  # max_concurrent_tasks, max_gpu_hours
    preferences = Column(JSON, nullable=False)  # allow_training, allow_inference

    # Stats
    tasks_completed = Column(Integer, default=0)
    tasks_running = Column(Integer, default=0)
    success_rate = Column(Float, default=1.0)
    reputation_score = Column(Float, default=5.0)

    # Timestamps
    registered_at = Column(DateTime(timezone=True), nullable=False)
    last_heartbeat_at = Column(DateTime(timezone=True))
    last_task_assigned_at = Column(DateTime(timezone=True))

    # Relationships
    activities = relationship("NodeActivity", back_populates="node")
```

---

### NodeActivity (New)
**File**: `backend/models/node_activity.py`

```python
class NodeActivity(Base):
    __tablename__ = "node_activities"

    id = Column(UUID, primary_key=True, default=uuid4)
    node_id = Column(UUID, ForeignKey("peer_nodes.id"), nullable=False, index=True)
    activity_type = Column(Enum(ActivityType), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    data = Column(JSON)  # Type-specific activity data

    node = relationship("PeerNode", back_populates="activities")
```

---

### PeerConnection (New)
**File**: `backend/models/peer_connection.py`

```python
class PeerConnection(Base):
    __tablename__ = "peer_connections"

    id = Column(UUID, primary_key=True, default=uuid4)
    source_peer_id = Column(String(128), nullable=False, index=True)
    target_peer_id = Column(String(128), nullable=False, index=True)
    connection_quality = Column(Float, default=0.0)  # 0.0 to 1.0
    latency_ms = Column(Integer)
    last_seen_at = Column(DateTime(timezone=True), nullable=False)

    # Composite index for fast topology queries
    __table_args__ = (
        Index('idx_peer_connections', 'source_peer_id', 'target_peer_id'),
    )
```

---

## Frontend Components

### React Hooks

#### useNodeRegistration
```typescript
export function useNodeRegistration() {
  return useMutation({
    mutationFn: async (data: NodeRegistrationRequest) => {
      const response = await fetch('/api/v1/nodes/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      return response.json();
    },
    onSuccess: (data) => {
      // Store capability token in localStorage
      localStorage.setItem('capability_token', data.capability_token);
      localStorage.setItem('node_id', data.node_id);
    }
  });
}
```

---

#### useNodeHealth
```typescript
export function useNodeHealth(nodeId: string) {
  return useQuery({
    queryKey: ['node-health', nodeId],
    queryFn: async () => {
      const response = await fetch(`/api/v1/nodes/${nodeId}/health`);
      return response.json();
    },
    refetchInterval: 5000  // Poll every 5 seconds
  });
}
```

---

#### useNetworkTopology
```typescript
export function useNetworkTopology(nodeId: string) {
  return useQuery({
    queryKey: ['network-topology', nodeId],
    queryFn: async () => {
      const response = await fetch(`/api/v1/nodes/${nodeId}/network-topology`);
      return response.json();
    },
    refetchInterval: 10000  // Poll every 10 seconds
  });
}
```

---

### Network Topology Visualization

**Library**: React Flow (https://reactflow.dev/) or D3.js

**Component**: `components/nodes/NetworkTopologyGraph.tsx`

**Features**:
- Force-directed layout
- Node dragging
- Zoom and pan
- Hover tooltips
- Click to view details
- Real-time updates

---

## Navigation

### Updated Sidebar Menu

```
┌──────────────────────┐
│ OpenClaw             │
├──────────────────────┤
│ 📊 Dashboard         │
│ 🤖 Agents            │
│ 🔗 Channels          │
│ ⚙️  Settings         │
├──────────────────────┤
│ 🌐 P2P Network  NEW  │  ← Add this section
│   • My Node          │
│   • Network Map      │
│   • Peer Discovery   │
│   • Activity Feed    │
└──────────────────────┘
```

---

## User Stories

### Epic: Peer Node Management

#### Story 1: Node Registration
```
AS AN employee with a workstation
I WANT TO register my machine as a peer node
SO THAT I can contribute compute resources to the swarm

ACCEPTANCE CRITERIA:
- [ ] Registration wizard detects hardware automatically
- [ ] User can override detected values
- [ ] System generates Ed25519 keypair locally
- [ ] System registers node with coordinator backend
- [ ] User receives capability token (JWT)
- [ ] Registration completes in <2 minutes
```

#### Story 2: Node Dashboard
```
AS A node operator
I WANT TO view my node's health and activity
SO THAT I can monitor performance and earnings

ACCEPTANCE CRITERIA:
- [ ] Dashboard shows connection status (online/offline)
- [ ] Dashboard displays peer ID with copy button
- [ ] Dashboard shows real-time resource usage (CPU, GPU, memory)
- [ ] Dashboard lists recent tasks (assigned, completed)
- [ ] Dashboard shows reputation score and earnings
- [ ] Metrics update every 5 seconds
```

#### Story 3: Network Visualization
```
AS A node operator
I WANT TO see the P2P network topology
SO THAT I understand my position in the network

ACCEPTANCE CRITERIA:
- [ ] Interactive graph shows my node + connected peers
- [ ] Graph updates in real-time as peers join/leave
- [ ] Clicking on peer shows details modal
- [ ] Graph displays connection quality (line thickness)
- [ ] Bootstrap node and coordinator are highlighted
```

#### Story 4: Capability Management
```
AS A node operator
I WANT TO adjust my resource limits
SO THAT I can control workload and availability

ACCEPTANCE CRITERIA:
- [ ] Settings page shows current capabilities
- [ ] User can adjust max concurrent tasks (slider)
- [ ] User can adjust GPU hours per week (slider)
- [ ] User can toggle task type preferences
- [ ] Changes trigger token rotation
- [ ] New token issued within 5 seconds
```

---

## Security Considerations

1. **Local Key Storage**: Ed25519 private key stored securely (encrypted localStorage or native keystore)
2. **Token Transmission**: Capability tokens only sent over HTTPS
3. **Peer Verification**: All peer connections verified via Ed25519 signatures
4. **Rate Limiting**: API endpoints rate-limited per node (10 req/min for registration, 100 req/min for health)
5. **Node Approval**: Optional admin approval step before node can receive tasks

---

## Implementation Priority

### Phase 0: MVP (Week 1-2)
- [ ] Node registration API endpoint
- [ ] Node registration wizard UI
- [ ] Basic node dashboard (status + stats)
- [ ] Backend NodeRegistrationService

### Phase 1: Core Features (Week 3-4)
- [ ] Peer discovery API endpoints
- [ ] Network topology API
- [ ] Network visualization component
- [ ] Activity feed

### Phase 2: Advanced Features (Week 5-6)
- [ ] Capability management settings
- [ ] Token rotation UI
- [ ] Peer details modal
- [ ] Real-time metrics

---

## Open Questions

1. **Agent Desktop App vs Web UI**: Should nodes run a desktop app (Electron/Tauri) or web-based client?
   - **Desktop App**: Better for local key storage, always-running background process
   - **Web UI**: Easier deployment, works on any device

2. **Hardware Detection**: Use native APIs (Electron) or require manual entry?
   - **Recommendation**: Auto-detect with override (best UX)

3. **Approval Workflow**: Should coordinators manually approve new nodes?
   - **Recommendation**: Yes for production, no for dev/testing (feature flag)

4. **Earnings/Rewards**: How are task completions rewarded?
   - **Recommendation**: Credit system tracked in database (outside this scope)

---

## Dependencies

### NPM Packages
- `react-flow` - Network topology visualization
- `recharts` - Resource usage charts
- `@tanstack/react-query` - API state management
- `libp2p` (node package) - If building desktop app

### Backend
- `py-libp2p` - Python libp2p implementation
- Existing P2P protocols (Epic E5)
- Existing security services (Epic E7)

---

## Timeline

| Week | Deliverables |
|------|-------------|
| 1 | Node registration API + basic UI wizard |
| 2 | Node dashboard with real-time metrics |
| 3 | Peer discovery API + peer list view |
| 4 | Network topology API + visualization |
| 5 | Capability management settings |
| 6 | Activity feed + polish |

**Total**: 6 weeks (parallel with P2P integration backend work)

---

## Next Steps

1. **User Testing**: Create interactive mockups for employee feedback
2. **Architecture Review**: Decide desktop app vs web client
3. **Backend API Contract**: Finalize API spec with backend team
4. **Create Stories**: Break down into Shortcut stories
5. **Design System**: Ensure components match existing UI patterns

---

**Document Version**: 1.0
**Last Updated**: 2026-02-24
**Author**: System Architect
**Status**: Ready for Review
