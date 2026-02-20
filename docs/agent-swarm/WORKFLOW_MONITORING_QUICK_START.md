# Workflow Monitoring - Quick Start Guide

## Quick Run

```bash
cd /Users/aideveloper/core/src/backend
python3 test_workflow_complete_verification.py
```

## What It Does

1. **Authenticates** with admin credentials
2. **Starts** a simple Next.js workflow
3. **Monitors** for 10 minutes (120 checks @ 5-second intervals)
4. **Alerts** if stuck at 25% or no progress for 1+ minute
5. **Logs** everything to `workflow_monitor_YYYYMMDD_HHMMSS.log`
6. **Reports** comprehensive metrics at the end

## Reading the Output

### Real-Time Format
```
[Check #15 | 75s] 🔄 in_progress | architecture_design | 25% | Stages: 3 | Agents: Frontend, Backend
```

- **Check #**: Sequential check number (1-120)
- **Time**: Elapsed seconds since start
- **Status**: Workflow status (⏳pending, 🔄in_progress, ✅completed, ❌failed)
- **Stage**: Current execution stage
- **Progress**: Percentage complete (0-100%)
- **Stages**: Number of completed stages
- **Agents**: Active agents (if any)

### Alert Types

#### 🚨 Stuck at 25%
```
⚠️  ALERT: Progress stuck at 25% for 120s
```
**Meaning**: Progress hasn't moved from 25% for over 2 minutes

#### 🚨 No Progress
```
⚠️  ALERT: No progress change for 60s
```
**Meaning**: No progress updates for over 1 minute

#### 📊 Checkpoint (every 5 minutes)
```
📊 CHECKPOINT - 5 minutes elapsed
Status: in_progress
Stage: frontend_development
Progress: 50%
```

## Finding the Log File

```bash
# View latest log
tail -f /Users/aideveloper/core/src/backend/workflow_monitor_*.log

# View all logs
ls -lt /Users/aideveloper/core/src/backend/workflow_monitor_*.log
```

## Understanding the Report

At the end, you'll get a comprehensive report with:

1. **Summary** - Final status and timing
2. **Status Changes** - When status transitioned
3. **Stage Changes** - Stage progression timeline
4. **Progress Changes** - How progress advanced
5. **Alerts** - Any stuck/stagnation alerts
6. **Errors** - All errors encountered
7. **Agent Activity** - When agents were active
8. **Conclusion** - Overall assessment

## Initial Test Results

**Test Run**: 2025-12-04 22:10:53
**Project**: Simple Next.js blog app
**Duration Tested**: ~3 minutes (so far)

### Key Observations

✅ **Working**:
- Authentication succeeds
- Workflow starts successfully
- Monitoring works perfectly
- Logging works correctly

❌ **Issues Found**:
- **Progress stuck at 0%** (not 25% as reported)
- Should be ~25% with 3 stages completed
- Progress calculation appears broken
- No active agents shown in status
- Stages taking >2 minutes each

### Status Progression (First 3 Minutes)
```
0-16s:  requirements_analysis (0% progress, 0 stages)
21s:    architecture_design   (0% progress, 1 stage)
26s:    architecture_design   (0% progress, 2 stages)
43s+:   architecture_design   (0% progress, 3 stages) - STUCK
```

## Interpreting Results

### Good Workflow (Expected)
```
[Check #  5 |  25s] 🔄 in_progress | architecture_design       | 10% | Stages: 1
[Check # 10 |  50s] 🔄 in_progress | frontend_development     | 25% | Stages: 3
[Check # 15 |  75s] 🔄 in_progress | backend_development      | 50% | Stages: 6
[Check # 20 | 100s] 🔄 in_progress | testing                  | 75% | Stages: 9
[Check # 25 | 125s] ✅ completed   | completion               | 100% | Stages: 12
```

### Problematic Workflow (Current)
```
[Check #  5 |  21s] ❓ running      | architecture_design       | 0% | Stages: 1
[Check # 10 |  49s] ❓ running      | architecture_design       | 0% | Stages: 3
[Check # 15 |  75s] ❓ running      | architecture_design       | 0% | Stages: 3
[Check # 20 | 102s] ❓ running      | architecture_design       | 0% | Stages: 3
[Check # 25 | 129s] ❓ running      | architecture_design       | 0% | Stages: 3
```

## Next Steps

1. **Let it run** for full 10 minutes to get complete data
2. **Check the final report** in the log file
3. **Investigate progress calculation** bug in `application_workflow.py`
4. **Verify agent status** reporting in status endpoint
5. **Compare with database** to see if persistence is working

## Script Configuration

Edit these values in `test_workflow_complete_verification.py`:

```python
MONITORING_DURATION = 600  # 10 minutes
POLL_INTERVAL = 5          # 5 seconds
STUCK_AT_25_THRESHOLD = 120  # 2 minutes
NO_PROGRESS_THRESHOLD = 60   # 1 minute
CHECKPOINT_INTERVAL = 300    # 5 minutes
```

## Troubleshooting

### Script won't start
```bash
# Check backend is running
curl http://localhost:8000/health

# Check Python dependencies
python3 -c "import httpx, asyncio"
```

### No log file created
```bash
# Check write permissions
touch /Users/aideveloper/core/src/backend/test.log
rm /Users/aideveloper/core/src/backend/test.log
```

### Authentication fails
```bash
# Verify credentials in script
grep "ADMIN_USERNAME\|ADMIN_PASSWORD" test_workflow_complete_verification.py
```

## Test Artifacts

After running, you'll have:
1. **Log file**: `workflow_monitor_YYYYMMDD_HHMMSS.log`
2. **Console output**: Real-time monitoring
3. **Project ID**: For manual verification
4. **Complete metrics**: For analysis

## Key Metrics to Watch

1. **Progress %** - Should increase steadily
2. **Stages completed** - Should grow (0 → 12)
3. **Stage duration** - Should be 20-60s per stage
4. **Active agents** - Should show during dev stages
5. **Errors** - Should be zero
6. **Alerts** - Should be zero for healthy workflow

## Integration Testing

This script can be used for:
- ✅ Regression testing
- ✅ Performance monitoring
- ✅ Bug investigation
- ✅ Progress tracking verification
- ✅ Database persistence testing
- ✅ Alert system validation

## Success Criteria

A successful workflow should show:
- ✅ Progress increases from 0% to 100%
- ✅ No alerts triggered
- ✅ All stages complete in <5 minutes
- ✅ Active agents visible during dev stages
- ✅ Final status: "completed"
- ✅ No errors in log

## Current Status

Based on initial 3-minute test:
- ❌ Progress calculation **BROKEN** (stuck at 0%)
- ❌ Stage execution **TOO SLOW** (>2 min per stage)
- ❌ Agent visibility **MISSING** (no agents shown)
- ✅ Workflow **RUNNING** (not crashed)
- ✅ Monitoring **WORKING** (captures all data)

**Recommendation**: Fix progress calculation as highest priority issue.
