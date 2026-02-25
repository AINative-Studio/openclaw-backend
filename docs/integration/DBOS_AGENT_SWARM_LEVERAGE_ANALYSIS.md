# DBOS Leverage Analysis for Agent Swarm Orchestration

**Status**: Strategic Architecture Analysis
**Created**: 2026-02-25
**Purpose**: Analyze how to leverage existing DBOS infrastructure for Agent Swarm Orchestration

---

## Executive Summary

**YES - We can and SHOULD leverage DBOS extensively for Agent Swarm Orchestration.**

DBOS provides **exactly** the capabilities we need for long-running agent workflows with automatic crash recovery, state persistence, and built-in retry logic.

### Key Benefits:
- ✅ **Crash Recovery**: If orchestrator crashes, DBOS auto-resumes from last checkpoint
- ✅ **Long-Running Workflows**: Agent tasks can run for hours - DBOS handles this natively
- ✅ **State Persistence**: All workflow state stored in PostgreSQL, survives restarts
- ✅ **Built-in Retries**: Automatic retry logic with exponential backoff
- ✅ **Multi-Step Workflows**: Perfect for discover → spawn → monitor → PR flow
- ✅ **Already Integrated**: Gateway already running, agent lifecycle workflows proven

---

## Current DBOS Usage (Proven Pattern)

### Existing Agent Lifecycle Workflow

From `openclaw-gateway/dist/workflows/agent-lifecycle-workflow.js`:

```typescript
@Workflow()
static async provisionAgentWorkflow(ctx, request) {
  // Step 1: Validate request
  await this.validateProvisionRequest(ctx, request);

  // Step 2: Store metadata (idempotent, survives crashes)
  await this.storeAgentMetadata(ctx, request);

  // Step 3: Connect channels (external call via @Communicator)
  const channelResult = await this.connectAgentChannels(ctx, request);

  // Step 4: Start heartbeat monitoring
  await this.startHeartbeatMonitoring(ctx, request);

  // Step 5: Update status to running
  await this.updateAgentStatus(ctx, request.agentId, 'running', channelResult.openclawAgentId);

  return { agentId, status: 'provisioned', ... };
}
```

**Key Pattern**: Multi-step workflow with automatic checkpointing. If crash occurs after Step 2, DBOS auto-resumes from Step 3.

### DBOS Decorators

1. **`@Workflow()`**: Main orchestration function with crash recovery
2. **`@Step()`**: Database operations (idempotent, logged in DBOS)
3. **`@Communicator()`**: External API calls (GitHub, tmux, shell commands)

---

## Agent Swarm Orchestration: DBOS Mapping

### Component 1: Task Discovery Service

**Current Plan**: Cron job every 30 min scanning GitHub
**DBOS Enhancement**: Scheduled durable workflow

```typescript
@Workflow()
static async taskDiscoveryWorkflow(ctx, repoConfig) {
  // Step 1: Fetch GitHub issues (Communicator for API calls)
  const issues = await this.fetchGitHubIssues(ctx, repoConfig);

  // Step 2: Filter existing tasks (Step for DB query)
  const newIssues = await this.filterExistingTasks(ctx, issues);

  // Step 3: Create task records (Step for DB insert)
  const tasks = await this.createTaskRecords(ctx, newIssues);

  // Step 4: Auto-spawn if slots available (Communicator for shell exec)
  for (const task of tasks) {
    if (await this.hasSlotsAvailable(ctx, repoConfig)) {
      await ctx.startWorkflow(AgentSpawnerWorkflow, { task });
    }
  }

  return { discovered: tasks.length };
}

@Communicator()
static async fetchGitHubIssues(ctx, repoConfig) {
  // Use PyGithub to fetch issues
  // External API call - DBOS logs but doesn't retry automatically
}

@Step()
static async filterExistingTasks(ctx, issues) {
  // Query tasks.json or DB to filter duplicates
}
```

**Benefits**:
- **Crash Recovery**: If orchestrator crashes mid-discovery, DBOS resumes
- **Idempotent**: Steps can be re-run without side effects
- **Audit Trail**: DBOS logs every step execution in `dbos_system.workflow_status`

---

### Component 2: Agent Spawner

**Current Plan**: Shell script + Python service
**DBOS Enhancement**: Durable multi-step workflow

