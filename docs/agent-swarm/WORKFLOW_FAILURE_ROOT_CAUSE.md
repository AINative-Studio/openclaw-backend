# Workflow Failure - Root Cause Analysis

**Date**: 2025-12-09
**Status**: 🔴 CRITICAL BUG IDENTIFIED

---

## Problem Summary

The Agent Swarm workflow is **NOT stopping** at `max_stage: "architecture_design"` as expected. Instead, it continues past this stage to `frontend_development`, `backend_development`, and beyond, ultimately failing due to missing dependencies and errors in later stages.

---

## Evidence

### Backend Logs Show Continued Execution

From the logs:
```
🎯 STAGE DEBUG: Executing stage requirements_analysis
🎯 STAGE DEBUG: Executing stage architecture_design
🎯 STAGE DEBUG: Executing stage frontend_development     ← SHOULD HAVE STOPPED HERE!
🎯 STAGE DEBUG: Executing stage backend_development
🎯 STAGE DEBUG: Executing stage integration
🎯 STAGE DEBUG: Executing stage security_scanning
...
📍 Stage: completed | Progress: 100% | Status: failed    ← WORKFLOW FAILED
```

The workflow reached `architecture_design` (Stage 2) but **did NOT stop** as configured by `max_stage`.

### Missing Log Message

We should see this log message if `max_stage` was working:
```python
# From application_workflow.py:1009
logger.info(f"🎯 Max stage limit set: {max_stage.value}")
```

**This log message is MISSING** from all workflow executions, indicating that `max_stage` is either:
1. Not being passed to the workflow
2. Not being parsed correctly
3. Being set to `None`

---

## Root Cause

**The `max_stage` parameter is not being parsed from the request OR it's failing to convert to the `WorkflowStage` enum.**

### Current Flow:

1. **Frontend sends** (from test script):
   ```json
   {
     "max_stage": "architecture_design",
     ...
   }
   ```

2. **Backend `/orchestrate` endpoint receives** (line 1283):
   ```python
   project_config: Dict[str, Any]  # Contains max_stage
   ```

3. **Workflow config is passed** (line 1501-1506):
   ```python
   await workflow.generate_application(
       user_prompt,
       {
           "project_id": project_id,
           "project_type": project_config["project_type"],
           "features": project_config.get("features", []),
           "max_stage": project_config.get("max_stage")  # ← Passed here
       },
       user_id=str(current_user.id)
   )
   ```

4. **Workflow tries to parse** (line 1004-1012):
   ```python
   max_stage = None
   if config and config.get('max_stage'):
       max_stage_str = config.get('max_stage')
       try:
           max_stage = WorkflowStage(max_stage_str)
           logger.info(f"🎯 Max stage limit set: {max_stage.value}")  # ← NEVER LOGGED
       except ValueError:
           logger.warning(f"⚠️ Invalid max_stage value: {max_stage_str}, ignoring")
           max_stage = None
   ```

5. **Stopping logic should trigger** (line 6523-6544):
   ```python
   if execution.max_stage and stage == execution.max_stage:
       logger.info(f"✅ Reached max_stage: {execution.max_stage.value} - stopping workflow")
       execution.status = WorkflowStatus.COMPLETED
       return  # Exit workflow
   ```

---

## Why It's Failing

### Hypothesis 1: `config` is None or Empty

The `config` parameter might not be populated correctly when calling `generate_application()`.

**Check**: Line 1501 - is the config dict being created correctly?

### Hypothesis 2: Enum Parsing Fails Silently

The `WorkflowStage(max_stage_str)` call might be failing with a `ValueError` that's being caught and ignored, setting `max_stage = None`.

**Evidence**: No warning log `"⚠️ Invalid max_stage value"` in the logs.

### Hypothesis 3: Timing Issue with Auto-Reload

The backend with `--reload` might have been restarting and losing the `max_stage` value in memory.

**Evidence**: The logs show server restarts mid-execution.

