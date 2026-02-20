# Claude Orchestration Layer for NousCoder Agents

**Issue:** #1076
**Status:** Implemented
**Coverage:** 89% (43 tests passing)

## Overview

The Claude Orchestration Layer is the autonomous development system that ties together OpenClaw WhatsApp integration, NousCoder agent spawning, and GitHub workflow automation into a complete 24/7 development pipeline.

## Architecture

```
WhatsApp Message (@mention OpenClaw)
          ↓
OpenClaw Gateway (routing configured ✓)
          ↓
Claude Orchestration Layer ← YOU ARE HERE
          ↓
NousCoder Agent Spawner (already built ✓)
          ↓
GitHub Issue Work + PR Creation
          ↓
Status Updates → WhatsApp
```

## Components

### 1. Command Parser (`command_parser.py`)

**Purpose:** Parses WhatsApp commands into structured commands

**Coverage:** 98% (21 tests)

**Supported Commands:**
- `work on issue #1234` - Spawn agent to work on GitHub issue
- `status of issue #1234` - Check status of work on issue
- `stop work on issue #1234` - Stop agent and cleanup resources
- `list active agents` - List all currently active agents

**Example:**
```python
from app.agents.orchestration import CommandParser

parser = CommandParser()
command = parser.parse("work on issue #1234")

print(command.command_type)  # CommandType.WORK_ON_ISSUE
print(command.issue_number)  # 1234
```

