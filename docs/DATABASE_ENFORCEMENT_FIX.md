# Database Connection Enforcement Fix

**Date:** 2026-03-06  
**Issue:** Pre-backend-start hook checked .env file but didn't test actual database connection  
**Solution:** Added connection test to `init_db()` that fails hard if Railway database unreachable

## The Problem

**User reported:** "the app loaded without the database from railway"

**Root cause analysis:**
1. Pre-backend-start hook (`.claude/hooks/pre-backend-start.sh`) checked `.env` file contains Railway URL ✅
2. But the hook ran in subshell - environment exports didn't persist to Python process
3. Python `init_db()` just called `Base.metadata.create_all()` - no connection test
4. App could start even if database was unreachable (lazy connection)
5. No startup logging showed database connection status

## The Solution

### Modified: `backend/db/base.py` - `init_db()` function

**Before:**
```python
def init_db() -> None:
    """
    Initialize database by creating all tables
    """
    Base.metadata.create_all(bind=engine)
```

**After:**
```python
def init_db() -> None:
    """
    Initialize database by creating all tables
    
    ENFORCES: Railway PostgreSQL connection MUST work or app fails to start
    """
    print("🔒 ENFORCING Railway PostgreSQL Connection...")
    
    # TEST DATABASE CONNECTION - fail hard if unreachable
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        print(f"✅ Connected to Railway PostgreSQL: {engine.url.host}:{engine.url.port}/{engine.url.database}")
    except Exception as e:
        print(f"❌ FATAL: Cannot connect to Railway PostgreSQL database")
        print(f"   Host: {engine.url.host}")
        print(f"   Port: {engine.url.port}")
        print(f"   Database: {engine.url.database}")
        print(f"   Error: {str(e)}")
        print("")
        print("🚫 OpenClaw Backend REQUIRES Railway PostgreSQL connection")
        print("   The application will NOT start without it")
        raise SystemExit(1)
    
    # Create tables if needed
    Base.metadata.create_all(bind=engine)
    print("✅ Database tables verified/created")
```

**Key changes:**
- Added `from sqlalchemy import text` import
- Added actual connection test: `engine.connect()` + `SELECT 1` query
- Added clear success message showing host/port/database
- Added comprehensive error message with troubleshooting info
- **Hard fail with `SystemExit(1)`** - app CANNOT start without database

## Testing

### Test 1: Broken Database (Should BLOCK)
```bash
# Break DATABASE_URL
sed -i '' 's/yamabiko.proxy.rlwy.net/fake-wrong-host.net/g' .env

# Try to start backend
python3 -c "from backend.db.base import init_db; init_db()"
```

**Result:**
```
🔒 ENFORCING Railway PostgreSQL Connection...
❌ FATAL: Cannot connect to Railway PostgreSQL database
   Host: fake-wrong-host.net
   Port: 51955
   Database: railway
   Error: (psycopg2.OperationalError) could not translate host name "fake-wrong-host.net" to address: nodename nor servname provided, or not known

🚫 OpenClaw Backend REQUIRES Railway PostgreSQL connection
   The application will NOT start without it
```
✅ **BLOCKED** - App exits with code 1

### Test 2: Correct Database (Should PASS)
```bash
# Restore correct DATABASE_URL
mv .env.backup .env

# Start backend
python3 -c "from backend.db.base import init_db; init_db()"
```

**Result:**
```
🔒 ENFORCING Railway PostgreSQL Connection...
✅ Connected to Railway PostgreSQL: yamabiko.proxy.rlwy.net:51955/railway
✅ Database tables verified/created
```
✅ **PASSED** - App starts successfully

## Startup Logs - Before vs After

### Before Fix
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```
❌ No database connection verification  
❌ Could start with broken database

### After Fix
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Waiting for application startup.
🔒 ENFORCING Railway PostgreSQL Connection...
✅ Connected to Railway PostgreSQL: yamabiko.proxy.rlwy.net:51955/railway
✅ Database tables verified/created
INFO:     Application startup complete.
```
✅ Clear connection verification  
✅ App CANNOT start without database

## Why Both Hooks Are Needed

### 1. Pre-Backend-Start Hook (`.claude/hooks/pre-backend-start.sh`)
**Purpose:** Checks `.env` file has Railway URL BEFORE starting Python process  
**When it runs:** Before `uvicorn backend.main:app` starts  
**What it validates:**
- `.env` file exists
- `DATABASE_URL` is set
- URL contains "railway.net" or "rlwy.net"
- Uses asyncpg driver

**Limitation:** Can't test actual connection (runs in bash subshell)

### 2. Python `init_db()` Connection Test
**Purpose:** Tests actual database connection during FastAPI startup  
**When it runs:** Inside `@app.on_event("startup")` after Python loads  
**What it validates:**
- Database host is reachable
- Credentials are valid
- Can execute queries

**Advantage:** Runs inside Python process with actual database engine

## Enforcement Layers

```
┌─────────────────────────────────────────────┐
│ Layer 1: Bash Hook (Pre-Startup)           │
│ ✓ Checks .env file                         │
│ ✓ Validates DATABASE_URL format            │
│ ✗ Cannot test actual connection            │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Layer 2: Python load_dotenv()              │
│ ✓ Loads environment variables               │
│ ✓ Raises if DATABASE_URL missing           │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Layer 3: SQLAlchemy Engine Creation        │
│ ✓ Parses connection string                 │
│ ✓ Creates connection pool                  │
│ ✗ Lazy connection - doesn't connect yet   │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│ Layer 4: init_db() Connection Test (NEW)   │
│ ✓ Actually connects to database            │
│ ✓ Executes SELECT 1 query                  │
│ ✓ Fails hard if unreachable                │
│ ✓ Clear success/error messages             │
└─────────────────────────────────────────────┘
```

## Impact

**Before:**
- App could start with broken DATABASE_URL
- First query would fail silently
- No clear indication of database status in startup logs
- User had to guess if database was connected

**After:**
- App CANNOT start without working Railway connection
- Clear "ENFORCING" + "Connected" messages in logs
- Explicit error with host/port/database on failure
- SystemExit(1) blocks startup completely

## Files Modified

1. `backend/db/base.py`:
   - Added `text` import from sqlalchemy
   - Rewrote `init_db()` with connection test and clear logging

## Related Documents

- `docs/AGENT_GUARDRAILS_ANALYSIS.md` - Original guardrails analysis
- `docs/PHASE_3_PRETOOLUSE_HOOK_IMPLEMENTATION.md` - PreToolUse hook for code changes
- `.claude/hooks/pre-backend-start.sh` - Pre-startup database URL validation

## Conclusion

**Problem:** Pre-backend-start hook checked .env but didn't test actual connection  
**Solution:** Added Python-level connection test in `init_db()` with hard failure  
**Result:** App CANNOT start without Railway PostgreSQL - ZERO TOLERANCE enforced

---

**Fixed:** 2026-03-06  
**Tested:** ✅ Blocks on broken database, passes on correct database  
**Status:** Production Ready
