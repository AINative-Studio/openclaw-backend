#!/usr/bin/env python3
"""Test script to see what OpenClaw Gateway actually returns"""

import asyncio
import json
import logging
import sys
sys.path.insert(0, "/Users/aideveloper/openclaw-backend")

from integrations.openclaw_bridge import OpenClawBridge

# Enable debug logging
logging.basicConfig(level=logging.DEBUG)

async def test():
    bridge = OpenClawBridge(
        url="ws://localhost:18789",
        token="7ae5aa8730848791e5a017fe95b80ad26f8c31d90e7b9ab60f5f8974d6519fc1"
    )

    try:
        await bridge.connect()
        print("✅ Connected to gateway")

        result = await bridge.send_to_agent("agent:main:main", "Hello! Please respond.")

        print("\n📦 FULL RESULT:")
        print(json.dumps(result, indent=2))

    finally:
        await bridge.close()

if __name__ == "__main__":
    asyncio.run(test())