---

## Debugging Steps

### Step 1: Add Debug Logging

Add these debug logs to `application_workflow.py`:

```python
# Line 1004 - Add debug logging
max_stage = None
logger.error(f"🔍 DEBUG: config = {config}")  # NEW
logger.error(f"🔍 DEBUG: config.get('max_stage') = {config.get('max_stage') if config else 'config is None'}")  # NEW
if config and config.get('max_stage'):
    max_stage_str = config.get('max_stage')
    logger.error(f"🔍 DEBUG: max_stage_str = {max_stage_str}")  # NEW
    try:
        max_stage = WorkflowStage(max_stage_str)
        logger.info(f"🎯 Max stage limit set: {max_stage.value}")
    except ValueError as e:
        logger.warning(f"⚠️ Invalid max_stage value: {max_stage_str}, ignoring")
        logger.error(f"🔍 DEBUG: ValueError: {e}")  # NEW
        max_stage = None
```

### Step 2: Run Test Again with Stable Backend

1. Kill all backend processes
2. Start backend **without** `--reload`:
   ```bash
   cd /Users/aideveloper/core/src/backend
   python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```
3. Run test script
4. Check logs for debug messages

### Step 3: Verify Request Body

Check that the request actually includes `max_stage`:

```bash
# In test script, add debug output
echo "Request body:"
jq -n \
  --arg name "$PROJECT_NAME" \
  --arg desc "$PRD_CONTENT" \
  --arg zerodb_id "$ZERODB_PROJECT_ID" \
  '{
    name: $name,
    description: $desc,
    project_type: "web_app",
    technologies: ["FastAPI", "React"],
    features: ["user_authentication", "task_management"],
    zerodb_project_id: $zerodb_id,
    max_stage: "architecture_design"
  }'
```

---

## Expected vs Actual Behavior

### Expected (WITH max_stage working):

```
🎯 Max stage limit set: architecture_design
🎯 STAGE DEBUG: Executing stage requirements_analysis
   ✅ PRD generated
   ✅ Data Model generated
   ✅ Backlog generated
🎯 STAGE DEBUG: Executing stage architecture_design
   ✅ Sprint Plan generated
   ✅ Architecture Design generated
✅ Reached max_stage: architecture_design - stopping workflow
✅ Workflow completed at max_stage: architecture_design
📍 Stage: completed | Progress: 100% | Status: completed
```

### Actual (WITHOUT max_stage working):

```
🎯 STAGE DEBUG: Executing stage requirements_analysis
🎯 STAGE DEBUG: Executing stage architecture_design
🎯 STAGE DEBUG: Executing stage frontend_development     ← SHOULD STOP
🎯 STAGE DEBUG: Executing stage backend_development
🎯 STAGE DEBUG: Executing stage integration
❌ Stage integration failed
📍 Stage: completed | Progress: 100% | Status: failed
```

---

## Impact

**Without the `max_stage` parameter working**:

1. ❌ Frontend gets workflow failures instead of success
2. ❌ Documents (Data Model, Backlog, Sprint Plan) are generated but workflow marks as "failed"
3. ❌ Steps 3-5 in the UI cannot be tested because workflow never completes successfully
4. ❌ Testing is BLOCKED until this is fixed

---

## Next Actions

1. ✅ **IMMEDIATE**: Add debug logging to identify why `max_stage` isn't being set
2. ⏳ **RUN TEST**: Re-run workflow with debug logs to see actual values
3. ⏳ **FIX BUG**: Based on debug output, fix the parsing issue
4. ⏳ **VERIFY**: Re-test to confirm workflow stops at `architecture_design`
5. ⏳ **CONTINUE**: Once fixed, test Steps 3-5 UI display

---

**Status**: 🔴 BLOCKED - Must fix `max_stage` parameter before testing UI
**Priority**: CRITICAL
**Estimated Fix Time**: 30 minutes (debug → fix → test)
