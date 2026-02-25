# Local Startup Skill

**USE THIS SKILL** when starting the complete OpenClaw system locally or when the user requests to run the system locally.

## Overview

This skill ensures all prerequisites are met before starting the complete OpenClaw stack locally:
1. **OpenClaw Gateway** (Node.js WebSocket server on port 18789)
2. **Backend API** (FastAPI server on port 8000)
3. **Frontend Dashboard** (Next.js app on port 3002)

All three services must be running for the full system to work.

## Prerequisites Checklist

### 1. OpenClaw Gateway

**CRITICAL**: The backend depends on the OpenClaw Gateway (Node.js WebSocket server) running on port 18789.

**Check Steps**:
```bash
# Check if gateway is running
curl -s http://localhost:18789/health || echo "Gateway not running"

# Check if port 18789 is in use
lsof -i :18789 || netstat -an | grep 18789
```

**If Not Running**:
- Navigate to `openclaw-gateway/` directory
- Check if `node_modules` exists, if not run: `npm install`
- Start gateway: `npm start` or `node dist/index.js`
- Verify: `curl http://localhost:18789/health`

### 2. Python Virtual Environment

**Check Steps**:
```bash
# Check if venv exists
ls -la venv/ || ls -la .venv/

# Check if activated (should see venv in prompt or)
python -c "import sys; print('Virtual env active' if hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix) else 'Not in venv')"
```

**If Not Setup**:
```bash
# Create virtual environment
python3 -m venv venv

# Activate it
source venv/bin/activate  # On macOS/Linux
# or
venv\Scripts\activate  # On Windows

# Install dependencies
pip install -r requirements.txt
```

### 3. Database Connectivity

**For Local Development** (SQLite - default):
- No setup required, SQLite database will be created automatically at `./openclaw.db`

**For PostgreSQL** (Railway production):
- Set `DATABASE_URL` environment variable
- Test connection:
```bash
python -c "from backend.db.base import engine; engine.connect(); print('Database connected successfully')"
```

### 4. Required Environment Variables

**Minimum Required**:
- `SECRET_KEY` - For JWT signing (TaskLeaseIssuanceService)
- `OPENCLAW_GATEWAY_URL` - Default: `http://localhost:18789`
- `OPENCLAW_GATEWAY_TOKEN` - Default: `openclaw-dev-token-12345`

**Optional**:
- `DATABASE_URL` - Defaults to `sqlite:///./openclaw.db`
- `ENVIRONMENT` - Set to `development` for local
- `ANTHROPIC_API_KEY` - For NL command parsing fallback
- `DD_LLMOBS_ENABLED` - Set to `1` to enable Datadog tracing

**Setup**:
```bash
# Create .env file in project root
cat > .env << EOF
SECRET_KEY=your-secret-key-here-change-in-production
OPENCLAW_GATEWAY_URL=http://localhost:18789
OPENCLAW_GATEWAY_TOKEN=openclaw-dev-token-12345
ENVIRONMENT=development
DATABASE_URL=sqlite:///./openclaw.db
EOF

# Or export directly
export SECRET_KEY="your-secret-key-here"
export OPENCLAW_GATEWAY_URL="http://localhost:18789"
export OPENCLAW_GATEWAY_TOKEN="openclaw-dev-token-12345"
export ENVIRONMENT="development"
```

### 5. WireGuard (Optional for local dev)

WireGuard is used for secure agent-to-agent communication but is **NOT required** for basic local backend startup.

**Skip for local development** unless testing WireGuard provisioning endpoints.

### 6. Frontend Dashboard (agent-swarm-monitor)

**Location**: `../agent-swarm-monitor/` (parent directory)

**Prerequisites**:
- Node.js and npm installed
- Backend API running on port 8000

**Check Steps**:
```bash
# Check if frontend directory exists
ls -la ../agent-swarm-monitor/

# Check if node_modules exists
ls ../agent-swarm-monitor/node_modules/ || echo "Need to run npm install"
```

