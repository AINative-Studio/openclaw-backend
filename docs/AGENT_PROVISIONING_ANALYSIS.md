# Agent Provisioning & Model API Analysis

**Date**: 2026-02-24
**Issues Investigated**:
1. Agents stuck in "provisioning" status for 3+ days
2. Model API key configuration and usage (OpenClaw vs AINative)

---

## Issue 1: Agents Stuck in Provisioning Status

### Current Situation

**Database Evidence**:
```sql
sqlite3 openclaw.db "SELECT id, name, status, created_at FROM agent_swarm_instances;"

278ee5a2-d285-4d83-b0fa-0bdb470ef8a2 | Sales Agent  | provisioning | 2026-02-21 01:58:04
6448b18b-b1ba-4544-9094-f2c2db4be302 | VP Marketing | provisioning | 2026-02-21 01:42:32
```

Two agents created 3 days ago are still in "provisioning" status.

### Root Cause Analysis

#### Backend Flow

The agent lifecycle has **TWO separate steps** that must both complete:

1. **`create_agent()`** - Creates agent in database with status = `PROVISIONING`
   - Location: `backend/services/agent_swarm_lifecycle_service.py:81-153`
   - Creates DB record
   - Does NOT start the agent

2. **`provision_agent()`** - Actually provisions the agent with OpenClaw
   - Location: `backend/services/agent_swarm_lifecycle_service.py:155-244`
   - Connects to OpenClaw Gateway
   - Sends provisioning message
   - Updates status to `RUNNING`
   - **This step was NEVER called for these agents**

#### API Endpoints

Backend exposes separate endpoints:
- `POST /api/v1/agents` - Creates agent (status: provisioning)
- `POST /api/v1/agents/{id}/provision` - Provisions agent (status: running)

Location: `backend/api/v1/endpoints/agent_lifecycle.py`

#### Frontend Issue

**The frontend is missing the provision call!**

Analysis of `agent-swarm-monitor`:

1. **Service Layer** (`lib/openclaw-service.ts`):
   - Has `createAgent()` method ✅
   - Has `provisionAgent()` method ✅
   - Both methods exist and work correctly

2. **Hooks Layer** (`hooks/useOpenClawAgents.ts`):
   - Has `useCreateAgent()` hook ✅
   - **MISSING** `useProvisionAgent()` hook ❌
   - No way for UI to call provision endpoint

3. **UI Components**:
   - Create agent dialog calls `useCreateAgent()`
   - Never calls provision after creation
   - Agents stay in provisioning forever

### Why This Happens

The two-step design is intentional for these reasons:

1. **Validation First**: Create agent in DB, validate inputs
2. **Async Provisioning**: OpenClaw connection may take time
3. **Error Handling**: Can retry provision without duplicating agents
4. **Status Tracking**: Clear status progression

However, the frontend doesn't implement the second step!

### The Bug

**Location**: Frontend (`agent-swarm-monitor`)

**What's Missing**:
1. No `useProvisionAgent()` hook in `hooks/useOpenClawAgents.ts`
2. No auto-provision logic after agent creation
3. No UI button/action to manually trigger provisioning

**Expected Flow**:
```
User clicks "Create Agent"
  → POST /agents (status: provisioning)
  → Auto-call POST /agents/{id}/provision
  → Status updates to "running"
```

**Actual Flow**:
```
User clicks "Create Agent"
  → POST /agents (status: provisioning)
  → ❌ Nothing happens
  → Agent stuck in provisioning forever
```

### Solutions

#### Option 1: Auto-Provision in Frontend (Recommended)

Update `hooks/useOpenClawAgents.ts`:

```typescript
export function useCreateAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: CreateAgentRequest) => {
      // Step 1: Create agent
      const agent = await openClawService.createAgent(data);

      // Step 2: Auto-provision
      await openClawService.provisionAgent(agent.id);

      return agent;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['openclaw-agents'] });
    },
  });
}
```

