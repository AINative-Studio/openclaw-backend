/**
 * ZeroDB Client for Gateway
 *
 * TypeScript client for ZeroDB Memory MCP integration.
 * Provides agent memory storage, semantic search, and context retrieval.
 *
 * Based on: /Users/aideveloper/core/zerodb-memory-mcp
 * Pattern: MCP-style agent memory with session/agent isolation
 */

import { DBOS } from '@dbos-inc/dbos-sdk';

// ==================== Types ====================

export interface ZeroDBConfig {
  apiUrl: string;
  username: string;
  password: string;
  projectId: string;
}

export interface StoreMemoryRequest {
  content: string;
  role: 'user' | 'assistant' | 'system';
  session_id: string;
  agent_id: string;
  metadata?: {
    agent_type?: string;
    task_id?: string;
    importance?: number;
    [key: string]: any;
  };
  tags?: string[];
}

export interface SearchMemoryRequest {
  query: string;
  session_id?: string;
  agent_id?: string;
  limit?: number;
  type?: string;
}

export interface GetContextRequest {
  session_id: string;
  agent_id?: string;
  max_tokens?: number;
  limit?: number;
}

export interface MemoryResult {
  id: string;
  content: string;
  role: string;
  session_id: string;
  agent_id: string;
  metadata: Record<string, any>;
  tags: string[];
  created_at: string;
  score?: number;
}

export interface SearchResult {
  results: MemoryResult[];
  total: number;
  query: string;
}

export interface ContextWindow {
  memories: MemoryResult[];
  total_tokens: number;
  truncated: boolean;
}

// ==================== Client ====================

export class ZeroDBClient {
  private config: ZeroDBConfig;
  private authToken?: string;
  private tokenExpiry?: number;

  constructor(config: ZeroDBConfig) {
    this.config = config;
  }

  /**
   * Initialize client and authenticate
   */
  async initialize(): Promise<void> {
    await this.authenticate();
  }

