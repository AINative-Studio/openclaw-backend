# Chat Persistence Migration Guide

## Overview

This guide helps you migrate an existing OpenClaw Backend deployment to enable chat persistence. It covers upgrading from non-persistent to persistent chat storage with minimal downtime.

**Migration Scope:**
- Add PostgreSQL tables (workspaces, users, conversations)
- Extend agent_swarm_instances table with workspace relationship
- Provision ZeroDB projects for workspaces
- Enable ProductionOpenClawBridge persistence
- Backfill existing agent data

**Estimated Time:** 30-60 minutes (depending on data volume)

**Downtime Required:** 5-10 minutes (for database migration only)

## Pre-Migration Checklist

Before starting migration:

- [ ] **Backup existing database** (critical - test restore procedure)
- [ ] **Provision ZeroDB account** and obtain API key
- [ ] **Test ZeroDB connection** from backend server
- [ ] **Review architecture** ([chat-persistence-architecture.md](chat-persistence-architecture.md))
- [ ] **Notify users** of planned maintenance window (if applicable)
- [ ] **Prepare rollback plan** (see Rollback section)
- [ ] **Verify Python version** (3.11+ required)
- [ ] **Check disk space** (database will grow ~5-10% from new tables)

## Step 1: Backup Existing Data

### PostgreSQL Backup

```bash
# Full database backup
pg_dump -U postgres -d openclaw_db > backup_$(date +%Y%m%d_%H%M%S).sql

# Or using DATABASE_URL
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d_%H%M%S).sql

# Verify backup is valid
file backup_*.sql
# Should show: "ASCII text"

# Test restore on separate database (recommended)
createdb openclaw_test
psql openclaw_test < backup_*.sql
dropdb openclaw_test
```

### Backup Existing Agent Data

```bash
# Export existing agents to JSON (for verification later)
psql $DATABASE_URL -c "
    COPY (
        SELECT id, name, persona, model, status, created_at
        FROM agent_swarm_instances
    ) TO STDOUT WITH CSV HEADER;
" > agents_backup_$(date +%Y%m%d).csv

# Verify export
wc -l agents_backup_*.csv
# Should show count of agents + 1 (header row)
```

## Step 2: Update Environment Variables

### Add New Variables

Update `/Users/aideveloper/openclaw-backend/.env`:

```bash
# Add ZeroDB configuration
ZERODB_API_KEY=zdb_your_api_key_here
ZERODB_API_URL=https://api.ainative.studio

# Existing variables (verify they're set)
DATABASE_URL=postgresql+asyncpg://user:password@host:port/database
OPENCLAW_GATEWAY_URL=ws://localhost:18789
OPENCLAW_GATEWAY_TOKEN=your_token
SECRET_KEY=your_secret_key
ENVIRONMENT=production
```

### Verify Environment Loads

```bash
# Test that backend can read new variables
python -c "
import os
from dotenv import load_dotenv
load_dotenv()

assert os.getenv('ZERODB_API_KEY'), 'ZERODB_API_KEY not set'
assert os.getenv('DATABASE_URL'), 'DATABASE_URL not set'
print('✓ All environment variables set')
"
```

## Step 3: Run Database Migrations

### Update Dependencies

```bash
cd /Users/aideveloper/openclaw-backend
source venv/bin/activate  # Or .venv/bin/activate

# Install any new dependencies
pip install --upgrade -r requirements.txt

# Verify Alembic is installed
alembic --version
```

### Run Migrations

```bash
# Check current database version
alembic current

# Preview migrations
alembic history

# Run migrations (THIS MODIFIES DATABASE)
# Downtime starts here
alembic upgrade head

# Verify migrations succeeded
alembic current
# Should show latest revision (e.g., "d96afe8e6c07")
```

**Expected Output:**

```
INFO  [alembic.runtime.migration] Running upgrade  -> a1b2c3d4e5f6, create workspaces table
INFO  [alembic.runtime.migration] Running upgrade a1b2c3d4e5f6 -> b2c3d4e5f6a7, create users table
INFO  [alembic.runtime.migration] Running upgrade b2c3d4e5f6a7 -> c3d4e5f6a7b8, add workspace_id to agent_swarm_instances
INFO  [alembic.runtime.migration] Running upgrade c3d4e5f6a7b8 -> d96afe8e6c07, add conversation model
```

### Verify New Tables Created

