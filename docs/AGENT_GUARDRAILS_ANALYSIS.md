# Agent Guardrails Analysis & Improvement Plan

## ✅ Implementation Status

**Phase 1 Completed:** 2026-03-06

All immediate guardrails have been implemented:

1. ✅ **architecture-first command** - `.claude/commands/architecture-first.md` (2.6 KB)
   - Enforces documentation reading before code changes in high-risk areas
   - Includes real incident example as learning reference
   - Provides verification questions checklist

2. ✅ **frontend-workflow skill** - `.claude/skills/frontend-workflow/SKILL.md` (4.0 KB)
   - ZERO TOLERANCE rule for frontend changes without backend understanding
   - Red flags that trigger immediate documentation review
   - Example showing wrong vs. correct approach

3. ✅ **context-reset command** - `.claude/commands/context-reset.md` (4.6 KB)
   - Emergency recovery procedure for when agents go off track
   - 5-step recovery process with bash examples
   - "Emergency keywords" to detect when agents are guessing

4. ✅ **delivery-checklist updated** - `.claude/commands/delivery-checklist.md` (2.7 KB)
   - Added "Documentation-First Requirement" section at top
   - Added mandatory checkbox: "Read relevant documentation BEFORE making changes"
   - Lists high-risk areas requiring docs check

**Usage:**
- `/architecture-first` - Load before modifying frontend/backend/database code
- `/context-reset` - Use when realizing you're off track
- `/delivery-checklist` - Pre-delivery verification (now includes docs requirement)
- Automatic trigger for frontend-workflow skill on "modify frontend", "change UI", etc.

## Incident Summary

**Date:** 2026-03-06
**Issue:** Agent modified frontend chat component without reading documentation, nearly breaking the entire frontend
**Root Cause:** No documentation-first requirement enforced before code changes

## What Happened

1. User reported: "simulated response from Main Agent" error
2. Agent jumped straight to changing frontend code
3. Agent created wrong API endpoint call without checking existing architecture
4. User caught the error: "did you read the docs before you just start changing fucking code"
5. Agent discovered 5,109 lines of comprehensive chat persistence documentation **after** making changes

## Current Guardrails (What Exists)

### ✅ Git Hooks (Working)
**Location:** `.claude/hooks/`

- **pre-commit:** Blocks misplaced .md/.sh files
- **commit-msg:** Blocks AI attribution
- **pre-backend-start.sh:** Enforces Railway PostgreSQL database
- **pre-frontend-start.sh:** Enforces API URL configuration

**Effectiveness:** ✅ GOOD - Catches problems at commit/runtime

### ✅ Modular Skills System
**Location:** `.claude/skills/`, `.claude/commands/`

**8 Core Skills:**
1. `mandatory-tdd` - Test-driven development enforcement
2. `git-workflow` - Git/PR standards
3. `file-placement` - Documentation organization
4. `database-schema-sync` - Schema management
5. `story-workflow` - Backlog management
6. `code-quality` - Coding standards
7. `ci-cd-compliance` - CI/CD requirements
8. `delivery-checklist` - Pre-delivery verification

**Effectiveness:** ⚠️ PARTIAL - Load when triggered, but no "read docs first" requirement

### ✅ Comprehensive Documentation
**Location:** `docs/`

**46 Architecture Documents** including:
- `SYSTEM_ARCHITECTURE.md` (26 KB)
- `chat-persistence-*` (7 files, 5,109 lines)
- `OPENCLAW_PLATFORM_ALIGNMENT_GAP_ANALYSIS.md` (31 KB)
- Integration guides, implementation plans, troubleshooting

**Effectiveness:** ✅ EXCELLENT - Documentation exists, but agents don't read it first

## Critical Gaps (What's Missing)

### ❌ GAP 1: No "Documentation-First" Enforcement

**Problem:** Agents can modify code without reading relevant documentation

**Impact:**
- Nearly broke entire frontend
- Wasted time reverting changes
- Created wrong implementation that had to be redone

**What Should Have Happened:**
1. Agent sees "simulated response" error
2. Agent searches for `chat*` or `conversation*` documentation
3. Agent finds `chat-persistence-api.md`
4. Agent learns `/api/v1/agents/{id}/message` endpoint exists
5. Agent implements correctly the first time

### ❌ GAP 2: No Frontend-Specific Workflow

**Problem:** No special rules for UI/frontend changes

**Frontend is Higher Risk:**
- User-facing (mistakes are immediately visible)
- Complex state management
- API integration points
- Often has detailed documentation

**Missing:**
- Frontend code change workflow
- UI testing requirements
- API endpoint verification steps

### ❌ GAP 3: No Pre-Code-Change Validation

