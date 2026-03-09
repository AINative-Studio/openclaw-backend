# Phase 4: Skill Workflows Architecture

## Overview

Phase 4 implements durable skill installation and execution using DBOS workflows. The architecture ensures crash recovery, automatic rollback, and complete audit trails for all skill operations.

---

## System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                          OpenClaw System                             │
├─────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  ┌───────────────┐         ┌──────────────┐      ┌──────────────┐  │
│  │   WhatsApp    │────────▶│   Gateway    │─────▶│   Backend    │  │
│  │   Interface   │         │  (DBOS Node) │      │  (FastAPI)   │  │
│  └───────────────┘         └──────────────┘      └──────────────┘  │
│                                   │                      │           │
│                                   │                      │           │
│                                   ▼                      ▼           │
│                            ┌──────────────┐      ┌──────────────┐  │
│                            │  PostgreSQL  │      │ OpenClaw CLI │  │
│                            │   (Railway)  │      │   (Skills)   │  │
│                            └──────────────┘      └──────────────┘  │
│                                                                       │
└─────────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

**Gateway (port 18789)**:
- Receives workflow requests via HTTP POST
- Executes DBOS durable workflows
- Manages crash recovery and resume
- Records workflow state in PostgreSQL

**Backend (port 8000)**:
- Executes actual skill installation commands
- Runs skill execution binaries
- Validates prerequisites and binary paths
- Returns results to Gateway

**PostgreSQL (Railway)**:
- Stores DBOS workflow state
- Stores skill installation history
- Stores skill execution history
- Provides crash recovery state

**OpenClaw CLI**:
- Provides skill installation commands
- Provides skill execution commands
- Manages skill binaries and dependencies

---

## Workflow Architecture

### 1. Skill Installation Workflow

```mermaid
graph TD
    A[POST /workflows/skill-installation] --> B{Validate Request}
    B -->|Invalid| C[Return 400 Error]
    B -->|Valid| D[Start Workflow]

    D --> E[@Step: validatePrerequisites]
    E --> F{Method Available?}
    F -->|No| G[Return PREREQUISITE_MISSING]
    F -->|Yes| H[@Step: recordInstallationStart]

    H --> I[Insert DB: STARTED]
    I --> J[@Step: executeInstallation]

    J --> K[POST /api/v1/skills/NAME/install]
    K --> L{Success?}
    L -->|No| M[@Step: rollbackInstallation]
    M --> N[Update DB: ROLLED_BACK]
    N --> O[Return Failure]

    L -->|Yes| P[@Step: verifyBinary]
    P --> Q{Binary Exists?}
    Q -->|No| R[Update DB: FAILED]
    R --> O

    Q -->|Yes| S[@Step: recordSuccess]
    S --> T[Update DB: COMPLETED]
    T --> U[Return Success]

    style E fill:#e1f5fe
    style H fill:#e1f5fe
    style J fill:#e1f5fe
    style M fill:#e1f5fe
    style P fill:#e1f5fe
    style S fill:#e1f5fe
```

**DBOS Steps** (blue boxes):
- Each `@Step` is durable and exactly-once
- If Gateway crashes, workflow resumes from last completed step
- Steps are never re-executed (idempotent by design)

---

### 2. Skill Execution Workflow

```mermaid
graph TD
    A[POST /workflows/skill-execution] --> B{Validate Request}
    B -->|Invalid| C[Return 400 Error]
    B -->|Valid| D[Start Workflow]

    D --> E[@Step: validateInstallation]
    E --> F{Skill Installed?}
    F -->|No| G[Return SKILL_NOT_INSTALLED]
    F -->|Yes| H[@Step: checkPermissions]

    H --> I{Has Permission?}
    I -->|No| J[Return PERMISSION_DENIED]
    I -->|Yes| K[@Step: recordExecutionStart]

    K --> L[Insert DB: RUNNING]
    L --> M[@Step: executeSkill]

    M --> N[POST /api/v1/skills/NAME/execute]
    N --> O{Success?}
    O -->|Timeout| P[@Step: recordTimeout]
    P --> Q[Update DB: TIMEOUT]
    Q --> R[Return Timeout Error]

    O -->|Failed| S[@Step: recordFailure]
    S --> T[Update DB: FAILED]
    T --> U[Return Failure]

    O -->|Success| V[@Step: recordSuccess]
    V --> W[Update DB: COMPLETED]
    W --> X[Return Success + Output]

    style E fill:#e1f5fe
    style H fill:#e1f5fe
    style K fill:#e1f5fe
    style M fill:#e1f5fe
    style P fill:#e1f5fe
    style S fill:#e1f5fe
    style V fill:#e1f5fe
```

