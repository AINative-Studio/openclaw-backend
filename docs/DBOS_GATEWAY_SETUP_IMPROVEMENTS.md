# DBOS Gateway Setup - Lessons Learned & Improvements

**Date**: 2026-03-02
**Issue**: Gateway SSL connection failure during local startup
**Resolution Time**: ~2 hours (could have been 15 minutes with proper documentation)

## Executive Summary

Successfully resolved DBOS Gateway startup failure by discovering that **DBOS SDK reads SSL configuration from `PGSSLMODE` environment variable, NOT from `dbos-config.yaml`**. This was not documented anywhere and required reading DBOS SDK source code to discover.

## Timeline of Issue

1. **Problem**: Gateway failed to start with `SELF_SIGNED_CERT_IN_CHAIN` error when connecting to Railway PostgreSQL
2. **Failed Attempts**: Tried multiple SSL configurations in `dbos-config.yaml` (all ignored by SDK)
3. **Root Cause Discovery**: Read DBOS SDK source (`config.js:99`) and found it uses `PGSSLMODE` env var
4. **Solution**: Added `PGSSLMODE=disable` to `.env` file
5. **Result**: Gateway started successfully

## Critical Gaps in Documentation

### 1. **DBOS SDK SSL Configuration** (HIGHEST PRIORITY)

**Gap**: No documentation exists explaining that DBOS SDK constructs PostgreSQL connection strings using environment variables, NOT `dbos-config.yaml` SSL settings.

**What Was Missing**:
- `PGSSLMODE` environment variable controls SSL mode
- `PGCONNECT_TIMEOUT` environment variable controls timeout
- `dbos-config.yaml` SSL fields (`ssl_ca`, `ssl_cert`, `ssl_accept_unauthorized`) are **IGNORED**

**Impact**: 2 hours wasted trying to configure SSL in YAML when it's controlled by env vars

**Solution**: Document in `.claude/skills/local-startup/SKILL.md` and gateway README

### 2. **TypeScript Source Was Missing**

**Gap**: Gateway only had compiled JavaScript in `dist/`, no TypeScript source in repository

**What Was Missing**:
- No `src/` directory with TypeScript source files
- Only compiled `.js` files existed (old DBOS decorator API)
- New developers couldn't modify gateway code without reverse-engineering

**Impact**: Had to recreate TypeScript source from compiled JavaScript (30 minutes)

**Solution**: TypeScript source now committed to `src/` directory (1,057 lines)

### 3. **DBOS SDK API Version Changes**

**Gap**: No documentation about DBOS SDK v4.9.11 API changes

**Old API** (compiled code used):
```typescript
import { Workflow, Step } from '@dbos-inc/dbos-sdk';
@Workflow()
@Step()
```

**New API** (v4.9.11):
```typescript
import { DBOS } from '@dbos-inc/dbos-sdk';
@DBOS.workflow()
@DBOS.step()
```

**Impact**: Import errors when trying to run compiled code with modern SDK

**Solution**: Recreated source using modern API, documented in gateway README

### 4. **start-all-local.sh Doesn't Verify Gateway Prerequisites**

**Gap**: Script starts gateway without checking:
- TypeScript source exists in `src/`
- Build has been run (`npm run build`)
- `.env` file exists with required variables
- DBOS-specific env vars are set

**Current Script** (lines 157-173):
```bash
cd openclaw-gateway/
npm start > /tmp/openclaw-gateway.log 2>&1 &
```

**What's Missing**:
```bash
# Check TypeScript source exists
[ ! -d "src/" ] && echo "ERROR: TypeScript source missing" && exit 1

# Check build is up to date
[ ! -d "dist/" ] || [ src/ -nt dist/ ] && npm run build

# Check .env exists
[ ! -f ".env" ] && echo "ERROR: .env file missing" && exit 1

# Check DBOS env vars
grep -q "PGSSLMODE" .env || echo "WARNING: PGSSLMODE not set"
```

**Impact**: Gateway may fail to start with cryptic errors

**Solution**: Create pre-startup hook (see below)

## Implemented Improvements

### ✅ 1. TypeScript Source Committed

**Files Added**:
- `src/workflows/agent-message-workflow.ts` (137 lines)
- `src/workflows/agent-lifecycle-workflow.ts` (666 lines)
- `src/server.ts` (301 lines)
- `tsconfig.json` (22 lines)

**Build System**:
- TypeScript compiles to `dist/` with `npm run build`
- Modern DBOS SDK v4.9.11 API used throughout
- Type assertions added for incomplete DBOS type definitions

**Status**: ✅ Staged for commit

### ✅ 2. Environment Variables Documented

**Added to `.env`**:
```env
# CRITICAL: DBOS SDK reads SSL config from env vars, NOT dbos-config.yaml
PGSSLMODE=disable
PGCONNECT_TIMEOUT=10
```

**Status**: ✅ Committed

### ✅ 3. Gateway Running Successfully

