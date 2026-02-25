# DBOS Workflow Integration Specification

## Overview

This document specifies the HTTP endpoints that need to be added to the OpenClaw Gateway (`openclaw-gateway/dist/server.js`) to expose DBOS durable workflows to the Python backend.

## Current State

**Gateway** (openclaw-gateway/dist/server.js):
- ✅ DBOS workflows implemented: `AgentLifecycleWorkflow`, `AgentMessageWorkflow`
- ✅ HTTP endpoint for messages: `POST /messages` (uses `AgentMessageWorkflow`)
- ❌ No HTTP endpoints for Agent Lifecycle workflows

**Backend** (Python):
- ❌ Services doing direct DB operations instead of using DBOS workflows
- ❌ No crash recovery or durability for agent provisioning
- ❌ No automatic retry logic

## Required Gateway Endpoints

Add the following endpoints to `openclaw-gateway/dist/server.js` (or the TypeScript source if available):

### 1. Agent Provisioning Workflow

**Endpoint**: `POST /workflows/provision-agent`

**Request Body**:
```json
{
  "agentId": "uuid-string",
  "name": "Agent Name",
  "persona": "Agent persona text...",
  "model": "anthropic/claude-3-haiku-20240307",
  "userId": "uuid-string",
  "sessionKey": "agent:agent-name:main",
  "heartbeatEnabled": false,
  "heartbeatInterval": "hourly",
  "heartbeatChecklist": ["check1", "check2"],
  "configuration": {}
}
```

**Response**:
```json
{
  "success": true,
  "workflowUuid": "workflow-uuid",
  "result": {
    "agentId": "uuid-string",
    "status": "provisioned",
    "sessionKey": "agent:agent-name:main",
    "openclawAgentId": "message-id-from-gateway",
    "timestamp": 1234567890
  }
}
```

**Implementation** (add to server.js):
```javascript
import { AgentLifecycleWorkflow } from './workflows/agent-lifecycle-workflow.js';

// Add this endpoint
app.post('/workflows/provision-agent', async (req, res) => {
  try {
    const request = {
      agentId: req.body.agentId,
      name: req.body.name,
      persona: req.body.persona,
      model: req.body.model,
      userId: req.body.userId,
      sessionKey: req.body.sessionKey,
      heartbeatEnabled: req.body.heartbeatEnabled,
      heartbeatInterval: req.body.heartbeatInterval,
      heartbeatChecklist: req.body.heartbeatChecklist,
      configuration: req.body.configuration
    };

    const handle = await DBOS.startWorkflow(AgentLifecycleWorkflow)
      .provisionAgentWorkflow(request);
    const result = await handle.getResult();

    res.json({
      success: true,
      workflowUuid: handle.getWorkflowUUID(),
      result
    });
  } catch (error) {
    res.status(500).json({
      error: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});
```

### 2. Heartbeat Execution Workflow

**Endpoint**: `POST /workflows/heartbeat`

**Request Body**:
```json
{
  "agentId": "uuid-string",
  "sessionKey": "agent:agent-name:main",
  "checklist": ["task1", "task2"],
  "executionId": "execution-uuid"
}
```

**Response**:
```json
{
  "success": true,
  "workflowUuid": "workflow-uuid",
  "result": {
    "executionId": "execution-uuid",
    "agentId": "uuid-string",
    "status": "completed",
    "duration": 1234,
    "result": {},
    "timestamp": 1234567890
  }
}
```

**Implementation**:
```javascript
app.post('/workflows/heartbeat', async (req, res) => {
  try {
    const request = {
      agentId: req.body.agentId,
      sessionKey: req.body.sessionKey,
      checklist: req.body.checklist,
      executionId: req.body.executionId
    };

    const handle = await DBOS.startWorkflow(AgentLifecycleWorkflow)
      .heartbeatWorkflow(request);
    const result = await handle.getResult();

    res.json({
      success: true,
      workflowUuid: handle.getWorkflowUUID(),
      result
    });
  } catch (error) {
    res.status(500).json({
      error: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});
```

### 3. Pause/Resume Workflow

