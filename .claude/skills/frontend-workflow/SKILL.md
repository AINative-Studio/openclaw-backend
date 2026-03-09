---
description: Frontend code modification workflow with mandatory documentation checks
trigger_phrases:
  - modify frontend
  - change UI
  - update component
  - fix frontend bug
  - implement frontend feature
---

# Frontend Code Modification Workflow

## ZERO TOLERANCE RULE

**Never modify frontend code without understanding backend API integration.**

## Mandatory Pre-Change Checklist

### 1. Documentation Discovery
```bash
# Find relevant API docs
ls docs/ | grep -i "api\|chat\|conversation"

# Find integration docs
ls docs/ | grep -i "integration\|architecture"
```

### 2. Endpoint Verification
```bash
# Test endpoint exists
curl -X GET http://localhost:8000/api/v1/[endpoint]

# Check API documentation
curl http://localhost:8000/docs
```

### 3. Read Existing Code
- Check similar components for patterns
- Review API client implementation
- Understand state management flow

### 4. Implement
- Follow existing patterns
- Use correct API endpoints (verified with curl)
- Add loading states
- Handle errors

### 5. Test
- Verify API calls return expected data
- Check network tab in browser
- Test error scenarios

## Red Flags - STOP IMMEDIATELY

🚨 **If you encounter any of these, STOP and read documentation:**

1. "Simulated response" or "mock data" in existing code
2. No API call in component (when data should come from backend)
3. Uncertain about endpoint URL structure
4. Don't understand how data flows from backend to frontend
5. Can't find existing usage examples

## Recovery Procedure

If you realize you're modifying code incorrectly:

1. **STOP** editing immediately
2. **REVERT** any uncommitted changes
3. **SEARCH** for documentation: `ls docs/ | grep -i [feature]`
4. **READ** the architecture documentation
5. **VERIFY** endpoints exist with curl
6. **START OVER** with correct understanding

## Example: Chat Component Implementation

### ❌ WRONG APPROACH (Don't do this)
```typescript
// Guessing at endpoint without verification
const response = await fetch(`/send-message`, {
  method: 'POST',
  body: JSON.stringify({ text: message })
});
```

### ✅ CORRECT APPROACH (Do this)
```bash
# Step 1: Find documentation
ls docs/ | grep -i chat
# Found: chat-persistence-api.md

# Step 2: Read documentation
cat docs/chat-persistence-api.md
# Learned: endpoint is /api/v1/agents/{id}/message

# Step 3: Verify endpoint exists
curl -X POST http://localhost:8000/api/v1/agents/{agent_id}/message \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
# Response: {"response": "...", "message_id": "..."}

# Step 4: Implement correctly
```

```typescript
// Using verified endpoint from documentation
const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1';

const response = await fetch(`${API_URL}/agents/${agent.id}/message`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({ message: trimmed }),
});
```

## Critical Files Reference

**Frontend Components:**
- `agent-swarm-monitor/components/openclaw/` - OpenClaw UI components
- `agent-swarm-monitor/app/` - Next.js app routes

**Documentation:**
- `docs/chat-persistence-api.md` - API endpoint reference
- `docs/chat-persistence-README.md` - Architecture overview
- `docs/SYSTEM_ARCHITECTURE.md` - System design

**Backend Endpoints:**
- `backend/api/v1/endpoints/` - FastAPI endpoint definitions

## Environment Configuration

**CRITICAL:** Frontend requires proper API URL configuration

**Check `.env` file:**
```bash
# Must have this in agent-swarm-monitor/.env
NEXT_PUBLIC_API_URL=http://localhost:8000/api/v1
```

**Verify configuration:**
```bash
# Run pre-frontend-start hook
.claude/hooks/pre-frontend-start.sh
```

## Common Mistakes to Avoid

1. **Guessing endpoint names** - Always verify with curl and documentation
2. **Skipping error handling** - Frontend must handle API failures gracefully
3. **Hardcoding URLs** - Use environment variables
4. **Ignoring existing patterns** - Check how other components call APIs
5. **Not testing edge cases** - Test loading states, errors, empty responses