**Pros**:
- Simple, one-button creation
- Matches user expectation
- No UI changes needed

**Cons**:
- Hides provision step from user
- Can't retry provision separately if it fails

#### Option 2: Separate Provision Button

Add new hook:

```typescript
export function useProvisionAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (agentId: string) => openClawService.provisionAgent(agentId),
    onSuccess: (_, agentId) => {
      queryClient.invalidateQueries({ queryKey: ['openclaw-agents'] });
      queryClient.invalidateQueries({ queryKey: ['openclaw-agent', agentId] });
    },
  });
}
```

Add button in agent list for provisioning status agents.

**Pros**:
- Explicit control
- Can retry provision
- Shows real status

**Cons**:
- Extra UI complexity
- User must click twice

#### Option 3: Backend Auto-Provision (Not Recommended)

Make `create_agent()` automatically call `provision_agent()`.

**Pros**:
- No frontend changes
- Simple for frontend

**Cons**:
- Slower API response
- Harder error handling
- Breaks two-step design pattern
- Can't provision later if OpenClaw is down

### Recommendation

**Implement Option 1** (Auto-provision in frontend) with retry logic:

```typescript
export function useCreateAgent() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (data: CreateAgentRequest) => {
      // Step 1: Create agent
      const agent = await openClawService.createAgent(data);

      // Step 2: Auto-provision with retry
      try {
        await openClawService.provisionAgent(agent.id);
      } catch (error) {
        // Log error but don't fail creation
        console.error('Provision failed, agent left in provisioning state:', error);
        // User can manually retry via provision button
      }

      return agent;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['openclaw-agents'] });
    },
  });
}
```

Then add a "Provision" button for agents still in provisioning status (Option 2 as fallback).

---

## Issue 2: Model API Key Configuration

### Current Implementation

**API Used**: **Direct Anthropic API** (Official SDK)

**Evidence**:

1. **Package**: Uses official `anthropic` Python package
   - Location: `backend/agents/orchestration/command_parser.py:142`
   - Import: `from anthropic import Anthropic`

2. **API Key**: `ANTHROPIC_API_KEY` environment variable
   - Location: `backend/agents/orchestration/command_parser.py:143`
   - Code: `api_key = os.getenv("ANTHROPIC_API_KEY")`

3. **Client**: Direct Anthropic client
   - Location: `backend/agents/orchestration/command_parser.py:145`
   - Code: `self.client = Anthropic(api_key=api_key)`

4. **API Calls**: Standard Anthropic Messages API
   - Location: `backend/agents/orchestration/command_parser.py:331-336`
   - Code: `self.client.messages.create(model=self.llm_model, ...)`

### Where It's Used

**Single Use Case**: WhatsApp Command Parsing

- **File**: `backend/agents/orchestration/command_parser.py`
- **Purpose**: Parse natural language commands via Claude Haiku
- **Model**: `claude-3-5-haiku-20241022` (fast, cheap for parsing)
- **Cost**: ~$0.0001 per command
- **Optional**: Falls back to regex if API key not set

**Not Used For**:
- Agent execution ❌
- Agent conversations ❌
- Agent code generation ❌

### Model Configuration in Agents

Agents store model names in database:
```sql
SELECT model FROM agent_swarm_instances;
→ "google/gemini-2.0-flash"
→ "anthropic/claude-opus-4-5"
```

**Important**: These model names are **only metadata**. They're stored but **not currently used** to make API calls. The agent execution logic that would use these models is not yet implemented in the codebase.

### AINative Chat Completion APIs

**Search Results**: No references found to:
- AINative chat completion APIs
- Custom API base URLs
- OpenRouter
- LiteLLM
- Any API gateway/proxy

**Conclusion**: The system does **NOT** use AINative's chat completion APIs. It only uses direct Anthropic APIs for command parsing.

### API Key Configuration

