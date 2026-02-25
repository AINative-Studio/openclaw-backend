#!/usr/bin/env python3
"""Update Main Agent status to running"""
import httpx

agent_id = "a4b5a493-8aa8-49ed-8999-cf03c5da9534"

response = httpx.put(
    f"http://localhost:8000/api/v1/agents/{agent_id}",
    json={"status": "running"}
)

print(f"Status: {response.status_code}")
if response.status_code == 200:
    print("✅ Main Agent updated to 'running' status")
    agent = response.json()
    print(f"Name: {agent['name']}")
    print(f"Status: {agent['status']}")
else:
    print(response.text)
