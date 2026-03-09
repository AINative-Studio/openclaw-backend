# Phase 4: DBOS Skills Integration - Analysis

**Date**: March 7, 2026
**Status**: NOT STARTED (0%)

---

## Executive Summary

**Phase 4 Claim**: "Need SkillInstallationWorkflow and SkillExecutionWorkflow for durable skill operations"

**Verification Result**: ✅ **CLAIM IS VALID** - Phase 4 is genuinely needed

**Current State**:
- ✅ Skill installation service EXISTS (`skill_installation_service.py`)
- ✅ Skill API endpoints EXIST (`skill_installation.py`)
- ❌ NO crash recovery for installations
- ❌ NO atomic transactions
- ❌ NO rollback on failures
- ❌ NO skill execution workflows
- ❌ NO execution history tracking

**Impact**: Skills can be installed/used, but:
- Installation can fail halfway (leaves system in bad state)
- No automatic retry on transient failures
- No audit trail of what was installed when
- Skill execution has no crash recovery

---

## What EXISTS Today

### 1. Backend Skill Services ✅

**File**: `backend/services/skill_installation_service.py`

**Capabilities**:
- NPM skill installation (`install_neuro_skill()`)
- Homebrew package installation (`install_brew_package()`)
- Binary verification after install
- Timeout handling (default 300s)

**Limitations**:
- ❌ Non-atomic: If npm succeeds but binary check fails, no rollback
- ❌ No retry logic
- ❌ No installation history
- ❌ No crash recovery

**Example Code**:
```python
async def install_neuro_skill(
    self,
    skill_name: str,
    neuro_package: str,
    timeout: int = 300,
) -> InstallResult:
    # Step 1: npm install -g
    # Step 2: Verify binary exists
    # If Step 2 fails, Step 1's changes remain (no rollback!)
```

### 2. Backend Skill API Endpoints ✅

**File**: `backend/api/v1/endpoints/skill_installation.py`

**Endpoints**:
- `GET /api/v1/skills/installable` - List installable skills
- `POST /api/v1/skills/{name}/install` - Install a skill
- `GET /api/v1/skills/{name}/installation-status` - Check if installed
- `DELETE /api/v1/skills/{name}/install` - Uninstall (NPM only)

**Limitations**:
- ❌ Direct service calls (not durable)
- ❌ No workflow orchestration
- ❌ Install failures leave partial state

### 3. Gateway Has NO Skill Workflows ❌

**Current Workflows**:
- `agent-lifecycle-workflow.ts` - Agent provisioning
- `agent-message-workflow.ts` - Message handling
- `chat-workflow.ts` - Chat with personality/memory

**Missing**:
- ❌ `skill-installation-workflow.ts`
- ❌ `skill-execution-workflow.ts`

---

## What's MISSING (Phase 4 Requirements)

### 1. SkillInstallationWorkflow ❌

**File**: `openclaw-gateway/src/workflows/skill-installation-workflow.ts` (DOES NOT EXIST)

**Required Functionality**:

