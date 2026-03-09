# PostgreSQL Migration - March 2026

## Summary

**Migration Date:** March 4, 2026
**Status:** COMPLETED ✓
**Database:** SQLite → PostgreSQL 14+ (Railway)

OpenClaw Backend has **permanently migrated** from SQLite to PostgreSQL for production-grade reliability and chat persistence features.

## Why We Migrated

### SQLite Limitations
- ❌ Not suitable for production multi-user applications
- ❌ Limited concurrent write operations
- ❌ No native UUID type support
- ❌ Poor performance with large datasets
- ❌ No async driver support for FastAPI
- ❌ Cannot handle multiple backend instances

### PostgreSQL Benefits
- ✅ Production-grade ACID compliance
- ✅ Excellent concurrency and connection pooling
- ✅ Native UUID type support
- ✅ Async driver (asyncpg) for FastAPI
- ✅ Scalable to millions of records
- ✅ Support for multiple backend instances
- ✅ Railway managed hosting with automatic backups

## What Changed

### Database Configuration

**Before (SQLite):**
```python
# backend/db/base.py
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./openclaw.db")
```

**After (PostgreSQL):**
```python
# backend/db/base.py
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError(
        "DATABASE_URL environment variable is required. "
        "OpenClaw Backend requires PostgreSQL 14+ with asyncpg driver."
    )
```

### Environment Variable

**Before:**
```bash
# .env (optional, defaulted to SQLite)
DATABASE_URL=sqlite:///./openclaw.db
```

**After:**
```bash
# .env (REQUIRED, must be PostgreSQL)
DATABASE_URL=postgresql+asyncpg://postgres:password@yamabiko.proxy.rlwy.net:51955/railway
```

### Database Tables Created

The migration includes creation of these core tables:

1. **conversations** - Conversation metadata
   - UUID primary key
   - Foreign keys to workspaces, agents, users
   - Message count and timestamp tracking
   - Status enum (ACTIVE, ARCHIVED, DELETED)

2. **messages** - Chat message storage
   - UUID primary key
   - Foreign key to conversations (CASCADE delete)
   - Role (user, assistant, system)
   - Content (TEXT)
   - Metadata (JSONB)
   - Created timestamp

3. **workspaces** - Multi-tenant organization
4. **users** - User accounts
5. **agent_swarm_instances** - Agent configuration

### Driver Architecture

PostgreSQL requires two different drivers for sync vs async operations:

```python
# Sync operations (migrations, seed scripts) - psycopg2
SYNC_DATABASE_URL = "postgresql://postgres:password@host:port/db"

# Async operations (FastAPI endpoints) - asyncpg
ASYNC_DATABASE_URL = "postgresql+asyncpg://postgres:password@host:port/db"
```

The system automatically handles this conversion based on the DATABASE_URL format.

## Migration Steps Completed

### 1. Database Provisioning ✓
- Provisioned PostgreSQL 14 on Railway
- Database: `railway`
- Host: `yamabiko.proxy.rlwy.net:51955`
- Connection pooling via PgBouncer (port 6432 also available)

### 2. Environment Configuration ✓
```bash
# Updated .env
DATABASE_URL=postgresql+asyncpg://postgres:xDelQrUbmzAnRtgNqtNaNbaoAfKBftHM@yamabiko.proxy.rlwy.net:51955/railway
```

### 3. Code Updates ✓
- Updated `backend/db/base.py` to require PostgreSQL
- Added validation for DATABASE_URL format
- Removed SQLite-specific code paths
- Added `pool_pre_ping=True` for connection health checks

### 4. Schema Creation ✓
```sql
-- Created conversations table
CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agent_swarm_instances(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    openclaw_session_key VARCHAR(255),
    zerodb_table_name VARCHAR(100),
    zerodb_conversation_row_id VARCHAR(255),
    started_at TIMESTAMPTZ DEFAULT NOW(),
    last_message_at TIMESTAMPTZ,
    message_count INTEGER DEFAULT 0,
    status conversation_status DEFAULT 'ACTIVE'
);

-- Created messages table
CREATE TABLE messages (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Added indexes
CREATE INDEX ix_messages_conversation_created ON messages (conversation_id, created_at);
```

### 5. Data Seeding ✓
```sql
-- Verified default workspace exists
SELECT id, name FROM workspaces;
-- dc17346c-f46c-4cd4-9277-a2efcaadfbb2 | default

-- Verified agent exists
SELECT id, name, workspace_id FROM agent_swarm_instances;
-- 3f632883-94eb-4269-9b57-fd56a3a88361 | Main Agent | dc17346c...
```

### 6. Testing ✓
Successfully tested end-to-end message persistence:

