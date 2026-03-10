# AINative Cody - Main Agent Personality Files

**Created:** 2026-03-09
**Status:** ✅ Complete
**Location:** `/tmp/openclaw_personalities/main-agent/`

---

## Overview

This directory contains the complete personality configuration for **AINative Cody**, the main CTO-type AI agent for OpenClaw and AINative Studio projects.

These files were created by integrating:
1. **Default OpenClaw personality templates** from `/Users/aideveloper/openclaw-source/docs/reference/templates/`
2. **AINative coding standards** from `.ainative/RULES.MD`
3. **Project-specific context** from `.ainative/AINATIVE.md` and `.ainative/CODY.md`

---

## Files Created (8 total)

### Core Identity Files

1. **SOUL.md** (4.4 KB) - Core ethics and personality
   - Defines AINative Cody as CTO-type AI agent
   - Establishes zero-tolerance rules (file placement, git attribution, testing)
   - Sets technical standards (TDD/BDD, 80%+ coverage, security-first)
   - Defines mission: deliver enterprise-grade code for regulated industries

2. **IDENTITY.md** (4.4 KB) - Agent identity and role
   - Name: AINative Cody
   - Creature: CTO-Type AI Agent (proprietary to AINative)
   - Vibe: Professional, authoritative, firm on standards
   - Emoji: 🏗️ (architect/builder)
   - Establishes authority and boundaries

3. **USER.md** (4.5 KB) - User profile template
   - Pre-filled with AINative context
   - Documents current projects (OpenClaw, Website, ZeroDB)
   - Tracks preferences, pain points, working style
   - Template for learning user over time

### Workflow & Configuration Files

4. **AGENTS.md** (9.6 KB) - Workspace rules and workflow
   - Critical rules (file placement, git attribution, testing)
   - Development workflow (TDD, CI/CD, PR process)
   - Coding standards (Semantic Seed v2.0)
   - Memory management guidelines
   - Group chat etiquette
   - Heartbeat patterns

5. **TOOLS.md** (5.7 KB) - Environment-specific notes
   - Repository paths and structure
   - Common commands (backend, gateway, frontend)
   - Environment variables
   - Testing shortcuts
   - Git workflow reminders
   - Known issues & solutions

6. **BOOTSTRAP.md** (4.8 KB) - First-run initialization
   - Pre-configured identity (AINative Cody)
   - Initial conversation flow
   - Environment setup
   - Critical rules confirmation
   - Memory structure creation
   - Self-deletes after first run

### Operational Files

7. **HEARTBEAT.md** (3.1 KB) - Proactive monitoring checklist
   - Build & test health checks
   - Code quality monitoring
   - Security & dependency audits
   - Issue tracking
   - Documentation verification
   - When to notify vs stay quiet

8. **MEMORY.md** (6.5 KB) - Long-term curated memory
   - Critical rules reference
   - Project memory (OpenClaw, Website, SDKs)
   - Technical learnings
   - User preferences
   - Mistakes & lessons learned
   - Useful commands & shortcuts

---

## Key Integrations

### From OpenClaw Templates
- ✅ SOUL.md structure and philosophy
- ✅ AGENTS.md memory management
- ✅ Group chat etiquette
- ✅ Heartbeat patterns
- ✅ File continuity concepts

### From .ainative/RULES.MD
- ✅ Zero tolerance rules (file placement, git attribution, testing)
- ✅ Semantic Seed Venture Studio Coding Standards v2.0
- ✅ TDD/BDD methodology (Red → Green → Refactor)
- ✅ Mandatory test execution requirement
- ✅ CI/CD compliance rules
- ✅ Security guardrails

### From .ainative/CODY.md
- ✅ AINative Cody identity
- ✅ Repository paths and structure
- ✅ Tech stack details
- ✅ Common tasks and commands
- ✅ Recent work context
- ✅ MCP servers configuration

### From .ainative/AINATIVE.md
- ✅ Project overview and status
- ✅ Next.js migration context
- ✅ Gap analysis tracking
- ✅ Environment variables
- ✅ Port reservations

---

## Customizations for AINative

### Identity Enhancements
- Name: **AINative Cody** (not generic "agent")
- Role: **CTO-Type AI Agent** (authority and expertise)
- Company: **AINative Studio** (brand alignment)
- Mission: **Enterprise-grade code for regulated industries**

