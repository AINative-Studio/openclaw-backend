# AgentSwarm - Complete Master Context for AI Agents

**Document Type**: Master Context & Onboarding
**Audience**: AI Agents, Developers, New Team Members
**Last Updated**: December 5, 2025
**Status**: Authoritative Reference

---

## 🎯 START HERE - Essential Context

**If you are an AI agent assigned to work on AgentSwarm, read this document FIRST before making any code changes.**

### What is AgentSwarm?

AgentSwarm is an **autonomous multi-agent software development platform** that transforms a Product Requirements Document (PRD) into a complete, working full-stack application through an 11-stage automated workflow.

**Key Concept**: Multiple specialized AI agents (Architect, Backend, Frontend, QA, DevOps) work in parallel to build professional-grade applications following industry best practices (Agile, TDD, CI/CD).

### Quick Stats (December 2025)

- **Status**: 60% Complete (Production-ready for stages 1-8)
- **Frontend**: 100% (8/8 components, 7/7 tests passing ✅)
- **Backend**: 70% (Core working, Stage 9 missing ❌)
- **GitHub Integration**: 30% (Repo creation works, issue import missing)
- **ZeroDB Integration**: 60% (File storage works, vectors/embeddings/RLHF not integrated)

### Critical Gap (BLOCKER)

**Stage 9: Import Backlog as GitHub Issues** is NOT implemented. This blocks the complete workflow. Users cannot proceed past Stage 8.

---

## 📋 Table of Contents

