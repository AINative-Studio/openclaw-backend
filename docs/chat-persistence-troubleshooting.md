# Chat Persistence Troubleshooting Guide

## Table of Contents

1. [Messages Not Persisting](#1-messages-not-persisting)
2. [Workspace Missing ZeroDB Project](#2-workspace-missing-zerodb-project)
3. [ZeroDB Connection Failures](#3-zerodb-connection-failures)
4. [Semantic Search Not Working](#4-semantic-search-not-working)
5. [Database Connection Issues](#5-database-connection-issues)
6. [Conversation Not Found](#6-conversation-not-found)
7. [API Endpoint 503 Errors](#7-api-endpoint-503-errors)
8. [Message Count Mismatch](#8-message-count-mismatch)
9. [Slow Query Performance](#9-slow-query-performance)
10. [Memory Leaks or High Resource Usage](#10-memory-leaks-or-high-resource-usage)

---

## 1. Messages Not Persisting

### Symptoms

- Agent sends/receives messages successfully via OpenClaw Gateway
- No conversations created in PostgreSQL database
- No error messages in logs
- API returns empty conversation list

### Diagnosis

**Step 1:** Check if bridge has persistence enabled

```bash
# Search backend logs for initialization message
grep "ProductionOpenClawBridge" logs/backend.log

# Expected (persistence enabled):
# "ProductionOpenClawBridge initialized with conversation persistence enabled"

# Problem (persistence disabled):
# "ProductionOpenClawBridge initialized without conversation persistence"
```

**Step 2:** Verify dependencies are provided to bridge

```python
# In AgentSwarmLifecycleService or wherever bridge is created
# Check this code:

bridge = ProductionOpenClawBridge(
    url=gateway_url,
    token=gateway_token,
    db=db,              # ← Must be provided
    zerodb_client=zerodb_client  # ← Must be provided
)

# If either is None, persistence won't work
```

**Step 3:** Check environment variables

```bash
# Verify both are set
echo $DATABASE_URL
echo $ZERODB_API_KEY

# Should print actual values, not empty
```

### Solution

**Solution 1:** Pass db and zerodb_client to bridge

```python
# File: backend/services/lifecycle_service.py (or similar)

from sqlalchemy.ext.asyncio import AsyncSession
from backend.integrations.zerodb_client import ZeroDBClient


class AgentSwarmLifecycleService:
    def __init__(self, db: AsyncSession):
        self.db = db
        # Initialize ZeroDB client
        self.zerodb_client = ZeroDBClient(
            api_key=os.getenv("ZERODB_API_KEY")
        )

    async def create_agent(self, ...):
        # Create bridge WITH persistence
        bridge = ProductionOpenClawBridge(
            url=os.getenv("OPENCLAW_GATEWAY_URL"),
            token=os.getenv("OPENCLAW_GATEWAY_TOKEN"),
            db=self.db,                    # ← Pass database session
            zerodb_client=self.zerodb_client  # ← Pass ZeroDB client
        )
        # ...
```

**Solution 2:** Verify environment variables are loaded

```bash
# Add to .env file (if missing)
DATABASE_URL=postgresql+asyncpg://user:password@host:port/db
ZERODB_API_KEY=zdb_your_api_key_here

# Restart backend server to reload environment
pkill -f "uvicorn backend.main:app"
uvicorn backend.main:app --reload
```

**Solution 3:** Check import availability

```python
# Run this to verify imports work
python -c "
from sqlalchemy.ext.asyncio import AsyncSession
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
print('All imports successful')
"

# If ImportError, install dependencies
pip install -r requirements.txt
```

### Verification

```bash
# Send a test message
curl -X POST "http://localhost:8000/api/v1/agents/{agent_id}/send" \
  -H "Content-Type: application/json" \
  -d '{"message": "Test message"}'

# Check if conversation created
psql $DATABASE_URL -c "SELECT COUNT(*) FROM conversations;"

# Should show 1 (or more)
```

---

## 2. Workspace Missing ZeroDB Project

### Symptoms

```
ValueError: Workspace 123e4567-e89b-12d3-a456-426614174000 does not have a ZeroDB project configured
```

This error occurs when trying to create a conversation for a workspace that doesn't have a linked ZeroDB project.

### Diagnosis

**Check workspace configuration:**

```bash
psql $DATABASE_URL -c "
    SELECT id, name, zerodb_project_id
    FROM workspaces
    WHERE id = '123e4567-e89b-12d3-a456-426614174000';
"

# Output:
#                  id                  |        name        | zerodb_project_id
# -------------------------------------+--------------------+-------------------
#  123e4567-e89b-12d3-a456-426614174000 | Default Workspace  | NULL

# Problem: zerodb_project_id is NULL
```

### Solution

**Option 1:** Auto-provision by creating an agent

```python
# When you create an agent, the system will auto-provision
# Just create an agent normally and the workspace will be configured

from backend.services.lifecycle_service import AgentSwarmLifecycleService

await lifecycle_service.create_agent(
    workspace_id=workspace_id,
    name="Test Agent",
    # ... other params
)
# This will create ZeroDB project if missing
```

**Option 2:** Manual provisioning script

```python
# File: scripts/provision_missing_zerodb_projects.py
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from backend.models.workspace import Workspace
from backend.integrations.zerodb_client import ZeroDBClient


async def provision_all():
    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            # Find workspaces without projects
            stmt = select(Workspace).where(Workspace.zerodb_project_id.is_(None))
            result = await db.execute(stmt)
            workspaces = result.scalars().all()

            for workspace in workspaces:
                print(f"Provisioning project for: {workspace.name}")

                project = await zerodb.create_project(
                    name=workspace.name,
                    description=f"ZeroDB project for {workspace.name}"
                )

                workspace.zerodb_project_id = project["id"]
                print(f"  Created: {project['id']}")

            await db.commit()
            print(f"Provisioned {len(workspaces)} projects")


asyncio.run(provision_all())
```

**Run the script:**

```bash
python scripts/provision_missing_zerodb_projects.py
```

**Option 3:** Manual SQL update (if project already exists)

```bash
# If you already created a ZeroDB project manually
# Update workspace with project ID

psql $DATABASE_URL -c "
    UPDATE workspaces
    SET zerodb_project_id = 'proj_abc123xyz'
    WHERE id = '123e4567-e89b-12d3-a456-426614174000';
"
```

### Verification

```bash
# Check workspace now has project
psql $DATABASE_URL -c "
    SELECT id, name, zerodb_project_id
    FROM workspaces;
"

# All workspaces should have non-NULL zerodb_project_id
```

---

## 3. ZeroDB Connection Failures

### Symptoms

```
WARNING: Failed to store message in ZeroDB: Connection error
```

or

```
ZeroDBConnectionError: Connection refused
```

Messages still sent to OpenClaw Gateway (graceful degradation), but not persisted.

### Diagnosis

**Step 1:** Test ZeroDB connectivity

```bash
python scripts/test_zerodb_connection.py
```

**Expected output (success):**

```
Testing ZeroDB connection...

1. Creating test project...
   ✓ Project created: proj_test123

2. Creating test table...
   ✓ Table created: test_messages

# ... more tests ...

✓ All tests passed - ZeroDB connection working correctly
```

**Expected output (failure):**

```
✗ Connection Error: [Errno 61] Connection refused
  Check ZERODB_API_URL and network connectivity
```

**Step 2:** Check API key

```bash
# Verify API key is set and valid
echo $ZERODB_API_KEY

# Should start with "zdb_"
# If empty or wrong format, regenerate from ainative.studio
```

**Step 3:** Check API URL

```bash
echo $ZERODB_API_URL

# Should be: https://api.ainative.studio
# Not: http://... (no HTTPS)
# Not: localhost or 127.0.0.1
```

### Solution

**Solution 1:** Fix API key

```bash
# Log into https://ainative.studio
# Navigate to Settings → API Keys
# Generate new key
# Copy to .env file

echo "ZERODB_API_KEY=zdb_new_key_here" >> .env

# Restart backend
```

**Solution 2:** Check network/firewall

```bash
# Test if API is reachable
curl -I https://api.ainative.studio/health

# Expected: HTTP 200 OK
# If timeout or connection refused, check:
# - Firewall settings
# - Proxy configuration
# - VPN blocking external APIs
```

**Solution 3:** Verify TLS/SSL certificates

```bash
# Test SSL connection
openssl s_client -connect api.ainative.studio:443 -showcerts

# Should complete TLS handshake
# If SSL error, update CA certificates:
# - macOS: Update Keychain certificates
# - Linux: sudo apt-get install ca-certificates
```

**Solution 4:** Use HTTP client debugging

```python
# Add to test script for detailed errors
import httpx

async with httpx.AsyncClient(timeout=30.0) as client:
    try:
        response = await client.get(
            "https://api.ainative.studio/health",
            headers={"Authorization": f"Bearer {api_key}"}
        )
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
    except httpx.ConnectError as e:
        print(f"Connection error: {e}")
    except httpx.TimeoutException as e:
        print(f"Timeout: {e}")
```

### Verification

```bash
# Full connection test
python scripts/test_zerodb_connection.py

# All 6 tests should pass
```

---

## 4. Semantic Search Not Working

### Symptoms

- Pagination works (messages visible via `/messages` endpoint)
- Semantic search returns empty results or very few results
- No errors in logs

### Diagnosis

**Step 1:** Check if messages stored in Memory API

```python
# Count messages in table vs memory
import asyncio
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os

async def diagnose():
    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            conversation_id = "your-conversation-id-here"

            # Get table messages
            table_messages = await service.get_messages(
                conversation_id=conversation_id,
                limit=100
            )
            print(f"Messages in table: {len(table_messages)}")

            # Get memory messages
            search_results = await service.search_conversation_semantic(
                conversation_id=conversation_id,
                query="anything",  # Generic query
                limit=100
            )
            print(f"Messages in memory: {search_results['total']}")

            # If mismatch, some messages not in Memory API

asyncio.run(diagnose())
```

**Step 2:** Check logs for memory storage failures

```bash
# Search for warning messages
grep "Memory storage failed" logs/backend.log

# If found, Memory API was unavailable during message storage
```

**Step 3:** Test Memory API directly

```python
# Test if Memory API works now
from backend.integrations.zerodb_client import ZeroDBClient

async with ZeroDBClient(api_key="your_key") as client:
    memory = await client.create_memory(
        title="Test",
        content="Test memory",
        type="test",
        tags=["test"],
        metadata={}
    )
    print(f"Created memory: {memory['id']}")

    results = await client.search_memories(
        query="test",
        limit=5
    )
    print(f"Found {len(results['results'])} results")
```

### Solution

**Solution 1:** Re-store existing messages in Memory API

```python
# File: scripts/backfill_memory_api.py
import asyncio
import os
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from backend.models.conversation import Conversation


async def backfill_memories():
    """Re-store all messages in Memory API."""

    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            # Get all conversations
            stmt = select(Conversation).where(Conversation.status == "active")
            result = await db.execute(stmt)
            conversations = result.scalars().all()

            for conv in conversations:
                print(f"Processing conversation: {conv.id}")

                # Get messages from table
                messages = await service.get_messages(
                    conversation_id=conv.id,
                    limit=1000
                )

                # Re-store in Memory API
                for msg in messages:
                    try:
                        await zerodb.create_memory(
                            title=f"Message in conversation {conv.id}",
                            content=msg["content"],
                            type="conversation",
                            tags=[str(conv.id), msg["role"]],
                            metadata={
                                "conversation_id": str(conv.id),
                                "role": msg["role"],
                                "timestamp": msg["timestamp"]
                            }
                        )
                        print(f"  ✓ Stored message: {msg['id']}")
                    except Exception as e:
                        print(f"  ✗ Failed: {e}")

            print("Backfill complete")


asyncio.run(backfill_memories())
```

**Run the backfill:**

```bash
python scripts/backfill_memory_api.py
```

**Solution 2:** Enable Memory API for future messages

Memory API storage is automatic. Just ensure:

1. `ZERODB_API_KEY` is valid
2. ZeroDB Memory API is accessible (test with `test_zerodb_connection.py`)
3. Bridge has persistence enabled (db and zerodb_client provided)

Future messages will store in both table and memory.

### Verification

```bash
# Test semantic search
curl -X POST "http://localhost:8000/api/v1/conversations/{id}/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "test query", "limit": 5}'

# Should return results
```

---

## 5. Database Connection Issues

### Symptoms

```
sqlalchemy.exc.OperationalError: could not connect to server
```

or

```
asyncpg.exceptions.ConnectionDoesNotExistError
```

### Diagnosis

**Step 1:** Test PostgreSQL connectivity

```bash
# Using psql
psql $DATABASE_URL -c "SELECT 1;"

# Expected: Single row with value 1
# Error: Check connection parameters
```

**Step 2:** Check DATABASE_URL format

```bash
echo $DATABASE_URL

# Correct format for async:
# postgresql+asyncpg://user:password@host:port/database

# Wrong (sync driver):
# postgresql://user:password@host:port/database
# (missing "+asyncpg")
```

**Step 3:** Test network connectivity

```bash
# Extract host and port from DATABASE_URL
# Example: yamabiko.proxy.rlwy.net:51955

nc -zv yamabiko.proxy.rlwy.net 51955

# Expected: Connection succeeded
# Error: Check firewall, VPN, network
```

### Solution

**Solution 1:** Fix DATABASE_URL format

```bash
# In .env file, ensure "+asyncpg" is present
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database

# Not:
# DATABASE_URL=postgresql://user:password@host:port/database
```

**Solution 2:** Check PostgreSQL is running

```bash
# For Railway (if using Railway PostgreSQL)
# Log into Railway dashboard
# Check "PostgreSQL" service is "Active"
# If "Sleeping", deploy or wake it

# For local PostgreSQL:
brew services list | grep postgresql
# Or:
systemctl status postgresql
```

**Solution 3:** Verify credentials

```bash
# Test with explicit credentials
psql "postgresql://user:password@host:port/database" -c "SELECT 1;"

# If "authentication failed", password is wrong
# Regenerate password in hosting provider (Railway, etc.)
```

**Solution 4:** Check connection pooling

```python
# If "too many connections" error, adjust pool size

from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    os.getenv("DATABASE_URL"),
    pool_size=5,        # Default: 5
    max_overflow=10,    # Default: 10
    pool_pre_ping=True  # Test connections before use
)
```

### Verification

```bash
# Run database migrations (tests connection)
alembic upgrade head

# Should complete without errors
```

---

## 6. Conversation Not Found

### Symptoms

```
404 Not Found: Conversation with ID '...' not found
```

When trying to access messages or search.

### Diagnosis

**Step 1:** Verify conversation exists

```bash
psql $DATABASE_URL -c "
    SELECT id, workspace_id, agent_id, message_count, status
    FROM conversations
    WHERE id = '123e4567-e89b-12d3-a456-426614174000';
"

# If no rows, conversation doesn't exist
# If status='deleted', conversation was deleted
```

**Step 2:** Check if conversation was archived

```bash
psql $DATABASE_URL -c "
    SELECT id, status
    FROM conversations
    WHERE id = '123e4567-e89b-12d3-a456-426614174000';
"

# If status='archived', API may be filtering it out
```

### Solution

**Solution 1:** Create conversation if missing

```python
# File: scripts/create_conversation.py
import asyncio
import os
from uuid import UUID
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


async def create():
    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            conversation = await service.create_conversation(
                workspace_id=UUID("workspace-id-here"),
                agent_id=UUID("agent-id-here"),
                user_id=UUID("user-id-here"),
                openclaw_session_key="session_key_here"
            )

            print(f"Created conversation: {conversation.id}")


asyncio.run(create())
```

**Solution 2:** Unarchive conversation

```bash
psql $DATABASE_URL -c "
    UPDATE conversations
    SET status = 'active'
    WHERE id = '123e4567-e89b-12d3-a456-426614174000';
"
```

**Solution 3:** Check API filters

```bash
# If using filters, remove them
curl -X GET "http://localhost:8000/api/v1/conversations"
# (no filters - should show all conversations)

# Instead of:
curl -X GET "http://localhost:8000/api/v1/conversations?status=active"
# (might be filtering out archived conversations)
```

### Verification

```bash
# Get conversation by ID
curl -X GET "http://localhost:8000/api/v1/conversations/{conversation_id}"

# Should return conversation details
```

---

## 7. API Endpoint 503 Errors

### Symptoms

```
503 Service Unavailable
Detail: "ZeroDB API key not configured"
```

When calling conversation endpoints.

### Diagnosis

**Check environment variable:**

```bash
echo $ZERODB_API_KEY

# Should print API key (starting with "zdb_")
# If empty, not set
```

### Solution

**Solution 1:** Set ZERODB_API_KEY

```bash
# Add to .env file
echo "ZERODB_API_KEY=zdb_your_key_here" >> .env

# Export for current session
export ZERODB_API_KEY=zdb_your_key_here

# Restart backend
pkill -f "uvicorn backend.main:app"
uvicorn backend.main:app --reload
```

**Solution 2:** Verify key is loaded by backend

```python
# Add debug logging to backend startup
# File: backend/main.py

import os
import logging

logger = logging.getLogger(__name__)

@app.on_event("startup")
async def startup():
    zerodb_key = os.getenv("ZERODB_API_KEY")
    if zerodb_key:
        logger.info(f"ZERODB_API_KEY loaded: {zerodb_key[:10]}...")
    else:
        logger.warning("ZERODB_API_KEY not set!")
```

**Solution 3:** Check environment loading

```bash
# If using systemd service
# Edit service file to load environment

[Service]
EnvironmentFile=/path/to/.env

# If using Docker
# Add to docker-compose.yml

services:
  backend:
    env_file:
      - .env
```

### Verification

```bash
# Test endpoint
curl -X GET "http://localhost:8000/api/v1/conversations"

# Should return 200 (not 503)
```

---

## 8. Message Count Mismatch

### Symptoms

- Conversation shows `message_count=5` in database
- But only 3 messages returned by `/messages` endpoint
- Or semantic search finds different count

### Diagnosis

**Check actual vs metadata:**

```python
import asyncio
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os


async def check_count():
    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            conversation_id = "your-id-here"

            # Get conversation metadata
            conv = await service.get_conversation(conversation_id)
            print(f"Metadata count: {conv.message_count}")

            # Get actual messages
            messages = await service.get_messages(
                conversation_id=conversation_id,
                limit=1000
            )
            print(f"Actual count: {len(messages)}")


asyncio.run(check_count())
```

### Solution

**Solution 1:** Recalculate message count

```python
# File: scripts/fix_message_counts.py
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from backend.models.conversation import Conversation
from backend.integrations.zerodb_client import ZeroDBClient


async def fix_counts():
    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            # Get all conversations
            stmt = select(Conversation)
            result = await db.execute(stmt)
            conversations = result.scalars().all()

            for conv in conversations:
                # Query actual message count from ZeroDB
                messages = await zerodb.query_table(
                    project_id=conv.workspace.zerodb_project_id,
                    table_name="messages",
                    limit=10000,
                    skip=0
                )

                actual_count = len(messages)
                if conv.message_count != actual_count:
                    print(f"Fixing {conv.id}: {conv.message_count} → {actual_count}")
                    conv.message_count = actual_count

            await db.commit()
            print("Fixed all message counts")


asyncio.run(fix_counts())
```

**Run the script:**

```bash
python scripts/fix_message_counts.py
```

### Verification

```bash
# Check counts match
psql $DATABASE_URL -c "
    SELECT id, message_count FROM conversations;
"

# Verify with API
curl -X GET "http://localhost:8000/api/v1/conversations/{id}/messages"
# Compare 'total' in response with database message_count
```

---

## 9. Slow Query Performance

### Symptoms

- API requests take >5 seconds
- Pagination slow with large conversations
- Database CPU usage high

### Diagnosis

**Step 1:** Check query execution time

```bash
# Enable PostgreSQL query logging
psql $DATABASE_URL -c "ALTER SYSTEM SET log_min_duration_statement = 1000;"
# (logs queries >1 second)

# Reload config
psql $DATABASE_URL -c "SELECT pg_reload_conf();"

# Check logs for slow queries
tail -f /var/log/postgresql/postgresql.log | grep "duration:"
```

**Step 2:** Check missing indexes

```bash
psql $DATABASE_URL -c "
    SELECT
        schemaname,
        tablename,
        indexname
    FROM pg_indexes
    WHERE tablename IN ('conversations', 'workspaces', 'users');
"

# Should show indexes on:
# - conversations: workspace_id, agent_id, user_id, status, openclaw_session_key
# - workspaces: zerodb_project_id
# - users: email, workspace_id
```

### Solution

**Solution 1:** Add missing indexes

```bash
# If indexes missing, create them
psql $DATABASE_URL -c "
    CREATE INDEX CONCURRENTLY idx_conversations_workspace
    ON conversations(workspace_id);

    CREATE INDEX CONCURRENTLY idx_conversations_agent
    ON conversations(agent_id);

    CREATE INDEX CONCURRENTLY idx_conversations_status
    ON conversations(status);
"
```

**Solution 2:** Optimize pagination queries

```python
# Use cursor-based pagination instead of offset
# (more efficient for large datasets)

# Instead of:
messages = await service.get_messages(
    conversation_id=conv_id,
    limit=50,
    offset=100  # Slow for large offsets
)

# Use timestamp cursor:
messages = await zerodb.query_table(
    project_id=project_id,
    table_name="messages",
    filters={"timestamp": {"$gt": last_timestamp}},  # Cursor
    limit=50
)
```

**Solution 3:** Reduce ZeroDB query limit

```python
# Don't fetch more than needed
messages = await service.get_messages(
    conversation_id=conv_id,
    limit=50,  # Good
    offset=0
)

# Instead of:
messages = await service.get_messages(
    conversation_id=conv_id,
    limit=10000,  # Slow!
    offset=0
)
```

### Verification

```bash
# Test query speed
time curl -X GET "http://localhost:8000/api/v1/conversations/{id}/messages?limit=50"

# Should complete in <1 second
```

---

## 10. Memory Leaks or High Resource Usage

### Symptoms

- Backend process memory usage grows over time
- Eventually crashes with `MemoryError` or killed by OS
- CPU usage consistently high

### Diagnosis

**Step 1:** Monitor memory usage

```bash
# Check process memory
ps aux | grep uvicorn

# Or use htop
htop -p $(pgrep -f uvicorn)
```

**Step 2:** Profile memory usage

```python
# Add memory profiling
# File: backend/main.py

import tracemalloc
tracemalloc.start()

@app.get("/debug/memory")
async def debug_memory():
    snapshot = tracemalloc.take_snapshot()
    top_stats = snapshot.statistics("lineno")

    return {
        "top_10": [
            {
                "file": str(stat.traceback),
                "size_mb": stat.size / 1024 / 1024
            }
            for stat in top_stats[:10]
        ]
    }
```

### Solution

**Solution 1:** Close ZeroDB clients properly

```python
# Always use context manager
async with ZeroDBClient(api_key=key) as client:
    # Use client
    pass
# Client auto-closed here

# Avoid:
client = ZeroDBClient(api_key=key)
# ... use client ...
# Client never closed! (memory leak)
```

**Solution 2:** Limit database connection pool

```python
# File: backend/db/base.py

from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    DATABASE_URL,
    pool_size=5,        # Limit concurrent connections
    max_overflow=10,    # Limit overflow
    pool_recycle=3600   # Recycle connections every hour
)
```

**Solution 3:** Add request timeout

```python
# File: backend/main.py

from fastapi import FastAPI
from starlette.middleware.base import BaseHTTPMiddleware
import asyncio


class TimeoutMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=30.0)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={"detail": "Request timeout"}
            )


app.add_middleware(TimeoutMiddleware)
```

**Solution 4:** Restart service periodically

```bash
# Add to cron (restart daily at 3 AM)
0 3 * * * systemctl restart openclaw-backend

# Or use process manager with auto-restart
# supervisord, pm2, etc.
```

### Verification

```bash
# Monitor memory over time
while true; do
    ps aux | grep uvicorn | grep -v grep | awk '{print $6}'
    sleep 60
done

# Memory should stay stable (not grow continuously)
```

---

## General Debugging Tips

### Enable Debug Logging

```python
# File: backend/main.py

import logging

logging.basicConfig(
    level=logging.DEBUG,  # Show all debug messages
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)

# Or per-module:
logging.getLogger("backend.services.conversation_service").setLevel(logging.DEBUG)
logging.getLogger("backend.integrations.zerodb_client").setLevel(logging.DEBUG)
```

### Check Backend Health

```bash
# Add health endpoint
curl -X GET "http://localhost:8000/health"

# Should return service status
```

### Review Recent Logs

```bash
# Backend logs
tail -f logs/backend.log

# PostgreSQL logs
tail -f /var/log/postgresql/postgresql.log

# OpenClaw Gateway logs
tail -f openclaw-gateway/logs/gateway.log
```

### Database Integrity Check

```bash
# Run this periodically
psql $DATABASE_URL -c "
    SELECT
        COUNT(*) as total_conversations,
        SUM(message_count) as total_messages,
        COUNT(DISTINCT workspace_id) as workspaces,
        COUNT(DISTINCT agent_id) as agents
    FROM conversations;
"

# Verify counts make sense
```

## Getting Help

If issue persists after trying solutions above:

1. Collect diagnostic info:
   - Backend logs (last 100 lines)
   - Database schema (`\d conversations` output)
   - Environment variables (redact secrets)
   - Error messages (full stack trace)

2. Check documentation:
   - [Architecture](chat-persistence-architecture.md)
   - [Setup Guide](chat-persistence-setup.md)
   - [API Reference](chat-persistence-api.md)

3. Search GitHub issues for similar problems

4. Open new issue with:
   - Clear description of problem
   - Steps to reproduce
   - Diagnostic info from step 1
   - What you've already tried
