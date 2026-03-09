# Chat Persistence Architecture

## Overview

The OpenClaw Backend chat persistence system provides durable storage for agent-user conversations with dual storage architecture: PostgreSQL for metadata and ZeroDB for message content. This enables both efficient pagination and powerful semantic search capabilities across conversation histories.

**Key Features:**
- Workspace-isolated conversation management
- Dual storage: PostgreSQL metadata + ZeroDB message content
- Automatic message persistence through OpenClaw Gateway bridge
- Semantic search using ZeroDB vector embeddings
- Graceful degradation on storage failures
- Paginated message retrieval
- Support for conversation archival and lifecycle management

## Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              User Layer                                   │
│  ┌────────────┐         ┌────────────┐         ┌────────────┐           │
│  │  WhatsApp  │ ──────► │   FastAPI  │ ◄────── │  REST API  │           │
│  │   Client   │         │  Backend   │         │   Client   │           │
│  └────────────┘         └────────────┘         └────────────┘           │
└───────────────────────────────┬──────────────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────────────┐
│                         Bridge Layer                                      │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │         ProductionOpenClawBridge (Auto-Persistence)              │    │
│  │  ┌────────────────────┐              ┌──────────────────────┐   │    │
│  │  │ send_message()     │──────────┬──►│ ConversationService  │   │    │
│  │  └────────────────────┘          │   └──────────────────────┘   │    │
│  │                                   │                               │    │
│  │  ┌────────────────────┐          │   ┌──────────────────────┐   │    │
│  │  │ Gateway WebSocket  │          └──►│  Persistence Logic   │   │    │
│  │  └────────────────────┘              └──────────────────────┘   │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└───────────────────────────┬──────────────────────────────────────────────┘
                            │
         ┌──────────────────┴──────────────────┐
         ▼                                      ▼
┌─────────────────────┐              ┌──────────────────────┐
│   PostgreSQL DB     │              │     ZeroDB Cloud     │
│ ┌─────────────────┐ │              │ ┌────────────────┐  │
│ │  workspaces     │ │              │ │  messages      │  │
│ │  - id           │ │              │ │  (table rows)  │  │
│ │  - name         │ │              │ │                │  │
│ │  - zerodb_      │ │              │ │  - id          │  │
│ │    project_id   │ │◄────link─────┤ │  - content     │  │
│ └─────────────────┘ │              │ │  - role        │  │
│                     │              │ │  - timestamp   │  │
│ ┌─────────────────┐ │              │ └────────────────┘  │
│ │  users          │ │              │                      │
│ │  - id           │ │              │ ┌────────────────┐  │
│ │  - email        │ │              │ │  Memory API    │  │
│ │  - workspace_id │ │              │ │  (embeddings)  │  │
│ └─────────────────┘ │              │ │                │  │
│                     │              │ │  - title       │  │
│ ┌─────────────────┐ │              │ │  - content     │  │
│ │  conversations  │ │              │ │  - tags        │  │
│ │  - id           │ │              │ │  - metadata    │  │
│ │  - workspace_id │ │              │ │  - vector      │  │
│ │  - agent_id     │ │              │ └────────────────┘  │
│ │  - user_id      │ │              │                      │
│ │  - session_key  │ │              └──────────────────────┘
│ │  - message_count│ │
│ │  - status       │ │
│ └─────────────────┘ │
│                     │
│ ┌─────────────────┐ │
│ │agent_swarm_     │ │
│ │  instances      │ │
│ │  - id           │ │
│ │  - workspace_id │ │
│ │  - openclaw_    │ │
│ │    session_key  │ │
│ └─────────────────┘ │
└─────────────────────┘
```

## Data Flow

### 1. Message Sending Flow

```
User Message
    │
    ▼
WhatsApp/API Client
    │
    ▼
FastAPI Backend
    │
    ▼