**Setup**:
```bash
# Navigate to frontend
cd ../agent-swarm-monitor/

# Install dependencies (if not already installed)
npm install

# Create .env file if it doesn't exist
if [ ! -f .env ]; then
  echo "API_URL=http://localhost:8000" > .env
fi

# Return to backend directory
cd ../openclaw-backend/
```

## Startup Commands

### Complete 3-Service Startup (Recommended)

**Terminal 1 - OpenClaw Gateway**:
```bash
cd openclaw-gateway/
npm start
# Verify: curl http://localhost:18789/health
```

**Terminal 2 - Backend API**:
```bash
# From project root (openclaw-backend/)
export SECRET_KEY="dev-secret-key-for-local-testing"
export OPENCLAW_GATEWAY_URL="http://localhost:18789"
export OPENCLAW_GATEWAY_TOKEN="openclaw-dev-token-12345"
export ENVIRONMENT="development"
export DATABASE_URL="sqlite:///./openclaw.db"

python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
# Verify: curl http://localhost:8000/health
```

**Terminal 3 - Frontend Dashboard**:
```bash
cd ../agent-swarm-monitor/
npm run dev
# Access: http://localhost:3002
```

### Backend Only (No Frontend)

Once all prerequisites are verified:

```bash
# Make sure you're in the project root and venv is activated
source venv/bin/activate

# Start the backend with uvicorn
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000

# Or with specific log level
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 --log-level debug
```

**Verify All Services Running**:
```bash
# Gateway
curl http://localhost:18789/health

# Backend
curl http://localhost:8000/health
# Should return: {"status":"ok"}

# Frontend (open in browser)
open http://localhost:3002
# Or: curl http://localhost:3002

# API Documentation
open http://localhost:8000/docs
```

## Common Issues

### 1. Port Already in Use
```bash
# Find process using port 8000
lsof -i :8000
# Kill it
kill -9 <PID>
```

### 2. Import Errors
```bash
# Reinstall dependencies
pip install -r requirements.txt --upgrade

# Check Python path
python -c "import sys; print(sys.path)"
```

### 3. Database Migration Issues
```bash
# For SQLite, just delete and recreate
rm openclaw.db

# For PostgreSQL, run migrations
alembic upgrade head
```

### 4. Gateway Connection Failed
- Verify gateway is running: `curl http://localhost:18789/health`
- Check `OPENCLAW_GATEWAY_URL` in environment matches gateway host/port
- Check `OPENCLAW_GATEWAY_TOKEN` matches the token in `openclaw-gateway/.env`

### 5. Frontend Not Loading
```bash
# Check if frontend port is available
lsof -i :3002

# Check if backend is reachable from frontend
cd ../agent-swarm-monitor/
cat .env  # Should have API_URL=http://localhost:8000

# Check for npm errors
npm run dev  # Look for error messages
```

### 6. Frontend Shows "Failed to fetch" Errors
- Verify backend is running: `curl http://localhost:8000/health`
- Check `.env` in agent-swarm-monitor has correct `API_URL`
- Check CORS is enabled in backend (it should be by default)
- Try clearing browser cache / hard refresh (Cmd+Shift+R)

## Automated Startup Script (Recommended)

### Complete System Startup (All 3 Services)

Create a `start-all-local.sh` script in the backend directory:

