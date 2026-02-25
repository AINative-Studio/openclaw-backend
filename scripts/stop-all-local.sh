#!/bin/bash
# stop-all-local.sh - Stop all OpenClaw services

echo "🛑 Stopping OpenClaw services..."
echo ""

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Stop processes on specific ports
for port in 18789 8000 3002; do
    PID=$(lsof -ti :$port 2>/dev/null)
    if [ ! -z "$PID" ]; then
        SERVICE=$(
            case $port in
                18789) echo "Gateway" ;;
                8000) echo "Backend" ;;
                3002) echo "Frontend" ;;
            esac
        )
        echo "   Stopping $SERVICE on port $port (PID: $PID)"
        kill $PID 2>/dev/null || kill -9 $PID 2>/dev/null
        sleep 1
    fi
done

echo ""
echo -e "${GREEN}✅ All services stopped${NC}"
echo ""

# Clean up log files
if ls /tmp/openclaw-*.log 1> /dev/null 2>&1; then
    echo "🗑️  Cleaning up log files..."
    rm -f /tmp/openclaw-*.log
    echo -e "${GREEN}✅ Logs cleaned${NC}"
fi

echo ""
echo "To restart services, run: ./start-all-local.sh"
