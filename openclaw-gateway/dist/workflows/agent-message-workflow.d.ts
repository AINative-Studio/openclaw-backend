/**
 * Agent Message Routing Workflow
 *
 * DBOS durable workflow for routing agent messages with guaranteed delivery.
 * This workflow survives crashes and automatically recovers.
 */
interface AgentMessage {
    id: string;
    from: string;
    to: string;
    content: string;
    timestamp?: number;
    metadata?: Record<string, unknown>;
}
interface MessageDeliveryResult {
    messageId: string;
    status: 'delivered' | 'failed';
    deliveryAttempts: number;
    lastAttemptTime: number;
    response?: string;
}
/**
 * Main workflow class for agent message routing
 */
export declare class AgentMessageWorkflow {
    /**
     * Validate incoming message
     */
    static validateMessage(message: AgentMessage): Promise<boolean>;
    /**
     * Store message in database for durability
     * Note: Using knex raw queries as DBOS.query() doesn't exist
     */
    static storeMessage(message: AgentMessage): Promise<void>;
    /**
     * Route message to target agent
     */
    static routeMessage(message: AgentMessage): Promise<MessageDeliveryResult>;
    /**
     * Main workflow: orchestrates message routing with durability
     */
    static routeAgentMessage(message: AgentMessage): Promise<MessageDeliveryResult>;
    /**
     * Recovery workflow: automatically resumes interrupted workflows
     */
    static recoverWorkflow(workflowUuid: string): Promise<void>;
}
export {};
//# sourceMappingURL=agent-message-workflow.d.ts.map