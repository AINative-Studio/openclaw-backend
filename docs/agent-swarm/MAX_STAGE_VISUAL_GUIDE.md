# max_stage Implementation - Visual Bug Report

**Date**: 2025-12-09
**For**: Backend Agent
**Purpose**: Visual guide showing exactly what's missing

---

## 🔍 Current Data Flow (BROKEN)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                     │
├─────────────────────────────────────────────────────────────────────┤
│  AgentSwarmDashboard.tsx (Line 439-447)                             │
│                                                                      │
│  const response = await apiClient.post('/v1/public/agent-swarms/orchestrate', {
│    name: projectName,                                               │
│    description: prdContent,                                         │
│    project_type: 'web_app',                                         │
│    max_stage: 'architecture_design'  ✅ SENT                        │
│  });                                                                 │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           │ HTTP POST
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      BACKEND API                                     │
├─────────────────────────────────────────────────────────────────────┤
│  agent_swarms.py (Line 1282-1656)                                   │
│                                                                      │
│  @router.post("/orchestrate")                                       │
│  async def create_agent_swarm_project(                              │
│      project_config: Dict[str, Any],  # Contains max_stage          │
│      ...                                                             │
│  ):                                                                  │
│      # ❌ BUG-001: Never extracts max_stage!                        │
│      # max_stage = project_config.get("max_stage")  # MISSING!      │
│                                                                      │
│      execution_id = await workflow.generate_application(            │
│          user_prompt,                                                │
│          {                                                           │
│              "project_id": project_id,                               │
│              "project_type": project_config["project_type"],        │
│              # ❌ max_stage NOT PASSED!                             │
│          },                                                          │
│          user_id=str(current_user.id)                               │
│      )                                                               │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           │ Missing max_stage in config dict
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW LOGIC                                    │
├─────────────────────────────────────────────────────────────────────┤
│  application_workflow.py (Line 1002-1021)                           │
│                                                                      │
│  max_stage = None                                                   │
│  if config and config.get('max_stage'):  # ❌ Never triggers!       │
│      max_stage_str = config.get('max_stage')                        │
│      max_stage = WorkflowStage(max_stage_str)                       │
│                                                                      │
│  execution = WorkflowExecution(                                     │
│      max_stage=max_stage,  # ❌ Always None!                        │
│      ...                                                             │
│  )                                                                   │
│                                                                      │
│  # Workflow executes all stages because max_stage is None           │
└─────────────────────────────────────────────────────────────────────┘
```

**Result**: 🔴 Feature fails silently - workflow runs all 11 stages

---

## ✅ Fixed Data Flow (TARGET)

```
┌─────────────────────────────────────────────────────────────────────┐
│                         FRONTEND                                     │
├─────────────────────────────────────────────────────────────────────┤
│  AgentSwarmDashboard.tsx (Line 439-447)                             │
│                                                                      │
│  const response = await apiClient.post('/v1/public/agent-swarms/orchestrate', {
│    max_stage: 'architecture_design'  ✅ SENT                        │
│  });                                                                 │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           │ HTTP POST
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      BACKEND API (FIXED)                             │
├─────────────────────────────────────────────────────────────────────┤
│  agent_swarms.py (Line ~1479)                                       │
│                                                                      │
│  @router.post("/orchestrate")                                       │
│  async def create_agent_swarm_project(...):                         │
│      # ✅ FIX: Extract max_stage                                    │
│      max_stage = project_config.get("max_stage")                    │
│                                                                      │
│      execution_id = await workflow.generate_application(            │
│          user_prompt,                                                │
│          {                                                           │
│              "project_id": project_id,                               │
│              "project_type": project_config["project_type"],        │
│              "max_stage": max_stage,  # ✅ PASSED                   │
│          },                                                          │
│          user_id=str(current_user.id)                               │
│      )                                                               │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           │ Config dict includes max_stage
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│                 WORKFLOW LOGIC (PARSING - WORKS)                     │
├─────────────────────────────────────────────────────────────────────┤
│  application_workflow.py (Line 1002-1021)                           │
│                                                                      │
│  max_stage = None                                                   │
│  if config and config.get('max_stage'):  # ✅ Triggers!             │
│      max_stage_str = config.get('max_stage')                        │
│      max_stage = WorkflowStage('architecture_design')               │
│      logger.info(f"🎯 Max stage limit set: {max_stage.value}")      │
│                                                                      │
│  execution = WorkflowExecution(                                     │
│      max_stage=max_stage,  # ✅ = ARCHITECTURE_DESIGN               │
│      ...                                                             │
│  )                                                                   │
└──────────────────────────┬───────────────────────────────────────────┘
                           │
                           │ execution.max_stage is set
                           ▼
