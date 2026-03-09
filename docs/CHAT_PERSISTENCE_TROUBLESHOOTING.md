# Chat Persistence Troubleshooting Guide

**Epic E9 - Chat Persistence**
**Version:** 1.0
**Last Updated:** 2026-03-08

---

## Table of Contents

1. [Common Issues](#common-issues)
2. [Error Messages](#error-messages)
3. [Database Issues](#database-issues)
4. [ZeroDB Connection Issues](#zerodb-connection-issues)
5. [Performance Problems](#performance-problems)
6. [Data Consistency Issues](#data-consistency-issues)
7. [Migration Failures](#migration-failures)
8. [API Errors](#api-errors)
9. [Debugging Tools](#debugging-tools)
10. [Prevention Tips](#prevention-tips)

---

## Common Issues

### Issue 1: "Conversation not found" (404 Error)

**Symptom**: API returns 404 when trying to access a conversation.

**Possible Causes**:
1. Conversation was deleted
2. Wrong conversation ID in request
3. Conversation belongs to different workspace
4. Database connection lost

**Solution Steps**:

```bash
# 1. Verify conversation exists in database
psql $DATABASE_URL -c "SELECT id, status, workspace_id FROM conversations WHERE id = 'your-uuid-here';"

# 2. Check if conversation was deleted or archived
psql $DATABASE_URL -c "SELECT id, status, archived_at FROM conversations WHERE id = 'your-uuid-here';"

# 3. Verify workspace association
psql $DATABASE_URL -c "
SELECT c.id, c.status, c.workspace_id, w.name as workspace_name
FROM conversations c
JOIN workspaces w ON c.workspace_id = w.id
WHERE c.id = 'your-uuid-here';
"

# 4. Test database connection
psql $DATABASE_URL -c "SELECT NOW();"
```

**Prevention**:
- Always validate UUIDs before database queries
- Implement soft deletes instead of hard deletes
- Add workspace_id to all queries for proper isolation

---

### Issue 2: ZeroDB Connection Timeout

**Symptom**: Requests hang or timeout when creating/retrieving messages.

**Error Message**:
```
ZeroDBConnectionError: Connection timeout after 30s
```

**Solution Steps**:

```bash
# 1. Test ZeroDB API connectivity
curl -H "Authorization: Bearer $ZERODB_API_KEY" \
  https://api.zerodb.io/v1/health

# Expected response: {"status": "ok"}

# 2. Verify API key is correct
echo $ZERODB_API_KEY

# 3. Check firewall/network rules
# Ensure outbound HTTPS (443) is allowed

# 4. Test from Python
python3 << 'EOF'
import asyncio
import os
from backend.integrations.zerodb_client import ZeroDBClient

async def test():
    async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as client:
        health = await client.health_check()
        print(f"ZeroDB health: {health}")

asyncio.run(test())
EOF
```

**Workaround**:
The system has graceful degradation for ZeroDB Memory API failures. Messages will still be stored in ZeroDB tables even if Memory API fails.

**Prevention**:
- Monitor ZeroDB API status
- Implement circuit breaker pattern for external API calls
- Set appropriate timeout values (default: 30s)

---

### Issue 3: Message Count Mismatch

**Symptom**: `Conversation.message_count` doesn't match actual messages in ZeroDB.

**Possible Causes**:
1. ZeroDB write failure after metadata update
2. Race condition in concurrent message creation
3. Manual database modification

**Diagnostic Query**:

```python
# Check message count consistency
from backend.services.conversation_service import ConversationService

async def diagnose_count_mismatch(conversation_id):
    # Get count from PostgreSQL
    conversation = await service.get_conversation(conversation_id)
    pg_count = conversation.message_count

    # Get actual count from ZeroDB
    messages = await service.get_messages(conversation_id, limit=10000, offset=0)
    zerodb_count = len(messages)

    print(f"PostgreSQL count: {pg_count}")
    print(f"ZeroDB count: {zerodb_count}")
    print(f"Mismatch: {abs(pg_count - zerodb_count)}")

    return pg_count, zerodb_count
```

**Solution**:

```python
# Recalculate and fix message count
async def fix_message_count(conversation_id):
    from sqlalchemy import select, update
    from backend.models.conversation import Conversation

    # Get actual message count from ZeroDB
    messages = await service.get_messages(conversation_id, limit=10000, offset=0)
    actual_count = len(messages)

    # Update PostgreSQL
    stmt = (
        update(Conversation)
        .where(Conversation.id == conversation_id)
        .values(message_count=actual_count)
    )
    await db.execute(stmt)
    await db.commit()

    print(f"Fixed message_count to {actual_count}")
```

**Prevention**:
- Use database transactions for message creation
- Add periodic reconciliation job
- Implement idempotent message creation

---

### Issue 4: Workspace Missing ZeroDB Project

**Symptom**: "Workspace does not have a ZeroDB project configured"

**Error Message**:
```
ValueError: Workspace 789e4567-e89b-12d3-a456-426614174111 does not have a ZeroDB project configured
```

**Solution**:

```bash
# 1. Check which workspaces are missing ZeroDB projects
psql $DATABASE_URL -c "
SELECT id, name, zerodb_project_id
FROM workspaces
WHERE zerodb_project_id IS NULL;
"

# 2. Provision ZeroDB project for workspace
python3 << 'EOF'
import asyncio
import os
from uuid import UUID
from backend.integrations.zerodb_client import ZeroDBClient
from backend.db.base import get_async_db
from backend.models.workspace import Workspace

async def provision_workspace(workspace_id_str):
    workspace_id = UUID(workspace_id_str)

    async for db in get_async_db():
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            # Create ZeroDB project
            project = await zerodb.create_project(
                name=f"workspace_{workspace_id}",
                description="OpenClaw workspace storage"
            )

            # Update workspace
            workspace = await db.get(Workspace, workspace_id)
            workspace.zerodb_project_id = project["id"]
            await db.commit()

            print(f"✓ Provisioned project {project['id']} for workspace {workspace_id}")
        break

asyncio.run(provision_workspace("your-workspace-uuid"))
EOF
```

**Prevention**:
- Provision ZeroDB project automatically during workspace creation
- Add validation check in workspace creation endpoint
- Monitor workspaces for missing ZeroDB projects

---

### Issue 5: Migration Conflicts

**Symptom**: Alembic migration fails with "relation already exists" or "column already exists"

**Error Message**:
```
sqlalchemy.exc.ProgrammingError: (psycopg2.errors.DuplicateTable) relation "conversations" already exists
```

**Solution**:

```bash
# 1. Check current migration version
alembic current

# 2. Check migration history
alembic history

# 3. Check if tables exist manually
psql $DATABASE_URL -c "\dt"

# 4. If tables exist but Alembic thinks they don't, stamp the database
alembic stamp head

# 5. If migration is partially applied, rollback and retry
alembic downgrade -1
alembic upgrade head
```

**For Clean Database Reset** (⚠️ Data Loss):

```bash
# Backup first!
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# Drop all tables
psql $DATABASE_URL << 'EOF'
DROP TABLE IF EXISTS alembic_version CASCADE;
DROP TABLE IF EXISTS conversations CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS workspaces CASCADE;
DROP TABLE IF EXISTS agent_swarm_instances CASCADE;
EOF

# Re-run migrations from scratch
alembic upgrade head
```

**Prevention**:
- Always test migrations on staging first
- Never manually create tables managed by Alembic
- Use `alembic stamp` to mark existing schema as migrated

---

## Error Messages

### Error: "InvalidUUID" (422 Unprocessable Entity)

**Cause**: Malformed UUID in request.

**Solution**:
```python
from uuid import UUID

# Validate UUID before sending
try:
    conversation_id = UUID("123e4567-e89b-12d3-a456-426614174000")
except ValueError:
    print("Invalid UUID format")
```

**Valid UUID Format**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx` (8-4-4-4-12 hex digits)

---

### Error: "field required" (422 Unprocessable Entity)

**Cause**: Missing required field in request body.

**Solution**:
```bash
# Check request body matches schema
curl -X POST "http://localhost:8000/conversations" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
    "agent_id": "456e4567-e89b-12d3-a456-426614174222",
    "user_id": "987e4567-e89b-12d3-a456-426614174333"
  }'

# All three fields are required for POST /conversations
```

---

### Error: "duplicate key value violates unique constraint"

**Cause**: Attempting to create conversation with duplicate `(channel, channel_conversation_id)`.

**Error Message**:
```
IntegrityError: duplicate key value violates unique constraint "ix_conversations_channel_conversation_id"
```

**Solution**:
```python
# Check if conversation already exists before creating
existing = await service.get_conversation_by_session_key(session_key)
if existing:
    print(f"Conversation already exists: {existing.id}")
else:
    conversation = await service.create_conversation(...)
```

**Prevention**:
- Use `get_or_create` pattern
- Handle `IntegrityError` gracefully in code

---

## Database Issues

### Issue: Slow Query Performance

**Symptom**: Queries take > 1 second to return.

**Diagnostic**:

```sql
-- Enable query timing
\timing

-- Check slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
WHERE mean_exec_time > 1000  -- > 1 second
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Check missing indexes
SELECT schemaname, tablename, attname, n_distinct, correlation
FROM pg_stats
WHERE schemaname = 'public'
  AND tablename = 'conversations'
ORDER BY abs(correlation) DESC;
```

**Solution**:

```sql
-- Create missing indexes
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_workspace_id
ON conversations(workspace_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_user_id
ON conversations(user_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_agent_id
ON conversations(agent_swarm_instance_id);

CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_conversations_status
ON conversations(status);

-- Analyze tables to update statistics
ANALYZE conversations;
ANALYZE users;
ANALYZE workspaces;
```

---

### Issue: Connection Pool Exhausted

**Symptom**: "QueuePool limit exceeded" or "too many connections"

**Error Message**:
```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 20 overflow 40 reached, connection timed out
```

**Solution**:

```python
# In backend/db/base.py, increase pool size
from sqlalchemy.ext.asyncio import create_async_engine

engine = create_async_engine(
    DATABASE_URL,
    pool_size=40,          # Increase from 20
    max_overflow=80,       # Increase from 40
    pool_pre_ping=True,
    pool_recycle=3600
)
```

**Prevention**:
- Always close database sessions after use
- Use context managers (`async with`)
- Monitor connection pool metrics

---

## ZeroDB Connection Issues

### Issue: API Rate Limit Exceeded

**Symptom**: ZeroDB returns 429 status code.

**Error Message**:
```
ZeroDBAPIError: Rate limit exceeded (429)
```

**Solution**:

```python
# Implement exponential backoff retry
import asyncio
from tenacity import retry, wait_exponential, stop_after_attempt

@retry(wait=wait_exponential(multiplier=1, min=4, max=60), stop=stop_after_attempt(5))
async def add_message_with_retry(conversation_id, role, content):
    return await service.add_message(conversation_id, role, content)

# Use batching for bulk operations
async def add_messages_batch(messages):
    for message in messages:
        await add_message_with_retry(...)
        await asyncio.sleep(0.1)  # Rate limit to 10/second
```

**ZeroDB Rate Limits** (check documentation):
- Table operations: 100 requests/second
- Memory API: 50 requests/second

---

## Performance Problems

### Issue: Message Retrieval Too Slow

**Symptom**: `GET /conversations/{id}/messages` takes > 1 second.

**Diagnostic**:

```python
import time

async def diagnose_slow_retrieval(conversation_id):
    start = time.time()
    messages = await service.get_messages(conversation_id, limit=50)
    elapsed = time.time() - start

    print(f"Retrieved {len(messages)} messages in {elapsed:.2f}s")

    if elapsed > 1.0:
        print("⚠️ Slow query detected!")
        print("Possible causes:")
        print("1. ZeroDB connection latency")
        print("2. Large message payloads")
        print("3. Network issues")
```

**Solutions**:

1. **Use Pagination**:
```python
# Bad: Load all 10,000 messages
messages = await service.get_messages(conversation_id, limit=10000)

# Good: Paginate
messages = await service.get_messages(conversation_id, limit=50, offset=0)
```

2. **Implement Caching**:
```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def cache_recent_messages(conversation_id, limit, offset):
    # Cache key includes all parameters
    return service.get_messages(conversation_id, limit, offset)
```

3. **Compress Large Payloads**:
```python
import gzip
import json

# Compress response for frontend
compressed = gzip.compress(json.dumps(messages).encode())
```

---

### Issue: High Memory Usage

**Symptom**: Backend server runs out of memory or crashes.

**Diagnostic**:

```python
import tracemalloc

tracemalloc.start()

# Your code here
messages = await service.get_messages(conversation_id, limit=10000)

current, peak = tracemalloc.get_traced_memory()
print(f"Current memory: {current / 1024 / 1024:.2f} MB")
print(f"Peak memory: {peak / 1024 / 1024:.2f} MB")
tracemalloc.stop()
```

**Solutions**:

1. **Limit Query Size**:
```python
# Enforce maximum limit
MAX_LIMIT = 200

async def get_messages(conversation_id, limit=50, offset=0):
    limit = min(limit, MAX_LIMIT)
    return await service.get_messages(conversation_id, limit, offset)
```

2. **Stream Large Responses**:
```python
from fastapi.responses import StreamingResponse

@app.get("/conversations/{id}/messages/stream")
async def stream_messages(conversation_id: UUID):
    async def generate():
        offset = 0
        while True:
            messages = await service.get_messages(conversation_id, limit=50, offset=offset)
            if not messages:
                break
            yield json.dumps(messages).encode() + b"\n"
            offset += 50

    return StreamingResponse(generate(), media_type="application/x-ndjson")
```

---

## Data Consistency Issues

### Issue: Messages Missing from ZeroDB

**Symptom**: `message_count` shows 10 messages, but ZeroDB query returns only 8.

**Diagnostic**:

```python
async def audit_message_consistency(conversation_id):
    # Get PostgreSQL count
    conversation = await service.get_conversation(conversation_id)
    pg_count = conversation.message_count

    # Get ZeroDB count
    messages = await service.get_messages(conversation_id, limit=10000)
    zerodb_count = len(messages)

    if pg_count != zerodb_count:
        print(f"❌ Inconsistency detected!")
        print(f"PostgreSQL: {pg_count}, ZeroDB: {zerodb_count}")
        print(f"Missing: {pg_count - zerodb_count} messages")

        # Check ZeroDB Memory API
        search_results = await service.search_conversation_semantic(
            conversation_id, query="*", limit=1000
        )
        memory_count = search_results["total"]
        print(f"ZeroDB Memory: {memory_count} messages")
```

**Solution**:

1. **Implement Reconciliation Job**:
```python
async def reconcile_conversation(conversation_id):
    """Reconcile message counts and missing messages."""

    # Get all messages from ZeroDB
    messages = await service.get_messages(conversation_id, limit=10000)

    # Update PostgreSQL count
    conversation = await service.get_conversation(conversation_id)
    conversation.message_count = len(messages)
    await db.commit()

    print(f"✓ Reconciled conversation {conversation_id}: {len(messages)} messages")
```

2. **Enable Audit Logging**:
```python
# Log all message creation attempts
import logging

logger = logging.getLogger(__name__)

async def add_message_with_logging(conversation_id, role, content):
    try:
        result = await service.add_message(conversation_id, role, content)
        logger.info(f"Message added: conv={conversation_id}, msg_id={result['id']}")
        return result
    except Exception as e:
        logger.error(f"Failed to add message: conv={conversation_id}, error={e}")
        raise
```

---

## Migration Failures

### Issue: Foreign Key Constraint Violation

**Error**:
```
ForeignKeyViolationError: insert or update on table "conversations" violates foreign key constraint
```

**Cause**: Referenced entity (workspace, user, agent) doesn't exist.

**Solution**:

```bash
# Check if referenced entities exist
psql $DATABASE_URL << 'EOF'
-- Check missing workspaces
SELECT c.id as conversation_id, c.workspace_id
FROM conversations c
LEFT JOIN workspaces w ON c.workspace_id = w.id
WHERE w.id IS NULL;

-- Check missing users
SELECT c.id as conversation_id, c.user_id
FROM conversations c
LEFT JOIN users u ON c.user_id = u.id
WHERE u.id IS NULL;

-- Check missing agents
SELECT c.id as conversation_id, c.agent_swarm_instance_id
FROM conversations c
LEFT JOIN agent_swarm_instances a ON c.agent_swarm_instance_id = a.id
WHERE a.id IS NULL AND c.agent_swarm_instance_id IS NOT NULL;
EOF
```

**Fix Orphaned Records**:

```sql
-- Option 1: Delete orphaned conversations
DELETE FROM conversations
WHERE workspace_id NOT IN (SELECT id FROM workspaces);

-- Option 2: Nullify agent references
UPDATE conversations
SET agent_swarm_instance_id = NULL
WHERE agent_swarm_instance_id NOT IN (SELECT id FROM agent_swarm_instances);
```

---

## API Errors

### Issue: 503 Service Unavailable

**Cause**: ZeroDB service is down or unreachable.

**Solution**:

```python
# Implement fallback behavior
from backend.integrations.zerodb_client import ZeroDBConnectionError

async def add_message_with_fallback(conversation_id, role, content):
    try:
        return await service.add_message(conversation_id, role, content)
    except ZeroDBConnectionError:
        # Fallback: Store in PostgreSQL JSON column temporarily
        logger.warning(f"ZeroDB unavailable, using fallback storage")

        conversation = await service.get_conversation(conversation_id)
        pending_messages = conversation.conversation_metadata.get("pending_messages", [])
        pending_messages.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        conversation.conversation_metadata["pending_messages"] = pending_messages
        await db.commit()

        # Schedule background job to flush pending messages
        # when ZeroDB comes back online
```

---

## Debugging Tools

### Tool 1: Database Query Analyzer

```python
# backend/utils/query_analyzer.py
import time
from contextlib import contextmanager

@contextmanager
def analyze_query(description: str):
    """Context manager to analyze query performance."""
    start = time.time()
    print(f"⏱️ Starting: {description}")

    try:
        yield
    finally:
        elapsed = time.time() - start
        print(f"✓ Completed: {description} in {elapsed:.3f}s")

        if elapsed > 1.0:
            print(f"⚠️ Slow query detected: {description}")

# Usage
async def test_performance():
    with analyze_query("List conversations"):
        conversations = await service.list_conversations(workspace_id, limit=50)

    with analyze_query("Get messages"):
        messages = await service.get_messages(conversation_id, limit=100)
```

### Tool 2: ZeroDB Connection Tester

```python
# scripts/test_zerodb_connection.py
import asyncio
import os
from backend.integrations.zerodb_client import ZeroDBClient

async def test_zerodb():
    """Test ZeroDB connectivity and performance."""
    api_key = os.getenv("ZERODB_API_KEY")

    if not api_key:
        print("❌ ZERODB_API_KEY not set")
        return

    async with ZeroDBClient(api_key=api_key) as client:
        # Test 1: Health check
        print("Test 1: Health check...")
        try:
            health = await client.health_check()
            print(f"✓ Health: {health}")
        except Exception as e:
            print(f"❌ Health check failed: {e}")

        # Test 2: Create table row
        print("\nTest 2: Create table row...")
        try:
            row = await client.create_table_row(
                project_id="test_project",
                table_name="test_messages",
                row_data={"content": "Test message"}
            )
            print(f"✓ Created row: {row.get('id')}")
        except Exception as e:
            print(f"❌ Create table row failed: {e}")

        # Test 3: Query table
        print("\nTest 3: Query table...")
        try:
            rows = await client.query_table(
                project_id="test_project",
                table_name="test_messages",
                limit=10
            )
            print(f"✓ Queried {len(rows)} rows")
        except Exception as e:
            print(f"❌ Query table failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_zerodb())
```

Run:
```bash
python scripts/test_zerodb_connection.py
```

### Tool 3: Conversation Integrity Checker

```python
# scripts/check_conversation_integrity.py
import asyncio
from uuid import UUID
from backend.db.base import get_async_db
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
import os

async def check_integrity(conversation_id: UUID):
    """Check conversation data integrity across PostgreSQL and ZeroDB."""

    async for db in get_async_db():
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            print(f"Checking conversation {conversation_id}...")

            # Check 1: Conversation exists
            conversation = await service.get_conversation(conversation_id)
            if not conversation:
                print("❌ Conversation not found in PostgreSQL")
                return

            print(f"✓ Conversation found: {conversation.id}")
            print(f"  Workspace: {conversation.workspace_id}")
            print(f"  User: {conversation.user_id}")
            print(f"  Agent: {conversation.agent_swarm_instance_id}")
            print(f"  Status: {conversation.status}")
            print(f"  Message count (PostgreSQL): {conversation.message_count}")

            # Check 2: Message count consistency
            messages = await service.get_messages(conversation_id, limit=10000)
            zerodb_count = len(messages)
            print(f"  Message count (ZeroDB): {zerodb_count}")

            if conversation.message_count != zerodb_count:
                print(f"❌ Count mismatch: PostgreSQL={conversation.message_count}, ZeroDB={zerodb_count}")
            else:
                print("✓ Message counts match")

            # Check 3: Foreign key integrity
            print("\nForeign key checks:")
            print(f"  Workspace exists: {conversation.workspace is not None}")
            print(f"  User exists: {conversation.user is not None}")
            print(f"  Agent exists: {conversation.agent_swarm_instance is not None}")

        break

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python check_conversation_integrity.py <conversation_id>")
        sys.exit(1)

    conversation_id = UUID(sys.argv[1])
    asyncio.run(check_integrity(conversation_id))
```

Run:
```bash
python scripts/check_conversation_integrity.py 123e4567-e89b-12d3-a456-426614174000
```

---

## Prevention Tips

### Tip 1: Always Use Transactions

```python
# Bad: No transaction
async def add_message_no_transaction(conversation_id, role, content):
    await zerodb.create_table_row(...)  # Might fail
    conversation.message_count += 1     # Gets incremented anyway
    await db.commit()                    # Inconsistent state

# Good: Use transaction
async def add_message_with_transaction(conversation_id, role, content):
    try:
        # All operations in transaction
        row = await zerodb.create_table_row(...)
        conversation.message_count += 1
        await db.commit()
    except Exception:
        await db.rollback()
        raise
```

### Tip 2: Implement Health Checks

```python
# backend/api/v1/endpoints/health.py
from fastapi import APIRouter

router = APIRouter()

@router.get("/health")
async def health_check():
    checks = {}

    # Check 1: Database
    try:
        await db.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"

    # Check 2: ZeroDB
    try:
        await zerodb_client.health_check()
        checks["zerodb"] = "ok"
    except Exception as e:
        checks["zerodb"] = f"error: {e}"

    # Overall status
    all_ok = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "checks": checks
    }
```

### Tip 3: Monitor Key Metrics

```python
# Monitor these metrics with Prometheus/Grafana
from prometheus_client import Counter, Histogram

message_creation_counter = Counter(
    "messages_created_total",
    "Total messages created",
    ["workspace_id", "status"]
)

message_creation_duration = Histogram(
    "message_creation_duration_seconds",
    "Time to create message",
    ["workspace_id"]
)

# Use in code
with message_creation_duration.labels(workspace_id=workspace_id).time():
    await service.add_message(...)

message_creation_counter.labels(workspace_id=workspace_id, status="success").inc()
```

### Tip 4: Implement Circuit Breaker

```python
from circuitbreaker import circuit

@circuit(failure_threshold=5, recovery_timeout=60)
async def add_message_with_circuit_breaker(conversation_id, role, content):
    """Fail fast if ZeroDB is consistently failing."""
    return await service.add_message(conversation_id, role, content)
```

---

## Getting Help

If you've tried all troubleshooting steps and still have issues:

1. **Check Logs**:
   ```bash
   # Backend logs
   tail -f logs/openclaw_backend.log

   # PostgreSQL logs
   tail -f /var/log/postgresql/postgresql-14-main.log
   ```

2. **Enable Debug Logging**:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   ```

3. **Run Integration Tests**:
   ```bash
   pytest tests/integration/test_chat_persistence_e2e.py -v
   ```

4. **Contact Support**:
   - Email: engineering@ainative.studio
   - Slack: #openclaw-support
   - GitHub Issues: [openclaw-backend/issues](https://github.com/ainative/openclaw-backend/issues)

---

## Additional Resources

- **Main Documentation**: [docs/CHAT_PERSISTENCE.md](CHAT_PERSISTENCE.md)
- **API Reference**: [docs/api/CONVERSATION_API.md](api/CONVERSATION_API.md)
- **Architecture Diagrams**: [docs/diagrams/chat-persistence-architecture.md](diagrams/chat-persistence-architecture.md)
- **Migration Guide**: [docs/CHAT_PERSISTENCE_MIGRATION.md](CHAT_PERSISTENCE_MIGRATION.md)

---

**Document Version**: 1.0
**Last Updated**: 2026-03-08
