# Phase 4: Usage Examples

## Overview

This document provides real-world usage examples for Phase 4 skill installation and execution workflows. All examples use the Gateway API at `http://localhost:18789`.

---

## Example 1: Install a Skill via Gateway

### Basic Installation

Install the `bear-notes` skill using npm:

```bash
curl -X POST http://localhost:18789/workflows/skill-installation \
  -H "Content-Type: application/json" \
  -d '{
    "skillName": "bear-notes",
    "method": "npm",
    "agentId": "550e8400-e29b-41d4-a716-446655440000"
  }'
```

**Response (Success)**:
```json
{
  "success": true,
  "skillName": "bear-notes",
  "installedAt": "2026-03-07T12:00:15.234Z",
  "binaryPath": "/usr/local/bin/grizzly"
}
```

**What Happens Behind the Scenes**:

1. **Validate Prerequisites** (Step 1):
   - Gateway checks if npm is installed
   - If not: returns `{"success": false, "error": "npm not found"}`

2. **Record Installation Start** (Step 2):
   - Inserts record into `skill_installation_history`:
     ```sql
     INSERT INTO skill_installation_history
       (skill_name, agent_id, status, method, started_at)
     VALUES
       ('bear-notes', '550e8400...', 'STARTED', 'npm', NOW())
     ```

3. **Execute Installation** (Step 3):
   - Calls Backend: `POST http://localhost:8000/api/v1/skills/bear-notes/install`
   - Backend runs: `npm install -g @openclaw/bear-notes`
   - Backend returns: `{"success": true, "binaryPath": "/usr/local/bin/grizzly"}`

4. **Verify Binary** (Step 4):
   - Gateway checks if `/usr/local/bin/grizzly` exists
   - If not: rolls back installation and returns failure

5. **Record Success** (Step 5):
   - Updates DB record:
     ```sql
     UPDATE skill_installation_history
     SET status = 'COMPLETED',
         binary_path = '/usr/local/bin/grizzly',
         completed_at = NOW()
     WHERE id = '...'
     ```

**Timeline**: ~10-30 seconds (dominated by npm install)

---

### Installation with Homebrew

Install `himalaya` email client using Homebrew:

```bash
curl -X POST http://localhost:18789/workflows/skill-installation \
  -H "Content-Type: application/json" \
  -d '{
    "skillName": "himalaya",
    "method": "brew",
    "agentId": "660e9511-f30c-52e5-b827-557766551111"
  }'
```

**Response (Success)**:
```json
{
  "success": true,
  "skillName": "himalaya",
  "installedAt": "2026-03-07T12:05:42.567Z",
  "binaryPath": "/usr/local/bin/himalaya"
}
```

**Backend Command**:
```bash
brew install himalaya
```

**Timeline**: ~30-120 seconds (Homebrew downloads source)

---

### Installation Failure Example

Attempt to install non-existent skill:

```bash
curl -X POST http://localhost:18789/workflows/skill-installation \
  -H "Content-Type: application/json" \
  -d '{
    "skillName": "nonexistent-skill",
    "method": "npm"
  }'
```

**Response (Failure)**:
```json
{
  "success": false,
  "skillName": "nonexistent-skill",
  "error": "Installation failed: npm ERR! 404 '@openclaw/nonexistent-skill' is not in the npm registry."
}
```

**Database Record**:
```sql
-- After automatic rollback
SELECT * FROM skill_installation_history
WHERE skill_name = 'nonexistent-skill'
ORDER BY started_at DESC LIMIT 1;

-- Result:
id           | 770fa622-...
skill_name   | nonexistent-skill
status       | ROLLED_BACK
method       | npm
started_at   | 2026-03-07 12:10:00+00
completed_at | 2026-03-07 12:10:05+00
error_message| npm ERR! 404 '@openclaw/nonexistent-skill' is not in the npm registry.
```

---

## Example 2: Execute a Skill

### Basic Execution

Execute `himalaya` to list emails:

```bash
curl -X POST http://localhost:18789/workflows/skill-execution \
  -H "Content-Type: application/json" \
  -d '{
    "skillName": "himalaya",
    "agentId": "550e8400-e29b-41d4-a716-446655440000",
    "parameters": {
      "command": "list",
      "folder": "inbox"
    },
    "timeoutSeconds": 30
  }'
```

