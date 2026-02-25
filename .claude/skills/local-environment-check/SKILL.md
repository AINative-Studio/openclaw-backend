# Local Environment Check Skill

**USE THIS SKILL** when troubleshooting local development environment issues or when verifying the local setup.

## Quick Diagnostic Commands

### Full System Check

Run this comprehensive check script to diagnose all aspects of the local environment:

```bash
#!/bin/bash
echo "=== OpenClaw Backend Environment Check ==="
echo ""

# 1. OpenClaw Gateway
echo "1️⃣  OpenClaw Gateway Status"
if curl -s -o /dev/null -w "%{http_code}" http://localhost:18789/health | grep -q "200"; then
    echo "   ✅ Gateway running on port 18789"
    curl -s http://localhost:18789/health | python3 -m json.tool
else
    echo "   ❌ Gateway NOT responding on port 18789"
    if lsof -i :18789 > /dev/null 2>&1; then
        echo "   ⚠️  Port 18789 is in use by another process"
        lsof -i :18789
    else
        echo "   💡 Start gateway: cd openclaw-gateway && npm start"
    fi
fi
echo ""

# 2. Python Environment
echo "2️⃣  Python Environment"
if [ -d "venv" ] || [ -d ".venv" ]; then
    echo "   ✅ Virtual environment exists"

    if python -c "import sys; exit(0 if (hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix)) else 1)" 2>/dev/null; then
        echo "   ✅ Virtual environment is ACTIVATED"
        echo "   📍 Python: $(which python)"
        echo "   📌 Version: $(python --version)"
    else
        echo "   ⚠️  Virtual environment NOT activated"
        echo "   💡 Run: source venv/bin/activate"
    fi
else
    echo "   ❌ Virtual environment NOT found"
    echo "   💡 Create: python3 -m venv venv"
fi
echo ""

# 3. Dependencies
echo "3️⃣  Required Dependencies"
DEPS=("fastapi" "uvicorn" "pydantic" "sqlalchemy")
ALL_INSTALLED=true
for dep in "${DEPS[@]}"; do
    if python -c "import $dep" 2>/dev/null; then
        VERSION=$(python -c "import $dep; print(getattr($dep, '__version__', 'unknown'))")
        echo "   ✅ $dep ($VERSION)"
    else
        echo "   ❌ $dep NOT installed"
        ALL_INSTALLED=false
    fi
done

if [ "$ALL_INSTALLED" = false ]; then
    echo "   💡 Install: pip install -r requirements.txt"
fi
echo ""

# 4. Environment Variables
echo "4️⃣  Environment Variables"
check_env_var() {
    if [ -n "${!1}" ]; then
        # Mask sensitive values
        if [[ "$1" == *"KEY"* ]] || [[ "$1" == *"TOKEN"* ]] || [[ "$1" == *"PASSWORD"* ]]; then
            echo "   ✅ $1=****** (set)"
        else
            echo "   ✅ $1=${!1}"
        fi
    else
        echo "   ⚠️  $1 not set"
    fi
}

check_env_var "SECRET_KEY"
check_env_var "OPENCLAW_GATEWAY_URL"
check_env_var "OPENCLAW_GATEWAY_TOKEN"
check_env_var "DATABASE_URL"
check_env_var "ENVIRONMENT"
check_env_var "ANTHROPIC_API_KEY"
echo ""

# 5. Database
echo "5️⃣  Database Connectivity"
if [ -n "$DATABASE_URL" ]; then
    if [[ "$DATABASE_URL" == sqlite* ]]; then
        DB_FILE=$(echo $DATABASE_URL | sed 's/sqlite:\/\/\///')
        if [ -f "$DB_FILE" ]; then
            echo "   ✅ SQLite database exists: $DB_FILE"
            SIZE=$(du -h "$DB_FILE" | cut -f1)
            echo "   📊 Size: $SIZE"
        else
            echo "   ⚠️  SQLite database not created yet: $DB_FILE"
            echo "   💡 Will be created on first startup"
        fi
    else
        echo "   🔗 PostgreSQL configured"
        # Test connection without exposing credentials
        if python -c "from backend.db.base import engine; engine.connect()" 2>/dev/null; then
            echo "   ✅ Database connection successful"
        else
            echo "   ❌ Database connection failed"
            echo "   💡 Check DATABASE_URL credentials and network"
        fi
    fi
else
    echo "   ℹ️  DATABASE_URL not set (will default to sqlite:///./openclaw.db)"
fi
echo ""

# 6. Backend Service
echo "6️⃣  Backend Service Status"
if curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/health | grep -q "200"; then
    echo "   ✅ Backend running on port 8000"
    curl -s http://localhost:8000/health | python3 -m json.tool
else
    echo "   ❌ Backend NOT responding on port 8000"
    if lsof -i :8000 > /dev/null 2>&1; then
        echo "   ⚠️  Port 8000 is in use by another process"
        lsof -i :8000
    else
        echo "   💡 Backend not started yet"
    fi
fi
echo ""

# 7. Ports Summary
echo "7️⃣  Port Usage Summary"
echo "   Gateway (18789): $(lsof -i :18789 > /dev/null 2>&1 && echo '🟢 IN USE' || echo '🔴 FREE')"
echo "   Backend (8000):  $(lsof -i :8000 > /dev/null 2>&1 && echo '🟢 IN USE' || echo '🔴 FREE')"
echo ""

echo "=== End of Environment Check ==="
```

## Individual Component Checks

### Gateway Only
```bash
curl -v http://localhost:18789/health
```

### Backend Only
```bash
curl -v http://localhost:8000/health
```

### Python Environment
```bash
python -c "
import sys
print('Python:', sys.version)
print('Executable:', sys.executable)
print('In venv:', hasattr(sys, 'real_prefix') or (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix))
"
```

