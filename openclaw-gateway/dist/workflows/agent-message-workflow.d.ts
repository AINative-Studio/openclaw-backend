/**
 * Agent Message Routing Workflow
 *
 * DBOS durable workflow for routing agent messages with guaranteed delivery.
 * This workflow survives crashes and automatically recovers.
 */
import { WorkflowContext, StepContext } from '@dbos-inc/dbos-sdk';
export interface AgentMessage {
    id: string;
    from: string;
    to: string;
    content: string;
    timestamp: number;
    metadata?: Record<string, unknown>;
}
export interface MessageRoutingResult {
    messageId: string;
    status: 'delivered' | 'pending' | 'failed';
    deliveryAttempts: number;
    lastAttemptTime: number;
}
/**
 * Main workflow class for agent message routing
 */
export declare class AgentMessageWorkflow {
    /**
     * Validate incoming message
     */
    static validateMessage(ctx: StepContext, message: AgentMessage): Promise<boolean>;
    /**
     * Store message in database for durability
     */
    static storeMessage(ctx: StepContext, message: AgentMessage): Promise<void>;
    /**
     * Route message to target agent
     */
    static routeMessage(ctx: StepContext, message: AgentMessage): Promise<MessageRoutingResult>;
    /**
     * Main workflow: orchestrates message routing with durability
     */
    static routeAgentMessage(ctx: WorkflowContext, message: AgentMessage): Promise<MessageRoutingResult>;
    /**
     * Recovery workflow: automatically resumes interrupted workflows
     */
    static recoverWorkflow(ctx: WorkflowContext, workflowUuid: string): Promise<void>;
}
//# sourceMappingURL=agent-message-workflow.d.ts.map