**Response (Success)**:
```json
{
  "success": true,
  "skillName": "himalaya",
  "executionId": "880fb733-g41d-63f6-c938-668877662222",
  "output": "Inbox (3 messages)\n\n1. john@example.com    Welcome to Himalaya     2026-03-07 10:00\n2. jane@example.com    Meeting tomorrow        2026-03-07 11:30\n3. bot@example.com     Daily digest            2026-03-07 12:00",
  "executionTimeMs": 1234
}
```

**What Happens**:

1. **Validate Installation** (Step 1):
   - Query DB: `SELECT * FROM skill_installation_history WHERE skill_name = 'himalaya' AND status = 'COMPLETED'`
   - If not found: return `{"success": false, "error": "Skill not installed: himalaya"}`

2. **Check Permissions** (Step 2):
   - Verify agent `550e8400...` has permission to execute `himalaya`
   - (Currently: always allows; future: RBAC check)

3. **Record Execution Start** (Step 3):
   - Insert DB record:
     ```sql
     INSERT INTO skill_execution_history
       (execution_id, skill_name, agent_id, status, parameters, started_at)
     VALUES
       ('880fb733...', 'himalaya', '550e8400...', 'RUNNING',
        '{"command": "list", "folder": "inbox"}', NOW())
     ```

4. **Execute Skill** (Step 4):
   - Call Backend: `POST http://localhost:8000/api/v1/skills/himalaya/execute`
   - Backend runs: `himalaya list --folder inbox`
   - Backend captures stdout: `"Inbox (3 messages)..."`
   - Backend returns: `{"success": true, "output": "...", "executionTimeMs": 1234}`

5. **Record Success** (Step 5):
   - Update DB:
     ```sql
     UPDATE skill_execution_history
     SET status = 'COMPLETED',
         output = 'Inbox (3 messages)...',
         execution_time_ms = 1234,
         completed_at = NOW()
     WHERE execution_id = '880fb733...'
     ```

**Timeline**: ~1-2 seconds

---

### Execution with Complex Parameters

Execute `bear-notes` to create a new note:

```bash
curl -X POST http://localhost:18789/workflows/skill-execution \
  -H "Content-Type: application/json" \
  -d '{
    "skillName": "bear-notes",
    "agentId": "550e8400-e29b-41d4-a716-446655440000",
    "parameters": {
      "action": "create",
      "title": "Meeting Notes",
      "body": "Discussed Phase 4 implementation\n- Skill workflows complete\n- Documentation in progress",
      "tags": ["work", "meetings", "phase4"]
    },
    "timeoutSeconds": 10
  }'
```

**Response (Success)**:
```json
{
  "success": true,
  "skillName": "bear-notes",
  "executionId": "990gc844-h52e-74g7-d049-779988773333",
  "output": "Note created successfully\nNote ID: ABC123DEF456\nURL: bear://x-callback-url/open-note?id=ABC123DEF456",
  "executionTimeMs": 567
}
```

**Backend Command**:
```bash
grizzly create \
  --title "Meeting Notes" \
  --body "Discussed Phase 4..." \
  --tags "work,meetings,phase4"
```

---

### Execution Timeout Example

Execute a long-running skill that exceeds timeout:

```bash
curl -X POST http://localhost:18789/workflows/skill-execution \
  -H "Content-Type: application/json" \
  -d '{
    "skillName": "long-running-skill",
    "agentId": "550e8400-e29b-41d4-a716-446655440000",
    "parameters": {
      "duration": 120
    },
    "timeoutSeconds": 5
  }'
```

**Response (Timeout)**:
```json
{
  "success": false,
  "skillName": "long-running-skill",
  "executionId": "aa0hd955-i63f-85h8-e150-880099884444",
  "error": "Skill execution timed out after 5 seconds",
  "executionTimeMs": 5000
}
```

**Database Record**:
```sql
SELECT * FROM skill_execution_history
WHERE execution_id = 'aa0hd955-i63f-85h8-e150-880099884444';

-- Result:
status          | TIMEOUT
output          | (partial output captured before timeout)
error_message   | Skill execution timed out after 5 seconds
execution_time_ms | 5000
```