**Current State**:
```bash
# Only this environment variable is used:
ANTHROPIC_API_KEY=sk-ant-...

# Not used (agents are only metadata):
# - No API keys for agent execution
# - No AINative API keys
# - No OpenRouter/LiteLLM keys
```

**Location**: Set in environment variables (not in database or config files)

### Security Notes

✅ **Good Practices**:
- API key in environment variable (not hardcoded)
- Optional feature (works without key)
- Graceful degradation (falls back to regex)

⚠️ **Missing**:
- No key rotation
- No key validation on startup
- No rate limiting
- No cost tracking

### Future Considerations

When agent execution is implemented, you'll need to decide:

1. **Direct API Calls**:
   - Each agent uses `ANTHROPIC_API_KEY` or `OPENAI_API_KEY`
   - Simple, direct
   - Hard to track costs per agent

2. **AINative Chat Completion API**:
   - Route through AINative's unified API
   - Track costs per agent
   - Support multiple model providers
   - Better observability

3. **Hybrid Approach**:
   - Command parsing: Direct Anthropic (current)
   - Agent execution: AINative chat API
   - Best of both worlds

---

## Summary & Action Items

### Issue 1: Agents Stuck in Provisioning

**Root Cause**: Frontend doesn't call provision endpoint after creating agents

**Action Required**:
1. ✅ Add auto-provision to `useCreateAgent()` hook
2. ✅ Add `useProvisionAgent()` hook for manual retry
3. ✅ Add "Provision" button for agents in provisioning status
4. ✅ Add error handling and retry logic

**Files to Modify**:
- `agent-swarm-monitor/hooks/useOpenClawAgents.ts`
- `agent-swarm-monitor/components/openclaw/CreateAgentDialog.tsx` (optional)
- `agent-swarm-monitor/components/openclaw/AgentStatusBadge.tsx` (optional provision button)

### Issue 2: Model API Configuration

**Current State**: Uses direct Anthropic API for command parsing only

**Confirmed**:
- ✅ Uses official Anthropic SDK
- ✅ Uses `ANTHROPIC_API_KEY` environment variable
- ✅ Only used for WhatsApp command parsing
- ✅ Does NOT use AINative chat completion APIs
- ✅ Does NOT use OpenClaw for model API calls

**No Action Required**: Current implementation is correct for its purpose

**Future Considerations**:
- When implementing agent execution, decide on API strategy
- Consider AINative chat completion API for better observability
- Implement cost tracking and rate limiting

---

## Testing the Fix

### 1. Fix Existing Stuck Agents

```bash
# Provision the two stuck agents manually via API
curl -X POST http://localhost:8000/api/v1/agents/278ee5a2-d285-4d83-b0fa-0bdb470ef8a2/provision
curl -X POST http://localhost:8000/api/v1/agents/6448b18b-b1ba-4544-9094-f2c2db4be302/provision

# Verify status changed to "running"
sqlite3 openclaw.db "SELECT id, name, status FROM agent_swarm_instances;"
```

### 2. Test New Agent Creation

After implementing the frontend fix:

1. Create new agent via UI
2. Check network tab - should see TWO API calls:
   - POST `/api/v1/agents` (create)
   - POST `/api/v1/agents/{id}/provision` (provision)
3. Agent should show "running" status immediately
4. No agents should be stuck in "provisioning"

### 3. Test Error Handling

1. Stop OpenClaw Gateway
2. Create new agent
3. Should create successfully but fail to provision
4. Should see "Provision" button to retry
5. Start Gateway and click "Provision"
6. Should succeed and status → "running"

---

## Questions?

- **Why separate endpoints?** → Better error handling, async operations
- **Why not auto-provision in backend?** → Slower, blocks API response, harder to retry
- **Is the API key secure?** → Yes (env var), but needs rotation strategy
- **Do agents use the API key?** → Not yet, only command parsing uses it
- **Should we use AINative APIs?** → Decision pending, not currently needed
