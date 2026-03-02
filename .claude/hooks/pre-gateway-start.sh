#!/bin/bash
# .claude/hooks/pre-gateway-start.sh
# Verifies OpenClaw Gateway prerequisites before startup
# Prevents cryptic errors by catching configuration issues early

GATEWAY_DIR="openclaw-gateway"

echo "🔍 Verifying OpenClaw Gateway Prerequisites..."

# 1. Check TypeScript source exists
if [ ! -d "$GATEWAY_DIR/src" ]; then
    echo "❌ ERROR: TypeScript source missing at $GATEWAY_DIR/src/"
    echo "   TypeScript source is required for gateway modifications"
    echo "   Solution: Ensure src/ directory is committed to git"
    exit 1
fi

echo "   ✅ TypeScript source exists"

# 2. Check .env file exists
if [ ! -f "$GATEWAY_DIR/.env" ]; then
    echo "❌ ERROR: .env file missing at $GATEWAY_DIR/.env"
    echo "   Create .env from .env.example or with these required vars:"
    echo "   - PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE"
    echo "   - PGSSLMODE (CRITICAL for Railway PostgreSQL)"
    echo "   - PGCONNECT_TIMEOUT"
    exit 1
fi

echo "   ✅ .env file exists"

# 3. Check DBOS-specific environment variables
if ! grep -q "^PGSSLMODE=" "$GATEWAY_DIR/.env"; then
    echo "⚠️  WARNING: PGSSLMODE not set in .env"
    echo "   DBOS SDK reads SSL config from PGSSLMODE env var, NOT dbos-config.yaml"
    echo "   For Railway PostgreSQL with self-signed certs, use: PGSSLMODE=disable"
    echo ""
    echo "   Add to $GATEWAY_DIR/.env:"
    echo "   PGSSLMODE=disable"
    echo ""
    read -p "   Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
else
    echo "   ✅ PGSSLMODE configured"
fi

if ! grep -q "^PGCONNECT_TIMEOUT=" "$GATEWAY_DIR/.env"; then
    echo "   ℹ️  INFO: PGCONNECT_TIMEOUT not set (will use DBOS default: 10s)"
fi

# 4. Check if build is needed
if [ ! -d "$GATEWAY_DIR/dist" ] || [ "$GATEWAY_DIR/src" -nt "$GATEWAY_DIR/dist" ]; then
    echo "🔨 TypeScript source is newer than compiled output - building..."
    cd "$GATEWAY_DIR" && npm run build
    if [ $? -ne 0 ]; then
        echo "❌ ERROR: TypeScript build failed"
        exit 1
    fi
    cd ..
    echo "   ✅ TypeScript compiled successfully"
else
    echo "   ✅ Build is up to date"
fi

# 5. Check PostgreSQL credentials are set
required_vars=("PGHOST" "PGPORT" "PGUSER" "PGPASSWORD" "PGDATABASE")
missing_vars=()

for var in "${required_vars[@]}"; do
    if ! grep -q "^${var}=" "$GATEWAY_DIR/.env"; then
        missing_vars+=("$var")
    fi
done

if [ ${#missing_vars[@]} -gt 0 ]; then
    echo "❌ ERROR: Required env vars not set in .env:"
    for var in "${missing_vars[@]}"; do
        echo "   - $var"
    done
    exit 1
fi

echo "   ✅ All PostgreSQL credentials configured"

echo "✅ All gateway prerequisites verified - ready to start!"
exit 0