---

### Execution Failure Example

Execute a skill with invalid parameters:

```bash
curl -X POST http://localhost:18789/workflows/skill-execution \
  -H "Content-Type: application/json" \
  -d '{
    "skillName": "himalaya",
    "agentId": "550e8400-e29b-41d4-a716-446655440000",
    "parameters": {
      "command": "invalid-command"
    }
  }'
```

**Response (Failure)**:
```json
{
  "success": false,
  "skillName": "himalaya",
  "executionId": "bb0ie066-j74g-96i9-f261-991100995555",
  "error": "Skill execution failed: error: Found argument 'invalid-command' which wasn't expected",
  "executionTimeMs": 123
}
```

**Database Record**:
```sql
status        | FAILED
error_message | error: Found argument 'invalid-command' which wasn't expected
output        | (stderr from skill)
```

---

## Example 3: Query Installation History

### Get All Installations for an Agent

```sql
SELECT
  skill_name,
  status,
  method,
  binary_path,
  started_at,
  completed_at,
  EXTRACT(EPOCH FROM (completed_at - started_at)) as duration_seconds,
  error_message
FROM skill_installation_history
WHERE agent_id = '550e8400-e29b-41d4-a716-446655440000'
ORDER BY started_at DESC;
```

**Sample Output**:
```
skill_name   | status    | method | binary_path              | started_at          | completed_at        | duration_seconds | error_message
-------------|-----------|--------|--------------------------|---------------------|---------------------|------------------|---------------
himalaya     | COMPLETED | brew   | /usr/local/bin/himalaya  | 2026-03-07 12:05:30 | 2026-03-07 12:06:15 | 45.2             | NULL
bear-notes   | COMPLETED | npm    | /usr/local/bin/grizzly   | 2026-03-07 12:00:00 | 2026-03-07 12:00:15 | 15.3             | NULL
```

---

### Get Failed Installations

```sql
SELECT
  skill_name,
  method,
  started_at,
  error_message,
  status
FROM skill_installation_history
WHERE status IN ('FAILED', 'ROLLED_BACK')
ORDER BY started_at DESC
LIMIT 10;
```

**Sample Output**:
```
skill_name         | method | started_at          | error_message                                | status
-------------------|--------|---------------------|----------------------------------------------|-------------
nonexistent-skill  | npm    | 2026-03-07 12:10:00 | npm ERR! 404 not in the npm registry.       | ROLLED_BACK
broken-skill       | brew   | 2026-03-07 11:30:00 | Error: Download failed: 404 Not Found       | FAILED
```

---

### Get Installation Success Rate

```sql
SELECT
  skill_name,
  COUNT(*) as total_attempts,
  COUNT(*) FILTER (WHERE status = 'COMPLETED') as successful,
  COUNT(*) FILTER (WHERE status IN ('FAILED', 'ROLLED_BACK')) as failed,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status = 'COMPLETED') / COUNT(*),
    2
  ) as success_rate_percent
FROM skill_installation_history
WHERE started_at > NOW() - INTERVAL '7 days'
GROUP BY skill_name
ORDER BY total_attempts DESC;
```

**Sample Output**:
```
skill_name   | total_attempts | successful | failed | success_rate_percent
-------------|----------------|------------|--------|---------------------
himalaya     | 15             | 15         | 0      | 100.00
bear-notes   | 12             | 11         | 1      | 91.67
custom-skill | 5              | 3          | 2      | 60.00
```

---

### Check if Skill is Installed

```sql
-- Simple check: any successful installation?
SELECT EXISTS (
  SELECT 1
  FROM skill_installation_history
  WHERE skill_name = 'himalaya'
    AND status = 'COMPLETED'
) as is_installed;

-- More robust: get latest installation status
SELECT
  skill_name,
  status,
  binary_path,
  completed_at
FROM skill_installation_history
WHERE skill_name = 'himalaya'
ORDER BY started_at DESC
LIMIT 1;
```

---

## Example 4: Query Execution History

### Get All Executions for a Skill

```sql
SELECT
  execution_id,
  agent_id,
  status,
  parameters,
  execution_time_ms,
  started_at,
  SUBSTRING(output, 1, 100) as output_preview
FROM skill_execution_history
WHERE skill_name = 'himalaya'
ORDER BY started_at DESC
LIMIT 10;
```