```bash
psql $DATABASE_URL -c "\dt"

# Should show:
# - agent_swarm_instances (existing, now with workspace_id column)
# - workspaces (new)
# - users (new)
# - conversations (new)
# - alembic_version (existing)
```

## Step 4: Seed Initial Data

### Create Default Workspace

```bash
# File: scripts/migration_seed_workspace.py
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from backend.models.workspace import Workspace


async def seed_default_workspace():
    """Create default workspace for migration."""

    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        workspace = Workspace(
            name="Default Workspace",
            slug="default",
            description="Primary workspace (created during migration)"
        )
        session.add(workspace)
        await session.commit()
        await session.refresh(workspace)

        print(f"✓ Created workspace: {workspace.id}")
        print(f"  Name: {workspace.name}")
        print(f"  Slug: {workspace.slug}")

        return workspace.id


if __name__ == "__main__":
    workspace_id = asyncio.run(seed_default_workspace())
    print(f"\nWorkspace ID: {workspace_id}")
    print("Save this ID for next step!")
```

**Run it:**

```bash
python scripts/migration_seed_workspace.py

# Output:
# ✓ Created workspace: 123e4567-e89b-12d3-a456-426614174000
#   Name: Default Workspace
#   Slug: default
#
# Workspace ID: 123e4567-e89b-12d3-a456-426614174000
# Save this ID for next step!

# Copy the workspace ID (you'll need it)
```

### Create Default User

```bash
# File: scripts/migration_seed_user.py
import asyncio
import os
from uuid import UUID
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from backend.models.user import User
from backend.models.workspace import Workspace


async def seed_default_user():
    """Create default user for migration."""

    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get default workspace
        stmt = select(Workspace).where(Workspace.slug == "default")
        result = await session.execute(stmt)
        workspace = result.scalar_one()

        # Create default user
        user = User(
            email="admin@openclaw.local",
            workspace_id=workspace.id
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)

        print(f"✓ Created user: {user.id}")
        print(f"  Email: {user.email}")
        print(f"  Workspace: {workspace.name}")

        return user.id


if __name__ == "__main__":
    user_id = asyncio.run(seed_default_user())
    print(f"\nUser ID: {user_id}")
```

**Run it:**

```bash
python scripts/migration_seed_user.py

# Output:
# ✓ Created user: 223e4567-e89b-12d3-a456-426614174000
#   Email: admin@openclaw.local
#   Workspace: Default Workspace
#
# User ID: 223e4567-e89b-12d3-a456-426614174000
```

## Step 5: Migrate Existing Agents

### Link Agents to Default Workspace

```bash
# File: scripts/migration_link_agents_to_workspace.py
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, update
from backend.models.agent_swarm_instance import AgentSwarmInstance
from backend.models.workspace import Workspace
from backend.models.user import User


async def link_agents_to_workspace():
    """Link existing agents to default workspace."""

    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get default workspace and user
        stmt = select(Workspace).where(Workspace.slug == "default")
        result = await session.execute(stmt)
        workspace = result.scalar_one()

        stmt = select(User).where(User.workspace_id == workspace.id)
        result = await session.execute(stmt)
        user = result.scalar_one()

        # Update all agents without workspace_id
        stmt = (
            update(AgentSwarmInstance)
            .where(AgentSwarmInstance.workspace_id.is_(None))
            .values(workspace_id=workspace.id, user_id=user.id)
        )
        result = await session.execute(stmt)
        await session.commit()

        count = result.rowcount
        print(f"✓ Linked {count} agents to workspace: {workspace.name}")

        # Verify all agents now have workspace
        stmt = select(AgentSwarmInstance).where(AgentSwarmInstance.workspace_id.is_(None))
        result = await session.execute(stmt)
        orphaned = result.scalars().all()

        if orphaned:
            print(f"⚠ Warning: {len(orphaned)} agents still without workspace")
        else:
            print("✓ All agents linked to workspaces")


if __name__ == "__main__":
    asyncio.run(link_agents_to_workspace())
```

**Run it:**

```bash
python scripts/migration_link_agents_to_workspace.py

# Output:
# ✓ Linked 15 agents to workspace: Default Workspace
# ✓ All agents linked to workspaces
```

### Verify Agent Migration

```bash
# Check all agents have workspace_id
psql $DATABASE_URL -c "
    SELECT
        COUNT(*) as total_agents,
        COUNT(workspace_id) as agents_with_workspace,
        COUNT(*) - COUNT(workspace_id) as agents_without_workspace
    FROM agent_swarm_instances;
"

# Expected output:
#  total_agents | agents_with_workspace | agents_without_workspace
# --------------+-----------------------+--------------------------
#            15 |                    15 |                        0
```

