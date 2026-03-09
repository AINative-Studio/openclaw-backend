---
description: Emergency context reset when agent goes off track
---

# Context Reset - Get Back On Track

## When to Use

Execute this when you realize you're:
- Modifying code without understanding the system
- Making assumptions about API endpoints
- Creating implementations that might exist already
- Changing code without reading documentation first

## Recovery Steps

### Step 1: STOP All Changes
```bash
# Don't commit anything yet
git status

# If changes are wrong, revert
git checkout -- [file]

# Or revert last commit if already committed
git reset --hard HEAD~1
```

### Step 2: Find Documentation
```bash
# Search for relevant docs
ls docs/ | grep -i [feature_name]
ls docs/ | grep -i [component_name]

# Search in docs content
grep -r "your search term" docs/

# List all available documentation
ls -lh docs/
```

### Step 3: Read Architecture
```bash
# Start with system architecture
cat docs/SYSTEM_ARCHITECTURE.md

# Then read feature-specific docs
cat docs/[relevant_doc].md

# For chat/conversation features
cat docs/chat-persistence-README.md
cat docs/chat-persistence-api.md
```

### Step 4: Verify Understanding
```bash
# Test endpoints exist
curl http://localhost:8000/api/v1/[endpoint]

# Check API docs in browser
curl http://localhost:8000/docs | grep [endpoint]

# Or open in browser
open http://localhost:8000/docs

# Test with real request
curl -X POST http://localhost:8000/api/v1/[endpoint] \
  -H "Content-Type: application/json" \
  -d '{"test": "data"}'
```

### Step 5: Implement Correctly
- Now you understand the system
- Follow documented patterns
- Use verified endpoints
- Implement with confidence

## Tell the User

When you execute context reset, inform them:
> "I'm stopping to read the documentation first. Let me verify the correct implementation approach."

## Common Scenarios

### Scenario 1: Frontend Component Changes
**Red Flag:** Seeing "simulated response" or mock data in code
**Action:**
```bash
# Find chat/conversation docs
ls docs/ | grep -i "chat\|conversation"

# Read API documentation
cat docs/chat-persistence-api.md

# Verify endpoints
curl http://localhost:8000/docs
```

### Scenario 2: Backend Endpoint Creation
**Red Flag:** Not sure if endpoint already exists
**Action:**
```bash
# Search existing endpoints
grep -r "router\\.post\\|router\\.get" backend/api/v1/endpoints/

# Check system architecture
cat docs/SYSTEM_ARCHITECTURE.md

# Look for similar endpoints
ls backend/api/v1/endpoints/
```

### Scenario 3: Database Schema Changes
**Red Flag:** About to run Alembic migrations directly
**Action:**
```bash
# Read database migration docs
cat docs/POSTGRESQL_MIGRATION.md

# Use the correct command
/database-schema-sync

# Never run: alembic upgrade head (WRONG!)
```

## Documentation Index

**High Priority Docs:**
- `docs/SYSTEM_ARCHITECTURE.md` - Overall system design (26 KB)
- `docs/chat-persistence-README.md` - Chat feature overview
- `docs/chat-persistence-api.md` - API endpoint reference
- `docs/POSTGRESQL_MIGRATION.md` - Database guidelines

**Integration Docs:**
- `docs/OPENCLAW_BRIDGE_QUICK_REFERENCE.md` - OpenClaw integration
- `docs/OPENCLAW_PLATFORM_ALIGNMENT_GAP_ANALYSIS.md` - Platform gaps

**Setup Docs:**
- `docs/OPENCLAW_SKILLS_SETUP.md` - CLI skills setup

**Total Documentation:** 46 architecture documents, 5,109+ lines

## Quick Checklist

Before implementing any code change:
- [ ] Searched for relevant documentation
- [ ] Read the architecture docs
- [ ] Verified endpoints exist with curl
- [ ] Checked for existing patterns
- [ ] Understand the data flow

If ANY checkbox is unchecked → use this context-reset command first!

## Example: Chat Feature Recovery

**Situation:** About to modify AgentChatTab.tsx without reading docs

**Recovery:**
```bash
# Step 1: Stop and revert
git checkout -- agent-swarm-monitor/components/openclaw/AgentChatTab.tsx

# Step 2: Find docs
ls docs/ | grep -i chat
# Output: chat-persistence-README.md, chat-persistence-api.md, etc.

# Step 3: Read docs
cat docs/chat-persistence-api.md
# Learned: Use /api/v1/agents/{id}/message endpoint

# Step 4: Verify
curl -X POST http://localhost:8000/api/v1/agents/3f632883-94eb-4269-9b57-fd56a3a88361/message \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'
# Response: {"response": "...", "message_id": "..."}

# Step 5: Now implement correctly with confidence
```

## Emergency Keywords

If you see these in your own thought process, STOP and context-reset:
- "I'll try..."
- "Maybe it's..."
- "I think the endpoint is..."
- "Let me guess..."
- "Probably should..."
- "I assume..."

**Replace with:**
- "Let me check the documentation first"
- "I'll verify this endpoint exists"
- "I'll read the architecture docs"
- "I'll test this with curl"