```bash
#!/bin/bash
# start-all-local.sh - Start complete OpenClaw stack (Gateway + Backend + Frontend)

set -e

echo "🚀 OpenClaw Complete Stack Startup"
echo "===================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if port is in use
check_port() {
    lsof -i :$1 > /dev/null 2>&1
}

# 1. Check/Start Gateway
echo "1️⃣  OpenClaw Gateway (port 18789)"
if curl -s http://localhost:18789/health > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Already running${NC}"
else
    if check_port 18789; then
        echo -e "   ${RED}❌ Port in use by another process${NC}"
        exit 1
    fi

    echo "   Starting gateway in background..."
    cd openclaw-gateway/
    npm start > /tmp/openclaw-gateway.log 2>&1 &
    GATEWAY_PID=$!
    cd ..

    # Wait for gateway to be ready
    for i in {1..30}; do
        if curl -s http://localhost:18789/health > /dev/null 2>&1; then
            echo -e "   ${GREEN}✅ Started (PID: $GATEWAY_PID)${NC}"
            break
        fi
        sleep 1
    done
fi
echo ""

# 2. Setup and check Python environment
echo "2️⃣  Backend API Environment"
if python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo -e "   ${GREEN}✅ Python dependencies installed${NC}"
else
    echo "   Installing dependencies..."
    pip3 install -r requirements.txt
fi

# Set environment variables
export SECRET_KEY="dev-secret-key-for-local-testing"
export OPENCLAW_GATEWAY_URL="http://localhost:18789"
export OPENCLAW_GATEWAY_TOKEN="openclaw-dev-token-12345"
export ENVIRONMENT="development"
export DATABASE_URL="sqlite:///./openclaw.db"
echo -e "   ${GREEN}✅ Environment configured${NC}"
echo ""

# 3. Start Backend
echo "3️⃣  Backend API (port 8000)"
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Already running${NC}"
else
    if check_port 8000; then
        echo -e "   ${RED}❌ Port in use by another process${NC}"
        exit 1
    fi

    echo "   Starting backend in background..."
    python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 > /tmp/openclaw-backend.log 2>&1 &
    BACKEND_PID=$!

    # Wait for backend to be ready
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            echo -e "   ${GREEN}✅ Started (PID: $BACKEND_PID)${NC}"
            break
        fi
        sleep 1
    done
fi
echo ""

# 4. Check/Setup Frontend
echo "4️⃣  Frontend Dashboard (port 3002)"
if [ ! -d "../agent-swarm-monitor" ]; then
    echo -e "   ${RED}❌ Frontend directory not found at ../agent-swarm-monitor/${NC}"
    exit 1
fi

cd ../agent-swarm-monitor/

# Install dependencies if needed
if [ ! -d "node_modules" ]; then
    echo "   Installing frontend dependencies..."
    npm install
fi

# Create .env if it doesn't exist
if [ ! -f .env ]; then
    echo "API_URL=http://localhost:8000" > .env
    echo "   Created .env file"
fi

# Start frontend
if check_port 3002; then
    echo -e "   ${GREEN}✅ Already running${NC}"
else
    echo "   Starting frontend in background..."
    npm run dev > /tmp/openclaw-frontend.log 2>&1 &
    FRONTEND_PID=$!

    # Wait for frontend to be ready
    sleep 5
    echo -e "   ${GREEN}✅ Started (PID: $FRONTEND_PID)${NC}"
fi

cd ../openclaw-backend/
echo ""

# Summary
echo "======================================"
echo -e "${GREEN}✅ All services started!${NC}"
echo ""
echo "📍 Service URLs:"
echo "   Gateway:  http://localhost:18789"
echo "   Backend:  http://localhost:8000"
echo "   Frontend: http://localhost:3002"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "📋 Logs:"
echo "   Gateway:  tail -f /tmp/openclaw-gateway.log"
echo "   Backend:  tail -f /tmp/openclaw-backend.log"
echo "   Frontend: tail -f /tmp/openclaw-frontend.log"
echo ""
echo "🛑 To stop all services:"
echo "   kill $GATEWAY_PID $BACKEND_PID $FRONTEND_PID"
echo "   Or run: scripts/stop-all-local.sh"
echo ""
echo "🌐 Opening frontend in browser..."
sleep 2
open http://localhost:3002
```

Create a companion `stop-all-local.sh` script:

```bash
#!/bin/bash
# stop-all-local.sh - Stop all OpenClaw services

echo "🛑 Stopping OpenClaw services..."

# Stop processes on specific ports
for port in 18789 8000 3002; do
    PID=$(lsof -ti :$port 2>/dev/null)
    if [ ! -z "$PID" ]; then
        echo "   Stopping service on port $port (PID: $PID)"
        kill $PID 2>/dev/null || kill -9 $PID 2>/dev/null
    fi
done

echo "✅ All services stopped"

# Clean up log files
rm -f /tmp/openclaw-*.log
```

Make both scripts executable:
```bash
chmod +x scripts/start-all-local.sh scripts/stop-all-local.sh
```

## Testing the Setup

