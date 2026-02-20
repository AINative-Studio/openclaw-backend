# OpenClaw Backend

DBOS-powered durable workflows for AI agent lifecycle management.

## Overview

This repository contains the backend infrastructure for the OpenClaw Gateway and AgentSwarm system, providing crash-recoverable AI agent lifecycle management with WhatsApp integration.

## Components

### OpenClaw Gateway (Node.js/TypeScript)
- **Path:** `openclaw-gateway/`
- **Technology:** Express.js + WebSocket + DBOS SDK
- **Port:** 18789
- **Purpose:** DBOS runtime for durable workflow execution

**Features:**
- Durable agent provisioning workflows
- Crash-recoverable message routing
- State persistence in PostgreSQL
- WebSocket-based real-time communication

### Backend Services (Python/FastAPI)
- **Path:** `backend/`
- **Components:**
  - `agents/orchestration/` - OpenClaw bridge, orchestrator, command parser
  - `services/` - DBOS workflow monitor, lifecycle service
  - `models/` - Agent lifecycle database models
  - `api/v1/endpoints/` - REST API endpoints

### Integrations
- **Path:** `integrations/`
- OpenClaw bridge client
- Routing monitor
- WhatsApp notifier

## Quick Start

### OpenClaw Gateway
```bash
cd openclaw-gateway
npm install
npm run build
npm start  # Runs on port 18789
```

### Backend Services
Integrate into your FastAPI application:
```python
from backend.services.dbos_workflow_monitor import DBOSWorkflowMonitor
from backend.services.agent_swarm_lifecycle_service import AgentSwarmLifecycleService
```

## Architecture

```
OpenClaw Backend Architecture:

┌─────────────────────────────────────┐
│   OpenClaw Gateway (Node.js/DBOS)  │
│   - Durable workflows               │
│   - WebSocket server (port 18789)  │
│   - Crash recovery                  │
└──────────────┬──────────────────────┘
               │
               ↓
┌─────────────────────────────────────┐
│   FastAPI Backend Services          │
│   - Lifecycle orchestration         │
│   - DBOS workflow monitoring        │
│   - Command parsing                 │
└──────────────┬──────────────────────┘
               │
               ↓
┌─────────────────────────────────────┐
│   PostgreSQL (Railway, port 6432)  │
│   - DBOS system tables              │
│   - Agent lifecycle state           │
│   - Workflow execution tracking     │
└─────────────────────────────────────┘
```

## DBOS Features

- **Durable Workflows:** All agent operations survive crashes
- **Automatic Recovery:** Workflows resume from last checkpoint
- **State Persistence:** PostgreSQL-backed workflow state
- **Health Monitoring:** Continuous workflow health checks
- **Message Durability:** Guaranteed message delivery

## Database Configuration

**Railway PostgreSQL:**
- Port: 6432 (PgBouncer)
- App DB: `ainative_app`
- System DB: `dbos_system`
- Connection pool: 20 connections per instance

## API Endpoints

```
POST   /api/v1/agents/provision          - Create durable agent
POST   /api/v1/agents/{id}/heartbeat     - Execute durable heartbeat
POST   /api/v1/agents/{id}/pause         - Pause with state preservation
POST   /api/v1/agents/{id}/resume        - Resume from checkpoint
GET    /api/v1/openclaw/status           - Gateway connection status
```

## Documentation

- **Integration Guides:** `docs/integration/`
- **Verification Reports:** `docs/verification/`
- **Implementation Reports:** `docs/reports/`
- **Agent Swarm Docs:** `docs/agent-swarm/`

## Testing

```bash
cd tests
python -m pytest test_agent_swarm_lifecycle_with_dbos.py -v
python -m pytest test_agentclaw_e2e.py -v
```

## Environment Variables

**OpenClaw Gateway:**
```
PORT=18789
HOST=127.0.0.1
AUTH_TOKEN=your-token
LOG_LEVEL=info
HEALTH_CHECK_INTERVAL=30000
```

**Backend Services:**
```
DATABASE_URL=postgresql://user:pass@host:6432/ainative_app
OPENCLAW_GATEWAY_URL=ws://127.0.0.1:18789
```

## Related Repositories

- **Frontend Dashboard:** [agent-swarm-monitor](https://github.com/AINative-Studio/agent-swarm-monitor)
- **Core AINative:** [core](https://github.com/AINative-Studio/core)

## License

MIT

## Issues & Support

Report issues at: https://github.com/AINative-Studio/openclaw-backend/issues
