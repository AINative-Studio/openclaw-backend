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
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Port conflict resolution mode (can be overridden via env var)
# Options: "kill", "reassign", "ask", "error"
PORT_CONFLICT_MODE="${OPENCLAW_PORT_CONFLICT_MODE:-ask}"

# Function to check if port is in use
check_port() {
    lsof -i :$1 > /dev/null 2>&1
}

# Function to kill process on specific port
kill_port() {
    local port=$1
    local pids=$(lsof -ti :$port 2>/dev/null)

    if [ ! -z "$pids" ]; then
        echo -e "   ${YELLOW}⚠️  Killing process on port $port (PIDs: $pids)${NC}"
        echo "$pids" | xargs kill -9 2>/dev/null || true
        sleep 1
        return 0
    fi
    return 1
}

# Function to find next available port starting from base
find_free_port() {
    local base_port=$1
    local port=$base_port
    local max_attempts=100

    while check_port $port && [ $max_attempts -gt 0 ]; do
        port=$((port + 1))
        max_attempts=$((max_attempts - 1))
    done

    if [ $max_attempts -eq 0 ]; then
        echo -e "   ${RED}❌ Could not find free port after $base_port${NC}" >&2
        return 1
    fi

    echo $port
}

# Function to handle port conflict with smart resolution
resolve_port_conflict() {
    local service_name=$1
    local required_port=$2
    local allow_reassign=${3:-true}  # Whether this service supports port reassignment

    if ! check_port $required_port; then
        # Port is free, no conflict
        echo $required_port
        return 0
    fi

    # Port is in use - get process info
    local process_info=$(lsof -i :$required_port 2>/dev/null | tail -n +2 | head -1)
    echo -e "   ${YELLOW}⚠️  Port $required_port is in use${NC}" >&2
    echo -e "   ${BLUE}Process: $process_info${NC}" >&2

    case "$PORT_CONFLICT_MODE" in
        kill)
            echo -e "   ${YELLOW}🔧 Auto-killing conflicting process...${NC}" >&2
            kill_port $required_port
            echo $required_port
            return 0
            ;;

        reassign)
            if [ "$allow_reassign" = "true" ]; then
                local new_port=$(find_free_port $required_port)
                echo -e "   ${BLUE}🔄 Reassigning to port $new_port${NC}" >&2
                echo $new_port
                return 0
            else
                echo -e "   ${RED}❌ Service $service_name cannot use alternate port${NC}" >&2
                return 1
            fi
            ;;

        ask)
            echo -e "   ${BLUE}Choose action:${NC}" >&2
            echo -e "   ${BLUE}  [k] Kill process and use port $required_port${NC}" >&2
            if [ "$allow_reassign" = "true" ]; then
                echo -e "   ${BLUE}  [r] Reassign to next available port${NC}" >&2
            fi
            echo -e "   ${BLUE}  [a] Abort startup${NC}" >&2
            read -p "   Your choice: " -n 1 -r choice
            echo "" >&2

            case "$choice" in
                k|K)
                    kill_port $required_port
                    echo $required_port
                    return 0
                    ;;
                r|R)
                    if [ "$allow_reassign" = "true" ]; then
                        local new_port=$(find_free_port $required_port)
                        echo -e "   ${GREEN}✅ Using port $new_port${NC}" >&2
                        echo $new_port
                        return 0
                    else
                        echo -e "   ${RED}❌ Invalid choice${NC}" >&2
                        return 1
                    fi
                    ;;
                *)
                    echo -e "   ${RED}❌ Startup aborted${NC}" >&2
                    return 1
                    ;;
            esac
            ;;

        error)
            echo -e "   ${RED}❌ Port conflict mode set to 'error'${NC}" >&2
            echo -e "   ${YELLOW}Tip: Set OPENCLAW_PORT_CONFLICT_MODE=kill or =reassign${NC}" >&2
            return 1
            ;;

        *)
            echo -e "   ${RED}❌ Invalid PORT_CONFLICT_MODE: $PORT_CONFLICT_MODE${NC}" >&2
            return 1
            ;;
    esac
}