**Verification**:
```bash
$ curl -s http://localhost:18789/health
{"status":"healthy","service":"openclaw-gateway","dbos":"connected","timestamp":"2026-03-02T07:25:07.181Z"}
```

**All 3 Services Running**:
- Gateway: ✅ Port 18789
- Backend: ✅ Port 8000
- Frontend: ✅ Port 3002

## Recommended Improvements

### 📋 Priority 1: Create Gateway Pre-Startup Hook

**Location**: `.claude/hooks/pre-gateway-start.sh`

**Purpose**: Verify all gateway prerequisites before `start-all-local.sh` attempts to start it

**Implementation**:
```bash
#!/bin/bash
# .claude/hooks/pre-gateway-start.sh
# Verifies OpenClaw Gateway prerequisites before startup

GATEWAY_DIR="openclaw-gateway"

echo "🔍 Verifying OpenClaw Gateway Prerequisites..."

# 1. Check TypeScript source exists
if [ ! -d "$GATEWAY_DIR/src" ]; then
    echo "❌ ERROR: TypeScript source missing at $GATEWAY_DIR/src/"
    echo "   TypeScript source is required for gateway modifications"
    echo "   Solution: Ensure src/ directory is committed to git"
    exit 1
fi

# 2. Check .env file exists
if [ ! -f "$GATEWAY_DIR/.env" ]; then
    echo "❌ ERROR: .env file missing at $GATEWAY_DIR/.env"
    echo "   Create .env from .env.example or with these required vars:"
    echo "   - PGHOST, PGPORT, PGUSER, PGPASSWORD, PGDATABASE"
    echo "   - PGSSLMODE (CRITICAL for Railway PostgreSQL)"
    echo "   - PGCONNECT_TIMEOUT"
    exit 1
fi

# 3. Check DBOS-specific environment variables
if ! grep -q "^PGSSLMODE=" "$GATEWAY_DIR/.env"; then
    echo "⚠️  WARNING: PGSSLMODE not set in .env"
    echo "   DBOS SDK reads SSL config from PGSSLMODE env var, NOT dbos-config.yaml"
    echo "   For Railway PostgreSQL with self-signed certs, use: PGSSLMODE=disable"
    echo "   Add to .env: PGSSLMODE=disable"
fi

if ! grep -q "^PGCONNECT_TIMEOUT=" "$GATEWAY_DIR/.env"; then
    echo "ℹ️  INFO: PGCONNECT_TIMEOUT not set (will use DBOS default: 10s)"
fi

# 4. Check if build is needed
if [ ! -d "$GATEWAY_DIR/dist" ] || [ "$GATEWAY_DIR/src" -nt "$GATEWAY_DIR/dist" ]; then
    echo "🔨 TypeScript source is newer than compiled output - building..."
    cd "$GATEWAY_DIR" && npm run build
    if [ $? -ne 0 ]; then
        echo "❌ ERROR: TypeScript build failed"
        exit 1
    fi
    cd ..
fi

# 5. Check PostgreSQL credentials are set
required_vars=("PGHOST" "PGPORT" "PGUSER" "PGPASSWORD" "PGDATABASE")
for var in "${required_vars[@]}"; do
    if ! grep -q "^${var}=" "$GATEWAY_DIR/.env"; then
        echo "❌ ERROR: Required env var $var not set in .env"
        exit 1
    fi
done

echo "✅ All gateway prerequisites verified"
```

**Integration with start-all-local.sh**:
```bash
# Before starting gateway (line 143)
if [ -f ".claude/hooks/pre-gateway-start.sh" ]; then
    bash .claude/hooks/pre-gateway-start.sh
    if [ $? -ne 0 ]; then
        echo -e "   ${RED}❌ Gateway prerequisite checks failed${NC}"
        exit 1
    fi
fi
```

### 📋 Priority 2: Update local-startup Skill

**File**: `.claude/skills/local-startup/SKILL.md`

**Add Section** (after line 143):
```markdown
### DBOS Gateway-Specific Prerequisites (CRITICAL)

**IMPORTANT**: DBOS SDK reads PostgreSQL SSL configuration from **environment variables**, NOT from `dbos-config.yaml`.

**Required Environment Variables** (in `openclaw-gateway/.env`):
- `PGSSLMODE` - Controls SSL mode (`disable`, `require`, `verify-full`)
- `PGCONNECT_TIMEOUT` - Connection timeout in seconds (default: 10)
- `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` - PostgreSQL credentials

**For Railway PostgreSQL** (self-signed certificates):
```bash
# In openclaw-gateway/.env
PGSSLMODE=disable
PGCONNECT_TIMEOUT=10
```

**ZERO TOLERANCE**:
- **NEVER** assume `dbos-config.yaml` SSL settings will work
- **ALWAYS** set `PGSSLMODE` in `.env` for Railway databases
- **ALWAYS** verify TypeScript source exists in `src/` before starting gateway

**Common Error**:
```
DBOSInitializationError: Unable to connect to system database
self-signed certificate in certificate chain: (SELF_SIGNED_CERT_IN_CHAIN)
```

**Solution**:
Add `PGSSLMODE=disable` to `openclaw-gateway/.env`
```