**Features:**
- Case-insensitive parsing
- Flexible syntax (with/without # symbol)
- Comprehensive error handling
- Clear error messages for invalid commands

### 2. Notification Service (`notification_service.py`)

**Purpose:** Sends WhatsApp status updates via OpenClaw bridge

**Coverage:** 100% (13 tests)

**Notification Types:**
- Agent spawned
- Work started
- PR created
- Tests passing/failing
- Work completed
- Errors

**Example:**
```python
from app.agents.orchestration import NotificationService

service = NotificationService(openclaw_bridge=bridge)

await service.notify_agent_spawned(
    issue_number=1234,
    agent_id="nouscoder_abc123"
)
# Sends: "✓ Agent spawned for issue #1234\n\nAgent ID: nouscoder_abc123"
```

**Features:**
- Automatic retry with exponential backoff (3 retries)
- Connection validation
- Rich emoji-enhanced messages
- Error handling and logging

### 3. Claude Orchestrator (`claude_orchestrator.py`)

**Purpose:** Main orchestration controller that coordinates all components

**Coverage:** 81% (9 tests)

**Workflow States:**
- PARSING_COMMAND
- SPAWNING_AGENT
- AGENT_READY
- WORK_IN_PROGRESS
- PR_CREATED
- TESTS_RUNNING
- COMPLETED
- FAILED
- STOPPED

**Example:**
```python
from app.agents.orchestration import ClaudeOrchestrator
from app.agents.swarm import get_nouscoder_spawner
from integrations.openclaw_bridge import OpenClawBridge

# Setup
bridge = OpenClawBridge()
await bridge.connect()

spawner = get_nouscoder_spawner()
notification_service = NotificationService(openclaw_bridge=bridge)

orchestrator = ClaudeOrchestrator(
    spawner=spawner,
    notification_service=notification_service
)

# Handle WhatsApp command
result = await orchestrator.handle_whatsapp_command("work on issue #1234")
```

**Features:**
- Tracks active workflows by issue number
- Automatic agent spawning with retry
- Status monitoring and reporting
- Error handling with user notifications
- Agent cleanup on stop/completion

## Complete Workflow Example

### User Journey

**Step 1: User sends WhatsApp message**
```
@OpenClaw work on issue #1234
```

**Step 2: OpenClaw routes to orchestrator**
```python
# OpenClaw internal routing (already configured)
await orchestrator.handle_whatsapp_command("work on issue #1234")
```

**Step 3: Orchestrator spawns agent**
```python
# Parsed command
command = ParsedCommand(
    command_type=CommandType.WORK_ON_ISSUE,
    raw_command="work on issue #1234",
    issue_number=1234
)

# Spawn agent with retry
agent = await spawner.spawn_agent_with_retry(
    issue_number=1234,
    task_description=None,
    max_retries=3
)
```

**Step 4: Send spawned notification**
```
✓ Agent spawned for issue #1234

Agent ID: nouscoder_abc123
```

**Step 5: Agent works on issue**
```python
# Agent performs work (GitHub checkout, code changes, tests, etc.)
result = await spawner.complete_task(agent.agent_id)
```

**Step 6: Send PR created notification**
```
✓ PR #5678 created for issue #1234

URL: https://github.com/org/repo/pull/5678
```

**Step 7: Send tests status notification**
```
✓ All tests passing for issue #1234

Coverage: 92%
```

**Step 8: Send completion notification**
```
✅ Issue #1234 completed

PR #5678 ready for review
URL: https://github.com/org/repo/pull/5678
```

## Testing

### Test Coverage Summary

**Overall:** 89% coverage (43 tests passing)

| Component | Coverage | Tests | Status |
|-----------|----------|-------|--------|
| Command Parser | 98% | 21 | ✓ All passing |
| Notification Service | 100% | 13 | ✓ All passing |
| Claude Orchestrator | 81% | 9 | ✓ All passing |

### Running Tests

```bash
cd /Users/aideveloper/core/src/backend

# Run all orchestration tests
python3 -m pytest tests/agents/orchestration/ -v --cov=app.agents.orchestration --cov-report=term-missing

# Run specific component
python3 -m pytest tests/agents/orchestration/test_command_parser.py -v
python3 -m pytest tests/agents/orchestration/test_notification_service.py -v
python3 -m pytest tests/agents/orchestration/test_claude_orchestrator.py -v
```

### Test Results

```
================================ tests coverage ================================
Name                                               Stmts   Miss  Cover   Missing
--------------------------------------------------------------------------------
app/agents/orchestration/__init__.py                   2      0   100%
app/agents/orchestration/claude_orchestrator.py      113     21    81%
app/agents/orchestration/command_parser.py            40      1    98%
app/agents/orchestration/notification_service.py      52      0   100%
--------------------------------------------------------------------------------
TOTAL                                                207     22    89%
======================= 43 passed, 593 warnings in 5.08s =======================
```

## Error Handling

### Spawn Failures

**Scenario:** Agent spawn fails due to resource allocation error

```python
# Orchestrator automatically:
# 1. Retries up to 3 times with exponential backoff
# 2. Sends error notification to user
# 3. Marks workflow as FAILED
# 4. Returns detailed error response

{
    "success": False,
    "issue_number": 1234,
    "error": "Resource allocation error: Max concurrent agents (5) reached",
    "state": "failed"
}
```

**WhatsApp Notification:**
```
❌ Error on issue #1234

Error: Resource allocation error: Max concurrent agents (5) reached
```

### Notification Failures

**Scenario:** WhatsApp notification fails to send

```python
# Notification service automatically:
# 1. Retries up to 3 times with exponential backoff
# 2. Logs detailed error
# 3. Raises NotificationError if all retries fail

# Retry delays: 1s, 2s, 4s (exponential backoff)
```

### Connection Failures

**Scenario:** OpenClaw bridge disconnected

```python
# Raises NotificationError immediately
raise NotificationError("OpenClaw bridge is not connected")
```

## Integration Points

### Required Dependencies

1. **OpenClaw Bridge** (`integrations/openclaw_bridge.py`)
   - WebSocket connection to OpenClaw Gateway
   - Authentication token required
   - Status: ✓ Already implemented

2. **NousCoder Agent Spawner** (`app/agents/swarm/nouscoder_agent_spawner.py`)
   - Spawns and manages NousCoder-14B agents
   - Modal serverless platform integration
   - Status: ✓ Already implemented

3. **OpenClaw Gateway**
   - WhatsApp routing configuration
   - Session key: `agent:whatsapp:main`
   - Status: ✓ Already configured

### Environment Variables

```bash
# OpenClaw configuration
OPENCLAW_TOKEN=your_token_here  # OpenClaw authentication token
```

## Deployment

### Local Development

```bash
# 1. Start OpenClaw Gateway (separate process)
# See OpenClaw documentation

# 2. Set environment variables
export OPENCLAW_TOKEN=your_token_here

# 3. Run tests
cd /Users/aideveloper/core/src/backend
python3 -m pytest tests/agents/orchestration/ -v

# 4. Start orchestrator (integrated with main FastAPI app)
cd /Users/aideveloper/core/src/backend
python3 -m uvicorn app.main:app --reload
```

### Production Deployment

The orchestrator is integrated into the main FastAPI application and deploys automatically with the backend.

**Railway Configuration:**
- Service: AINative- Core -Production
- URL: `https://ainative-browser-builder.up.railway.app`
- Environment: Set `OPENCLAW_TOKEN` in Railway dashboard

## API Integration

### Creating Orchestrator Endpoint

```python
# In app/api/v1/endpoints/orchestration.py
from fastapi import APIRouter, Depends
from app.agents.orchestration import ClaudeOrchestrator

router = APIRouter()

@router.post("/whatsapp/command")
async def handle_whatsapp_command(
    command: str,
    orchestrator: ClaudeOrchestrator = Depends(get_orchestrator)
):
    """Handle WhatsApp command from OpenClaw"""
    result = await orchestrator.handle_whatsapp_command(command)
    return result

@router.get("/workflows")
async def list_workflows(
    orchestrator: ClaudeOrchestrator = Depends(get_orchestrator)
):
    """List all active workflows"""
    return orchestrator.get_active_workflows()

@router.get("/workflows/{issue_number}")
async def get_workflow(
    issue_number: int,
    orchestrator: ClaudeOrchestrator = Depends(get_orchestrator)
):
    """Get workflow for specific issue"""
    workflow = orchestrator.get_workflow(issue_number)
    if not workflow:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflow
```

## Monitoring and Observability

### Logging

All components include structured logging:

```python
logger.info(f"Spawning agent for issue #{issue_number}")
logger.error(f"Failed to spawn agent: {error}", exc_info=True)
```

### Workflow Tracking

```python
# Get all active workflows
workflows = orchestrator.get_active_workflows()

# Get specific workflow
workflow = orchestrator.get_workflow(issue_number=1234)

# Example workflow object
{
    "issue_number": 1234,
    "agent_id": "nouscoder_abc123",
    "state": "work_in_progress",
    "started_at": "2026-02-05T23:00:00",
    "pr_url": None,
    "error": None
}
```

## Future Enhancements

1. **Database Persistence**
   - Store workflow state in PostgreSQL
   - Enable workflow recovery after restart
   - Historical workflow analytics

2. **Advanced Monitoring**
   - Prometheus metrics
   - Grafana dashboards
   - Alert on workflow failures

3. **Multi-Agent Coordination**
   - Parallel agent execution
   - Agent collaboration on complex issues
   - Load balancing across agents

4. **Enhanced Notifications**
   - Customizable notification templates
   - Multiple notification channels (Slack, Discord)
   - Rich media attachments (code diffs, screenshots)

## Troubleshooting

### Common Issues

**Problem:** Tests failing with "OpenClaw bridge is not connected"

**Solution:** Ensure mock bridge in tests has `is_connected = True`

```python
mock_bridge = AsyncMock()
mock_bridge.is_connected = True
```

**Problem:** Agent spawn fails with "Max concurrent agents reached"

**Solution:** Cleanup unused agents or increase limit

```python
# Cleanup all agents
await spawner.cleanup_all_agents()

# Or increase limit in config
config = NousCoderConfig(max_concurrent_agents=10)
spawner = NousCoderAgentSpawner(config)
```

**Problem:** Notifications not sent

**Solution:** Check OpenClaw bridge connection and token

```python
# Verify connection
print(bridge.is_connected)  # Should be True

# Re-authenticate
await bridge.connect()
```

## References

- Issue #1076: Claude Orchestration Layer for NousCoder Agents
- Issue #1075: NousCoder Agent Spawner
- `integrations/openclaw_bridge.py` - OpenClaw integration
- `app/agents/swarm/nouscoder_agent_spawner.py` - Agent spawner
- `.ainative/RULES.MD` - TDD/BDD testing standards

## Built By

Built by AINative Dev Team

Refs #1076
