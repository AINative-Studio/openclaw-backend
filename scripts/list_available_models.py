#!/usr/bin/env python3
"""List all models available via Anthropic API /v1/models endpoint"""

import httpx
import os
import json

API_KEY = os.getenv("ANTHROPIC_API_KEY")

def list_models():
    """Query the /v1/models endpoint"""
    url = "https://api.anthropic.com/v1/models"
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    try:
        response = httpx.get(url, headers=headers, timeout=10.0)

        print(f"Status Code: {response.status_code}\n")

        if response.status_code == 200:
            data = response.json()
            print("✅ API Response:")
            print(json.dumps(data, indent=2))

            # Extract and display model list if available
            if "data" in data:
                print("\n" + "=" * 80)
                print("AVAILABLE MODELS:")
                print("=" * 80)
                for model in data["data"]:
                    print(f"\nModel ID: {model.get('id')}")
                    print(f"  Type: {model.get('type')}")
                    print(f"  Display Name: {model.get('display_name', 'N/A')}")
                    print(f"  Created: {model.get('created_at', 'N/A')}")

            return True
        elif response.status_code == 404:
            print("❌ Endpoint not found (404)")
            print(f"Response: {response.text}")
            return False
        elif response.status_code == 401:
            print("❌ Authentication error (401)")
            print(f"Response: {response.text}")
            return False
        else:
            print(f"⚠️  Unexpected status code: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error querying API: {e}")
        return False

if __name__ == "__main__":
    list_models()
