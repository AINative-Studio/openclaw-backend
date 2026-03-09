# Chat Persistence Setup Guide

## Prerequisites

Before setting up chat persistence, ensure you have:

- **PostgreSQL 14+** (Railway PostgreSQL recommended)
- **ZeroDB Account** with API key ([sign up at ainative.studio](https://ainative.studio))
- **Python 3.11+** installed
- **OpenClaw Backend** cloned and dependencies installed
- **OpenClaw Gateway** running (DBOS-based WebSocket server)

## Environment Variables

### Required Variables

Create or update `/Users/aideveloper/openclaw-backend/.env`:

```bash
# PostgreSQL Connection
DATABASE_URL=postgresql+asyncpg://postgres:password@yamabiko.proxy.rlwy.net:51955/railway

# ZeroDB Configuration
ZERODB_API_KEY=your_zerodb_api_key_here
ZERODB_API_URL=https://api.ainative.studio

# OpenClaw Gateway
OPENCLAW_GATEWAY_URL=ws://localhost:18789
OPENCLAW_GATEWAY_TOKEN=your_gateway_token

# Application Settings
ENVIRONMENT=development
SECRET_KEY=your_secret_key_for_jwt_signing
```

### Variable Descriptions

| Variable | Purpose | Example | Required |
|----------|---------|---------|----------|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg driver) | `postgresql+asyncpg://user:pass@host:port/db` | Yes |
| `ZERODB_API_KEY` | Authentication for ZeroDB API | `zdb_abc123...` | Yes |
| `ZERODB_API_URL` | ZeroDB API base URL | `https://api.ainative.studio` | Yes (default provided) |
| `OPENCLAW_GATEWAY_URL` | Gateway WebSocket URL | `ws://localhost:18789` | Yes |
| `OPENCLAW_GATEWAY_TOKEN` | Gateway authentication token | `openclaw-dev-token-12345` | Yes |
| `SECRET_KEY` | JWT signing key for lease tokens | Random 32+ character string | Yes |
| `ENVIRONMENT` | Runtime environment | `development`, `production`, `testing` | No (default: development) |

### Getting ZeroDB API Key

1. Visit [https://ainative.studio](https://ainative.studio)
2. Sign up for an account or log in
3. Navigate to **API Keys** in dashboard
4. Click **Create New API Key**
5. Copy the key (format: `zdb_...`)
6. Add to `.env` file

**Security Note:** Never commit `.env` files to version control. Add `.env` to `.gitignore`.

## Database Migration

### Step 1: Install Alembic

Alembic is included in project dependencies, but verify:

```bash
cd /Users/aideveloper/openclaw-backend
source venv/bin/activate  # or .venv/bin/activate
pip install alembic
```

### Step 2: Run Migrations

Apply all database migrations to create required tables:

```bash
# From project root
alembic upgrade head
```

**Expected Output:**
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade  -> a1b2c3d4e5f6, create workspaces table
INFO  [alembic.runtime.migration] Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a7, create users table
INFO  [alembic.runtime.migration] Running upgrade b2c3d4e5f6a7 -> d96afe8e6c07, add conversation model
```

### Step 3: Verify Migration

Check that tables were created:

```bash
# Connect to your PostgreSQL database
psql $DATABASE_URL

# List tables
\dt

# Expected tables:
# - workspaces
# - users
# - conversations
# - agent_swarm_instances (extended with workspace_id column)
# - alembic_version

# Exit psql
\q
```

### Step 4: Seed Default Data

Create default workspace and user for development:

```bash
# Create default workspace
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.models.workspace import Workspace
import os

async def seed_workspace():
    engine = create_async_engine(os.getenv('DATABASE_URL'))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        workspace = Workspace(
            name='Default Workspace',
            slug='default',
            description='Primary workspace for development'
        )
        session.add(workspace)
        await session.commit()
        print(f'Created workspace: {workspace.id}')

asyncio.run(seed_workspace())
"
```

```bash
# Create default user
python -c "
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from backend.models.user import User
from backend.models.workspace import Workspace
import os

async def seed_user():
    engine = create_async_engine(os.getenv('DATABASE_URL'))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get default workspace
        stmt = select(Workspace).where(Workspace.slug == 'default')
        result = await session.execute(stmt)
        workspace = result.scalar_one()

        user = User(
            email='dev@openclaw.local',
            workspace_id=workspace.id
        )
        session.add(user)
        await session.commit()
        print(f'Created user: {user.id} in workspace: {workspace.id}')

asyncio.run(seed_user())
"
```

**Alternative:** Create seed scripts in `/Users/aideveloper/openclaw-backend/scripts/`

## ZeroDB Project Provisioning

### Option 1: Auto-Provisioning (Recommended)

The system automatically provisions ZeroDB projects when creating agents. No manual setup required.

**How it works:**

1. When `AgentSwarmLifecycleService` creates an agent:
   ```python
   # Internally called during agent creation
   if not workspace.zerodb_project_id:
       project = await zerodb_client.create_project(
           name=workspace.name,
           description=f"ZeroDB project for workspace {workspace.name}"
       )
       workspace.zerodb_project_id = project["id"]
       await db.commit()
   ```

2. The workspace is automatically linked to the new ZeroDB project
3. All future messages use this project

**Verify auto-provisioning:**

```bash
# Check workspace has zerodb_project_id
psql $DATABASE_URL -c "SELECT id, name, zerodb_project_id FROM workspaces;"

# Expected output:
#                  id                  |        name        | zerodb_project_id
# -------------------------------------+--------------------+-------------------
#  123e4567-e89b-12d3-a456-426614174000 | Default Workspace  | proj_abc123xyz
```

### Option 2: Manual Provisioning

Manually provision ZeroDB projects for existing workspaces:

```python
# File: scripts/provision_zerodb_projects.py
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from backend.models.workspace import Workspace
from backend.integrations.zerodb_client import ZeroDBClient


async def provision_projects():
    """Provision ZeroDB projects for all workspaces missing them."""

    # Initialize database connection
    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Initialize ZeroDB client
    zerodb_api_key = os.getenv("ZERODB_API_KEY")
    if not zerodb_api_key:
        raise ValueError("ZERODB_API_KEY not set in environment")

    async with ZeroDBClient(api_key=zerodb_api_key) as zerodb:
        async with async_session() as session:
            # Find workspaces without ZeroDB projects
            stmt = select(Workspace).where(Workspace.zerodb_project_id.is_(None))
            result = await session.execute(stmt)
            workspaces = result.scalars().all()

            if not workspaces:
                print("All workspaces already have ZeroDB projects")
                return

            print(f"Found {len(workspaces)} workspaces needing ZeroDB projects")

            for workspace in workspaces:
                print(f"Creating project for workspace: {workspace.name}")

                # Create ZeroDB project
                project = await zerodb.create_project(
                    name=workspace.name,
                    description=f"ZeroDB project for workspace {workspace.name}"
                )

                # Link workspace to project
                workspace.zerodb_project_id = project["id"]
                print(f"  Created project: {project['id']}")

            # Commit all changes
            await session.commit()
            print(f"Successfully provisioned {len(workspaces)} projects")


if __name__ == "__main__":
    asyncio.run(provision_projects())
```

**Run the script:**

```bash
python scripts/provision_zerodb_projects.py
```

### Option 3: Interactive Provisioning

Create projects via Python REPL:

```python
import asyncio
import os
from backend.integrations.zerodb_client import ZeroDBClient

async def create_project_interactive():
    api_key = os.getenv("ZERODB_API_KEY")

    async with ZeroDBClient(api_key=api_key) as client:
        project = await client.create_project(
            name="My Workspace",
            description="Development workspace for testing"
        )
        print(f"Created project: {project['id']}")
        print(f"Project details: {project}")
        return project

# Run it
asyncio.run(create_project_interactive())
```

## Verification

### Step 1: Run Integration Tests

```bash
# Activate virtual environment
source venv/bin/activate

# Run conversation-specific tests
pytest tests/services/test_conversation_service.py -v

# Run API endpoint tests
pytest tests/api/v1/endpoints/test_conversations.py -v

# Run bridge persistence tests
pytest tests/agents/orchestration/test_production_openclaw_bridge_persistence.py -v
```

**Expected Output:**
```
tests/services/test_conversation_service.py::TestConversationService::test_create_conversation PASSED
tests/services/test_conversation_service.py::TestConversationService::test_add_message PASSED
tests/services/test_conversation_service.py::TestConversationService::test_get_messages PASSED
tests/services/test_conversation_service.py::TestConversationService::test_search_semantic PASSED
...

======================== 24 passed in 3.45s ========================
```

### Step 2: Verify Database Schema

```bash
# Check table structure
psql $DATABASE_URL -c "\d conversations"
```

**Expected Schema:**
```
                                   Table "public.conversations"
         Column          |           Type           | Collation | Nullable |      Default
-------------------------+--------------------------+-----------+----------+-------------------
 id                      | uuid                     |           | not null | uuid_generate_v4()
 workspace_id            | uuid                     |           | not null |
 agent_id                | uuid                     |           | not null |
 user_id                 | uuid                     |           |          |
 openclaw_session_key    | character varying(255)   |           |          |
 zerodb_table_name       | character varying(100)   |           |          | 'messages'
 zerodb_conversation_row_id | character varying(255) |           |          |
 started_at              | timestamp with time zone |           |          | now()
 last_message_at         | timestamp with time zone |           |          |
 message_count           | integer                  |           |          | 0
 status                  | conversation_status      |           |          | 'active'
Indexes:
    "conversations_pkey" PRIMARY KEY, btree (id)
    "conversations_openclaw_session_key_key" UNIQUE, btree (openclaw_session_key)
    "ix_conversations_agent_id" btree (agent_id)
    "ix_conversations_status" btree (status)
    "ix_conversations_user_id" btree (user_id)
    "ix_conversations_workspace_id" btree (workspace_id)
Foreign-key constraints:
    "conversations_agent_id_fkey" FOREIGN KEY (agent_id) REFERENCES agent_swarm_instances(id) ON DELETE CASCADE
    "conversations_user_id_fkey" FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE SET NULL
    "conversations_workspace_id_fkey" FOREIGN KEY (workspace_id) REFERENCES workspaces(id) ON DELETE CASCADE
```

### Step 3: Test ZeroDB Connection

```python
# File: scripts/test_zerodb_connection.py
import asyncio
import os
from backend.integrations.zerodb_client import ZeroDBClient, ZeroDBConnectionError, ZeroDBAPIError


async def test_connection():
    """Test ZeroDB API connection and basic operations."""

    api_key = os.getenv("ZERODB_API_KEY")
    if not api_key:
        print("ERROR: ZERODB_API_KEY not set")
        return False

    try:
        async with ZeroDBClient(api_key=api_key) as client:
            print("Testing ZeroDB connection...")

            # Test 1: Create project
            print("\n1. Creating test project...")
            project = await client.create_project(
                name=f"Test Project {asyncio.get_event_loop().time()}",
                description="Connection test project"
            )
            print(f"   ✓ Project created: {project['id']}")
            project_id = project["id"]

            # Test 2: Create table
            print("\n2. Creating test table...")
            table = await client.create_table(
                project_id=project_id,
                table_name="test_messages"
            )
            print(f"   ✓ Table created: {table['table_name']}")

            # Test 3: Insert row
            print("\n3. Inserting test row...")
            row = await client.create_table_row(
                project_id=project_id,
                table_name="test_messages",
                row_data={
                    "content": "Test message",
                    "role": "system",
                    "timestamp": "2026-03-02T00:00:00Z"
                }
            )
            print(f"   ✓ Row created: {row['id']}")

            # Test 4: Query table
            print("\n4. Querying table...")
            rows = await client.query_table(
                project_id=project_id,
                table_name="test_messages",
                limit=10,
                skip=0
            )
            print(f"   ✓ Retrieved {len(rows)} rows")

            # Test 5: Create memory
            print("\n5. Testing Memory API...")
            memory = await client.create_memory(
                title="Test Memory",
                content="This is a test memory for semantic search",
                type="test",
                tags=["test", "verification"],
                metadata={"source": "setup_verification"}
            )
            print(f"   ✓ Memory created: {memory['id']}")

            # Test 6: Search memories
            print("\n6. Testing semantic search...")
            search_results = await client.search_memories(
                query="test memory",
                limit=5,
                type="test"
            )
            print(f"   ✓ Found {len(search_results.get('results', []))} results")

            print("\n" + "="*60)
            print("✓ All tests passed - ZeroDB connection working correctly")
            print("="*60)
            return True

    except ZeroDBConnectionError as e:
        print(f"\n✗ Connection Error: {e}")
        print("  Check ZERODB_API_URL and network connectivity")
        return False
    except ZeroDBAPIError as e:
        print(f"\n✗ API Error: {e}")
        print("  Check ZERODB_API_KEY is valid")
        return False
    except Exception as e:
        print(f"\n✗ Unexpected Error: {e}")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_connection())
    exit(0 if success else 1)
```

**Run the test:**

```bash
python scripts/test_zerodb_connection.py
```

### Step 4: End-to-End Test

Test the complete flow from agent creation to message persistence:

```python
# File: scripts/test_chat_persistence_e2e.py
import asyncio
import os
from uuid import uuid4
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select

from backend.models.workspace import Workspace
from backend.models.user import User
from backend.models.agent_swarm_instance import AgentSwarmInstance
from backend.integrations.zerodb_client import ZeroDBClient
from backend.services.conversation_service import ConversationService


async def test_e2e():
    """End-to-end test of chat persistence system."""

    print("Starting end-to-end chat persistence test...\n")

    # Setup
    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Get default workspace
        stmt = select(Workspace).where(Workspace.slug == "default")
        result = await db.execute(stmt)
        workspace = result.scalar_one_or_none()

        if not workspace:
            print("ERROR: Default workspace not found. Run seed scripts first.")
            return False

        print(f"✓ Found workspace: {workspace.name}")

        # Get or create ZeroDB project for workspace
        if not workspace.zerodb_project_id:
            print("  Provisioning ZeroDB project...")
            async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
                project = await zerodb.create_project(
                    name=workspace.name,
                    description=f"Project for {workspace.name}"
                )
                workspace.zerodb_project_id = project["id"]
                await db.commit()
                print(f"  ✓ Created project: {project['id']}")

        # Get default user
        stmt = select(User).where(User.workspace_id == workspace.id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

        if not user:
            print("ERROR: No user found in workspace. Run seed scripts first.")
            return False

        print(f"✓ Found user: {user.email}")

        # Create test agent
        agent = AgentSwarmInstance(
            name="Test Agent",
            persona="helpful assistant",
            model="claude-3-5-sonnet-20241022",
            status="running",
            workspace_id=workspace.id,
            user_id=user.id,
            openclaw_session_key=f"session_{uuid4()}"
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        print(f"✓ Created agent: {agent.name}")

        # Initialize ConversationService
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            # Create conversation
            conversation = await service.create_conversation(
                workspace_id=workspace.id,
                agent_id=agent.id,
                user_id=user.id,
                openclaw_session_key=agent.openclaw_session_key
            )
            print(f"✓ Created conversation: {conversation.id}")

            # Add messages
            msg1 = await service.add_message(
                conversation_id=conversation.id,
                role="user",
                content="Hello, how are you?"
            )
            print(f"✓ Added message 1: {msg1['id']}")

            msg2 = await service.add_message(
                conversation_id=conversation.id,
                role="assistant",
                content="I'm doing well, thank you for asking! How can I help you today?"
            )
            print(f"✓ Added message 2: {msg2['id']}")

            msg3 = await service.add_message(
                conversation_id=conversation.id,
                role="user",
                content="Can you explain Python async/await?"
            )
            print(f"✓ Added message 3: {msg3['id']}")

            # Retrieve messages
            messages = await service.get_messages(
                conversation_id=conversation.id,
                limit=10,
                offset=0
            )
            print(f"✓ Retrieved {len(messages)} messages")

            # Semantic search
            search_results = await service.search_conversation_semantic(
                conversation_id=conversation.id,
                query="Python programming",
                limit=5
            )
            print(f"✓ Semantic search found {search_results['total']} results")

            # Verify conversation metadata
            await db.refresh(conversation)
            assert conversation.message_count == 3, f"Expected 3 messages, got {conversation.message_count}"
            print(f"✓ Conversation metadata correct: {conversation.message_count} messages")

    print("\n" + "="*60)
    print("✓ End-to-end test passed successfully!")
    print("="*60)
    return True


if __name__ == "__main__":
    success = asyncio.run(test_e2e())
    exit(0 if success else 1)
```

**Run the test:**

```bash
python scripts/test_chat_persistence_e2e.py
```

## Common Setup Issues

### Issue 1: "ZERODB_API_KEY not configured"

**Symptoms:**
```
HTTPException: 503 Service Unavailable
Detail: "ZeroDB API key not configured"
```

**Solution:**
1. Verify `.env` file exists in project root
2. Check `ZERODB_API_KEY` is set correctly (no quotes, no spaces)
3. Restart FastAPI server to reload environment
4. Verify with: `echo $ZERODB_API_KEY` (should print key)

### Issue 2: Database connection failed

**Symptoms:**
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Solution:**
1. Verify PostgreSQL is running: `pg_isready -h <host> -p <port>`
2. Check `DATABASE_URL` format: `postgresql+asyncpg://user:pass@host:port/db`
3. Ensure firewall allows connection on PostgreSQL port
4. For Railway: Check project is not sleeping (free tier limitation)

### Issue 3: Alembic migration fails

**Symptoms:**
```
ERROR [alembic.util.messaging] Can't locate revision identified by 'abc123'
```

**Solution:**
1. Check `alembic_version` table exists: `psql $DATABASE_URL -c "SELECT * FROM alembic_version;"`
2. If missing, initialize: `alembic stamp head`
3. If conflicting, reset: `psql $DATABASE_URL -c "DELETE FROM alembic_version;"`
4. Re-run: `alembic upgrade head`

### Issue 4: ZeroDB project creation fails

**Symptoms:**
```
ZeroDBAPIError: API error: 401 - Unauthorized
```

**Solution:**
1. Verify API key is valid: Log into [ainative.studio](https://ainative.studio) and regenerate
2. Check API key format (should start with `zdb_`)
3. Ensure no leading/trailing whitespace in `.env`
4. Test connection: `python scripts/test_zerodb_connection.py`

### Issue 5: Workspace missing zerodb_project_id

**Symptoms:**
```
ValueError: Workspace 123e4567-e89b-12d3-a456-426614174000 does not have a ZeroDB project configured
```

**Solution:**
1. Run manual provisioning: `python scripts/provision_zerodb_projects.py`
2. Or trigger auto-provisioning by creating an agent (will provision automatically)
3. Verify: `psql $DATABASE_URL -c "SELECT id, name, zerodb_project_id FROM workspaces;"`

### Issue 6: Import errors for ConversationService

**Symptoms:**
```
ImportError: cannot import name 'ConversationService'
```

**Solution:**
1. Ensure all dependencies installed: `pip install -r requirements.txt`
2. Check Python path includes project root
3. Verify file exists: `ls backend/services/conversation_service.py`
4. Restart Python interpreter/FastAPI server

## Production Deployment Checklist

Before deploying to production:

- [ ] `DATABASE_URL` points to production PostgreSQL instance
- [ ] `ZERODB_API_KEY` is production key (not development)
- [ ] All environment variables set in production environment (Railway/Heroku/etc.)
- [ ] Database migrations applied: `alembic upgrade head`
- [ ] Default workspace and user created
- [ ] ZeroDB projects provisioned for all workspaces
- [ ] Connection tests passed: `python scripts/test_zerodb_connection.py`
- [ ] Integration tests passed: `pytest tests/ -v`
- [ ] Monitoring configured (logs, metrics, alerts)
- [ ] Backup strategy implemented for PostgreSQL
- [ ] ZeroDB project limits reviewed (message count, search queries)

## Next Steps

1. **Read API Reference:** See [chat-persistence-api.md](chat-persistence-api.md) for endpoint documentation
2. **Enable Semantic Search:** See [chat-persistence-semantic-search.md](chat-persistence-semantic-search.md) for usage guide
3. **Troubleshooting:** See [chat-persistence-troubleshooting.md](chat-persistence-troubleshooting.md) for common issues
4. **Migration:** See [chat-persistence-migration.md](chat-persistence-migration.md) if upgrading existing deployment