## Step 6: Provision ZeroDB Projects

### Auto-Provision for Default Workspace

```bash
# File: scripts/migration_provision_zerodb.py
import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select
from backend.models.workspace import Workspace
from backend.integrations.zerodb_client import ZeroDBClient


async def provision_zerodb_projects():
    """Provision ZeroDB projects for all workspaces."""

    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            # Get workspaces without ZeroDB projects
            stmt = select(Workspace).where(Workspace.zerodb_project_id.is_(None))
            result = await session.execute(stmt)
            workspaces = result.scalars().all()

            if not workspaces:
                print("✓ All workspaces already have ZeroDB projects")
                return

            print(f"Provisioning {len(workspaces)} ZeroDB projects...")

            for workspace in workspaces:
                print(f"\n  Workspace: {workspace.name}")

                # Create ZeroDB project
                project = await zerodb.create_project(
                    name=workspace.name,
                    description=f"ZeroDB project for {workspace.name} (created during migration)"
                )

                # Link workspace to project
                workspace.zerodb_project_id = project["id"]
                print(f"  ✓ Created project: {project['id']}")

            await session.commit()
            print(f"\n✓ Provisioned {len(workspaces)} ZeroDB projects")


if __name__ == "__main__":
    asyncio.run(provision_zerodb_projects())
```

**Run it:**

```bash
python scripts/migration_provision_zerodb.py

# Output:
# Provisioning 1 ZeroDB projects...
#
#   Workspace: Default Workspace
#   ✓ Created project: proj_abc123xyz
#
# ✓ Provisioned 1 ZeroDB projects
```

### Verify ZeroDB Provisioning

```bash
# Check all workspaces have projects
psql $DATABASE_URL -c "
    SELECT id, name, zerodb_project_id
    FROM workspaces;
"

# Expected:
#                  id                  |        name        | zerodb_project_id
# -------------------------------------+--------------------+-------------------
#  123e4567-e89b-12d3-a456-426614174000 | Default Workspace  | proj_abc123xyz
```

## Step 7: Update Backend Code

### Enable Persistence in Lifecycle Service

Update the file that creates `ProductionOpenClawBridge` (typically `backend/services/lifecycle_service.py` or similar):

```python
# Before (no persistence):
class AgentSwarmLifecycleService:
    def __init__(self):
        pass

    async def create_agent(self, ...):
        bridge = ProductionOpenClawBridge(
            url=os.getenv("OPENCLAW_GATEWAY_URL"),
            token=os.getenv("OPENCLAW_GATEWAY_TOKEN")
            # No db or zerodb_client - persistence disabled
        )
```

```python
# After (with persistence):
from backend.integrations.zerodb_client import ZeroDBClient

class AgentSwarmLifecycleService:
    def __init__(self, db: AsyncSession):
        self.db = db
        # Initialize ZeroDB client
        self.zerodb_client = ZeroDBClient(
            api_key=os.getenv("ZERODB_API_KEY")
        )

    async def create_agent(self, ...):
        bridge = ProductionOpenClawBridge(
            url=os.getenv("OPENCLAW_GATEWAY_URL"),
            token=os.getenv("OPENCLAW_GATEWAY_TOKEN"),
            db=self.db,                      # ← Add database session
            zerodb_client=self.zerodb_client # ← Add ZeroDB client
        )
```

### Restart Backend Service

```bash
# If using systemd
sudo systemctl restart openclaw-backend

# If using pm2
pm2 restart openclaw-backend

# If running manually
pkill -f "uvicorn backend.main:app"
uvicorn backend.main:app --host 0.0.0.0 --port 8000

# Verify service is running
curl http://localhost:8000/health
# Should return 200 OK
```

**Downtime ends here** (service is back online)

## Step 8: Verification

### Test Conversation Creation

