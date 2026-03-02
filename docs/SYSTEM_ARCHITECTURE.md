# OpenClaw Backend - Complete System Architecture

**Last Updated**: 2026-03-02
**Status**: Production-Ready (with Gateway TypeScript source and DBOS SSL fix)

---

## Table of Contents

1. [System Overview](#system-overview)
2. [Three-Service Architecture](#three-service-architecture)
3. [Component Details](#component-details)
4. [Data Flow](#data-flow)
5. [Technology Stack](#technology-stack)
6. [Deployment Architecture](#deployment-architecture)
7. [Critical Configuration](#critical-configuration)

---

## System Overview

OpenClaw Backend is a **three-service architecture** for AI agent orchestration with durable workflow execution:

```
┌────────────────────────────────────────────────────────────────┐
│                    OpenClaw Backend System                      │
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐   │
│  │   Frontend   │────▶│   Backend    │────▶│   Gateway    │   │
│  │  (Next.js)   │     │  (FastAPI)   │     │   (DBOS)     │   │
│  │  Port 3002   │     │  Port 8000   │     │  Port 18789  │   │
│  └──────────────┘     └──────┬───────┘     └──────┬───────┘   │
│                               │                     │            │
│                               │                     │            │
│                               ▼                     ▼            │
│                        ┌──────────────────────────────┐         │
│                        │  Railway PostgreSQL (6432)   │         │
│                        │  - Backend DB (ainative_app) │         │
│                        │  - DBOS System (dbos_sys)    │         │
│                        └──────────────────────────────┘         │
└────────────────────────────────────────────────────────────────┘
```

**Purpose**: Durable, crash-recoverable AI agent lifecycle management with DBOS workflows

---

## Three-Service Architecture

### 1. Frontend Dashboard (agent-swarm-monitor)

**Technology**: Next.js 14 (React, TypeScript)
**Port**: 3002
**Repository**: `../agent-swarm-monitor/`

**Responsibilities**:
- Agent swarm visualization and monitoring
- Agent lifecycle control (create, start, pause, stop)
- Task progress tracking
- Real-time status updates via WebSocket
- GitHub repository integration UI

**Key Features**:
- Server-side rendering (SSR)
- Real-time WebSocket updates
- Agent workflow visualization (7-step wizard)
- Task queue and execution timeline
- RLHF feedback collection

**API Consumption**:
- Backend API (port 8000) via `NEXT_PUBLIC_API_URL`
- All REST endpoints: `/api/v1/agents`, `/api/v1/swarm/health`, `/api/v1/metrics`

**Configuration**:
```env
# agent-swarm-monitor/.env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

### 2. Backend API (FastAPI)

**Technology**: Python 3.12, FastAPI, SQLAlchemy 2.0
**Port**: 8000
**Location**: `backend/`

**Responsibilities**:
- REST API for agent lifecycle operations
- WhatsApp command parsing (hybrid regex + Claude LLM)
- OpenClaw Gateway integration (WebSocket bridge)
- WireGuard VPN provisioning
- P2P task distribution
- Prometheus metrics export
- Swarm health monitoring

**Key Services**:
- `AgentSwarmLifecycleService` - Agent CRUD operations
- `ClaudeOrchestrator` - AI-driven agent orchestration
- `CommandParser` - Natural language command parsing
- `DBOSWorkflowMonitor` - Gateway workflow health checks
- `WireGuardProvisioningService` - Secure P2P networking
- `TaskAssignmentOrchestrator` - P2P task distribution
- `PrometheusMetricsService` - Observability (Epic E8-S1)

**API Endpoints**:
| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Service health check |
| `GET /api/v1/agents` | List all agents |
| `POST /api/v1/agents` | Create new agent |
| `POST /api/v1/agents/{id}/provision` | Provision agent via DBOS |
| `POST /api/v1/agents/{id}/pause` | Pause agent via DBOS |
| `POST /api/v1/agents/{id}/resume` | Resume agent via DBOS |
| `GET /api/v1/swarm/health` | Swarm health snapshot (E8-S2) |
| `GET /api/v1/swarm/timeline` | Task execution timeline (E8-S3) |
| `GET /api/v1/metrics` | Prometheus metrics (E8-S1) |
| `POST /api/v1/wireguard/provision` | Provision WireGuard peer |
| `GET /openclaw/status` | OpenClaw connection status |

**Database**: Railway PostgreSQL (port 6432 via PgBouncer)
- Database: `ainative_app`
- Pool size: 20 connections (10 base + 10 overflow)

**Configuration**:
```env
# backend .env
SECRET_KEY=dev-secret-key-for-local-testing
OPENCLAW_GATEWAY_URL=http://localhost:18789
OPENCLAW_GATEWAY_TOKEN=openclaw-dev-token-12345
DATABASE_URL=postgresql://postgres:***@yamabiko.proxy.rlwy.net:6432/ainative_app
ENVIRONMENT=development
ANTHROPIC_API_KEY=sk-ant-***
```

---

### 3. OpenClaw Gateway (DBOS)

**Technology**: Node.js 20, TypeScript, DBOS SDK v4.9.11, Express, WebSocket
**Port**: 18789
**Location**: `openclaw-gateway/`

**Responsibilities**:
- **Durable workflow execution** (survives crashes)
- Agent provisioning workflows (`provisionAgentWorkflow`)
- Agent heartbeat workflows (`heartbeatWorkflow`)
- Agent pause/resume workflows (`pauseResumeWorkflow`)
- Message routing workflows (`routeAgentMessage`)
- Workflow recovery on restart

**Architecture**:
```
Gateway Internal Architecture:

┌─────────────────────────────────────────────────┐
│         OpenClaw Gateway (Port 18789)           │
│                                                  │
│  ┌────────────────────────────────────────┐    │
│  │      Express HTTP + WebSocket          │    │
│  │  - GET /health                          │    │
│  │  - POST /workflows/provision-agent      │    │
│  │  - POST /workflows/heartbeat            │    │
│  │  - POST /workflows/pause-resume         │    │
│  │  - WS / (message routing)               │    │
│  └──────────────┬─────────────────────────┘    │
│                 │                                │
│  ┌──────────────▼─────────────────────────┐    │
│  │      DBOS Runtime Engine               │    │
│  │  - @DBOS.workflow() decorators         │    │
│  │  - @DBOS.step() decorators             │    │
│  │  - Crash recovery                       │    │
│  │  - Exactly-once execution               │    │
│  └──────────────┬─────────────────────────┘    │
│                 │                                │
│                 ▼                                │
│  ┌────────────────────────────────────────┐    │
│  │   PostgreSQL System Database           │    │
│  │   - workflow_status                     │    │
│  │   - workflow_events                     │    │
│  │   - operation_outputs                   │    │
│  │   - notifications (agent messages)      │    │
│  └────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

**Key Workflows**:
1. **Agent Provisioning** (`provisionAgentWorkflow`)
   - Creates agent in OpenClaw
   - Assigns session key
   - Configures heartbeat (if enabled)
   - Returns provisioning result

2. **Agent Heartbeat** (`heartbeatWorkflow`)
   - Executes periodic agent health check
   - Runs checklist tasks
   - Stores execution results

3. **Agent Pause/Resume** (`pauseResumeWorkflow`)
   - Pauses agent execution
   - Preserves agent state
   - Resumes from checkpoint

4. **Message Routing** (`routeAgentMessage`)
   - Validates message format
   - Stores message for durability
   - Routes to target agent
   - Guaranteed delivery

**DBOS System Tables** (created automatically):
```sql
-- PostgreSQL schema: dbos_system
CREATE TABLE workflow_status (
    workflow_uuid UUID PRIMARY KEY,
    status VARCHAR(50),
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    recovery_attempts INT DEFAULT 0
);

CREATE TABLE workflow_events (
    id SERIAL PRIMARY KEY,
    workflow_uuid UUID REFERENCES workflow_status(workflow_uuid),
    event_type VARCHAR(100),
    event_data JSONB,
    created_at TIMESTAMP
);

CREATE TABLE operation_outputs (
    workflow_uuid UUID,
    step_name VARCHAR(255),
    output JSONB,
    error TEXT,
    created_at TIMESTAMP
);

CREATE TABLE notifications (
    workflow_uuid UUID,
    topic VARCHAR(255),
    message JSONB,
    created_at TIMESTAMP
);
```

**Database**: Railway PostgreSQL (separate system DB)
- Database: `openclaw_gateway_dbos_sys`
- Connection: Same Railway instance as backend

**Configuration**:
```env
# openclaw-gateway/.env
PORT=18789
HOST=127.0.0.1
AUTH_TOKEN=openclaw-dev-token-12345

# PostgreSQL Connection
PGHOST=yamabiko.proxy.rlwy.net
PGPORT=51955
PGUSER=postgres
PGPASSWORD=***
PGDATABASE=railway

# CRITICAL: DBOS SDK SSL Configuration
# DBOS SDK reads from env vars, NOT dbos-config.yaml!
PGSSLMODE=disable              # For Railway self-signed certs
PGCONNECT_TIMEOUT=10
```

**Source Files** (TypeScript):
- `src/server.ts` - Express + WebSocket + DBOS initialization
- `src/workflows/agent-lifecycle-workflow.ts` - Agent provisioning, heartbeat, pause/resume
- `src/workflows/agent-message-workflow.ts` - Message routing with durability
- `tsconfig.json` - TypeScript build configuration

**Build Process**:
```bash
# Compile TypeScript to JavaScript
npm run build  # → dist/

# Start gateway
npm start  # → node dist/server.js
```

---

## Data Flow

### Agent Provisioning Flow

```
┌──────────┐   1. POST /api/v1/agents   ┌──────────┐
│ Frontend │─────────────────────────────▶│ Backend  │
│  3002    │                              │  8000    │
└──────────┘                              └────┬─────┘
                                               │
                                     2. Create DB record
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │  PostgreSQL    │
                                      │  (6432)        │
                                      │  - Agent row   │
                                      │  Status: PROV  │
                                      └────────────────┘
                                               │
                                     3. POST /workflows/provision-agent
                                               │
                                               ▼
                                      ┌────────────────┐
                                      │   Gateway      │
                                      │   18789        │
                                      │  @DBOS.workflow│
                                      └────┬───────────┘
                                           │
                            4. Durable workflow execution
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    │                      │                       │
                    ▼                      ▼                       ▼
              ┌──────────┐          ┌──────────┐           ┌──────────┐
              │ @Step()  │          │ @Step()  │           │ @Step()  │
              │ Validate │          │ Create   │           │ Provision│
              │          │          │ Session  │           │ in       │
              │          │          │          │           │ OpenClaw │
              └──────────┘          └──────────┘           └──────────┘
                    │                      │                       │
                    └──────────────────────┼───────────────────────┘
                                           │
                                           ▼
                                  ┌────────────────┐
                                  │  PostgreSQL    │
                                  │  - Workflow    │
                                  │    state saved │
                                  │  - Checkpoints │
                                  └────────────────┘
                                           │
                            5. Return result to Backend
                                           │
                                           ▼
┌──────────┐   6. Return agent details   ┌──────────┐
│ Frontend │◀─────────────────────────────│ Backend  │
│          │   Status: RUNNING            │          │
└──────────┘                              └──────────┘
```

**Key Points**:
- Each `@DBOS.step()` is atomic and recoverable
- Workflow state persisted in PostgreSQL after each step
- If gateway crashes, workflow resumes from last checkpoint
- Backend polls workflow status until completion

---

### Message Routing Flow

```
WhatsApp Message
      │
      ▼
┌────────────────┐
│  WhatsApp API  │
│  Webhook       │
└────────┬───────┘
         │
         ▼
┌────────────────┐    Parse command       ┌────────────────┐
│  Backend       │───────────────────────▶│ CommandParser  │
│  /whatsapp/msg │    (regex + Claude)    │ (Hybrid NL)    │
└────────┬───────┘                        └────────────────┘
         │
         │ Extracted: { action, issueId, repo }
         │
         ▼
┌────────────────┐    POST /messages      ┌────────────────┐
│  Backend       │────────────────────────▶│  Gateway       │
│  sends to      │    { from, to, msg }   │  WebSocket     │
│  agent         │                         │                │
└────────────────┘                        └────────┬───────┘
                                                   │
                                       Start routeAgentMessage workflow
                                                   │
                                  ┌────────────────┼────────────────┐
                                  ▼                ▼                ▼
                            ┌─────────┐     ┌─────────┐     ┌─────────┐
                            │@Step()  │     │@Step()  │     │@Step()  │
                            │Validate │     │Store in │     │Route to │
                            │Message  │     │DBOS DB  │     │Agent    │
                            └─────────┘     └─────────┘     └─────────┘
                                                   │
                                                   ▼
                                         ┌─────────────────┐
                                         │ Notifications   │
                                         │ Table (durable) │
                                         └─────────────────┘
```

**Durability Guarantees**:
- Message validated before storage
- Stored in `dbos_system.notifications` table
- Routing attempted with retry
- If gateway crashes mid-routing, workflow resumes on restart
- Guaranteed exactly-once delivery

---

## Technology Stack

### Frontend (agent-swarm-monitor)
- **Framework**: Next.js 14.0.4
- **UI Library**: React 18
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **State**: React Context API
- **WebSocket**: native WebSocket API

### Backend (openclaw-backend)
- **Framework**: FastAPI 0.109.0
- **Language**: Python 3.12
- **ORM**: SQLAlchemy 2.0
- **Migrations**: Alembic
- **HTTP Client**: httpx (async)
- **WebSocket**: websockets library
- **AI**: Anthropic Claude API (Haiku for NL parsing)
- **Auth**: PyJWT with Ed25519 signing
- **Networking**: WireGuard, libp2p (Go)
- **Serialization**: msgpack

### Gateway (openclaw-gateway)
- **Runtime**: Node.js 20
- **Language**: TypeScript 5.7.2
- **Framework**: Express 5.2.1
- **WebSocket**: ws 8.19.0
- **Durable Workflows**: DBOS SDK 4.9.11
- **Database Client**: pg 8.11.3
- **Dotenv**: dotenv 17.3.1

### Infrastructure
- **Database**: PostgreSQL 15 (Railway)
  - Port 6432 (PgBouncer - use this!)
  - Port 5432 (Direct - avoid, 100 connection limit)
- **Hosting**: Railway.app
- **VPN**: WireGuard hub-and-spoke
- **P2P Discovery**: libp2p Kademlia DHT (Go bootstrap node)

---

## Deployment Architecture

### Local Development

```
Developer Machine (macOS/Linux)
│
├─ Port 3002: Frontend (npm run dev)
│  └─ Connects to Backend at localhost:8000
│
├─ Port 8000: Backend (uvicorn with --reload)
│  ├─ Connects to Gateway at localhost:18789
│  └─ Connects to PostgreSQL at yamabiko.proxy.rlwy.net:6432
│
├─ Port 18789: Gateway (npm start)
│  └─ Connects to PostgreSQL at yamabiko.proxy.rlwy.net:51955
│
└─ Database: Railway PostgreSQL (remote)
   ├─ ainative_app (Backend)
   └─ openclaw_gateway_dbos_sys (Gateway)
```

### Production (Railway)

```
Railway Platform
│
├─ Service: AINative-Core-Production (Backend)
│  ├─ Public URL: ainative-browser-builder.up.railway.app
│  ├─ Port: 8080
│  ├─ Database: PostgreSQL (port 6432 via PgBouncer)
│  └─ Env: OPENCLAW_GATEWAY_URL, DATABASE_URL
│
├─ Service: openclaw-gateway (Gateway)
│  ├─ Public URL: TBD (to be deployed)
│  ├─ Port: 18789
│  ├─ Database: PostgreSQL (separate system DB)
│  └─ Env: PGHOST, PGPORT, PGSSLMODE=disable
│
└─ Database: PostgreSQL
   ├─ ainative_app (Backend data)
   └─ openclaw_gateway_dbos_sys (DBOS workflows)
```

**Kong Gateway**:
- Public API: `api.ainative.studio:8000`
- Routes traffic to Backend service
- Cannot access internal Railway DNS (uses public URL)

---

## Critical Configuration

### DBOS Gateway SSL Configuration (ZERO TOLERANCE)

**CRITICAL**: DBOS SDK reads PostgreSQL SSL config from **environment variables**, NOT from `dbos-config.yaml`.

**Required in `openclaw-gateway/.env`**:
```env
PGSSLMODE=disable              # For Railway self-signed certificates
PGCONNECT_TIMEOUT=10
```

**Common Error**:
```
DBOSInitializationError: Unable to connect to system database
self-signed certificate in certificate chain: (SELF_SIGNED_CERT_IN_CHAIN)
```

**Solution**: Add `PGSSLMODE=disable` to `.env`

**Why `dbos-config.yaml` SSL settings don't work**:
DBOS SDK source code (`node_modules/@dbos-inc/dbos-sdk/dist/src/config.js:99`):
```javascript
const sslmode = process.env.PGSSLMODE || (host === 'localhost' ? 'disable' : 'allow');
dbUrl.searchParams.set('sslmode', sslmode);
```

The SDK **ignores** these fields in `dbos-config.yaml`:
- `ssl_ca`
- `ssl_cert`
- `ssl_key`
- `ssl_accept_unauthorized`

**Reference**: `docs/DBOS_GATEWAY_SETUP_IMPROVEMENTS.md`

---

### Port Configuration

**Local Ports**:
- Frontend: `3002` (configurable via `PORT` env var)
- Backend: `8000` (standard for FastAPI)
- Gateway: `18789` (MUST match `OPENCLAW_GATEWAY_URL` in backend)

**Port Conflict Resolution**:
The `scripts/start-all-local.sh` script includes smart port conflict handling with 4 modes:
- `ask` (default) - Interactive prompts
- `kill` - Auto-kill conflicting processes
- `reassign` - Use alternative ports
- `error` - Fail on conflicts

---

### Database Connection Strings

**Backend** (FastAPI):
```
postgresql://postgres:***@yamabiko.proxy.rlwy.net:6432/ainative_app
                                                   ^^^^
                                                   Use PgBouncer port!
```

**Gateway** (DBOS):
```
PGHOST=yamabiko.proxy.rlwy.net
PGPORT=51955                    # Direct connection (DBOS requirement)
PGDATABASE=railway
PGSSLMODE=disable               # CRITICAL for Railway
```

**Note**: Gateway uses different port (51955) because DBOS creates its own system database.

---

## Development Workflow

### Starting All Services

**Recommended** (one command):
```bash
scripts/start-all-local.sh
```

**Manual** (three terminals):

**Terminal 1 - Gateway**:
```bash
cd openclaw-gateway/
npm run build  # Compile TypeScript
npm start      # Start on port 18789
```

**Terminal 2 - Backend**:
```bash
export SECRET_KEY="dev-secret-key"
export OPENCLAW_GATEWAY_URL="http://localhost:18789"
export DATABASE_URL="sqlite:///./openclaw.db"  # Or PostgreSQL URL
python3 -m uvicorn backend.main:app --reload --port 8000
```

**Terminal 3 - Frontend**:
```bash
cd ../agent-swarm-monitor/
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env
npm run dev
```

**Verification**:
```bash
curl http://localhost:18789/health  # Gateway
curl http://localhost:8000/health   # Backend
open http://localhost:3002          # Frontend
```

---

## Security Considerations

1. **API Keys**: Never commit `.env` files with real credentials
2. **JWT Signing**: Backend requires `SECRET_KEY` for task lease tokens
3. **WireGuard**: Private keys must be secured
4. **DBOS Auth**: Gateway `AUTH_TOKEN` for backend-gateway communication
5. **Ed25519 Signing**: P2P message signing for task distribution
6. **CORS**: Backend allows frontend origin (localhost:3002 in dev)

---

## Monitoring & Observability

### Health Checks
- Gateway: `GET /health` → `{"status":"healthy","dbos":"connected"}`
- Backend: `GET /health` → `{"status":"ok"}`
- Frontend: HTTP 200 on root path

### Metrics (Prometheus)
- Backend exports metrics at `GET /api/v1/metrics`
- 15 counters (task_assigned, lease_issued, lease_expired, etc.)
- 4 gauges (active_leases, buffer_size, buffer_utilization, partition_degraded)
- 1 histogram (recovery_duration_seconds)

### Swarm Health
- `GET /api/v1/swarm/health` - Overall swarm status
- `GET /api/v1/swarm/timeline` - Task execution events
- `GET /api/v1/swarm/alerts/thresholds` - Alert configuration

### DBOS Workflow Monitoring
- Gateway stores workflow status in `dbos_system.workflow_status`
- Backend polls via `DBOSWorkflowMonitor`
- Check workflow: `GET /workflows/{uuid}`

---

## Troubleshooting

### Gateway Won't Start

**Error**: `SELF_SIGNED_CERT_IN_CHAIN`
**Solution**: Add `PGSSLMODE=disable` to `openclaw-gateway/.env`

**Error**: `Named export 'Step' not found`
**Solution**: Run `npm run build` to compile TypeScript source

### Backend Can't Connect to Gateway

**Check**:
```bash
curl http://localhost:18789/health
```

**If fails**:
1. Verify gateway is running: `lsof -i :18789`
2. Check `OPENCLAW_GATEWAY_URL` in backend .env
3. Check `AUTH_TOKEN` matches between services

### Frontend Shows "Failed to fetch"

**Check**:
```bash
curl http://localhost:8000/health
cat ../agent-swarm-monitor/.env  # Should have API_URL=http://localhost:8000
```

### Database Connection Pool Exhausted

**Error**: `QueuePool limit of size X reached`
**Solution**: Backend already configured with pool_size=20 (10 base + 10 overflow)
**Verify**: Check `backend/db/session.py`

---

## References

- **DBOS Documentation**: https://docs.dbos.dev/typescript/
- **Gateway Source**: `openclaw-gateway/src/`
- **DBOS SSL Fix**: `docs/DBOS_GATEWAY_SETUP_IMPROVEMENTS.md`
- **Integration Guide**: `docs/DBOS_WORKFLOW_INTEGRATION.md`
- **OpenClaw Analysis**: `docs/integration/OPENCLAW_INTEGRATION_COMPLETE_ANALYSIS.md`
- **CLAUDE.md**: Project instructions with tech stack and data models

---

**Status**: ✅ All three services operational with TypeScript source and DBOS SSL configuration documented.
