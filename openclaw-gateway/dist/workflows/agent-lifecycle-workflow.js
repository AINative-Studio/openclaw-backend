/**
 * Agent Lifecycle Workflows
 *
 * DBOS durable workflows for agent provisioning, heartbeat tracking,
 * and pause/resume operations with automatic crash recovery.
 *
 * Refs #1217
 */
var __decorate = (this && this.__decorate) || function (decorators, target, key, desc) {
    var c = arguments.length, r = c < 3 ? target : desc === null ? desc = Object.getOwnPropertyDescriptor(target, key) : desc, d;
    if (typeof Reflect === "object" && typeof Reflect.decorate === "function") r = Reflect.decorate(decorators, target, key, desc);
    else for (var i = decorators.length - 1; i >= 0; i--) if (d = decorators[i]) r = (c < 3 ? d(r) : c > 3 ? d(target, key, r) : d(target, key)) || r;
    return c > 3 && r && Object.defineProperty(target, key, r), r;
};
var __metadata = (this && this.__metadata) || function (k, v) {
    if (typeof Reflect === "object" && typeof Reflect.metadata === "function") return Reflect.metadata(k, v);
};
import { Workflow, Step, Communicator } from '@dbos-inc/dbos-sdk';
/**
 * Agent Lifecycle Workflow Class
 *
 * Implements durable workflows for agent lifecycle operations:
 * - Agent provisioning with automatic retry
 * - Heartbeat tracking with failure recovery
 * - Pause/resume with state preservation
 */