```bash
# File: scripts/migration_test_persistence.py
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


async def test_persistence():
    """Test that chat persistence works."""

    print("Testing chat persistence...\n")

    engine = create_async_engine(os.getenv("DATABASE_URL"))
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        # Get default workspace and user
        stmt = select(Workspace).where(Workspace.slug == "default")
        result = await db.execute(stmt)
        workspace = result.scalar_one()

        stmt = select(User).where(User.workspace_id == workspace.id)
        result = await db.execute(stmt)
        user = result.scalar_one()

        # Create test agent
        agent = AgentSwarmInstance(
            name="Migration Test Agent",
            persona="test assistant",
            model="claude-3-5-sonnet-20241022",
            status="running",
            workspace_id=workspace.id,
            user_id=user.id,
            openclaw_session_key=f"session_{uuid4()}"
        )
        db.add(agent)
        await db.commit()
        await db.refresh(agent)
        print(f"1. ✓ Created test agent: {agent.id}")

        # Create conversation
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            service = ConversationService(db=db, zerodb_client=zerodb)

            conversation = await service.create_conversation(
                workspace_id=workspace.id,
                agent_id=agent.id,
                user_id=user.id,
                openclaw_session_key=agent.openclaw_session_key
            )
            print(f"2. ✓ Created conversation: {conversation.id}")

            # Add test message
            message = await service.add_message(
                conversation_id=conversation.id,
                role="user",
                content="Hello, this is a test message after migration!"
            )
            print(f"3. ✓ Added message: {message['id']}")

            # Retrieve messages
            messages = await service.get_messages(
                conversation_id=conversation.id,
                limit=10
            )
            print(f"4. ✓ Retrieved {len(messages)} messages")

            # Test semantic search
            try:
                search_results = await service.search_conversation_semantic(
                    conversation_id=conversation.id,
                    query="test message",
                    limit=5
                )
                print(f"5. ✓ Semantic search found {search_results['total']} results")
            except Exception as e:
                print(f"5. ⚠ Semantic search failed (may need time to index): {e}")

            # Verify via API
            print("\n6. Testing API endpoints...")
            import httpx

            async with httpx.AsyncClient() as client:
                # List conversations
                response = await client.get(
                    "http://localhost:8000/api/v1/conversations",
                    params={"agent_id": str(agent.id)}
                )
                assert response.status_code == 200
                data = response.json()
                print(f"   ✓ API returned {data['total']} conversations")

                # Get messages
                response = await client.get(
                    f"http://localhost:8000/api/v1/conversations/{conversation.id}/messages"
                )
                assert response.status_code == 200
                data = response.json()
                print(f"   ✓ API returned {len(data['messages'])} messages")

        print("\n" + "="*60)
        print("✓ Migration verification complete!")
        print("  Chat persistence is working correctly.")
        print("="*60)


if __name__ == "__main__":
    asyncio.run(test_persistence())
```

**Run verification:**

```bash
python scripts/migration_test_persistence.py

# Expected output:
# Testing chat persistence...
#
# 1. ✓ Created test agent: ...
# 2. ✓ Created conversation: ...
# 3. ✓ Added message: ...
# 4. ✓ Retrieved 1 messages
# 5. ✓ Semantic search found 1 results
#
# 6. Testing API endpoints...
#    ✓ API returned 1 conversations
#    ✓ API returned 1 messages
#
# ============================================================
# ✓ Migration verification complete!
#   Chat persistence is working correctly.
# ============================================================
```

### Check Database State

```bash
# Final verification queries
psql $DATABASE_URL -c "
    SELECT
        (SELECT COUNT(*) FROM workspaces) as workspaces,
        (SELECT COUNT(*) FROM users) as users,
        (SELECT COUNT(*) FROM agent_swarm_instances) as agents,
        (SELECT COUNT(*) FROM conversations) as conversations;
"

# Expected (numbers will vary):
#  workspaces | users | agents | conversations
# ------------+-------+--------+---------------
#           1 |     1 |     16 |             1
```

## Post-Migration Tasks

### 1. Monitor Logs

```bash
# Watch for errors in first hour after migration
tail -f logs/backend.log | grep -i error

# Check for persistence-related messages
grep "conversation persistence" logs/backend.log
# Should show: "ProductionOpenClawBridge initialized with conversation persistence enabled"
```

### 2. Update Documentation

Update internal documentation to reflect:
- New conversation API endpoints
- Workspace and user management
- Semantic search capabilities

### 3. Notify Users

If applicable, notify users that:
- Chat history is now persisted
- They can search past conversations
- Workspace organization is available

### 4. Clean Up Migration Scripts

```bash
# Move migration scripts to archive
mkdir -p scripts/migration_archive
mv scripts/migration_*.py scripts/migration_archive/

# Keep them for reference but out of main scripts directory
```

## Rollback Plan

If migration fails or issues are discovered:

### Option 1: Restore from Backup (Recommended)