**Sample Output**:
```
execution_id  | agent_id     | status    | parameters                      | execution_time_ms | started_at          | output_preview
--------------|--------------|-----------|----------------------------------|-------------------|---------------------|------------------
880fb733...   | 550e8400...  | COMPLETED | {"command":"list","folder":"i... | 1234              | 2026-03-07 12:15:00 | Inbox (3 messages)...
770ea622...   | 550e8400...  | COMPLETED | {"command":"read","id":"1"}      | 890               | 2026-03-07 12:10:00 | From: john@exam...
660d9511...   | 660e9511...  | FAILED    | {"command":"invalid"}            | 123               | 2026-03-07 12:05:00 | error: Found arg...
```

---

### Get Slow Executions (>5 seconds)

```sql
SELECT
  skill_name,
  agent_id,
  execution_id,
  execution_time_ms,
  ROUND(execution_time_ms / 1000.0, 2) as execution_time_seconds,
  started_at,
  status
FROM skill_execution_history
WHERE execution_time_ms > 5000
ORDER BY execution_time_ms DESC
LIMIT 20;
```

**Sample Output**:
```
skill_name     | agent_id    | execution_id | execution_time_ms | execution_time_seconds | started_at          | status
---------------|-------------|--------------|-------------------|------------------------|---------------------|--------
data-processor | 550e8400... | cc0jf177...  | 45678             | 45.68                  | 2026-03-07 10:00:00 | COMPLETED
file-converter | 660e9511... | dd0kg288...  | 23456             | 23.46                  | 2026-03-07 11:30:00 | COMPLETED
image-resizer  | 550e8400... | ee0lh399...  | 12345             | 12.35                  | 2026-03-07 12:00:00 | COMPLETED
```

---

### Get Execution Statistics per Agent

```sql
SELECT
  agent_id,
  COUNT(*) as total_executions,
  COUNT(*) FILTER (WHERE status = 'COMPLETED') as successful,
  COUNT(*) FILTER (WHERE status = 'FAILED') as failed,
  COUNT(*) FILTER (WHERE status = 'TIMEOUT') as timeouts,
  ROUND(AVG(execution_time_ms), 2) as avg_execution_time_ms,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status = 'COMPLETED') / COUNT(*),
    2
  ) as success_rate_percent
FROM skill_execution_history
WHERE started_at > NOW() - INTERVAL '24 hours'
GROUP BY agent_id
ORDER BY total_executions DESC;
```

**Sample Output**:
```
agent_id         | total_executions | successful | failed | timeouts | avg_execution_time_ms | success_rate_percent
-----------------|------------------|------------|--------|----------|----------------------|---------------------
550e8400-...     | 150              | 145        | 3      | 2        | 2345.67              | 96.67
660e9511-...     | 89               | 85         | 4      | 0        | 1890.23              | 95.51
770fa622-...     | 45               | 40         | 3      | 2        | 3456.78              | 88.89
```

---

### Get Most Used Skills

```sql
SELECT
  skill_name,
  COUNT(*) as execution_count,
  COUNT(DISTINCT agent_id) as unique_agents,
  ROUND(AVG(execution_time_ms), 2) as avg_execution_time_ms,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status = 'COMPLETED') / COUNT(*),
    2
  ) as success_rate_percent
FROM skill_execution_history
WHERE started_at > NOW() - INTERVAL '7 days'
GROUP BY skill_name
ORDER BY execution_count DESC
LIMIT 10;
```

**Sample Output**:
```
skill_name     | execution_count | unique_agents | avg_execution_time_ms | success_rate_percent
---------------|-----------------|---------------|-----------------------|---------------------
himalaya       | 450             | 12            | 1234.56               | 98.44
bear-notes     | 320             | 8             | 890.23                | 99.06
file-converter | 215             | 15            | 5678.90               | 95.35
data-processor | 189             | 6             | 12345.67              | 92.06
```

---

### Find Executions by Parameters