After all services start, run comprehensive health checks:

```bash
# 1. Gateway health
curl http://localhost:18789/health

# 2. Backend health
curl http://localhost:8000/health
# Should return: {"status":"ok"}

# 3. Frontend (open in browser)
open http://localhost:3002
# Should load the AgentClaw dashboard

# 4. Backend API Documentation
open http://localhost:8000/docs
# Should show Swagger UI

# 5. Check specific backend endpoints
curl http://localhost:8000/api/v1/swarm/health | python3 -m json.tool
curl http://localhost:8000/api/v1/metrics | head -20
curl http://localhost:8000/api/v1/wireguard/health
```

### Expected Results

**Gateway** (port 18789):
- HTML response or web UI

**Backend** (port 8000):
- `/health` returns `{"status":"ok"}`
- `/docs` shows Swagger UI with all API endpoints
- `/api/v1/swarm/health` returns health status JSON
- `/api/v1/metrics` returns Prometheus metrics

**Frontend** (port 3002):
- Loads AgentClaw dashboard UI
- Shows navigation sidebar
- Displays agent list (may be empty or show mock data)
- No "Failed to fetch" errors in browser console

## Automatic Agent Initialization

**NEW**: The backend now automatically initializes and provisions default agents on startup!

### What Happens Automatically

When the backend starts, the `AgentInitializationService` runs and:

1. **Checks for Main Agent** - Looks for an agent named "Main Agent"
2. **Creates if Missing** - If no Main Agent exists, creates one with:
   - Name: "Main Agent"
   - Model: Claude 3 Haiku (cheapest model for cost efficiency)
   - Status: Automatically provisioned to "running"
   - Persona: Configured to manage the AINative agent swarm via WhatsApp
3. **Auto-Provisions if Stuck** - If Main Agent exists but is in "provisioning" status, automatically transitions it to "running"
4. **Skips if Ready** - If Main Agent already exists and is "running", no action taken

### Verification

Check the agent initialization status in backend logs:

```bash
# Watch for initialization message in logs
tail -f /tmp/openclaw-backend.log | grep "Agent initialization"

# Expected output:
# ✅ Agent initialization: created (first time)
# ✅ Agent initialization: provisioned (agent was stuck)
# ✅ Agent initialization: already_exists (agent ready)
```

Verify Main Agent is in the database:

```bash
curl http://localhost:8000/api/v1/agents?limit=50 | python3 -m json.tool | grep -A 5 "Main Agent"
```

Expected response:
```json
{
    "name": "Main Agent",
    "model": "anthropic/claude-3-haiku-20240307",
    "status": "running",
    ...
}
```

### Benefits for New Employees

When a new employee sets up the system:
1. Runs `scripts/start-all-local.sh`
2. Backend starts and automatically creates Main Agent
3. Opens UI and sees Main Agent already configured and running
4. **No manual setup required** - fully employee-ready out of the box!

### Configuration

Default Main Agent configuration (in `backend/services/agent_initialization_service.py`):

```python
DEFAULT_MAIN_AGENT = {
    "name": "Main Agent",
    "persona": "You are the main AI assistant that manages the AINative agent swarm platform via WhatsApp...",
    "model": "anthropic/claude-3-haiku-20240307",  # Cheapest model
    "openclaw_session_key": "agent:main:main",
    "heartbeat_enabled": False,
}
```

## ZERO TOLERANCE Rules

1. **NEVER** start the backend without verifying OpenClaw Gateway is running first
2. **NEVER** start the frontend without verifying the backend is running
3. **NEVER** commit `.env` files with real credentials to git
4. **ALWAYS** ensure all three services are running for complete functionality
5. **ALWAYS** set `ENVIRONMENT=development` for local development
6. **ALWAYS** verify `SECRET_KEY` is set (even if just a dev key)
7. **ALWAYS** check that frontend `.env` has correct `API_URL=http://localhost:8000`

## Integration with Other Skills

- Use `/database-schema-sync` skill when database schema changes are needed
- Use `/mandatory-tdd` skill when running tests during development
- Use `/file-placement` skill when creating new documentation or scripts
