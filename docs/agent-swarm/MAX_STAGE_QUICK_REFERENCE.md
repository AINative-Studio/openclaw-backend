# max_stage Parameter - Quick Reference

## Overview

The `max_stage` parameter allows you to stop workflows at a specific stage instead of running all 11 stages. This is useful for testing, development, and staged deployments.

## Valid Stage Values

```
requirements_analysis      # Stage 1
architecture_design        # Stage 2
frontend_development      # Stage 3
backend_development       # Stage 4
integration               # Stage 5
security_scanning         # Stage 6
testing                   # Stage 7
deployment_setup          # Stage 8
github_deployment         # Stage 9
backlog_publishing        # Stage 10
validation                # Stage 11
```

## Usage

### API Request

```bash
curl -X POST http://localhost:8000/api/v1/admin/agent-swarm/orchestrate \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "project_type": "web_application",
    "description": "Create a simple web app",
    "max_stage": "architecture_design"
  }'
```

### Python Code

```python
from app.agents.swarm.application_workflow import ApplicationWorkflow

workflow = ApplicationWorkflow()

config = {
    "project_id": "my-project-123",
    "project_type": "web_application",
    "features": ["authentication", "dashboard"],
    "max_stage": "architecture_design"  # Stop here
}

execution_id = await workflow.generate_application(
    "Create a web app with auth",
    config
)
```

## Common Use Cases

### 1. Test Requirements + Architecture Only
```json
{
  "max_stage": "architecture_design"
}
```
**Time**: ~5-10 minutes
**Stages**: 2

### 2. Test Frontend Development
```json
{
  "max_stage": "frontend_development"
}
```
**Time**: ~15-20 minutes
**Stages**: 3

### 3. Test Backend Development
```json
{
  "max_stage": "backend_development"
}
```
**Time**: ~20-25 minutes
**Stages**: 4

### 4. Full Integration Test
```json
{
  "max_stage": "integration"
}
```
**Time**: ~30-35 minutes
**Stages**: 5

### 5. Security + Testing
```json
{
  "max_stage": "testing"
}
```
**Time**: ~35-40 minutes
**Stages**: 7

### 6. Full Workflow (No max_stage)
```json
{
  // No max_stage parameter
}
```
**Time**: ~45-50 minutes
**Stages**: 11

## Expected Log Output

### Workflow Start
```
🎯 Max stage limit requested: architecture_design
🎯 Workflow will stop at stage: architecture_design
```

### During Execution
```
🎯 STAGE DEBUG: Executing stage requirements_analysis (will stop at architecture_design)
✅ Completed sequential stage: requirements_analysis

🎯 STAGE DEBUG: Executing stage architecture_design (will stop at architecture_design)
✅ Completed sequential stage: architecture_design
```

### Workflow Stop
```
✅ Reached max_stage: architecture_design - stopping workflow
✅ Workflow completed at max_stage: architecture_design
```

## Verification

### Check Workflow Status
```python
execution = workflow.workflow_executions[execution_id]

assert execution.status == WorkflowStatus.COMPLETED
assert execution.current_stage == WorkflowStage.COMPLETION
assert execution.max_stage == WorkflowStage.ARCHITECTURE_DESIGN
assert WorkflowStage.ARCHITECTURE_DESIGN in execution.stages_completed
```

### Check Logs
```bash
docker logs backend | grep "max_stage"
```

Should show:
- `🎯 Max stage limit requested:`
- `🎯 Workflow will stop at stage:`
- `✅ Reached max_stage:`

## Error Handling

### Invalid Stage Value
```json
{
  "max_stage": "invalid_stage_name"
}
```
**Result**: Warning logged, max_stage ignored, full workflow runs

```
⚠️ Invalid max_stage value: invalid_stage_name, ignoring
🔍 DEBUG: ValueError: 'invalid_stage_name' is not a valid WorkflowStage
🎯 No max_stage limit - workflow will run all stages
```

### Missing max_stage (Default)
```json
{
  // No max_stage parameter
}
```
**Result**: Full workflow runs all 11 stages

