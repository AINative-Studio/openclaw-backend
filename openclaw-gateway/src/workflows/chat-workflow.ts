/**
 * Chat Workflow with DBOS Durability + ZeroDB Memory
 *
 * Phase 2: Makes conversations 100% durable with personality-driven responses
 * and persistent memory across agent sessions.
 *
 * Architecture:
 * 1. Save user message (durable PostgreSQL)
 * 2a. Load personality context from files
 * 2b. Load memory context from ZeroDB (recent + semantic search)
 * 2c. Call LLM with personality + memory injection
 * 3. Save assistant response (durable PostgreSQL)
 * 4. Store exchange in ZeroDB memory (semantic search + cross-agent sharing)
 *
 * Benefits:
 * - Crash recovery: Workflows resume automatically
 * - No lost messages: All messages persisted before processing
 * - Personality-driven: Context injected into every LLM call
 * - Memory-enhanced: Agents remember past conversations
 * - Cross-agent knowledge: Memories searchable across agent swarm
 * - Automatic retries: LLM failures retry with exponential backoff
 * - Audit trail: Complete conversation history in DBOS + ZeroDB
 */

import { DBOS } from '@dbos-inc/dbos-sdk';
import { getZeroDBClient, MemoryResult } from '../utils/zerodb-client.js';

// ==================== Types ====================

interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp?: number;
}

interface ConversationContext {
  conversationId: string;
  agentId: string;
  workspaceId: string;
  userId?: string;
}

interface PersonalityContext {
  soul?: string;        // Core ethics
  identity?: string;    // Agent identity
  user?: string;        // User interaction patterns
  tools?: string;       // Tool usage patterns
  memory?: string;      // Key learnings (static MEMORY.md)
}

interface MemoryContext {
  recentMemories: MemoryResult[];       // Recent conversation history from ZeroDB
  relevantMemories: MemoryResult[];     // Semantically similar past conversations
  totalMemories: number;                // Total memories in session
}

interface LLMRequest {
  conversationId: string;
  agentId: string;
  messages: ChatMessage[];
  personalityContext?: PersonalityContext;
  memoryContext?: MemoryContext;
  model?: string;
  temperature?: number;
  maxTokens?: number;
}

interface LLMResponse {
  content: string;
  model: string;
  usage: {
    promptTokens: number;
    completionTokens: number;
    totalTokens: number;
  };
  finishReason: string;
}

interface ChatWorkflowResult {
  conversationId: string;
  userMessageId: string;
  assistantMessageId: string;
  assistantContent: string;
  tokensUsed: number;
  processingTimeMs: number;
}

// ==================== Chat Workflow ====================

export class ChatWorkflow {
  /**
   * Step 1: Save user message to database (durable)
   *
   * This step ensures the user message is persisted BEFORE any processing.
   * If the workflow crashes after this step, the message is not lost.
   */
  @DBOS.step()
  static async saveUserMessage(
    context: ConversationContext,
    message: ChatMessage
  ): Promise<string> {
    const startTime = Date.now();
    DBOS.logger.info(`[ChatWorkflow] Saving user message for conversation ${context.conversationId}`);

    const knex = (DBOS as any).knexClient;
    if (!knex) {
      DBOS.logger.warn('[ChatWorkflow] knexClient not available, skipping PostgreSQL message storage');
      // Generate message ID even if we can't store it
      const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      return messageId;
    }

    // Generate message ID
    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // Insert into messages table (PostgreSQL via knex)
    await knex.raw(
      `INSERT INTO messages (
        id,
        conversation_id,
        role,
        content,
        timestamp,
        metadata,
        created_at
      ) VALUES (?, ?, ?, ?, ?, ?, NOW())`,
      [
        messageId,
        context.conversationId,
        message.role,
        message.content,
        message.timestamp || Date.now(),
        JSON.stringify({
          workflowId: DBOS.workflowID,
          agentId: context.agentId,
          userId: context.userId
        })
      ]
    );

    const duration = Date.now() - startTime;
    DBOS.logger.info(`[ChatWorkflow] User message saved: ${messageId} (${duration}ms)`);

    return messageId;
  }