# 1. Check/Start Gateway
echo "1️⃣  OpenClaw Gateway (port 18789)"
GATEWAY_PORT=18789

if curl -s http://localhost:$GATEWAY_PORT/health > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Already running on port $GATEWAY_PORT${NC}"
else
    # Resolve port conflict (Gateway requires fixed port for backend to connect)
    GATEWAY_PORT=$(resolve_port_conflict "Gateway" 18789 false)
    if [ $? -ne 0 ]; then
        echo -e "   ${RED}❌ Cannot start Gateway - port conflict${NC}"
        exit 1
    fi

    echo "   Starting DBOS gateway on port $GATEWAY_PORT..."
    cd openclaw-gateway/

    # Update .env if port changed
    if [ "$GATEWAY_PORT" != "18789" ]; then
        echo -e "   ${YELLOW}⚠️  Using non-default port $GATEWAY_PORT${NC}"
        echo "PORT=$GATEWAY_PORT" >> .env
    fi

    # Load PostgreSQL credentials from parent .env
    if [ -f "../.env" ]; then
        export $(grep -E "^(PGHOST|PGPORT|PGUSER|PGPASSWORD|PGDATABASE)=" ../.env | xargs)
    fi

    # Start DBOS gateway with proper environment
    PORT=$GATEWAY_PORT node dist/server.js > /tmp/openclaw-gateway.log 2>&1 &
    GATEWAY_PID=$!
    cd ..

    # Wait for gateway to be ready
    echo "   Waiting for gateway to start..."
    for i in {1..30}; do
        if curl -s http://localhost:$GATEWAY_PORT/health > /dev/null 2>&1; then
            echo -e "   ${GREEN}✅ Started on port $GATEWAY_PORT (PID: $GATEWAY_PID)${NC}"
            break
        fi
        sleep 1
    done

    if ! curl -s http://localhost:$GATEWAY_PORT/health > /dev/null 2>&1; then
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
export OPENCLAW_GATEWAY_URL="http://localhost:$GATEWAY_PORT"
export OPENCLAW_GATEWAY_TOKEN="openclaw-dev-token-12345"
export ENVIRONMENT="development"
# Use PostgreSQL from .env file instead of SQLite
export DATABASE_URL="${DATABASE_URL:-postgresql+asyncpg://postgres:xDelQrUbmzAnRtgNqtNaNbaoAfKBftHM@yamabiko.proxy.rlwy.net:51955/railway}"
echo -e "   ${GREEN}✅ Environment configured (Gateway: http://localhost:$GATEWAY_PORT)${NC}"
echo ""

# 3. Start Backend
echo "3️⃣  Backend API (port 8000)"
BACKEND_PORT=8000