```typescript
@Workflow()
static async agentSpawnerWorkflow(ctx, { task, repoConfig }) {
  // Step 1: Validate task is PENDING
  await this.validateTaskPending(ctx, task.task_id);

  // Step 2: Transition to SPAWNING
  await this.updateTaskStatus(ctx, task.task_id, 'spawning');

  // Step 3: Create git worktree (Communicator for shell)
  const worktreePath = await this.createGitWorktree(ctx, task);

  // Step 4: Create tmux session (Communicator for shell)
  const tmuxSession = await this.createTmuxSession(ctx, task);

  // Step 5: Generate prompt from template
  const prompt = await this.generatePrompt(ctx, task);

  // Step 6: Spawn Claude Code agent (Communicator for shell)
  await this.spawnClaudeCodeAgent(ctx, task, prompt);

  // Step 7: Transition to IN_PROGRESS
  await this.updateTaskStatus(ctx, task.task_id, 'in_progress', {
    worktree_path: worktreePath,
    tmux_session: tmuxSession,
    spawned_at: new Date().toISOString()
  });

  // Step 8: Start monitoring workflow
  await ctx.startWorkflow(SwarmMonitorWorkflow, { task });

  return { task_id: task.task_id, status: 'spawned' };
}

@Communicator()
static async createGitWorktree(ctx, task) {
  // Execute: git worktree add /path/to/worktree branch-name
  // External shell command
}

@Communicator()
static async spawnClaudeCodeAgent(ctx, task, prompt) {
  // Execute: tmux send-keys -t session "claude --prompt 'prompt'" Enter
  // External shell command
}
```

**Benefits**:
- **Crash Recovery**: If crash after worktree creation, DBOS skips worktree step on resume
- **Cleanup on Failure**: Can add error handling to remove partial worktrees
- **State Tracking**: All metadata stored in DBOS workflow state

---

### Component 3: Swarm Monitor

**Current Plan**: Cron job every 10 min checking tmux/GitHub/CI
**DBOS Enhancement**: Long-running durable workflow per task

```typescript
@Workflow()
static async swarmMonitorWorkflow(ctx, { task }) {
  let currentStatus = 'in_progress';
  let retryCount = 0;

  // Loop until task reaches terminal state
  while (!['done', 'merged', 'abandoned'].includes(currentStatus)) {
    // Step 1: Check tmux session health
    const sessionHealth = await this.checkTmuxSession(ctx, task.tmux_session);

    if (!sessionHealth.alive) {
      // Tmux died - trigger failure recovery
      await ctx.startWorkflow(FailureRecoveryWorkflow, {
        task,
        failure_type: 'CRASH',
        context: sessionHealth.lastOutput
      });
      return;
    }

    // Step 2: Check for PR creation
    const prStatus = await this.checkPRStatus(ctx, task);
    if (prStatus.pr_created && currentStatus === 'in_progress') {
      await this.updateTaskStatus(ctx, task.task_id, 'pr_created', {
        pr_number: prStatus.pr_number,
        pr_url: prStatus.pr_url
      });
      currentStatus = 'pr_created';
    }

    // Step 3: Check CI status
    if (currentStatus === 'pr_created') {
      const ciStatus = await this.checkCIStatus(ctx, task);
      if (ciStatus.all_passed) {
        await this.updateTaskStatus(ctx, task.task_id, 'review_ready');
        currentStatus = 'review_ready';
      }
    }

    // Step 4: Check timeout (>60 min)
    const elapsedMs = Date.now() - new Date(task.spawned_at).getTime();
    if (elapsedMs > 60 * 60 * 1000) {
      await ctx.startWorkflow(FailureRecoveryWorkflow, {
        task,
        failure_type: 'TIMEOUT',
        context: 'Task exceeded 60 minute limit'
      });
      return;
    }

    // Step 5: Sleep for 10 minutes (DBOS supports ctx.sleep)
    await ctx.sleep(10 * 60 * 1000);
  }

  return { task_id: task.task_id, final_status: currentStatus };
}

@Communicator()
static async checkTmuxSession(ctx, sessionName) {
  // Execute: tmux has-session -t session && tmux capture-pane -p -t session
  // Returns { alive: boolean, lastOutput: string }
}

@Communicator()
static async checkPRStatus(ctx, task) {
  // Execute: gh pr list --repo owner/repo --head branch
  // Returns { pr_created: boolean, pr_number: number, pr_url: string }
}
```

**Benefits**:
- **Persistent Monitoring**: Workflow survives orchestrator restarts
- **ctx.sleep()**: DBOS supports long sleeps without holding connections
- **Auto-Resume**: If crash during sleep, DBOS resumes after sleep completes

---

### Component 4: Failure Recovery System