  /**
   * Authenticate and get access token
   */
  private async authenticate(): Promise<void> {
    try {
      const response = await fetch(`${this.config.apiUrl}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: this.config.username,
          password: this.config.password
        })
      });

      if (!response.ok) {
        throw new Error(`Authentication failed: ${response.status}`);
      }

      const data = await response.json() as { access_token: string; expires_in?: number };
      this.authToken = data.access_token;
      this.tokenExpiry = Date.now() + (data.expires_in || 3600) * 1000;

      DBOS.logger.info('[ZeroDB] Authenticated successfully');
    } catch (error) {
      DBOS.logger.error('[ZeroDB] Authentication failed', error);
      throw error;
    }
  }

  /**
   * Ensure token is valid, refresh if needed
   */
  private async ensureAuthenticated(): Promise<void> {
    if (!this.authToken || !this.tokenExpiry || Date.now() >= this.tokenExpiry - 60000) {
      await this.authenticate();
    }
  }

  /**
   * Get authorization headers
   */
  private getHeaders(): Record<string, string> {
    return {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.authToken}`
    };
  }

  /**
   * Store agent memory (MCP pattern)
   *
   * Stores a memory entry for an agent within a session.
   * Memories are searchable via semantic similarity.
   *
   * @param request - Memory storage request
   * @returns Stored memory with ID
   */
  async storeMemory(request: StoreMemoryRequest): Promise<MemoryResult> {
    await this.ensureAuthenticated();

    try {
      const response = await fetch(
        `${this.config.apiUrl}/projects/${this.config.projectId}/memory`,
        {
          method: 'POST',
          headers: this.getHeaders(),
          body: JSON.stringify({
            content: request.content,
            role: request.role,
            session_id: request.session_id,
            agent_id: request.agent_id,
            metadata: request.metadata || {},
            tags: request.tags || []
          })
        }
      );

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`Failed to store memory: ${response.status} - ${error}`);
      }

      const result = await response.json() as MemoryResult;
      DBOS.logger.info(`[ZeroDB] Memory stored: ${result.id} (agent: ${request.agent_id})`);
      return result;

    } catch (error) {
      DBOS.logger.error('[ZeroDB] Failed to store memory', error);
      throw error;
    }
  }

  /**
   * Search memories using semantic similarity (MCP pattern)
   *
   * Searches across agent memories within a session.
   * Optional agent_id filter for single-agent search.
   *
   * @param request - Search request
   * @returns Search results with similarity scores
   */
  async searchMemory(request: SearchMemoryRequest): Promise<SearchResult> {
    await this.ensureAuthenticated();

    try {
      const params: Record<string, string> = {
        query: request.query,
        limit: String(request.limit || 10)
      };

      if (request.session_id) {
        params.session_id = request.session_id;
      }
      if (request.agent_id) {
        params.agent_id = request.agent_id;
      }
      if (request.type) {
        params.type = request.type;
      }

      const queryString = new URLSearchParams(params).toString();
      const response = await fetch(
        `${this.config.apiUrl}/projects/${this.config.projectId}/memory/search?${queryString}`,
        {
          method: 'GET',
          headers: this.getHeaders()
        }
      );

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`Failed to search memory: ${response.status} - ${error}`);
      }

      const result = await response.json() as SearchResult;
      DBOS.logger.info(`[ZeroDB] Memory search: found ${result.total} results`);
      return result;

    } catch (error) {
      DBOS.logger.error('[ZeroDB] Failed to search memory', error);
      throw error;
    }
  }

  /**
   * Get context window for agent session (MCP pattern)
   *
   * Retrieves recent memories for an agent within a session,
   * respecting token budget constraints.
   *
   * @param request - Context request
   * @returns Context window with memories
   */
  async getContext(request: GetContextRequest): Promise<ContextWindow> {
    await this.ensureAuthenticated();

    try {
      const params: Record<string, string> = {
        session_id: request.session_id,
        max_tokens: String(request.max_tokens || 8192),
        limit: String(request.limit || 50)
      };

      if (request.agent_id) {
        params.agent_id = request.agent_id;
      }

      const queryString = new URLSearchParams(params).toString();
      const response = await fetch(
        `${this.config.apiUrl}/projects/${this.config.projectId}/memory/context?${queryString}`,
        {
          method: 'GET',
          headers: this.getHeaders()
        }
      );

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`Failed to get context: ${response.status} - ${error}`);
      }

      const result = await response.json() as ContextWindow;
      DBOS.logger.info(
        `[ZeroDB] Context retrieved: ${result.memories.length} memories, ` +
        `${result.total_tokens} tokens, truncated: ${result.truncated}`
      );
      return result;

    } catch (error) {
      DBOS.logger.error('[ZeroDB] Failed to get context', error);
      throw error;
    }
  }
}

// ==================== Singleton Factory ====================

let _zeroDBClient: ZeroDBClient | null = null;

/**
 * Get singleton ZeroDB client instance
 */
export function getZeroDBClient(): ZeroDBClient {
  if (!_zeroDBClient) {
    const config: ZeroDBConfig = {
      apiUrl: process.env.ZERODB_API_URL || 'https://api.ainative.studio',
      username: process.env.ZERODB_USERNAME || '',
      password: process.env.ZERODB_PASSWORD || '',
      projectId: process.env.ZERODB_PROJECT_ID || ''
    };

    if (!config.username || !config.password || !config.projectId) {
      throw new Error(
        'ZeroDB configuration incomplete. Required env vars: ' +
        'ZERODB_API_URL, ZERODB_USERNAME, ZERODB_PASSWORD, ZERODB_PROJECT_ID'
      );
    }

    _zeroDBClient = new ZeroDBClient(config);
  }

  return _zeroDBClient;
}

/**
 * Initialize ZeroDB client on startup
 */
export async function initializeZeroDBClient(): Promise<void> {
  try {
    const client = getZeroDBClient();
    await client.initialize();
    DBOS.logger.info('[ZeroDB] Client initialized successfully');
  } catch (error) {
    DBOS.logger.error('[ZeroDB] Failed to initialize client', error);
    throw error;
  }
}