```sql
-- Find all himalaya executions that listed inbox
SELECT
  execution_id,
  agent_id,
  status,
  output,
  started_at
FROM skill_execution_history
WHERE skill_name = 'himalaya'
  AND parameters @> '{"command": "list", "folder": "inbox"}'::jsonb
ORDER BY started_at DESC
LIMIT 10;

-- Find all bear-notes executions with specific tag
SELECT
  execution_id,
  agent_id,
  parameters->>'title' as note_title,
  started_at
FROM skill_execution_history
WHERE skill_name = 'bear-notes'
  AND parameters @> '{"action": "create"}'::jsonb
  AND parameters->'tags' @> '["work"]'::jsonb
ORDER BY started_at DESC;
```

---

## Example 5: Monitoring Dashboard Queries

### Real-Time Activity Dashboard

```sql
-- Last 10 installations
SELECT
  skill_name,
  status,
  started_at,
  completed_at,
  EXTRACT(EPOCH FROM (COALESCE(completed_at, NOW()) - started_at)) as duration_seconds
FROM skill_installation_history
ORDER BY started_at DESC
LIMIT 10;

-- Last 20 executions
SELECT
  skill_name,
  agent_id,
  status,
  execution_time_ms,
  started_at
FROM skill_execution_history
ORDER BY started_at DESC
LIMIT 20;

-- Currently running executions
SELECT
  skill_name,
  agent_id,
  execution_id,
  started_at,
  EXTRACT(EPOCH FROM (NOW() - started_at)) as running_for_seconds
FROM skill_execution_history
WHERE status = 'RUNNING'
ORDER BY started_at ASC;
```

---

### Health Check Dashboard

```sql
-- Installation health (last hour)
SELECT
  COUNT(*) as total_installations,
  COUNT(*) FILTER (WHERE status = 'COMPLETED') as successful,
  COUNT(*) FILTER (WHERE status IN ('FAILED', 'ROLLED_BACK')) as failed,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status = 'COMPLETED') / COUNT(*),
    2
  ) as success_rate_percent
FROM skill_installation_history
WHERE started_at > NOW() - INTERVAL '1 hour';

-- Execution health (last hour)
SELECT
  COUNT(*) as total_executions,
  COUNT(*) FILTER (WHERE status = 'COMPLETED') as successful,
  COUNT(*) FILTER (WHERE status = 'FAILED') as failed,
  COUNT(*) FILTER (WHERE status = 'TIMEOUT') as timeouts,
  ROUND(AVG(execution_time_ms), 2) as avg_execution_time_ms,
  ROUND(
    100.0 * COUNT(*) FILTER (WHERE status = 'COMPLETED') / COUNT(*),
    2
  ) as success_rate_percent
FROM skill_execution_history
WHERE started_at > NOW() - INTERVAL '1 hour';
```

---

### Alert Queries

```sql
-- Alert: Stuck installations (>10 minutes in STARTED)
SELECT
  id,
  skill_name,
  agent_id,
  started_at,
  EXTRACT(EPOCH FROM (NOW() - started_at)) / 60 as minutes_stuck
FROM skill_installation_history
WHERE status = 'STARTED'
  AND started_at < NOW() - INTERVAL '10 minutes'
ORDER BY started_at ASC;

-- Alert: High failure rate (>20% in last hour)
WITH failure_stats AS (
  SELECT
    skill_name,
    COUNT(*) as total,
    COUNT(*) FILTER (WHERE status IN ('FAILED', 'ROLLED_BACK')) as failed
  FROM skill_installation_history
  WHERE started_at > NOW() - INTERVAL '1 hour'
  GROUP BY skill_name
)
SELECT
  skill_name,
  total,
  failed,
  ROUND(100.0 * failed / total, 2) as failure_rate_percent
FROM failure_stats
WHERE (100.0 * failed / total) > 20
ORDER BY failure_rate_percent DESC;

-- Alert: Execution timeouts (any in last 15 minutes)
SELECT
  skill_name,
  agent_id,
  execution_id,
  started_at,
  parameters
FROM skill_execution_history
WHERE status = 'TIMEOUT'
  AND started_at > NOW() - INTERVAL '15 minutes'
ORDER BY started_at DESC;
```

---

## Example 6: Python Client Usage

### Install a Skill via Python