**Problem:** No hook/check before allowing code modifications

**Missing Checks:**
- "Does documentation exist for this component?"
- "Have you read the architecture docs?"
- "Do you understand the existing implementation?"

### ❌ GAP 4: No Context Recovery Guide

**Problem:** When agent goes off track, no clear recovery procedure

**Missing:**
- "Stop and read docs" command
- Quick context reset procedure
- Emergency brake for agents

## Improvement Plan

### 🔧 SOLUTION 1: Create `architecture-first` Skill

**Purpose:** Enforce documentation reading before code changes

**Trigger Phrases:**
- "modify frontend", "change UI", "update component"
- "add endpoint", "API integration"
- "fix bug in [component]"
- "implement [feature]"

**Workflow:**
```markdown
# Architecture-First Skill

BEFORE modifying any code in these areas, you MUST read relevant documentation:

## High-Risk Areas Requiring Docs Check

### Frontend/UI Changes
**Location:** `agent-swarm-monitor/components/`, `agent-swarm-monitor/app/`
**Docs:** `docs/chat-persistence-api.md`, integration docs

**Mandatory Steps:**
1. Search docs for component name (e.g., "chat", "conversation", "agent")
2. Read API endpoint documentation
3. Verify endpoint exists with curl test
4. Check existing implementation patterns
5. THEN modify code

### Backend API Changes
**Location:** `backend/api/v1/endpoints/`
**Docs:** `docs/SYSTEM_ARCHITECTURE.md`, feature-specific docs

**Mandatory Steps:**
1. Read architecture documentation
2. Check for existing endpoints
3. Verify data flow diagrams
4. Review service layer patterns
5. THEN add/modify endpoints

### Database Changes
**Location:** `backend/models/`, `alembic/`
**Docs:** `docs/POSTGRESQL_MIGRATION.md`, schema docs

**Mandatory Steps:**
1. Read database schema documentation
2. Use `/database-schema-sync` command
3. Never run Alembic migrations directly
4. THEN make schema changes

## Emergency Stop Command

If you realize you're modifying code without understanding the architecture:

**STOP. Execute:**
```bash
# Find relevant documentation
ls docs/ | grep -i [component_name]

# Read before proceeding
cat docs/[relevant_doc].md
```

## Verification Questions

Before committing code changes, answer:

1. ✅ Did I read the documentation for this component/feature?
2. ✅ Do I understand how it integrates with the rest of the system?
3. ✅ Did I verify the API endpoints exist with curl?
4. ✅ Did I check for existing patterns in the codebase?

If any answer is NO → STOP and read documentation.
```

**Implementation:**
```bash
# Create skill
cat > .claude/commands/architecture-first.md << 'EOF'
---
description: Enforce reading documentation before code modifications
---

[Insert workflow above]
EOF
```

### 🔧 SOLUTION 2: Create Pre-Code-Change Hook

**Purpose:** Block code changes until documentation is verified

**Implementation:**
```bash
# .claude/hooks/pre-code-edit.sh
#!/bin/bash
# Checks if agent should read docs before modifying code

set -e

CHANGED_FILES="$1"

# High-risk paths that require docs check
HIGH_RISK_PATHS=(
    "agent-swarm-monitor/components/"
    "agent-swarm-monitor/app/"
    "backend/api/v1/endpoints/"
    "backend/models/"
)

# Check if any high-risk files are being modified
for file in $CHANGED_FILES; do
    for path in "${HIGH_RISK_PATHS[@]}"; do
        if [[ "$file" == *"$path"* ]]; then
            echo "⚠️  DOCUMENTATION CHECK REQUIRED"
            echo "   You are modifying: $file"
            echo ""
            echo "   BEFORE proceeding, verify you have read:"
            echo "   1. Search docs for relevant component/feature"
            echo "   2. Read API documentation if applicable"
            echo "   3. Verify endpoints exist with curl tests"
            echo ""
            echo "   Continue? (yes/no)"
            read -r response

            if [[ "$response" != "yes" ]]; then
                echo "❌ Code modification blocked - read docs first"
                exit 1
            fi
        fi
    done
done

exit 0
```

**Note:** This would be invoked by Claude Code's edit rejection system

### 🔧 SOLUTION 3: Frontend-Specific Workflow

**Create:** `.claude/skills/frontend-workflow/SKILL.md`

```markdown
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
```

### 🔧 SOLUTION 4: Context Recovery Command

**Create:** `.claude/commands/context-reset.md`