---

## Database Schema Design

### Entity Relationship Diagram

```
┌─────────────────────────────┐
│ skill_installation_history  │
├─────────────────────────────┤
│ id (PK)                     │
│ skill_name                  │
│ agent_id (FK) ◄─────────┐   │
│ status                  │   │
│ method                  │   │
│ binary_path             │   │
│ started_at              │   │
│ completed_at            │   │
│ error_message           │   │
└─────────────────────────┘   │
                              │
                              │
┌─────────────────────────────┐
│ skill_execution_history     │
├─────────────────────────────┤
│ id (PK)                     │
│ execution_id (UNIQUE)       │
│ skill_name                  │
│ agent_id (FK) ──────────────┘
│ status                      │
│ parameters (JSONB)          │
│ output                      │
│ error_message               │
│ execution_time_ms           │
│ started_at                  │
│ completed_at                │
└─────────────────────────────┘

Note: agent_id is FK to agents table (not shown - part of existing schema)
```

### Index Strategy

**Installation History**:
1. Primary lookup: `skill_name` - check if skill is installed
2. Audit queries: `agent_id` - who installed what
3. Monitoring: `status` - find failures
4. Composite: `(skill_name, status)` - fast "is installed?" check

**Execution History**:
1. Workflow tracking: `execution_id` (unique) - find specific execution
2. Skill analysis: `skill_name` - usage patterns
3. Agent tracking: `agent_id` - agent activity
4. Recent activity: `started_at DESC` - timeline queries
5. Usage patterns: `(skill_name, agent_id)` - agent-skill relationships

---

## Crash Recovery Scenarios

### Scenario 1: Gateway Crashes During Installation

```
Timeline:
─────────────────────────────────────────────────────────────────
T0: POST /workflows/skill-installation received
T1: @Step: validatePrerequisites → COMPLETED
T2: @Step: recordInstallationStart → COMPLETED (DB: STARTED)
T3: @Step: executeInstallation → IN PROGRESS
T4: Backend installing skill...
T5: ⚠️  GATEWAY CRASHES
─────────────────────────────────────────────────────────────────
T6: Gateway restarts
T7: DBOS resumes workflow from T3
T8: @Step: executeInstallation → RETRIES
T9: Backend returns success (idempotent - already installed)
T10: @Step: verifyBinary → COMPLETED
T11: @Step: recordSuccess → COMPLETED (DB: COMPLETED)
T12: Response returned to client (or workflow marked complete)
─────────────────────────────────────────────────────────────────
```

**Key Points**:
- Steps T1-T2 are NOT re-executed
- Step T3 retries from beginning
- Backend installation is idempotent (npm/brew skip if already installed)
- Final state is consistent

---

### Scenario 2: Gateway Crashes During Execution

```
Timeline:
─────────────────────────────────────────────────────────────────
T0: POST /workflows/skill-execution received
T1: @Step: validateInstallation → COMPLETED
T2: @Step: checkPermissions → COMPLETED
T3: @Step: recordExecutionStart → COMPLETED (DB: RUNNING)
T4: @Step: executeSkill → IN PROGRESS
T5: Backend executing skill...
T6: Skill producing output...
T7: ⚠️  GATEWAY CRASHES
─────────────────────────────────────────────────────────────────
T8: Gateway restarts
T9: DBOS resumes workflow from T4
T10: @Step: executeSkill → RETRIES
T11: Backend re-executes skill (NEW execution)
T12: Skill completes (may have different output)
T13: @Step: recordSuccess → COMPLETED (DB: COMPLETED)
T14: Response returned (latest output)
─────────────────────────────────────────────────────────────────
```

