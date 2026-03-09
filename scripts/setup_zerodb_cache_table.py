#!/usr/bin/env python3
"""
Setup ZeroDB Cache Table

Creates the openclaw_cache table in the ZeroDB project if it doesn't exist.
Run this script before running cache service tests.
"""

import asyncio
import httpx
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

API_KEY = os.getenv("ZERODB_API_KEY")
API_URL = os.getenv("ZERODB_API_URL", "https://api.ainative.studio/v1")
PROJECT_ID = os.getenv("ZERODB_PROJECT_ID")

if not API_KEY:
    raise ValueError("ZERODB_API_KEY not found in environment")
if not PROJECT_ID:
    raise ValueError("ZERODB_PROJECT_ID not found in environment")


async def create_table():
    """Create openclaw_cache table in ZeroDB project"""
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        # Create table
        print(f"Creating table 'openclaw_cache' in project '{PROJECT_ID}'...")

        try:
            response = await client.post(
                f"{API_URL}/public/{PROJECT_ID}/database/tables",
                headers=headers,
                json={"table_name": "openclaw_cache"}
            )

            if response.status_code == 200 or response.status_code == 201:
                print(f"✅ Table 'openclaw_cache' created successfully!")
                print(f"Response: {response.json()}")
            elif response.status_code == 409:
                print(f"ℹ️  Table 'openclaw_cache' already exists")
            else:
                print(f"❌ Failed to create table: {response.status_code}")
                print(f"Response: {response.text}")

        except Exception as e:
            print(f"❌ Error creating table: {e}")


if __name__ == "__main__":
    asyncio.run(create_table())