### Dependencies Check
```bash
pip list | grep -E 'fastapi|uvicorn|pydantic|sqlalchemy|pytest'
```

### Environment Variables
```bash
env | grep -E 'SECRET_KEY|OPENCLAW|DATABASE|ENVIRONMENT|ANTHROPIC' | sed 's/=.*/=******/'
```

### Database Check (SQLite)
```bash
# Check if database file exists
ls -lh openclaw.db 2>/dev/null || echo "Database not created yet"

# Check tables (if exists)
sqlite3 openclaw.db ".tables" 2>/dev/null || echo "No tables yet"
```

### Database Check (PostgreSQL)
```bash
python -c "
from sqlalchemy import create_engine, text
import os
try:
    engine = create_engine(os.getenv('DATABASE_URL'))
    with engine.connect() as conn:
        result = conn.execute(text('SELECT version()'))
        print('PostgreSQL version:', result.fetchone()[0])
except Exception as e:
    print('Error:', e)
"
```

## API Endpoint Health Checks

### Core Endpoints
```bash
# Health check
curl http://localhost:8000/health

# API docs
curl http://localhost:8000/docs
```

### Agent Lifecycle Endpoints
```bash
# List agents (if endpoint exists)
curl http://localhost:8000/api/v1/agents

# Agent swarm status
curl http://localhost:8000/api/v1/swarm/status
```

### WireGuard Endpoints
```bash
# WireGuard health
curl http://localhost:8000/api/v1/wireguard/health

# IP pool stats
curl http://localhost:8000/api/v1/wireguard/pool/stats

# Peer list
curl http://localhost:8000/api/v1/wireguard/peers
```

### Monitoring Endpoints
```bash
# Swarm health
curl http://localhost:8000/api/v1/swarm/health | python3 -m json.tool

# Timeline events
curl http://localhost:8000/api/v1/swarm/timeline | python3 -m json.tool

# Alert thresholds
curl http://localhost:8000/api/v1/swarm/alerts/thresholds | python3 -m json.tool

# Monitoring status
curl http://localhost:8000/api/v1/swarm/monitoring/status | python3 -m json.tool

# Prometheus metrics
curl http://localhost:8000/api/v1/metrics
```

## Automated Fix Script

```bash
#!/bin/bash
# auto-fix-local.sh - Automatically fix common issues

echo "🔧 OpenClaw Local Environment Auto-Fix"
echo ""

# Fix 1: Create venv if missing
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
fi

# Fix 2: Activate venv
source venv/bin/activate
echo "✅ Virtual environment activated"

# Fix 3: Install/update dependencies
echo "Installing dependencies..."
pip install -q -r requirements.txt
echo "✅ Dependencies installed"

# Fix 4: Set environment variables if missing
if [ -z "$SECRET_KEY" ]; then
    export SECRET_KEY="dev-secret-key-$(date +%s)"
    echo "✅ SECRET_KEY set (temporary dev key)"
fi

if [ -z "$OPENCLAW_GATEWAY_URL" ]; then
    export OPENCLAW_GATEWAY_URL="http://localhost:18789"
    echo "✅ OPENCLAW_GATEWAY_URL set"
fi

if [ -z "$OPENCLAW_GATEWAY_TOKEN" ]; then
    export OPENCLAW_GATEWAY_TOKEN="openclaw-dev-token-12345"
    echo "✅ OPENCLAW_GATEWAY_TOKEN set"
fi

if [ -z "$ENVIRONMENT" ]; then
    export ENVIRONMENT="development"
    echo "✅ ENVIRONMENT set to development"
fi

# Fix 5: Check gateway
if ! curl -s http://localhost:18789/health > /dev/null 2>&1; then
    echo "⚠️  Gateway not running. Attempting to start..."
    if [ -d "openclaw-gateway" ]; then
        cd openclaw-gateway
        if [ ! -d "node_modules" ]; then
            echo "Installing gateway dependencies..."
            npm install
        fi
        echo "Starting gateway in background..."
        npm start &
        sleep 3
        cd ..
        echo "✅ Gateway started"
    else
        echo "❌ openclaw-gateway directory not found"
    fi
fi

echo ""
echo "🎉 Auto-fix complete! Ready to start backend."
echo "   Run: uvicorn backend.main:app --reload"
```

## Troubleshooting Decision Tree

```
Backend won't start?
├─ Import errors? → pip install -r requirements.txt
├─ Port 8000 in use? → kill -9 $(lsof -t -i:8000)
├─ Database error? → Check DATABASE_URL, permissions
└─ Gateway error? → Check OPENCLAW_GATEWAY_URL, gateway health

Gateway not responding?
├─ Port 18789 in use? → lsof -i :18789
├─ Gateway not started? → cd openclaw-gateway && npm start
├─ node_modules missing? → npm install
└─ Wrong token? → Check OPENCLAW_GATEWAY_TOKEN matches .env

Tests failing?
├─ Not in venv? → source venv/bin/activate
├─ Missing pytest? → pip install pytest pytest-asyncio
├─ Database locked? → Close other connections
└─ Import errors? → Check PYTHONPATH

Database issues?
├─ SQLite locked? → Close all connections, restart backend
├─ PostgreSQL connection failed? → Check DATABASE_URL, network
├─ Missing tables? → Run alembic upgrade head
└─ Migration conflict? → Check alembic versions
```

## Integration with Local Startup

This skill provides diagnostic commands that the `local-startup` skill uses for prerequisite verification.

**Usage Pattern**:
1. Run environment check first to identify issues
2. Use auto-fix script to resolve common problems
3. Then use local-startup skill to start the backend