```
🎯 No max_stage limit - workflow will run all stages
```

## Stage Dependencies

Some stages have dependencies. Stopping at a stage means:

| Stop at Stage | What Gets Executed | What's Skipped |
|--------------|-------------------|----------------|
| `requirements_analysis` | Stage 1 | Stages 2-11 |
| `architecture_design` | Stages 1-2 | Stages 3-11 |
| `frontend_development` | Stages 1-3 | Stages 4-11 |
| `backend_development` | Stages 1-4 | Stages 5-11 |
| `integration` | Stages 1-5 | Stages 6-11 |
| `testing` | Stages 1-7 | Stages 8-11 |
| `deployment_setup` | Stages 1-8 | Stages 9-11 |

## Troubleshooting

### Workflow Doesn't Stop

**Symptom**: Workflow continues past max_stage
**Check**:
1. Is max_stage in request body?
2. Is stage name spelled correctly?
3. Check logs for "Max stage limit requested"

**Solution**: Verify request includes max_stage parameter

### Workflow Fails Instead of Completing

**Symptom**: Status is "failed" instead of "completed"
**Check**:
1. Check logs for stage errors
2. Verify stage dependencies are met
3. Check resource availability

**Solution**: Fix underlying stage error, not related to max_stage

### Invalid Stage Name

**Symptom**: Warning about invalid max_stage
**Check**: Stage name spelling and case

**Valid**: `architecture_design`
**Invalid**: `architecture-design`, `ArchitectureDesign`, `arch_design`

## Performance Tips

1. **Development**: Use `architecture_design` for quick validation
2. **Frontend Work**: Use `frontend_development`
3. **Backend Work**: Use `backend_development`
4. **Pre-Production**: Use `testing` to validate everything except deployment
5. **Full Deployment**: Omit max_stage parameter

## API Examples

### Test Architecture Only
```bash
curl -X POST http://localhost:8000/api/v1/admin/agent-swarm/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "project_type": "web_application",
    "description": "E-commerce platform",
    "max_stage": "architecture_design"
  }'
```

### Test Up to Integration
```bash
curl -X POST http://localhost:8000/api/v1/admin/agent-swarm/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "project_type": "mobile_app",
    "description": "Social media app",
    "features": ["authentication", "feed", "messaging"],
    "max_stage": "integration"
  }'
```

### Full Workflow
```bash
curl -X POST http://localhost:8000/api/v1/admin/agent-swarm/orchestrate \
  -H "Content-Type: application/json" \
  -d '{
    "project_type": "api",
    "description": "RESTful API for inventory management"
  }'
```

## Monitoring

### Key Metrics to Track
- Workflows by max_stage
- Success rate per max_stage
- Average duration per max_stage
- Failure points per max_stage

### Grafana Query Examples
```promql
# Workflows completed by max_stage
sum(workflow_completed_total) by (max_stage)

# Average duration by max_stage
avg(workflow_duration_seconds) by (max_stage)

# Failure rate by max_stage
rate(workflow_failed_total{max_stage="architecture_design"}[5m])
```

## Best Practices

1. **Use max_stage for development**: Test incrementally, not all at once
2. **Log review**: Always check logs for expected max_stage messages
3. **Stage naming**: Use exact stage enum values
4. **Error handling**: Handle invalid stage names gracefully
5. **Documentation**: Document which max_stage you used for tests

## Related Files

- **Orchestrate Endpoint**: `/Users/aideveloper/core/src/backend/app/api/admin/agent_swarm.py`
- **Workflow Logic**: `/Users/aideveloper/core/src/backend/app/agents/swarm/application_workflow.py`
- **Test Script**: `/Users/aideveloper/core/src/backend/test_max_stage_fix.py`
- **Implementation Summary**: `/Users/aideveloper/core/src/backend/MAX_STAGE_FIX_IMPLEMENTATION_SUMMARY.md`

## Support

For issues or questions:
1. Check logs for max_stage messages
2. Verify stage name is valid
3. Review implementation summary
4. Contact backend team

---

**Last Updated**: December 9, 2025
**Status**: ✅ Production Ready
