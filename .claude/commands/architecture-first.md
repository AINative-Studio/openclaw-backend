---
description: Enforce reading documentation before code modifications
---

# Architecture-First Skill

BEFORE modifying any code in these areas, you MUST read relevant documentation:

## High-Risk Areas Requiring Docs Check

### Frontend/UI Changes
**Location:** `agent-swarm-monitor/components/`, `agent-swarm-monitor/app/`
**Docs:** `docs/chat-persistence-api.md`, integration docs

**Mandatory Steps:**
1. Search docs for component name (e.g., "chat", "conversation", "agent")
2. Read API endpoint documentation
3. Verify endpoint exists with curl test
4. Check existing implementation patterns
5. THEN modify code

### Backend API Changes
**Location:** `backend/api/v1/endpoints/`
**Docs:** `docs/SYSTEM_ARCHITECTURE.md`, feature-specific docs

**Mandatory Steps:**
1. Read architecture documentation
2. Check for existing endpoints
3. Verify data flow diagrams
4. Review service layer patterns
5. THEN add/modify endpoints

### Database Changes
**Location:** `backend/models/`, `alembic/`
**Docs:** `docs/POSTGRESQL_MIGRATION.md`, schema docs

**Mandatory Steps:**
1. Read database schema documentation
2. Use `/database-schema-sync` command
3. Never run Alembic migrations directly
4. THEN make schema changes

## Emergency Stop Command

If you realize you're modifying code without understanding the architecture:

**STOP. Execute:**
```bash
# Find relevant documentation
ls docs/ | grep -i [component_name]

# Read before proceeding
cat docs/[relevant_doc].md
```

## Verification Questions

Before committing code changes, answer:

1. ✅ Did I read the documentation for this component/feature?
2. ✅ Do I understand how it integrates with the rest of the system?
3. ✅ Did I verify the API endpoints exist with curl?
4. ✅ Did I check for existing patterns in the codebase?

If any answer is NO → STOP and read documentation.

## Real Incident Example

**Date:** 2026-03-06

**What Happened:**
1. User reported: "simulated response from Main Agent" error
2. Agent jumped straight to changing frontend code
3. Agent created wrong API endpoint call without checking existing architecture
4. User caught the error: "did you read the docs before you just start changing fucking code"
5. Agent discovered 5,109 lines of comprehensive chat persistence documentation **after** making changes

**What Should Have Happened:**
1. Agent sees "simulated response" error
2. Agent searches for `chat*` or `conversation*` documentation
3. Agent finds `docs/chat-persistence-api.md`
4. Agent learns `/api/v1/agents/{id}/message` endpoint exists
5. Agent implements correctly the first time

**Lesson:** If 5,109 lines of documentation exist, agents MUST read it before making changes.
