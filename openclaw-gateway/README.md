# OpenClaw Gateway - DBOS Phase 1

WebSocket gateway for agent orchestration with DBOS durable workflows.

## Status

**Issue:** #1216  
**Phase:** 1 - Setup & Configuration  
**Implementation:** Complete

## Overview

OpenClaw Gateway provides durable workflow execution for agent message routing using DBOS (Database-Oriented Operating System). All workflows are persisted in PostgreSQL and automatically recover from crashes.

## Quick Start

See full documentation: `/Users/aideveloper/core/docs/guides/DBOS_PHASE1_OPENCLAW_GATEWAY.md`

### Installation

```bash
cd packages/openclaw-gateway
npm install
```

### Configuration

1. Copy `.env.example` to `.env`
2. Configure Railway PostgreSQL credentials (use port 6432)
3. Run database migration:
   ```bash
   npm run dbos:migrate
   ```

### Running

```bash
# Development
npm run dev

# Production
npm run build && npm start
```

## Architecture

```
WebSocket/HTTP Clients
         ↓
OpenClaw Gateway (Express + WS)
         ↓
DBOS Runtime (Workflows)
         ↓
PostgreSQL (Railway - Port 6432)
```

## Key Features

- **Durable Workflows**: All agent message routing workflows survive crashes
- **Automatic Recovery**: Workflows resume from last checkpoint on restart
- **Connection Pooling**: Optimized for Railway PostgreSQL (max 20 connections)
- **WebSocket Support**: Real-time bidirectional communication
- **HTTP API**: REST endpoints for workflow management

## Implementation Files

- `src/workflows/agent-message-workflow.ts` - Core durable workflow
- `src/dbos/migrate.ts` - Database schema migration
- `src/server.ts` - Main gateway server
- `tests/workflows/` - Workflow durability tests

## Database Schema

DBOS creates the following tables in `dbos_system` schema:
- `workflow_status` - Workflow execution tracking
- `workflow_events` - Event log for debugging
- `operation_outputs` - Step outputs and errors  
- `notifications` - Agent messages

## Testing

```bash
npm test                # Run all tests
npm run test:coverage   # Run with coverage
```

## Documentation

See `/Users/aideveloper/core/docs/guides/DBOS_PHASE1_OPENCLAW_GATEWAY.md` for:
- Complete setup instructions
- API endpoint documentation
- Workflow durability examples
- Troubleshooting guide
- Next phase roadmap

## References

- [DBOS Documentation](https://docs.dbos.dev/typescript/)
- [Issue #1216](https://github.com/AINative-Studio/core/issues/1216)

Refs #1216