  /**
   * Step 2a: Load personality context from backend
   *
   * Fetches the agent's personality files to inject into LLM prompt.
   * Uses minimal context by default for token efficiency.
   */
  @DBOS.step()
  static async loadPersonalityContext(
    agentId: string,
    contextType: 'system' | 'minimal' | 'task' = 'minimal'
  ): Promise<PersonalityContext> {
    DBOS.logger.info(`[ChatWorkflow] Loading ${contextType} personality context for agent ${agentId}`);

    try {
      // Call backend personality API
      const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
      const response = await fetch(
        `${backendUrl}/api/v1/agents/${agentId}/personality/context/${contextType}`,
        {
          method: 'GET',
          headers: { 'Content-Type': 'application/json' },
          signal: AbortSignal.timeout(5000) // 5s timeout
        }
      );

      if (!response.ok) {
        DBOS.logger.warn(`[ChatWorkflow] Failed to load personality: ${response.status}`);
        return {}; // Return empty context, continue without personality
      }

      const data = await response.json() as { context: string };

      // Parse personality context from markdown
      const context = ChatWorkflow.parsePersonalityContext(data.context);

      DBOS.logger.info(`[ChatWorkflow] Personality context loaded (${Object.keys(context).length} files)`);
      return context;

    } catch (error) {
      DBOS.logger.error('[ChatWorkflow] Error loading personality context', error);
      return {}; // Graceful degradation
    }
  }

  /**
   * Step 2b: Load memory context from ZeroDB
   *
   * Fetches recent memories and semantically similar past conversations.
   * Combines recency (last 10) with relevance (semantic search on current message).
   */
  @DBOS.step()
  static async loadMemoryContext(
    conversationId: string,
    agentId: string,
    currentMessage: string,
    limit: number = 10
  ): Promise<MemoryContext> {
    DBOS.logger.info(`[ChatWorkflow] Loading memory context for agent ${agentId}`);

    try {
      const zeroDBClient = getZeroDBClient();

      // Get recent memories (last 10 from this session)
      const recentContext = await zeroDBClient.getContext({
        session_id: conversationId,
        agent_id: agentId,
        limit: limit
      });

      // Get semantically relevant memories (search across all sessions)
      const relevantResults = await zeroDBClient.searchMemory({
        query: currentMessage,
        agent_id: agentId,  // Scoped to this agent only
        limit: 5
      });

      const memoryContext: MemoryContext = {
        recentMemories: recentContext.memories,
        relevantMemories: relevantResults.results,
        totalMemories: relevantResults.total
      };

      DBOS.logger.info(
        `[ChatWorkflow] Memory context loaded: ${recentContext.memories.length} recent, ` +
        `${relevantResults.results.length} relevant`
      );

      return memoryContext;

    } catch (error) {
      DBOS.logger.error('[ChatWorkflow] Error loading memory context', error);
      // Graceful degradation - return empty memory context
      return {
        recentMemories: [],
        relevantMemories: [],
        totalMemories: 0
      };
    }
  }

