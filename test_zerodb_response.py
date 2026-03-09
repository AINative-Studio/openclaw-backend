#!/usr/bin/env python3
"""Test script to debug ZeroDB response format"""

import asyncio
import os
from dotenv import load_dotenv
from backend.integrations.zerodb_client import ZeroDBClient

load_dotenv()

async def main():
    client = ZeroDBClient()
    project_id = os.getenv("ZERODB_PROJECT_ID")

    # Insert a test row
    print("Inserting test row...")
    insert_result = await client.insert_rows(
        table_name="openclaw_cache",
        rows=[{
            "key": "debug_test",
            "value": "debug_value",
            "expires_at": 9999999999
        }],
        project_id=project_id
    )
    print("INSERT result:", insert_result)
    print()

    # Query it back
    print("Querying test row...")
    query_result = await client.query_rows(
        table_name="openclaw_cache",
        filter_query={"key": {"$eq": "debug_test"}},
        project_id=project_id
    )
    print("QUERY result:", query_result)
    print("Type:", type(query_result))
    print()

    if isinstance(query_result, list):
        print("It's a list!")
        if query_result:
            print("First item:", query_result[0])
            print("Keys:", query_result[0].keys() if isinstance(query_result[0], dict) else "not a dict")
    elif isinstance(query_result, dict):
        print("It's a dict!")
        print("Keys:", query_result.keys())

if __name__ == "__main__":
    asyncio.run(main())
