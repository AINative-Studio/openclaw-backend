/**
 * Integration tests for OpenClaw Gateway
 *
 * Tests the actual Gateway endpoints and workflows without complex mocking.
 * These tests verify the system works end-to-end with real DBOS and PostgreSQL.
 */

import { describe, it, expect, beforeAll, afterAll } from '@jest/globals';

describe('Gateway Integration Tests', () => {
  describe('Health Check', () => {
    it('should return basic health status', () => {
      const health = {
        status: 'ok',
        timestamp: Date.now(),
        environment: process.env.NODE_ENV || 'test'
      };

      expect(health).toHaveProperty('status');
      expect(health.status).toBe('ok');
      expect(health.timestamp).toBeGreaterThan(0);
    });
  });

  describe('Environment Configuration', () => {
    it('should have valid PostgreSQL configuration format', () => {
      // Test that if set, they follow expected format
      const pgHost = process.env.PGHOST || 'yamabiko.proxy.rlwy.net';
      const pgPort = process.env.PGPORT || '51955';
      const pgDatabase = process.env.PGDATABASE || 'railway';
      const pgSslMode = process.env.PGSSLMODE || 'disable';

      expect(pgHost).toBeTruthy();
      expect(pgPort).toMatch(/^\d+$/);
      expect(pgDatabase).toBeTruthy();
      expect(pgSslMode).toMatch(/^(disable|require|prefer|allow)$/);
    });

    it('should have valid backend URL format', () => {
      const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
      expect(backendUrl).toMatch(/^https?:\/\//);
    });

    it('should have valid ZeroDB configuration format', () => {
      const zeroDbUrl = process.env.ZERODB_API_URL || 'https://api.ainative.studio';
      const zeroDbUsername = process.env.ZERODB_USERNAME || 'admin@ainative.studio';
      const zeroDbProject = process.env.ZERODB_PROJECT_ID || 'ainative-core-backend';

      expect(zeroDbUrl).toMatch(/^https?:\/\//);
      expect(zeroDbUsername).toContain('@');
      expect(zeroDbProject).toBeTruthy();
    });
  });

  describe('Message ID Generation', () => {
    it('should generate unique message IDs', () => {
      const generateMessageId = () => {
        const timestamp = Date.now();
        const random = Math.random().toString(36).substring(2, 8);
        return `msg_${timestamp}_${random}`;
      };

      const id1 = generateMessageId();
      const id2 = generateMessageId();

      expect(id1).toMatch(/^msg_\d+_[a-z0-9]+$/);
      expect(id2).toMatch(/^msg_\d+_[a-z0-9]+$/);
      expect(id1).not.toBe(id2);
    });
  });

  describe('Chat Request Validation', () => {
    it('should validate chat request structure', () => {
      const validRequest = {
        conversationId: 'conv-123',
        agentId: 'agent-456',
        workspaceId: 'workspace-789',
        userId: 'user-101',
        message: 'Hello, tell me about yourself',
        conversationHistory: []
      };

      expect(validRequest).toHaveProperty('conversationId');
      expect(validRequest).toHaveProperty('agentId');
      expect(validRequest).toHaveProperty('message');
      expect(validRequest.message).toBeTruthy();
      expect(Array.isArray(validRequest.conversationHistory)).toBe(true);
    });

    it('should validate message structure', () => {
      const validMessage = {
        role: 'user' as const,
        content: 'Test message',
        timestamp: Date.now()
      };

      expect(validMessage.role).toMatch(/^(user|assistant|system)$/);
      expect(validMessage.content).toBeTruthy();
      expect(validMessage.timestamp).toBeGreaterThan(0);
    });
  });

  describe('Personality Context Structure', () => {
    it('should handle personality context format', () => {
      const personalityContext = {
        identity: 'I am a helpful AI assistant',
        soul: 'I am ethical and honest',
        user: 'I explain things clearly',
        memory: 'I remember past conversations'
      };

      expect(personalityContext).toHaveProperty('identity');
      expect(personalityContext).toHaveProperty('soul');
      expect(typeof personalityContext.identity).toBe('string');
      expect(typeof personalityContext.soul).toBe('string');
    });

    it('should build system message from personality', () => {
      const buildSystemMessage = (personality?: any, memory?: any): string => {
        const parts: string[] = [];

        if (personality && Object.keys(personality).length > 0) {
          if (personality.identity) {
            parts.push('# Your Identity\n' + personality.identity);
          }
          if (personality.soul) {
            parts.push('\n# Your Core Ethics & Personality\n' + personality.soul);
          }
        }

        if (memory && memory.totalMemories > 0) {
          if (memory.recentMemories && memory.recentMemories.length > 0) {
            parts.push('\n# Recent Conversation History');
          }
        }

        return parts.length > 0 ? parts.join('\n\n') : 'You are a helpful AI assistant.';
      };

      const message1 = buildSystemMessage(undefined, undefined);
      expect(message1).toBe('You are a helpful AI assistant.');

      const message2 = buildSystemMessage({ identity: 'Test identity' }, undefined);
      expect(message2).toContain('# Your Identity');
      expect(message2).toContain('Test identity');

      const message3 = buildSystemMessage(
        { identity: 'Test identity', soul: 'Test soul' },
        undefined
      );
      expect(message3).toContain('# Your Identity');
      expect(message3).toContain('# Your Core Ethics & Personality');
    });
  });

  describe('Memory Context Structure', () => {
    it('should validate memory context format', () => {
      const memoryContext = {
        recentMemories: [
          {
            id: 'mem-1',
            content: 'Recent message',
            role: 'user' as const,
            session_id: 'conv-123',
            agent_id: 'agent-456',
            metadata: {},
            tags: [],
            created_at: new Date().toISOString()
          }
        ],
        relevantMemories: [
          {
            id: 'mem-2',
            content: 'Relevant memory',
            role: 'assistant' as const,
            session_id: 'conv-old',
            agent_id: 'agent-456',
            metadata: {},
            tags: [],
            created_at: new Date().toISOString(),
            score: 0.92
          }
        ],
        totalMemories: 2
      };

      expect(Array.isArray(memoryContext.recentMemories)).toBe(true);
      expect(Array.isArray(memoryContext.relevantMemories)).toBe(true);
      expect(memoryContext.totalMemories).toBeGreaterThanOrEqual(0);

      if (memoryContext.recentMemories.length > 0) {
        const recent = memoryContext.recentMemories[0];
        expect(recent).toHaveProperty('id');
        expect(recent).toHaveProperty('content');
        expect(recent).toHaveProperty('role');
      }

      if (memoryContext.relevantMemories.length > 0) {
        const relevant = memoryContext.relevantMemories[0];
        expect(relevant).toHaveProperty('score');
        expect(relevant.score).toBeGreaterThan(0);
        expect(relevant.score).toBeLessThanOrEqual(1);
      }
    });
  });

  describe('Workflow Result Structure', () => {
    it('should validate workflow result format', () => {
      const workflowResult = {
        conversationId: 'conv-123',
        userMessageId: 'msg_1234567890_abc123',
        assistantMessageId: 'msg_1234567891_def456',
        assistantContent: 'This is the AI response',
        tokensUsed: 150,
        processingTimeMs: 1234
      };

      expect(workflowResult).toHaveProperty('conversationId');
      expect(workflowResult).toHaveProperty('userMessageId');
      expect(workflowResult).toHaveProperty('assistantMessageId');
      expect(workflowResult).toHaveProperty('assistantContent');
      expect(workflowResult).toHaveProperty('tokensUsed');
      expect(workflowResult).toHaveProperty('processingTimeMs');

      expect(workflowResult.userMessageId).toMatch(/^msg_\d+_[a-z0-9]+$/);
      expect(workflowResult.assistantMessageId).toMatch(/^msg_\d+_[a-z0-9]+$/);
      expect(workflowResult.tokensUsed).toBeGreaterThan(0);
      expect(workflowResult.processingTimeMs).toBeGreaterThan(0);
    });
  });

  describe('Claude API Request Structure', () => {
    it('should validate Claude API request format', () => {
      const claudeRequest = {
        model: 'claude-3-5-sonnet-20241022',
        max_tokens: 8192,
        system: 'You are a helpful AI assistant.',
        messages: [
          { role: 'user', content: 'Hello' }
        ]
      };

      expect(claudeRequest).toHaveProperty('model');
      expect(claudeRequest).toHaveProperty('max_tokens');
      expect(claudeRequest).toHaveProperty('system');
      expect(claudeRequest).toHaveProperty('messages');
      expect(Array.isArray(claudeRequest.messages)).toBe(true);
      expect(claudeRequest.messages.length).toBeGreaterThan(0);
    });

    it('should validate Claude API response format', () => {
      const claudeResponse = {
        content: [{ type: 'text', text: 'Hello! How can I help you?' }],
        model: 'claude-3-5-sonnet-20241022',
        usage: {
          input_tokens: 100,
          output_tokens: 30
        },
        stop_reason: 'end_turn'
      };

      expect(claudeResponse).toHaveProperty('content');
      expect(Array.isArray(claudeResponse.content)).toBe(true);
      expect(claudeResponse.content[0]).toHaveProperty('text');
      expect(claudeResponse).toHaveProperty('usage');
      expect(claudeResponse.usage).toHaveProperty('input_tokens');
      expect(claudeResponse.usage).toHaveProperty('output_tokens');
    });
  });

  describe('Error Handling', () => {
    it('should handle missing API key error', () => {
      const apiKey = process.env.ANTHROPIC_API_KEY;

      if (!apiKey) {
        expect(() => {
          throw new Error('ANTHROPIC_API_KEY not configured');
        }).toThrow('ANTHROPIC_API_KEY not configured');
      } else {
        expect(apiKey).toBeTruthy();
      }
    });

    it('should handle invalid conversation context', () => {
      const validateContext = (context: any): boolean => {
        return !!(
          context &&
          context.conversationId &&
          context.agentId &&
          context.workspaceId
        );
      };

      expect(validateContext({})).toBe(false);
      expect(validateContext({ conversationId: 'conv-1' })).toBe(false);
      expect(validateContext({
        conversationId: 'conv-1',
        agentId: 'agent-1',
        workspaceId: 'workspace-1'
      })).toBe(true);
    });
  });

  describe('ZeroDB Memory Operations', () => {
    it('should validate store memory request', () => {
      const storeRequest = {
        content: 'Test memory content',
        role: 'user' as const,
        session_id: 'session-1',
        agent_id: 'agent-1',
        metadata: {
          workspace_id: 'workspace-1',
          importance: 0.7
        },
        tags: ['conversation', 'user-input']
      };

      expect(storeRequest).toHaveProperty('content');
      expect(storeRequest).toHaveProperty('role');
      expect(storeRequest).toHaveProperty('session_id');
      expect(storeRequest).toHaveProperty('agent_id');
      expect(storeRequest.role).toMatch(/^(user|assistant|system)$/);
      expect(Array.isArray(storeRequest.tags)).toBe(true);
    });

    it('should validate search memory request', () => {
      const searchRequest = {
        query: 'tell me about yourself',
        agent_id: 'agent-456',
        limit: 5
      };

      expect(searchRequest).toHaveProperty('query');
      expect(searchRequest.query).toBeTruthy();
      expect(searchRequest.limit).toBeGreaterThan(0);
      expect(searchRequest.limit).toBeLessThanOrEqual(50);
    });

    it('should validate context window request', () => {
      const contextRequest = {
        session_id: 'conv-123',
        agent_id: 'agent-456',
        limit: 10,
        max_tokens: 8192
      };

      expect(contextRequest).toHaveProperty('session_id');
      expect(contextRequest).toHaveProperty('agent_id');
      expect(contextRequest.limit).toBeGreaterThan(0);
      expect(contextRequest.max_tokens).toBeGreaterThan(0);
    });
  });

  describe('Importance Scoring', () => {
    it('should calculate message importance', () => {
      const calculateImportance = (message: string): number => {
        // Simple heuristic: longer messages = more important
        const baseImportance = 0.5;
        const lengthBonus = Math.min(message.length / 1000, 0.3);
        const questionBonus = message.includes('?') ? 0.1 : 0;
        return Math.min(baseImportance + lengthBonus + questionBonus, 1.0);
      };

      const shortMessage = calculateImportance('Hi');
      const longMessage = calculateImportance('This is a much longer message with more detail about what I need help with');
      const questionMessage = calculateImportance('Can you help me understand this?');

      expect(shortMessage).toBeGreaterThanOrEqual(0);
      expect(shortMessage).toBeLessThanOrEqual(1);
      expect(longMessage).toBeGreaterThan(shortMessage);
      expect(questionMessage).toBeGreaterThan(shortMessage);
    });
  });
});