```bash
# Stop backend service
sudo systemctl stop openclaw-backend

# Restore database from backup
psql $DATABASE_URL < backup_YYYYMMDD_HHMMSS.sql

# Verify restoration
psql $DATABASE_URL -c "SELECT COUNT(*) FROM agent_swarm_instances;"

# Downgrade Alembic (if migrations were applied)
alembic downgrade base

# Restart service
sudo systemctl start openclaw-backend
```

### Option 2: Manual Rollback (Partial)

```bash
# If only removing new tables (keeps existing agents intact)
psql $DATABASE_URL -c "
    DROP TABLE IF EXISTS conversations CASCADE;
    DROP TABLE IF EXISTS users CASCADE;
    DROP TABLE IF EXISTS workspaces CASCADE;
    DROP TYPE IF EXISTS conversation_status;
"

# Remove workspace_id column from agents (if safe)
psql $DATABASE_URL -c "
    ALTER TABLE agent_swarm_instances
    DROP COLUMN IF EXISTS workspace_id,
    DROP COLUMN IF EXISTS user_id;
"

# Downgrade Alembic version
alembic downgrade base
```

### Option 3: Keep New Tables, Disable Persistence

```bash
# Keep database changes but disable persistence in code
# Edit lifecycle service to NOT pass db and zerodb_client

# In backend/services/lifecycle_service.py:
bridge = ProductionOpenClawBridge(
    url=os.getenv("OPENCLAW_GATEWAY_URL"),
    token=os.getenv("OPENCLAW_GATEWAY_TOKEN")
    # No db or zerodb_client - disables persistence
)

# Restart service
sudo systemctl restart openclaw-backend

# Chat persistence disabled, but tables remain for future use
```

## Common Migration Issues

### Issue 1: Alembic Migration Fails

**Error:**
```
sqlalchemy.exc.ProgrammingError: relation "workspaces" already exists
```

**Solution:**
```bash
# Check if tables were partially created
psql $DATABASE_URL -c "\dt"

# If tables exist, stamp Alembic version without running migration
alembic stamp head

# Then verify current version
alembic current
```

### Issue 2: Agent Workspace Link Fails

**Error:**
```
IntegrityError: null value in column "workspace_id" violates not-null constraint
```

**Solution:**
```bash
# Ensure default workspace was created first
psql $DATABASE_URL -c "SELECT id FROM workspaces LIMIT 1;"

# If empty, create workspace manually (see Step 4)

# Then re-run agent linking script
python scripts/migration_link_agents_to_workspace.py
```

### Issue 3: ZeroDB Project Creation Fails

**Error:**
```
ZeroDBAPIError: API error: 401 - Unauthorized
```

**Solution:**
```bash
# Verify API key is valid
echo $ZERODB_API_KEY

# Test connection
python scripts/test_zerodb_connection.py

# If fails, regenerate key at ainative.studio
# Update .env file
# Re-run provisioning script
```

## Performance Considerations

After migration, monitor:

### Database Size

```bash
# Check database size
psql $DATABASE_URL -c "
    SELECT
        pg_size_pretty(pg_database_size(current_database())) as database_size;
"

# Check table sizes
psql $DATABASE_URL -c "
    SELECT
        tablename,
        pg_size_pretty(pg_total_relation_size(tablename::text)) as size
    FROM pg_tables
    WHERE schemaname = 'public'
    ORDER BY pg_total_relation_size(tablename::text) DESC;
"
```

### Query Performance

```bash
# Enable query timing in psql
psql $DATABASE_URL

# In psql:
\timing on

# Test query performance
SELECT * FROM conversations WHERE workspace_id = '...';
# Should complete in <100ms
```

### ZeroDB Usage

```bash
# Log into ainative.studio dashboard
# Check ZeroDB project usage:
# - Total messages stored
# - API request count
# - Storage quota used
```

## Next Steps

1. **Monitor for 24 hours:** Watch logs and metrics for errors
2. **Gather user feedback:** Ask users about chat persistence experience
3. **Optimize if needed:** Add indexes if queries slow
4. **Plan next features:**
   - Multi-workspace support
   - User authentication
   - Conversation export
   - Advanced search filters

## Related Documentation

- [Architecture](chat-persistence-architecture.md) - System design
- [Setup Guide](chat-persistence-setup.md) - Fresh installation
- [API Reference](chat-persistence-api.md) - Endpoint documentation
- [Troubleshooting](chat-persistence-troubleshooting.md) - Common issues
