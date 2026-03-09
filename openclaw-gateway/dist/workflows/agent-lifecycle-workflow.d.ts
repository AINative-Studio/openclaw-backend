/**
 * Agent Lifecycle Workflows
 *
 * DBOS durable workflows for agent provisioning, heartbeat tracking,
 * and pause/resume operations with automatic crash recovery.
 *
 * Refs #1217
 */
interface ProvisionRequest {
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
interface HeartbeatRequest {
    executionId: string;
    agentId: string;
    checklist: string[];
}
interface PauseResumeRequest {
    agentId: string;
    action: 'pause' | 'resume';
    preserveState?: boolean;
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
    static validateProvisionRequest(request: ProvisionRequest): Promise<boolean>;
    /**
     * Store agent metadata in database
     */
    static storeAgentMetadata(request: ProvisionRequest): Promise<void>;
    /**
     * Connect agent channels (external API calls allowed in steps)
     */
    static connectAgentChannels(request: ProvisionRequest): Promise<{
        openclawAgentId: string;
    }>;
    /**
     * Start heartbeat monitoring if enabled
     */
    static startHeartbeatMonitoring(request: ProvisionRequest): Promise<void>;
    /**
     * Update agent status
     */
    static updateAgentStatus(agentId: string, status: string, openclawAgentId?: string, error?: string): Promise<void>;
    /**
     * Main provisioning workflow
     *
     * Orchestrates agent provisioning with automatic retry and recovery.
     * If the process crashes mid-execution, DBOS will automatically resume
     * from the last completed step.
     */
    static provisionAgentWorkflow(request: ProvisionRequest): Promise<{
        agentId: string;
        status: string;
        sessionKey: string;
        openclawAgentId: string;
        timestamp: number;
    } | {
        agentId: string;
        status: string;
        sessionKey: string;
        error: string;
        timestamp: number;
    }>;
    /**
     * Create heartbeat execution record
     */
    static createHeartbeatExecution(request: HeartbeatRequest): Promise<void>;
    /**
     * Execute heartbeat tasks (external calls allowed)
     */
    static executeHeartbeatTasks(request: HeartbeatRequest): Promise<{
        tasksCompleted: number;
        checklist: string[];
        executionTime: number;
    }>;
    /**
     * Update heartbeat execution status
     */
    static updateHeartbeatExecution(executionId: string, status: string, result?: unknown, error?: string): Promise<void>;
    /**
     * Schedule next heartbeat
     */
    static scheduleNextHeartbeat(agentId: string, interval: string): Promise<void>;
    /**
     * Main heartbeat workflow
     *
     * Executes agent heartbeat tasks with durability.
     * Auto-recovers from crashes and ensures heartbeat continuity.
     */
    static heartbeatWorkflow(request: HeartbeatRequest): Promise<{
        executionId: string;
        agentId: string;
        status: string;
        duration: number;
        result: {
            tasksCompleted: number;
            checklist: string[];
            executionTime: number;
        };
        timestamp: number;
    } | {
        executionId: string;
        agentId: string;
        status: string;
        duration: number;
        error: string;
        timestamp: number;
    }>;
    /**
     * Capture agent state for pause
     */
    static captureAgentState(agentId: string): Promise<{
        configuration: any;
        heartbeatEnabled: any;
        heartbeatInterval: any;
        nextHeartbeatAt: any;
        previousStatus: any;
        capturedAt: string;
    }>;
    /**
     * Store agent state checkpoint
     */
    static storeStateCheckpoint(agentId: string, state: unknown): Promise<void>;
    /**
     * Update agent pause/resume status
     */
    static updatePauseResumeStatus(agentId: string, action: string, state?: any): Promise<void>;
    /**
     * Restore agent state from checkpoint
     */
    static restoreAgentState(agentId: string): Promise<any>;
    /**
     * Main pause/resume workflow
     *
     * Gracefully pauses or resumes agent with state preservation.
     * Uses DBOS checkpointing to ensure state consistency.
     */
    static pauseResumeWorkflow(request: PauseResumeRequest): Promise<{
        agentId: string;
        action: "pause" | "resume";
        status: string;
        state: {};
        timestamp: number;
    } | {
        agentId: string;
        action: "pause" | "resume";
        status: string;
        error: string;
        timestamp: number;
    }>;
    /**
     * Recover workflow from crash
     *
     * DBOS automatically handles recovery, but this can be used for
     * monitoring and manual intervention if needed.
     */
    static recoverWorkflow(workflowUuid: string): Promise<{
        recovered: boolean;
        status: any;
    }>;
}
export {};
//# sourceMappingURL=agent-lifecycle-workflow.d.ts.map