┌─────────────────────────────────────────────────────────────────────┐
│              WORKFLOW EXECUTION (NEEDS FIX)                          │
├─────────────────────────────────────────────────────────────────────┤
│  _execute_stages_with_parallelism() (Line 6460-6490)                │
│                                                                      │
│  for stage in stages:                                               │
│      # Execute stage                                                │
│      success = await self._execute_stage(stage, execution)          │
│                                                                      │
│      # ✅ ADD THIS CHECK:                                           │
│      if execution.max_stage and stage == execution.max_stage:       │
│          logger.info(f"✅ Workflow stopped at max_stage: {stage}")  │
│          execution.status = WorkflowStatus.COMPLETED                │
│          return  # ⏹️ STOP HERE!                                    │
│                                                                      │
│      # Continue to next stage...                                    │
└─────────────────────────────────────────────────────────────────────┘
```

**Result**: ✅ Workflow stops after architecture_design stage (2/11 stages)

---

## 🔧 Fix #1: Backend API (BUG-001)

### Current Code (BROKEN)
```python
# File: app/api/api_v1/endpoints/agent_swarms.py
# Around line 1479

execution_id = await workflow.generate_application(
    user_prompt,
    {
        "project_id": project_id,
        "project_type": project_config["project_type"],
        "features": project_config.get("features", [])
        # ❌ max_stage is missing!
    },
    user_id=str(current_user.id)
)
```

### Fixed Code (TARGET)
```python
# File: app/api/api_v1/endpoints/agent_swarms.py
# Around line 1479

# ✅ Extract max_stage from request body
max_stage = project_config.get("max_stage")

execution_id = await workflow.generate_application(
    user_prompt,
    {
        "project_id": project_id,
        "project_type": project_config["project_type"],
        "features": project_config.get("features", []),
        "max_stage": max_stage  # ✅ ADD THIS LINE
    },
    user_id=str(current_user.id)
)
```

---

## 🔧 Fix #2: Workflow Stopping Logic (BUG-002)

### Current Code (BROKEN)
```python
# File: app/agents/swarm/application_workflow.py
# Lines 6460-6490

for stage in stages:
    if stage == WorkflowStage.INITIALIZATION:
        continue

    # Execute stage
    success = await self._execute_stage(stage, execution)

    # ❌ No check for max_stage!
    # Workflow continues to all stages

    if not success:
        if self._is_stage_critical(stage):
            raise Exception(f"Critical stage {stage.value} failed")
```

### Fixed Code (TARGET)
```python
# File: app/agents/swarm/application_workflow.py
# Lines 6460-6490

for stage in stages:
    if stage == WorkflowStage.INITIALIZATION:
        continue

    # Execute stage
    success = await self._execute_stage(stage, execution)

    # ✅ ADD THIS CHECK:
    if execution.max_stage and stage == execution.max_stage:
        logger.info(f"✅ Workflow stopped at max_stage: {stage.value}")
        execution.status = WorkflowStatus.COMPLETED
        execution.stages_completed.append(stage)

        # Broadcast stop message
        await ws_manager.broadcast_to_project(execution.id, {
            "type": "workflow_stopped_at_max_stage",
            "workflow_id": execution.id,
            "max_stage": stage.value,
            "stages_completed": [s.value for s in execution.stages_completed],
            "timestamp": datetime.utcnow().isoformat()
        })

        return  # ⏹️ EXIT EARLY - Don't execute more stages

    # Continue with error handling...
    if not success:
        if self._is_stage_critical(stage):
            raise Exception(f"Critical stage {stage.value} failed")
