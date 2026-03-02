#!/usr/bin/env python3
"""Test sending message via HTTP API"""
import requests
import json

agent_id = "a4b5a493-8aa8-49ed-8999-cf03c5da9534"  # Main Agent
url = f"http://localhost:8000/api/v1/agents/{agent_id}/message"

payload = {"message": "Hello! What is 5 times 7?"}

print(f"Sending POST to: {url}")
print(f"Payload: {json.dumps(payload, indent=2)}")
print("\nWaiting for response...")

try:
    response = requests.post(url, json=payload, timeout=180)
    print(f"\nStatus code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except requests.exceptions.Timeout:
    print("\n❌ Request timed out")
except Exception as e:
    print(f"\n❌ Error: {e}")
    print(f"Response text: {response.text if 'response' in locals() else 'N/A'}")