```typescript
import { DBOS, WorkflowContext } from '@dbos-inc/dbos-sdk';

export interface SkillInstallRequest {
  skillName: string;
  method: 'npm' | 'brew';
  agentId?: string;
}

export interface SkillInstallResult {
  success: boolean;
  skillName: string;
  installedAt: Date;
  binaryPath?: string;
  error?: string;
}

export class SkillInstallationWorkflow {
  /**
   * Durable skill installation with rollback
   *
   * Steps:
   * 1. Validate prerequisites (package manager available)
   * 2. Record installation start in DB
   * 3. Execute installation command (npm/brew)
   * 4. Verify binary exists and is executable
   * 5. Record success in DB
   *
   * On failure: Rollback (uninstall package)
   * On crash: Resume from last completed step
   */
  @DBOS.workflow()
  static async installSkill(
    ctx: WorkflowContext,
    request: SkillInstallRequest
  ): Promise<SkillInstallResult> {
    // Step 1: Pre-flight validation
    const validated = await ctx.invoke(this.validatePrerequisites, request);
    if (!validated.success) {
      return { success: false, skillName: request.skillName, error: validated.error };
    }

    // Step 2: Record installation attempt (audit trail)
    await ctx.invoke(this.recordInstallationStart, request);

    // Step 3: Execute installation (durable step)
    let installResult;
    try {
      installResult = await ctx.invoke(this.executeInstallCommand, request);
    } catch (error) {
      // Rollback on failure
      await ctx.invoke(this.rollbackInstallation, request);
      throw error;
    }

    // Step 4: Verify binary (crash-recoverable)
    const verified = await ctx.invoke(this.verifyBinary, request.skillName);
    if (!verified.success) {
      // Rollback - binary not found
      await ctx.invoke(this.rollbackInstallation, request);
      return { success: false, skillName: request.skillName, error: 'Binary verification failed' };
    }

    // Step 5: Record success
    await ctx.invoke(this.recordInstallationSuccess, {
      skillName: request.skillName,
      binaryPath: verified.binaryPath,
      installedAt: new Date()
    });

    return {
      success: true,
      skillName: request.skillName,
      installedAt: new Date(),
      binaryPath: verified.binaryPath
    };
  }

  @DBOS.step()
  static async validatePrerequisites(ctx: WorkflowContext, request: SkillInstallRequest) {
    // Check if npm/brew is available
    // Return { success: boolean, error?: string }
  }

  @DBOS.step()
  static async executeInstallCommand(ctx: WorkflowContext, request: SkillInstallRequest) {
    // Call Backend API: POST /api/v1/skills/{name}/install
    // This wraps the existing SkillInstallationService logic
  }

  @DBOS.step()
  static async rollbackInstallation(ctx: WorkflowContext, request: SkillInstallRequest) {
    // Call Backend API: DELETE /api/v1/skills/{name}/install
    // Or execute uninstall command directly
  }

  @DBOS.step()
  static async verifyBinary(ctx: WorkflowContext, skillName: string) {
    // Check if binary exists in PATH
    // Return { success: boolean, binaryPath?: string }
  }

  @DBOS.step()
  static async recordInstallationStart(ctx: WorkflowContext, request: SkillInstallRequest) {
    // Insert into skill_installation_history table
    // Columns: skill_name, agent_id, status='STARTED', started_at
  }

  @DBOS.step()
  static async recordInstallationSuccess(ctx: WorkflowContext, data: any) {
    // Update skill_installation_history table
    // Set status='COMPLETED', completed_at, binary_path
  }
}
```

**Benefits**:
- ✅ Atomic installation (all-or-nothing)
- ✅ Automatic rollback on failure
- ✅ Crash recovery (resume from last step)
- ✅ Audit trail (who installed what when)
- ✅ Retry on transient failures

### 2. SkillExecutionWorkflow ❌

**File**: `openclaw-gateway/src/workflows/skill-execution-workflow.ts` (DOES NOT EXIST)

**Required Functionality**:

```typescript
import { DBOS, WorkflowContext } from '@dbos-inc/dbos-sdk';

export interface SkillExecutionRequest {
  skillName: string;
  agentId: string;
  parameters: Record<string, any>;
  timeoutSeconds?: number;
}

export interface SkillExecutionResult {
  success: boolean;
  skillName: string;
  output?: string;
  error?: string;
  executionTimeMs: number;
}

export class SkillExecutionWorkflow {
  /**
   * Durable skill execution with retry
   *
   * Steps:
   * 1. Validate skill is installed and accessible
   * 2. Validate agent has permission to use skill
   * 3. Record execution start
   * 4. Execute skill command
   * 5. Capture output/errors
   * 6. Record execution result
   *
   * On crash: Resume and complete execution
   * On timeout: Retry with backoff
   */
  @DBOS.workflow()
  static async executeSkill(
    ctx: WorkflowContext,
    request: SkillExecutionRequest
  ): Promise<SkillExecutionResult> {
    const startTime = Date.now();

    // Step 1: Validate skill is installed
    const installed = await ctx.invoke(this.validateSkillInstalled, request.skillName);
    if (!installed.success) {
      return {
        success: false,
        skillName: request.skillName,
        error: `Skill '${request.skillName}' not installed`,
        executionTimeMs: Date.now() - startTime
      };
    }

    // Step 2: Check agent permissions
    const authorized = await ctx.invoke(this.checkAgentPermission, request);
    if (!authorized.success) {
      return {
        success: false,
        skillName: request.skillName,
        error: `Agent ${request.agentId} not authorized for skill '${request.skillName}'`,
        executionTimeMs: Date.now() - startTime
      };
    }

    // Step 3: Record execution start
    const executionId = await ctx.invoke(this.recordExecutionStart, request);

    // Step 4: Execute skill (with retry on transient failures)
    let result;
    try {
      result = await ctx.invoke(this.runSkillCommand, {
        skillName: request.skillName,
        parameters: request.parameters,
        timeoutSeconds: request.timeoutSeconds || 60
      });
    } catch (error) {
      // Record failure
      await ctx.invoke(this.recordExecutionFailure, {
        executionId,
        error: error.message
      });
      throw error;
    }

    // Step 5: Record success
    await ctx.invoke(this.recordExecutionSuccess, {
      executionId,
      output: result.output,
      executionTimeMs: Date.now() - startTime
    });

    return {
      success: true,
      skillName: request.skillName,
      output: result.output,
      executionTimeMs: Date.now() - startTime
    };
  }

  @DBOS.step()
  static async validateSkillInstalled(ctx: WorkflowContext, skillName: string) {
    // Call Backend: GET /api/v1/skills/{name}/installation-status
  }

  @DBOS.step()
  static async checkAgentPermission(ctx: WorkflowContext, request: SkillExecutionRequest) {
    // Call Backend: GET /api/v1/agents/{agentId}/skills/{skillName}
    // Check if agent has this skill enabled
  }

  @DBOS.step()
  static async runSkillCommand(ctx: WorkflowContext, params: any) {
    // Execute skill binary with parameters
    // Example: openclaw skills exec himalaya -- list
    // Return { output: string }
  }

  @DBOS.step()
  static async recordExecutionStart(ctx: WorkflowContext, request: SkillExecutionRequest) {
    // Insert into skill_execution_history table
    // Columns: execution_id, skill_name, agent_id, status='RUNNING', started_at, parameters
    // Return: execution_id (UUID)
  }

  @DBOS.step()
  static async recordExecutionSuccess(ctx: WorkflowContext, data: any) {
    // Update skill_execution_history
    // Set status='COMPLETED', completed_at, output, execution_time_ms
  }

  @DBOS.step()
  static async recordExecutionFailure(ctx: WorkflowContext, data: any) {
    // Update skill_execution_history
    // Set status='FAILED', completed_at, error
  }
}
```

