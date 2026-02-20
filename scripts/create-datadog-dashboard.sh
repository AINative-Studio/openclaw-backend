#!/usr/bin/env bash
#
# Import the AgentClaw Datadog dashboard via the Datadog API.
#
# Prerequisites:
#   export DD_API_KEY=<your-api-key>
#   export DD_APP_KEY=<your-app-key>
#   export DD_SITE=datadoghq.com   # optional, defaults to datadoghq.com
#
# Usage:
#   bash scripts/create-datadog-dashboard.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DASHBOARD_JSON="${SCRIPT_DIR}/../docs/datadog/agentclaw-dashboard.json"
DD_SITE="${DD_SITE:-datadoghq.com}"

if [ -z "${DD_API_KEY:-}" ] || [ -z "${DD_APP_KEY:-}" ]; then
    echo "Error: DD_API_KEY and DD_APP_KEY must be set."
    echo "  export DD_API_KEY=<your-api-key>"
    echo "  export DD_APP_KEY=<your-app-key>"
    exit 1
fi

if [ ! -f "$DASHBOARD_JSON" ]; then
    echo "Error: Dashboard JSON not found at $DASHBOARD_JSON"
    exit 1
fi

echo "Creating AgentClaw dashboard on ${DD_SITE}..."

RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "https://api.${DD_SITE}/api/v1/dashboard" \
    -H "Content-Type: application/json" \
    -H "DD-API-KEY: ${DD_API_KEY}" \
    -H "DD-APPLICATION-KEY: ${DD_APP_KEY}" \
    -d @"${DASHBOARD_JSON}")

HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$HTTP_CODE" -ge 200 ] && [ "$HTTP_CODE" -lt 300 ]; then
    DASHBOARD_URL=$(echo "$BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('url',''))" 2>/dev/null || echo "")
    echo "Dashboard created successfully (HTTP ${HTTP_CODE})"
    if [ -n "$DASHBOARD_URL" ]; then
        echo "URL: https://app.${DD_SITE}${DASHBOARD_URL}"
    fi
else
    echo "Failed to create dashboard (HTTP ${HTTP_CODE})"
    echo "$BODY"
    exit 1
fi
