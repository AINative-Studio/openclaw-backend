# Agent Swarm Orchestration System - Integration Plan

**Epic**: GitHub-Driven Autonomous Agent Swarm
**Status**: Planning Phase
**Created**: 2026-02-24
**Priority**: High
**Target**: OpenClaw Backend + Claude Code Agents

## Vision

Transform OpenClaw into an autonomous agent swarm that discovers GitHub issues, spawns Claude Code agents in isolated worktrees, monitors their progress, creates PRs, and handles failures with automatic respawn and enriched prompts.

## Target Architecture

```
GitHub Issues → Task Discovery → tasks.json → Agent Spawner → Claude Code (tmux)
                    ↓                                              ↓
                repos.json                                    Git Worktree
                    ↓                                              ↓
            Cron Jobs (5)                               PR Creation + CI
                    ↓                                              ↓
          Swarm Monitor ←────────────────────────────────────────┘
                    ↓
          State Machine (8 states)
                    ↓
          Failure Recovery → Respawn with enriched prompt
                    ↓
          Telegram Notifications
```

## State Machine (8 states)

```
pending → spawning → in_progress → pr_created → review_ready → merged → done
                          ↓              ↓
                       failed ←──────────┘
                          ↓
                    respawn (retry_count < 3) → pending
                          ↓
                      abandoned (retry_count >= 3)
```

## Key Components

### 1. Task Discovery Service
**Files**: `backend/services/task_discovery_service.py`

**Responsibilities**:
- Scan GitHub repos for issues matching labels
- Filter out existing tasks
- Add new tasks to tasks.json
- Auto-spawn if slots available

**Cron**: Every 30 minutes

### 2. Agent Spawner
**Files**: `scripts/spawn-agent.sh`, `backend/services/agent_spawner_service.py`

**Responsibilities**:
- Create git worktree for issue branch
- Create tmux session
- Run Claude Code with `--dangerously-skip-permissions`
- Inject task-specific prompt
- Track session metadata

### 3. Swarm Monitor
**Files**: `scripts/check-agents.sh`, `backend/services/swarm_monitor_service.py`

**Responsibilities**:
- Check tmux session health (every 10 min)
- Check GitHub PR status
- Check CI status
- Transition task states
- Detect timeouts (> 60 min)
- Trigger respawn on failure

**Cron**: Every 10 minutes

### 4. Failure Recovery System
**Files**: `scripts/respawn-agent.sh`, `backend/services/failure_recovery_service.py`

**Responsibilities**:
- Capture tmux output (last 50 lines)
- Classify failure: CRASH, TIMEOUT, TEST_FAILURE, STUCK
- Enrich prompt with failure context
- Log to metrics/prompt-history.jsonl
- Respawn agent with improved prompt
- Send Telegram notification

**Max Retries**: 3

### 5. PR Review Automation
**Files**: `backend/services/pr_review_service.py`

**Responsibilities**:
- Run gh-issues skill with --reviews-only
- Automated code review
- Suggest changes
- Manage review lifecycle

**Cron**: Every 15 minutes

### 6. Notification Service
**Files**: `scripts/notify.sh`, `backend/services/telegram_notification_service.py`

**Responsibilities**:
- Send Telegram messages via OpenClaw
- Task discovery summaries
- State change notifications
- Daily digests
- Failure alerts

### 7. Cleanup Service
**Files**: `scripts/cleanup.sh`, `backend/services/swarm_cleanup_service.py`

**Responsibilities**:
- Archive completed/merged tasks
- Remove stale git worktrees
- Kill leftover tmux sessions

**Cron**: 2 AM IST daily

## Data Models

### tasks.json
```json
{
  "task_id": "uuid",
  "repo_name": "openclaw-backend",
  "issue_number": 123,
  "issue_url": "https://github.com/...",
  "title": "Fix authentication bug",
  "labels": ["bug", "priority:high"],
  "state": "in_progress",
  "worktree_path": "/path/to/worktree",
  "branch_name": "fix/issue-123",
  "tmux_session": "agent-123",
  "pr_number": null,
  "retry_count": 0,
  "max_retries": 3,
  "spawned_at": "2026-02-24T12:00:00Z",
  "updated_at": "2026-02-24T12:30:00Z",
  "failure_context": null
}
```

### repos.json
```json
{
  "name": "openclaw-backend",
  "owner": "AINative-Studio",
  "repo": "openclaw-backend",
  "path": "/Users/aideveloper/openclaw-backend",
  "enabled": true,
  "labels_filter": ["bug", "feature", "ready"],
  "scan_issues": true,
  "max_concurrent_agents": 4
}
```

