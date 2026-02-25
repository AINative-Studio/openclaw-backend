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
        echo "   Run: lsof -ti :18789 | xargs kill"
        exit 1
    fi

    echo "   Starting gateway in background..."
    cd openclaw-gateway/
    npm start > /tmp/openclaw-gateway.log 2>&1 &
    GATEWAY_PID=$!
    cd ..

    # Wait for gateway to be ready
    echo "   Waiting for gateway to start..."
    for i in {1..30}; do
        if curl -s http://localhost:18789/health > /dev/null 2>&1; then
            echo -e "   ${GREEN}✅ Started (PID: $GATEWAY_PID)${NC}"
            break
        fi
        sleep 1
    done

    if ! curl -s http://localhost:18789/health > /dev/null 2>&1; then
        echo -e "   ${RED}❌ Gateway failed to start. Check logs: tail -f /tmp/openclaw-gateway.log${NC}"
        exit 1
    fi
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
        echo "   Run: lsof -ti :8000 | xargs kill"
        exit 1
    fi

    echo "   Starting backend in background..."
    python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000 > /tmp/openclaw-backend.log 2>&1 &
    BACKEND_PID=$!

    # Wait for backend to be ready
    echo "   Waiting for backend to start (this includes agent initialization)..."
    for i in {1..30}; do
        if curl -s http://localhost:8000/health > /dev/null 2>&1; then
            echo -e "   ${GREEN}✅ Started (PID: $BACKEND_PID)${NC}"
            break
        fi
        sleep 1
    done

    if ! curl -s http://localhost:8000/health > /dev/null 2>&1; then
        echo -e "   ${RED}❌ Backend failed to start. Check logs: tail -f /tmp/openclaw-backend.log${NC}"
        exit 1
    fi

    # Check agent initialization status from logs
    sleep 2
    if grep -q "✅ Agent initialization" /tmp/openclaw-backend.log 2>/dev/null; then
        INIT_STATUS=$(grep "Agent initialization" /tmp/openclaw-backend.log | tail -1 | grep -o "created\|provisioned\|already_exists" || echo "unknown")
        echo -e "   ${GREEN}✅ Main Agent: $INIT_STATUS${NC}"
    fi
fi
echo ""

# 4. Check/Setup Frontend
echo "4️⃣  Frontend Dashboard (port 3002)"
if [ ! -d "../agent-swarm-monitor" ]; then
    echo -e "   ${RED}❌ Frontend directory not found at ../agent-swarm-monitor/${NC}"
    echo "   Skipping frontend startup"
else
    cd ../agent-swarm-monitor/

    # Install dependencies if needed
    if [ ! -d "node_modules" ]; then
        echo "   Installing frontend dependencies..."
        npm install
    fi

    # Create .env if it doesn't exist
    if [ ! -f .env ]; then
        echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env
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
fi
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
echo "🔍 Verify agents:"
echo "   curl http://localhost:8000/api/v1/agents?limit=50 | python3 -m json.tool"
echo ""
echo "🛑 To stop all services:"
echo "   ./stop-all-local.sh"
echo ""
echo "🌐 Opening frontend in browser..."
sleep 2
open http://localhost:3002 2>/dev/null || echo "   Open manually: http://localhost:3002"