**Benefits**:
- ✅ Crash recovery during skill execution
- ✅ Complete audit trail (who ran what when)
- ✅ Retry on transient failures
- ✅ Timeout handling
- ✅ Permission enforcement

### 3. Database Tables for Skill History ❌

**Required Tables** (do not exist):

```sql
-- Skill installation audit trail
CREATE TABLE skill_installation_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  skill_name VARCHAR(255) NOT NULL,
  agent_id UUID REFERENCES agent_swarms(id),
  status VARCHAR(50) NOT NULL, -- STARTED, COMPLETED, FAILED, ROLLED_BACK
  method VARCHAR(50), -- npm, brew, manual
  package_name VARCHAR(255),
  binary_path VARCHAR(500),
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  error_message TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_skill_install_history_skill ON skill_installation_history(skill_name);
CREATE INDEX idx_skill_install_history_agent ON skill_installation_history(agent_id);
CREATE INDEX idx_skill_install_history_status ON skill_installation_history(status);

-- Skill execution audit trail
CREATE TABLE skill_execution_history (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  execution_id UUID UNIQUE NOT NULL DEFAULT gen_random_uuid(),
  skill_name VARCHAR(255) NOT NULL,
  agent_id UUID REFERENCES agent_swarms(id),
  status VARCHAR(50) NOT NULL, -- RUNNING, COMPLETED, FAILED, TIMEOUT
  parameters JSONB,
  output TEXT,
  error_message TEXT,
  execution_time_ms INTEGER,
  started_at TIMESTAMPTZ NOT NULL,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_skill_exec_history_skill ON skill_execution_history(skill_name);
CREATE INDEX idx_skill_exec_history_agent ON skill_execution_history(agent_id);
CREATE INDEX idx_skill_exec_history_status ON skill_execution_history(status);
CREATE INDEX idx_skill_exec_history_started ON skill_execution_history(started_at DESC);
```

---

## Architecture Comparison