ProductionOpenClawBridge.send_message()
    │
    ├──► OpenClaw Gateway (WebSocket) ────► Agent Processing
    │
    └──► ConversationService.add_message()
            │
            ├──► Find/Create Conversation (PostgreSQL)
            │       - Lookup by session_key
            │       - Create if first message
            │
            ├──► Store Message (ZeroDB Table)
            │       - project_id from workspace.zerodb_project_id
            │       - table_name: "messages"
            │       - row_data: {conversation_id, role, content, timestamp}
            │
            ├──► Store Embedding (ZeroDB Memory) [OPTIONAL]
            │       - Graceful degradation if fails
            │       - type: "conversation"
            │       - tags: [conversation_id, role]
            │
            └──► Update Metadata (PostgreSQL)
                    - conversation.message_count += 1
                    - conversation.last_message_at = now()
```

### 2. Message Retrieval Flow

```
GET /conversations/{id}/messages
    │
    ▼
ConversationService.get_messages()
    │
    ├──► Fetch Conversation (PostgreSQL)
    │       - Validate conversation exists
    │       - Get workspace.zerodb_project_id
    │
    └──► Query Messages (ZeroDB Table)
            - project_id: workspace.zerodb_project_id
            - table_name: "messages"
            - filter: conversation_id
            - pagination: limit, offset
            │
            ▼
        Return message list with metadata
```

### 3. Semantic Search Flow

```
POST /conversations/{id}/search
    │
    ▼
ConversationService.search_conversation_semantic()
    │
    ├──► Validate Conversation (PostgreSQL)
    │       - Ensure conversation exists
    │
    ├──► Search Memories (ZeroDB Memory API)
    │       - query: user's search text
    │       - type: "conversation"
    │       - limit: 5-10 results
    │
    ├──► Filter Results (In-Memory)
    │       - Only messages from this conversation_id
    │       - Check metadata.conversation_id
    │
    └──► Return Ranked Results
            - results: [{content, score, metadata}]
            - total: count after filtering
```

## Components

### 1. PostgreSQL Storage Layer

**Purpose:** Store conversation metadata and relationships

**Tables:**

#### `workspaces`
- Primary organizational boundary
- Links to ZeroDB project via `zerodb_project_id`
- Cascading delete for all contained data

**Schema:**
```sql
CREATE TABLE workspaces (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    slug VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    zerodb_project_id VARCHAR(255) UNIQUE,  -- Link to ZeroDB
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ
);
CREATE INDEX idx_workspaces_name ON workspaces(name);
CREATE INDEX idx_workspaces_zerodb_project ON workspaces(zerodb_project_id);
```

#### `users`
- Workspace members
- Email-based identification

**Schema:**
```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email VARCHAR(255) NOT NULL UNIQUE,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_workspace ON users(workspace_id);
```

#### `conversations`
- Conversation metadata and tracking
- Links user, agent, workspace, and OpenClaw session

**Schema:**
```sql
CREATE TYPE conversation_status AS ENUM ('active', 'archived', 'deleted');

