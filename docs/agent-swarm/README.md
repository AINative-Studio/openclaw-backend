# AgentSwarm - Complete Documentation Index

**Version:** 2.0
**Last Updated:** December 5, 2025
**Status:** Production Ready

## 📋 Table of Contents

1. [Quick Start](#quick-start)
2. [Architecture](#architecture)
3. [File Structure](#file-structure)
4. [API Endpoints](#api-endpoints)
5. [Storage (ZeroDB)](#storage-zerodb)
6. [Testing](#testing)
7. [Deployment](#deployment)
8. [History](#history)
9. [Related Documentation](#related-documentation)

---

## 🚀 Quick Start

**For AI Agents**: Start here for context on the AgentSwarm system.

### What is AgentSwarm?

AgentSwarm is an 11-stage autonomous software development workflow that uses multiple specialized AI agents to generate complete full-stack applications from a single Product Requirements Document (PRD).

**Key Concept**: All project data (PRDs, code files, test videos) is stored in **ZeroDB** using a `project_id` identifier.

### Essential Reading (in order)
1. [`AGENTSWARM_MASTER_CONTEXT.md`](./AGENTSWARM_MASTER_CONTEXT.md) - **START HERE** - Complete system overview
2. [`AGENTSWARM_HISTORY.md`](./AGENTSWARM_HISTORY.md) - Evolution timeline and version history
3. [`AGENTSWARM_FILE_MAP.md`](./AGENTSWARM_FILE_MAP.md) - Complete file location reference
4. [`AGENTSWARM_REPOSITORY_GUIDE.md`](./AGENTSWARM_REPOSITORY_GUIDE.md) - Infrastructure and deployment
5. [`architecture/AGENT_SWARM_WORKFLOW_V2_PRD.md`](./architecture/AGENT_SWARM_WORKFLOW_V2_PRD.md) - V2 workflow specification

### Quick Command Reference
```bash
# Backend (FastAPI)
cd /Users/aideveloper/core/src/backend
python3 -m uvicorn app.main:app --reload --port 8000

# Frontend (React + Vite)
cd /Users/aideveloper/core/AINative-website
npm run dev

# Run E2E Tests
cd /Users/aideveloper/core/src/backend
pytest tests/e2e/test_agent_swarm_e2e.py -v
```

---

## 🏗️ Architecture

### 11-Stage Workflow

**Preparation Stages (1-6):**
1. **Project Creation** - Initialize ZeroDB project
2. **PRD Upload** - Upload PRD to ZeroDB storage (`/v1/public/{project_id}/database/files`)
3. **Data Model Generation** - LLM generates database schema
4. **Backlog Creation** - Stories with Fibonacci points
5. **Sprint Planning** - Timeline and velocity calculation
6. **Execution Setup** - Single Agent vs. Agent Swarm comparison

**Execution Stages (7-11):**
7. **Launch Swarm** - Start multi-agent orchestration
8. **GitHub Repository** - Create repo with AINative branding
9. **Publish Issues** - Backlog → GitHub Issues (CURRENTLY MISSING)
10. **Feature Development** - TDD workflow (Red → Green → Refactor)
11. **Validation** - Tests, build, video recording to MinIO

### Architecture Documents
- [`architecture/ENHANCED_AGENT_SWARM_ARCHITECTURE.md`](./architecture/ENHANCED_AGENT_SWARM_ARCHITECTURE.md) - Enhanced architecture
- [`architecture/SUB_AGENT_ORCHESTRATOR.md`](./architecture/SUB_AGENT_ORCHESTRATOR.md) - Sub-agent coordination
- [`architecture/AGENT_SWARM_WORKFLOW_V2_PRD.md`](./architecture/AGENT_SWARM_WORKFLOW_V2_PRD.md) - V2 PRD
- [`architecture/multi_agent_swarm_architecture_actual.md`](./architecture/multi_agent_swarm_architecture_actual.md) - Implementation details
- [`storage/AGENT_SWARM_STORAGE_ARCHITECTURE.md`](./storage/AGENT_SWARM_STORAGE_ARCHITECTURE.md) - Storage design

---

## 📁 File Structure

### Backend Files
```
/Users/aideveloper/core/src/backend/
├── AgentSwarm-Workflow.md                    # Official 11-stage workflow spec (2643 lines)
├── app/
│   ├── api/
│   │   ├── api_v1/endpoints/agent_swarms.py  # Main API router (with /github endpoint)
│   │   ├── admin/agent_swarm.py              # Admin endpoints (DEPRECATED - moved to public)
│   │   └── routers/
│   │       ├── public.py                     # Public router (line 26: agent-swarms)
│   │       └── admin.py                      # Admin router
│   ├── agents/swarm/
│   │   ├── agent_swarm.py                    # Core orchestration logic
│   │   ├── api_integration.py                # Kong+Celery integration
│   │   └── application_workflow.py           # Workflow state machine
│   ├── services/
│   │   └── project_github_service.py         # GitHub integration service
│   └── websocket/
│       └── agent_swarm_ws.py                 # Real-time progress updates
├── tests/
│   ├── e2e/test_agent_swarm_e2e.py          # End-to-end tests
│   ├── integration/                          # Integration tests
│   └── E2E_AGENT_SWARM_QUICK_START.md       # Test guide
└── docs/
    ├── guides/AgentSwarm-Workflow.md         # Workflow copy
    ├── implementation/AGENT_SWARM_GITHUB_INTEGRATION_STATUS.md
    └── reports/AGENT_SWARM_PROGRESS_REPORT.md
```

### Frontend Files
```
/Users/aideveloper/core/AINative-website/
├── src/
│   ├── pages/dashboard/AgentSwarmDashboard.tsx  # Main UI (1813 lines)
│   ├── services/AgentSwarmService.ts             # API service (line 267: GitHub)
│   ├── components/
│   │   ├── TimeComparisonCard.tsx
│   │   ├── GitHubIntegrationCard.tsx
│   │   ├── GitHubRepoStatus.tsx
│   │   ├── StageIndicator.tsx
│   │   ├── TDDProgressDisplay.tsx
│   │   ├── CompletionStatistics.tsx
│   │   ├── CompletionTimeSummary.tsx
│   │   └── ExecutionTimer.tsx
│   └── tests/
│       └── e2e/
│           ├── agentswarm-components.spec.ts    # Component tests (7/7 passing)
│           └── github-integration.spec.ts       # GitHub integration tests
└── WORKFLOW_GAP_ANALYSIS.md                     # Current gaps (60% complete)
```

### Documentation Files (Organized Structure)
```
/Users/aideveloper/core/docs/agent-swarm/
├── README.md                                    # This file (master index)
├── AGENTSWARM_MASTER_CONTEXT.md                # Complete context for AI agents
├── AGENTSWARM_HISTORY.md                       # Evolution and timeline
├── AGENTSWARM_FILE_MAP.md                      # Complete file reference
├── AGENTSWARM_REPOSITORY_GUIDE.md              # Infrastructure and deployment
├── architecture/                                # Architecture documentation (4 files)
│   ├── AGENT_SWARM_WORKFLOW_V2_PRD.md
│   ├── ENHANCED_AGENT_SWARM_ARCHITECTURE.md
│   ├── SUB_AGENT_ORCHESTRATOR.md
│   └── multi_agent_swarm_architecture_actual.md
├── api/                                         # API documentation (2 files)
│   ├── AGENT_SWARM_DOWNLOAD_API.md
│   └── ENHANCED_AGENT_SWARM_API_REFERENCE.md
├── guides/                                      # Integration & best practices (5 files)
│   ├── AGENT_SDK_INTEGRATION_GUIDE.md
│   ├── ENHANCED_AGENT_SWARM_BEST_PRACTICES.md
│   ├── ENHANCED_AGENT_SWARM_INTEGRATION_GUIDE.md
│   ├── ENHANCED_AGENT_SWARM_MIGRATION_GUIDE.md
│   └── SUB_AGENT_QUICK_START.md
├── planning/                                    # Enhancement plans (5 files)
├── reports/                                     # Status reports & analyses (10 files)
├── storage/                                     # Storage architecture (4 files)
├── testing/                                     # E2E testing reports (1 file)
├── troubleshooting/                            # Troubleshooting guides (2 files)
├── configuration/                               # Configuration references (1 file)
└── videos/                                      # Video demonstrations (1 file)
```

---

## 🔌 API Endpoints

### Base URLs
- **Development**: `http://localhost:8000`
- **Production**: `https://api.ainative.studio`

### Public Endpoints (`/v1/public/agent-swarms`)

#### Projects
```http
POST   /v1/public/agent-swarms/projects          # Create project
GET    /v1/public/agent-swarms/projects          # List projects
GET    /v1/public/agent-swarms/projects/{id}     # Get project
PATCH  /v1/public/agent-swarms/projects/{id}     # Update project
DELETE /v1/public/agent-swarms/projects/{id}     # Delete project

GET    /v1/public/agent-swarms/projects/{id}/github  # GitHub status (line 675)
```

#### Workflow Execution
```http
POST   /v1/public/agent-swarms/projects/{id}/prd              # Upload PRD
POST   /v1/public/agent-swarms/projects/{id}/ai/generate-data-model
POST   /v1/public/agent-swarms/projects/{id}/ai/generate-backlog
POST   /v1/public/agent-swarms/projects/{id}/ai/generate-sprint-plan
POST   /v1/public/agent-swarms/projects/{id}/launch           # Launch swarm
```

### Admin Endpoints (`/v1/admin/agent-swarm`)
**Note**: Most admin endpoints moved to public router. Legacy admin endpoints deprecated.

---

## 💾 Storage (ZeroDB)

### Key Concept
**All AgentSwarm data uses ZeroDB with `project_id` as the primary identifier.**

### ZeroDB API Base Path
```
/v1/public/{project_id}/database/
```

### File Storage
```http
POST   /v1/public/{project_id}/database/files/upload    # Upload PRD/code
GET    /v1/public/{project_id}/database/files           # List files
GET    /v1/public/{project_id}/database/files/{file_id} # Download file
DELETE /v1/public/{project_id}/database/files/{file_id} # Delete file
```

**Storage Locations**:
- **PRD Files**: ZeroDB files table (`content_type: application/pdf` or `text/markdown`)
- **Generated Code**: ZeroDB files table (`folder: 'generated-code'`)
- **Test Videos**: MinIO object storage (uploaded via ZeroDB API)

### Tables
```http
POST   /v1/public/{project_id}/database/tables           # Create table
GET    /v1/public/{project_id}/database/tables           # List tables
GET    /v1/public/{project_id}/database/tables/{id}/rows # Query rows
```

**AgentSwarm Tables**:
- `agent_swarm_projects` - Project metadata
- `agent_swarm_workflows` - Workflow state
- `agent_swarm_rules` - Custom rules
- `github_integration` - GitHub repo data

### Reference
- [`storage/AGENT_SWARM_STORAGE_ARCHITECTURE.md`](./storage/AGENT_SWARM_STORAGE_ARCHITECTURE.md) - Storage architecture
- [`storage/AGENT_SWARM_STORAGE_STATUS.md`](./storage/AGENT_SWARM_STORAGE_STATUS.md) - Storage status
- [`storage/AGENT_SWARM_CODE_STORAGE.md`](./storage/AGENT_SWARM_CODE_STORAGE.md) - Code storage details
- [`/Users/aideveloper/core/docs/Zero-DB/ZeroDB_Public_Developer_Guide.md`](../Zero-DB/ZeroDB_Public_Developer_Guide.md) - Full ZeroDB API docs

---

## 🧪 Testing

### Test Files

**Backend Tests**:
```bash
/Users/aideveloper/core/src/backend/tests/
├── e2e/test_agent_swarm_e2e.py              # Full workflow test
├── integration/
│   ├── test_github_integration.py           # GitHub integration
│   ├── test_websocket_integration.py        # WebSocket tests
│   └── test_sscs_compliance.py              # Coding standards
└── E2E_AGENT_SWARM_TEST_REPORT.md           # Test report
```

**Frontend Tests**:
```bash
/Users/aideveloper/core/AINative-website/tests/e2e/
├── agentswarm-components.spec.ts            # Component tests (7/7 passing ✅)
├── github-integration.spec.ts               # GitHub UI tests
└── auth.setup.ts                            # Authentication setup
```

### Running Tests

**Backend E2E**:
```bash
cd /Users/aideveloper/core/src/backend
pytest tests/e2e/test_agent_swarm_e2e.py -v
```

**Frontend Playwright**:
```bash
cd /Users/aideveloper/core/AINative-website
npx playwright test tests/e2e/agentswarm-components.spec.ts --project=chromium
```

### Test Documentation
- [`testing/AGENT_SWARM_E2E_TESTING_COMPLETE.md`](./testing/AGENT_SWARM_E2E_TESTING_COMPLETE.md)
- [`/Users/aideveloper/core/src/backend/tests/E2E_AGENT_SWARM_QUICK_START.md`](/Users/aideveloper/core/src/backend/tests/E2E_AGENT_SWARM_QUICK_START.md)

---

## 🚀 Deployment

### Repositories

**Backend**:
- **Repo**: `github.com/relycapital/core` (private)
- **Path**: `/src/backend`
- **Platform**: Railway
- **URL**: `https://api.ainative.studio`

**Frontend**:
- **Repo**: `github.com/relycapital/AINative-website` (private)
- **Path**: `/`
- **Platform**: Vercel
- **URL**: `https://www.ainative.studio`

### Environment Variables

**Backend** (Railway):
```bash
DATABASE_URL=postgresql://...
ZERODB_API_KEY=...
ZERODB_PROJECT_ID=...
MINIO_URL=...
GITHUB_TOKEN=...
```

**Frontend** (Vercel):
```bash
VITE_API_URL=https://api.ainative.studio/v1
VITE_API_BASE_URL=https://api.ainative.studio
```

### Deployment Docs
- [`AGENTSWARM_REPOSITORY_GUIDE.md`](./AGENTSWARM_REPOSITORY_GUIDE.md) - Complete infrastructure guide
- [`reports/AGENT_SWARM_DEPLOYMENT_SUMMARY.md`](./reports/AGENT_SWARM_DEPLOYMENT_SUMMARY.md)
- [`reports/AGENT_DEPLOYMENT_PUSH_SUMMARY.md`](./reports/AGENT_DEPLOYMENT_PUSH_SUMMARY.md)

---

## 📜 History

### Timeline
- **October 2024**: AgentSwarm V1 - Initial implementation
- **November 2024**: V2 Refactor - Kong + Celery integration
- **December 2024**: UI Components - React dashboard complete
- **Current**: Gap Analysis - 60% complete, Stage 9 missing

### Key Milestones
1. **V1 Launch**: Single-stage proof of concept
2. **11-Stage Workflow**: Full SDLC automation
3. **ZeroDB Integration**: Project-based storage
4. **GitHub Integration**: Auto repo creation
5. **UI Dashboard**: React components (8/8 complete)

### Evolution Document
See [`AGENTSWARM_HISTORY.md`](./AGENTSWARM_HISTORY.md) for complete evolution timeline.

---

## 📚 Related Documentation

### In This Folder (`/docs/agent-swarm/`)
- [`AGENTSWARM_MASTER_CONTEXT.md`](./AGENTSWARM_MASTER_CONTEXT.md) - **START HERE**
- [`AGENTSWARM_HISTORY.md`](./AGENTSWARM_HISTORY.md) - Evolution timeline
- [`AGENTSWARM_FILE_MAP.md`](./AGENTSWARM_FILE_MAP.md) - File location reference
- [`AGENTSWARM_REPOSITORY_GUIDE.md`](./AGENTSWARM_REPOSITORY_GUIDE.md) - Infrastructure guide

### Subdirectories
- **architecture/** - Architecture specifications (4 files)
- **api/** - API documentation (2 files)
- **guides/** - Integration & best practices (5 files)
- **planning/** - Enhancement plans (5 files)
- **reports/** - Status reports (10 files)
- **storage/** - Storage architecture (4 files)
- **testing/** - Test reports (1 file)
- **troubleshooting/** - Troubleshooting guides (2 files)
- **configuration/** - Configuration references (1 file)
- **videos/** - Video demonstrations (1 file)

### Backend Docs (`/src/backend/`)
- [`AgentSwarm-Workflow.md`](/Users/aideveloper/core/src/backend/AgentSwarm-Workflow.md) - **Official 2643-line spec**
- `docs/guides/` - Implementation guides
- `docs/reports/` - Progress reports
- `tests/` - Test documentation

### Frontend Docs (`/AINative-website/`)
- [`WORKFLOW_GAP_ANALYSIS.md`](/Users/aideveloper/core/AINative-website/WORKFLOW_GAP_ANALYSIS.md) - **Current status**
- `src/components/` - Component README files

### External References
- [ZeroDB Developer Guide](../Zero-DB/ZeroDB_Public_Developer_Guide.md)
- [SSCS Coding Standards](https://docs.google.com/document/d/1example) - Semantic Seed standards

---

## 🎯 Current Status (December 2025)

### Completion: 60%
- ✅ Frontend UI: 100% (8/8 components integrated)
- ⚠️ Backend Integration: 30%
- ❌ GitHub Workflow: 20%
- ❌ SSCS Compliance: 10%

### Critical Gaps
1. ❌ **Stage 9: Backlog → GitHub Issues** - MISSING (blocks workflow)
2. ❌ **SSCS Compliance** - Claude branding in commits (standards violation)
3. ❌ **WebSocket Updates** - No real-time progress
4. ⚠️ **GitHub Setup** - Incomplete (no branches, README)

See [`/AINative-website/WORKFLOW_GAP_ANALYSIS.md`](/Users/aideveloper/core/AINative-website/WORKFLOW_GAP_ANALYSIS.md) for detailed gap analysis.

---

## 📞 Support

**For AI Agents**: If you encounter issues understanding AgentSwarm:
1. Read [`AGENTSWARM_MASTER_CONTEXT.md`](./AGENTSWARM_MASTER_CONTEXT.md) first
2. Check [`AGENTSWARM_FILE_MAP.md`](./AGENTSWARM_FILE_MAP.md) for file locations
3. Review official spec: [`/src/backend/AgentSwarm-Workflow.md`](/Users/aideveloper/core/src/backend/AgentSwarm-Workflow.md)

**For Developers**:
- GitHub Issues: `github.com/relycapital/core/issues`
- Email: dev@ainative.studio

---

**Last Updated**: December 5, 2025
**Maintained By**: AINative Studio Engineering Team