**Current Plan**: Shell script + Python service for respawn
**DBOS Enhancement**: Durable retry workflow with enriched prompts

```typescript
@Workflow()
static async failureRecoveryWorkflow(ctx, { task, failure_type, context }) {
  // Step 1: Capture tmux output (if session still alive)
  const tmuxOutput = await this.captureTmuxOutput(ctx, task.tmux_session);

  // Step 2: Classify failure
  const classification = await this.classifyFailure(ctx, failure_type, context, tmuxOutput);

  // Step 3: Check retry limit
  if (task.retry_count >= 3) {
    await this.updateTaskStatus(ctx, task.task_id, 'abandoned', {
      failure_type,
      final_context: context
    });
    await this.sendTelegramNotification(ctx, {
      message: `Task ${task.task_id} abandoned after 3 retries`,
      priority: 'high'
    });
    return { task_id: task.task_id, status: 'abandoned' };
  }

  // Step 4: Enrich prompt with failure context
  const enrichedPrompt = await this.enrichPrompt(ctx, task, classification, tmuxOutput);

  // Step 5: Log to metrics/prompt-history.jsonl
  await this.logPromptHistory(ctx, {
    task_id: task.task_id,
    retry_count: task.retry_count + 1,
    failure_type: classification.category,
    context,
    enriched_prompt: enrichedPrompt
  });

  // Step 6: Cleanup old worktree/tmux
  await this.cleanupFailedTask(ctx, task);

  // Step 7: Increment retry count, reset to PENDING
  await this.updateTaskStatus(ctx, task.task_id, 'pending', {
    retry_count: task.retry_count + 1,
    failure_context: context
  });

  // Step 8: Calculate backoff (exponential: 2^retry_count minutes)
  const backoffMs = Math.pow(2, task.retry_count) * 60 * 1000;
  await ctx.sleep(backoffMs);

  // Step 9: Respawn agent with enriched prompt
  await ctx.startWorkflow(AgentSpawnerWorkflow, {
    task: { ...task, retry_count: task.retry_count + 1 },
    promptOverride: enrichedPrompt
  });

  // Step 10: Send Telegram notification
  await this.sendTelegramNotification(ctx, {
    message: `Task ${task.task_id} respawned (attempt ${task.retry_count + 1}/3)`,
    priority: 'normal'
  });

  return { task_id: task.task_id, status: 'respawned' };
}

@Step()
static async classifyFailure(ctx, failure_type, context, tmuxOutput) {
  // Classify as CRASH, TIMEOUT, TEST_FAILURE, STUCK
  // Store in DB for metrics
}

@Communicator()
static async cleanupFailedTask(ctx, task) {
  // Execute: git worktree remove path && tmux kill-session -t session
}
```

**Benefits**:
- **Automatic Retry**: Built-in exponential backoff with ctx.sleep()
- **Failure Audit**: All retry attempts logged in DBOS workflow history
- **Crash-Safe Cleanup**: If cleanup fails, DBOS can retry cleanup on resume

---

### Component 5: PR Review Automation

**Current Plan**: Cron job every 15 min running gh-issues skill
**DBOS Enhancement**: Durable review workflow per PR

```typescript
@Workflow()
static async prReviewWorkflow(ctx, { task, pr }) {
  // Step 1: Fetch PR diff
  const diff = await this.fetchPRDiff(ctx, pr);

  // Step 2: Run automated code review
  const reviewComments = await this.performCodeReview(ctx, diff);

  // Step 3: Post review comments
  await this.postReviewComments(ctx, pr, reviewComments);

  // Step 4: Approve or request changes
  const decision = reviewComments.critical_issues > 0 ? 'request_changes' : 'approve';
  await this.submitReview(ctx, pr, decision);

  // Step 5: Update task status
  await this.updateTaskStatus(ctx, task.task_id,
    decision === 'approve' ? 'review_ready' : 'in_progress');

  return { pr_number: pr.number, review_decision: decision };
}
```

---

### Component 6: Cleanup Service

**Current Plan**: Daily cron at 2 AM IST
**DBOS Enhancement**: Scheduled durable cleanup workflow

```typescript
@Workflow()
static async swarmCleanupWorkflow(ctx, cutoffDate) {
  // Step 1: Query completed/merged/abandoned tasks
  const tasksToArchive = await this.queryArchivableTasks(ctx, cutoffDate);

  // Step 2: Archive each task
  for (const task of tasksToArchive) {
    await this.archiveTask(ctx, task);
    await this.removeGitWorktree(ctx, task.worktree_path);
    await this.killTmuxSession(ctx, task.tmux_session);
  }

  // Step 3: Vacuum metrics logs (keep last 30 days)
  await this.vacuumMetricsLogs(ctx, 30);

  return { archived: tasksToArchive.length };
}
```

