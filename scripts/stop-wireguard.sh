#!/bin/bash
#
# Stop WireGuard Interface for OpenClaw
#
# Usage: sudo ./scripts/stop-wireguard.sh

set -e

WG_CONFIG="$HOME/.wireguard/wg0.conf"

echo "🔐 Stopping WireGuard interface..."

# Check if running
if ! wg show wg0 &>/dev/null; then
    echo "⚠️  WireGuard interface wg0 is not running"
    exit 0
fi

# Stop the interface
wg-quick down "$WG_CONFIG"

echo "✅ WireGuard interface stopped successfully!"
