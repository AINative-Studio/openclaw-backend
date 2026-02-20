/**
 * Agent Lifecycle Workflows
 *
 * DBOS durable workflows for agent provisioning, heartbeat tracking,
 * and pause/resume operations with automatic crash recovery.
 *
 * Refs #1217
 */
import { WorkflowContext, StepContext, CommunicatorContext } from '@dbos-inc/dbos-sdk';
/**
 * Agent provisioning request
 */
export interface AgentProvisionRequest {
    agentId: string;
    name: string;
    persona?: string;
    model: string;
    userId: string;
    sessionKey: string;
    heartbeatEnabled?: boolean;
    heartbeatInterval?: string;
    heartbeatChecklist?: string[];
    configuration?: Record<string, unknown>;
}
/**
 * Agent provisioning result
 */
export interface AgentProvisionResult {
    agentId: string;
    status: 'provisioned' | 'failed';
    sessionKey: string;
    openclawAgentId?: string;
    error?: string;
    timestamp: number;
}
/**
 * Heartbeat execution request
 */
export interface HeartbeatRequest {
    agentId: string;
    sessionKey: string;
    checklist: string[];
    executionId: string;
}
/**
 * Heartbeat execution result
 */
export interface HeartbeatResult {
    executionId: string;
    agentId: string;
    status: 'completed' | 'failed' | 'skipped';
    duration: number;
    error?: string;
    result?: Record<string, unknown>;
    timestamp: number;
}
/**
 * Pause/resume request
 */
export interface PauseResumeRequest {
    agentId: string;
    action: 'pause' | 'resume';
    sessionKey: string;
    preserveState?: boolean;
}
/**
 * Pause/resume result
 */
export interface PauseResumeResult {
    agentId: string;
    action: 'pause' | 'resume';
    status: 'success' | 'failed';
    state?: Record<string, unknown>;
    error?: string;
    timestamp: number;
}
/**
 * Agent Lifecycle Workflow Class
 *
 * Implements durable workflows for agent lifecycle operations:
 * - Agent provisioning with automatic retry
 * - Heartbeat tracking with failure recovery
 * - Pause/resume with state preservation
 */
export declare class AgentLifecycleWorkflow {
    /**
     * Validate provisioning request
     */
    static validateProvisionRequest(ctx: StepContext, request: AgentProvisionRequest): Promise<boolean>;
    /**
     * Store agent metadata in database
     */
    static storeAgentMetadata(ctx: StepContext, request: AgentProvisionRequest): Promise<void>;
    /**
     * Connect agent channels (communicator for external API calls)
     */
    static connectAgentChannels(ctx: CommunicatorContext, request: AgentProvisionRequest): Promise<{
        openclawAgentId: string;
    }>;
    /**
     * Start heartbeat monitoring if enabled
     */
    static startHeartbeatMonitoring(ctx: StepContext, request: AgentProvisionRequest): Promise<void>;
    /**
     * Update agent status to running
     */
    static updateAgentStatus(ctx: StepContext, agentId: string, status: string, openclawAgentId?: string, error?: string): Promise<void>;
    /**
     * Main provisioning workflow
     *
     * Orchestrates agent provisioning with automatic retry and recovery.
     * If the process crashes mid-execution, DBOS will automatically resume
     * from the last completed step.
     */
    static provisionAgentWorkflow(ctx: WorkflowContext, request: AgentProvisionRequest): Promise<AgentProvisionResult>;
    /**
     * Create heartbeat execution record
     */
    static createHeartbeatExecution(ctx: StepContext, request: HeartbeatRequest): Promise<void>;
    /**
     * Execute heartbeat tasks (communicator for external calls)
     */
    static executeHeartbeatTasks(ctx: CommunicatorContext, request: HeartbeatRequest): Promise<Record<string, unknown>>;
    /**
     * Update heartbeat execution status
     */
    static updateHeartbeatExecution(ctx: StepContext, executionId: string, status: string, result?: Record<string, unknown>, error?: string): Promise<void>;
    /**
     * Schedule next heartbeat
     */
    static scheduleNextHeartbeat(ctx: StepContext, agentId: string, interval: string): Promise<void>;
    /**
     * Main heartbeat workflow
     *
     * Executes agent heartbeat tasks with durability.
     * Auto-recovers from crashes and ensures heartbeat continuity.
     */
    static heartbeatWorkflow(ctx: WorkflowContext, request: HeartbeatRequest): Promise<HeartbeatResult>;
    /**
     * Capture agent state for pause
     */
    static captureAgentState(ctx: StepContext, agentId: string): Promise<Record<string, unknown>>;
    /**
     * Store agent state checkpoint
     */
    static storeStateCheckpoint(ctx: StepContext, agentId: string, state: Record<string, unknown>): Promise<void>;
    /**
     * Update agent pause/resume status
     */
    static updatePauseResumeStatus(ctx: StepContext, agentId: string, action: 'pause' | 'resume', state?: Record<string, unknown>): Promise<void>;
    /**
     * Restore agent state from checkpoint
     */
    static restoreAgentState(ctx: StepContext, agentId: string): Promise<Record<string, unknown>>;
    /**
     * Main pause/resume workflow
     *
     * Gracefully pauses or resumes agent with state preservation.
     * Uses DBOS checkpointing to ensure state consistency.
     */
    static pauseResumeWorkflow(ctx: WorkflowContext, request: PauseResumeRequest): Promise<PauseResumeResult>;
    /**
     * Recover workflow from crash
     *
     * DBOS automatically handles recovery, but this can be used for
     * monitoring and manual intervention if needed.
     */
    static recoverWorkflow(ctx: WorkflowContext, workflowUuid: string): Promise<{
        recovered: boolean;
        status: string;
    }>;
}
//# sourceMappingURL=agent-lifecycle-workflow.d.ts.map