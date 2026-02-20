# Agent Swarm Workflow - Official Specification

**Version**: 1.0.0
**Date**: 2025-12-04
**Purpose**: Define the correct end-to-end workflow for Agent Swarm application generation
**Status**: Specification Document for Implementation Validation

---

## Table of Contents

1. [Workflow Overview](#workflow-overview)
2. [Detailed Stage Breakdown](#detailed-stage-breakdown)
3. [SSCS Integration](#sscs-integration)
4. [Agent Roles & Responsibilities](#agent-roles--responsibilities)
5. [GitHub Integration Flow](#github-integration-flow)
6. [MinIO Storage Strategy](#minio-storage-strategy)
7. [Implementation Gaps](#implementation-gaps)

---

## Workflow Overview

### Complete 11-Stage User-Facing Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│                    USER PREPARATION PHASE                        │
│                      (Dashboard Steps 1-6)                       │
└─────────────────────────────────────────────────────────────────┘

Stage 1: Create Project & Upload Project Rules (Optional)
         ↓
Stage 2: Upload or Generate PRD
         ↓
Stage 3: System Generates ZeroDB-Aligned Data Model
         ↓
Stage 4: System Generates Agile Backlog (Epics + User Stories + Acceptance Criteria)
         ↓
Stage 5: System Generates Sprint Plan with Time Estimates
         ↓
Stage 6: User Reviews & Accepts Sprint Plan
         ↓

┌─────────────────────────────────────────────────────────────────┐
│                   AGENT EXECUTION PHASE                          │
│                      (Backend Workflow)                          │
└─────────────────────────────────────────────────────────────────┘

Stage 7: User Launches Agent Swarm
         ↓
Stage 8: DevOps Agent Creates GitHub Repository (User's Token)
         ↓
Stage 9: Product Manager Agent Publishes Backlog as GitHub Issues
         ↓
Stage 10: Specialized Agents Work on Issues in Parallel
         ↓
Stage 11: Agents Commit Code Following SSCS Standards
         ↓
         Final Deliverable: Production-Ready Repository
```

---

## Detailed Stage Breakdown

### **STAGE 1: Create Project & Upload Project Rules**

**Location**: Dashboard
**User Action**: Create new Agent Swarm project
**Optional**: Upload custom project rules (coding standards)

**What Happens**:
1. User clicks "Create New Project" in Agent Swarm Dashboard
2. User enters project name and description
3. User selects project type:
   - Web Application
   - Mobile App
   - API Service
   - Full-Stack Application
   - Microservices Architecture
4. **OPTIONAL**: User uploads custom project rules file (e.g., `my-company-rules.md`)
5. **DEFAULT**: If no rules uploaded, system applies **SSCS (Semantic Seed Venture Studio Coding Standards v2.0)**
6. System creates project record in database

**API Endpoint**:
```
POST /v1/public/agent-swarms/projects
{
  "name": "My SaaS App",
  "description": "Multi-tenant SaaS application",
  "project_type": "web_application",
  "custom_rules": null | "base64_encoded_rules_file"
}
```

**Database Record**:
```json
{
  "project_id": "uuid",
  "name": "My SaaS App",
  "project_type": "web_application",
  "custom_rules": null,
  "uses_sscs": true,
  "status": "created",
  "created_at": "2025-12-04T10:00:00Z"
}
```

**Output**:
- ✅ Project created
- ✅ Rules strategy determined (SSCS or Custom)
- ✅ Ready for PRD upload

---

### **STAGE 2: Upload or Generate PRD**

**Location**: Dashboard (Step 2)
**User Action**: Upload PRD file, paste PRD text, or AI-generate PRD
**Required**: User must provide PRD content

**What Happens**:

**Option A: Upload PRD**
1. User uploads `.md`, `.txt`, or `.pdf` file containing PRD
2. System extracts text content
3. System stores PRD in database

**Option B: Paste PRD**
1. User pastes PRD text into text area
2. System stores PRD in database

**Option C: AI-Generate PRD**
1. User provides brief description (2-3 sentences)
2. System calls Architect Agent to generate full PRD
3. User reviews and edits generated PRD
4. User confirms PRD
5. System stores PRD in database

**API Endpoint**:
```
POST /v1/public/agent-swarms/projects/{project_id}/prd
{
  "prd_source": "upload" | "paste" | "generate",
  "prd_content": "string",
  "prd_file": "base64_encoded_file" (optional)
}
```

**PRD Structure** (Generated or User-Provided):
```markdown
# Product Requirements Document

## Project Overview
- Name: My SaaS App
- Type: Multi-tenant SaaS
- Target Users: Small businesses

## Features
1. User Authentication (OAuth2, Email/Password)
2. Dashboard with Analytics
3. Multi-tenant Data Isolation
4. Real-time Notifications
5. API Integrations

## Non-Functional Requirements
- Response Time: <2s for all pages
- Uptime: 99.9%
- Security: OWASP Top 10 compliant
- Scalability: 10,000 concurrent users

## Technology Preferences
- Frontend: React + TypeScript
- Backend: FastAPI + Python
- Database: ZeroDB (SQL + Vector)
- Deployment: Railway
```

**Database Record Update**:
```json
{
  "project_id": "uuid",
  "prd_content": "full_prd_markdown_text",
  "prd_source": "upload",
  "status": "prd_uploaded",
  "updated_at": "2025-12-04T10:05:00Z"
}
```

**Output**:
- ✅ PRD stored
- ✅ Ready for data model generation
- → Triggers Stage 3 automatically

---

### **STAGE 3: System Generates ZeroDB-Aligned Data Model**

**Location**: Backend (Automatic)
**Agent**: Architect Agent (Claude 3.7 Sonnet - Extended Thinking)
**Triggered By**: PRD upload/confirmation in Stage 2

**What Happens**:
1. Architect Agent analyzes PRD content
2. Identifies entities and relationships
3. Generates data model **optimized for ZeroDB**:
   - SQL tables for relational data
   - Vector collections for semantic search
   - Memory tables for caching/sessions
4. User reviews generated data model in dashboard
5. User can edit/approve data model

**AI Processing**:
```python
# Architect Agent analyzes PRD
data_model = await architect_agent.generate_data_model(
    prd_content=project.prd_content,
    database_type="zerodb",  # ZeroDB-aligned
    include_vector_search=True
)
```

**Generated Data Model Example**:
```json
{
  "entities": [
    {
      "name": "User",
      "table_type": "sql",
      "fields": [
        {"name": "id", "type": "UUID", "primary_key": true},
        {"name": "email", "type": "String", "unique": true, "indexed": true},
        {"name": "hashed_password", "type": "String"},
        {"name": "tenant_id", "type": "UUID", "indexed": true},
        {"name": "created_at", "type": "DateTime"}
      ],
      "relationships": [
        {"type": "many_to_one", "target": "Tenant", "foreign_key": "tenant_id"}
      ]
    },
    {
      "name": "Post",
      "table_type": "sql",
      "fields": [
        {"name": "id", "type": "UUID", "primary_key": true},
        {"name": "title", "type": "String"},
        {"name": "content", "type": "Text"},
        {"name": "user_id", "type": "UUID", "indexed": true},
        {"name": "created_at", "type": "DateTime"}
      ],
      "vector_index": {
        "enabled": true,
        "field": "content",
        "dimensions": 1536,
        "purpose": "semantic_search"
      }
    },
    {
      "name": "Session",
      "table_type": "memory",
      "purpose": "User session caching",
      "ttl": 3600
    }
  ],
  "relationships": [
    {"from": "User", "to": "Tenant", "type": "many_to_one"},
    {"from": "Post", "to": "User", "type": "many_to_one"}
  ],
  "indexes": [
    {"entity": "User", "fields": ["email"], "unique": true},
    {"entity": "User", "fields": ["tenant_id"]},
    {"entity": "Post", "fields": ["user_id"]}
  ]
}
```

**API Endpoint**:
```
POST /v1/public/agent-swarms/projects/{project_id}/ai/generate-data-model
{
  "prd_content": "string"
}

Response:
{
  "data_model": { /* as shown above */ },
  "entities_count": 5,
  "relationships_count": 3,
  "vector_enabled_entities": ["Post"],
  "status": "generated"
}
```

**Dashboard Display**:
- User sees visual diagram of entities and relationships
- User can edit entity names, add/remove fields
- User can enable/disable vector search per entity
- User clicks "Approve Data Model" to proceed

**Database Record Update**:
```json
{
  "project_id": "uuid",
  "data_model": { /* full data model JSON */ },
  "status": "data_model_approved",
  "updated_at": "2025-12-04T10:10:00Z"
}
```

**Output**:
- ✅ ZeroDB-aligned data model generated
- ✅ Vector search enabled for appropriate entities
- ✅ Ready for backlog generation
- → Triggers Stage 4 automatically

---

### **STAGE 4: System Generates Agile Backlog**

**Location**: Backend (Automatic)
**Agent**: Product Manager Agent (Claude 3.5 Sonnet)
**Triggered By**: Data model approval in Stage 3

**What Happens**:
1. Product Manager Agent analyzes PRD + Data Model
2. Generates Agile backlog with:
   - **Epics** (high-level features)
   - **User Stories** (specific functionality)
   - **Acceptance Criteria** (given/when/then)
   - **Story Points** (Fibonacci: 0, 1, 2, 3, 5, 8)
   - **Story Type** (Feature, Bug, Chore)
3. User reviews backlog in dashboard
4. User can edit stories, points, acceptance criteria
5. User approves backlog

**AI Processing**:
```python
# Product Manager Agent generates backlog
backlog = await product_manager_agent.generate_backlog(
    prd_content=project.prd_content,
    data_model=project.data_model,
    coding_standards="sscs" if project.uses_sscs else "custom"
)
```

**Generated Backlog Structure**:
```json
{
  "epics": [
    {
      "epic_id": "EPIC-1",
      "title": "User Authentication System",
      "description": "Complete authentication and authorization system",
      "stories": ["STORY-1", "STORY-2", "STORY-3"]
    },
    {
      "epic_id": "EPIC-2",
      "title": "Dashboard & Analytics",
      "description": "User dashboard with real-time analytics",
      "stories": ["STORY-4", "STORY-5", "STORY-6"]
    }
  ],
  "stories": [
    {
      "story_id": "STORY-1",
      "epic_id": "EPIC-1",
      "type": "feature",
      "title": "User Registration API Endpoint",
      "description": "As a new user, I want to register an account so that I can access the platform",
      "acceptance_criteria": [
        "Given a new user with valid email and password",
        "When they submit the registration form",
        "Then a new user account is created in ZeroDB",
        "And a confirmation email is sent",
        "And a JWT token is returned"
      ],
      "points": 3,
      "point_rationale": "Requires database model, validation, email service integration, and JWT generation",
      "dependencies": [],
      "assigned_agent": "backend",
      "technical_notes": [
        "Use bcrypt for password hashing",
        "Validate email format and uniqueness",
        "Generate JWT with 1-hour expiration",
        "Store user in ZeroDB SQL table"
      ]
    },
    {
      "story_id": "STORY-2",
      "epic_id": "EPIC-1",
      "type": "feature",
      "title": "Login UI Component",
      "description": "As a returning user, I want to log in so that I can access my account",
      "acceptance_criteria": [
        "Given a valid email and password",
        "When I submit the login form",
        "Then I am redirected to the dashboard",
        "And my session is stored in ZeroDB Memory"
      ],
      "points": 2,
      "point_rationale": "Frontend form with validation and API integration",
      "dependencies": ["STORY-1"],
      "assigned_agent": "frontend",
      "technical_notes": [
        "Use React Hook Form for validation",
        "Store JWT in httpOnly cookie",
        "Implement loading states",
        "Add accessibility labels"
      ]
    },
    {
      "story_id": "STORY-3",
      "epic_id": "EPIC-1",
      "type": "chore",
      "title": "Authentication Integration Tests",
      "description": "Write E2E tests for complete authentication flow",
      "acceptance_criteria": [
        "Given the registration and login flows",
        "When tests are executed",
        "Then all authentication scenarios pass",
        "And test coverage is >90%"
      ],
      "points": 2,
      "point_rationale": "Multiple test scenarios with setup/teardown",
      "dependencies": ["STORY-1", "STORY-2"],
      "assigned_agent": "qa",
      "technical_notes": [
        "Use Playwright for E2E tests",
        "Record videos for all test runs",
        "Test happy path and error cases",
        "Verify JWT token handling"
      ]
    }
  ],
  "total_stories": 15,
  "total_points": 42,
  "epics_count": 5
}
```

**Backlog Scoring Summary**:
```json
{
  "by_type": {
    "feature": 10,
    "bug": 0,
    "chore": 5
  },
  "by_points": {
    "0": 2,
    "1": 3,
    "2": 5,
    "3": 3,
    "5": 2,
    "8": 0
  },
  "by_agent": {
    "frontend": 5,
    "backend": 6,
    "qa": 2,
    "devops": 2
  },
  "total_points": 42,
  "estimated_sprints": 1
}
```

**API Endpoint**:
```
POST /v1/public/agent-swarms/projects/{project_id}/ai/generate-backlog
{
  "data_model": { /* data model JSON */ }
}

Response:
{
  "backlog": { /* as shown above */ },
  "total_stories": 15,
  "total_points": 42,
  "epics_count": 5,
  "status": "generated"
}
```

**Dashboard Display**:
- User sees Kanban-style backlog board
- Epics grouped together
- Stories show: ID, Title, Points, Type, Agent
- User can drag-and-drop to reorder priorities
- User can edit story details
- User clicks "Approve Backlog" to proceed

**Database Record Update**:
```json
{
  "project_id": "uuid",
  "backlog": { /* full backlog JSON */ },
  "status": "backlog_approved",
  "updated_at": "2025-12-04T10:15:00Z"
}
```

**Output**:
- ✅ Agile backlog generated with epics and stories
- ✅ All stories scored with Fibonacci points
- ✅ Acceptance criteria defined for each story
- ✅ Stories assigned to appropriate agents
- ✅ Ready for sprint planning
- → Triggers Stage 5 automatically

---

### **STAGE 5: System Generates Sprint Plan with Time Estimates**

**Location**: Backend (Automatic)
**Agent**: Product Manager Agent (Claude 3.5 Sonnet)
**Triggered By**: Backlog approval in Stage 4

**What Happens**:
1. Product Manager Agent analyzes backlog
2. Generates sprint plan with time estimates based on:
   - **Single Agent Mode**: Sequential execution (longer)
   - **Agent Swarm Mode**: Parallel execution (faster)
3. Calculates dependencies between stories
4. Creates sprint schedule
5. User reviews sprint plan in dashboard
6. User selects execution mode (Single Agent vs Agent Swarm)
7. User approves sprint plan

**AI Processing**:
```python
# Product Manager Agent generates sprint plan
sprint_plan = await product_manager_agent.generate_sprint_plan(
    backlog=project.backlog,
    execution_modes=["single_agent", "agent_swarm"]
)
```

**Generated Sprint Plan**:
```json
{
  "sprint_id": "SPRINT-1",
  "sprint_name": "MVP Development Sprint",
  "total_stories": 15,
  "total_points": 42,
  "execution_modes": {
    "single_agent": {
      "mode": "sequential",
      "estimated_time_minutes": 180,
      "estimated_time_human": "3 hours",
      "workflow": "Stories executed one at a time by a single agent",
      "parallel_execution": false,
      "agent_count": 1,
      "breakdown": [
        {
          "agent": "backend",
          "stories": ["STORY-1", "STORY-4", "STORY-7", "STORY-10", "STORY-13", "STORY-15"],
          "total_points": 18,
          "estimated_minutes": 90
        },
        {
          "agent": "frontend",
          "stories": ["STORY-2", "STORY-5", "STORY-8", "STORY-11", "STORY-14"],
          "total_points": 15,
          "estimated_minutes": 60
        },
        {
          "agent": "qa",
          "stories": ["STORY-3", "STORY-9"],
          "total_points": 4,
          "estimated_minutes": 20
        },
        {
          "agent": "devops",
          "stories": ["STORY-6", "STORY-12"],
          "total_points": 5,
          "estimated_minutes": 10
        }
      ]
    },
    "agent_swarm": {
      "mode": "parallel",
      "estimated_time_minutes": 15,
      "estimated_time_human": "15 minutes",
      "workflow": "Multiple specialized agents work on stories in parallel",
      "parallel_execution": true,
      "agent_count": 6,
      "max_parallel_stories": 6,
      "breakdown": [
        {
          "wave": 1,
          "parallel_stories": ["STORY-1", "STORY-4", "STORY-6"],
          "agents": ["backend", "backend", "devops"],
          "estimated_minutes": 5,
          "description": "Initial setup and independent backend work"
        },
        {
          "wave": 2,
          "parallel_stories": ["STORY-2", "STORY-5", "STORY-7", "STORY-10"],
          "agents": ["frontend", "frontend", "backend", "backend"],
          "estimated_minutes": 5,
          "description": "Frontend + Backend parallel development",
          "dependencies_met": ["STORY-1"]
        },
        {
          "wave": 3,
          "parallel_stories": ["STORY-3", "STORY-8", "STORY-9", "STORY-11", "STORY-12", "STORY-13"],
          "agents": ["qa", "frontend", "qa", "frontend", "devops", "backend"],
          "estimated_minutes": 5,
          "description": "Testing, final features, deployment setup",
          "dependencies_met": ["STORY-1", "STORY-2", "STORY-4", "STORY-5"]
        }
      ],
      "time_savings": "165 minutes (92% faster than single agent)"
    }
  },
  "recommended_mode": "agent_swarm",
  "dependency_graph": {
    "STORY-1": [],
    "STORY-2": ["STORY-1"],
    "STORY-3": ["STORY-1", "STORY-2"],
    "STORY-4": [],
    "STORY-5": ["STORY-4"]
  }
}
```

**API Endpoint**:
```
POST /v1/public/agent-swarms/projects/{project_id}/ai/generate-sprint-plan
{
  "backlog": { /* backlog JSON */ }
}

Response:
{
  "sprint_plan": { /* as shown above */ },
  "single_agent_time": "3 hours",
  "agent_swarm_time": "15 minutes",
  "time_savings": "92%",
  "status": "generated"
}
```

**Dashboard Display**:
- User sees side-by-side comparison:
  - **Single Agent**: 3 hours (sequential)
  - **Agent Swarm**: 15 minutes (parallel)
- Visual dependency graph showing story relationships
- Timeline visualization showing execution waves
- User selects execution mode
- User clicks "Accept Sprint Plan" to proceed

**Database Record Update**:
```json
{
  "project_id": "uuid",
  "sprint_plan": { /* full sprint plan JSON */ },
  "execution_mode": "agent_swarm",
  "status": "sprint_plan_approved",
  "updated_at": "2025-12-04T10:20:00Z"
}
```

**Output**:
- ✅ Sprint plan generated with time estimates
- ✅ Single Agent vs Agent Swarm comparison provided
- ✅ Dependency graph calculated
- ✅ Execution waves planned for parallel execution
- ✅ User selected execution mode
- ✅ Ready for agent swarm launch

---

### **STAGE 6: User Reviews & Accepts Sprint Plan**

**Location**: Dashboard (Step 5)
**User Action**: Review sprint plan and click "Accept"

**What Happens**:
1. User reviews complete sprint plan
2. User sees time estimates for both modes
3. User confirms execution mode selection
4. User clicks "Accept Sprint Plan"
5. System updates project status to "ready_for_launch"
6. "Launch Agent Swarm" button becomes active

**Dashboard Display**:
```
┌────────────────────────────────────────────────────────┐
│              Sprint Plan Summary                        │
├────────────────────────────────────────────────────────┤
│ Total Stories: 15                                      │
│ Total Points: 42                                       │
│ Epics: 5                                               │
│                                                        │
│ Execution Mode:                                        │
│ ○ Single Agent (3 hours)                              │
│ ● Agent Swarm (15 minutes) ⚡ RECOMMENDED              │
│                                                        │
│ Time Savings: 165 minutes (92% faster)                │
│                                                        │
│ [View Dependency Graph] [View Timeline]               │
│                                                        │
│ [← Edit Sprint Plan]  [Accept Sprint Plan →]          │
└────────────────────────────────────────────────────────┘
```

**Database Record Update**:
```json
{
  "project_id": "uuid",
  "sprint_plan_accepted": true,
  "status": "ready_for_launch",
  "updated_at": "2025-12-04T10:25:00Z"
}
```

**Output**:
- ✅ Sprint plan accepted
- ✅ Execution mode confirmed
- ✅ Ready for Agent Swarm launch

---

### **STAGE 7: User Launches Agent Swarm**

**Location**: Dashboard (Step 6)
**User Action**: Click "Launch Agent Swarm" button
**Triggers**: Backend workflow execution

**What Happens**:
1. User clicks "Launch Agent Swarm"
2. Frontend sends launch request to backend
3. Backend creates workflow execution record
4. Backend initializes Agent Swarm orchestrator
5. Real-time status updates sent to frontend via WebSocket
6. User sees progress dashboard with live updates

**API Endpoint**:
```
POST /v1/public/agent-swarms/projects/{project_id}/launch
{
  "execution_mode": "agent_swarm",
  "sprint_plan_id": "SPRINT-1"
}

Response:
{
  "execution_id": "uuid",
  "status": "initializing",
  "estimated_completion": "15 minutes",
  "started_at": "2025-12-04T10:30:00Z",
  "websocket_channel": "project_{project_id}_execution"
}
```

**Backend Initialization**:
```python
# Create workflow execution
execution = WorkflowExecution(
    id=str(uuid.uuid4()),
    project_id=project.project_id,
    sprint_plan=project.sprint_plan,
    execution_mode="agent_swarm",
    status="initializing",
    started_at=datetime.utcnow()
)

# Initialize Agent Swarm Orchestrator
orchestrator = AgentSwarmOrchestrator(
    execution=execution,
    coding_standards=project.custom_rules or "sscs",
    github_token=await get_user_github_token(user.id)
)

# Start execution (non-blocking)
await orchestrator.start_execution()
```

**WebSocket Updates**:
```json
{
  "type": "execution_status",
  "execution_id": "uuid",
  "status": "initializing",
  "message": "Agent Swarm initialized. Starting Stage 8: GitHub repository creation...",
  "timestamp": "2025-12-04T10:30:05Z"
}
```

**Dashboard Display**:
```
┌────────────────────────────────────────────────────────┐
│         Agent Swarm Execution (Live)                    │
├────────────────────────────────────────────────────────┤
│ Execution ID: a1b2c3d4-e5f6-7890                       │
│ Started: 10:30:05                                      │
│ Estimated Completion: 10:45:05 (15 min)               │
│                                                        │
│ Status: Initializing...                               │
│                                                        │
│ Progress:                                              │
│ [████░░░░░░░░░░░░░░░░] 7%                             │
│                                                        │
│ Current Stage: 8 - Creating GitHub Repository         │
│                                                        │
│ [View Live Logs] [View Agent Activity]                │
└────────────────────────────────────────────────────────┘
```

**Database Record**:
```json
{
  "execution_id": "uuid",
  "project_id": "uuid",
  "status": "in_progress",
  "current_stage": 8,
  "started_at": "2025-12-04T10:30:00Z",
  "estimated_completion": "2025-12-04T10:45:00Z"
}
```

**Output**:
- ✅ Agent Swarm launched
- ✅ Workflow execution started
- ✅ Real-time updates initialized
- → Proceeds to Stage 8

---

### **STAGE 8: DevOps Agent Creates GitHub Repository**

**Location**: Backend (Agent Execution)
**Agent**: DevOps Agent (Claude 3.5 Sonnet)
**Dependencies**: Stage 7 completion
**User's GitHub Token**: Retrieved from database (encrypted)

**What Happens**:
1. DevOps Agent retrieves user's GitHub Personal Access Token from database
2. Agent validates token has required permissions
3. Agent creates new GitHub repository under user's account
4. Agent initializes repository with:
   - `main` branch (protected)
   - `develop` branch (default for work)
   - `.gitignore` file
   - Initial `README.md`
5. Agent sets up branch protection rules on `main`
6. Agent creates repository metadata in ZeroDB
7. Repository URL returned to orchestrator

**Token Retrieval**:
```python
# Retrieve user's encrypted GitHub token
from app.services.github_settings_service import GitHubSettingsService
from app.db.session import async_session_maker

async with async_session_maker() as db:
    github_service = GitHubSettingsService(db)
    github_token = await github_service.get_decrypted_token(execution.user_id)

if not github_token:
    raise Exception(
        "GitHub Personal Access Token not found. "
        "Please configure your token in Settings → Integrations → GitHub"
    )
```

**GitHub Repository Creation**:
```python
# Use MCP GitHub tools with user's token
from app.integrations.github_mcp import github_mcp

# Create repository
repo_name = project.name.lower().replace(" ", "-")
repo_description = f"{project.description[:100]}"

repo_result = await github_mcp.create_repository(
    name=repo_name,
    description=repo_description,
    private=project.github_private or False,
    auto_init=True,  # Create with initial README
    gitignore_template="Python",  # Based on project type
    github_token=github_token  # User's token!
)

repo_url = repo_result['html_url']
repo_owner = repo_result['owner']['login']
```

**Branch Creation**:
```python
# Create develop branch
await github_mcp.create_branch(
    owner=repo_owner,
    repo=repo_name,
    branch='develop',
    from_branch='main',
    github_token=github_token
)

# Set develop as default branch
await github_mcp.update_repository(
    owner=repo_owner,
    repo=repo_name,
    default_branch='develop',
    github_token=github_token
)
```

**Branch Protection**:
```python
# Protect main branch
await github_mcp.set_branch_protection(
    owner=repo_owner,
    repo=repo_name,
    branch='main',
    required_approving_review_count=1,
    require_code_owner_reviews=False,
    dismiss_stale_reviews=True,
    require_status_checks=True,
    required_status_checks=['ci/tests', 'ci/lint'],
    enforce_admins=False,
    allow_force_pushes=False,
    allow_deletions=False,
    github_token=github_token
)
```

**Initial README.md**:
```markdown
# {Project Name}

{Project Description}

## Project Overview

This project was generated using AINative Agent Swarm.

## Technology Stack

- **Frontend**: React + TypeScript
- **Backend**: FastAPI + Python
- **Database**: ZeroDB (SQL + Vector)
- **Deployment**: Railway

## Development Setup

### Prerequisites
- Node.js 18+
- Python 3.11+
- Docker (optional)

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Backend
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Project Structure

```
.
├── frontend/          # React application
├── backend/           # FastAPI application
├── docs/              # Documentation
└── .github/           # GitHub workflows
```

## Contributing

All development happens on the `develop` branch. Create feature branches from `develop` and submit PRs.

Branch naming convention:
- `feature/{issue-id}-{description}`
- `bug/{issue-id}-{description}`
- `chore/{issue-id}-{description}`

## License

MIT
```

**Store Repository Info**:
```python
# Store in execution record
execution.github_repository = {
    "url": repo_url,
    "owner": repo_owner,
    "name": repo_name,
    "default_branch": "develop",
    "created_at": datetime.utcnow().isoformat()
}

# Store in ZeroDB
await zerodb_service.store_memory(
    agent_id="devops",
    content=f"Created GitHub repository: {repo_url}",
    metadata={
        "project_id": project.project_id,
        "execution_id": execution.id,
        "repo_url": repo_url,
        "repo_owner": repo_owner,
        "repo_name": repo_name
    }
)
```

**WebSocket Update**:
```json
{
  "type": "stage_complete",
  "execution_id": "uuid",
  "stage": 8,
  "status": "completed",
  "message": "GitHub repository created successfully",
  "data": {
    "repo_url": "https://github.com/urbantech/my-saas-app",
    "repo_owner": "urbantech",
    "repo_name": "my-saas-app"
  },
  "timestamp": "2025-12-04T10:32:00Z"
}
```

**Database Record Update**:
```json
{
  "execution_id": "uuid",
  "current_stage": 8,
  "stage_8_status": "completed",
  "github_repository": {
    "url": "https://github.com/urbantech/my-saas-app",
    "owner": "urbantech",
    "name": "my-saas-app",
    "default_branch": "develop"
  },
  "updated_at": "2025-12-04T10:32:00Z"
}
```

**Output**:
- ✅ GitHub repository created under user's account
- ✅ `main` branch protected
- ✅ `develop` branch set as default
- ✅ Initial README.md committed
- ✅ Repository URL stored
- → Proceeds to Stage 9

---

### **STAGE 9: Product Manager Agent Publishes Backlog as GitHub Issues**

**Location**: Backend (Agent Execution)
**Agent**: Product Manager Agent (Claude 3.5 Sonnet)
**Dependencies**: Stage 8 completion
**GitHub Token**: User's token from Stage 8

**What Happens**:
1. Product Manager Agent retrieves approved backlog
2. Agent converts each user story to GitHub Issue
3. Agent creates issues in the GitHub repository
4. Agent applies labels (feature, bug, chore)
5. Agent assigns story points in issue description
6. Agent links related issues (epics, dependencies)
7. Agent stores GitHub issue IDs in database
8. All stories now trackable in GitHub Issues

**Backlog to GitHub Issues Conversion**:
```python
# Product Manager Agent publishes backlog
from app.integrations.github_mcp import github_mcp

backlog = project.backlog
repo_owner = execution.github_repository['owner']
repo_name = execution.github_repository['name']
github_token = github_token  # From Stage 8

github_issues = []

for story in backlog['stories']:
    # Create issue body following SSCS format
    issue_body = f"""## Story
{story['description']}

## Acceptance Criteria
{chr(10).join(f'- {ac}' for ac in story['acceptance_criteria'])}

## Story Details
- **Type**: {story['type']}
- **Points**: {story['points']}
- **Assigned Agent**: {story['assigned_agent']}
- **Epic**: {story['epic_id']}

## Point Rationale
{story['point_rationale']}

## Technical Notes
{chr(10).join(f'- {note}' for note in story.get('technical_notes', []))}

## Dependencies
{chr(10).join(f'- #{dep}' for dep in story.get('dependencies', [])) or 'None'}
"""

    # Create GitHub issue
    issue_result = await github_mcp.create_issue(
        owner=repo_owner,
        repo=repo_name,
        title=f"[{story['story_id']}] {story['title']}",
        body=issue_body,
        labels=[
            story['type'],  # feature, bug, or chore
            f"points-{story['points']}",
            f"agent-{story['assigned_agent']}",
            story['epic_id'].lower()
        ],
        github_token=github_token
    )

    github_issues.append({
        "story_id": story['story_id'],
        "github_issue_number": issue_result['number'],
        "github_issue_url": issue_result['html_url']
    })

    # Store mapping in database
    await db.execute(
        "INSERT INTO story_github_mapping (story_id, github_issue_number, github_issue_url) VALUES ($1, $2, $3)",
        story['story_id'], issue_result['number'], issue_result['html_url']
    )
```

**Example GitHub Issue Created**:
```
Title: [STORY-1] User Registration API Endpoint

Labels: feature, points-3, agent-backend, epic-1

Body:
## Story
As a new user, I want to register an account so that I can access the platform

## Acceptance Criteria
- Given a new user with valid email and password
- When they submit the registration form
- Then a new user account is created in ZeroDB
- And a confirmation email is sent
- And a JWT token is returned

## Story Details
- **Type**: feature
- **Points**: 3
- **Assigned Agent**: backend
- **Epic**: EPIC-1

## Point Rationale
Requires database model, validation, email service integration, and JWT generation

## Technical Notes
- Use bcrypt for password hashing
- Validate email format and uniqueness
- Generate JWT with 1-hour expiration
- Store user in ZeroDB SQL table

## Dependencies
None
```

**Create Epic Labels**:
```python
# Create labels for epics
for epic in backlog['epics']:
    await github_mcp.create_label(
        owner=repo_owner,
        repo=repo_name,
        name=epic['epic_id'].lower(),
        description=epic['title'],
        color="0366d6",  # Blue
        github_token=github_token
    )

# Create labels for points
for points in [0, 1, 2, 3, 5, 8]:
    await github_mcp.create_label(
        owner=repo_owner,
        repo=repo_name,
        name=f"points-{points}",
        description=f"Story points: {points}",
        color="fbca04",  # Yellow
        github_token=github_token
    )

# Create labels for agents
for agent in ["frontend", "backend", "qa", "devops"]:
    await github_mcp.create_label(
        owner=repo_owner,
        repo=repo_name,
        name=f"agent-{agent}",
        description=f"Assigned to {agent} agent",
        color="7057ff",  # Purple
        github_token=github_token
    )
```

**Create Project Board** (Optional):
```python
# Create GitHub Project board for sprint tracking
project_board = await github_mcp.create_project(
    owner=repo_owner,
    repo=repo_name,
    name="Sprint 1 - MVP Development",
    body="Agent Swarm execution tracking",
    github_token=github_token
)

# Create columns
columns = ["To Do", "In Progress", "In Review", "Done"]
for column_name in columns:
    await github_mcp.create_project_column(
        project_id=project_board['id'],
        name=column_name,
        github_token=github_token
    )

# Add issues to "To Do" column
for issue_mapping in github_issues:
    await github_mcp.add_project_card(
        column_id=todo_column_id,
        content_id=issue_mapping['github_issue_number'],
        content_type='Issue',
        github_token=github_token
    )
```

**Store Issue Mapping**:
```python
# Update execution record with GitHub issues
execution.github_issues = github_issues
execution.total_issues_created = len(github_issues)

# Store in ZeroDB
await zerodb_service.store_memory(
    agent_id="product_manager",
    content=f"Published {len(github_issues)} issues to GitHub repository",
    metadata={
        "project_id": project.project_id,
        "execution_id": execution.id,
        "total_issues": len(github_issues),
        "repo_url": execution.github_repository['url']
    }
)
```

**WebSocket Update**:
```json
{
  "type": "stage_complete",
  "execution_id": "uuid",
  "stage": 9,
  "status": "completed",
  "message": "Published 15 issues to GitHub repository",
  "data": {
    "total_issues": 15,
    "repo_url": "https://github.com/urbantech/my-saas-app/issues",
    "issues_created": [
      {"story_id": "STORY-1", "issue_number": 1, "url": "..."},
      {"story_id": "STORY-2", "issue_number": 2, "url": "..."}
    ]
  },
  "timestamp": "2025-12-04T10:34:00Z"
}
```

**Database Record Update**:
```json
{
  "execution_id": "uuid",
  "current_stage": 9,
  "stage_9_status": "completed",
  "github_issues": [
    {"story_id": "STORY-1", "issue_number": 1, "url": "..."},
    {"story_id": "STORY-2", "issue_number": 2, "url": "..."}
  ],
  "total_issues_created": 15,
  "updated_at": "2025-12-04T10:34:00Z"
}
```

**Output**:
- ✅ 15 GitHub issues created (one per user story)
- ✅ Labels applied (type, points, agent, epic)
- ✅ Issue descriptions include acceptance criteria and technical notes
- ✅ Dependencies linked between issues
- ✅ Project board created (optional)
- ✅ Issue mapping stored in database
- → Proceeds to Stage 10

---

### **STAGE 10: Specialized Agents Work on Issues in Parallel**

**Location**: Backend (Agent Execution)
**Agents**: All specialized agents (Frontend, Backend, QA, DevOps)
**Dependencies**: Stage 9 completion
**Execution Mode**: Parallel (up to 6 agents simultaneously)
**Follows**: SSCS (Semantic Seed Venture Studio Coding Standards v2.0)

**What Happens**:
1. Orchestrator retrieves GitHub issues from Stage 9
2. Orchestrator analyzes dependencies and creates execution waves
3. Specialized agents assigned to stories based on `assigned_agent` field
4. Each agent:
   - Reads assigned GitHub issue
   - Creates feature branch named `feature/{issue-number}-{slug}`
   - Follows TDD: Red → Green → Refactor
   - Commits code with clear messages (NO Claude/Anthropic branding)
   - Stores files in MinIO via ZeroDB API
   - Updates GitHub issue with progress
5. Agents work in parallel where dependencies allow
6. Code reviewed and merged following SSCS workflow

**Execution Wave Planning**:
```python
# Orchestrator plans execution waves based on dependencies
execution_waves = await orchestrator.plan_execution_waves(
    github_issues=execution.github_issues,
    backlog=project.backlog
)

# Example execution waves:
# Wave 1: STORY-1, STORY-4, STORY-6 (no dependencies)
# Wave 2: STORY-2, STORY-5, STORY-7 (depends on Wave 1)
# Wave 3: STORY-3, STORY-8, STORY-9 (depends on Wave 2)
```

**Agent Assignment & Parallel Execution**:
```python
# Wave 1: Start 3 agents in parallel
tasks = []
for story_id in wave_1_stories:
    story = get_story(story_id)
    agent_type = story['assigned_agent']  # "backend", "frontend", etc.

    # Create agent instance
    agent = create_agent(
        agent_type=agent_type,
        coding_standards=project.custom_rules or "sscs",
        github_token=github_token,
        minio_config=minio_config
    )

    # Start work on story (non-blocking)
    task = agent.work_on_story(
        story=story,
        github_issue=get_github_issue(story_id),
        repo_info=execution.github_repository
    )
    tasks.append(task)

# Wait for all agents in wave to complete
results = await asyncio.gather(*tasks)
```

**Individual Agent Workflow (Example: Backend Agent on STORY-1)**:

**Step 1: Read GitHub Issue**
```python
# Backend Agent retrieves issue
issue = await github_mcp.get_issue(
    owner=repo_owner,
    repo=repo_name,
    issue_number=1,  # STORY-1 maps to issue #1
    github_token=github_token
)

# Parse story details from issue body
story_details = parse_issue_body(issue['body'])
# Returns: {
#   "acceptance_criteria": [...],
#   "points": 3,
#   "type": "feature",
#   "technical_notes": [...]
# }
```

**Step 2: Create Feature Branch**
```python
# Branch naming: feature/{issue-number}-{slug}
branch_name = f"feature/{issue['number']}-user-registration-api"

await github_mcp.create_branch(
    owner=repo_owner,
    repo=repo_name,
    branch=branch_name,
    from_branch='develop',
    github_token=github_token
)

# Update issue with "In Progress" label
await github_mcp.add_labels(
    owner=repo_owner,
    repo=repo_name,
    issue_number=issue['number'],
    labels=['in-progress'],
    github_token=github_token
)

# Move project card to "In Progress"
await github_mcp.move_project_card(
    card_id=story_card_id,
    column_id=in_progress_column_id,
    github_token=github_token
)
```

**Step 3: TDD - Red (Write Failing Tests)**
```python
# Backend Agent generates failing tests first
test_code = await backend_agent.generate_tests(
    story=story_details,
    test_type="red",  # Failing tests
    coding_standards="sscs"
)

# Example generated test (pytest + BDD):
"""
# tests/api/test_user_registration.py
import pytest
from httpx import AsyncClient
from app.main import app

describe('User Registration API', () => {
    describe('POST /api/auth/register', () => {
        it('should create a new user with valid credentials', async () => {
            # Given
            client = AsyncClient(app=app, base_url="http://test")
            user_data = {
                "email": "test@example.com",
                "password": "Test123!",
                "confirm_password": "Test123!"
            }

            # When
            response = await client.post("/api/auth/register", json=user_data)

            # Then
            assert response.status_code == 201
            data = response.json()
            assert data["email"] == "test@example.com"
            assert "access_token" in data
            assert "id" in data
        })

        it('should reject duplicate email', async () => {
            # Given
            client = AsyncClient(app=app, base_url="http://test")
            existing_user = await create_test_user("existing@example.com")

            # When
            response = await client.post("/api/auth/register", json={
                "email": "existing@example.com",
                "password": "Test123!"
            })

            # Then
            assert response.status_code == 400
            assert "already registered" in response.json()["detail"].lower()
        })
    })
})
"""

# Store test file in MinIO
await minio_service.upload_file(
    bucket="agent-swarm-projects",
    file_path=f"{execution.id}/backend/tests/api/test_user_registration.py",
    content=test_code
)

# Commit to GitHub (WIP commit - SSCS workflow)
await github_mcp.create_commit(
    owner=repo_owner,
    repo=repo_name,
    branch=branch_name,
    message="WIP: red tests for user registration",  # SSCS format
    files=[{
        "path": "backend/tests/api/test_user_registration.py",
        "content": test_code
    }],
    github_token=github_token
)
```

**Step 4: TDD - Green (Implement Minimal Code)**
```python
# Backend Agent generates minimal implementation to pass tests
implementation_code = await backend_agent.generate_implementation(
    story=story_details,
    tests=test_code,
    test_type="green",  # Passing implementation
    coding_standards="sscs"
)

# Generated files:
# 1. API endpoint
router_code = """
# app/api/routers/auth_router.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.auth import UserCreate, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["authentication"])

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):
    auth_service = AuthService(db)

    # Check if user exists
    existing_user = await auth_service.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="Email already registered"
        )

    # Create user
    user = await auth_service.create_user(user_data)

    # Generate JWT token
    access_token = auth_service.create_access_token(user.id)

    return {
        "id": user.id,
        "email": user.email,
        "access_token": access_token,
        "token_type": "bearer"
    }
"""

# 2. Service layer
service_code = """
# app/services/auth_service.py
from sqlalchemy.orm import Session
from app.models.user import User
from app.schemas.auth import UserCreate
from passlib.context import CryptContext
from jose import jwt
from datetime import datetime, timedelta
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

class AuthService:
    def __init__(self, db: Session):
        self.db = db

    async def get_user_by_email(self, email: str):
        return self.db.query(User).filter(User.email == email).first()

    async def create_user(self, user_data: UserCreate):
        hashed_password = pwd_context.hash(user_data.password)
        user = User(
            email=user_data.email,
            hashed_password=hashed_password
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def create_access_token(self, user_id: str):
        expire = datetime.utcnow() + timedelta(hours=1)
        to_encode = {"sub": str(user_id), "exp": expire}
        return jwt.encode(to_encode, settings.JWT_SECRET, algorithm="HS256")
"""

# 3. Database model
model_code = """
# app/models/user.py
from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.postgresql import UUID
from app.db.base_class import Base
import uuid
from datetime import datetime

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
"""

# 4. Pydantic schemas
schema_code = """
# app/schemas/auth.py
from pydantic import BaseModel, EmailStr, validator
from uuid import UUID

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    confirm_password: str

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not any(char.isdigit() for char in v):
            raise ValueError('Password must contain a number')
        if not any(char.isupper() for char in v):
            raise ValueError('Password must contain an uppercase letter')
        return v

    @validator('confirm_password')
    def passwords_match(cls, v, values):
        if 'password' in values and v != values['password']:
            raise ValueError('Passwords do not match')
        return v

class UserResponse(BaseModel):
    id: UUID
    email: str
    access_token: str
    token_type: str = "bearer"

    class Config:
        orm_mode = True
"""

# Store all files in MinIO
files_to_store = {
    "backend/app/api/routers/auth_router.py": router_code,
    "backend/app/services/auth_service.py": service_code,
    "backend/app/models/user.py": model_code,
    "backend/app/schemas/auth.py": schema_code
}

for file_path, content in files_to_store.items():
    await minio_service.upload_file(
        bucket="agent-swarm-projects",
        file_path=f"{execution.id}/{file_path}",
        content=content
    )

# Commit to GitHub (Green commit - SSCS format)
await github_mcp.create_commit(
    owner=repo_owner,
    repo=repo_name,
    branch=branch_name,
    message="green: user registration endpoint with JWT auth",  # SSCS format, NO Claude branding
    files=[
        {"path": path, "content": content}
        for path, content in files_to_store.items()
    ],
    github_token=github_token
)
```

**Step 5: TDD - Refactor (Improve Code Quality)**
```python
# Backend Agent refactors code while keeping tests green
refactored_code = await backend_agent.refactor_code(
    current_code=implementation_code,
    tests=test_code,
    coding_standards="sscs"
)

# Example refactoring:
# - Extract password hashing to utility function
# - Add comprehensive error logging
# - Improve type hints
# - Add docstrings

# Commit refactoring (SSCS format)
await github_mcp.create_commit(
    owner=repo_owner,
    repo=repo_name,
    branch=branch_name,
    message="refactor: extract password utilities and improve error handling",  # SSCS format
    files=refactored_files,
    github_token=github_token
)
```

**Step 6: Run Tests Locally**
```python
# Backend Agent runs tests to verify
test_results = await backend_agent.run_tests(
    test_files=["tests/api/test_user_registration.py"],
    environment="test"
)

# Example test results:
"""
======================== test session starts =========================
collected 2 items

tests/api/test_user_registration.py::test_register_new_user PASSED
tests/api/test_user_registration.py::test_reject_duplicate_email PASSED

========================= 2 passed in 1.24s ==========================
"""

# Store test results in ZeroDB
await zerodb_service.rlhf_log_interaction(
    workflow_id=execution.id,
    agent_id="backend",
    story_id="STORY-1",
    test_results=test_results,
    success=True
)
```

**Step 7: Create Pull Request**
```python
# Backend Agent creates PR following SSCS template
pr_body = f"""## Problem/Context
Implements user registration API endpoint as specified in issue #{issue['number']}.

## Solution Summary
- Created `/api/auth/register` POST endpoint
- Implemented password validation (min 8 chars, uppercase, number)
- Added email uniqueness check
- Integrated JWT token generation
- Stored user data in ZeroDB SQL table

## Test Plan
```bash
# Run tests
cd backend
pytest tests/api/test_user_registration.py -v

# Expected output:
# ✓ test_register_new_user PASSED
# ✓ test_reject_duplicate_email PASSED
```

## Test Results
- ✅ 2/2 tests passing
- ✅ Coverage: 100% for auth_router.py
- ✅ All acceptance criteria met

## Risk/Rollback
- **Risk**: Low - new feature, no existing dependencies
- **Rollback**: Revert this PR and remove auth_router registration from main.py

## Story Link
- **Story**: STORY-1
- **Issue**: #{issue['number']}
- **Type**: feature
- **Estimate**: 3 points

## Acceptance Criteria Met
- ✅ Given a new user with valid email and password
- ✅ When they submit the registration form
- ✅ Then a new user account is created in ZeroDB
- ✅ And a confirmation email is sent (deferred to STORY-4)
- ✅ And a JWT token is returned

## Files Changed
- `backend/app/api/routers/auth_router.py` (new)
- `backend/app/services/auth_service.py` (new)
- `backend/app/models/user.py` (new)
- `backend/app/schemas/auth.py` (new)
- `backend/tests/api/test_user_registration.py` (new)
"""

# Create PR (NO Claude/Anthropic branding per SSCS rules)
pr_result = await github_mcp.create_pull_request(
    owner=repo_owner,
    repo=repo_name,
    title=f"[STORY-1] User Registration API Endpoint",
    body=pr_body,
    head=branch_name,
    base='develop',
    draft=False,
    github_token=github_token
)

# Link PR to issue
await github_mcp.add_comment(
    owner=repo_owner,
    repo=repo_name,
    issue_number=issue['number'],
    body=f"Pull request created: #{pr_result['number']}",
    github_token=github_token
)

# Update issue status
await github_mcp.add_labels(
    owner=repo_owner,
    repo=repo_name,
    issue_number=issue['number'],
    labels=['in-review'],
    github_token=github_token
)

# Move project card to "In Review"
await github_mcp.move_project_card(
    card_id=story_card_id,
    column_id=in_review_column_id,
    github_token=github_token
)
```

**Step 8: Auto-Merge PR (CI Passing)**
```python
# If CI passes, auto-merge PR
ci_status = await github_mcp.get_pull_request_status(
    owner=repo_owner,
    repo=repo_name,
    pull_number=pr_result['number'],
    github_token=github_token
)

if ci_status['state'] == 'success':
    # Merge PR
    await github_mcp.merge_pull_request(
        owner=repo_owner,
        repo=repo_name,
        pull_number=pr_result['number'],
        merge_method='squash',
        commit_title=f"[STORY-1] User Registration API Endpoint (#{pr_result['number']})",
        github_token=github_token
    )

    # Close issue
    await github_mcp.update_issue(
        owner=repo_owner,
        repo=repo_name,
        issue_number=issue['number'],
        state='closed',
        github_token=github_token
    )

    # Add "Delivered" label
    await github_mcp.add_labels(
        owner=repo_owner,
        repo=repo_name,
        issue_number=issue['number'],
        labels=['delivered'],
        github_token=github_token
    )

    # Move project card to "Done"
    await github_mcp.move_project_card(
        card_id=story_card_id,
        column_id=done_column_id,
        github_token=github_token
    )
```

**Parallel Execution Example**:
```python
# Wave 1: 3 agents work in parallel
# - Backend Agent on STORY-1 (User Registration API)
# - Backend Agent on STORY-4 (Dashboard API)
# - DevOps Agent on STORY-6 (CI/CD Setup)

# All 3 agents execute steps 1-8 concurrently

# Wave 2: Starts after Wave 1 completes
# - Frontend Agent on STORY-2 (Login UI) - depends on STORY-1
# - Frontend Agent on STORY-5 (Dashboard UI) - depends on STORY-4
# - Backend Agent on STORY-7 (Email Service)

# And so on...
```

**WebSocket Updates** (Real-time per agent):
```json
{
  "type": "agent_progress",
  "execution_id": "uuid",
  "agent": "backend",
  "story_id": "STORY-1",
  "github_issue": 1,
  "status": "in_progress",
  "step": "green",
  "message": "Backend Agent: Generated implementation code, tests passing",
  "branch": "feature/1-user-registration-api",
  "files_created": 5,
  "tests_passing": 2,
  "timestamp": "2025-12-04T10:37:15Z"
}

{
  "type": "agent_complete",
  "execution_id": "uuid",
  "agent": "backend",
  "story_id": "STORY-1",
  "github_issue": 1,
  "status": "completed",
  "message": "Pull request merged, issue closed",
  "pr_number": 1,
  "pr_url": "https://github.com/urbantech/my-saas-app/pull/1",
  "commits": 3,
  "files_changed": 5,
  "lines_added": 156,
  "timestamp": "2025-12-04T10:40:00Z"
}
```

**Database Record Updates** (Per agent completion):
```json
{
  "execution_id": "uuid",
  "current_stage": 10,
  "stories_completed": [
    {
      "story_id": "STORY-1",
      "agent": "backend",
      "github_issue": 1,
      "branch": "feature/1-user-registration-api",
      "pr_number": 1,
      "pr_merged": true,
      "commits": 3,
      "files_changed": 5,
      "tests_passing": 2,
      "completed_at": "2025-12-04T10:40:00Z"
    }
  ],
  "stories_in_progress": [
    {
      "story_id": "STORY-2",
      "agent": "frontend",
      "status": "green"
    }
  ],
  "updated_at": "2025-12-04T10:40:00Z"
}
```

**Output** (After all stories complete):
- ✅ All 15 stories completed by specialized agents
- ✅ 15 feature branches created
- ✅ 15 pull requests created and merged
- ✅ 15 GitHub issues closed
- ✅ All code follows SSCS standards
- ✅ TDD workflow (Red → Green → Refactor) applied
- ✅ NO Claude/Anthropic branding in commits/PRs
- ✅ All files stored in MinIO via ZeroDB API
- ✅ Test coverage >90%
- → Proceeds to Stage 11

---

### **STAGE 11: Final Validation & Deployment Preparation**

**Location**: Backend (Agent Execution)
**Agent**: QA Agent + DevOps Agent
**Dependencies**: Stage 10 completion
**Purpose**: Validate all code merged, run final E2E tests, prepare deployment

**What Happens**:
1. QA Agent validates all PRs merged
2. QA Agent runs comprehensive E2E test suite
3. QA Agent records test videos
4. DevOps Agent verifies deployment configuration
5. DevOps Agent prepares Railway deployment
6. System generates final project summary
7. User notified of completion

**QA Validation**:
```python
# QA Agent validates all stories completed
validation_results = await qa_agent.validate_completion(
    github_issues=execution.github_issues,
    repo_info=execution.github_repository
)

# Check all PRs merged
for issue_mapping in execution.github_issues:
    issue = await github_mcp.get_issue(
        owner=repo_owner,
        repo=repo_name,
        issue_number=issue_mapping['github_issue_number'],
        github_token=github_token
    )

    if issue['state'] != 'closed':
        raise Exception(f"Issue #{issue['number']} not closed")

    # Verify PR merged
    pr_number = extract_pr_number(issue['body'])
    pr = await github_mcp.get_pull_request(
        owner=repo_owner,
        repo=repo_name,
        pull_number=pr_number,
        github_token=github_token
    )

    if not pr['merged']:
        raise Exception(f"PR #{pr_number} not merged")
```

**Comprehensive E2E Testing**:
```python
# QA Agent runs full E2E test suite with video recording
e2e_results = await qa_agent.run_e2e_tests(
    repo_url=execution.github_repository['url'],
    branch='develop',
    video_recording=True
)

# Deploy app locally for testing
deployment_url = await qa_agent.deploy_for_testing(
    project_path=f"/tmp/{execution.id}",
    framework="react"  # from project config
)

# Run Playwright tests
test_results = await qa_agent.run_playwright_tests(
    base_url=deployment_url,
    test_suite="comprehensive",
    video_dir=f"/tmp/{execution.id}/videos"
)

# Upload test videos to MinIO
for video_file in test_results['videos']:
    await minio_service.upload_file(
        bucket="agent-swarm-test-videos",
        file_path=f"{execution.id}/e2e-tests/{os.path.basename(video_file)}",
        content=open(video_file, 'rb').read()
    )

# Store test results in ZeroDB RLHF
await zerodb_service.rlhf_log_interaction(
    workflow_id=execution.id,
    agent_id="qa",
    test_results=test_results,
    video_artifacts=test_results['videos'],
    success=test_results['success_rate'] > 0.9
)
```

**Deployment Preparation**:
```python
# DevOps Agent prepares Railway deployment
deployment_config = await devops_agent.prepare_deployment(
    project=project,
    repo_info=execution.github_repository
)

# Create railway.json
railway_config = {
    "build": {
        "builder": "NIXPACKS",
        "buildCommand": "npm run build"
    },
    "deploy": {
        "startCommand": "npm start",
        "healthcheckPath": "/health",
        "restartPolicyType": "ON_FAILURE"
    }
}

# Commit deployment config
await github_mcp.create_commit(
    owner=repo_owner,
    repo=repo_name,
    branch='develop',
    message="chore: add Railway deployment configuration",
    files=[{
        "path": "railway.json",
        "content": json.dumps(railway_config, indent=2)
    }],
    github_token=github_token
)
```

**Final Project Summary**:
```python
# Generate comprehensive project summary
summary = {
    "execution_id": execution.id,
    "project_name": project.name,
    "execution_time_minutes": (datetime.utcnow() - execution.started_at).total_seconds() / 60,
    "stories_completed": len(execution.github_issues),
    "total_points": project.backlog['total_points'],
    "github_repository": execution.github_repository['url'],
    "branches_created": 15,
    "pull_requests_merged": 15,
    "issues_closed": 15,
    "commits_total": sum(story['commits'] for story in execution.stories_completed),
    "files_created": sum(story['files_changed'] for story in execution.stories_completed),
    "lines_of_code": sum(story['lines_added'] for story in execution.stories_completed),
    "test_coverage": e2e_results['coverage_percentage'],
    "test_videos": len(e2e_results['videos']),
    "deployment_ready": True,
    "next_steps": [
        "1. Review repository: " + execution.github_repository['url'],
        "2. Connect Railway to GitHub repository",
        "3. Set environment variables in Railway",
        "4. Deploy to production with 'railway up'",
        "5. Configure custom domain (optional)"
    ]
}

# Store summary in database
execution.completion_summary = summary
execution.status = "completed"
execution.completed_at = datetime.utcnow()
await db.commit()
```

**WebSocket Final Update**:
```json
{
  "type": "execution_complete",
  "execution_id": "uuid",
  "status": "completed",
  "message": "Agent Swarm execution completed successfully!",
  "summary": {
    "execution_time": "14 minutes 32 seconds",
    "stories_completed": 15,
    "total_points": 42,
    "github_repository": "https://github.com/urbantech/my-saas-app",
    "pull_requests_merged": 15,
    "test_coverage": 94,
    "deployment_ready": true
  },
  "next_steps": [
    "Review repository",
    "Connect Railway",
    "Deploy to production"
  ],
  "timestamp": "2025-12-04T10:45:00Z"
}
```

**Dashboard Display**:
```
┌────────────────────────────────────────────────────────┐
│         Agent Swarm Execution Complete! 🎉              │
├────────────────────────────────────────────────────────┤
│ Execution Time: 14 minutes 32 seconds                  │
│ Stories Completed: 15/15 ✅                             │
│ Total Points: 42                                        │
│                                                         │
│ GitHub Repository:                                      │
│ https://github.com/urbantech/my-saas-app               │
│                                                         │
│ Statistics:                                             │
│ - Pull Requests Merged: 15                              │
│ - Issues Closed: 15                                     │
│ - Commits: 45                                           │
│ - Files Created: 60                                     │
│ - Lines of Code: 4,567                                  │
│ - Test Coverage: 94%                                    │
│ - Test Videos: 15                                       │
│                                                         │
│ Next Steps:                                             │
│ 1. Review repository ↗                                  │
│ 2. Connect Railway to GitHub                            │
│ 3. Set environment variables                            │
│ 4. Deploy to production                                 │
│                                                         │
│ [View Repository] [Download Test Videos] [Deploy Now]  │
└────────────────────────────────────────────────────────┘
```

**Output**:
- ✅ All 15 stories validated and closed
- ✅ Comprehensive E2E tests completed (94% coverage)
- ✅ Test videos uploaded to MinIO
- ✅ Railway deployment configuration committed
- ✅ Final project summary generated
- ✅ User notified of completion
- ✅ Ready for production deployment

---

## SSCS Integration

### Semantic Seed Venture Studio Coding Standards v2.0

**Applied Throughout Stages 8-11**

#### 1. Branch Naming Convention
```bash
# SSCS Requirement: Branch names follow pattern
feature/{issue-id}-{slug}
bug/{issue-id}-{slug}
chore/{issue-id}-{slug}

# Examples:
feature/1-user-registration-api
bug/7-login-token-expiration
chore/12-deployment-config
```

#### 2. TDD Workflow (Red → Green → Refactor)
```bash
# SSCS Requirement: All stories follow TDD

# Red: Write failing tests first
git commit -m "WIP: red tests for user registration"

# Green: Minimal code to pass tests
git commit -m "green: user registration endpoint with JWT auth"

# Refactor: Improve code quality
git commit -m "refactor: extract password utilities and improve error handling"
```

#### 3. Commit Message Format
```bash
# SSCS Requirement: Clear, professional messages
# ❌ FORBIDDEN: Any Claude/Anthropic/AI branding

# ✅ CORRECT Examples:
git commit -m "green: user registration endpoint with JWT auth"
git commit -m "refactor: extract password utilities"
git commit -m "WIP: red tests for dashboard analytics"

# ❌ FORBIDDEN Examples:
git commit -m "🤖 Generated with Claude Code"
git commit -m "Co-Authored-By: Claude <noreply@anthropic.com>"
git commit -m "AI-generated user registration"
```

#### 4. Story Types & Estimation
```bash
# SSCS Requirement: Fibonacci points (0, 1, 2, 3, 5, 8)

0 points: Trivial (typo fix, tiny UI change)
1 point:  Clear, contained task
2 points: Slightly complex, well-defined
3 points: Moderate complexity
5 points: Large - should be split






8 points: Very large - must be split
```

#### 5. Pull Request Template
```markdown
# SSCS Requirement: Complete PR descriptions

## Problem/Context
[What issue are we solving?]

## Solution Summary
[How did we solve it?]

## Test Plan
[Commands + expected results]

## Risk/Rollback
[What could go wrong? How to revert?]

## Story Link
- **Story**: STORY-X
- **Issue**: #X
- **Type**: feature | bug | chore
- **Estimate**: X points
```

#### 6. Testing Strategy (BDD)
```python
# SSCS Requirement: BDD-style tests (describe/it)

describe('User Registration API', () => {
    describe('POST /api/auth/register', () => {
        it('should create a new user with valid credentials', async () => {
            # Given
            user_data = {...}

            # When
            response = await client.post("/api/auth/register", json=user_data)

            # Then
            assert response.status_code == 201
        })
    })
})
```

#### 7. Code Quality Standards
```python
# SSCS Requirements:

# 1. Naming: camelCase for vars/functions, PascalCase for classes
def createUser(userData: UserCreate):  # ✅
def create_user(user_data: UserCreate):  # ❌ (snake_case)

# 2. Formatting: 4-space indentation, ≤80 chars per line
def register(
    user_data: UserCreate,
    db: Session = Depends(get_db)
):  # ✅

# 3. Comments: Meaningful, current; delete stale
# Create user account and send confirmation email  # ✅
# TODO: fix this later  # ❌ (not actionable)

# 4. Security: Never log secrets/PII
logger.info(f"User registered: {user.email}")  # ✅
logger.info(f"Password: {user.password}")  # ❌ (FORBIDDEN)

# 5. Errors: Explicit error types, structured logs
raise HTTPException(status_code=400, detail="Email already registered")  # ✅
raise Exception("Error")  # ❌ (not specific)
```

#### 8. CI/CD Gates
```yaml
# SSCS Requirement: CI pipeline gates

# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [develop, main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v3

      - name: Install dependencies
        run: npm install

      - name: Lint
        run: npm run lint

      - name: Type check
        run: npm run typecheck

      - name: Unit tests
        run: npm run test:unit

      - name: Integration tests
        run: npm run test:integration

      - name: Build
        run: npm run build
```

#### 9. Acceptance Checklist
```markdown
# SSCS Requirement: Before marking "Delivered"

- [ ] Story type + estimate stated
- [ ] Branch follows convention (feature/bug/chore-{id}-{slug})
- [ ] Red→Green→Refactor commits present
- [ ] Tests added/updated and passing locally & in CI
- [ ] Security/a11y considerations addressed (if UI)
- [ ] PR description complete with evidence
- [ ] Staging deploy verified (or verification plan included)
- [ ] NO Claude/Anthropic branding in commits/PRs
```

---

## Agent Roles & Responsibilities

### 1. **Product Manager Agent**
- **Stages**: 4, 5, 9
- **Responsibilities**:
  - Generate Agile backlog from PRD
  - Score user stories with Fibonacci points
  - Create sprint plan with time estimates
  - Publish backlog as GitHub issues
  - Track progress and update stakeholders

### 2. **Architect Agent**
- **Stages**: 3
- **Responsibilities**:
  - Analyze PRD requirements
  - Generate ZeroDB-aligned data model
  - Design system architecture
  - Create Architecture Decision Records (ADRs)

### 3. **DevOps Agent**
- **Stages**: 8, 11
- **Responsibilities**:
  - Create GitHub repository (user's token)
  - Set up branch protection rules
  - Configure CI/CD pipelines
  - Prepare deployment configurations (Railway)
  - Manage infrastructure as code

### 4. **Backend Agent**
- **Stages**: 10
- **Responsibilities**:
  - Implement API endpoints (FastAPI)
  - Create database models (SQLAlchemy + ZeroDB)
  - Write service layer business logic
  - Implement authentication/authorization
  - Follow TDD: Red → Green → Refactor
  - Store code in MinIO via ZeroDB API

### 5. **Frontend Agent**
- **Stages**: 10
- **Responsibilities**:
  - Generate React/Vue/Angular components
  - Implement UI pages and layouts
  - Create API client and service layer
  - Implement state management
  - Follow TDD: Red → Green → Refactor
  - Store code in MinIO via ZeroDB API

### 6. **QA Agent**
- **Stages**: 10, 11
- **Responsibilities**:
  - Write E2E tests (Playwright)
  - Execute comprehensive test suites
  - Record test videos
  - Validate test coverage (>90%)
  - Feed results to RLHF pipeline
  - Validate all PRs merged before completion

---

## GitHub Integration Flow

### User Token Setup
1. User navigates to: **Settings → Integrations → GitHub**
2. User creates GitHub Personal Access Token with scopes:
   - `repo` (full repository access)
   - `workflow` (GitHub Actions)
3. User pastes token in AINative dashboard
4. Token encrypted and stored in database
5. Token used by DevOps Agent and all agents for GitHub operations

### Repository Structure
```
my-saas-app/
├── .github/
│   └── workflows/
│       ├── ci.yml              # CI pipeline
│       └── deploy.yml          # Deployment pipeline
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── services/
│   │   └── App.tsx
│   ├── package.json
│   └── vite.config.ts
├── backend/
│   ├── app/
│   │   ├── api/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   └── requirements.txt
├── docs/
│   └── architecture.md
├── railway.json
├── docker-compose.yml
├── .gitignore
└── README.md
```

### Branch Strategy
- **main**: Protected, production-ready code
- **develop**: Default branch, all PRs merge here
- **feature/{issue-id}-{slug}**: Feature branches
- **bug/{issue-id}-{slug}**: Bug fix branches
- **chore/{issue-id}-{slug}**: Chore branches

### Issue Labels
- `feature` - New functionality
- `bug` - Bug fixes
- `chore` - Non-functional tasks
- `points-0`, `points-1`, `points-2`, `points-3`, `points-5`, `points-8` - Story points
- `agent-frontend`, `agent-backend`, `agent-qa`, `agent-devops` - Agent assignments
- `epic-1`, `epic-2`, etc. - Epic groupings
- `in-progress`, `in-review`, `delivered` - Status tracking

---

## MinIO Storage Strategy

### Storage via ZeroDB API
All file storage uses ZeroDB's MinIO integration, not direct MinIO access.

### Bucket Structure
```
agent-swarm-projects/
└── {execution-id}/
    ├── frontend/
    │   ├── src/
    │   │   ├── components/
    │   │   ├── pages/
    │   │   └── App.tsx
    │   ├── package.json
    │   └── vite.config.ts
    ├── backend/
    │   ├── app/
    │   │   ├── api/
    │   │   ├── models/
    │   │   └── main.py
    │   └── requirements.txt
    └── deployment/
        ├── railway.json
        └── Dockerfile

agent-swarm-test-videos/
└── {execution-id}/
    └── e2e-tests/
        ├── user-registration.webm
        ├── login-flow.webm
        ├── dashboard-view.webm
        └── ...
```

### File Upload Flow
```python
# Agents store files via ZeroDB API
from app.zerodb.services.minio_service import MinIOService

minio_service = MinIOService(
    project_id=settings.ZERODB_PROJECT_ID,
    api_key=settings.ZERODB_API_KEY
)

# Upload code file
await minio_service.upload_file(
    bucket="agent-swarm-projects",
    file_path=f"{execution.id}/backend/app/main.py",
    content=code_content,
    content_type="text/x-python"
)

# Upload test video
await minio_service.upload_file(
    bucket="agent-swarm-test-videos",
    file_path=f"{execution.id}/e2e-tests/user-registration.webm",
    content=video_bytes,
    content_type="video/webm"
)
```

### File Metadata
```json
{
  "execution_id": "uuid",
  "file_path": "backend/app/main.py",
  "bucket": "agent-swarm-projects",
  "size_bytes": 4567,
  "content_type": "text/x-python",
  "created_by": "backend_agent",
  "created_at": "2025-12-04T10:38:00Z",
  "checksum": "sha256-abc123...",
  "github_path": "backend/app/main.py",
  "github_commit": "abc123def456"
}
```

---

## Implementation Gaps

### Current Status vs Specification

Based on this workflow specification, here are the **implementation gaps** that need to be addressed:

#### ✅ **COMPLETED** (Stages that work correctly):
1. ✅ Stage 1: Project creation
2. ✅ Stage 2: PRD upload/generation
3. ✅ Stage 8: GitHub repository creation (user token integration working)

#### ⚠️ **PARTIALLY IMPLEMENTED** (Needs work):
4. ⚠️ Stage 3: Data model generation exists, but **not ZeroDB-optimized**
5. ⚠️ Stage 4: Backlog generation exists, but **not following SSCS format**
6. ⚠️ Stage 5: Sprint planning exists, but **no single agent vs swarm comparison**
7. ⚠️ Stage 10: Agents work on code, but **NOT following SSCS workflow** (Red→Green→Refactor missing)
8. ⚠️ Stage 11: Testing exists, but **no final validation stage**

#### ❌ **MISSING** (Not implemented):
9. ❌ Stage 6: User sprint plan acceptance flow (dashboard UI missing)
10. ❌ Stage 7: Launch button with real-time progress (WebSocket missing)
11. ❌ Stage 9: Backlog → GitHub Issues publishing (Product Manager Agent missing)
12. ❌ SSCS Integration: Agents **NOT following** Red→Green→Refactor TDD workflow
13. ❌ SSCS Integration: Commit messages **may contain** Claude/Anthropic branding (needs audit)
14. ❌ SSCS Integration: Branch naming **not following** feature/{issue-id}-{slug} pattern
15. ❌ MinIO Storage: Files **not stored** in ZeroDB MinIO buckets during execution

### Priority Fixes Needed:

**HIGH PRIORITY**:
1. **Stage 9**: Implement Product Manager Agent to publish backlog as GitHub issues
2. **Stage 10**: Refactor agent execution to follow SSCS TDD (Red→Green→Refactor)
3. **SSCS Compliance**: Remove all Claude/Anthropic branding from commit messages and PRs
4. **SSCS Compliance**: Implement branch naming convention (feature/{issue-id}-{slug})

**MEDIUM PRIORITY**:
5. **Stage 5**: Add single agent vs agent swarm time comparison
6. **Stage 6**: Implement dashboard sprint plan acceptance UI
7. **Stage 7**: Add WebSocket real-time progress updates
8. **MinIO Integration**: Store all code files in ZeroDB MinIO during execution

**LOW PRIORITY**:
9. **Stage 3**: Optimize data model for ZeroDB (vector search, caching)
10. **Stage 11**: Add final validation stage with comprehensive checks

---

## Next Steps

1. **Review this specification** for accuracy and completeness
2. **Validate current implementation** against this workflow
3. **Identify implementation gaps** (see section above)
4. **Prioritize missing features** for development
5. **Update codebase** to match specification
6. **Test end-to-end workflow** with real project

---

**Document Status**: ✅ Complete - Ready for Implementation Validation
**Last Updated**: 2025-12-04
**Maintained By**: AINative Development Team