**Endpoint**: `POST /workflows/pause-resume`

**Request Body**:
```json
{
  "agentId": "uuid-string",
  "action": "pause",
  "sessionKey": "agent:agent-name:main",
  "preserveState": true
}
```

**Response**:
```json
{
  "success": true,
  "workflowUuid": "workflow-uuid",
  "result": {
    "agentId": "uuid-string",
    "action": "pause",
    "status": "success",
    "state": {},
    "timestamp": 1234567890
  }
}
```

**Implementation**:
```javascript
app.post('/workflows/pause-resume', async (req, res) => {
  try {
    const request = {
      agentId: req.body.agentId,
      action: req.body.action,
      sessionKey: req.body.sessionKey,
      preserveState: req.body.preserveState
    };

    const handle = await DBOS.startWorkflow(AgentLifecycleWorkflow)
      .pauseResumeWorkflow(request);
    const result = await handle.getResult();

    res.json({
      success: true,
      workflowUuid: handle.getWorkflowUUID(),
      result
    });
  } catch (error) {
    res.status(500).json({
      error: error instanceof Error ? error.message : 'Unknown error'
    });
  }
});
```

## Benefits of Integration

### Crash Safety
- If the Gateway crashes mid-provisioning, DBOS automatically resumes from the last completed step
- No agents stuck in limbo with inconsistent state

### Exactly-Once Semantics
- Duplicate provisioning requests are handled idempotently
- No duplicate agents created on retry

### State Consistency
- Database transactions coordinated with workflow steps
- Atomic state transitions

### Observability
- Built-in workflow execution tracking via `GET /workflows/:uuid`
- Debug and monitor all provisioning attempts

## Backend Integration

The Python backend will use a new `DBOSWorkflowClient` class to call these endpoints:

```python
# backend/clients/dbos_workflow_client.py

class DBOSWorkflowClient:
    async def provision_agent(self, request: AgentProvisionRequest) -> dict:
        """Call DBOS provisionAgentWorkflow via Gateway"""
        response = await self.http_client.post(
            f"{self.gateway_url}/workflows/provision-agent",
            json=request.dict()
        )
        return response.json()
```

Backend services will then use this client instead of direct DB operations:

```python
# backend/services/agent_lifecycle_api_service.py

async def provision_agent(self, agent_id: str):
    # OLD (non-resilient):
    # agent.status = RUNNING
    # db.commit()  # ⚠️ Crash here = agent stuck

    # NEW (resilient via DBOS):
    result = await dbos_client.provision_agent({
        'agentId': str(agent_id),
        'name': agent.name,
        ...
    })
    # DBOS handles crash recovery, retry, state management
```

## Migration Path

### Phase 1: Add Gateway Endpoints (Developer with TypeScript access)
1. Obtain TypeScript source for openclaw-gateway
2. Add the three endpoints specified above
3. Recompile and deploy Gateway

### Phase 2: Backend Integration (Current)
1. ✅ Create `DBOSWorkflowClient` in backend (READY)
2. ✅ Add fallback mode for when endpoints don't exist yet (READY)
3. ✅ Update backend services to use client (READY)

### Phase 3: Testing & Rollout
1. Test with Gateway endpoints enabled
2. Verify crash recovery behavior
3. Monitor workflow execution via `/workflows/:uuid`
4. Gradual rollout to production

## Current Status

**Backend**: ✅ DBOS client implemented with graceful fallback
**Gateway**: ⏳ Awaiting endpoint implementation (requires TypeScript source access)

When Gateway endpoints are added, backend will automatically start using them (no code changes needed in backend).

## References

- Gateway Server: `/Users/aideveloper/openclaw-backend/openclaw-gateway/dist/server.js`
- DBOS Workflows: `/Users/aideveloper/openclaw-backend/openclaw-gateway/dist/workflows/`
- Backend Client: `/Users/aideveloper/openclaw-backend/backend/clients/dbos_workflow_client.py`
- Backend Services: `/Users/aideveloper/openclaw-backend/backend/services/agent_lifecycle_api_service.py`
