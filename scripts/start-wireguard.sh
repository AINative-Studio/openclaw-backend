#!/bin/bash
#
# Start WireGuard Interface for OpenClaw
#
# This script starts the WireGuard VPN interface used for
# secure agent-to-agent communication.
#
# Usage: sudo ./scripts/start-wireguard.sh

set -e

WG_CONFIG="$HOME/.wireguard/wg0.conf"

echo "🔐 Starting WireGuard interface..."

# Check if config exists
if [ ! -f "$WG_CONFIG" ]; then
    echo "❌ Configuration not found at $WG_CONFIG"
    exit 1
fi

# Check if already running
if wg show wg0 &>/dev/null; then
    echo "✅ WireGuard interface wg0 is already running"
    wg show wg0
    exit 0
fi

# Start the interface
echo "   Bringing up wg0..."
wg-quick up "$WG_CONFIG"

echo "✅ WireGuard interface started successfully!"
echo ""
echo "Interface details:"
wg show wg0

echo ""
echo "📋 To stop: sudo wg-quick down $WG_CONFIG"
echo "📋 To check status: wg show wg0"