export class AgentLifecycleWorkflow {
    // ============================================================================
    // PROVISIONING WORKFLOW
    // ============================================================================
    /**
     * Validate provisioning request
     */
    static async validateProvisionRequest(ctx, request) {
        ctx.logger.info(`Validating provision request for agent ${request.agentId}`);
        if (!request.agentId || !request.name || !request.model || !request.userId || !request.sessionKey) {
            throw new Error('Invalid provision request: missing required fields');
        }
        if (!request.model.includes('/')) {
            throw new Error('Invalid model format: must be provider/model-name');
        }
        return true;
    }
    /**
     * Store agent metadata in database
     */
    static async storeAgentMetadata(ctx, request) {
        ctx.logger.info(`Storing agent metadata for ${request.agentId}`);
        await ctx.query(`INSERT INTO dbos_agents (
        agent_id, name, persona, model, user_id, session_key,
        heartbeat_enabled, heartbeat_interval, heartbeat_checklist,
        configuration, workflow_uuid, status, created_at
      ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, NOW())
      ON CONFLICT (agent_id) DO UPDATE SET
        workflow_uuid = $11,
        status = $12,
        updated_at = NOW()`, [
            request.agentId,
            request.name,
            request.persona,
            request.model,
            request.userId,
            request.sessionKey,
            request.heartbeatEnabled || false,
            request.heartbeatInterval,
            JSON.stringify(request.heartbeatChecklist || []),
            JSON.stringify(request.configuration || {}),
            ctx.workflowUUID,
            'provisioning'
        ]);
    }
    /**
     * Connect agent channels (communicator for external API calls)
     */
    static async connectAgentChannels(ctx, request) {
        ctx.logger.info(`Connecting channels for agent ${request.agentId}`);
        // Simulate channel connection (in production, this would call OpenClaw API)
        // This is a communicator, so it can make external HTTP calls
        const openclawAgentId = `openclaw_${request.agentId}_${Date.now()}`;
        // Simulate API call delay
        await new Promise(resolve => setTimeout(resolve, 100));
        return { openclawAgentId };
    }
    /**
     * Start heartbeat monitoring if enabled
     */
    static async startHeartbeatMonitoring(ctx, request) {
        if (!request.heartbeatEnabled) {
            ctx.logger.info(`Heartbeat not enabled for agent ${request.agentId}`);
            return;
        }
        ctx.logger.info(`Starting heartbeat monitoring for agent ${request.agentId}`);
        // Calculate next heartbeat time
        const intervalMap = {
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '30m': 30 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '2h': 2 * 60 * 60 * 1000,
        };
        const intervalMs = intervalMap[request.heartbeatInterval || '5m'] || 5 * 60 * 1000;
        const nextHeartbeat = new Date(Date.now() + intervalMs);
        await ctx.query(`UPDATE dbos_agents
       SET next_heartbeat_at = $1, updated_at = NOW()
       WHERE agent_id = $2`, [nextHeartbeat, request.agentId]);
    }
    /**
     * Update agent status to running
     */
    static async updateAgentStatus(ctx, agentId, status, openclawAgentId, error) {
        ctx.logger.info(`Updating agent ${agentId} status to ${status}`);
        await ctx.query(`UPDATE dbos_agents
       SET status = $1,
           openclaw_agent_id = COALESCE($2, openclaw_agent_id),
           error_message = $3,
           error_count = CASE WHEN $1 = 'failed' THEN error_count + 1 ELSE error_count END,
           last_error_at = CASE WHEN $1 = 'failed' THEN NOW() ELSE last_error_at END,
           provisioned_at = CASE WHEN $1 = 'running' THEN NOW() ELSE provisioned_at END,
           updated_at = NOW()
       WHERE agent_id = $4`, [status, openclawAgentId, error, agentId]);
    }
    /**
     * Main provisioning workflow
     *
     * Orchestrates agent provisioning with automatic retry and recovery.
     * If the process crashes mid-execution, DBOS will automatically resume
     * from the last completed step.
     */
    static async provisionAgentWorkflow(ctx, request) {
        ctx.logger.info(`Starting provision workflow for agent ${request.agentId}`);
        try {
            // Step 1: Validate request
            await AgentLifecycleWorkflow.validateProvisionRequest(ctx, request);
            // Step 2: Store metadata (idempotent)
            await AgentLifecycleWorkflow.storeAgentMetadata(ctx, request);
            // Step 3: Connect channels (external call, uses communicator)
            const channelResult = await AgentLifecycleWorkflow.connectAgentChannels(ctx, request);
            // Step 4: Start heartbeat if enabled
            await AgentLifecycleWorkflow.startHeartbeatMonitoring(ctx, request);
            // Step 5: Update status to running
            await AgentLifecycleWorkflow.updateAgentStatus(ctx, request.agentId, 'running', channelResult.openclawAgentId);
            const result = {
                agentId: request.agentId,
                status: 'provisioned',
                sessionKey: request.sessionKey,
                openclawAgentId: channelResult.openclawAgentId,
                timestamp: Date.now()
            };
            ctx.logger.info(`Provision workflow completed for agent ${request.agentId}`, result);
            return result;
        }
        catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            ctx.logger.error(`Provision workflow failed for agent ${request.agentId}`, error);
            // Update status to failed
            await AgentLifecycleWorkflow.updateAgentStatus(ctx, request.agentId, 'failed', undefined, errorMessage);
            const result = {
                agentId: request.agentId,
                status: 'failed',
                sessionKey: request.sessionKey,
                error: errorMessage,
                timestamp: Date.now()
            };
            return result;
        }
    }
    // ============================================================================
    // HEARTBEAT WORKFLOW
    // ============================================================================
    /**
     * Create heartbeat execution record
     */
    static async createHeartbeatExecution(ctx, request) {
        ctx.logger.info(`Creating heartbeat execution ${request.executionId}`);
        await ctx.query(`INSERT INTO dbos_heartbeat_executions (
        execution_id, agent_id, status, checklist_items,
        workflow_uuid, started_at, created_at
      ) VALUES ($1, $2, $3, $4, $5, NOW(), NOW())
      ON CONFLICT (execution_id) DO UPDATE SET
        workflow_uuid = $5,
        updated_at = NOW()`, [
            request.executionId,
            request.agentId,
            'running',
            JSON.stringify(request.checklist),
            ctx.workflowUUID
        ]);
    }
    /**
     * Execute heartbeat tasks (communicator for external calls)
     */
    static async executeHeartbeatTasks(ctx, request) {
        ctx.logger.info(`Executing heartbeat tasks for agent ${request.agentId}`);
        // Simulate heartbeat execution (in production, this would call OpenClaw)
        const result = {
            tasksCompleted: request.checklist.length,
            checklist: request.checklist,
            executionTime: Date.now()
        };
        // Simulate API call delay
        await new Promise(resolve => setTimeout(resolve, 100));
        return result;
    }
    /**
     * Update heartbeat execution status
     */
    static async updateHeartbeatExecution(ctx, executionId, status, result, error) {
        ctx.logger.info(`Updating heartbeat execution ${executionId} to ${status}`);
        await ctx.query(`UPDATE dbos_heartbeat_executions
       SET status = $1,
           result = $2,
           error_message = $3,
           completed_at = NOW(),
           duration_seconds = EXTRACT(EPOCH FROM (NOW() - started_at)),
           updated_at = NOW()
       WHERE execution_id = $4`, [status, JSON.stringify(result), error, executionId]);
    }
    /**
     * Schedule next heartbeat
     */
    static async scheduleNextHeartbeat(ctx, agentId, interval) {
        ctx.logger.info(`Scheduling next heartbeat for agent ${agentId}`);
        const intervalMap = {
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '30m': 30 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '2h': 2 * 60 * 60 * 1000,
        };
        const intervalMs = intervalMap[interval] || 5 * 60 * 1000;
        const nextHeartbeat = new Date(Date.now() + intervalMs);
        await ctx.query(`UPDATE dbos_agents
       SET last_heartbeat_at = NOW(),
           next_heartbeat_at = $1,
           updated_at = NOW()
       WHERE agent_id = $2`, [nextHeartbeat, agentId]);
    }
    /**
     * Main heartbeat workflow
     *
     * Executes agent heartbeat tasks with durability.
     * Auto-recovers from crashes and ensures heartbeat continuity.
     */
    static async heartbeatWorkflow(ctx, request) {
        ctx.logger.info(`Starting heartbeat workflow for agent ${request.agentId}`);
        const startTime = Date.now();
        try {
            // Step 1: Create execution record
            await AgentLifecycleWorkflow.createHeartbeatExecution(ctx, request);
            // Step 2: Execute heartbeat tasks
            const result = await AgentLifecycleWorkflow.executeHeartbeatTasks(ctx, request);
            // Step 3: Update execution status
            await AgentLifecycleWorkflow.updateHeartbeatExecution(ctx, request.executionId, 'completed', result);
            // Step 4: Schedule next heartbeat
            // Get agent's heartbeat interval from database
            const agentQuery = await ctx.query(`SELECT heartbeat_interval FROM dbos_agents WHERE agent_id = $1`, [request.agentId]);
            if (agentQuery.rows.length > 0) {
                const interval = agentQuery.rows[0].heartbeat_interval || '5m';
                await AgentLifecycleWorkflow.scheduleNextHeartbeat(ctx, request.agentId, interval);
            }
            const heartbeatResult = {
                executionId: request.executionId,
                agentId: request.agentId,
                status: 'completed',
                duration: Date.now() - startTime,
                result,
                timestamp: Date.now()
            };
            ctx.logger.info(`Heartbeat workflow completed for agent ${request.agentId}`, heartbeatResult);
            return heartbeatResult;
        }
        catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            ctx.logger.error(`Heartbeat workflow failed for agent ${request.agentId}`, error);
            // Update execution to failed
            await AgentLifecycleWorkflow.updateHeartbeatExecution(ctx, request.executionId, 'failed', undefined, errorMessage);
            // Update agent error tracking
            await ctx.query(`UPDATE dbos_agents
         SET error_count = error_count + 1,
             last_error_at = NOW(),
             updated_at = NOW()
         WHERE agent_id = $1`, [request.agentId]);
            const heartbeatResult = {
                executionId: request.executionId,
                agentId: request.agentId,
                status: 'failed',
                duration: Date.now() - startTime,
                error: errorMessage,
                timestamp: Date.now()
            };
            return heartbeatResult;
        }
    }
    // ============================================================================
    // PAUSE/RESUME WORKFLOW
    // ============================================================================
    /**
     * Capture agent state for pause
     */
    static async captureAgentState(ctx, agentId) {
        ctx.logger.info(`Capturing state for agent ${agentId}`);
        // Query current agent state
        const result = await ctx.query(`SELECT configuration, heartbeat_enabled, heartbeat_interval,
              next_heartbeat_at, status
       FROM dbos_agents
       WHERE agent_id = $1`, [agentId]);
        if (result.rows.length === 0) {
            throw new Error(`Agent not found: ${agentId}`);
        }
        const agent = result.rows[0];
        return {
            configuration: agent.configuration,
            heartbeatEnabled: agent.heartbeat_enabled,
            heartbeatInterval: agent.heartbeat_interval,
            nextHeartbeatAt: agent.next_heartbeat_at,
            previousStatus: agent.status,
            capturedAt: new Date().toISOString()
        };
    }
    /**
     * Store agent state checkpoint
     */
    static async storeStateCheckpoint(ctx, agentId, state) {
        ctx.logger.info(`Storing state checkpoint for agent ${agentId}`);
        await ctx.query(`INSERT INTO dbos_agent_checkpoints (
        agent_id, state, workflow_uuid, created_at
      ) VALUES ($1, $2, $3, NOW())`, [agentId, JSON.stringify(state), ctx.workflowUUID]);
    }
    /**
     * Update agent pause/resume status
     */
    static async updatePauseResumeStatus(ctx, agentId, action, state) {
        ctx.logger.info(`Updating agent ${agentId} to ${action}`);
        if (action === 'pause') {
            await ctx.query(`UPDATE dbos_agents
         SET status = 'paused',
             paused_at = NOW(),
             updated_at = NOW()
         WHERE agent_id = $1`, [agentId]);
        }
        else {
            // Resume: restore previous state if available
            const nextHeartbeat = state?.nextHeartbeatAt
                ? new Date(state.nextHeartbeatAt)
                : new Date(Date.now() + 5 * 60 * 1000);
            await ctx.query(`UPDATE dbos_agents
         SET status = 'running',
             paused_at = NULL,
             next_heartbeat_at = $1,
             updated_at = NOW()
         WHERE agent_id = $2`, [nextHeartbeat, agentId]);
        }
    }
    /**
     * Restore agent state from checkpoint
     */
    static async restoreAgentState(ctx, agentId) {
        ctx.logger.info(`Restoring state for agent ${agentId}`);
        // Get latest checkpoint
        const result = await ctx.query(`SELECT state FROM dbos_agent_checkpoints
       WHERE agent_id = $1
       ORDER BY created_at DESC
       LIMIT 1`, [agentId]);
        if (result.rows.length === 0) {
            ctx.logger.warn(`No checkpoint found for agent ${agentId}`);
            return {};
        }
        return result.rows[0].state;
    }
    /**
     * Main pause/resume workflow
     *
     * Gracefully pauses or resumes agent with state preservation.
     * Uses DBOS checkpointing to ensure state consistency.
     */
    static async pauseResumeWorkflow(ctx, request) {
        ctx.logger.info(`Starting ${request.action} workflow for agent ${request.agentId}`);
        try {
            let state = {};
            if (request.action === 'pause') {
                // Pause: capture and store state
                if (request.preserveState) {
                    state = await AgentLifecycleWorkflow.captureAgentState(ctx, request.agentId);
                    await AgentLifecycleWorkflow.storeStateCheckpoint(ctx, request.agentId, state);
                }
            }
            else {
                // Resume: restore state
                state = await AgentLifecycleWorkflow.restoreAgentState(ctx, request.agentId);
            }
            // Update agent status
            await AgentLifecycleWorkflow.updatePauseResumeStatus(ctx, request.agentId, request.action, state);
            const result = {
                agentId: request.agentId,
                action: request.action,
                status: 'success',
                state: request.preserveState ? state : undefined,
                timestamp: Date.now()
            };
            ctx.logger.info(`${request.action} workflow completed for agent ${request.agentId}`, result);
            return result;
        }
        catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            ctx.logger.error(`${request.action} workflow failed for agent ${request.agentId}`, error);
            const result = {
                agentId: request.agentId,
                action: request.action,
                status: 'failed',
                error: errorMessage,
                timestamp: Date.now()
            };
            return result;
        }
    }
    // ============================================================================
    // WORKFLOW RECOVERY
    // ============================================================================
    /**
     * Recover workflow from crash
     *
     * DBOS automatically handles recovery, but this can be used for
     * monitoring and manual intervention if needed.
     */
    static async recoverWorkflow(ctx, workflowUuid) {
        ctx.logger.info(`Recovering workflow ${workflowUuid}`);
        // Query workflow status from DBOS system tables
        const status = await ctx.query(`SELECT status, name FROM dbos_system.workflow_status
       WHERE workflow_uuid = $1`, [workflowUuid]);
        if (!status.rows.length) {
            return { recovered: false, status: 'not_found' };
        }
        const workflow = status.rows[0];
        ctx.logger.info(`Found workflow in status: ${workflow.status}`);
        // Update recovery tracking
        await ctx.query(`UPDATE dbos_system.workflow_status
       SET recovery_attempts = COALESCE(recovery_attempts, 0) + 1,
           updated_at = NOW()
       WHERE workflow_uuid = $1`, [workflowUuid]);
        return {
            recovered: true,
            status: workflow.status
        };
    }
}
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "validateProvisionRequest", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "storeAgentMetadata", null);
__decorate([
    Communicator(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "connectAgentChannels", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "startHeartbeatMonitoring", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String, String, String, String]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "updateAgentStatus", null);
__decorate([
    Workflow(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "provisionAgentWorkflow", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "createHeartbeatExecution", null);
__decorate([
    Communicator(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "executeHeartbeatTasks", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String, String, Object, String]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "updateHeartbeatExecution", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String, String]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "scheduleNextHeartbeat", null);
__decorate([
    Workflow(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "heartbeatWorkflow", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "captureAgentState", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "storeStateCheckpoint", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String, String, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "updatePauseResumeStatus", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "restoreAgentState", null);
__decorate([
    Workflow(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "pauseResumeWorkflow", null);
__decorate([
    Workflow(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String]),
    __metadata("design:returntype", Promise)
], AgentLifecycleWorkflow, "recoverWorkflow", null);
//# sourceMappingURL=agent-lifecycle-workflow.js.map