# Chat Persistence Migration Guide

**Epic E9 - Chat Persistence**
**Version:** 1.0
**Last Updated:** 2026-03-08

---

## Table of Contents

1. [Overview](#overview)
2. [Pre-Migration Checklist](#pre-migration-checklist)
3. [Migration Steps](#migration-steps)
4. [Database Migrations](#database-migrations)
5. [Data Migration](#data-migration)
6. [Post-Migration Validation](#post-migration-validation)
7. [Rollback Procedures](#rollback-procedures)
8. [Troubleshooting](#troubleshooting)

---

## Overview

This guide covers migrating from legacy chat storage systems to the new Chat Persistence architecture (Epic E9).

### What's Changing

**Before (Legacy)**:
- No persistent conversation storage
- Messages stored in memory or temporary files
- No conversation context between sessions
- Agent restarts lose conversation history

**After (Epic E9)**:
- PostgreSQL for conversation metadata
- ZeroDB for persistent message storage
- Conversation history preserved across sessions
- Semantic search capabilities
- Multi-channel support

### Migration Timeline

| Phase | Duration | Description |
|-------|----------|-------------|
| Pre-migration | 1-2 days | Backups, setup, validation |
| Database migration | 1 hour | Run Alembic migrations |
| Data migration | 2-4 hours | Migrate existing conversations (if any) |
| Validation | 1-2 hours | Test functionality |
| **Total** | **2-3 days** | Including buffer time |

---

## Pre-Migration Checklist

Complete ALL items before starting migration:

### 1. Backup Existing Data

```bash
# Backup PostgreSQL database
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# Verify backup
ls -lh backup_*.sql

# Test restore (on separate test database)
createdb openclaw_test
psql openclaw_test < backup_*.sql
```

### 2. Verify Prerequisites

```bash
# Check PostgreSQL version (12+ required, 14+ recommended)
psql $DATABASE_URL -c "SELECT version();"

# Check Python version (3.10+ required)
python --version

# Check Alembic installed
alembic --version

# Verify environment variables set
echo "DATABASE_URL: $DATABASE_URL"
echo "ZERODB_API_KEY: ${ZERODB_API_KEY:0:10}..."  # Only show first 10 chars
```

### 3. Test Environment Setup

```bash
# Set up test environment
cp .env .env.backup
cp .env.example .env.test

# Run tests to ensure nothing is broken
pytest tests/ -v

# If tests pass, proceed
```

### 4. ZeroDB Setup

```bash
# Test ZeroDB connection
python3 << 'EOF'
import asyncio
import os
from backend.integrations.zerodb_client import ZeroDBClient

async def test():
    async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as client:
        try:
            health = await client.health_check()
            print(f"✓ ZeroDB connection OK: {health}")
        except Exception as e:
            print(f"❌ ZeroDB connection failed: {e}")

asyncio.run(test())
EOF
```

### 5. Schedule Maintenance Window

**Recommended maintenance window**: 2-4 hours during low traffic

During migration:
- Users may experience brief interruptions
- New conversations may be unavailable for ~15 minutes
- Existing conversations remain accessible

---

## Migration Steps

### Step 1: Enable Maintenance Mode

```bash
# Create maintenance mode file
touch .maintenance_mode

# Update load balancer health check to return 503
# (Implementation depends on your setup)
```

### Step 2: Stop Background Workers

```bash
# Stop Celery workers (if running)
pkill -f celery

# Stop any scheduled tasks
# (Implementation specific)
```

### Step 3: Run Database Migrations

```bash
# Navigate to project directory
cd /Users/aideveloper/openclaw-backend

# Activate virtual environment
source venv/bin/activate

# Check current migration version
alembic current

# Show pending migrations
alembic show head

# Run migrations
alembic upgrade head

# Expected output:
# INFO  [alembic.runtime.migration] Running upgrade -> add_user_model
# INFO  [alembic.runtime.migration] Running upgrade add_user_model -> add_conversation_model
# INFO  [alembic.runtime.migration] Running upgrade add_conversation_model -> update_conversation_model_for_issue_103
# INFO  [alembic.runtime.migration] Running upgrade update_conversation_model_for_issue_103 -> add_current_conversation_id_to_agent

# Verify migrations completed
alembic current
```

### Step 4: Verify Schema

```bash
# Check tables created
psql $DATABASE_URL -c "\dt"

# Expected tables:
# - workspaces
# - users
# - conversations
# - agent_swarm_instances
# - alembic_version

# Verify conversations table structure
psql $DATABASE_URL -c "\d conversations"

# Expected columns:
# - id (uuid, PK)
# - workspace_id (uuid, FK)
# - user_id (uuid, FK)
# - agent_swarm_instance_id (uuid, FK, nullable)
# - channel (varchar)
# - channel_conversation_id (varchar)
# - title (varchar, nullable)
# - conversation_metadata (json)
# - status (enum)
# - created_at (timestamp)
# - updated_at (timestamp)
# - archived_at (timestamp, nullable)
```

### Step 5: Provision ZeroDB Projects

```bash
# Provision ZeroDB project for each workspace
python3 << 'EOF'
import asyncio
import os
from backend.db.base import get_async_db
from backend.models.workspace import Workspace
from backend.integrations.zerodb_client import ZeroDBClient
from sqlalchemy import select

async def provision_all_workspaces():
    async for db in get_async_db():
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            # Get all workspaces
            stmt = select(Workspace)
            result = await db.execute(stmt)
            workspaces = result.scalars().all()

            for workspace in workspaces:
                if workspace.zerodb_project_id:
                    print(f"✓ Workspace {workspace.name} already has project: {workspace.zerodb_project_id}")
                    continue

                # Create ZeroDB project
                project = await zerodb.create_project(
                    name=f"workspace_{workspace.id}",
                    description=f"OpenClaw workspace: {workspace.name}"
                )

                # Update workspace
                workspace.zerodb_project_id = project["id"]
                await db.commit()

                print(f"✓ Provisioned project {project['id']} for workspace {workspace.name}")

        break

asyncio.run(provision_all_workspaces())
EOF
```

### Step 6: Test Conversation Creation

```bash
# Test conversation creation
python3 << 'EOF'
import asyncio
from uuid import uuid4
from backend.db.base import get_async_db
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
from backend.models.workspace import Workspace
from backend.models.user import User
from backend.models.agent_swarm_lifecycle import AgentSwarmInstance
from sqlalchemy import select
import os

async def test_conversation():
    async for db in get_async_db():
        # Get first workspace
        stmt = select(Workspace).limit(1)
        result = await db.execute(stmt)
        workspace = result.scalar_one_or_none()

        if not workspace:
            print("❌ No workspaces found. Create a workspace first.")
            return

        print(f"Using workspace: {workspace.name} ({workspace.id})")

        # Get or create user
        stmt = select(User).where(User.workspace_id == workspace.id).limit(1)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                id=uuid4(),
                email="test@example.com",
                full_name="Test User",
                workspace_id=workspace.id
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"✓ Created test user: {user.email}")
        else:
            print(f"Using existing user: {user.email}")

        # Get or create agent
        stmt = select(AgentSwarmInstance).where(AgentSwarmInstance.workspace_id == workspace.id).limit(1)
        result = await db.execute(stmt)
        agent = result.scalar_one_or_none()

        if not agent:
            print("❌ No agents found. Create an agent first.")
            return

        print(f"Using agent: {agent.name} ({agent.id})")

        # Create conversation
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            conversation = await service.create_conversation(
                workspace_id=workspace.id,
                agent_id=agent.id,
                user_id=user.id
            )

            print(f"✓ Created conversation: {conversation.id}")

            # Add test message
            message = await service.add_message(
                conversation_id=conversation.id,
                role="user",
                content="Hello, this is a test migration message!"
            )

            print(f"✓ Added message: {message['id']}")

            # Retrieve messages
            messages = await service.get_messages(conversation.id, limit=10)
            print(f"✓ Retrieved {len(messages)} messages")

            print("\n✓ Migration test successful!")

        break

asyncio.run(test_conversation())
EOF
```

### Step 7: Restart Services

```bash
# Remove maintenance mode
rm .maintenance_mode

# Restart application servers
systemctl restart openclaw-backend

# Or with Docker Compose
docker-compose restart backend

# Verify services running
curl http://localhost:8000/health
```

---

## Database Migrations

### Migration Details

The following Alembic migrations are applied:

#### 1. Add User Model
**File**: `alembic/versions/xxx_add_user_model.py`

Creates `users` table:
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    full_name VARCHAR(255),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX ix_users_email ON users(email);
CREATE INDEX ix_users_workspace_id ON users(workspace_id);
```

#### 2. Add Conversation Model
**File**: `alembic/versions/xxx_add_conversation_model.py`

Creates `conversations` table:
```sql
CREATE TABLE conversations (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    agent_swarm_instance_id UUID REFERENCES agent_swarm_instances(id) ON DELETE SET NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX ix_conversations_workspace_id ON conversations(workspace_id);
CREATE INDEX ix_conversations_user_id ON conversations(user_id);
CREATE INDEX ix_conversations_agent_id ON conversations(agent_swarm_instance_id);
```

#### 3. Update Conversation Model (Issue #103)
**File**: `alembic/versions/xxx_update_conversation_model_for_issue_103.py`

Adds multi-channel support:
```sql
ALTER TABLE conversations
ADD COLUMN channel VARCHAR(50) NOT NULL DEFAULT 'whatsapp',
ADD COLUMN channel_conversation_id VARCHAR(255) NOT NULL DEFAULT '',
ADD COLUMN title VARCHAR(500),
ADD COLUMN conversation_metadata JSON NOT NULL DEFAULT '{}',
ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active',
ADD COLUMN archived_at TIMESTAMP WITH TIME ZONE;

CREATE TYPE conversation_status AS ENUM ('active', 'archived', 'deleted');
ALTER TABLE conversations ALTER COLUMN status TYPE conversation_status USING status::conversation_status;

CREATE UNIQUE INDEX ix_conversations_channel_conversation_id
ON conversations(channel, channel_conversation_id);

CREATE INDEX ix_conversations_status ON conversations(status);
```

#### 4. Add Current Conversation to Agent
**File**: `alembic/versions/xxx_add_current_conversation_id_to_agent.py`

Links agents to conversations:
```sql
ALTER TABLE agent_swarm_instances
ADD COLUMN current_conversation_id UUID REFERENCES conversations(id) ON DELETE SET NULL;

CREATE INDEX ix_agent_swarm_instances_current_conversation_id
ON agent_swarm_instances(current_conversation_id);
```

### Manual Migration (If Alembic Fails)

If Alembic migrations fail, you can apply manually:

```bash
# Run each migration SQL file
psql $DATABASE_URL < alembic/versions/xxx_add_user_model.sql
psql $DATABASE_URL < alembic/versions/xxx_add_conversation_model.sql
psql $DATABASE_URL < alembic/versions/xxx_update_conversation_model_for_issue_103.sql
psql $DATABASE_URL < alembic/versions/xxx_add_current_conversation_id_to_agent.sql

# Update alembic_version table
psql $DATABASE_URL -c "
INSERT INTO alembic_version (version_num)
VALUES ('head_migration_version')
ON CONFLICT (version_num) DO UPDATE SET version_num = EXCLUDED.version_num;
"
```

---

## Data Migration

### Migrating Existing Conversations (If Any)

If you have conversations stored in a legacy system:

```python
# scripts/migrate_legacy_conversations.py
import asyncio
from uuid import UUID
from backend.db.base import get_async_db
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
import os

async def migrate_legacy_conversations(legacy_data):
    """
    Migrate conversations from legacy system to new schema.

    legacy_data format:
    [
        {
            "workspace_id": "uuid",
            "user_email": "user@example.com",
            "agent_id": "uuid",
            "messages": [
                {"role": "user", "content": "...", "timestamp": "..."},
                {"role": "assistant", "content": "...", "timestamp": "..."}
            ]
        }
    ]
    """
    async for db in get_async_db():
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            for legacy_conv in legacy_data:
                try:
                    # Create conversation
                    conversation = await service.create_conversation(
                        workspace_id=UUID(legacy_conv["workspace_id"]),
                        agent_id=UUID(legacy_conv["agent_id"]),
                        user_id=UUID(legacy_conv["user_id"])
                    )

                    print(f"✓ Created conversation: {conversation.id}")

                    # Migrate messages
                    for msg in legacy_conv["messages"]:
                        await service.add_message(
                            conversation_id=conversation.id,
                            role=msg["role"],
                            content=msg["content"],
                            metadata={"migrated": True, "original_timestamp": msg.get("timestamp")}
                        )

                    print(f"  ✓ Migrated {len(legacy_conv['messages'])} messages")

                except Exception as e:
                    print(f"  ❌ Failed to migrate conversation: {e}")

        break

# Load legacy data and migrate
# legacy_data = load_from_file("legacy_conversations.json")
# asyncio.run(migrate_legacy_conversations(legacy_data))
```

---

## Post-Migration Validation

### Validation Checklist

Run ALL validation checks:

```bash
# 1. Verify tables exist
psql $DATABASE_URL -c "
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN ('users', 'conversations', 'workspaces', 'agent_swarm_instances');
"

# Expected: 4 tables

# 2. Verify indexes created
psql $DATABASE_URL -c "
SELECT indexname
FROM pg_indexes
WHERE tablename = 'conversations';
"

# Expected indexes:
# - conversations_pkey
# - ix_conversations_workspace_id
# - ix_conversations_user_id
# - ix_conversations_agent_id
# - ix_conversations_channel_conversation_id
# - ix_conversations_status

# 3. Verify foreign keys
psql $DATABASE_URL -c "
SELECT conname, conrelid::regclass, confrelid::regclass
FROM pg_constraint
WHERE contype = 'f' AND conrelid = 'conversations'::regclass;
"

# Expected: 3 foreign keys (workspace_id, user_id, agent_swarm_instance_id)

# 4. Test conversation creation via API
curl -X POST "http://localhost:8000/conversations" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "your-workspace-uuid",
    "agent_id": "your-agent-uuid",
    "user_id": "your-user-uuid"
  }'

# Expected: 201 Created

# 5. Test message creation
CONV_ID="conversation-uuid-from-step-4"
curl -X POST "http://localhost:8000/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "user",
    "content": "Test message after migration"
  }'

# Expected: 201 Created

# 6. Test message retrieval
curl "http://localhost:8000/conversations/$CONV_ID/messages?limit=10"

# Expected: 200 OK with messages array
```

### Automated Validation Script

```bash
# Run integration tests
pytest tests/integration/test_chat_persistence_e2e.py -v

# Expected: All tests passing
```

### Performance Validation

```bash
# Test query performance
python3 << 'EOF'
import asyncio
import time
from backend.db.base import get_async_db
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient
from uuid import UUID
import os

async def validate_performance():
    async for db in get_async_db():
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            # Test 1: List conversations (should be < 300ms)
            start = time.time()
            conversations, total = await service.list_conversations(limit=50)
            elapsed = time.time() - start
            print(f"List conversations: {elapsed*1000:.0f}ms (target: <300ms)")

            if not conversations:
                print("No conversations to test. Create some first.")
                return

            conv_id = conversations[0].id

            # Test 2: Get messages (should be < 200ms)
            start = time.time()
            messages = await service.get_messages(conv_id, limit=50)
            elapsed = time.time() - start
            print(f"Get messages: {elapsed*1000:.0f}ms (target: <200ms)")

            # Test 3: Add message (should be < 500ms)
            start = time.time()
            await service.add_message(conv_id, "user", "Performance test message")
            elapsed = time.time() - start
            print(f"Add message: {elapsed*1000:.0f}ms (target: <500ms)")

        break

asyncio.run(validate_performance())
EOF
```

---

## Rollback Procedures

### Emergency Rollback

If migration fails and system is unstable:

```bash
# 1. Enable maintenance mode
touch .maintenance_mode

# 2. Stop application servers
systemctl stop openclaw-backend

# 3. Restore database from backup
psql $DATABASE_URL -c "
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid();
"

dropdb openclaw_backend
createdb openclaw_backend
psql openclaw_backend < backup_YYYYMMDD_HHMMSS.sql

# 4. Rollback Alembic migrations
alembic downgrade -1  # Rollback one migration
# Or
alembic downgrade base  # Rollback all migrations

# 5. Verify rollback
psql $DATABASE_URL -c "\dt"

# 6. Restart with old code
git checkout previous_version
systemctl restart openclaw-backend

# 7. Remove maintenance mode
rm .maintenance_mode
```

### Partial Rollback (Keep New Schema, Revert Data)

If you need to keep the new schema but revert data changes:

```sql
-- Delete migrated conversations
DELETE FROM conversations WHERE id IN (
    SELECT id FROM conversations WHERE created_at > '2026-03-08 00:00:00'
);

-- Verify
SELECT COUNT(*) FROM conversations;
```

---

## Troubleshooting

### Issue: "relation already exists"

**Cause**: Tables were manually created before running migrations.

**Solution**:
```bash
# Mark migrations as completed
alembic stamp head

# Or drop tables and re-run
psql $DATABASE_URL -c "DROP TABLE IF EXISTS conversations, users CASCADE;"
alembic upgrade head
```

### Issue: Migration Hangs

**Cause**: Long-running queries blocking migration.

**Solution**:
```bash
# Check blocking queries
psql $DATABASE_URL -c "
SELECT pid, usename, query, state
FROM pg_stat_activity
WHERE state != 'idle';
"

# Kill blocking queries
psql $DATABASE_URL -c "SELECT pg_terminate_backend(PID);"

# Retry migration
alembic upgrade head
```

### Issue: "workspace does not have ZeroDB project"

**Cause**: ZeroDB provisioning step was skipped.

**Solution**: Re-run Step 5 from [Migration Steps](#step-5-provision-zerodb-projects)

---

## Post-Migration Tasks

### 1. Monitor Performance

```bash
# Watch database connection pool
watch -n 1 'psql $DATABASE_URL -c "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database();"'

# Monitor API response times
tail -f logs/openclaw_backend.log | grep "GET /conversations"
```

### 2. Update Documentation

```bash
# Update CLAUDE.md with new schema
# Update README.md with setup instructions
# Notify team of new conversation endpoints
```

### 3. Schedule Cleanup

```bash
# After 7 days, delete old backup files
find . -name "backup_*.sql" -mtime +7 -delete
```

---

## Additional Resources

- **Main Documentation**: [docs/CHAT_PERSISTENCE.md](CHAT_PERSISTENCE.md)
- **API Reference**: [docs/api/CONVERSATION_API.md](api/CONVERSATION_API.md)
- **Troubleshooting**: [docs/CHAT_PERSISTENCE_TROUBLESHOOTING.md](CHAT_PERSISTENCE_TROUBLESHOOTING.md)
- **Architecture Diagrams**: [docs/diagrams/chat-persistence-architecture.md](diagrams/chat-persistence-architecture.md)

---

**Document Version**: 1.0
**Last Updated**: 2026-03-08