```python
import requests
import json
from datetime import datetime

GATEWAY_URL = "http://localhost:18789"

def install_skill(skill_name: str, method: str, agent_id: str = None):
    """Install a skill via Gateway API"""
    url = f"{GATEWAY_URL}/workflows/skill-installation"
    payload = {
        "skillName": skill_name,
        "method": method
    }
    if agent_id:
        payload["agentId"] = agent_id

    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()

# Example usage
result = install_skill("bear-notes", "npm", "550e8400-e29b-41d4-a716-446655440000")
print(f"Installation {'succeeded' if result['success'] else 'failed'}")
if result['success']:
    print(f"Binary installed at: {result['binaryPath']}")
    print(f"Installed at: {result['installedAt']}")
else:
    print(f"Error: {result['error']}")
```

---

### Execute a Skill via Python

```python
def execute_skill(skill_name: str, agent_id: str, parameters: dict, timeout_seconds: int = 30):
    """Execute a skill via Gateway API"""
    url = f"{GATEWAY_URL}/workflows/skill-execution"
    payload = {
        "skillName": skill_name,
        "agentId": agent_id,
        "parameters": parameters,
        "timeoutSeconds": timeout_seconds
    }

    response = requests.post(url, json=payload)
    response.raise_for_status()
    return response.json()

# Example: List emails
result = execute_skill(
    skill_name="himalaya",
    agent_id="550e8400-e29b-41d4-a716-446655440000",
    parameters={"command": "list", "folder": "inbox"},
    timeout_seconds=30
)

if result['success']:
    print(f"Execution completed in {result['executionTimeMs']}ms")
    print(f"Output:\n{result['output']}")
else:
    print(f"Execution failed: {result['error']}")

# Example: Create note
result = execute_skill(
    skill_name="bear-notes",
    agent_id="550e8400-e29b-41d4-a716-446655440000",
    parameters={
        "action": "create",
        "title": "Python Test Note",
        "body": "Created via Python API client",
        "tags": ["test", "api"]
    },
    timeout_seconds=10
)
```

---

### Check Installation Status via Python

```python
import psycopg2
from psycopg2.extras import RealDictCursor

def is_skill_installed(skill_name: str, db_url: str) -> bool:
    """Check if skill is installed by querying database"""
    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT EXISTS (
                    SELECT 1
                    FROM skill_installation_history
                    WHERE skill_name = %s
                      AND status = 'COMPLETED'
                ) as is_installed
            """, (skill_name,))
            result = cur.fetchone()
            return result['is_installed']
    finally:
        conn.close()

# Example usage
DB_URL = "postgresql://user:pass@host:port/database"
if is_skill_installed("himalaya", DB_URL):
    print("Himalaya is installed")
else:
    print("Himalaya is NOT installed")
```

---

## Example 7: Troubleshooting Common Issues

### Issue: Installation Fails with "Binary Not Found"

**Symptom**:
```json
{
  "success": false,
  "error": "Binary verification failed: /usr/local/bin/grizzly does not exist"
}
```

**Diagnosis**:
```bash
# Check if npm install actually succeeded
npm list -g @openclaw/bear-notes

# Check if binary exists but at different path
which grizzly

# Check npm global bin directory
npm config get prefix
```

**Solution**:
Update Backend's binary path configuration to match actual install location.

---

### Issue: Execution Timeout on Simple Commands

**Symptom**:
```json
{
  "success": false,
  "error": "Skill execution timed out after 30 seconds"
}
```

**Diagnosis**:
```sql
-- Check if other executions also timeout
SELECT skill_name, COUNT(*) as timeout_count
FROM skill_execution_history
WHERE status = 'TIMEOUT'
  AND started_at > NOW() - INTERVAL '1 hour'
GROUP BY skill_name;

-- Check execution times for this skill
SELECT execution_time_ms, started_at
FROM skill_execution_history
WHERE skill_name = 'himalaya'
  AND status = 'COMPLETED'
ORDER BY started_at DESC
LIMIT 10;
```

**Solutions**:
1. Increase timeout: `"timeoutSeconds": 60`
2. Check Backend server load (CPU/memory)
3. Check skill configuration (network timeouts, etc.)

---

### Issue: Duplicate Executions After Gateway Crash

**Symptom**: Same skill executed twice with same parameters