---

## DBOS Architecture for Agent Swarm

### Workflow Hierarchy

```
TaskDiscoveryWorkflow (scheduled every 30 min)
    └──> AgentSpawnerWorkflow (per task)
            └──> SwarmMonitorWorkflow (long-running, per task)
                    ├──> FailureRecoveryWorkflow (on failure)
                    │       └──> AgentSpawnerWorkflow (respawn)
                    └──> PRReviewWorkflow (on PR creation)

SwarmCleanupWorkflow (scheduled daily at 2 AM IST)
```

### DBOS Tables (Existing + New)

**Existing** (from gateway):
- `dbos_system.workflow_status` - All workflow executions
- `dbos_system.workflow_inputs` - Workflow parameters
- `dbos_system.workflow_events` - Step execution log

**New** (Agent Swarm specific):
- `swarm_tasks` - Task registry (replaces tasks.json)
- `swarm_repos` - Repo configuration (replaces repos.json)
- `swarm_prompt_history` - Failure recovery metrics

### Database Schema (PostgreSQL)

```sql
CREATE TABLE swarm_tasks (
  task_id UUID PRIMARY KEY,
  repo_name TEXT NOT NULL,
  issue_number INT NOT NULL,
  issue_url TEXT,
  title TEXT,
  labels JSONB,
  state TEXT CHECK (state IN ('pending', 'spawning', 'in_progress',
                               'pr_created', 'review_ready', 'merged',
                               'done', 'failed', 'abandoned')),
  worktree_path TEXT,
  branch_name TEXT,
  tmux_session TEXT,
  pr_number INT,
  pr_url TEXT,
  retry_count INT DEFAULT 0,
  max_retries INT DEFAULT 3,
  spawned_at TIMESTAMPTZ,
  pr_created_at TIMESTAMPTZ,
  merged_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ DEFAULT NOW(),
  failure_context JSONB,
  workflow_uuid UUID, -- Links to DBOS workflow
  UNIQUE(repo_name, issue_number)
);

CREATE TABLE swarm_repos (
  name TEXT PRIMARY KEY,
  owner TEXT NOT NULL,
  repo TEXT NOT NULL,
  path TEXT NOT NULL,
  enabled BOOLEAN DEFAULT true,
  labels_filter JSONB,
  scan_issues BOOLEAN DEFAULT true,
  max_concurrent_agents INT DEFAULT 4,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE swarm_prompt_history (
  id SERIAL PRIMARY KEY,
  task_id UUID REFERENCES swarm_tasks(task_id),
  retry_count INT,
  failure_type TEXT,
  context TEXT,
  enriched_prompt TEXT,
  timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_swarm_tasks_state ON swarm_tasks(state);
CREATE INDEX idx_swarm_tasks_repo ON swarm_tasks(repo_name);
CREATE INDEX idx_swarm_tasks_workflow ON swarm_tasks(workflow_uuid);
```

---

## Migration Strategy: Cron → DBOS

### Phase 1: Hybrid Approach (Weeks 1-2)

Keep cron jobs, add DBOS workflows in parallel:

```bash
# Cron job triggers DBOS workflow via HTTP
*/30 * * * * curl -X POST http://localhost:18789/workflows/task-discovery

# Python cron script
import httpx

async def trigger_discovery():
    response = await httpx.post(
        "http://localhost:18789/workflows/task-discovery",
        json={"repo": "openclaw-backend"}
    )
    workflow_uuid = response.json()["workflow_uuid"]
    print(f"Started workflow: {workflow_uuid}")
```

### Phase 2: Pure DBOS (Weeks 3-4)

Replace cron with DBOS scheduled workflows:

```typescript
// In gateway: register scheduled workflows
import { ScheduledWorkflow } from '@dbos-inc/dbos-sdk';

@ScheduledWorkflow({ cron: '*/30 * * * *' })  // Every 30 min
static async scheduledTaskDiscovery(ctx) {
  const repos = await ctx.query('SELECT * FROM swarm_repos WHERE enabled = true');
  for (const repo of repos.rows) {
    await ctx.startWorkflow(TaskDiscoveryWorkflow, { repo });
  }
}

@ScheduledWorkflow({ cron: '0 2 * * *' })  // 2 AM daily
static async scheduledCleanup(ctx) {
  const cutoffDate = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  await ctx.startWorkflow(SwarmCleanupWorkflow, { cutoffDate });
}
```