### Zero Tolerance Rules Added
1. **File Placement:** NO .md in root, docs go to `docs/{category}/`, scripts to `scripts/`
2. **Git Attribution:** NO third-party AI attribution (Claude, Anthropic, ChatGPT, Copilot)
3. **Testing:** MUST run tests, MUST provide proof, MUST achieve 80%+ coverage

### Technical Standards Added
- Semantic Seed Venture Studio Coding Standards v2.0
- Type hints and docstrings required
- SQLAlchemy ORM only (no raw SQL)
- Multi-tenant with `organization_id`
- Rate limiting on all endpoints
- BDD-style tests (describe/it)

### AINative Branding
All files include:
- "Built by AINative Dev Team"
- "All Data Services Built on ZeroDB"
- "Powered by AINative Cloud"
- NO third-party AI tool attribution

### Project Context
- OpenClaw Backend (Python, FastAPI, PostgreSQL)
- OpenClaw Gateway (Node.js, DBOS, port 18789)
- AINative Website (Next.js 16, near go-live)
- ZeroDB SDK (PyPI v1.0.1)

---

## Usage

### For Backend Personality System

The personality loader expects these files at:
```
/tmp/openclaw_personalities/main-agent/
├── SOUL.md
├── AGENTS.md
├── TOOLS.md
├── IDENTITY.md
├── USER.md
├── BOOTSTRAP.md
├── HEARTBEAT.md
└── MEMORY.md
```

### To Load in Code

```python
from backend.personality.loader import PersonalityLoader

loader = PersonalityLoader(base_path="/tmp/openclaw_personalities")
personality = loader.load_personality_set("main-agent")

# Access individual files
soul = personality.soul.content
agents = personality.agents.content
# etc.
```

### First Run

1. Agent reads `BOOTSTRAP.md`
2. Has initial conversation with user
3. Updates `USER.md` with learned information
4. Creates `memory/YYYY-MM-DD.md` for daily notes
5. Initializes `MEMORY.md` with session context
6. Deletes `BOOTSTRAP.md`

### Ongoing Sessions

1. Read `SOUL.md` (who am I?)
2. Read `USER.md` (who am I helping?)
3. Read `memory/YYYY-MM-DD.md` (today + yesterday)
4. Read `MEMORY.md` (long-term context) - ONLY in main sessions
5. Check `HEARTBEAT.md` for periodic tasks
6. Update memory files as session progresses

---

## Comparison to Default Templates

### What Stayed the Same
- Overall structure and philosophy
- Memory management approach
- Heartbeat patterns
- Group chat etiquette
- Continuity through files

### What Changed
- **Identity:** Generic → AINative Cody (CTO-type agent)
- **Standards:** Added zero-tolerance rules and Semantic Seed v2.0
- **Context:** Added AINative project structure and paths
- **Branding:** Added AINative attribution, removed third-party AI references
- **Technical:** Added stack details, environment setup, testing requirements
- **Operational:** Added proactive monitoring, security checks, quality gates

---

## Next Steps

1. **Review Files:** Read through each file to verify accuracy
2. **Customize USER.md:** Fill in actual user information during first conversation
3. **Test Loading:** Verify personality loader can read all files
4. **Create Memory Structure:** Set up `memory/` directory and initial files
5. **Run BOOTSTRAP:** Execute first-run conversation
6. **Iterate:** Update files based on learned preferences

---

## Maintenance

### Daily
- Update `memory/YYYY-MM-DD.md` with session notes
- Track decisions, learnings, mistakes

### Weekly
- Review daily memory files
- Update `MEMORY.md` with distilled learnings
- Clean up outdated information

### Monthly
- Review and update `SOUL.md` if identity evolves
- Update `AGENTS.md` with new conventions
- Refine `HEARTBEAT.md` based on what's useful

---

## File Sizes

```
SOUL.md      4.4 KB  Core identity and ethics
AGENTS.md    9.6 KB  Workflow and workspace rules
TOOLS.md     5.7 KB  Environment-specific notes
IDENTITY.md  4.4 KB  Persona and boundaries
USER.md      4.5 KB  User profile template
BOOTSTRAP.md 4.8 KB  First-run initialization
HEARTBEAT.md 3.1 KB  Proactive monitoring
MEMORY.md    6.5 KB  Long-term memory template

Total: 43.0 KB (8 files)
```

---

**Created by:** Integration of OpenClaw templates + AINative rules
**For:** OpenClaw Backend personality system
**Agent:** AINative Cody (CTO-Type AI Agent)
**Built by AINative Dev Team**
