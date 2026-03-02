#!/bin/bash
# .claude/hooks/pre-gateway-start.sh
# Verifies OpenClaw Gateway prerequisites before startup

GATEWAY_DIR="openclaw-gateway"

echo "🔍 Verifying OpenClaw Gateway Prerequisites..."

# 1. Check TypeScript source exists
if [ ! -d "$GATEWAY_DIR/src" ]; then
    echo "❌ ERROR: TypeScript source missing"
    exit 1
fi

# 2. Check .env file exists
if [ ! -f "$GATEWAY_DIR/.env" ]; then
    echo "❌ ERROR: .env file missing"
    exit 1
fi

# 3. Check PGSSLMODE configured
if ! grep -q "^PGSSLMODE=" "$GATEWAY_DIR/.env"; then
    echo "⚠️  WARNING: PGSSLMODE not set in .env"
fi

echo "✅ Gateway prerequisites verified"
