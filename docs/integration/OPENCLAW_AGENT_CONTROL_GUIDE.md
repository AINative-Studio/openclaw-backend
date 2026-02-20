# OpenClaw Agent Control via WhatsApp

## Overview
This guide shows you how to control your AINative agent swarms through WhatsApp commands using OpenClaw Gateway.

## Architecture

```
WhatsApp Message → OpenClaw Gateway → Python Backend → Agent Swarm
                                    ↓
                            Notification ← Status Updates
```

## Part 1: Control Agents via WhatsApp Commands

### Step 1: Create Agent Controller

**File**: `/Users/aideveloper/core/integrations/openclaw_agent_controller.py`

This service listens for WhatsApp messages starting with `/` and executes commands.

**Key Features**:
- Listen for WhatsApp commands
- Parse and execute commands
- Send responses back to WhatsApp
- Control agent swarm lifecycle

**Available Commands**:
- `/help` - Show available commands
- `/status` - Show agent swarm status
- `/start <repo>` - Start agent swarm for repository
- `/stop` - Stop all running agents
- `/list [repo]` - List open issues
- `/assign <issue#> <count>` - Assign N agents to issue
- `/deploy <env>` - Deploy to environment

### Step 2: Implement the Controller

Create the controller file (I'll provide the code below).

### Step 3: Run the Controller

```bash
cd /Users/aideveloper/core
python3 integrations/openclaw_agent_controller.py
```

Output:
```
✓ Connected to OpenClaw Gateway
✓ Listening for WhatsApp commands...
```

### Step 4: Test Commands via WhatsApp

Send these commands to your WhatsApp:

1. **Get Help**:
   ```
   /help
   ```
   Response: Lists all available commands

2. **Check Status**:
   ```
   /status
   ```
   Response: Shows active agents, queued tasks, system load

3. **Start Agent Swarm**:
   ```
   /start core
   ```
   Response: Initializes agents for the core repository

4. **List Issues**:
   ```
   /list core
   ```
   Response: Shows open issues with priorities

5. **Assign Agents to Issue**:
   ```
   /assign 1234 5
   ```
   Response: Assigns 5 agents to work on issue #1234

6. **Deploy**:
   ```
   /deploy staging
   ```
   Response: Triggers deployment to staging environment

## Part 2: Integrate with Agent Swarm Workflows

### Integration Points

Add OpenClaw notifications to these key events:

1. **Swarm Lifecycle**:
   - Swarm started
   - Swarm completed
   - Summary statistics

2. **Agent Lifecycle**:
   - Agent started on issue
   - Agent progress updates
   - Agent completed successfully
   - Agent failed with error

3. **Deployment Events**:
   - Deployment started
   - Deployment completed
   - Health check results

4. **PR Events**:
   - PR created
   - PR merged
   - PR review requested

### Example Integration Pattern

```python
# In your existing agent orchestration code:

from integrations.agent_swarm_notifier import get_notifier

async def run_agent_swarm():
    notifier = await get_notifier()

    # 1. Notify swarm start
    await notifier.notify_swarm_started("core", 10, issues)

    # 2. Run agents with progress updates
    for i, issue in enumerate(issues):
        agent_id = f"agent-{i+1}"

        # Start notification
        await notifier.notify_agent_started(agent_id, issue.number, issue.title)

        # Your agent logic here
        result = await run_agent(issue)

        # Progress notifications during work
        await notifier.notify_agent_progress(
            agent_id, issue.number, "coding", "Implementing solution"
        )

        # Completion notification
        if result.success:
            await notifier.notify_agent_completed(
                agent_id, issue.number, result.branch,
                result.tests_passed, result.coverage
            )
        else:
            await notifier.notify_agent_failed(agent_id, issue.number, result.error)

    # 3. Notify swarm completion
    await notifier.notify_swarm_summary("core", completed, failed, total_time, merged)
```

### Quick Integration: Add to Existing Code

**Minimal changes to add notifications**:

```python
# At the top of your file
from integrations.agent_swarm_notifier import get_notifier

# In your main function
async def main():
    notifier = await get_notifier()

    # Before starting work
    await notifier.notify_swarm_started(repo, agent_count, issues)

    # Your existing code runs here...

    # After completion
    await notifier.notify_swarm_summary(repo, completed, failed, time, merged)
```

## Part 3: Complete Workflow Example

### Scenario: Process Open Issues with Agent Swarm

**Step 1: From WhatsApp, check status**
```
/status
```
Response:
```
🤖 Agent Swarm Status

Core Repo:
  Active agents: 0
  Queued tasks: 0
  Open issues: 15

Ready to start!
```

**Step 2: Start agent swarm**
```
/start core
```
Response:
```
🚀 Agent Swarm Started

Repository: core
Agents: 10
Issues: 15

Initializing...
```

**Step 3: Automatic notifications as agents work**

You'll receive messages like:
```
🤖 Agent 1 Started
Issue: #1234
Title: Add streaming endpoint

⌨️ Agent 1 - Coding
Issue: #1234
Writing code...

🧪 Agent 1 - Testing
Issue: #1234
Running tests (85% coverage)

✅ Agent 1 Complete
Issue: #1234
Branch: feature/1234-streaming
Tests: ✓ Passing
Coverage: 85.2%
```

**Step 4: Monitor progress**
```
/status
```
Response:
```
🤖 Agent Swarm Status

Core Repo:
  Active agents: 7
  Completed: 3
  Failed: 0
  Remaining: 12
```

**Step 5: Final summary when complete**
```
🎉 Agent Swarm Complete

Repository: core
Duration: 15m 32s

Results:
  ✅ Completed: 13
  ❌ Failed: 2
  🔀 Merged: 11

All agents have finished!
```

**Step 6: Deploy to staging**
```
/deploy staging
```
Response:
```
🚀 Deploying to staging...

Steps:
✓ Tests passed
✓ Docker build
✓ Push to Railway
✓ Health checks

✅ Deployment complete!
URL: https://ainative-staging.up.railway.app
```

## Part 4: Implementation Files

### File 1: Agent Controller (Command Listener)

Create this file to handle commands:

**Location**: `/Users/aideveloper/core/integrations/openclaw_agent_controller.py`

**Purpose**: Listens for WhatsApp commands and controls agent swarms

**Run**:
```bash
python3 integrations/openclaw_agent_controller.py
```

### File 2: Agent Swarm Notifier (Event Notifications)

Create this file for lifecycle notifications:

**Location**: `/Users/aideveloper/core/integrations/agent_swarm_notifier.py`

**Purpose**: Sends notifications during agent swarm execution

**Usage**: Import and call from your existing agent code

### File 3: Integration Helper

Add this to your existing orchestration:

**Location**: `/Users/aideveloper/core/integrations/openclaw_integration.py`

**Purpose**: Helper functions to simplify integration

## Part 5: Configuration

### Environment Variables

Already configured in `/Users/aideveloper/core/.env`:

```bash
OPENCLAW_GATEWAY_URL="ws://127.0.0.1:18789"
OPENCLAW_GATEWAY_TOKEN="7ae5aa8730848791e5a017fe95b80ad26f8c31d90e7b9ab60f5f8974d6519fc1"
```

### WhatsApp Group

Already configured in `~/.openclaw/openclaw.json`:
- Group ID: `120363401780756402@g.us`
- Allowed numbers: +18312950562, 18312951482

## Part 6: Testing

### Test 1: Basic Connection
```bash
# Send a test notification
python3 integrations/examples/openclaw_whatsapp_notifier.py "Test message"
```

### Test 2: Command Processing
```
# In WhatsApp, send:
/help
```
You should receive a list of available commands.

### Test 3: Integration Test
```bash
# Run a test agent swarm with notifications
python3 tests/integration/test_openclaw_integration.py
```

## Part 7: Production Deployment

### Option 1: Run as Background Service

```bash
# Start controller in background
nohup python3 integrations/openclaw_agent_controller.py > /tmp/openclaw_controller.log 2>&1 &
```

### Option 2: Run as systemd Service (Linux)

Create `/etc/systemd/system/openclaw-controller.service`:

```ini
[Unit]
Description=OpenClaw Agent Controller
After=network.target

[Service]
Type=simple
User=aideveloper
WorkingDirectory=/Users/aideveloper/core
ExecStart=/usr/bin/python3 integrations/openclaw_agent_controller.py
Restart=always

[Install]
WantedBy=multi-user.target
```

### Option 3: Add to Existing Backend

Integrate directly into your FastAPI backend:

```python
# In main.py
from integrations.openclaw_agent_controller import AgentController

@app.on_event("startup")
async def startup():
    controller = AgentController()
    asyncio.create_task(controller.run())
```

## Summary

You now have:

1. **Command Control**: Send `/commands` from WhatsApp to control agents
2. **Real-time Notifications**: Get updates as agents work
3. **Status Monitoring**: Check progress anytime with `/status`
4. **Deployment Control**: Deploy from WhatsApp with `/deploy`
5. **Full Integration**: Connect to your existing agent swarm code

Next step: Create the actual implementation files (agent_controller.py and agent_swarm_notifier.py)!
