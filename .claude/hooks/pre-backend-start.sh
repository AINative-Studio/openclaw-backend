#!/bin/bash
# .claude/hooks/pre-backend-start.sh
# ENFORCES that OpenClaw backend ALWAYS uses Railway PostgreSQL database
# ZERO TOLERANCE for local SQLite or missing DATABASE_URL

set -e

echo "🔒 Enforcing Railway PostgreSQL Database Connection..."

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ FATAL ERROR: .env file not found"
    echo "   OpenClaw backend MUST use Railway cloud database"
    exit 1
fi

# Load .env
export $(grep -v '^#' .env | xargs)

# Check DATABASE_URL is set
if [ -z "$DATABASE_URL" ]; then
    echo "❌ FATAL ERROR: DATABASE_URL not set in .env"
    echo "   OpenClaw backend MUST connect to Railway PostgreSQL"
    echo ""
    echo "   Required format:"
    echo "   DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@yamabiko.proxy.rlwy.net:51955/railway"
    exit 1
fi

# Verify it's Railway database (matches both railway.net and rlwy.net)
if [[ ! "$DATABASE_URL" =~ (railway\.net|rlwy\.net|railway) ]]; then
    echo "❌ FATAL ERROR: DATABASE_URL does not point to Railway"
    echo "   Current: $DATABASE_URL"
    echo ""
    echo "   OpenClaw backend MUST use Railway cloud database"
    echo "   Local SQLite is NOT ALLOWED"
    echo ""
    echo "   Correct format:"
    echo "   DATABASE_URL=postgresql+asyncpg://postgres:PASSWORD@yamabiko.proxy.rlwy.net:51955/railway"
    exit 1
fi

# Verify asyncpg driver
if [[ ! "$DATABASE_URL" =~ postgresql\+asyncpg ]]; then
    echo "⚠️  WARNING: DATABASE_URL should use asyncpg driver"
    echo "   Current: $DATABASE_URL"
    echo "   Expected: postgresql+asyncpg://..."
    echo ""
    read -p "   Continue anyway? (y/N) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

echo "   ✅ DATABASE_URL configured: Railway PostgreSQL"
echo "   ✅ Database host: $(echo $DATABASE_URL | grep -o '@[^/]*' | tr -d '@')"

echo "✅ Railway database enforced - ready to start!"
exit 0
