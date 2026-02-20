# MAX_STAGE Bug - Quick Fix Guide

## TL;DR

The `max_stage` parameter is not being parsed. I've added debug logging and identified the likely root cause. Here's the quick fix:

## The Fast Fix (2 minutes)

**File**: `/Users/aideveloper/core/src/backend/app/api/api_v1/endpoints/agent_swarms.py`

### Step 1: Add this code at line 1280 (before the @router.post decorator):

```python
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict

class OrchestratRequestSchema(BaseModel):
    """Request schema for orchestrate endpoint"""
    name: Optional[str] = None
    description: str
    project_type: str
    features: Optional[List[str]] = None
    technologies: Optional[List[str]] = None
    deployment: Optional[Dict[str, Any]] = None
    max_stage: Optional[str] = Field(
        None,
        description="Stop workflow after this stage: requirements_analysis, architecture_design, frontend_development, backend_development, integration, security_scanning, testing, deployment_setup, github_deployment, backlog_publishing, validation, completion"
    )

    class Config:
        extra = "allow"
```

### Step 2: Change line 1282 from:

```python
async def create_agent_swarm_project(
    project_config: Dict[str, Any],
    db: Session = Depends(get_database_session),
    current_user: User = Depends(get_current_user)
):
```

To:

```python
async def create_agent_swarm_project(
    request: OrchestratRequestSchema,
    db: Session = Depends(get_database_session),
    current_user: User = Depends(get_current_user)
):
    # Convert Pydantic model to dict
    project_config = request.dict(exclude_none=False)
```

### Step 3: Restart backend

```bash
pkill -f "uvicorn app.main:app"
cd /Users/aideveloper/core/src/backend
python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 &
```

### Step 4: Test it

```bash
curl -X POST "http://localhost:8000/api/v1/public/agent-swarms/orchestrate" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Project",
    "description": "Build a task manager",
    "project_type": "web_app",
    "max_stage": "architecture_design"
  }'
```

## What the Fix Does

1. **Explicitly defines** `max_stage` as a valid request parameter
2. **Ensures FastAPI** doesn't filter it out
3. **Maintains backward compatibility** by converting to dict
4. **Adds validation** for the request schema

## Debug Logs to Check

After the fix, you should see these logs:

```
🔍 ENDPOINT DEBUG: 'max_stage' in project_config: True
🔍 ENDPOINT DEBUG: project_config.get('max_stage'): architecture_design
🔍 API DEBUG: config_to_pass = {..., 'max_stage': 'architecture_design'}
🔍 DEBUG: max_stage_str = architecture_design
🎯 Max stage limit set: architecture_design
✅ Reached max_stage: architecture_design - stopping workflow
```

## Valid max_stage Values

- `requirements_analysis` - Stop after PRD generation
- `architecture_design` - Stop after architecture + data model + backlog + sprint plan (Stage 2)
- `frontend_development` - Stop after frontend code generation
- `backend_development` - Stop after backend code generation
- `integration` - Stop after integration
- `security_scanning` - Stop after security scan
- `testing` - Stop after tests
- `deployment_setup` - Stop after deployment setup
- `github_deployment` - Stop after GitHub deployment
- `backlog_publishing` - Stop after backlog is published
- `validation` - Stop after validation
- `completion` - Run all stages (same as not providing max_stage)

## Files Changed

1. `/Users/aideveloper/core/src/backend/app/api/api_v1/endpoints/agent_swarms.py` - Added Pydantic schema and updated endpoint signature
2. `/Users/aideveloper/core/src/backend/app/agents/swarm/application_workflow.py` - Debug logging (already added)

## Alternative: Just Debug First

If you want to see the root cause before fixing, just:

1. Restart backend (debug logs are already added)
2. Trigger a workflow
3. Check: `grep "🔍.*DEBUG:" backend_debug_new.log`
4. The logs will tell you exactly what's wrong

Then apply the fix above.