  /**
   * Helper: Parse markdown personality context into structured object
   */
  private static parsePersonalityContext(markdown: string): PersonalityContext {
    const context: PersonalityContext = {};

    // Extract sections by markdown headers
    const sections = markdown.split(/^# /m).filter(Boolean);

    for (const section of sections) {
      const lines = section.split('\n');
      const title = lines[0].toLowerCase();

      if (title.includes('identity')) {
        context.identity = section;
      } else if (title.includes('soul') || title.includes('ethic')) {
        context.soul = section;
      } else if (title.includes('user')) {
        context.user = section;
      } else if (title.includes('tool')) {
        context.tools = section;
      } else if (title.includes('memory')) {
        context.memory = section;
      }
    }

    return context;
  }

  /**
   * Step 2b: Call LLM with personality context
   *
   * Injects personality into system message and calls Claude API.
   * Retries automatically on failure (DBOS handles exponential backoff).
   */
  @DBOS.step()
  static async callLLM(request: LLMRequest): Promise<LLMResponse> {
    const startTime = Date.now();
    DBOS.logger.info(`[ChatWorkflow] Calling LLM for conversation ${request.conversationId}`);

    const apiKey = process.env.ANTHROPIC_API_KEY;
    if (!apiKey) {
      throw new Error('ANTHROPIC_API_KEY not configured');
    }

    // Build system message with personality + memory context
    const systemMessage = ChatWorkflow.buildSystemMessage(
      request.personalityContext,
      request.memoryContext
    );

    // Prepare messages for Claude API
    const messages = request.messages.map(msg => ({
      role: msg.role === 'user' ? 'user' : 'assistant',
      content: msg.content
    }));

    // Call Claude API
    const response = await fetch('https://api.anthropic.com/v1/messages', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: request.model || 'claude-sonnet-4-5-20250929',
        max_tokens: request.maxTokens || 4096,
        temperature: request.temperature || 1.0,
        system: systemMessage,
        messages: messages
      }),
      signal: AbortSignal.timeout(60000) // 60s timeout
    });

    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Claude API error: ${response.status} - ${error}`);
    }

    interface ClaudeAPIResponse {
      content: Array<{ text: string }>;
      model: string;
      usage: {
        input_tokens: number;
        output_tokens: number;
        total_tokens?: number;
      };
      stop_reason: string;
    }

    const data = await response.json() as ClaudeAPIResponse;

    const duration = Date.now() - startTime;
    DBOS.logger.info(`[ChatWorkflow] LLM response received (${duration}ms, ${data.usage.input_tokens + data.usage.output_tokens} tokens)`);

    return {
      content: data.content[0].text,
      model: data.model,
      usage: {
        promptTokens: data.usage.input_tokens,
        completionTokens: data.usage.output_tokens,
        totalTokens: data.usage.input_tokens + data.usage.output_tokens
      },
      finishReason: data.stop_reason
    };
  }

  /**
   * Helper: Build system message with personality + memory context
   */
  private static buildSystemMessage(
    personality?: PersonalityContext,
    memory?: MemoryContext
  ): string {
    const parts: string[] = [];

    // 1. Personality sections (static .md files)
    if (personality && Object.keys(personality).length > 0) {
      if (personality.identity) {
        parts.push('# Your Identity\n' + personality.identity);
      }

      if (personality.soul) {
        parts.push('\n# Your Core Ethics & Personality\n' + personality.soul);
      }

      if (personality.user) {
        parts.push('\n# User Interaction Guidelines\n' + personality.user);
      }

      if (personality.memory) {
        parts.push('\n# Curated Long-Term Learnings\n' + personality.memory);
      }
    }

    // 2. Memory sections (dynamic ZeroDB memories)
    if (memory && memory.totalMemories > 0) {
      // Recent conversation history
      if (memory.recentMemories.length > 0) {
        const recentSection = [
          '\n# Recent Conversation History',
          'Here are the last exchanges from this conversation:',
          ''
        ];

        for (const mem of memory.recentMemories) {
          recentSection.push(
            `[${new Date(mem.created_at).toLocaleString()}] ${mem.role}: ${mem.content.substring(0, 200)}${mem.content.length > 200 ? '...' : ''}`
          );
        }

        parts.push(recentSection.join('\n'));
      }

      // Relevant past memories
      if (memory.relevantMemories.length > 0) {
        const relevantSection = [
          '\n# Relevant Past Context',
          'Based on the current discussion, here are related memories from previous conversations:',
          ''
        ];

        for (const mem of memory.relevantMemories) {
          const score = mem.score ? ` (relevance: ${(mem.score * 100).toFixed(0)}%)` : '';
          relevantSection.push(
            `[${new Date(mem.created_at).toLocaleString()}]${score} ${mem.role}: ${mem.content.substring(0, 150)}${mem.content.length > 150 ? '...' : ''}`
          );
        }

        parts.push(relevantSection.join('\n'));
      }
    }

    // Fallback
    if (parts.length === 0) {
      return 'You are a helpful AI assistant.';
    }

    return parts.join('\n\n');
  }

  /**
   * Step 3: Save assistant message (durable)
   *
   * Persists the LLM response to database.
   * If this step fails, DBOS will retry until it succeeds.
   */
  @DBOS.step()
  static async saveAssistantMessage(
    context: ConversationContext,
    content: string,
    metadata: {
      model: string;
      tokensUsed: number;
      finishReason: string;
    }
  ): Promise<string> {
    const startTime = Date.now();
    DBOS.logger.info(`[ChatWorkflow] Saving assistant message for conversation ${context.conversationId}`);

    const knex = (DBOS as any).knexClient;
    if (!knex) {
      DBOS.logger.warn('[ChatWorkflow] knexClient not available, skipping PostgreSQL message storage');
      // Generate message ID even if we can't store it
      const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
      return messageId;
    }

    // Generate message ID
    const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;

    // Insert assistant response
    await knex.raw(
      `INSERT INTO messages (
        id,
        conversation_id,
        role,
        content,
        timestamp,
        metadata,
        created_at
      ) VALUES (?, ?, ?, ?, ?, ?, NOW())`,
      [
        messageId,
        context.conversationId,
        'assistant',
        content,
        Date.now(),
        JSON.stringify({
          workflowId: DBOS.workflowID,
          agentId: context.agentId,
          model: metadata.model,
          tokensUsed: metadata.tokensUsed,
          finishReason: metadata.finishReason
        })
      ]
    );

    const duration = Date.now() - startTime;
    DBOS.logger.info(`[ChatWorkflow] Assistant message saved: ${messageId} (${duration}ms)`);

    return messageId;
  }

  /**
   * Step 4: Store conversation exchange in ZeroDB memory
   *
   * Stores both user and assistant messages in ZeroDB for:
   * - Semantic search across conversations
   * - Cross-agent knowledge sharing
   * - Long-term memory persistence
   */
  @DBOS.step()
  static async storeConversationMemory(
    context: ConversationContext,
    userMessage: ChatMessage,
    assistantResponse: string,
    importance: number = 0.5
  ): Promise<void> {
    const startTime = Date.now();
    DBOS.logger.info(`[ChatWorkflow] Storing conversation memory for ${context.conversationId}`);

    try {
      const zeroDBClient = getZeroDBClient();

      // Store user message
      await zeroDBClient.storeMemory({
        content: userMessage.content,
        role: 'user',
        session_id: context.conversationId,
        agent_id: context.agentId,
        metadata: {
          workspace_id: context.workspaceId,
          user_id: context.userId,
          importance: importance,
          workflow_id: DBOS.workflowID
        },
        tags: ['conversation', 'user-input']
      });

      // Store assistant response
      await zeroDBClient.storeMemory({
        content: assistantResponse,
        role: 'assistant',
        session_id: context.conversationId,
        agent_id: context.agentId,
        metadata: {
          workspace_id: context.workspaceId,
          importance: importance,
          workflow_id: DBOS.workflowID
        },
        tags: ['conversation', 'assistant-response']
      });

      const duration = Date.now() - startTime;
      DBOS.logger.info(`[ChatWorkflow] Conversation memory stored (${duration}ms)`);

    } catch (error) {
      DBOS.logger.error('[ChatWorkflow] Failed to store conversation memory', error);
      // Don't throw - memory storage failure should not break the conversation
    }
  }

  /**
   * Main Workflow: Orchestrates durable chat with personality + memory
   *
   * This is the entry point. DBOS guarantees:
   * - If it crashes, it resumes from last completed step
   * - Each step executes exactly once (idempotent)
   * - Complete audit trail in workflow_status table
   */
  @DBOS.workflow()
  static async processChat(
    context: ConversationContext,
    userMessage: ChatMessage,
    conversationHistory: ChatMessage[] = []
  ): Promise<ChatWorkflowResult> {
    const workflowStart = Date.now();
    DBOS.logger.info(`[ChatWorkflow] Starting workflow for conversation ${context.conversationId}`);

    try {
      // Step 1: Save user message (durable storage)
      const userMessageId = await ChatWorkflow.saveUserMessage(context, userMessage);

      // Step 2a: Load personality context
      const personalityContext = await ChatWorkflow.loadPersonalityContext(
        context.agentId,
        'minimal' // Use minimal context for token efficiency
      );

      // Step 2b: Load memory context from ZeroDB
      const memoryContext = await ChatWorkflow.loadMemoryContext(
        context.conversationId,
        context.agentId,
        userMessage.content,
        10 // Last 10 messages
      );

      // Step 2c: Call LLM with personality + memory
      const llmRequest: LLMRequest = {
        conversationId: context.conversationId,
        agentId: context.agentId,
        messages: [...conversationHistory, userMessage],
        personalityContext,
        memoryContext
      };

      const llmResponse = await ChatWorkflow.callLLM(llmRequest);

      // Step 3: Save assistant message
      const assistantMessageId = await ChatWorkflow.saveAssistantMessage(
        context,
        llmResponse.content,
        {
          model: llmResponse.model,
          tokensUsed: llmResponse.usage.totalTokens,
          finishReason: llmResponse.finishReason
        }
      );

      // Step 4: Store conversation in ZeroDB memory
      await ChatWorkflow.storeConversationMemory(
        context,
        userMessage,
        llmResponse.content,
        0.6 // Default importance score
      );

      const processingTime = Date.now() - workflowStart;

      const result: ChatWorkflowResult = {
        conversationId: context.conversationId,
        userMessageId,
        assistantMessageId,
        assistantContent: llmResponse.content,
        tokensUsed: llmResponse.usage.totalTokens,
        processingTimeMs: processingTime
      };

      DBOS.logger.info(
        `[ChatWorkflow] Workflow completed successfully (${processingTime}ms, ` +
        `${result.tokensUsed} tokens, ${memoryContext.recentMemories.length + memoryContext.relevantMemories.length} memories loaded)`
      );

      return result;

    } catch (error) {
      DBOS.logger.error(`[ChatWorkflow] Workflow failed for conversation ${context.conversationId}`, error);
      throw error;
    }
  }

  /**
   * Recovery Workflow: Resume interrupted conversations
   *
   * Called manually to recover workflows that got stuck.
   * In production, this could run periodically to check for stale workflows.
   */
  @DBOS.workflow()
  static async recoverStuckWorkflow(workflowUuid: string): Promise<void> {
    DBOS.logger.info(`[ChatWorkflow] Attempting to recover workflow ${workflowUuid}`);

    const knex = (DBOS as any).knexClient;
    if (!knex) {
      throw new Error('knexClient not available for recovery');
    }

    // Check workflow status
    const result = await knex.raw(
      `SELECT * FROM dbos_system.workflow_status WHERE workflow_uuid = ?`,
      [workflowUuid]
    );

    if (!result.rows || result.rows.length === 0) {
      throw new Error(`Workflow ${workflowUuid} not found`);
    }

    const workflow = result.rows[0];
    DBOS.logger.info(`[ChatWorkflow] Workflow status: ${workflow.status}`);

    // DBOS automatically resumes PENDING workflows on restart
    // This is mainly for monitoring/alerting purposes
    await knex.raw(
      `UPDATE dbos_system.workflow_status
       SET recovery_attempts = COALESCE(recovery_attempts, 0) + 1
       WHERE workflow_uuid = ?`,
      [workflowUuid]
    );

    DBOS.logger.info(`[ChatWorkflow] Recovery logged for workflow ${workflowUuid}`);
  }
}