1. [How AgentSwarm Works](#how-agentswarm-works)
2. [The 11-Stage Workflow](#the-11-stage-workflow)
3. [Technical Architecture](#technical-architecture)
4. [Critical Files Reference](#critical-files-reference)
5. [Data Storage (ZeroDB)](#data-storage-zerodb)
6. [GitHub Integration](#github-integration)
7. [Current Gaps & Issues](#current-gaps--issues)
8. [Common Development Tasks](#common-development-tasks)
9. [Testing Strategy](#testing-strategy)
10. [Troubleshooting](#troubleshooting)
11. [Quick Reference Commands](#quick-reference-commands)

---

## 🔄 How AgentSwarm Works

### The Big Picture

```
User Upload PRD
      ↓
Planning Phase (Stages 1-6)
  → Data Model Generation
  → Backlog Creation
  → Sprint Planning
      ↓
GitHub Setup (Stages 7-8)
  → Create Repository
  → Commit Documentation
      ↓
Execution Phase (Stages 9-11)
  → ❌ Import Issues (MISSING)
  → Launch Multi-Agent Swarm
  → Generate Code in Parallel
      ↓
Complete Application in GitHub Repo
```

### Multi-Agent Architecture

**Coordinator Agent** (Extended Thinking - Claude 3.7):
- Plans the overall workflow
- Breaks down tasks for sub-agents
- Synthesizes results

**Specialized Sub-Agents** (Claude 3.5 Sonnet):
1. **Architect Agent**: Project structure, dependencies, configuration
2. **Backend Agent(s)**: API endpoints, business logic, database integration
3. **Frontend Agent(s)**: UI components, state management, routing
4. **QA Agent**: Test writing, code review, quality validation
5. **DevOps Agent**: CI/CD, deployment, monitoring setup

**Parallelization Model**:
- User chooses agent count (1, 3, 6, or 12 agents)
- Agents work simultaneously on different features
- Each agent has isolated workspace (`/tmp/dagger-workspace-{agent-id}/`)
- Results merged by coordinator

---

## 📊 The 11-Stage Workflow

### **Official Specification**:
`/Users/aideveloper/core/src/backend/AgentSwarm-Workflow.md` (2643 lines)

### Stage Overview

#### **Preparation Stages (1-6)**

**Stage 1: Project Creation**
- **File**: `app/api/api_v1/endpoints/agent_swarms.py` (line 123)
- **Action**: Initialize ZeroDB project
- **Output**: `project_id` (UUID)
- **Status**: ✅ Working

**Stage 2: PRD Upload**
- **File**: `app/api/api_v1/endpoints/agent_swarms.py` (line 234)
- **Action**: Upload PRD file to ZeroDB storage
- **API**: `POST /v1/public/{project_id}/database/files/upload`
- **Storage**: MinIO bucket (via ZeroDB)
- **Status**: ✅ Working

**Stage 3: Data Model Generation**
- **File**: `app/agents/swarm/application_workflow.py` (line 456)
- **Action**: LLM analyzes PRD and generates database schema
- **Default**: ZeroDB NoSQL tables (NOT PostgreSQL)
- **Output**: JSON schema saved to ZeroDB
- **Status**: ✅ Working

**Stage 4: Backlog Creation**
- **File**: `app/agents/swarm/application_workflow.py` (line 589)
- **Action**: Generate Agile backlog (Epics → Stories → Tasks)
- **Format**: Markdown with Fibonacci story points
- **Output**: `backlog.md` stored in ZeroDB
- **Status**: ✅ Working

**Stage 5: Sprint Planning**
- **File**: `app/agents/swarm/application_workflow.py` (line 723)
- **Action**: Create sprint timeline based on agent count
- **Formula**: `duration_days = total_story_points / (agent_count * 5 SP/day)`
- **Output**: `sprint_plan.md` with agent assignments
- **Status**: ✅ Working

**Stage 6: Execution Setup**
- **Action**: Display comparison (Single Agent vs Agent Swarm)
- **UI Component**: `TimeComparisonCard.tsx`
- **Status**: ✅ Working

#### **GitHub Setup Stages (7-8)**

**Stage 7: GitHub Repository Creation**
- **File**: `app/services/project_github_service.py` (line 45)
- **Action**: Create GitHub repo, initialize structure
- **Requirements**: User provides GitHub PAT
- **Created**: `.gitignore`, `README.md`, `LICENSE`, `docs/` folder
- **Status**: ⚠️ Partial (repo created, but incomplete README)

**Stage 8: Documentation Commit**
- **File**: `app/services/project_github_service.py` (line 156)
- **Action**: Commit all `.md` files to `docs/` folder
- **Files**: `PRD.md`, `DATA_MODEL.md`, `BACKLOG.md`, `SPRINT_PLAN.md`
- **Status**: ⚠️ Partial (commits work, but no proper git workflow)

#### **Execution Stages (9-11)**

**Stage 9: Import Backlog as GitHub Issues** ❌ **MISSING**
- **File**: NOT IMPLEMENTED
- **Action**: Parse `backlog.md` and create GitHub Issues
- **Requirements**:
  - Convert Epics to issues with label `epic`
  - Convert User Stories to issues with labels `user-story`, `frontend`, `backend`
  - Add story points to issue body
  - Create milestones for each sprint
  - Link issues with dependencies
- **Blocker**: This is the #1 priority gap
- **Impact**: Workflow cannot proceed past Stage 8

**Stage 10: Launch Agent Swarm**
- **File**: `app/agents/swarm/agent_swarm.py` (line 234)
- **Action**: Spawn N agents to work in parallel
- **Process**:
  1. Load sprint plan and GitHub issues
  2. Assign issues to agents
  3. Create isolated workspaces
  4. Start parallel execution
- **Status**: ⚠️ Partial (agent execution works, but no GitHub issue assignment)

**Stage 11: Code Generation & Validation**
- **File**: `app/agents/swarm/swarm_agent.py` (line 89)
- **Action**: Each agent generates code, tests, commits to GitHub
- **Workflow** (per agent):
  1. Clone repo to workspace
  2. Create feature branch `feature/{issue-number}-{slug}`
  3. Generate code following custom rules
  4. Run TDD cycle (Red → Green → Refactor)
  5. Commit changes
  6. Push to GitHub
  7. Create Pull Request
  8. Upload code to MinIO storage
- **Status**: ✅ Working (but needs GitHub issue integration)

---

## 🏗️ Technical Architecture

### Technology Stack

**Backend**:
- **Framework**: FastAPI (Python 3.11+)
- **AI Provider**: Anthropic Claude (currently legacy API, needs migration to Messages API)
- **Task Queue**: Celery + Redis
- **API Gateway**: Kong
- **Database**: PostgreSQL (for metadata) + ZeroDB (for project data)
- **File Storage**: MinIO (via ZeroDB API)

**Frontend**:
- **Framework**: React 18 + Vite
- **UI Library**: shadcn/ui (Tailwind CSS)
- **State Management**: React Context + Hooks
- **API Client**: Custom service layer (`AgentSwarmService.ts`)
- **Testing**: Playwright (E2E)

**Infrastructure**:
- **Backend Deployment**: Railway (https://api.ainative.studio)
- **Frontend Deployment**: Vercel (https://www.ainative.studio)
- **Version Control**: GitHub (private repos)
- **CI/CD**: GitHub Actions

### System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (React + Vite)                   │
│                  https://www.ainative.studio                 │
│                                                              │
│  Components:                                                 │
│  ├── AgentSwarmDashboard.tsx (Main UI)                      │
│  ├── TimeComparisonCard.tsx                                 │
│  ├── GitHubIntegrationCard.tsx                              │
│  └── ... (8 components total)                               │
└───────────────────────┬──────────────────────────────────────┘
                        │ REST API + WebSocket
                        ↓
┌─────────────────────────────────────────────────────────────┐
│              Backend (FastAPI + Celery)                      │
│                https://api.ainative.studio                   │
│                                                              │
│  API Router:                                                 │
│  /v1/public/agent-swarms/*                                  │
│                                                              │
│  Core Services:                                              │
│  ├── application_workflow.py (Workflow state machine)       │
│  ├── agent_swarm.py (Agent orchestration)                   │
│  ├── project_github_service.py (GitHub integration)         │
│  └── kong_celery_integration.py (Async tasks)               │
└───────────┬────────────────────────┬────────────────────────┘
            │                        │
            ↓                        ↓
┌─────────────────────┐  ┌──────────────────────────────────┐
│   ZeroDB Platform   │  │      GitHub API                  │
│                     │  │                                  │
│  - NoSQL Tables     │  │  - Repo Creation                │
│  - File Storage     │  │  - Commits                      │
│  - Vectors (future) │  │  - Issues (Stage 9 - MISSING)   │
│  - Embeddings       │  │  - Pull Requests                │
│  - RLHF             │  │  - Webhooks                     │
└─────────────────────┘  └──────────────────────────────────┘
```

### Data Flow

**User Uploads PRD** →
`POST /v1/public/agent-swarms/projects/{id}/prd`
→ **Stored in ZeroDB Files**
→ `GET /v1/public/{project_id}/database/files`

**LLM Generates Data Model** →
**Stored in ZeroDB Tables**
→ `POST /v1/public/{project_id}/database/tables`

**Agents Generate Code** →
**Committed to GitHub**
→ **Uploaded to MinIO**
→ `POST /v1/public/{project_id}/database/files/upload`

---

## 📁 Critical Files Reference

### Backend Core Files

**Main API Router**:
```
/src/backend/app/api/api_v1/endpoints/agent_swarms.py
├── Line 123: POST /projects (Create project)
├── Line 234: POST /projects/{id}/prd (Upload PRD)
├── Line 345: POST /projects/{id}/ai/generate-data-model
├── Line 456: POST /projects/{id}/ai/generate-backlog
├── Line 567: POST /projects/{id}/ai/generate-sprint-plan
├── Line 675: GET /projects/{id}/github (GitHub status)
└── Line 789: POST /projects/{id}/launch (Launch swarm)
```

**Workflow State Machine**:
```
/src/backend/app/agents/swarm/application_workflow.py (325,902 bytes!)
├── WorkflowStage enum (stages 1-11)
├── generate_data_model() → Stage 3
├── generate_backlog() → Stage 4
├── generate_sprint_plan() → Stage 5
└── execute_workflow() → Main orchestration
```

**Agent Orchestration**:
```
/src/backend/app/agents/swarm/agent_swarm.py
├── AgentSwarm class
├── assign_agents_to_tasks()
├── execute_parallel()
└── monitor_progress()
```

**GitHub Service**:
```
/src/backend/app/services/project_github_service.py
├── create_repository()
├── commit_documentation()
├── create_branch()
└── create_pull_request()
```

**Sub-Agent Orchestrator**:
```
/src/backend/app/agents/swarm/sub_agent_orchestrator.py
├── SubAgentOrchestrator class
├── plan_and_execute() → Coordinator with extended thinking
├── _execute_sub_agent_task() → Isolated sub-agent contexts
└── _synthesize_results()
```

### Frontend Core Files

**Main Dashboard**:
```
/AINative-website/src/pages/dashboard/AgentSwarmDashboard.tsx (1813 lines)
├── Workflow stepper UI
├── Stage progress tracking
├── WebSocket connection (planned)
└── Agent execution monitoring
```

**API Service Layer**:
```
/AINative-website/src/services/AgentSwarmService.ts
├── All API endpoint wrappers
├── Line 267: getGitHubStatus()
├── Error handling
└── Request/response typing
```

**UI Components** (all in `/src/components/`):
1. `TimeComparisonCard.tsx` - Single vs swarm comparison
2. `GitHubIntegrationCard.tsx` - GitHub status
3. `GitHubRepoStatus.tsx` - Repo health
4. `StageIndicator.tsx` - Stage progress
5. `TDDProgressDisplay.tsx` - TDD metrics
6. `CompletionStatistics.tsx` - Project stats
7. `CompletionTimeSummary.tsx` - Time tracking
8. `ExecutionTimer.tsx` - Real-time timer

### Test Files

**Backend E2E Tests**:
```
/src/backend/tests/e2e/test_agent_swarm_e2e.py
└── Full workflow test (stages 1-11)
```

**Frontend E2E Tests**:
```
/AINative-website/tests/e2e/agentswarm-components.spec.ts
└── 7/7 tests passing ✅
```

### Documentation Files

**Official Workflow Spec**:
```
/src/backend/AgentSwarm-Workflow.md (2643 lines)
└── Authoritative specification for all 11 stages
```

**Agent Swarm Docs** (`/docs/agent-swarm/`):
```
├── README.md (Master index)
├── AGENTSWARM_MASTER_CONTEXT.md (This file - START HERE)
├── AGENTSWARM_HISTORY.md (Complete evolution timeline)
├── AGENTSWARM_FILE_MAP.md (File location reference)
├── AGENTSWARM_REPOSITORY_GUIDE.md (Infrastructure guide)
├── architecture/ (4 files)
├── api/ (2 files)
├── guides/ (5 files)
├── storage/ (4 files)
├── testing/ (1 file)
└── ... (36 files total)
```

---

## 💾 Data Storage (ZeroDB)

### Key Concept: Project-Based Isolation

**ALL AgentSwarm data uses ZeroDB with `project_id` as the primary identifier.**

Every API call to ZeroDB is scoped to a project:
```
/v1/public/{project_id}/database/*
```

### ZeroDB Storage Locations

**1. File Storage (MinIO)**:
```
POST /v1/public/{project_id}/database/files/upload
GET  /v1/public/{project_id}/database/files
GET  /v1/public/{project_id}/database/files/{file_id}
DELETE /v1/public/{project_id}/database/files/{file_id}
```

**What's Stored**:
- PRD files (`.md`, `.pdf`)
- Generated code archives (`.zip`, `.tar.gz`)
- Test videos (`.mp4`) from Stage 11 validation
- Data model schemas (`.json`)
- Sprint plans (`.md`)

**2. NoSQL Tables**:
```
POST /v1/public/{project_id}/database/tables
GET  /v1/public/{project_id}/database/tables
POST /v1/public/{project_id}/database/tables/{table_name}/rows
GET  /v1/public/{project_id}/database/tables/{table_name}/rows
```

**AgentSwarm Tables**:
- `agent_swarm_projects` - Project metadata
- `agent_swarm_workflows` - Workflow state
- `agent_swarm_rules` - Custom coding rules
- `github_integration` - GitHub repo data
- `sprint_plans` - Sprint planning data

**3. Vector Storage (NOT YET INTEGRATED)**:
```
POST /v1/public/{project_id}/database/vectors/upsert
POST /v1/public/{project_id}/database/vectors/search
```

**Planned Use Cases**:
- Semantic code search
- Similar component finding
- Duplicate code detection
- Context retrieval for agents

**4. Memory Management (NOT YET INTEGRATED)**:
```
POST /v1/public/{project_id}/database/memory
GET  /v1/public/{project_id}/database/memory/search
```

**Planned Use Cases**:
- Agent conversation history
- Learned patterns from previous projects
- User preferences

**5. RLHF Feedback (NOT YET INTEGRATED)**:
```
POST /v1/public/{project_id}/database/rlhf/interactions
GET  /v1/public/{project_id}/database/rlhf/stats
```

**Planned Use Cases**:
- User feedback on generated code
- Thumbs up/down on workflow steps
- Model improvement data

### Complete ZeroDB Reference

See: `/docs/Zero-DB/ZeroDB_Public_Developer_Guide.md` for all 42+ endpoints

---

## 🐙 GitHub Integration

### Current State (30% Complete)

**What Works** ✅:
1. Repository creation via GitHub API
2. Basic commits to `main` branch
3. Status endpoint to check repo health

**What's Missing** ❌:
1. **Stage 9: Backlog → GitHub Issues** (CRITICAL BLOCKER)
2. Branch strategy (no feature branches)
3. Pull request creation
4. Code review automation
5. GitHub Actions workflow generation
6. Milestone creation
7. Label management
8. Issue assignment to agents

### GitHub API Integration

**Service File**: `/src/backend/app/services/project_github_service.py`

**Key Methods**:
```python
class ProjectGitHubService:
    def create_repository(self, repo_name: str, description: str)
        # Creates GitHub repo under user's account
        # Requires: GitHub PAT with repo scope

    def commit_documentation(self, repo_name: str, files: Dict[str, str])
        # Commits multiple .md files to docs/ folder

    def create_branch(self, repo_name: str, branch_name: str)
        # Creates feature branch from main

    def create_pull_request(self, repo_name: str, branch: str, title: str, body: str)
        # Creates PR for agent-generated code
```

**GitHub PAT Requirements**:
- Scope: `repo` (full control of private repositories)
- Scope: `workflow` (update GitHub Actions workflows)
- Scope: `admin:org` (if using organization repos)

**Security Note**: PAT is encrypted before storing in database

### Stage 9 Implementation Requirements

**Input**: `backlog.md` from Stage 4
**Output**: GitHub Issues created in repo

**Pseudocode**:
```python
async def import_backlog_to_github(project_id: str, repo_name: str):
    # 1. Fetch backlog from ZeroDB
    backlog = await get_file_from_zerodb(project_id, "backlog.md")

    # 2. Parse backlog markdown
    epics, stories = parse_backlog(backlog)

    # 3. Create GitHub milestones for sprints
    for sprint in sprint_plan.sprints:
        await github.create_milestone(
            repo_name,
            title=f"Sprint {sprint.number}",
            description=sprint.description,
            due_on=sprint.end_date
        )

    # 4. Create GitHub labels
    labels = ["epic", "user-story", "bug", "enhancement", "frontend", "backend", "qa"]
    for label in labels:
        await github.create_label(repo_name, label)

    # 5. Create Epic issues
    for epic in epics:
        issue = await github.create_issue(
            repo_name,
            title=f"Epic: {epic.title}",
            body=epic.description,
            labels=["epic"] + epic.tags
        )
        epic.github_issue_number = issue.number

    # 6. Create User Story issues
    for story in stories:
        issue = await github.create_issue(
            repo_name,
            title=story.title,
            body=format_user_story(story),
            labels=["user-story"] + story.tags,
            milestone=story.sprint_number,
            assignees=get_assigned_agents(story)
        )
        story.github_issue_number = issue.number

        # Link to parent epic
        await github.add_issue_comment(
            repo_name,
            issue.number,
            f"Part of #{epic.github_issue_number}"
        )

    return {"epics": len(epics), "stories": len(stories)}
```

**User Story Format** (in issue body):
```markdown
**As a** user
**I want** to create a new task
**So that** I can track my work

## Acceptance Criteria
- [ ] User can enter task title (required, max 200 chars)
- [ ] User can enter task description (optional)
- [ ] Task is saved to ZeroDB
- [ ] User sees confirmation message

## Story Points
3

## Technical Tasks
- Implement POST /api/tasks endpoint
- Create TaskService with ZeroDB integration
- Build CreateTaskForm component (React)
- Add form validation
- Write unit + integration tests

## Sprint
Sprint 1

## Agent Assignment
- Backend: @backend-agent-1
- Frontend: @frontend-agent-2
```

---

## ⚠️ Current Gaps & Issues

### Priority 1: Blockers (Must Fix)

**1. Stage 9: GitHub Issue Import - MISSING**
- **Impact**: Users cannot proceed past Stage 8
- **Effort**: 3-5 days
- **Complexity**: Medium
- **Dependencies**: GitHub API, backlog parser
- **File to Create**: `/src/backend/app/services/github_issue_importer.py`

**2. Anthropic Messages API Migration - CRITICAL**
- **Impact**: Using deprecated Completion API
- **Effort**: 5-7 days
- **Complexity**: High
- **Current**: `/app/providers/anthropic_provider.py` (legacy)
- **Target**: Messages API with tool use
- **Dependencies**: Need to register ZeroDB tools

**3. Sub-Agent Context Isolation - HIGH**
- **Impact**: Agents share context window (memory leak)
- **Effort**: 3-4 days
- **Complexity**: Medium
- **Solution**: Implement Anthropic Agent SDK
- **File**: `/app/agents/swarm/agent_sdk_integration.py`

### Priority 2: Important (Should Fix)

**4. ZeroDB Full Integration - 60% Complete**
- **Missing**: Vectors, embeddings, RLHF, memory
- **Impact**: Not leveraging ZeroDB's full capabilities
- **Effort**: 7-10 days
- **Complexity**: Medium

**5. RLHF Feedback UI - NOT IMPLEMENTED**
- **Missing**: Thumbs up/down components
- **Impact**: No user feedback collection
- **Effort**: 2-3 days
- **Complexity**: Low
- **Files**: Need `RLHFFeedback.tsx` component

**6. SSCS Coding Standards - NOT ENFORCED**
- **Issue**: Agents use Claude branding instead of AINative
- **Impact**: Generated commits don't follow standards
- **Effort**: 1-2 days
- **Fix**: Update commit message templates

### Priority 3: Nice to Have

**7. WebSocket Real-Time Updates**
- **Status**: Planned but not implemented
- **Impact**: No live progress updates in UI
- **Effort**: 2-3 days

**8. Advanced GitHub Workflow**
- **Missing**: Branch protection, code review, CI/CD
- **Impact**: Basic git workflow only
- **Effort**: 3-5 days

---

## 🛠️ Common Development Tasks

### Task 1: Add a New Workflow Stage

**Example**: Adding Stage 12 (Deployment)

1. **Update Workflow Enum**:
```python
# File: app/agents/swarm/application_workflow.py
class WorkflowStage(str, Enum):
    # ... existing stages
    DEPLOYMENT = "deployment"  # Stage 12
```

2. **Add Stage Handler**:
```python
async def execute_deployment(self, project_id: str):
    """Stage 12: Deploy application to production"""
    # Implementation
    pass
```

3. **Update API Router**:
```python
# File: app/api/api_v1/endpoints/agent_swarms.py
@router.post("/projects/{project_id}/deploy")
async def deploy_application(project_id: str):
    result = await workflow.execute_deployment(project_id)
    return result
```

4. **Update Frontend**:
```tsx
// File: src/pages/dashboard/AgentSwarmDashboard.tsx
const stages = [
  // ... existing stages
  { number: 12, name: "Deployment", status: "pending" }
];
```

5. **Add Tests**:
```python
# File: tests/e2e/test_agent_swarm_e2e.py
async def test_stage_12_deployment(client):
    response = await client.post(f"/v1/public/agent-swarms/projects/{project_id}/deploy")
    assert response.status_code == 200
```

### Task 2: Integrate a New ZeroDB Endpoint

**Example**: Adding semantic search

1. **Create Service Method**:
```python
# File: app/services/zerodb_integration_service.py
async def semantic_search(self, project_id: str, query: str):
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{self.base_url}/v1/public/{project_id}/embeddings/search",
            headers=self.headers,
            json={"query": query, "top_k": 10}
        ) as response:
            return await response.json()
```

2. **Register as Anthropic Tool** (when Messages API is migrated):
```python
# File: app/agents/swarm/tools/zerodb_tools.py
SEMANTIC_SEARCH_TOOL = {
    "name": "zerodb_semantic_search",
    "description": "Search code using natural language",
    "input_schema": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "query": {"type": "string"}
        },
        "required": ["project_id", "query"]
    }
}
```

3. **Use in Agent**:
```python
# File: app/agents/swarm/swarm_agent.py
results = await self.zerodb.semantic_search(
    project_id,
    "Find all React components with form validation"
)
```

### Task 3: Add a New UI Component

**Example**: Adding RLHF feedback buttons

1. **Create Component**:
```tsx
// File: src/components/RLHFFeedback.tsx
export function RLHFFeedback({ stepNumber, prompt, response, projectId }) {
  const [rating, setRating] = useState<number | null>(null);

  const handleFeedback = async (thumbsUp: boolean) => {
    await apiClient.post(`/v1/public/${projectId}/database/rlhf/interactions`, {
      prompt,
      response,
      rating: thumbsUp ? 1 : -1
    });
    setRating(thumbsUp ? 1 : -1);
  };

  return (
    <div className="flex gap-2">
      <Button onClick={() => handleFeedback(true)}>
        <ThumbsUp />
      </Button>
      <Button onClick={() => handleFeedback(false)}>
        <ThumbsDown />
      </Button>
    </div>
  );
}
```

2. **Add to Dashboard**:
```tsx
// File: src/pages/dashboard/AgentSwarmDashboard.tsx
import { RLHFFeedback } from '@/components/RLHFFeedback';

// In render:
<RLHFFeedback
  stepNumber={3}
  prompt="Generate data model"
  response={dataModel}
  projectId={projectId}
/>
```

3. **Add Tests**:
```typescript
// File: tests/e2e/rlhf-feedback.spec.ts
test('should submit thumbs up feedback', async ({ page }) => {
  await page.click('[data-testid="thumbs-up"]');
  await expect(page.locator('.success-message')).toBeVisible();
});
```

---

## 🧪 Testing Strategy

### Backend Testing

**Unit Tests**:
```bash
pytest tests/unit/ -v
```

**Integration Tests**:
```bash
pytest tests/integration/ -v
```

**E2E Tests** (Full Workflow):
```bash
pytest tests/e2e/test_agent_swarm_e2e.py -v
```

**Test Coverage Goal**: >80%

### Frontend Testing

**Component Tests** (Playwright):
```bash
cd /Users/aideveloper/core/AINative-website
npx playwright test tests/e2e/agentswarm-components.spec.ts --project=chromium
```

**Current Status**: 7/7 tests passing ✅

**Test Suite**:
1. TimeComparisonCard renders correctly
2. GitHubIntegrationCard shows repo status
3. StageIndicator updates progress
4. TDDProgressDisplay shows metrics
5. CompletionStatistics accurate
6. ExecutionTimer counts correctly
7. Full workflow integration

### Manual Testing Checklist

Before deploying:
- [ ] Create new project
- [ ] Upload PRD
- [ ] Generate data model (verify ZeroDB default)
- [ ] Generate backlog (verify story points)
- [ ] Generate sprint plan (verify agent count calculation)
- [ ] Create GitHub repo (verify structure)
- [ ] Commit docs (verify all .md files)
- [ ] ❌ Import issues (NOT IMPLEMENTED - skip)
- [ ] Launch swarm (verify parallel execution)
- [ ] Check MinIO storage (verify code uploaded)
- [ ] Verify GitHub commits
- [ ] Check UI updates in real-time

---

## 🔧 Troubleshooting

### Issue: "GitHub PAT Invalid"

**Symptoms**: Repo creation fails with 401 Unauthorized

**Causes**:
1. PAT expired
2. PAT missing required scopes
3. PAT not properly encrypted/decrypted

**Solution**:
```python
# Verify PAT scopes
import requests

response = requests.get(
    "https://api.github.com/user",
    headers={"Authorization": f"Bearer {pat}"}
)

if response.status_code == 200:
    print("PAT valid")
    scopes = response.headers.get("X-OAuth-Scopes", "").split(", ")
    if "repo" not in scopes:
        print("ERROR: Missing 'repo' scope")
```

### Issue: "ZeroDB File Upload Fails"

**Symptoms**: 500 error when uploading PRD

**Causes**:
1. MinIO service down
2. Bucket not created
3. File size exceeds limit

**Solution**:
```bash
# Check MinIO status
curl https://api.ainative.studio/v1/public/health/minio

# Verify bucket exists
curl -H "X-API-Key: $ZERODB_API_KEY" \
  https://api.ainative.studio/v1/public/$PROJECT_ID/database/files

# Check file size (<50MB limit)
ls -lh prd.md
```

### Issue: "Agent Execution Hangs"

**Symptoms**: Agent stuck in "executing" state, no progress

**Causes**:
1. Anthropic API rate limit hit
2. Celery worker crashed
3. Infinite loop in agent logic

**Solution**:
```bash
# Check Celery worker status
celery -A app.celery_app inspect active

# Check Anthropic API rate limits
curl https://api.anthropic.com/v1/rate-limits \
  -H "x-api-key: $ANTHROPIC_API_KEY"

# Kill stuck task
celery -A app.celery_app control revoke <task_id> --terminate
```

### Issue: "Frontend 404 on API Calls"

**Symptoms**: API calls fail with 404 Not Found

**Causes**:
1. API endpoint moved/renamed
2. Environment variable wrong
3. CORS issue

**Solution**:
```javascript
// Check API base URL
console.log(import.meta.env.VITE_API_BASE_URL);
// Should be: https://api.ainative.studio

// Verify endpoint exists
fetch('https://api.ainative.studio/v1/public/agent-swarms/projects')
  .then(res => console.log(res.status))
  .catch(err => console.error(err));
```

---

## ⚡ Quick Reference Commands

### Backend Development

**Start Backend Server**:
```bash
cd /Users/aideveloper/core/src/backend
python3 -m uvicorn app.main:app --reload --port 8000
```

**Start Celery Worker**:
```bash
cd /Users/aideveloper/core/src/backend
celery -A app.celery_app worker --loglevel=info
```

**Run Migrations**:
```bash
cd /Users/aideveloper/core/src/backend
alembic upgrade head
```

**Create Migration**:
```bash
alembic revision --autogenerate -m "Add new table"
```

### Frontend Development

**Start Dev Server**:
```bash
cd /Users/aideveloper/core/AINative-website
npm run dev
```

**Run Tests**:
```bash
npx playwright test
```

**Build for Production**:
```bash
npm run build
```

### Database

**Connect to PostgreSQL**:
```bash
psql $DATABASE_URL
```

**Query Projects**:
```sql
SELECT id, name, status FROM agent_swarm_projects ORDER BY created_at DESC LIMIT 10;
```

### ZeroDB

**List Project Files**:
```bash
curl -H "X-API-Key: $ZERODB_API_KEY" \
  https://api.ainative.studio/v1/public/$PROJECT_ID/database/files
```

**Upload File**:
```bash
curl -X POST -H "X-API-Key: $ZERODB_API_KEY" \
  -F "file=@prd.md" \
  https://api.ainative.studio/v1/public/$PROJECT_ID/database/files/upload
```

### GitHub

**Create Repo**:
```bash
gh repo create my-project --public --description "Generated by AgentSwarm"
```

**List Issues**:
```bash
gh issue list --repo my-project
```

**Create Issue**:
```bash
gh issue create --title "Epic: User Management" \
  --body "..." \
  --label epic \
  --repo my-project
```

---

## 📚 Additional Resources

### Documentation

- **Official Workflow**: `/src/backend/AgentSwarm-Workflow.md` (2643 lines)
- **History**: `/docs/agent-swarm/AGENTSWARM_HISTORY.md`
- **File Map**: `/docs/agent-swarm/AGENTSWARM_FILE_MAP.md`
- **Repository Guide**: `/docs/agent-swarm/AGENTSWARM_REPOSITORY_GUIDE.md`
- **ZeroDB Guide**: `/docs/Zero-DB/ZeroDB_Public_Developer_Guide.md`

### External References

- **Anthropic Messages API**: https://docs.anthropic.com/en/api/messages
- **Anthropic Tool Use**: https://docs.anthropic.com/en/docs/build-with-claude/tool-use
- **Anthropic Agent SDK**: https://docs.anthropic.com/en/docs/claude-code/sub-agents
- **GitHub API**: https://docs.github.com/en/rest
- **FastAPI**: https://fastapi.tiangolo.com/
- **React**: https://react.dev/

### Support

- **GitHub Issues**: `github.com/relycapital/core/issues`
- **Internal Slack**: `#agent-swarm-dev`
- **Email**: dev@ainative.studio

---

## 🎯 Summary for AI Agents

**If you are an AI agent working on AgentSwarm:**

1. **Read This Document First** - You now have complete context
2. **Check Current Status** - We are 60% complete, Stage 9 is MISSING
3. **Priority Task** - Implement Stage 9 (GitHub issue import)
4. **Follow the Workflow** - Use `/src/backend/AgentSwarm-Workflow.md` as spec
5. **Use ZeroDB First** - Default to ZeroDB APIs, not PostgreSQL
6. **Test Your Changes** - Run E2E tests before committing
7. **Ask Questions** - Refer to troubleshooting section or documentation

**Most Important Files to Know**:
- `/src/backend/AgentSwarm-Workflow.md` - Official spec
- `/src/backend/app/api/api_v1/endpoints/agent_swarms.py` - Main API
- `/src/backend/app/agents/swarm/application_workflow.py` - Workflow logic
- `/AINative-website/src/pages/dashboard/AgentSwarmDashboard.tsx` - UI

**Critical Gaps to Fix**:
1. Stage 9: GitHub issue import ❌
2. Anthropic Messages API migration ❌
3. Sub-agent context isolation ❌
4. ZeroDB full integration (vectors, RLHF) ⚠️
5. RLHF feedback UI ❌

**You are now ready to work on AgentSwarm! Good luck! 🚀**

---

**Document Version**: 1.0
**Last Updated**: December 5, 2025
**Maintained By**: AINative Studio Engineering Team
**Next Review**: January 1, 2026
