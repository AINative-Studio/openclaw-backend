#!/usr/bin/env python3
"""Check which Anthropic models are available with the API key"""

import httpx
import json
import os

API_KEY = os.getenv("ANTHROPIC_API_KEY")

# All current Anthropic models as of 2025
MODELS_TO_TEST = [
    "claude-3-5-sonnet-20241022",
    "claude-3-5-sonnet-20240620",
    "claude-3-5-haiku-20241022",
    "claude-3-opus-20240229",
    "claude-3-sonnet-20240229",
    "claude-3-haiku-20240307",
    "claude-2.1",
    "claude-2.0",
]

def test_model(model_name):
    """Test if a model is accessible"""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

    payload = {
        "model": model_name,
        "max_tokens": 5,
        "messages": [{"role": "user", "content": "Hi"}]
    }

    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=10.0)

        if response.status_code == 200:
            data = response.json()
            return {
                "available": True,
                "model": model_name,
                "response": data.get("content", [{}])[0].get("text", ""),
                "tokens": data.get("usage", {})
            }
        elif response.status_code == 404:
            return {"available": False, "model": model_name, "reason": "Model not found"}
        elif response.status_code == 401:
            return {"available": False, "model": model_name, "reason": "Authentication error"}
        else:
            return {"available": False, "model": model_name, "reason": f"HTTP {response.status_code}"}
    except Exception as e:
        return {"available": False, "model": model_name, "reason": str(e)}

print("Testing Anthropic models...\n")
print("=" * 80)

available_models = []
unavailable_models = []

for model in MODELS_TO_TEST:
    print(f"Testing: {model}...", end=" ")
    result = test_model(model)

    if result["available"]:
        print(f"✅ AVAILABLE")
        available_models.append(result)
        print(f"   Sample: {result['response'][:50]}...")
        print(f"   Tokens: {result['tokens']}")
    else:
        print(f"❌ Not available - {result['reason']}")
        unavailable_models.append(result)
    print()

print("=" * 80)
print(f"\n📊 SUMMARY:")
print(f"   Available: {len(available_models)}")
print(f"   Unavailable: {len(unavailable_models)}")

if available_models:
    print(f"\n✅ AVAILABLE MODELS:")
    for model in available_models:
        print(f"   - {model['model']}")

print("\n💡 RECOMMENDED FOR OPENCLAW:")
if available_models:
    # Prefer Sonnet 3.5 if available, otherwise Haiku
    sonnet_35 = [m for m in available_models if "3-5-sonnet" in m["model"]]
    haiku_35 = [m for m in available_models if "3-5-haiku" in m["model"]]
    opus_3 = [m for m in available_models if "3-opus" in m["model"]]

    if sonnet_35:
        print(f"   Best: {sonnet_35[0]['model']} (Most capable)")
    if haiku_35:
        print(f"   Fast: {haiku_35[0]['model']} (Fastest, cheapest)")
    if opus_3:
        print(f"   Premium: {opus_3[0]['model']} (Most intelligent)")
