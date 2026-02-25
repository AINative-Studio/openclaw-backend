#!/bin/bash
# Configure Anthropic API Key for OpenClaw Gateway

set -e

if [ -z "$1" ]; then
    echo "Usage: ./configure_api_key.sh <your-anthropic-api-key>"
    echo ""
    echo "Get your API key from: https://console.anthropic.com/settings/keys"
    echo ""
    echo "Example:"
    echo "  ./configure_api_key.sh sk-ant-api03-..."
    exit 1
fi

API_KEY="$1"
PLIST_FILE="$HOME/Library/LaunchAgents/ai.openclaw.gateway.plist"

echo "🔧 Configuring Anthropic API Key for OpenClaw Gateway..."

# Backup the current plist
cp "$PLIST_FILE" "$PLIST_FILE.backup"
echo "✅ Backed up plist to $PLIST_FILE.backup"

# Add ANTHROPIC_API_KEY to the EnvironmentVariables section
# Use plutil or manual XML editing
python3 << EOF
import plistlib
import sys

plist_path = "$PLIST_FILE"

# Read the plist
with open(plist_path, 'rb') as f:
    plist = plistlib.load(f)

# Add ANTHROPIC_API_KEY to EnvironmentVariables
if 'EnvironmentVariables' not in plist:
    plist['EnvironmentVariables'] = {}

plist['EnvironmentVariables']['ANTHROPIC_API_KEY'] = "$API_KEY"

# Write back
with open(plist_path, 'wb') as f:
    plistlib.dump(plist, f)

print("✅ Added ANTHROPIC_API_KEY to LaunchAgent configuration")
EOF

# Restart OpenClaw Gateway
echo "🔄 Restarting OpenClaw Gateway..."
launchctl unload "$PLIST_FILE" 2>/dev/null || true
sleep 2
launchctl load "$PLIST_FILE"
sleep 3

# Check if gateway is running
if openclaw gateway status | grep -q "Runtime: running"; then
    echo "✅ OpenClaw Gateway restarted successfully with API key configured"
    echo ""
    echo "🧪 Testing agent messaging..."
    python3 test_gateway_response.py
else
    echo "❌ Gateway failed to start. Check logs:"
    echo "   tail -f ~/.openclaw/logs/gateway.err.log"
    exit 1
fi