**Diagnosis**:
```sql
-- Find duplicate executions
SELECT
  skill_name,
  agent_id,
  parameters,
  COUNT(*) as execution_count,
  ARRAY_AGG(execution_id ORDER BY started_at) as execution_ids,
  ARRAY_AGG(started_at ORDER BY started_at) as timestamps
FROM skill_execution_history
WHERE started_at > NOW() - INTERVAL '1 hour'
GROUP BY skill_name, agent_id, parameters
HAVING COUNT(*) > 1;
```

**Explanation**: This is expected behavior when Gateway crashes during execution step. DBOS will retry the execution step, causing the skill to run again.

**Mitigation**:
1. Make skills idempotent when possible
2. Use `execution_id` to detect duplicates on client side
3. For non-idempotent skills, implement execution deduplication in Backend

---

## Example 8: Performance Testing

### Load Test Installation Endpoint

```bash
#!/bin/bash
# install_load_test.sh - Install 10 skills concurrently

GATEWAY_URL="http://localhost:18789"
SKILLS=("skill-1" "skill-2" "skill-3" "skill-4" "skill-5" \
        "skill-6" "skill-7" "skill-8" "skill-9" "skill-10")

for skill in "${SKILLS[@]}"; do
  curl -X POST "${GATEWAY_URL}/workflows/skill-installation" \
    -H "Content-Type: application/json" \
    -d "{\"skillName\":\"${skill}\",\"method\":\"npm\"}" \
    > "/tmp/install_${skill}.log" 2>&1 &
done

wait
echo "All installations complete"
```

---

### Load Test Execution Endpoint

```python
import asyncio
import aiohttp
import time

async def execute_skill(session, skill_name, agent_id, params):
    url = "http://localhost:18789/workflows/skill-execution"
    payload = {
        "skillName": skill_name,
        "agentId": agent_id,
        "parameters": params
    }
    start = time.time()
    async with session.post(url, json=payload) as resp:
        result = await resp.json()
        duration = time.time() - start
        return {
            "success": result.get("success"),
            "duration": duration,
            "executionTimeMs": result.get("executionTimeMs")
        }

async def load_test(num_concurrent=50):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for i in range(num_concurrent):
            task = execute_skill(
                session,
                "himalaya",
                "550e8400-e29b-41d4-a716-446655440000",
                {"command": "list"}
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)

        successful = sum(1 for r in results if r["success"])
        avg_duration = sum(r["duration"] for r in results) / len(results)

        print(f"Completed {len(results)} executions")
        print(f"Successful: {successful} ({100*successful/len(results):.2f}%)")
        print(f"Average total duration: {avg_duration:.2f}s")

# Run load test
asyncio.run(load_test(num_concurrent=50))
```

---

## Example 9: Cleanup and Maintenance

### Archive Old Execution Records

```sql
-- Create archive table (one-time)
CREATE TABLE skill_execution_history_archive (LIKE skill_execution_history INCLUDING ALL);

-- Archive records older than 90 days
WITH archived AS (
  DELETE FROM skill_execution_history
  WHERE completed_at < NOW() - INTERVAL '90 days'
  RETURNING *
)
INSERT INTO skill_execution_history_archive
SELECT * FROM archived;

-- Verify archive
SELECT
  COUNT(*) as archived_count,
  MIN(started_at) as oldest,
  MAX(started_at) as newest
FROM skill_execution_history_archive;
```

---

### Cleanup Failed Installations

```sql
-- Delete failed installations older than 30 days
DELETE FROM skill_installation_history
WHERE status IN ('FAILED', 'ROLLED_BACK')
  AND completed_at < NOW() - INTERVAL '30 days';

-- Vacuum to reclaim space
VACUUM ANALYZE skill_installation_history;
```

---

## Conclusion

These examples cover the most common use cases for Phase 4 skill workflows. For more details:

- **API Specification**: See `PHASE_4_API.md`
- **Architecture**: See `PHASE_4_ARCHITECTURE.md`
- **Backend Source**: `/Users/aideveloper/openclaw-backend/backend/api/v1/endpoints/openclaw_skills.py`
- **Gateway Source**: `/Users/aideveloper/openclaw-backend/openclaw-gateway/src/workflows/`
