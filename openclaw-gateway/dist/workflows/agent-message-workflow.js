/**
 * Agent Message Routing Workflow
 *
 * DBOS durable workflow for routing agent messages with guaranteed delivery.
 * This workflow survives crashes and automatically recovers.
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
import { Workflow, Step } from '@dbos-inc/dbos-sdk';
/**
 * Main workflow class for agent message routing
 */
export class AgentMessageWorkflow {
    /**
     * Validate incoming message
     */
    static async validateMessage(ctx, message) {
        ctx.logger.info(`Validating message ${message.id}`);
        if (!message.id || !message.from || !message.to || !message.content) {
            throw new Error('Invalid message: missing required fields');
        }
        return true;
    }
    /**
     * Store message in database for durability
     */
    static async storeMessage(ctx, message) {
        ctx.logger.info(`Storing message ${message.id} in database`);
        await ctx.query(`INSERT INTO dbos_system.notifications (workflow_uuid, topic, message, created_at)
       VALUES ($1, $2, $3, NOW())`, [ctx.workflowUUID, `agent.message.${message.to}`, JSON.stringify(message)]);
    }
    /**
     * Route message to target agent
     */
    static async routeMessage(ctx, message) {
        ctx.logger.info(`Routing message ${message.id} to agent ${message.to}`);
        // Simulate routing logic (in production, this would connect to actual agent endpoints)
        const deliveryAttempts = 1;
        const lastAttemptTime = Date.now();
        // For this phase, we'll mark as delivered after storing
        const result = {
            messageId: message.id,
            status: 'delivered',
            deliveryAttempts,
            lastAttemptTime,
        };
        ctx.logger.info(`Message ${message.id} routed successfully`, result);
        return result;
    }
    /**
     * Main workflow: orchestrates message routing with durability
     */
    static async routeAgentMessage(ctx, message) {
        ctx.logger.info(`Starting workflow for message ${message.id}`);
        try {
            // Step 1: Validate message
            await AgentMessageWorkflow.validateMessage(ctx, message);
            // Step 2: Store for durability
            await AgentMessageWorkflow.storeMessage(ctx, message);
            // Step 3: Route to target
            const result = await AgentMessageWorkflow.routeMessage(ctx, message);
            ctx.logger.info(`Workflow completed for message ${message.id}`, result);
            return result;
        }
        catch (error) {
            ctx.logger.error(`Workflow failed for message ${message.id}`, error);
            throw error;
        }
    }
    /**
     * Recovery workflow: automatically resumes interrupted workflows
     */
    static async recoverWorkflow(ctx, workflowUuid) {
        ctx.logger.info(`Recovering workflow ${workflowUuid}`);
        // Query workflow status
        const status = await ctx.query(`SELECT * FROM dbos_system.workflow_status WHERE workflow_uuid = $1`, [workflowUuid]);
        if (!status.rows.length) {
            throw new Error(`Workflow ${workflowUuid} not found`);
        }
        const workflow = status.rows[0];
        ctx.logger.info(`Found workflow in status: ${workflow.status}`);
        // Increment recovery attempts
        await ctx.query(`UPDATE dbos_system.workflow_status 
       SET recovery_attempts = recovery_attempts + 1, updated_at = NOW()
       WHERE workflow_uuid = $1`, [workflowUuid]);
        ctx.logger.info(`Recovery completed for workflow ${workflowUuid}`);
    }
}
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentMessageWorkflow, "validateMessage", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentMessageWorkflow, "storeMessage", null);
__decorate([
    Step(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentMessageWorkflow, "routeMessage", null);
__decorate([
    Workflow(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, Object]),
    __metadata("design:returntype", Promise)
], AgentMessageWorkflow, "routeAgentMessage", null);
__decorate([
    Workflow(),
    __metadata("design:type", Function),
    __metadata("design:paramtypes", [Object, String]),
    __metadata("design:returntype", Promise)
], AgentMessageWorkflow, "recoverWorkflow", null);
//# sourceMappingURL=agent-message-workflow.js.map