**Key Points**:
- Skill is executed TWICE (once before crash, once after)
- Only the second execution's output is captured
- This is acceptable for most skills (read operations are idempotent)
- For non-idempotent skills, client should use execution_id to detect duplicates

---

### Scenario 3: Installation Fails and Rollback Crashes

```
Timeline:
─────────────────────────────────────────────────────────────────
T0: POST /workflows/skill-installation received
T1: @Step: executeInstallation → FAILED (npm install error)
T2: @Step: rollbackInstallation → IN PROGRESS
T3: Backend uninstalling...
T4: ⚠️  GATEWAY CRASHES DURING ROLLBACK
─────────────────────────────────────────────────────────────────
T5: Gateway restarts
T6: DBOS resumes workflow from T2
T7: @Step: rollbackInstallation → RETRIES
T8: Backend uninstall completes (idempotent)
T9: DB updated: ROLLED_BACK
T10: Response returned: {success: false, error: "..."}
─────────────────────────────────────────────────────────────────
```

**Key Points**:
- Rollback is retried after crash
- Backend uninstall is idempotent
- Final state: clean rollback, no partial installation

---

## Error Handling Flows

### Installation Error Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Installation Error Flow                      │
└─────────────────────────────────────────────────────────────────┘

Error Type                    Handler                 DB Status
──────────────────────────────────────────────────────────────────
Prerequisite Missing     → Return early          → (no DB record)

Installation Failed      → @Step: rollback       → ROLLED_BACK
                          → npm uninstall
                          → brew uninstall

Binary Not Found         → No rollback           → FAILED
(after install)          → Backend install OK
                          → But binary missing

Rollback Failed          → Log error             → FAILED
                          → Leave partial state
                          → Alert admin

Database Error           → Retry transaction     → (retried)
                          → If persist: fail
                          → Manual cleanup
──────────────────────────────────────────────────────────────────
```

---

### Execution Error Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     Execution Error Flow                         │
└─────────────────────────────────────────────────────────────────┘

Error Type                    Handler                 DB Status
──────────────────────────────────────────────────────────────────
Skill Not Installed      → Return early          → (no DB record)
                          → HTTP 400

Permission Denied        → Return early          → (no DB record)
                          → HTTP 403

Execution Timeout        → Kill process          → TIMEOUT
                          → Capture partial
                            output

Skill Failed             → Capture error         → FAILED
(exit code != 0)          → Store stderr

Database Error           → Retry transaction     → (retried)
                          → Execution completes
                          → Result may be lost

Backend Unreachable      → Retry with backoff    → RUNNING
                          → Max 3 retries
                          → Then mark FAILED
──────────────────────────────────────────────────────────────────
```

---

## State Transitions

### Installation States

```
                    ┌──────────┐
                    │ (start)  │
                    └────┬─────┘
                         │
                    POST /workflows/
                    skill-installation
                         │
                         ▼
                   ┌──────────┐
           ┌───────│ STARTED  │
           │       └────┬─────┘
           │            │
           │      executeInstallation
           │            │
           │            ├────success────┐
           │            │               │
           │         failure        verifyBinary
           │            │               │
           │            ▼               ├─found─────┐
           │     ┌────────────┐         │           │
           │     │ ROLLED_BACK│      not found      │
           │     └────────────┘         │           │
           │                            ▼           ▼
           │                      ┌──────────┐ ┌───────────┐
           └──rollback failed───▶ │  FAILED  │ │ COMPLETED │
                                  └──────────┘ └───────────┘
```

**Valid Transitions**:
- `STARTED` → `COMPLETED` (happy path)
- `STARTED` → `FAILED` (installation succeeded but binary not found)
- `STARTED` → `ROLLED_BACK` (installation failed, rollback succeeded)
- `STARTED` → `FAILED` (installation failed, rollback also failed)

**Terminal States**: `COMPLETED`, `FAILED`, `ROLLED_BACK`

---

### Execution States

```
                    ┌──────────┐
                    │ (start)  │
                    └────┬─────┘
                         │
                    POST /workflows/
                    skill-execution
                         │
                         ▼
                   ┌──────────┐
                   │ RUNNING  │
                   └────┬─────┘
                        │
                  executeSkill
                        │
        ┌───────────────┼───────────────┐
        │               │               │
     timeout         failure         success
        │               │               │
        ▼               ▼               ▼
   ┌─────────┐    ┌──────────┐   ┌───────────┐
   │ TIMEOUT │    │  FAILED  │   │ COMPLETED │
   └─────────┘    └──────────┘   └───────────┘
```