if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Already running on port $BACKEND_PORT${NC}"
else
    # Resolve port conflict (Backend can run on alternative port)
    BACKEND_PORT=$(resolve_port_conflict "Backend" 8000 true)
    if [ $? -ne 0 ]; then
        echo -e "   ${RED}❌ Cannot start Backend - port conflict${NC}"
        exit 1
    fi

    # Run pre-backend-start hook to enforce Railway database
    if [ -f ".claude/hooks/pre-backend-start.sh" ]; then
        ./.claude/hooks/pre-backend-start.sh
        if [ $? -ne 0 ]; then
            echo -e "   ${RED}❌ Pre-start hook failed - database validation error${NC}"
            exit 1
        fi
    fi

    echo "   Starting backend on port $BACKEND_PORT..."
    python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port $BACKEND_PORT > /tmp/openclaw-backend.log 2>&1 &
    BACKEND_PID=$!

    # Wait for backend to be ready
    echo "   Waiting for backend to start (this includes agent initialization)..."
    for i in {1..30}; do
        if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
            echo -e "   ${GREEN}✅ Started on port $BACKEND_PORT (PID: $BACKEND_PID)${NC}"
            break
        fi
        sleep 1
    done

    if ! curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
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
FRONTEND_PORT=3002

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

    # Update or create .env with backend URL
    if [ -f .env ]; then
        sed -i.bak "s|NEXT_PUBLIC_API_URL=.*|NEXT_PUBLIC_API_URL=http://localhost:$BACKEND_PORT|g" .env
        rm -f .env.bak
    else
        echo "NEXT_PUBLIC_API_URL=http://localhost:$BACKEND_PORT" > .env
        echo "   Created .env file"
    fi

    # Resolve port conflict (Frontend can run on alternative port)
    if check_port $FRONTEND_PORT && ! curl -s http://localhost:$FRONTEND_PORT > /dev/null 2>&1; then
        FRONTEND_PORT=$(resolve_port_conflict "Frontend" 3002 true)
        if [ $? -ne 0 ]; then
            echo -e "   ${RED}❌ Cannot start Frontend - port conflict${NC}"
            cd ../openclaw-backend/
            exit 1
        fi
    fi

    # Run pre-frontend-start hook to enforce API URL configuration
    if [ -f ".claude/hooks/pre-frontend-start.sh" ]; then
        ./.claude/hooks/pre-frontend-start.sh
        if [ $? -ne 0 ]; then
            echo -e "   ${RED}❌ Pre-start hook failed - frontend configuration error${NC}"
            cd ../openclaw-backend/
            exit 1
        fi
    fi

    # Start frontend if not already running
    if curl -s http://localhost:$FRONTEND_PORT > /dev/null 2>&1; then
        echo -e "   ${GREEN}✅ Already running on port $FRONTEND_PORT${NC}"
    else
        echo "   Starting frontend on port $FRONTEND_PORT..."

        # Set PORT env var if using non-default port
        if [ "$FRONTEND_PORT" != "3002" ]; then
            export PORT=$FRONTEND_PORT
        fi

        npm run dev > /tmp/openclaw-frontend.log 2>&1 &
        FRONTEND_PID=$!

        # Wait for frontend to be ready
        sleep 5
        echo -e "   ${GREEN}✅ Started on port $FRONTEND_PORT (PID: $FRONTEND_PID)${NC}"
    fi

    cd ../openclaw-backend/
fi
echo ""

# Summary
echo "======================================"
echo -e "${GREEN}✅ All services started!${NC}"
echo ""
echo "📍 Service URLs:"
echo "   Gateway:  http://localhost:$GATEWAY_PORT"
echo "   Backend:  http://localhost:$BACKEND_PORT"
echo "   Frontend: http://localhost:${FRONTEND_PORT:-3002}"
echo "   API Docs: http://localhost:$BACKEND_PORT/docs"
echo ""
echo "📋 Logs:"
echo "   Gateway:  tail -f /tmp/openclaw-gateway.log"
echo "   Backend:  tail -f /tmp/openclaw-backend.log"
echo "   Frontend: tail -f /tmp/openclaw-frontend.log"
echo ""
echo "🔍 Verify agents:"
echo "   curl http://localhost:$BACKEND_PORT/api/v1/agents?limit=50 | python3 -m json.tool"
echo ""
echo "⚙️  Port Configuration:"
echo "   Mode: $PORT_CONFLICT_MODE"
if [ "$GATEWAY_PORT" != "18789" ] || [ "$BACKEND_PORT" != "8000" ] || [ "${FRONTEND_PORT:-3002}" != "3002" ]; then
    echo -e "   ${YELLOW}⚠️  Using non-default ports due to conflicts${NC}"
fi
echo ""
echo "🛑 To stop all services:"
echo "   scripts/stop-all-local.sh"
echo ""
echo "💡 Port Conflict Resolution Modes:"
echo "   OPENCLAW_PORT_CONFLICT_MODE=kill     # Auto-kill conflicting processes"
echo "   OPENCLAW_PORT_CONFLICT_MODE=reassign # Use alternative ports"
echo "   OPENCLAW_PORT_CONFLICT_MODE=ask      # Prompt user (default)"
echo "   OPENCLAW_PORT_CONFLICT_MODE=error    # Fail on conflicts"
echo ""
echo "🌐 Opening frontend in browser..."
sleep 2
open http://localhost:${FRONTEND_PORT:-3002} 2>/dev/null || echo "   Open manually: http://localhost:${FRONTEND_PORT:-3002}"
