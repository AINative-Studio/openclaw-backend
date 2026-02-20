/**
 * OpenClaw Gateway Server
 *
 * WebSocket gateway with DBOS durable workflows for agent orchestration.
 * Provides guaranteed message delivery and automatic recovery from crashes.
 */
import { DBOS } from '@dbos-inc/dbos-sdk';
import express from 'express';
import { WebSocketServer } from 'ws';
import dotenv from 'dotenv';
import { AgentMessageWorkflow } from './workflows/agent-message-workflow.js';
dotenv.config();
const PORT = parseInt(process.env.PORT || '8080');
/**
 * Initialize OpenClaw Gateway
 */
async function startGateway() {
    console.log('Starting OpenClaw Gateway with DBOS...');
    // Initialize DBOS
    await DBOS.launch();
    console.log('✓ DBOS initialized');
    // Create Express app
    const app = express();
    app.use(express.json());
    // Health check endpoint
    app.get('/health', (req, res) => {
        res.json({
            status: 'healthy',
            service: 'openclaw-gateway',
            dbos: 'connected',
            timestamp: new Date().toISOString(),
        });
    });
    // Workflow status endpoint
    app.get('/workflows/:uuid', async (req, res) => {
        try {
            const { uuid } = req.params;
            const handle = await DBOS.getWorkflowStatus(uuid);
            res.json({
                workflowUuid: uuid,
                status: handle?.status || 'not_found',
            });
        }
        catch (error) {
            res.status(500).json({ error: 'Failed to get workflow status' });
        }
    });
    // Start workflow endpoint (for testing)
    app.post('/messages', async (req, res) => {
        try {
            const msgId = req.body.id || 'msg_' + String(Date.now());
            const message = {
                id: msgId,
                from: req.body.from,
                to: req.body.to,
                content: req.body.content,
                timestamp: Date.now(),
                metadata: req.body.metadata,
            };
            const handle = await DBOS.startWorkflow(AgentMessageWorkflow).routeAgentMessage(message);
            const result = await handle.getResult();
            res.json({
                success: true,
                workflowUuid: handle.getWorkflowUUID(),
                result,
            });
        }
        catch (error) {
            const errorMessage = error instanceof Error ? error.message : 'Unknown error';
            res.status(500).json({ error: errorMessage });
        }
    });
    // Start HTTP server
    const server = app.listen(PORT, () => {
        console.log('✓ OpenClaw Gateway listening on port ' + PORT);
    });
    // Create WebSocket server
    const wss = new WebSocketServer({ server });
    wss.on('connection', (ws) => {
        console.log('WebSocket client connected');
        ws.on('message', async (data) => {
            try {
                const message = JSON.parse(data.toString());
                // Start durable workflow
                const handle = await DBOS.startWorkflow(AgentMessageWorkflow).routeAgentMessage(message);
                const result = await handle.getResult();
                ws.send(JSON.stringify({
                    type: 'workflow_result',
                    workflowUuid: handle.getWorkflowUUID(),
                    result,
                }));
            }
            catch (error) {
                const errorMessage = error instanceof Error ? error.message : 'Unknown error';
                ws.send(JSON.stringify({
                    type: 'error',
                    error: errorMessage,
                }));
            }
        });
        ws.on('close', () => {
            console.log('WebSocket client disconnected');
        });
    });
    console.log('✓ WebSocket server initialized');
    console.log('\n🚀 OpenClaw Gateway is ready!');
    console.log('   HTTP: http://localhost:' + PORT);
    console.log('   WebSocket: ws://localhost:' + PORT);
    // Graceful shutdown
    process.on('SIGTERM', async () => {
        console.log('\nShutting down gracefully...');
        server.close();
        await DBOS.shutdown();
        process.exit(0);
    });
}
// Start the gateway
startGateway().catch((error) => {
    console.error('Failed to start gateway:', error);
    process.exit(1);
});
//# sourceMappingURL=server.js.map