### metrics/prompt-history.jsonl
```json
{"task_id": "uuid", "retry_count": 1, "failure_type": "TEST_FAILURE", "context": "...", "enriched_prompt": "...", "timestamp": "..."}
```

## Cron Jobs (5)

| Name | Frequency | Script | Purpose |
|------|-----------|--------|---------|
| task-discovery | Every 30 min | discover-tasks.sh | Scan GitHub, spawn agents |
| swarm-monitor | Every 10 min | check-agents.sh | Monitor sessions, PRs, CI |
| pr-review | Every 15 min | (gh-issues skill) | Automated code review |
| daily-summary | 8 PM IST | (summary script) | Telegram digest |
| swarm-cleanup | 2 AM IST | cleanup.sh | Archive + cleanup |

## API Endpoints (New)

### Task Management
```
GET    /api/v1/swarm/tasks              - List all tasks
POST   /api/v1/swarm/tasks              - Manually create task
GET    /api/v1/swarm/tasks/{task_id}    - Get task details
PUT    /api/v1/swarm/tasks/{task_id}    - Update task state
DELETE /api/v1/swarm/tasks/{task_id}    - Cancel/abandon task
```

### Monitoring
```
GET    /api/v1/swarm/status             - Swarm health dashboard
GET    /api/v1/swarm/metrics            - Task success/failure rates
GET    /api/v1/swarm/sessions           - Active tmux sessions
```

### Configuration
```
GET    /api/v1/swarm/repos              - List monitored repos
POST   /api/v1/swarm/repos              - Add repo
PUT    /api/v1/swarm/repos/{name}       - Update repo config
DELETE /api/v1/swarm/repos/{name}       - Remove repo
```

## Scripts (Shell)

### 1. discover-tasks.sh
```bash
# Scan GitHub for new issues
# Add to tasks.json
# Auto-spawn if slots available
# Send Telegram notification
```

### 2. spawn-agent.sh
```bash
# Args: task_id, repo_path, issue_number, branch_name
# Create git worktree
# Create tmux session
# Run Claude Code with prompt template
# Update tasks.json state to "in_progress"
```

### 3. check-agents.sh
```bash
# For each active task:
#   - Check tmux session alive
#   - Check PR created
#   - Check CI status
#   - Transition state
#   - Trigger respawn if failed
# Send Telegram summary
```

### 4. respawn-agent.sh
```bash
# Args: task_id
# Capture tmux output
# Classify failure
# Build enriched prompt
# Log to metrics/prompt-history.jsonl
# Increment retry_count
# Spawn new agent with enriched prompt
# Send Telegram notification
```

### 5. cleanup.sh
```bash
# Archive tasks in done/merged/abandoned states
# Remove git worktrees
# Kill tmux sessions
# Vacuum metrics logs
```

### 6. notify.sh
```bash
# Args: message, priority
# Send Telegram via OpenClaw API
```

## Prompt Templates

### prompts/bug-fix.md
```markdown
You are an expert software engineer tasked with fixing bug #{{ISSUE_NUMBER}}.

Issue: {{ISSUE_TITLE}}
Description: {{ISSUE_BODY}}

Repository: {{REPO_NAME}}
Branch: {{BRANCH_NAME}}

Steps:
1. Read the issue carefully
2. Locate the bug in the codebase
3. Write failing tests
4. Fix the bug
5. Ensure tests pass
6. Create PR with summary

{{FAILURE_CONTEXT}}
```

### prompts/feature.md
```markdown
You are an expert software engineer implementing feature #{{ISSUE_NUMBER}}.

Feature: {{ISSUE_TITLE}}
Requirements: {{ISSUE_BODY}}

Repository: {{REPO_NAME}}
Branch: {{BRANCH_NAME}}

Steps:
1. Read feature requirements
2. Design the implementation
3. Write tests (TDD)
4. Implement feature
5. Ensure all tests pass
6. Create PR with documentation

{{FAILURE_CONTEXT}}
```

### Failure Context Injection
```markdown
## Previous Attempt Failed (Retry {{RETRY_COUNT}}/{{MAX_RETRIES}})

Failure Type: {{FAILURE_TYPE}}
Error Output:
```
{{TMUX_OUTPUT}}
```

Suggested Fix:
{{FAILURE_ADVICE}}
```

## Authentication

Agents authenticate via `CLAUDE_CODE_OAUTH_TOKEN` environment variable, read from `.claude-token` file.