**Valid Transitions**:
- `RUNNING` → `COMPLETED` (happy path)
- `RUNNING` → `FAILED` (execution error)
- `RUNNING` → `TIMEOUT` (exceeded time limit)

**Terminal States**: `COMPLETED`, `FAILED`, `TIMEOUT`

---

## Performance Characteristics

### Installation Workflow

| Operation | Typical Duration | Notes |
|-----------|------------------|-------|
| Validate Prerequisites | 10-50ms | Check npm/brew availability |
| Record Start (DB) | 20-100ms | Single INSERT |
| Execute Installation | 5-60s | Network-dependent (npm registry, Homebrew) |
| Verify Binary | 10-50ms | Filesystem check |
| Record Success (DB) | 20-100ms | Single UPDATE |
| **Total** | **5-60s** | Dominated by npm/brew install |

### Execution Workflow

| Operation | Typical Duration | Notes |
|-----------|------------------|-------|
| Validate Installation | 50-200ms | DB query + index lookup |
| Check Permissions | 10-50ms | In-memory check (future: DB query) |
| Record Start (DB) | 20-100ms | Single INSERT |
| Execute Skill | 100ms-300s | Skill-dependent (timeout enforced) |
| Record Success (DB) | 20-100ms | Single UPDATE |
| **Total** | **200ms-300s** | Dominated by skill execution |

### Database Performance

**Installation History**:
- Insert rate: ~100 records/second (limited by workflow rate)
- Query rate: ~1000 queries/second (with proper indexing)
- Storage: ~1KB per record → 1M records = 1GB

**Execution History**:
- Insert rate: ~500 records/second (limited by workflow rate)
- Query rate: ~2000 queries/second (with proper indexing)
- Storage: ~5KB per record (with output) → 1M records = 5GB

**Retention Strategy**:
- Keep all installation records (historical reference)
- Archive execution records older than 90 days
- Compress archived records (output field is large)

---

## Security Architecture

### Defense in Depth

```
Layer 1: Input Validation
─────────────────────────────────────────────────────────
- Skill name: alphanumeric + hyphens only
- Method: enum validation (npm/brew/manual)
- Agent ID: UUID validation
- Parameters: JSON schema validation (skill-specific)

Layer 2: Installation Method Security
─────────────────────────────────────────────────────────
- npm: Run with --ignore-scripts (prevent arbitrary code)
- brew: Run with --no-quarantine (skip code signature)
- manual: Require explicit binary path verification

Layer 3: Execution Isolation
─────────────────────────────────────────────────────────
- Timeout enforcement: OS-level process kill
- Resource limits: memory/CPU caps (future)
- Sandboxing: containerization (future)

Layer 4: Audit Trail
─────────────────────────────────────────────────────────
- Complete installation history with agent attribution
- Complete execution history with parameters and output
- Immutable logs (append-only tables)

Layer 5: Authorization
─────────────────────────────────────────────────────────
- Agent authentication via Gateway (existing)
- Skill permission checks (future: RBAC)
- Rate limiting per agent (future)
```

---

## Troubleshooting Guide

### Common Issues

#### 1. Installation Stuck in STARTED State

**Symptom**: Record in DB with status `STARTED`, no `completed_at`

**Diagnosis**:
```sql
SELECT id, skill_name, agent_id, started_at,
       NOW() - started_at as duration
FROM skill_installation_history
WHERE status = 'STARTED'
  AND started_at < NOW() - INTERVAL '5 minutes';
```

**Possible Causes**:
- Gateway crashed during installation
- DBOS workflow queue backed up
- Backend unreachable

**Resolution**:
1. Check Gateway logs for crash/restart
2. Check DBOS workflow status: `SELECT * FROM dbos.workflow_status WHERE workflow_uuid = ...`
3. If workflow is stuck, manually update DB: `UPDATE skill_installation_history SET status = 'FAILED', error_message = 'Manual cleanup after timeout' WHERE id = ...`

---

#### 2. Execution Returns Stale Output

