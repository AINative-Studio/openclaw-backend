# Phase 4: Skill Workflows API

## Overview

Phase 4 introduces durable skill installation and execution workflows with crash recovery, automatic rollback, and comprehensive audit trails. All workflows are powered by DBOS durable execution, ensuring no operation is lost even if the Gateway crashes.

---

## Endpoints

### POST /workflows/skill-installation

Install a skill with crash recovery and automatic rollback on failure.

**Request**:
```json
{
  "skillName": "bear-notes",
  "method": "npm",
  "agentId": "agent-uuid-123"  // optional
}
```

**Request Fields**:
- `skillName` (required): Name of the skill to install (matches OpenClaw CLI skill name)
- `method` (required): Installation method - `"npm"`, `"brew"`, or `"manual"`
- `agentId` (optional): UUID of the agent requesting installation (for audit trail)

**Response (Success - HTTP 200)**:
```json
{
  "success": true,
  "skillName": "bear-notes",
  "installedAt": "2026-03-07T12:00:00Z",
  "binaryPath": "/usr/local/bin/grizzly"
}
```

**Response (Failure - HTTP 200)**:
```json
{
  "success": false,
  "skillName": "bear-notes",
  "error": "Binary verification failed: /usr/local/bin/grizzly does not exist"
}
```

**Response (Validation Error - HTTP 400)**:
```json
{
  "error": "Missing required field: skillName"
}
```

**Workflow Steps**:
1. **Validate Prerequisites** - Check if installation method is available (npm/brew installed)
2. **Record Installation Start** - Insert record into `skill_installation_history` with status `STARTED`
3. **Execute Installation** - Call Backend: `POST /api/v1/skills/{skillName}/install`
4. **Verify Binary** - Check that expected binary exists at specified path
5. **Record Success** - Update DB record with status `COMPLETED` and binary path

**On Failure**:
- Automatic rollback of installation (uninstall command)
- DB record updated with status `ROLLED_BACK` or `FAILED`
- Complete error details captured in `error_message` field

**Crash Recovery**:
- If Gateway crashes during installation, workflow resumes from last completed step
- No duplicate installations (idempotency guaranteed)
- Partial installations automatically rolled back on resume

**Error Codes**:
- `PREREQUISITE_MISSING`: Installation method (npm/brew) not available
- `INSTALLATION_FAILED`: Backend installation command failed
- `BINARY_VERIFICATION_FAILED`: Expected binary not found after installation
- `ROLLBACK_FAILED`: Installation succeeded but rollback during error recovery failed

---

### POST /workflows/skill-execution

Execute a skill with permission checks, timeout enforcement, and complete audit trail.

**Request**:
```json
{
  "skillName": "himalaya",
  "agentId": "agent-uuid-456",
  "parameters": {
    "command": "list",
    "folder": "inbox"
  },
  "timeoutSeconds": 60
}
```

**Request Fields**:
- `skillName` (required): Name of the skill to execute
- `agentId` (required): UUID of the agent executing the skill
- `parameters` (required): Skill-specific parameters (passed to skill command)
- `timeoutSeconds` (optional): Execution timeout in seconds (default: 30, max: 300)

