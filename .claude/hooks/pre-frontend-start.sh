#!/bin/bash
# .claude/hooks/pre-frontend-start.sh
# ENFORCES that Frontend ALWAYS has correct API URL configuration
# ZERO TOLERANCE for missing /api/v1 prefix

set -e

echo "🔒 Enforcing Frontend API URL Configuration..."

# Check if .env exists
if [ ! -f ".env" ]; then
    echo "❌ FATAL ERROR: .env file not found in frontend directory"
    echo "   Frontend MUST have NEXT_PUBLIC_API_URL configured"
    exit 1
fi

# Load .env
export $(grep -v '^#' .env | xargs)

# Check NEXT_PUBLIC_API_URL is set
if [ -z "$NEXT_PUBLIC_API_URL" ]; then
    echo "❌ FATAL ERROR: NEXT_PUBLIC_API_URL not set in .env"
    echo "   Frontend MUST have API URL configured"
    echo ""
    echo "   Required format:"
    echo "   NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1"
    exit 1
fi

# Verify it ends with /api/v1
if [[ ! "$NEXT_PUBLIC_API_URL" =~ /api/v1$ ]]; then
    echo "❌ FATAL ERROR: NEXT_PUBLIC_API_URL does not end with /api/v1"
    echo "   Current: $NEXT_PUBLIC_API_URL"
    echo ""
    echo "   Frontend API calls will fail without the /api/v1 prefix"
    echo "   Backend API routes require /api/v1 prefix"
    echo ""
    echo "   Correct format:"
    echo "   NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1"
    exit 1
fi

# Verify backend is reachable
BACKEND_URL="${NEXT_PUBLIC_API_URL%/api/v1}/health"
if ! curl -s -f "$BACKEND_URL" > /dev/null 2>&1; then
    echo "⚠️  WARNING: Backend not reachable at $BACKEND_URL"
    echo "   Frontend will start but API calls may fail"
    echo "   Make sure backend is running on port $(echo $NEXT_PUBLIC_API_URL | grep -o ':[0-9]*' | tr -d ':')"
fi

echo "   ✅ NEXT_PUBLIC_API_URL configured: $NEXT_PUBLIC_API_URL"
echo "✅ Frontend configuration validated - ready to start!"
exit 0