**Symptom**: Skill execution returns cached/old output

**Diagnosis**:
```sql
SELECT execution_id, skill_name, started_at, completed_at,
       SUBSTRING(output, 1, 100) as output_preview
FROM skill_execution_history
WHERE skill_name = 'himalaya'
  AND agent_id = 'agent-xyz-789'
ORDER BY started_at DESC
LIMIT 5;
```

**Possible Causes**:
- Gateway crash caused retry with old output
- Skill is caching output (skill bug)
- DBOS workflow replayed with stale state

**Resolution**:
1. Check execution_id - if duplicate, workflow was retried
2. Re-run execution with different parameters to verify
3. Check skill implementation for caching bugs

---

#### 3. High Installation Failure Rate

**Symptom**: Many installations with status `FAILED` or `ROLLED_BACK`

**Diagnosis**:
```sql
SELECT skill_name, status, COUNT(*) as count,
       AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_sec
FROM skill_installation_history
WHERE started_at > NOW() - INTERVAL '1 day'
GROUP BY skill_name, status
ORDER BY count DESC;
```

**Possible Causes**:
- npm registry unreachable
- Homebrew repository issues
- Binary path misconfigured
- Disk space exhausted

**Resolution**:
1. Check error messages: `SELECT DISTINCT error_message FROM skill_installation_history WHERE status = 'FAILED' LIMIT 10`
2. Verify npm/brew availability on Backend server
3. Check disk space: `df -h`
4. Test manual installation: `npm install -g @openclaw/skill-name`

---

## Deployment Considerations

### Database Migrations

Run before deploying Phase 4:

```bash
# From openclaw-gateway directory
cd /Users/aideveloper/openclaw-backend/openclaw-gateway

# Run migration
psql $DATABASE_URL -f migrations/phase4_skill_workflows.sql

# Verify tables created
psql $DATABASE_URL -c "\d skill_installation_history"
psql $DATABASE_URL -c "\d skill_execution_history"
```

### Rollback Plan

If Phase 4 needs rollback:

```sql
-- Drop tables (data loss!)
DROP TABLE IF EXISTS skill_execution_history;
DROP TABLE IF EXISTS skill_installation_history;

-- Remove DBOS workflows (if needed)
DELETE FROM dbos.workflow_status
WHERE workflow_class_name IN ('SkillInstallationWorkflow', 'SkillExecutionWorkflow');
```

### Monitoring Setup

1. **Alert on stuck workflows**:
```sql
-- Alert if workflows stuck in STARTED for >10 minutes
SELECT COUNT(*) as stuck_count
FROM skill_installation_history
WHERE status = 'STARTED'
  AND started_at < NOW() - INTERVAL '10 minutes';
```

2. **Alert on high failure rate**:
```sql
-- Alert if failure rate >20% in last hour
SELECT
    (COUNT(*) FILTER (WHERE status IN ('FAILED', 'ROLLED_BACK')))::FLOAT /
    COUNT(*) as failure_rate
FROM skill_installation_history
WHERE started_at > NOW() - INTERVAL '1 hour';
```

3. **Dashboard queries** (see PHASE_4_EXAMPLES.md for full set)

---

## Future Enhancements

### Phase 4.1: Permission System
- Add `skill_permissions` table
- Implement RBAC for skill execution
- Check permissions in execution workflow

### Phase 4.2: Resource Limits
- Add CPU/memory limits per skill
- Track resource usage in execution history
- Enforce limits at OS level (cgroups)

### Phase 4.3: Caching
- Cache skill installation status (Redis)
- Cache binary path verification
- Invalidate on DB update

### Phase 4.4: Parallel Execution
- Allow multiple concurrent executions per agent
- Queue management for rate limiting
- Priority-based scheduling

### Phase 4.5: Skill Versioning
- Track skill versions in installation history
- Allow side-by-side version installations
- Version-specific execution

---

## References

- DBOS SDK Documentation: https://docs.dbos.dev/
- OpenClaw CLI Source: `/Users/aideveloper/openclaw-backend/openclaw-gateway/src/workflows/`
- API Documentation: `PHASE_4_API.md`
- Usage Examples: `PHASE_4_EXAMPLES.md`