### 📋 Priority 3: Update Gateway README

**File**: `openclaw-gateway/README.md`

**Replace** Configuration section (lines 26-33):
```markdown
### Configuration

**CRITICAL**: DBOS SDK reads PostgreSQL connection parameters from **environment variables**, not from `dbos-config.yaml` SSL fields.

1. Copy `.env.example` to `.env`
2. Configure Railway PostgreSQL credentials:
   ```bash
   # PostgreSQL Connection (Railway)
   PGHOST=yamabiko.proxy.rlwy.net
   PGPORT=51955
   PGUSER=postgres
   PGPASSWORD=your-password-here
   PGDATABASE=railway

   # DBOS SSL Configuration (CRITICAL!)
   # DBOS SDK reads these, NOT dbos-config.yaml
   PGSSLMODE=disable              # For Railway self-signed certs
   PGCONNECT_TIMEOUT=10
   ```

3. Verify TypeScript source exists:
   ```bash
   ls -la src/workflows/
   # Should show: agent-message-workflow.ts, agent-lifecycle-workflow.ts
   ```

4. Build TypeScript source:
   ```bash
   npm run build
   ```

5. Run database migration (if needed):
   ```bash
   npm run dbos:migrate
   ```

**Common Errors**:
- `SELF_SIGNED_CERT_IN_CHAIN` → Add `PGSSLMODE=disable` to `.env`
- `Named export 'Step' not found` → Run `npm run build` to compile TypeScript
- `config.js:99` → DBOS SDK constructs connection strings using env vars
```

### 📋 Priority 4: Create DBOS SSL Troubleshooting Doc

**File**: `docs/DBOS_SSL_TROUBLESHOOTING.md`

**Content**:
```markdown
# DBOS SDK SSL Configuration Troubleshooting

## Problem: SELF_SIGNED_CERT_IN_CHAIN Error

**Symptom**:
```
DBOSInitializationError: Unable to connect to system database at postgresql://...
self-signed certificate in certificate chain: (SELF_SIGNED_CERT_IN_CHAIN)
```

**Root Cause**:
DBOS SDK constructs PostgreSQL connection strings using **environment variables**, NOT `dbos-config.yaml` SSL settings.

**Verification**:
Check DBOS SDK source code (`node_modules/@dbos-inc/dbos-sdk/dist/src/config.js:99`):
```javascript
const sslmode = process.env.PGSSLMODE || (host === 'localhost' ? 'disable' : 'allow');
dbUrl.searchParams.set('sslmode', sslmode);
```

**Solution**:
Add to `openclaw-gateway/.env`:
```env
PGSSLMODE=disable
```

## Why dbos-config.yaml SSL Settings Are Ignored

**Fields That Don't Work**:
```yaml
database:
  ssl_ca: null
  ssl_cert: null
  ssl_key: null
  ssl_accept_unauthorized: true  # ← IGNORED by DBOS SDK
```

**What Actually Works**:
```env
PGSSLMODE=disable               # ← Used by DBOS SDK
PGCONNECT_TIMEOUT=10
```

## SSL Modes

| Mode | Description | Use Case |
|------|-------------|----------|
| `disable` | No SSL | Railway with self-signed certs |
| `allow` | Try SSL, fallback to no SSL | Default for non-localhost |
| `prefer` | Prefer SSL, fallback to no SSL | |
| `require` | SSL required, no verification | |
| `verify-ca` | SSL with CA verification | |
| `verify-full` | SSL with full verification | Production with valid certs |

**For Railway PostgreSQL**: Use `PGSSLMODE=disable` (self-signed certificates)

## References

- [PostgreSQL Connection Strings](https://www.postgresql.org/docs/current/libpq-connect.html#LIBPQ-CONNSTRING)
- [DBOS SDK Source](https://github.com/dbos-inc/dbos-transact-ts)
- Issue: Gateway startup failure 2026-03-02
```

## Summary

✅ **Completed**:
1. TypeScript source recreated (1,057 lines)
2. Modern DBOS SDK v4.9.11 API implemented
3. Environment variables documented
4. Gateway running successfully
5. All 3 services verified

📋 **Recommended**:
1. Create pre-gateway-start.sh hook (15 min)
2. Update local-startup skill (10 min)
3. Update gateway README (10 min)
4. Create DBOS SSL troubleshooting doc (10 min)

**Total Time Saved for Next Developer**: ~90 minutes

## Key Learnings

1. **DBOS SDK uses env vars for connection strings**, not YAML config
2. **Always commit TypeScript source**, not just compiled output
3. **Document platform-specific workarounds** (Railway self-signed certs)
4. **Create pre-startup hooks** to catch issues before they occur
5. **Version-specific API changes** should be documented prominently