**Token Generation**:
```bash
claude setup-token
# Generates 1-year OAuth token
# Stored in .claude-token (600 permissions)
```

## Implementation Phases

### Phase 1: Foundation (Week 1-2)
- [ ] Create tasks.json schema and CRUD operations
- [ ] Create repos.json config file
- [ ] Implement TaskDiscoveryService (GitHub API integration)
- [ ] Create spawn-agent.sh script
- [ ] Test manual task spawning

### Phase 2: Monitoring (Week 3)
- [ ] Implement SwarmMonitorService
- [ ] Create check-agents.sh script
- [ ] Implement state machine transitions
- [ ] Add tmux session health checks
- [ ] Add GitHub PR status checks

### Phase 3: Failure Recovery (Week 4)
- [ ] Implement FailureRecoveryService
- [ ] Create respawn-agent.sh script
- [ ] Implement failure classification logic
- [ ] Create prompt enrichment system
- [ ] Add metrics/prompt-history.jsonl logging

### Phase 4: Automation (Week 5)
- [ ] Set up cron jobs (5 total)
- [ ] Implement TelegramNotificationService
- [ ] Create notify.sh script
- [ ] Implement daily summary generation
- [ ] Create cleanup.sh script

### Phase 5: UI & Polish (Week 6)
- [ ] Add Swarm Dashboard UI (frontend)
- [ ] Add task list view
- [ ] Add real-time monitoring
- [ ] Add manual task creation form
- [ ] Documentation

## Dependencies

### External Tools
- `gh` CLI (GitHub)
- `tmux` (session management)
- `git` (worktree support)
- `claude` CLI (Claude Code)
- `jq` (JSON parsing in bash)

### Python Packages
- `PyGithub` - GitHub API client
- `schedule` - Cron job scheduling
- `libtmux` - Python tmux bindings (optional)

### Configuration Files
- `.claude-token` - OAuth token (600 perms)
- `repos.json` - Multi-repo config
- `tasks.json` - Live task registry
- `prompts/*.md` - Prompt templates

## Security Considerations

1. **Token Storage**: `.claude-token` must have 600 permissions
2. **Git Worktrees**: Isolated from main working directory
3. **Session Isolation**: Each agent in separate tmux session
4. **Auto-spawn Limits**: `max_concurrent_agents` prevents resource exhaustion
5. **Failure Cap**: Max 3 retries prevents infinite loops

## Monitoring Metrics

Track in Prometheus + Grafana:
- Tasks discovered per hour
- Active agents
- Success rate (merged PRs / total tasks)
- Failure rate by type (CRASH, TIMEOUT, TEST_FAILURE, STUCK)
- Average time to PR creation
- Average time to merge
- Retry distribution (0, 1, 2, 3 retries)

## Open Questions

1. **Telegram vs Email**: Should we support email notifications too?
   - Recommendation: Start with Telegram, add email later

2. **Parallel Repos**: Can one agent work on multiple repos?
   - Recommendation: No, one agent per repo clone to avoid conflicts

3. **Priority Queue**: Should high-priority issues spawn first?
   - Recommendation: Yes, add priority field to tasks.json

4. **Human Review**: Should all PRs require human approval?
   - Recommendation: Yes for production, optional for dev (feature flag)

5. **Cost Control**: How to limit Claude Code API usage?
   - Recommendation: Set max concurrent agents, add spending alerts

## Success Criteria

- [ ] System discovers GitHub issues automatically
- [ ] Agents spawn in isolated worktrees + tmux
- [ ] Agents create PRs without human intervention
- [ ] Failed agents respawn with enriched prompts (up to 3x)
- [ ] Telegram notifications sent for key events
- [ ] Cleanup removes stale worktrees and sessions
- [ ] >70% of spawned agents create valid PRs
- [ ] Average retry count < 1.5

## Timeline

| Week | Phase | Deliverables |
|------|-------|--------------|
| 1-2 | Foundation | Task discovery, agent spawning |
| 3 | Monitoring | State machine, session checks |
| 4 | Recovery | Failure classification, respawn |
| 5 | Automation | Cron jobs, notifications, cleanup |
| 6 | UI & Polish | Dashboard, docs, testing |

**Total**: 6 weeks

## Related Documents

- [P2P Security Integration Plan](P2P_SECURITY_INTEGRATION_PLAN.md)
- [P2P Node UI Design](P2P_NODE_UI_DESIGN.md)
- [CLAUDE.md](../CLAUDE.md) - Current system architecture

---

**Document Version**: 1.0
**Last Updated**: 2026-02-24
**Status**: Ready for Gap Analysis
