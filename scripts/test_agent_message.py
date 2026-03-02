#!/usr/bin/env python3
"""
Test script for sending a message to an agent and getting the full response
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from integrations.openclaw_bridge import OpenClawBridge


async def test_agent_message():
    gateway_url = os.getenv("OPENCLAW_GATEWAY_URL", "ws://127.0.0.1:18789")
    gateway_token = os.getenv("OPENCLAW_TOKEN")

    print(f"Connecting to gateway: {gateway_url}")
    bridge = OpenClawBridge(url=gateway_url, token=gateway_token)

    try:
        # Connect
        await bridge.connect()
        print("✓ Connected to gateway")

        # Send message to main agent
        session_key = "agent:main:main"
        message = "What is 2 plus 2?"

        print(f"\nSending message to {session_key}: '{message}'")
        print("Waiting for response...")

        result = await bridge.send_to_agent(
            session_key=session_key,
            message=message,
            timeout_seconds=120
        )

        print("\n=== FULL RESULT ===")
        import json
        print(json.dumps(result, indent=2))

        # Extract response text
        payloads = result.get("result", {}).get("payloads", [])
        if payloads:
            print("\n=== AGENT RESPONSE ===")
            for payload in payloads:
                text = payload.get("text", "")
                if text:
                    print(text)
        else:
            print("\n⚠ No payloads in response")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        await bridge.close()
        print("\n✓ Connection closed")


if __name__ == "__main__":
    asyncio.run(test_agent_message())