CREATE TABLE conversations (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    agent_id UUID NOT NULL REFERENCES agent_swarm_instances(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE SET NULL,
    openclaw_session_key VARCHAR(255) UNIQUE,  -- Link to OpenClaw Gateway session
    zerodb_table_name VARCHAR(100) DEFAULT 'messages',
    zerodb_conversation_row_id VARCHAR(255),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_message_at TIMESTAMPTZ,
    message_count INTEGER DEFAULT 0,
    status conversation_status DEFAULT 'active'
);
CREATE INDEX idx_conversations_workspace ON conversations(workspace_id);
CREATE INDEX idx_conversations_agent ON conversations(agent_id);
CREATE INDEX idx_conversations_user ON conversations(user_id);
CREATE INDEX idx_conversations_session ON conversations(openclaw_session_key);
CREATE INDEX idx_conversations_status ON conversations(status);
```

#### `agent_swarm_instances`
- Extended to include workspace relationship
- Existing fields preserved

**New Fields:**
```sql
ALTER TABLE agent_swarm_instances
ADD COLUMN workspace_id UUID REFERENCES workspaces(id) ON DELETE CASCADE;

CREATE INDEX idx_agent_swarm_instances_workspace ON agent_swarm_instances(workspace_id);
```

### 2. ZeroDB Dual Storage

**Purpose:** Store message content with dual retrieval methods

#### Storage Method 1: NoSQL Tables (Required)

**Use Case:** Paginated message retrieval, chronological display

**Structure:**
- **Project:** One per workspace (linked via `workspace.zerodb_project_id`)
- **Table Name:** `messages` (configurable)
- **Row Data:**
  ```json
  {
    "id": "row_abc123",
    "conversation_id": "uuid-of-conversation",
    "role": "user|assistant|system",
    "content": "The actual message text",
    "timestamp": "2026-03-02T10:30:00Z",
    "metadata": {
      "agent_version": "1.0.0",
      "model": "claude-3-5-sonnet-20241022",
      "tokens": 150
    }
  }
  ```

**Query Pattern:**
```python
# Retrieve messages for conversation
messages = await zerodb.query_table(
    project_id=workspace.zerodb_project_id,
    table_name="messages",
    limit=50,
    skip=0
)
```

#### Storage Method 2: Memory API (Optional)

**Use Case:** Semantic search, context retrieval, similarity queries

**Structure:**
- **Title:** `Message in conversation {conversation_id}`
- **Content:** The message text (used for embeddings)
- **Type:** `conversation`
- **Tags:** `[conversation_id, role]`
- **Metadata:**
  ```json
  {
    "conversation_id": "uuid-of-conversation",
    "role": "user",
    "timestamp": "2026-03-02T10:30:00Z"
  }
  ```

**Query Pattern:**
```python
# Semantic search within conversation
results = await zerodb.search_memories(
    query="How do I configure authentication?",
    limit=5,
    type="conversation"
)
# Then filter by conversation_id in results
```

**Graceful Degradation:**
- Table storage is REQUIRED (hard failure if unavailable)
- Memory storage is OPTIONAL (logs warning but continues)
- This ensures basic functionality even if semantic search is unavailable

### 3. ConversationService

**Location:** `backend/services/conversation_service.py`

**Purpose:** Business logic layer for conversation and message management

**Key Methods:**

```python
class ConversationService:
    def __init__(self, db: AsyncSession, zerodb_client: ZeroDBClient):
        """Initialize with database and ZeroDB client."""

    async def create_conversation(
        workspace_id: UUID,
        agent_id: UUID,
        user_id: UUID,
        openclaw_session_key: str
    ) -> Conversation:
        """
        Create new conversation.
        Validates workspace has zerodb_project_id before creation.
        """

    async def add_message(
        conversation_id: UUID,
        role: str,
        content: str,
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Add message with dual storage.
        Returns: {id, memory_id, conversation_id, role, content, timestamp}
        """

    async def get_messages(
        conversation_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict]:
        """Retrieve paginated messages from ZeroDB table."""

    async def search_conversation_semantic(
        conversation_id: UUID,
        query: str,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Semantic search within conversation.
        Returns: {results: [...], total: int, query: str}
        """

    async def list_conversations(
        workspace_id: Optional[UUID] = None,
        agent_id: Optional[UUID] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0
    ) -> Tuple[List[Conversation], int]:
        """List conversations with filters and pagination."""
```

**Error Handling:**
- `ValueError`: Conversation not found, workspace not found, missing zerodb_project_id
- `ZeroDBConnectionError`: Network failures, DNS issues
- `ZeroDBAPIError`: API errors (4xx/5xx responses)

### 4. ProductionOpenClawBridge

**Location:** `backend/agents/orchestration/production_openclaw_bridge.py`

**Purpose:** WebSocket bridge to OpenClaw Gateway with automatic message persistence

**Key Features:**

1. **Optional Persistence Dependencies**
   ```python
   def __init__(
       url: str,
       token: str,
       db: Optional[AsyncSession] = None,
       zerodb_client: Optional[ZeroDBClient] = None
   ):
       """
       If both db and zerodb_client provided:
           - Initialize ConversationService
           - Enable automatic persistence
       Otherwise:
           - Skip persistence (backward compatible)
       """
   ```

2. **Automatic Message Persistence**
   ```python
   async def send_message(
       session_key: str,
       message: str,
       metadata: Optional[Dict] = None
   ):
       """
       1. Send message to OpenClaw Gateway (primary)
       2. If persistence enabled:
          - Find/create conversation by session_key
          - Store message via ConversationService
       3. Graceful degradation on persistence failures
       """
   ```

3. **Graceful Degradation**
   - Persistence failures logged as warnings
   - Gateway communication continues uninterrupted
   - Messages still delivered to agents

**Backward Compatibility:**
- Existing code without `db`/`zerodb_client` works unchanged
- Persistence is opt-in via constructor parameters

### 5. API Endpoints

**Location:** `backend/api/v1/endpoints/conversations.py`

**Router:** `/api/v1/conversations`

**Endpoints:**

1. **GET /** - List conversations
   - Filters: `workspace_id`, `agent_id`, `status`
   - Pagination: `limit` (1-200, default 50), `offset` (default 0)
   - Response: `{conversations: [...], total: int, limit: int, offset: int}`

2. **GET /{conversation_id}** - Get single conversation
   - Returns: Conversation details with metadata
   - Error: 404 if not found

3. **GET /{conversation_id}/messages** - Get messages
   - Pagination: `limit` (1-200, default 50), `offset` (default 0)
   - Response: `{messages: [...], total: int}`

4. **POST /{conversation_id}/search** - Semantic search
   - Body: `{query: str, limit: int}`
   - Response: `{results: [...], total: int, query: str}`

**Dependency Injection:**
```python
async def get_conversation_service(db: AsyncSession = Depends(get_db)):
    """
    Creates ConversationService with ZeroDB client.
    Returns 503 if ZERODB_API_KEY not configured.
    """
```

## Key Design Decisions

### 1. Why Dual Storage (Table + Memory)?

**Problem:** Single storage method cannot efficiently support both use cases:
- **Pagination:** Requires ordered retrieval by timestamp
- **Semantic Search:** Requires vector similarity search

**Solution:** Store messages twice with different optimizations:

| Storage Method | Optimized For | Query Type | Failure Impact |
|---------------|---------------|------------|----------------|
| ZeroDB Table | Pagination, chronological display | SQL-like queries | Hard failure (required) |
| ZeroDB Memory | Semantic search, context retrieval | Vector similarity | Soft failure (graceful degradation) |

**Benefits:**
- Fast pagination without vector search overhead
- Powerful semantic search without scanning all messages
- Graceful degradation: basic features work even if semantic search fails

**Trade-offs:**
- Additional storage (messages stored twice)
- Slight delay on message send (two writes)
- Mitigated by: async writes, memory writes are non-blocking

### 2. Why PostgreSQL for Metadata, ZeroDB for Content?

**PostgreSQL Strengths:**
- ACID transactions for metadata consistency
- Complex joins (workspace → agents → conversations)
- Proven reliability for relational data
- Fast indexed queries on UUIDs and foreign keys

**ZeroDB Strengths:**
- Flexible schema for message content
- Built-in vector embeddings for semantic search
- Scalable document storage
- No need for schema migrations on message format changes

**Division of Responsibility:**

| Data Type | Storage | Reason |
|-----------|---------|--------|
| Workspace hierarchy | PostgreSQL | Relational integrity |
| User accounts | PostgreSQL | Authentication queries |
| Conversation metadata | PostgreSQL | Filtering, counting, joins |
| Message content | ZeroDB | Flexible schema, embeddings |
| Message vectors | ZeroDB | Semantic search |

### 3. Why Graceful Degradation Strategy?

**Problem:** Persistence failures should not disrupt agent communication

**Solution:** Layered fault tolerance:

```python
# Layer 1: Gateway communication (REQUIRED)
await gateway.send(message)  # Hard failure stops here

# Layer 2: Table storage (REQUIRED for persistence)
try:
    await zerodb.create_table_row(message_data)
except ZeroDBAPIError:
    raise  # Fail fast if table storage fails

# Layer 3: Memory storage (OPTIONAL)
try:
    await zerodb.create_memory(message_data)
except (ZeroDBConnectionError, ZeroDBAPIError):
    logger.warning("Memory storage failed - semantic search unavailable")
    # Continue anyway - pagination still works
```

**Benefits:**
- Agent communication never blocked by persistence issues
- Partial persistence better than no persistence
- Clear distinction between critical and optional features

**User Impact:**
- Critical path (gateway → agent) always works
- Message history (pagination) works if ZeroDB tables available
- Semantic search may be unavailable but doesn't break other features

### 4. Why Workspace-Level ZeroDB Projects?

**Problem:** How to isolate data in multi-tenant architecture?

**Solution:** One ZeroDB project per workspace

**Benefits:**
- Natural data isolation (tenant boundaries)
- Independent scaling per workspace
- Simplified access control (project-level API keys)
- Clean deletion (delete project → all messages gone)

**Implementation:**
```python
workspace.zerodb_project_id = "proj_abc123"  # Stored in PostgreSQL

# All messages for this workspace go to same project
await zerodb.create_table_row(
    project_id=workspace.zerodb_project_id,  # Workspace-scoped
    table_name="messages",
    row_data={...}
)
```

**Alternative Considered:** Single shared project with conversation_id filtering
- **Rejected because:** No tenant isolation, cross-contamination risk, harder access control

## Performance Characteristics

### Write Performance

**Message Send Path:**
1. Gateway send: ~50-100ms (WebSocket round-trip)
2. PostgreSQL conversation update: ~10-20ms (indexed lookup + counter increment)
3. ZeroDB table insert: ~30-50ms (HTTP POST to cloud API)
4. ZeroDB memory insert: ~50-100ms (embedding generation + storage)

**Total:** ~140-270ms end-to-end

**Optimization:** Memory insert happens asynchronously (non-blocking)

### Read Performance

**Pagination (50 messages):**
1. PostgreSQL conversation lookup: ~5-10ms (indexed UUID lookup)
2. ZeroDB table query: ~50-100ms (HTTP GET with pagination)

**Total:** ~55-110ms

**Semantic Search (5 results):**
1. PostgreSQL conversation lookup: ~5-10ms
2. ZeroDB memory search: ~100-200ms (vector similarity computation)
3. In-memory filtering: ~1-5ms

**Total:** ~106-215ms

### Scalability Limits

| Resource | Limit | Mitigation |
|----------|-------|------------|
| Messages per conversation | ~1M | Archive old conversations |
| Conversations per workspace | ~100K | Shard workspaces across projects |
| Concurrent writes | ~100/sec | ZeroDB API rate limits |
| Search query rate | ~10/sec | Cache frequent queries |

## Security Considerations

1. **Workspace Isolation:** All queries filtered by `workspace_id` to prevent cross-tenant access
2. **API Key Protection:** `ZERODB_API_KEY` stored in environment, never in code
3. **SQL Injection:** SQLAlchemy ORM prevents injection attacks
4. **Data Deletion:** Cascading deletes ensure no orphaned data
5. **Access Control:** Future enhancement - row-level security policies

## Monitoring and Observability

**Key Metrics:**
- Message persistence success rate
- ZeroDB API latency (p50, p95, p99)
- Memory storage degradation events
- Conversation creation rate
- Semantic search query performance

**Log Events:**
- `INFO`: Persistence enabled/disabled on bridge init
- `WARNING`: Memory storage failures (graceful degradation)
- `ERROR`: Table storage failures (hard failures)
- `DEBUG`: Message writes, conversation lookups

## Future Enhancements

1. **Message Edit/Delete:** Soft delete in ZeroDB, maintain audit trail
2. **Conversation Forking:** Create child conversations from message history
3. **Export to PDF/Markdown:** Generate conversation transcripts
4. **Full-Text Search:** Traditional keyword search alongside semantic search
5. **Message Reactions:** Emoji reactions stored in metadata
6. **Thread Support:** Sub-conversations within main conversation
7. **Read Receipts:** Track which messages user has seen
8. **Real-Time Updates:** WebSocket notifications for new messages
