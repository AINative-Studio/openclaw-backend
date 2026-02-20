# AgentSwarm - Complete File Location Map

**Document Type**: File Reference Guide
**Last Updated**: December 5, 2025
**Purpose**: Quick reference for finding any AgentSwarm file

---

## 📋 Table of Contents

1. [Backend Files](#backend-files)
2. [Frontend Files](#frontend-files)
3. [Documentation Files](#documentation-files)
4. [Test Files](#test-files)
5. [SDK Files](#sdk-files)
6. [CI/CD Files](#cicd-files)
7. [Configuration Files](#configuration-files)

---

## 🔙 Backend Files

### Core API Router

**Location**: `/Users/aideveloper/core/src/backend/app/api/api_v1/endpoints/agent_swarms.py`
**Size**: ~1,200 lines
**Purpose**: Main public API endpoints for AgentSwarm

**Key Endpoints**:
```python
# Line ~50: Router setup
router = APIRouter(prefix="/agent-swarms", tags=["agent-swarms"])

# Line ~123: Create project
@router.post("/projects", response_model=AgentSwarmProject)
async def create_project(...)

# Line ~234: Upload PRD
@router.post("/projects/{project_id}/prd")
async def upload_prd(project_id: str, file: UploadFile)

# Line ~345: Generate data model (Stage 3)
@router.post("/projects/{project_id}/ai/generate-data-model")
async def generate_data_model(project_id: str)

# Line ~456: Generate backlog (Stage 4)
@router.post("/projects/{project_id}/ai/generate-backlog")
async def generate_backlog(project_id: str)

# Line ~567: Generate sprint plan (Stage 5)
@router.post("/projects/{project_id}/ai/generate-sprint-plan")
async def generate_sprint_plan(project_id: str, agent_count: int)

# Line ~675: Get GitHub status
@router.get("/projects/{project_id}/github", response_model=GitHubStatus)
async def get_github_status(project_id: str)

# Line ~789: Launch swarm (Stage 10)
@router.post("/projects/{project_id}/launch")
async def launch_swarm(project_id: str, github_pat: str)

# Line ~890: Get project status
@router.get("/projects/{project_id}")
async def get_project(project_id: str)

# Line ~1000: List all projects
@router.get("/projects")
async def list_projects(skip: int = 0, limit: int = 100)

# Line ~1100: Delete project
@router.delete("/projects/{project_id}")
async def delete_project(project_id: str)
```

---

### Workflow State Machine

**Location**: `/Users/aideveloper/core/src/backend/app/agents/swarm/application_workflow.py`
**Size**: 325,902 bytes (~8,000 lines)
**Purpose**: Core workflow orchestration and stage execution

**Key Classes & Methods**:
```python
# Line ~50: Workflow stages enum
class WorkflowStage(str, Enum):
    PROJECT_CREATION = "project_creation"        # Stage 1
    PRD_UPLOAD = "prd_upload"                   # Stage 2
    DATA_MODEL_GENERATION = "data_model"        # Stage 3
    BACKLOG_CREATION = "backlog"                # Stage 4
    SPRINT_PLANNING = "sprint_plan"             # Stage 5
    EXECUTION_SETUP = "execution_setup"         # Stage 6
    GITHUB_REPO_CREATION = "github_repo"        # Stage 7
    DOCUMENTATION_COMMIT = "documentation"      # Stage 8
    GITHUB_ISSUE_IMPORT = "github_issues"       # Stage 9 (NOT IMPLEMENTED)
    LAUNCH_SWARM = "launch_swarm"               # Stage 10
    CODE_GENERATION = "code_generation"         # Stage 11

# Line ~200: Main workflow class
class ApplicationWorkflow:
    def __init__(self, project_id: str, zerodb_service, github_service)

    # Line ~300: Execute full workflow
    async def execute_workflow(self) -> Dict[str, Any]

    # Line ~456: Generate data model (Stage 3)
    async def generate_data_model(self) -> Dict[str, Any]
        # Uses LLM to analyze PRD
        # Generates ZeroDB-first schema
        # Stores schema in ZeroDB

    # Line ~589: Generate backlog (Stage 4)
    async def generate_backlog(self) -> Dict[str, Any]
        # Parses PRD for features
        # Creates Epics and User Stories
        # Estimates story points (Fibonacci)
        # Generates backlog.md

    # Line ~723: Generate sprint plan (Stage 5)
    async def generate_sprint_plan(self, agent_count: int) -> Dict[str, Any]
        # Calculates velocity: agent_count * 5 SP/day
        # Creates sprint timeline
        # Assigns agents to workstreams
        # Generates sprint_plan.md

    # Line ~890: Setup GitHub repo (Stage 7)
    async def setup_github_repository(self, repo_name: str, pat: str) -> Dict[str, Any]

    # Line ~1050: Commit docs to GitHub (Stage 8)
    async def commit_documentation(self) -> Dict[str, Any]

    # Line ~1200: Launch agent swarm (Stage 10)
    async def launch_agent_swarm(self) -> Dict[str, Any]
```

**Important Notes**:
- This is the LARGEST file in the project (325KB)
- Contains ALL workflow logic for stages 1-11
- Critical dependency on ZeroDB and GitHub services

---

### Agent Orchestration

**Location**: `/Users/aideveloper/core/src/backend/app/agents/swarm/agent_swarm.py`
**Size**: 27,418 bytes (~700 lines)
**Purpose**: Multi-agent coordination and parallel execution

**Key Classes & Methods**:
```python
# Line ~30: Main agent swarm class
class AgentSwarm:
    def __init__(self, project_id: str, num_agents: int = 3)

    # Line ~100: Assign agents to tasks
    async def assign_agents_to_tasks(self, tasks: List[Task]) -> Dict[str, List[Task]]
        # Distributes tasks across available agents
        # Considers agent specialization (frontend, backend, qa)
        # Returns agent_id -> tasks mapping

    # Line ~234: Execute agents in parallel
    async def execute_parallel(self, agent_assignments: Dict[str, List[Task]]) -> List[AgentResult]
        # Uses asyncio.gather() for parallel execution
        # Each agent gets isolated workspace
        # Returns aggregated results

    # Line ~356: Monitor agent progress
    async def monitor_progress(self) -> Dict[str, float]
        # Real-time progress tracking
        # Returns completion percentage per agent

    # Line ~450: Synthesize agent results
    async def synthesize_results(self, results: List[AgentResult]) -> Dict[str, Any]
        # Coordinator agent combines sub-agent work
        # Resolves conflicts
        # Creates final unified codebase
```

---

### Individual Agent

**Location**: `/Users/aideveloper/core/src/backend/app/agents/swarm/swarm_agent.py`
**Size**: 89,229 bytes (~2,200 lines)
**Purpose**: Individual agent implementation (Backend, Frontend, QA, etc.)

**Key Classes & Methods**:
```python
# Line ~50: Swarm agent class
class SwarmAgent:
    def __init__(self, agent_id: str, role: str, workspace_path: str)

    # Line ~89: Execute assigned tasks
    async def execute_tasks(self, tasks: List[Task], github_pat: str) -> AgentResult
        # Clone repo to workspace
        # Create feature branch
        # Generate code for each task
        # Run TDD cycle (Red -> Green -> Refactor)
        # Commit changes
        # Push to GitHub
        # Upload code to MinIO

    # Line ~234: Generate code following TDD
    async def generate_code_tdd(self, task: Task) -> str
        # RED: Write failing test first
        # GREEN: Write minimal code to pass
        # REFACTOR: Clean up code
        # Verify custom rules compliance

    # Line ~456: Apply custom coding rules
    async def apply_custom_rules(self, code: str, rules: List[Rule]) -> str
        # Validates code against user's custom standards
        # Enforces SSCS compliance
        # Returns validated/fixed code

    # Line ~678: Commit to GitHub
    async def commit_and_push(self, files: List[str], message: str) -> bool
        # Proper git commit with AINative branding
        # Follows semantic commit format
        # Pushes to feature branch

    # Line ~890: Upload code to MinIO
    async def upload_to_minio(self, code_archive: bytes) -> str
        # Stores generated code in ZeroDB/MinIO
        # Returns file_id for retrieval
```

---

### Sub-Agent Orchestrator (New - Anthropic SDK)

**Location**: `/Users/aideveloper/core/src/backend/app/agents/swarm/sub_agent_orchestrator.py`
**Size**: 32,589 bytes (~800 lines)
**Purpose**: Coordinator + sub-agent pattern with extended thinking

**Key Classes & Methods**:
```python
# Line ~30: Sub-agent orchestrator
class SubAgentOrchestrator:
    def __init__(self, anthropic_client: AnthropicMessagesProvider)

    # Line ~70: Plan and execute with extended thinking
    async def plan_and_execute(self, user_request: str, project_id: str) -> Dict[str, Any]
        # Coordinator uses extended thinking (Claude 3.7)
        # Breaks down into atomic tasks
        # Spawns sub-agents with isolated contexts
        # Synthesizes results

    # Line ~150: Execute single sub-agent task
    async def _execute_sub_agent_task(self, task: Dict, project_id: str) -> Dict[str, Any]
        # Creates isolated conversation context
        # Executes task independently
        # Returns result with tool uses

    # Line ~250: Parse coordinator plan
    def _parse_coordinator_plan(self, response) -> List[Dict]
        # Extracts task breakdown from coordinator
        # Validates task structure
        # Returns list of tasks for sub-agents
```

---

### GitHub Service

**Location**: `/Users/aideveloper/core/src/backend/app/services/project_github_service.py`
**Size**: ~1,500 lines
**Purpose**: GitHub API integration

**Key Classes & Methods**:
```python
# Line ~45: Create GitHub repository
async def create_repository(
    repo_name: str,
    description: str,
    pat: str,
    is_private: bool = False
) -> Dict[str, Any]:
    # Creates repo via GitHub API
    # Initializes with .gitignore, README, LICENSE
    # Returns repo URL and metadata

# Line ~156: Commit documentation files
async def commit_documentation(
    repo_name: str,
    files: Dict[str, str],  # filename -> content
    pat: str
) -> bool:
    # Commits multiple .md files to docs/ folder
    # Uses proper commit message format
    # Returns success status

# Line ~267: Create feature branch
async def create_branch(
    repo_name: str,
    branch_name: str,
    pat: str,
    from_branch: str = "main"
) -> bool:

# Line ~345: Create pull request
async def create_pull_request(
    repo_name: str,
    head_branch: str,
    base_branch: str,
    title: str,
    body: str,
    pat: str
) -> Dict[str, Any]:

# Line ~456: Create GitHub issue
async def create_issue(
    repo_name: str,
    title: str,
    body: str,
    labels: List[str],
    assignees: List[str],
    milestone: Optional[int],
    pat: str
) -> Dict[str, Any]:
    # This should be called by Stage 9 (NOT IMPLEMENTED YET)

# Line ~567: Create milestone
async def create_milestone(
    repo_name: str,
    title: str,
    description: str,
    due_on: datetime,
    pat: str
) -> Dict[str, Any]:
```

---

### ZeroDB Integration Service

**Location**: `/Users/aideveloper/core/src/backend/app/services/zerodb_integration_service.py`
**Size**: ~2,000 lines (if fully implemented)
**Status**: ⚠️ PARTIAL (60% implemented)
**Purpose**: Complete ZeroDB API wrapper

**Key Methods** (some not yet implemented):
```python
class ZeroDBIntegrationService:
    # === File Operations (IMPLEMENTED ✅) ===

    # Line ~50: Upload file
    async def upload_file(self, project_id: str, file: UploadFile) -> Dict[str, Any]

    # Line ~100: Download file
    async def download_file(self, project_id: str, file_id: str) -> bytes

    # Line ~150: List files
    async def list_files(self, project_id: str) -> List[Dict[str, Any]]

    # === NoSQL Tables (PARTIAL ⚠️) ===

    # Line ~200: Create table
    async def create_table(self, project_id: str, table_name: str, schema: Dict)

    # Line ~250: Insert rows
    async def insert_rows(self, project_id: str, table_name: str, rows: List[Dict])

    # Line ~300: Query rows
    async def query_rows(self, project_id: str, table_name: str, filter: Dict)

    # === Vector Operations (NOT IMPLEMENTED ❌) ===

    # TODO: Upsert vectors
    async def upsert_vectors(self, project_id: str, vectors: List[Dict])

    # TODO: Vector search
    async def vector_search(self, project_id: str, query_vector: List[float], top_k: int)

    # === Embeddings (NOT IMPLEMENTED ❌) ===

    # TODO: Generate embeddings
    async def generate_embeddings(self, project_id: str, text: str) -> List[float]

    # TODO: Semantic search
    async def semantic_search(self, project_id: str, query: str, top_k: int)

    # === Memory Management (NOT IMPLEMENTED ❌) ===

    # TODO: Store memory
    async def store_memory(self, project_id: str, content: str, metadata: Dict)

    # TODO: Search memories
    async def search_memory(self, project_id: str, query: str, limit: int)

    # === RLHF (NOT IMPLEMENTED ❌) ===

    # TODO: Log interaction
    async def log_rlhf_interaction(self, project_id: str, prompt: str, response: str, rating: int)

    # TODO: Get RLHF stats
    async def get_rlhf_stats(self, project_id: str) -> Dict[str, Any]
```

---

### Kong + Celery Integration

**Location**: `/Users/aideveloper/core/src/backend/app/agents/swarm/kong_celery_integration.py`
**Size**: 19,591 bytes (~500 lines)
**Purpose**: Async task queue for long-running agent operations

**Key Methods**:
```python
# Line ~50: Celery task for agent execution
@celery_app.task(bind=True)
def execute_agent_task(self, agent_id: str, tasks: List[Dict]) -> Dict[str, Any]:
    # Runs agent in background
    # Reports progress to Redis
    # Returns result when complete

# Line ~150: Kong rate limiting integration
async def rate_limit_check(user_id: str, endpoint: str) -> bool:
    # Checks Kong rate limits
    # Returns True if request allowed

# Line ~250: Task progress monitoring
async def get_task_progress(task_id: str) -> Dict[str, Any]:
    # Fetches progress from Redis
    # Returns percentage complete + status
```

---

### WebSocket Handler (Planned)

**Location**: `/Users/aideveloper/core/src/backend/app/websocket/agent_swarm_ws.py`
**Size**: ~500 lines (when implemented)
**Status**: 📋 PLANNED (not fully working)
**Purpose**: Real-time updates to frontend

**Planned Structure**:
```python
@router.websocket("/ws/agent-swarm/{project_id}")
async def agent_swarm_websocket(websocket: WebSocket, project_id: str):
    await websocket.accept()

    # Subscribe to Redis pub/sub for agent updates
    # Stream progress to frontend
    # Handle disconnections gracefully
```

---

### Database Models

**Location**: `/Users/aideveloper/core/src/backend/app/models/`

**agent_swarm_workflow.py** (~300 lines):
```python
# Line ~20: Workflow model
class AgentSwarmWorkflow(Base):
    __tablename__ = "agent_swarm_workflows"

    id: UUID
    user_id: UUID
    project_id: UUID
    current_stage: WorkflowStage
    status: str  # 'in_progress', 'completed', 'failed'
    created_at: datetime
    completed_at: Optional[datetime]
```

**agent_swarm_rules.py** (~200 lines):
```python
# Line ~20: Custom rules model
class AgentSwarmRules(Base):
    __tablename__ = "agent_swarm_rules"

    id: UUID
    workflow_id: UUID
    rules_content: str  # Markdown format
    parsed_rules: JSON  # Structured rules
    created_at: datetime
```

---

### Specialized Agents

**Location**: `/Users/aideveloper/core/src/backend/app/agents/swarm/specialized/`

Total: ~61,728 lines across 16 files

**Key Specialized Agents**:
1. **architect_agent.py** (~1,500 lines) - Project structure
2. **backend_agent.py** (~2,000 lines) - API endpoints
3. **frontend_agent.py** (~2,500 lines) - UI components
4. **qa_agent.py** (~1,800 lines) - Testing
5. **devops_agent.py** (~1,200 lines) - Deployment
6. **database_agent.py** (~1,500 lines) - Schema design
7. **security_agent.py** (~1,000 lines) - Auth & permissions
8. **performance_agent.py** (~900 lines) - Optimization

---

## 🎨 Frontend Files

### Main Dashboard

**Location**: `/Users/aideveloper/core/AINative-website/src/pages/dashboard/AgentSwarmDashboard.tsx`
**Size**: 1,813 lines
**Purpose**: Main UI orchestration for AgentSwarm workflow

**Key Components**:
```tsx
// Line ~50: Main dashboard component
export default function AgentSwarmDashboard() {
  const [currentStage, setCurrentStage] = useState<number>(1);
  const [project, setProject] = useState<Project | null>(null);

  // Line ~150: Handle PRD upload
  const handlePRDUpload = async (file: File) => { ... }

  // Line ~234: Handle data model generation
  const handleGenerateDataModel = async () => { ... }

  // Line ~345: Handle backlog generation
  const handleGenerateBacklog = async () => { ... }

  // Line ~456: Handle sprint plan generation
  const handleGenerateSprintPlan = async (agentCount: number) => { ... }

  // Line ~567: Handle GitHub setup
  const handleGitHubSetup = async (pat: string) => { ... }

  // Line ~678: Handle swarm launch
  const handleLaunchSwarm = async () => { ... }

  // Line ~789: Render workflow stepper
  return (
    <WorkflowStepper currentStage={currentStage}>
      {/* All 11 stages rendered here */}
    </WorkflowStepper>
  )
}
```

---

### API Service Layer

**Location**: `/Users/aideveloper/core/AINative-website/src/services/AgentSwarmService.ts`
**Size**: 267+ lines
**Purpose**: Type-safe API client for all AgentSwarm endpoints

**Key Methods**:
```typescript
// Line ~30: Create project
async createProject(name: string, description: string): Promise<Project>

// Line ~67: Upload PRD
async uploadPRD(projectId: string, file: File): Promise<UploadResult>

// Line ~123: Generate data model
async generateDataModel(projectId: string): Promise<DataModel>

// Line ~178: Generate backlog
async generateBacklog(projectId: string): Promise<Backlog>

// Line ~234: Generate sprint plan
async generateSprintPlan(projectId: string, agentCount: number): Promise<SprintPlan>

// Line ~267: Get GitHub status
async getGitHubStatus(projectId: string): Promise<GitHubStatus>

// Line ~312: Launch swarm
async launchSwarm(projectId: string, githubPAT: string): Promise<LaunchResult>

// Line ~356: Get project
async getProject(projectId: string): Promise<Project>

// Line ~401: List projects
async listProjects(skip?: number, limit?: number): Promise<Project[]>
```

---

### UI Components

**Location**: `/Users/aideveloper/core/AINative-website/src/components/`

**1. TimeComparisonCard.tsx** (~400 lines):
```tsx
// Shows comparison between single agent vs multi-agent swarm
// Calculates time savings
// Displays velocity metrics
```

**2. GitHubIntegrationCard.tsx** (~350 lines):
```tsx
// GitHub PAT input
// Repo creation UI
// Status indicators
```

**3. GitHubRepoStatus.tsx** (~300 lines):
```tsx
// Repo health indicators
// Commit count
// Branch status
```

**4. StageIndicator.tsx** (~250 lines):
```tsx
// Visual stage progress (1-11)
// Current stage highlighting
// Completion checkmarks
```

**5. TDDProgressDisplay.tsx** (~400 lines):
```tsx
// Test-driven development metrics
// Red/Green/Refactor cycle status
// Test coverage display
```

**6. CompletionStatistics.tsx** (~300 lines):
```tsx
// Overall project completion %
// Stage-by-stage breakdown
// Estimated time remaining
```

**7. CompletionTimeSummary.tsx** (~250 lines):
```tsx
// Total time elapsed
// Time per stage
// Comparison to estimates
```

**8. ExecutionTimer.tsx** (~200 lines):
```tsx
// Real-time execution timer
// Pause/resume functionality
// Time formatting
```

---

## 📚 Documentation Files

**Location**: `/Users/aideveloper/core/docs/agent-swarm/`

### Core Documentation

**README.md** (14,126 bytes):
- Master index and quick reference
- Links to all documentation
- Quick start commands

**AGENTSWARM_MASTER_CONTEXT.md** (~30,000 lines):
- **START HERE** for AI agents
- Complete system overview
- Critical files reference
- Troubleshooting guide

**AGENTSWARM_HISTORY.md** (~11,404 bytes):
- Evolution timeline
- Version history
- Key milestones
- Lessons learned

**AGENTSWARM_FILE_MAP.md** (This file):
- Complete file location reference
- Line number references
- File sizes and purposes

**AGENTSWARM_REPOSITORY_GUIDE.md** (to be created):
- Infrastructure details
- Repository structure
- Deployment guide

### Subdirectories

**architecture/** (4 files):
- `AGENT_SWARM_WORKFLOW_V2_PRD.md` (19,194 bytes)
- `ENHANCED_AGENT_SWARM_ARCHITECTURE.md` (12,094 bytes)
- `SUB_AGENT_ORCHESTRATOR.md` (16,222 bytes)
- `multi_agent_swarm_architecture_actual.md` (16,829 bytes)

**api/** (2 files):
- `AGENT_SWARM_DOWNLOAD_API.md` (18,382 bytes)
- `ENHANCED_AGENT_SWARM_API_REFERENCE.md` (16,181 bytes)

**guides/** (5 files):
- `AGENT_SDK_INTEGRATION_GUIDE.md` (15,128 bytes)
- `ENHANCED_AGENT_SWARM_BEST_PRACTICES.md` (54,521 bytes)
- `ENHANCED_AGENT_SWARM_INTEGRATION_GUIDE.md` (41,685 bytes)
- `ENHANCED_AGENT_SWARM_MIGRATION_GUIDE.md` (50,883 bytes)
- `SUB_AGENT_QUICK_START.md` (11,404 bytes)

**planning/** (5 files):
- `AGENT_CODING_STANDARDS_FIX_PLAN.md` (10,116 bytes)
- `AGENT_SWARM_COMPREHENSIVE_ANALYSIS_PLAN.md` (25,913 bytes)
- `AGENT_SWARM_ENHANCEMENT_PLAN_REVISED.md` (16,973 bytes)
- `ENHANCED_AGENT_SWARM_COMPLETION_PLAN.md` (13,577 bytes)
- `Revised_Agent_Swarm_Implementation_Plan.md` (8,873 bytes)

**reports/** (10 files):
- `AGENTSWARM_STATUS_REPORT.md` (14,557 bytes)
- `AGENT_DEPLOYMENT_PUSH_SUMMARY.md` (18,855 bytes)
- `AGENT_SWARM_DEPLOYMENT_SUMMARY.md` (15,204 bytes)
- `AGENT_SWARM_KONG_CELERY_INTEGRATION_COMPLETE.md` (8,505 bytes)
- `AGENT_SWARM_V2_COMPREHENSIVE_ANALYSIS.md` (34,707 bytes)
- `AGENT_TASK_ASSIGNMENTS.md` (13,038 bytes)
- `AGENT_WORKFLOW_BUG_REPORT.md` (12,661 bytes)
- `ENHANCED_AGENT_SWARM_CURRENT_STATUS.md` (11,842 bytes)
- `ENHANCED_AGENT_SWARM_FINAL_STATUS_MEMO.md` (8,662 bytes)
- `ENHANCED_AGENT_SWARM_VALIDATION_COMPLETE.md` (7,932 bytes)

**storage/** (4 files):
- `AGENT_SWARM_CODE_STORAGE.md` (8,921 bytes)
- `AGENT_SWARM_STORAGE_ARCHITECTURE.md` (16,423 bytes)
- `AGENT_SWARM_STORAGE_STATUS.md` (9,441 bytes)
- `AGENT_SWARM_STORAGE_TASK_ASSIGNMENTS.md` (8,669 bytes)

**testing/** (1 file):
- `AGENT_SWARM_E2E_TESTING_COMPLETE.md` (12,139 bytes)

**troubleshooting/** (2 files):
- `AGENT_SWARM_STORAGE.md` (16,029 bytes)
- `ENHANCED_AGENT_SWARM_TROUBLESHOOTING_GUIDE.md` (39,062 bytes)

**configuration/** (1 file):
- `ENHANCED_AGENT_SWARM_CONFIGURATION_REFERENCE.md` (25,818 bytes)

**videos/** (1 file):
- `ENHANCED_AGENT_SWARM_VIDEO_DEMONSTRATIONS.md` (51,315 bytes)

---

## 🧪 Test Files

### Backend Tests

**Location**: `/Users/aideveloper/core/src/backend/tests/`

**E2E Tests**:
```
tests/e2e/test_agent_swarm_e2e.py (~1,000 lines)
├── test_full_workflow() - Tests all 11 stages
├── test_stage_1_project_creation()
├── test_stage_2_prd_upload()
├── test_stage_3_data_model_generation()
├── test_stage_4_backlog_creation()
├── test_stage_5_sprint_planning()
├── test_stage_6_execution_setup()
├── test_stage_7_github_repo_creation()
├── test_stage_8_documentation_commit()
├── test_stage_9_github_issue_import() ❌ SKIPPED (not implemented)
├── test_stage_10_launch_swarm()
└── test_stage_11_code_generation()
```

**Integration Tests**:
```
tests/integration/
├── test_github_integration.py (~600 lines)
│   ├── test_create_repository()
│   ├── test_commit_files()
│   ├── test_create_branch()
│   └── test_create_pull_request()
├── test_zerodb_integration.py (~800 lines)
│   ├── test_file_upload()
│   ├── test_file_download()
│   ├── test_create_table()
│   └── test_query_rows()
└── test_websocket_integration.py (~400 lines)
    ├── test_connect_websocket()
    ├── test_receive_updates()
    └── test_disconnect_handling()
```

**Unit Tests**:
```
tests/unit/
├── test_workflow_state_machine.py
├── test_agent_orchestration.py
├── test_swarm_agent.py
└── test_rules_parser.py
```

**Test Documentation**:
```
tests/E2E_AGENT_SWARM_QUICK_START.md (~500 lines)
tests/E2E_AGENT_SWARM_TEST_REPORT.md (~800 lines)
```

---

### Frontend Tests

**Location**: `/Users/aideveloper/core/AINative-website/tests/e2e/`

**Component Tests**:
```
agentswarm-components.spec.ts (~800 lines)
├── test('TimeComparisonCard renders correctly')
├── test('GitHubIntegrationCard shows repo status')
├── test('StageIndicator updates progress')
├── test('TDDProgressDisplay shows metrics')
├── test('CompletionStatistics accurate')
├── test('ExecutionTimer counts correctly')
└── test('Full workflow integration')

Status: 7/7 passing ✅
```

**GitHub Integration Tests**:
```
github-integration.spec.ts (~600 lines)
├── test('PAT input validation')
├── test('Repo creation flow')
├── test('Repo status display')
└── test('Error handling')
```

**Workflow Tests**:
```
agentswarm-workflow.spec.ts (~900 lines)
├── test('Complete stages 1-8')
├── test('Stage progression')
├── test('Error states')
└── test('Data persistence')
```

**Test Utilities**:
```
test-utils.tsx (~200 lines)
- Custom render with providers
- Mock API responses
- Test data factories
```

---

## 📦 SDK Files

### TypeScript SDK

**Location**: `/Users/aideveloper/core/developer-tools/sdks/typescript/`

**Main Files**:
```
src/types/agent-swarm.ts (~400 lines)
- Type definitions for all AgentSwarm entities
- Project, Workflow, Stage types
- API request/response types

src/agent-swarm/client.ts (~600 lines)
- AgentSwarmClient class
- All API method wrappers
- Error handling

dist/types/agent-swarm.d.ts (~500 lines)
- Compiled type declarations

tests/agent-swarm.test.ts (~800 lines)
- Unit tests for SDK
- Integration tests
- Mock API responses
```

---

### Python SDK

**Location**: `/Users/aideveloper/core/developer-tools/sdks/python/`

**Main Files**:
```
ainative/agent_swarm/client.py (~700 lines)
- AgentSwarmClient class
- Async API methods
- Type hints

examples/agent_swarm.py (~300 lines)
- Usage examples
- Common workflows
- Best practices
```

---

### Go SDK

**Location**: `/Users/aideveloper/core/developer-tools/sdks/go/ainative/`

**Main Files**:
```
agent_swarm.go (~800 lines)
- AgentSwarmClient struct
- All API methods
- Error types

agent_swarm_test.go (~600 lines)
- Unit tests
- Integration tests
- Table-driven tests

examples/agent_swarm/ (~400 lines)
- Usage examples
- Sample workflows
```

---

## ⚙️ CI/CD Files

**Location**: `/Users/aideveloper/core/.github/workflows/`

**agent-swarm-ci.yml** (~200 lines):
```yaml
# Runs on every PR
# Jobs:
# - Backend tests (pytest)
# - Frontend tests (Playwright)
# - Lint checks
# - Type checking
```

**agent-swarm-deploy.yml** (~150 lines):
```yaml
# Runs on merge to main
# Jobs:
# - Deploy backend to Railway
# - Deploy frontend to Vercel
# - Run smoke tests
# - Notify on Slack
```

---

## 🔧 Configuration Files

### Backend Configuration

**Location**: `/Users/aideveloper/core/src/backend/`

**.env.example** (~50 lines):
```bash
DATABASE_URL=postgresql://...
ZERODB_API_KEY=...
ZERODB_PROJECT_ID=...
GITHUB_TOKEN=...
ANTHROPIC_API_KEY=...
MINIO_URL=...
REDIS_URL=...
```

**alembic.ini** (~100 lines):
- Database migration configuration

**pyproject.toml** (~150 lines):
- Python dependencies
- FastAPI
- Celery
- Anthropic
- aiohttp

---

### Frontend Configuration

**Location**: `/Users/aideveloper/core/AINative-website/`

**vite.config.ts** (~80 lines):
```typescript
// Build configuration
// Proxy setup for API
// Plugin configuration
```

**tailwind.config.js** (~120 lines):
```javascript
// Tailwind CSS configuration
// shadcn/ui theme
// Custom colors and spacing
```

**tsconfig.json** (~60 lines):
```json
// TypeScript configuration
// Path aliases (@/components)
// Strict type checking
```

**package.json** (~200 lines):
```json
// Dependencies
// Scripts (dev, build, test)
// Version info
```

---

## 📊 File Statistics Summary

### Backend

```
Total Lines of Code: ~61,728 (swarm/ folder alone)
Total Files: 100+
Largest File: application_workflow.py (325,902 bytes)
Core API Router: agent_swarms.py (~1,200 lines)
Main Orchestrator: agent_swarm.py (~700 lines)
Individual Agent: swarm_agent.py (~2,200 lines)
```

### Frontend

```
Total Lines of Code: ~5,000
Total Files: 20+
Largest File: AgentSwarmDashboard.tsx (1,813 lines)
UI Components: 8 files (~2,400 lines total)
Service Layer: AgentSwarmService.ts (267+ lines)
Tests: 3 files (~2,300 lines)
```

### Documentation

```
Total Documentation Files: 36
Total Documentation Size: ~500KB
Largest Doc: ENHANCED_AGENT_SWARM_BEST_PRACTICES.md (54,521 bytes)
This File Map: ~30,000 bytes
Master Context: ~100,000 bytes
```

---

## 🔍 Quick File Finder

**Need to find**:
- **Main API endpoints?** → `/app/api/api_v1/endpoints/agent_swarms.py`
- **Workflow logic?** → `/app/agents/swarm/application_workflow.py`
- **Agent execution?** → `/app/agents/swarm/swarm_agent.py`
- **GitHub integration?** → `/app/services/project_github_service.py`
- **ZeroDB calls?** → `/app/services/zerodb_integration_service.py`
- **Main UI dashboard?** → `/AINative-website/src/pages/dashboard/AgentSwarmDashboard.tsx`
- **API client?** → `/AINative-website/src/services/AgentSwarmService.ts`
- **UI components?** → `/AINative-website/src/components/*.tsx`
- **Tests?** → `/src/backend/tests/` or `/AINative-website/tests/e2e/`
- **Docs?** → `/docs/agent-swarm/`
- **Official spec?** → `/src/backend/AgentSwarm-Workflow.md`

---

**Document Version**: 1.0
**Last Updated**: December 5, 2025
**Total Files Catalogued**: 150+
**Maintained By**: AINative Studio Engineering Team
