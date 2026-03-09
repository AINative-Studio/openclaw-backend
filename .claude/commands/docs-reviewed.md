---
description: Mark documentation as reviewed to allow high-risk file edits
---

# Documentation Reviewed

**IMPORTANT: When this command loads, immediately execute:**
```bash
.claude/hooks/mark-docs-reviewed.sh
```

This command marks that you have reviewed the relevant documentation for the component/feature you're about to modify.

**Effect:** Allows Edit/Write operations on high-risk files for the remainder of this session.

## When to Use

Use this command **after** you have:

1. ✅ Searched for relevant documentation
2. ✅ Read the architecture/API documentation
3. ✅ Verified endpoints exist (if applicable)
4. ✅ Understood the existing implementation

## High-Risk Areas Protected

This flag enables edits for:
- Frontend components (`agent-swarm-monitor/components/`, `agent-swarm-monitor/app/`)
- Backend API endpoints (`backend/api/v1/endpoints/`)
- Database models (`backend/models/`, `alembic/`)

## Documentation Checklist

Before running this command, confirm you've reviewed:

### For Frontend Changes
- [ ] Read `docs/chat-persistence-api.md`
- [ ] Verified API endpoints with curl
- [ ] Checked existing component patterns
- [ ] Understood data flow from backend

### For Backend API Changes
- [ ] Read `docs/SYSTEM_ARCHITECTURE.md`
- [ ] Checked for existing similar endpoints
- [ ] Reviewed service layer patterns
- [ ] Understood data models

### For Database Changes
- [ ] Read `docs/POSTGRESQL_MIGRATION.md`
- [ ] Reviewed existing schema
- [ ] Confirmed migration approach (use `/database-schema-sync`)

## Usage

Simply type:
```
/docs-reviewed
```

The system will:
1. Create a session flag at `/tmp/claude-docs-reviewed-{session_id}`
2. Allow Edit/Write operations on high-risk files
3. Log that documentation was marked as reviewed

## Important Notes

⚠️ **This flag lasts only for the current session**
   - If you restart Claude Code, you'll need to re-review docs

⚠️ **Don't abuse this**
   - Only use after genuinely reading documentation
   - The goal is to prevent mistakes, not create paperwork

✅ **Best Practice**
   - Run `/architecture-first` or `/context-reset` first
   - Review docs thoroughly
   - Then run `/docs-reviewed`
   - Implement with confidence

## Example Workflow

```bash
# 1. Agent encounters "simulated response" error
# 2. Agent runs context-reset
/context-reset

# 3. Find docs
ls docs/ | grep -i chat
# Output: chat-persistence-api.md

# 4. Read docs
cat docs/chat-persistence-api.md
# Learned: Use /api/v1/agents/{id}/message endpoint

# 5. Verify endpoint
curl http://localhost:8000/api/v1/agents/{agent_id}/message
# Response confirms it works

# 6. Mark docs as reviewed
/docs-reviewed

# 7. Now edits are allowed
# Agent can modify AgentChatTab.tsx confidently
```

## Clearing the Flag

The flag auto-clears when:
- Session ends
- Claude Code restarts
- System reboots (flag is in `/tmp/`)

To manually clear (for testing):
```bash
rm /tmp/claude-docs-reviewed-*
```
