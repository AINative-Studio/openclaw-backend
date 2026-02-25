#!/usr/bin/env python3
"""
Test script for DBOS agent provisioning integration

Tests the provision flow with fallback mode when DBOS endpoints are unavailable.
"""

import httpx
import asyncio
import json

BASE_URL = "http://localhost:8000/api/v1"


async def test_provisioning():
    """Test agent creation and provisioning with DBOS integration"""

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Create a test agent
        print("📝 Creating test agent...")
        create_response = await client.post(
            f"{BASE_URL}/agents",
            json={
                "name": "DBOS Test Agent",
                "persona": "Test agent for DBOS integration verification",
                "model": "anthropic/claude-3-haiku-20240307"
            }
        )

        if create_response.status_code != 201:
            print(f"❌ Failed to create agent: {create_response.status_code}")
            print(create_response.text)
            return

        agent = create_response.json()
        agent_id = agent["id"]
        print(f"✅ Created agent: {agent_id}")
        print(f"   Status: {agent['status']}")
        print(f"   Session key: {agent['openclaw_session_key']}")

        # Step 2: Provision the agent (should test DBOS workflow with fallback)
        print(f"\n🚀 Provisioning agent {agent_id}...")
        provision_response = await client.post(
            f"{BASE_URL}/agents/{agent_id}/provision"
        )

        if provision_response.status_code != 200:
            print(f"❌ Failed to provision agent: {provision_response.status_code}")
            print(provision_response.text)
            return

        provisioned_agent = provision_response.json()
        print(f"✅ Agent provisioned successfully!")
        print(f"   Status: {provisioned_agent['status']}")
        print(f"   Provisioned at: {provisioned_agent.get('provisioned_at', 'N/A')}")

        # Step 3: Get agent details to verify
        print(f"\n🔍 Fetching agent details...")
        get_response = await client.get(f"{BASE_URL}/agents/{agent_id}")

        if get_response.status_code != 200:
            print(f"❌ Failed to get agent: {get_response.status_code}")
            return

        final_agent = get_response.json()
        print(f"✅ Final agent state:")
        print(json.dumps(final_agent, indent=2))

        # Step 4: Clean up - delete the test agent
        print(f"\n🗑️  Cleaning up test agent...")
        delete_response = await client.delete(f"{BASE_URL}/agents/{agent_id}")

        if delete_response.status_code == 204:
            print(f"✅ Test agent deleted successfully")
        else:
            print(f"⚠️  Failed to delete agent: {delete_response.status_code}")


if __name__ == "__main__":
    print("=" * 60)
    print("DBOS Agent Provisioning Integration Test")
    print("=" * 60)
    print("\nThis test will:")
    print("1. Create a test agent via API")
    print("2. Provision it (testing DBOS workflow with fallback)")
    print("3. Verify the provisioned state")
    print("4. Clean up by deleting the test agent")
    print("\nExpected: Should fall back to direct DB provisioning")
    print("since DBOS endpoints are not fully configured.\n")

    asyncio.run(test_provisioning())

    print("\n" + "=" * 60)
    print("✅ Test complete! Check backend logs for DBOS fallback messages")
    print("=" * 60)