```

---

## 📊 Stage Execution Timeline

### Current Behavior (BROKEN)
```
User uploads PRD
↓
API receives max_stage but ignores it
↓
Workflow starts with max_stage = None
↓
Stage 1: requirements_analysis  ✅ (1 min)
Stage 2: architecture_design    ✅ (1 min)
Stage 3: frontend_development   ✅ (3 min) ← SHOULD STOP HERE!
Stage 4: backend_development    ✅ (3 min) ← SHOULD NOT RUN!
Stage 5: integration            ✅ (2 min) ← SHOULD NOT RUN!
...
Stage 11: completion            ✅ (1 min) ← SHOULD NOT RUN!
↓
Total time: 15 minutes ❌
```

### Target Behavior (FIXED)
```
User uploads PRD
↓
API receives max_stage = "architecture_design"
↓
Workflow starts with max_stage = ARCHITECTURE_DESIGN
↓
Stage 1: requirements_analysis  ✅ (1 min)
Stage 2: architecture_design    ✅ (1 min)
↓
🛑 max_stage reached - stopping workflow
↓
Status = COMPLETED
↓
Total time: 2 minutes ✅ (13 minutes saved!)
```

---

## 🎯 Testing Instructions (After Fixes)

### 1. Start Servers
```bash
# Terminal 1: Backend
cd /Users/aideveloper/core/src/backend
uvicorn app.main:app --reload

# Terminal 2: Frontend
cd /Users/aideveloper/core/AINative-website
npm run dev
```

### 2. Open Browser Console
Navigate to: `http://localhost:5177/dashboard/agent-swarm`

### 3. Monitor Logs
Watch for these messages:

**Browser Console** (Should see):
```javascript
🚀 Creating Agent Swarm project via /orchestrate endpoint...
Request body: { ..., max_stage: 'architecture_design' }
```

**Backend Logs** (Should see):
```
🎯 Max stage limit set: architecture_design
🚀 Executing sequential stage: requirements_analysis
✅ Completed sequential stage: requirements_analysis
🚀 Executing sequential stage: architecture_design
✅ Completed sequential stage: architecture_design
✅ Workflow stopped at max_stage: architecture_design
```

**Backend Logs** (Should NOT see):
```
🚀 Executing sequential stage: frontend_development  ❌ FAIL IF THIS APPEARS
```

### 4. Verify Status Endpoint
```bash
curl http://localhost:8000/v1/public/agent-swarms/projects/{project_id}/status
```

Expected response:
```json
{
  "stage": "completed",
  "progress": 100,
  "status": "completed",
  "metadata": {
    "prd": "...",
    "data_model": "...",
    "backlog": "...",
    "sprint_plan": "..."
  }
}
```

---

## ✅ Success Criteria

After implementing both fixes, the following must be true:

1. ✅ Backend API extracts max_stage from request
2. ✅ Backend logs show "Max stage limit set: architecture_design"
3. ✅ Workflow executes requirements_analysis stage
4. ✅ Workflow executes architecture_design stage
5. ✅ Backend logs show "Workflow stopped at max_stage: architecture_design"
6. ✅ Workflow does NOT execute frontend_development stage
7. ✅ Workflow status = COMPLETED
8. ✅ Status endpoint returns 100% progress
9. ✅ All planning documents generated (PRD, Data Model, Backlog, Sprint Plan)
10. ✅ Execution time ~2 minutes (not 15 minutes)

---

## 🚀 Quick Verification Script

After implementing fixes, run:
```bash
cd /Users/aideveloper/core/src/backend
./monitor_max_stage_implementation.sh
```

Should see:
```
✅ Backend API: max_stage parameter found!
✅ Backend Workflow: max_stage logic found!
✅ Frontend Dashboard: max_stage parameter found!
🎉 ALL IMPLEMENTATIONS COMPLETE!
```

---

**Document Created**: 2025-12-09
**For**: Backend Agent implementing max_stage fixes
**QA Contact**: QA Agent (waiting for notification of completion)