**Response (Success - HTTP 200)**:
```json
{
  "success": true,
  "skillName": "himalaya",
  "output": "Inbox (3 messages)\n1. Welcome to Himalaya\n2. Test message\n3. Another test",
  "executionTimeMs": 1234,
  "executionId": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (Failure - HTTP 200)**:
```json
{
  "success": false,
  "skillName": "himalaya",
  "error": "Skill execution failed: Connection timeout",
  "executionTimeMs": 60000,
  "executionId": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response (Validation Error - HTTP 400)**:
```json
{
  "error": "Skill not installed: himalaya"
}
```

**Workflow Steps**:
1. **Validate Installation** - Check skill is installed in `skill_installation_history`
2. **Check Permissions** - Verify agent has permission to execute skill (future: RBAC)
3. **Record Execution Start** - Insert record into `skill_execution_history` with status `RUNNING`
4. **Execute Skill** - Call Backend: `POST /api/v1/skills/{skillName}/execute`
5. **Capture Output** - Store stdout/stderr from skill execution
6. **Record Result** - Update DB with status `COMPLETED`/`FAILED`, output, and execution time

**On Crash**:
- Workflow resumes from last step
- Execution state preserved in DB
- Output captured even if Gateway crashes during execution

**Timeout Handling**:
- Enforced at Backend level (skill process killed after timeout)
- DB record updated with status `TIMEOUT`
- Partial output captured before timeout

**Error Codes**:
- `SKILL_NOT_INSTALLED`: Skill must be installed before execution
- `PERMISSION_DENIED`: Agent lacks permission to execute skill
- `EXECUTION_TIMEOUT`: Skill exceeded timeout limit
- `EXECUTION_FAILED`: Skill command returned non-zero exit code
- `INVALID_PARAMETERS`: Skill-specific parameter validation failed

---

## Database Schema

### skill_installation_history

Tracks all skill installation attempts with complete audit trail.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PRIMARY KEY | Auto-generated unique identifier |
| skill_name | VARCHAR(255) | NOT NULL | Skill being installed (e.g., "bear-notes") |
| agent_id | UUID | NULLABLE | Agent requesting install (NULL for system installs) |
| status | VARCHAR(50) | NOT NULL | STARTED/COMPLETED/FAILED/ROLLED_BACK |
| method | VARCHAR(50) | NOT NULL | Installation method: npm/brew/manual |
| binary_path | VARCHAR(500) | NULLABLE | Path to installed binary (NULL until verified) |
| started_at | TIMESTAMPTZ | NOT NULL | When installation workflow started |
| completed_at | TIMESTAMPTZ | NULLABLE | When installation finished (NULL if still running) |
| error_message | TEXT | NULLABLE | Error details if status is FAILED |

**Indexes**:
- Primary key on `id`
- Index on `skill_name` (for lookups)
- Index on `agent_id` (for audit queries)
- Index on `status` (for monitoring failed installs)
- Composite index on `(skill_name, status)` (for checking if skill is installed)

**Sample Row**:
```sql
id: '123e4567-e89b-12d3-a456-426614174000'
skill_name: 'bear-notes'
agent_id: 'agent-abc-123'
status: 'COMPLETED'
method: 'npm'
binary_path: '/usr/local/bin/grizzly'
started_at: '2026-03-07 12:00:00+00'
completed_at: '2026-03-07 12:00:15+00'
error_message: NULL
```

---

### skill_execution_history

Tracks all skill executions with performance metrics.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| id | UUID | PRIMARY KEY | Auto-generated unique identifier |
| execution_id | UUID | NOT NULL, UNIQUE | Unique execution identifier (workflow UUID) |
| skill_name | VARCHAR(255) | NOT NULL | Skill being executed (e.g., "himalaya") |
| agent_id | UUID | NOT NULL | Agent executing the skill |
| status | VARCHAR(50) | NOT NULL | RUNNING/COMPLETED/FAILED/TIMEOUT |
| parameters | JSONB | NOT NULL | Skill-specific parameters (e.g., {"command": "list"}) |
| output | TEXT | NULLABLE | Captured stdout/stderr from skill |
| error_message | TEXT | NULLABLE | Error details if status is FAILED |
| execution_time_ms | INTEGER | NULLABLE | Execution duration in milliseconds |
| started_at | TIMESTAMPTZ | NOT NULL | When execution started |
| completed_at | TIMESTAMPTZ | NULLABLE | When execution finished (NULL if still running) |

**Indexes**:
- Primary key on `id`
- Unique index on `execution_id` (workflow UUID)
- Index on `skill_name` (for skill-specific queries)
- Index on `agent_id` (for agent activity tracking)
- Index on `status` (for monitoring failures)
- Index on `started_at DESC` (for recent activity queries)
- Composite index on `(skill_name, agent_id)` (for agent-skill usage patterns)

**Sample Row**:
```sql
id: '234e5678-e89b-12d3-a456-426614174001'
execution_id: '345e6789-e89b-12d3-a456-426614174002'
skill_name: 'himalaya'
agent_id: 'agent-xyz-789'
status: 'COMPLETED'
parameters: '{"command": "list", "folder": "inbox"}'
output: 'Inbox (3 messages)\n1. Welcome...'
error_message: NULL
execution_time_ms: 1234
started_at: '2026-03-07 12:05:00+00'
completed_at: '2026-03-07 12:05:01.234+00'
```

---

## Migration Script

Create tables with:

```sql
-- Migration: Phase 4 Skill Workflows
-- Created: 2026-03-07

-- Skill installation history
CREATE TABLE IF NOT EXISTS skill_installation_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_name VARCHAR(255) NOT NULL,
    agent_id UUID,
    status VARCHAR(50) NOT NULL CHECK (status IN ('STARTED', 'COMPLETED', 'FAILED', 'ROLLED_BACK')),
    method VARCHAR(50) NOT NULL CHECK (method IN ('npm', 'brew', 'manual')),
    binary_path VARCHAR(500),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    error_message TEXT
);

CREATE INDEX idx_skill_installation_skill_name ON skill_installation_history(skill_name);
CREATE INDEX idx_skill_installation_agent_id ON skill_installation_history(agent_id);
CREATE INDEX idx_skill_installation_status ON skill_installation_history(status);
CREATE INDEX idx_skill_installation_skill_status ON skill_installation_history(skill_name, status);

-- Skill execution history
CREATE TABLE IF NOT EXISTS skill_execution_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID NOT NULL UNIQUE,
    skill_name VARCHAR(255) NOT NULL,
    agent_id UUID NOT NULL,
    status VARCHAR(50) NOT NULL CHECK (status IN ('RUNNING', 'COMPLETED', 'FAILED', 'TIMEOUT')),
    parameters JSONB NOT NULL,
    output TEXT,
    error_message TEXT,
    execution_time_ms INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE UNIQUE INDEX idx_skill_execution_id ON skill_execution_history(execution_id);
CREATE INDEX idx_skill_execution_skill_name ON skill_execution_history(skill_name);
CREATE INDEX idx_skill_execution_agent_id ON skill_execution_history(agent_id);
CREATE INDEX idx_skill_execution_status ON skill_execution_history(status);
CREATE INDEX idx_skill_execution_started_at ON skill_execution_history(started_at DESC);
CREATE INDEX idx_skill_execution_skill_agent ON skill_execution_history(skill_name, agent_id);
```

---

## Status Values

### Installation Status
- `STARTED`: Installation workflow initiated
- `COMPLETED`: Installation successful, binary verified
- `FAILED`: Installation failed, rollback may have occurred
- `ROLLED_BACK`: Installation failed and was successfully rolled back

### Execution Status
- `RUNNING`: Skill execution in progress
- `COMPLETED`: Skill executed successfully
- `FAILED`: Skill execution failed (non-zero exit code)
- `TIMEOUT`: Skill execution exceeded timeout limit

---

## Rate Limits

- **Installation**: Max 10 concurrent installations per Gateway instance
- **Execution**: Max 50 concurrent executions per Gateway instance
- **Per-Agent**: Max 5 concurrent executions per agent

Exceeding rate limits returns HTTP 429 (Too Many Requests).

---

## Monitoring

### Prometheus Metrics (Future)

```
# Installation metrics
skill_installations_total{status="completed|failed|rolled_back"}
skill_installation_duration_seconds{skill_name}

# Execution metrics
skill_executions_total{skill_name,status="completed|failed|timeout"}
skill_execution_duration_seconds{skill_name}
skill_execution_timeout_total{skill_name}
```

### Health Check

Query database for recent failures:

```sql
-- Recent installation failures
SELECT skill_name, COUNT(*) as failure_count
FROM skill_installation_history
WHERE status IN ('FAILED', 'ROLLED_BACK')
  AND started_at > NOW() - INTERVAL '1 hour'
GROUP BY skill_name
ORDER BY failure_count DESC;

-- Recent execution failures
SELECT skill_name, COUNT(*) as failure_count
FROM skill_execution_history
WHERE status IN ('FAILED', 'TIMEOUT')
  AND started_at > NOW() - INTERVAL '1 hour'
GROUP BY skill_name
ORDER BY failure_count DESC;
```

---

## Security Considerations

1. **Input Validation**: All skill names validated against allowed character set (alphanumeric + hyphens)
2. **Agent Authorization**: Future: RBAC enforcement at permission check step
3. **Output Sanitization**: Skill output truncated at 1MB to prevent DoS
4. **Timeout Enforcement**: Hard timeout enforced at OS process level
5. **Audit Trail**: Complete history of who installed/executed what and when

---

## API Versioning

Current version: **v1**

All endpoints are prefixed with `/workflows/` to indicate DBOS durable workflows.

Future versioning will follow pattern: `/v2/workflows/skill-installation`