```bash
# Test message 1: "What is 5 plus 3?" → Response: "8"
# Test message 2: "What is 10 times 2?" → Response: "20"

# Verified in database:
# - Conversation created with message_count = 4
# - All user and assistant messages persisted
# - Timestamps correctly recorded
```

## Breaking Changes

### ❌ SQLite No Longer Supported

SQLite is **not supported** as of March 2026. The backend will **refuse to start** without a valid PostgreSQL DATABASE_URL.

**Error message if SQLite is attempted:**
```python
ValueError: Invalid DATABASE_URL format: sqlite:///./opencla...
Must start with 'postgresql://' or 'postgresql+asyncpg://'
```

### Required Environment Variable

`DATABASE_URL` is now **mandatory**. The backend will not start without it.

**Error message if missing:**
```python
ValueError: DATABASE_URL environment variable is required.
OpenClaw Backend requires PostgreSQL 14+ with asyncpg driver.
Example: postgresql+asyncpg://postgres:password@localhost:5432/openclaw
```

## Development Setup

### Local PostgreSQL

For local development, install PostgreSQL:

```bash
# macOS
brew install postgresql@14
brew services start postgresql@14

# Ubuntu/Debian
sudo apt install postgresql-14
sudo systemctl start postgresql

# Create database
createdb openclaw

# Set environment
export DATABASE_URL=postgresql+asyncpg://postgres@localhost:5432/openclaw
```

### Railway PostgreSQL (Recommended)

Railway provides managed PostgreSQL with:
- Automatic backups
- Connection pooling (PgBouncer)
- SSL support
- Monitoring and metrics
- Easy environment variable injection

```bash
# Railway automatically sets DATABASE_URL
# Format: postgresql://postgres:password@host:port/railway
```

## Rollback Not Supported

**This migration is one-way.** There is no rollback to SQLite. All future development and deployments must use PostgreSQL.

If you need to start fresh:
1. Drop all tables: `psql $DATABASE_URL -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"`
2. Run migrations: `alembic upgrade head`
3. Seed data: `python scripts/seed_default_workspace.py`

## Migration Verification

### Check Current Database Type

```bash
# View current DATABASE_URL
echo $DATABASE_URL

# Should output:
# postgresql+asyncpg://...
```

### Verify Tables Exist

```bash
# List all tables
PGPASSWORD=xDelQrUbmzAnRtgNqtNaNbaoAfKBftHM psql -h yamabiko.proxy.rlwy.net -p 51955 -U postgres -d railway -c "\dt"

# Expected output includes:
# - conversations
# - messages
# - workspaces
# - users
# - agent_swarm_instances
```

### Verify Chat Persistence

```bash
# Send test message
curl -X POST http://localhost:8000/api/v1/agents/{agent-id}/message \
  -H "Content-Type: application/json" \
  -d '{"message":"Test message"}'

# Check database
PGPASSWORD=... psql ... -c "SELECT COUNT(*) FROM messages;"
# Should return count > 0
```

## Documentation Updates

All documentation has been updated to reflect PostgreSQL requirement:

- ✓ `CLAUDE.md` - Updated database section
- ✓ `docs/chat-persistence-README.md` - Removed SQLite references
- ✓ `docs/chat-persistence-setup.md` - PostgreSQL-only instructions
- ✓ `backend/db/base.py` - Code enforces PostgreSQL
- ✓ `.env` - Updated with PostgreSQL connection string

## Support

### Common Issues

**Issue:** Backend fails to start with DATABASE_URL error
**Solution:** Ensure `DATABASE_URL` is set in `.env` with PostgreSQL connection string

**Issue:** MissingGreenlet error
**Solution:** This was fixed during migration. Sync operations use psycopg2, async use asyncpg

**Issue:** Table not found errors
**Solution:** Run migrations: `alembic upgrade head`

**Issue:** Foreign key constraint violations
**Solution:** Ensure workspace, user, and agent exist before creating conversations

### Getting Help

1. Check this migration document
2. Review `docs/chat-persistence-troubleshooting.md`
3. Verify DATABASE_URL format and connectivity
4. Check Railway dashboard for PostgreSQL status

## Future Considerations

### Scaling PostgreSQL

As usage grows, consider:
- Connection pooling tuning (PgBouncer configuration)
- Read replicas for high-traffic deployments
- Partitioning for large message tables
- Index optimization for frequent queries

### Monitoring

Track these PostgreSQL metrics:
- Connection pool usage
- Query performance (slow query log)
- Table sizes and growth rate
- Backup success/failure
- Replication lag (if using replicas)

---

**Migration Completed:** March 4, 2026
**Migration Team:** AI Developer + Claude
**Database:** PostgreSQL 14 on Railway
**Status:** Production Ready ✓
