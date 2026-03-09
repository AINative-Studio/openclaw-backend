# OpenClaw Startup Guide

## ⚠️ CRITICAL INFORMATION - READ FIRST

### Project Locations

**FRONTEND IS NOT IN THIS REPO!**

```
Backend:  /Users/aideveloper/openclaw-backend
Gateway:  /Users/aideveloper/openclaw-backend/openclaw-gateway
Frontend: /Users/aideveloper/agent-swarm-monitor  ← OUTSIDE BACKEND REPO
```

### Database Configuration

**All services use Railway PostgreSQL Cloud Database:**

```env
Host: yamabiko.proxy.rlwy.net
Port: 51955
Database: railway
SSL Mode: disable (self-signed cert)
```

## Full Stack Restart Commands

### 1. Kill All Processes

**⚠️ CRITICAL**: Stop Docker ZeroDB container first (it occupies port 8000):
```bash
docker stop zerodb-api
```

Then kill local processes:
```bash
pkill -f "uvicorn" && pkill -f "node dist/server.js" && pkill -f "next-server"
```

### 2. Start Backend (Port 8000)
```bash
cd /Users/aideveloper/openclaw-backend
source venv/bin/activate
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

### 3. Start Gateway (Port 18789)
```bash
cd /Users/aideveloper/openclaw-backend/openclaw-gateway
npm run dev
```

### 4. Start Frontend (Port 3002)
```bash
cd /Users/aideveloper/agent-swarm-monitor
npm run dev
```
**Note**: The frontend runs on port **3002**, NOT 3000 (port 3000 is ZeroDB Local UI)

### 5. Verify All Services
```bash
# Backend
curl http://localhost:8000/health

# Gateway
curl http://localhost:18789/health

# Frontend (OpenClaw UI)
curl http://localhost:3002

# ZeroDB Local UI (optional)
curl http://localhost:3000
```

## Important Configuration

### Gateway DBOS (.env requirements)
```env
PGHOST=yamabiko.proxy.rlwy.net
PGPORT=51955
PGUSER=postgres
PGPASSWORD=<railway-password>
PGDATABASE=railway
PGSSLMODE=disable              # CRITICAL - don't remove!
PGCONNECT_TIMEOUT=10
ANTHROPIC_API_KEY=sk-ant-api03-...
```

### Chat Workflow Model
```
claude-sonnet-4-5-20250929
```

## Troubleshooting

### Gateway won't start
- Check `PGSSLMODE=disable` in `.env`
- Verify PostgreSQL credentials in `.env`
- Check `dist/workflows/chat-workflow.js` is in `dbos-config.yaml` entrypoints

### Frontend won't load agents / shows no data
- **MOST COMMON**: Docker ZeroDB container is using port 8000
  ```bash
  docker ps | grep 8000
  docker stop zerodb-api
  ```
- Verify OpenClaw Backend is running (not ZeroDB):
  ```bash
  curl http://localhost:8000/api/v1/swarms
  # Should return: {"swarms":[],"total":0,...}
  # NOT: ZeroDB endpoints
  ```
- Check Backend health endpoint returns PostgreSQL healthy
- Restart all 3 services in order: Backend → Gateway → Frontend

### Chat returns 404
- Verify model name is `claude-sonnet-4-5-20250929`
- Check ANTHROPIC_API_KEY is set in Gateway `.env`
- Check Gateway logs for "knexClient not available" (should be warning, not error)

## Service Dependencies

```
Frontend (3002) - OpenClaw UI
    ↓
Backend (8000) ← Gateway (18789)
    ↓               ↓
Railway PostgreSQL (51955)

Optional:
Frontend (3000) - ZeroDB Local UI
```

## Phase 2 Status (DBOS Chat Integration)

✅ **COMPLETED** - All features working:
- User/Assistant message handling (graceful PostgreSQL degradation)
- Personality context loading (404 graceful fallback)
- Memory context loading (error graceful fallback)
- Claude API integration (Sonnet 4.5)
- DBOS durable workflow execution
- 19/19 integration tests passing

**Known Issues:**
- knexClient not exposed by DBOS SDK → graceful degradation implemented
- ZeroDB auth failing (404) → non-blocking, memory features disabled
- PostgreSQL message storage skipped → messages only stored in DBOS system tables