### Current Architecture (Non-Durable) ❌

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend UI                        │
│          POST /api/v1/skills/bear-notes/install         │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  Backend API (Port 8000)                │
│              skill_installation.py endpoint             │
│                  (Direct service call)                  │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│             SkillInstallationService                    │
│                                                         │
│  1. Run: npm install -g @instinctx_dev/skill           │
│  2. Verify binary exists                               │
│                                                         │
│  ❌ If crash after step 1: NPM package installed       │
│     but no record in DB - orphaned state               │
│  ❌ If binary check fails: NPM package remains         │
│     installed - no rollback                            │
└─────────────────────────────────────────────────────────┘
```

**Problems**:
- Crash between steps → inconsistent state
- No rollback on failure
- No audit trail

### Phase 4 Architecture (Durable) ✅

```
┌─────────────────────────────────────────────────────────┐
│                      Frontend UI                        │
│      POST /workflows/skill-installation (Gateway)       │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              DBOS Gateway (Port 18789)                  │
│          SkillInstallationWorkflow.installSkill()       │
│                                                         │
│  Step 1: validatePrerequisites() → DBOS persists       │
│  Step 2: recordInstallationStart() → DB write          │
│  Step 3: executeInstallCommand() → calls Backend       │
│  Step 4: verifyBinary() → check exists                │
│  Step 5: recordInstallationSuccess() → DB write        │
│                                                         │
│  ✅ If crash: Resume from last completed step          │
│  ✅ If failure: rollbackInstallation() auto-called     │
│  ✅ Complete audit trail in DB                         │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              Backend API (Step 3 only)                  │
│         POST /api/v1/skills/{name}/install              │
│           SkillInstallationService                      │
└─────────────────────────────────────────────────────────┘
```

**Benefits**:
- Exactly-once execution
- Crash recovery
- Automatic rollback
- Complete audit trail

---

## Implementation Plan

### Phase 4.1: Skill Installation Workflow (Week 1)

**Tasks**:
1. Create `skill-installation-workflow.ts` in Gateway
2. Create database migration for `skill_installation_history` table
3. Implement 5 workflow steps:
   - `validatePrerequisites()`
   - `executeInstallCommand()`
   - `rollbackInstallation()`
   - `verifyBinary()`
   - `recordInstallation*()` methods
4. Add Gateway endpoint: `POST /workflows/skill-installation`
5. Write integration tests (crash recovery, rollback)

**Testing**:
- Test normal install flow
- Test rollback on binary verification failure
- Test crash recovery (kill process mid-install, verify resume)
- Test idempotency (re-running same install returns cached result)

**Deliverable**: Atomic skill installation with rollback ✅

### Phase 4.2: Skill Execution Workflow (Week 1.5)

**Tasks**:
1. Create `skill-execution-workflow.ts` in Gateway
2. Create database migration for `skill_execution_history` table
3. Implement 6 workflow steps:
   - `validateSkillInstalled()`
   - `checkAgentPermission()`
   - `runSkillCommand()`
   - `recordExecution*()` methods
4. Add Gateway endpoint: `POST /workflows/skill-execution`
5. Wire into chat workflow (agents can invoke skills during conversation)
6. Write integration tests

**Testing**:
- Test skill execution with real skills (himalaya, mcporter)
- Test crash recovery during execution
- Test timeout handling
- Test permission enforcement
- Test audit trail completeness

**Deliverable**: Durable skill execution with audit trail ✅

### Phase 4.3: Frontend Integration (0.5 weeks)

**Tasks**:
1. Update Frontend to call Gateway skill workflows instead of Backend direct
2. Add skill execution history UI (show agent's skill usage)
3. Add installation status UI (show install progress/errors)

**Deliverable**: UI-triggered durable skill operations ✅

---

## Risks & Mitigations

### Risk 1: Skill Binaries Don't Support Programmatic Execution

**Risk**: Some skills may be interactive CLIs that don't support non-interactive execution

**Mitigation**:
- Start with well-tested skills (himalaya, mcporter have JSON output modes)
- Document skill compatibility requirements
- Graceful fallback for interactive skills

### Risk 2: Long-Running Skills May Timeout

**Risk**: Some skills (email sync, large file processing) may exceed DBOS step timeout

**Mitigation**:
- Use `@DBOS.step({ timeout: 300000 })` for 5-minute max
- Implement progress tracking for long operations
- Split into sub-workflows if needed

### Risk 3: Rollback May Fail

**Risk**: NPM uninstall may fail, leaving orphaned packages

**Mitigation**:
- Record rollback attempts in DB
- Manual cleanup workflow for failed rollbacks
- Alert operators when rollback fails

---

## Success Criteria

Phase 4 is complete when:

1. ✅ `SkillInstallationWorkflow` deployed and tested
   - Installation survives Gateway crashes
   - Rollback works on failures
   - Audit trail captured in DB

2. ✅ `SkillExecutionWorkflow` deployed and tested
   - Skill execution survives crashes
   - Permission checks enforced
   - Execution history queryable

3. ✅ Database tables created and migrated
   - `skill_installation_history`
   - `skill_execution_history`

4. ✅ Integration tests passing
   - 95%+ test coverage on workflows
   - Crash recovery tested
   - Rollback tested

5. ✅ Frontend using workflows
   - Install button triggers workflow
   - Execution requests go through workflow

---

## Timeline

**Total Estimate**: 2 weeks

- **Week 1**: SkillInstallationWorkflow + DB tables + tests
- **Week 1.5**: SkillExecutionWorkflow + tests
- **Week 2**: Frontend integration + end-to-end testing

**Dependencies**: None (Phase 2 Chat Workflow complete)

---

## Recommendation

**PROCEED WITH PHASE 4** ✅

**Why**:
- Skills infrastructure exists but lacks durability
- High-value improvement (crash recovery + audit trail)
- Clean architecture (follows Chat Workflow pattern)
- Reasonable effort (2 weeks)
- Enables agent autonomy (agents can reliably use skills)

**Next Step**: Create `skill-installation-workflow.ts` scaffolding and database migration
