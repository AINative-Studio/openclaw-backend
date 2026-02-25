#!/usr/bin/env python3
"""Validate Anthropic API key by making a test request"""

import httpx
import os
import sys

API_KEY = os.getenv("ANTHROPIC_API_KEY")

def validate_key():
    """Test the API key with a minimal request"""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": "claude-3-haiku-20240307",
        "max_tokens": 10,
        "messages": [
            {"role": "user", "content": "Hi"}
        ]
    }

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=30.0)

        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text[:500]}")

        if response.status_code == 200:
            print("\n✅ API KEY IS VALID AND WORKING!")
            return True
        elif response.status_code == 401:
            print("\n❌ API KEY IS INVALID (401 authentication error)")
            return False
        else:
            print(f"\n⚠️  Unexpected status code: {response.status_code}")
            return False

    except Exception as e:
        print(f"\n❌ Error testing API key: {e}")
        return False

if __name__ == "__main__":
    valid = validate_key()
    sys.exit(0 if valid else 1)
