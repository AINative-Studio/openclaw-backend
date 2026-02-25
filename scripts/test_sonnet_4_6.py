#!/usr/bin/env python3
"""Test the newest Claude Sonnet 4.6 model"""

import httpx
import os

API_KEY = os.getenv("ANTHROPIC_API_KEY")

def test_model(model_id):
    """Test a model"""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": model_id,
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "Say hello and tell me which model you are."}]
    }

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)

        print(f"Testing: {model_id}")
        print(f"Status Code: {response.status_code}\n")

        if response.status_code == 200:
            data = response.json()
            content = data.get("content", [{}])[0].get("text", "")
            usage = data.get("usage", {})

            print(f"✅ SUCCESS")
            print(f"\nResponse: {content}")
            print(f"\nUsage: {usage}")
            return True
        else:
            print(f"❌ FAILED: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    # Test the newest Sonnet 4.6
    test_model("claude-sonnet-4-6")
