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
import { AgentLifecycleWorkflow } from './workflows/agent-lifecycle-workflow.js';

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

  // Root endpoint - Gateway info
  app.get('/', (req, res) => {
    res.json({
      service: 'OpenClaw Gateway',
      version: '1.0.0',
      description: 'DBOS-powered durable workflow gateway for agent orchestration',
      endpoints: {
        health: 'GET /health',
        workflowStatus: 'GET /workflows/:uuid',
        sendMessage: 'POST /messages',
        provisionAgent: 'POST /workflows/provision-agent',
        heartbeat: 'POST /workflows/heartbeat',
        pauseResume: 'POST /workflows/pause-resume',
        websocket: 'ws://localhost:' + PORT
      },
      status: 'running',
      timestamp: new Date().toISOString()
    });
  });

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
    } catch (error) {
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
        workflowUuid: (handle as any).getWorkflowUUID(),
        result,
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      res.status(500).json({ error: errorMessage });
    }
  });

  // Agent provisioning workflow endpoint
  app.post('/workflows/provision-agent', async (req, res) => {
    try {
      const request = {
        agentId: req.body.agentId,
        name: req.body.name,
        persona: req.body.persona,
        model: req.body.model,
        userId: req.body.userId,
        sessionKey: req.body.sessionKey,
        heartbeatEnabled: req.body.heartbeatEnabled,
        heartbeatInterval: req.body.heartbeatInterval,
        heartbeatChecklist: req.body.heartbeatChecklist,
        configuration: req.body.configuration
      };

      const handle = await DBOS.startWorkflow(AgentLifecycleWorkflow).provisionAgentWorkflow(request);
      const result = await handle.getResult();

      res.json({
        success: true,
        workflowUuid: (handle as any).getWorkflowUUID(),
        result
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      res.status(500).json({ error: errorMessage });
    }
  });

  // Heartbeat execution workflow endpoint
  app.post('/workflows/heartbeat', async (req, res) => {
    try {
      const request = {
        agentId: req.body.agentId,
        sessionKey: req.body.sessionKey,
        checklist: req.body.checklist,
        executionId: req.body.executionId
      };

      const handle = await DBOS.startWorkflow(AgentLifecycleWorkflow).heartbeatWorkflow(request);
      const result = await handle.getResult();

      res.json({
        success: true,
        workflowUuid: (handle as any).getWorkflowUUID(),
        result
      });
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Unknown error';
      res.status(500).json({ error: errorMessage });
    }
  });

  // Pause/Resume workflow endpoint
  app.post('/workflows/pause-resume', async (req, res) => {
    try {
      const request = {
        agentId: req.body.agentId,
        action: req.body.action,
        sessionKey: req.body.sessionKey,
        preserveState: req.body.preserveState
      };

      const handle = await DBOS.startWorkflow(AgentLifecycleWorkflow).pauseResumeWorkflow(request);
      const result = await handle.getResult();

      res.json({
        success: true,
        workflowUuid: (handle as any).getWorkflowUUID(),
        result
      });
    } catch (error) {
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
        const rawMessage = JSON.parse(data.toString());
        console.log('[Gateway] Received message:', JSON.stringify(rawMessage, null, 2));

        // Handle RPC protocol messages
        if (rawMessage.type === 'req') {
          // Handle connect handshake
          if (rawMessage.method === 'connect') {
            console.log('[Gateway] Processing connect handshake');
            ws.send(JSON.stringify({
              type: 'res',
              id: rawMessage.id,
              ok: true,
              payload: {
                protocol: 3,
                server: {
                  id: 'openclaw-gateway-dbos',
                  displayName: 'OpenClaw Gateway',
                  version: '1.0.0'
                }
              }
            }));
            return;
          }

          // Handle agent.send messages
          if (rawMessage.method === 'agent.send') {
            console.log('[Gateway] Processing RPC agent.send message');
            const message = {
              id: rawMessage.id,
              from: 'backend-api',
              to: rawMessage.params.sessionKey,
              content: rawMessage.params.message,
              timestamp: Date.now()
            };

            // Start durable workflow
            const handle = await DBOS.startWorkflow(AgentMessageWorkflow).routeAgentMessage(message);
            const result = await handle.getResult();

            // Send RPC response with Claude's actual response
            ws.send(JSON.stringify({
              type: 'res',
              id: rawMessage.id,
              ok: true,
              payload: {
                response: result.response || `Message delivered to ${message.to}`,
                message_id: result.messageId,
                status: result.status
              }
            }));
            return;
          }

          // Unknown RPC method
          ws.send(JSON.stringify({
            type: 'error',
            id: rawMessage.id,
            error: `Unknown method: ${rawMessage.method}`
          }));
          return;
        }

        // Handle direct message format (not RPC)
        const message = rawMessage;
        const handle = await DBOS.startWorkflow(AgentMessageWorkflow).routeAgentMessage(message);
        const result = await handle.getResult();

        ws.send(JSON.stringify({
          type: 'workflow_result',
          workflowUUID: (handle as any).getWorkflowUUID(),
          result,
        }));
      } catch (error) {
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