---

## Implementation Checklist

### Week 1-2: Foundation with DBOS
- [ ] Create `swarm_tasks`, `swarm_repos`, `swarm_prompt_history` tables
- [ ] Implement `TaskDiscoveryWorkflow` with @Workflow decorator
- [ ] Implement `AgentSpawnerWorkflow` with git worktree + tmux steps
- [ ] Test workflow crash recovery (kill gateway mid-spawn)

### Week 3: Monitoring with DBOS
- [ ] Implement `SwarmMonitorWorkflow` with long-running loop
- [ ] Test ctx.sleep() for 10-minute intervals
- [ ] Verify workflow survives orchestrator restart

### Week 4: Failure Recovery with DBOS
- [ ] Implement `FailureRecoveryWorkflow` with retry logic
- [ ] Test exponential backoff with ctx.sleep()
- [ ] Verify prompt enrichment and respawn

### Week 5: Automation with DBOS
- [ ] Replace cron jobs with `@ScheduledWorkflow`
- [ ] Implement Telegram notifications via @Communicator
- [ ] Create `SwarmCleanupWorkflow`

### Week 6: UI & Polish
- [ ] Add workflow UUID to task list UI
- [ ] Add "View Workflow" link to DBOS dashboard
- [ ] Document DBOS workflow patterns

---

## Advantages vs. Pure Cron/Python

| Feature | Cron + Python | DBOS Workflows |
|---------|--------------|----------------|
| **Crash Recovery** | ❌ Manual restart, lost state | ✅ Auto-resume from checkpoint |
| **Long-Running** | ❌ Process must stay alive | ✅ Workflow persisted in DB |
| **Retry Logic** | ⚠️ Manual implementation | ✅ Built-in with ctx.sleep() |
| **Audit Trail** | ⚠️ Custom logging | ✅ Full execution log in DB |
| **State Persistence** | ❌ tasks.json file I/O | ✅ PostgreSQL transactions |
| **Concurrency** | ⚠️ Manage locks manually | ✅ DBOS handles isolation |
| **Monitoring** | ⚠️ Custom metrics | ✅ Built-in workflow dashboard |

---

## Risks & Mitigations

### Risk 1: DBOS Gateway Downtime
**Impact**: All workflows blocked
**Mitigation**:
- Implement graceful fallback (already done in E6-S3 partition detection)
- Gateway auto-restarts on crash
- Add health checks and alerts

### Risk 2: Workflow State Bloat
**Impact**: PostgreSQL storage grows over time
**Mitigation**:
- DBOS has built-in TTL for workflow history
- Configure retention: `workflowRetentionDays: 30` in dbos-config.yaml
- Cleanup workflow archives old tasks

### Risk 3: Complex Debugging
**Impact**: Hard to trace workflow failures
**Mitigation**:
- DBOS provides web dashboard at `http://localhost:18789/workflows/:uuid`
- All steps logged with timestamps
- Can replay workflows from specific step

---

## Success Metrics

Track in Prometheus + Grafana:

1. **Workflow Success Rate**: `sum(dbos_workflow_completed) / sum(dbos_workflow_started)`
2. **Average Workflow Duration**: `avg(dbos_workflow_duration_seconds)`
3. **Retry Distribution**: Count workflows by retry_count (0, 1, 2, 3)
4. **Crash Recovery Events**: Count DBOS auto-resume events
5. **Workflow Backlog**: Count workflows in "PENDING" state

---

## Recommendation

**Use DBOS for ALL Agent Swarm components.**

### Primary Workflows:
1. **TaskDiscoveryWorkflow** - Scheduled every 30 min
2. **AgentSpawnerWorkflow** - Per task, multi-step with worktree/tmux
3. **SwarmMonitorWorkflow** - Long-running per task, 10-min polling
4. **FailureRecoveryWorkflow** - Retry logic with exponential backoff
5. **PRReviewWorkflow** - Automated code review per PR
6. **SwarmCleanupWorkflow** - Scheduled daily at 2 AM IST

### Benefits:
- ✅ Proven pattern (agent lifecycle already uses this)
- ✅ Automatic crash recovery without custom retry logic
- ✅ Built-in audit trail and monitoring
- ✅ Simplified state management (no tasks.json file I/O)
- ✅ PostgreSQL transactions for consistency
- ✅ Easy to test (can kill gateway and verify resume)

---

**Document Version**: 1.0
**Last Updated**: 2026-02-25
**Status**: Ready for Implementation