```markdown
---
description: Emergency context reset when agent goes off track
---

# Context Reset - Get Back On Track

## When to Use

Execute this when you realize you're:
- Modifying code without understanding the system
- Making assumptions about API endpoints
- Creating implementations that might exist already

## Recovery Steps

### Step 1: STOP All Changes
```bash
# Don't commit anything yet
git status

# If changes are wrong, revert
git checkout -- [file]
```

### Step 2: Find Documentation
```bash
# Search for relevant docs
ls docs/ | grep -i [feature_name]
ls docs/ | grep -i [component_name]

# Search in docs content
grep -r "your search term" docs/
```

### Step 3: Read Architecture
```bash
# Start with system architecture
cat docs/SYSTEM_ARCHITECTURE.md

# Then read feature-specific docs
cat docs/[relevant_doc].md
```

### Step 4: Verify Understanding
```bash
# Test endpoints exist
curl http://localhost:8000/api/v1/[endpoint]

# Check API docs
curl http://localhost:8000/docs | grep [endpoint]
```

### Step 5: Implement Correctly
- Now you understand the system
- Follow documented patterns
- Use verified endpoints
- Implement with confidence

## Tell the User

When you execute context reset, inform them:
"I'm stopping to read the documentation first. Let me verify the correct implementation approach."
```

## Recommended Implementation Priority

### Phase 1: Immediate (Today) - ✅ COMPLETED
1. ✅ Create `architecture-first` skill - DONE (.claude/commands/architecture-first.md)
2. ✅ Create `frontend-workflow` skill - DONE (.claude/skills/frontend-workflow/SKILL.md)
3. ✅ Create `context-reset` command - DONE (.claude/commands/context-reset.md)
4. ✅ Document this incident as example in skills - DONE (included in architecture-first.md)

### Phase 2: This Week
5. ✅ Add "docs check" to delivery-checklist - DONE (updated .claude/commands/delivery-checklist.md)
6. Update code-quality skill with documentation requirements
7. Create documentation index/map for quick reference

### Phase 3: Next Sprint - ✅ COMPLETED (PreToolUse Hook)
8. ✅ Implement pre-code-change hook - DONE (.claude/hooks/pre-edit-check.sh)
   - PreToolUse hook blocks Edit/Write on high-risk files
   - Checks for /tmp/claude-docs-reviewed-{session_id} flag
   - Exit 2 = block with helpful error message
   - Exit 0 = allow if flag exists or low-risk file
   - See docs/PHASE_3_PRETOOLUSE_HOOK_IMPLEMENTATION.md
9. Add automated doc search to agent context - TODO (Phase 4)
10. Create "architecture Q&A" quick reference - TODO (Phase 4)

## How to Prevent This With Other Agents

### For Human Reviewers

**Catch Early:**
```bash
# In PR review, check for these red flags:
- Agent modified component without mentioning docs
- No API verification steps shown
- "Simulated" or "mock" removed without understanding why it was there
```

**Challenge Immediately:**
"Did you read the documentation for this component? Show me which docs you consulted."

### For Agent Instructions

**Add to Claude Code System Prompt:**
```
CRITICAL RULE: Before modifying any frontend or backend code:
1. Search for documentation: ls docs/ | grep -i [feature]
2. Read relevant architecture docs
3. Verify API endpoints exist with curl
4. THEN modify code

If uncertain, use /context-reset command to restart with documentation review.
```

### For Project Setup

**Add to README.md:**
```markdown
## Agent Development Rules

### Documentation-First Principle

**NEVER modify code without reading documentation first.**

High-risk areas requiring mandatory docs check:
- Frontend components (agent-swarm-monitor/components/)
- Backend API endpoints (backend/api/v1/endpoints/)
- Database models (backend/models/)

**Before ANY code change:**
1. `ls docs/ | grep -i [component]` - Find docs
2. `cat docs/[doc].md` - Read docs
3. `curl http://localhost:8000/api/v1/[endpoint]` - Verify endpoints
4. Then modify code
```

## Metrics to Track

**Prevention Success:**
- Number of "read docs first" skill invocations
- PRs that include "documentation consulted: X" in description
- Reduced code reverts due to wrong implementation

**Failure Detection:**
- PRs that modify high-risk code without doc references
- Reverted commits (track reason)
- User interventions due to wrong implementation

## Conclusion

**Root Cause:** No documentation-first enforcement
**Impact:** Nearly broke entire frontend, wasted 2 hours
**Solution:** 4 new skills/commands + documentation-first culture

**Key Insight:**
> "If 5,109 lines of documentation exist, agents MUST read it before making changes."

**Prevention Philosophy:**
> "Trust, but verify. Assume documentation exists. Read first, code second."

---

**Created:** 2026-03-06
**Incident:** Frontend chat component near-breakage
**Status:** Recommendations pending implementation
