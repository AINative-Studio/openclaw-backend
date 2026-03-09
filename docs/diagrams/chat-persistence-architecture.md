# Chat Persistence Architecture Diagrams

**Epic E9 - Chat Persistence**
**Version:** 1.0

This document contains Mermaid diagrams visualizing the Chat Persistence architecture.

---

## Table of Contents

1. [Database Schema (ER Diagram)](#database-schema-er-diagram)
2. [Message Flow (Sequence Diagram)](#message-flow-sequence-diagram)
3. [Component Architecture (System Diagram)](#component-architecture-system-diagram)
4. [Dual Storage Architecture](#dual-storage-architecture)
5. [Conversation Lifecycle State Machine](#conversation-lifecycle-state-machine)
6. [Multi-Channel Routing](#multi-channel-routing)

---

## Database Schema (ER Diagram)

This diagram shows the relationships between PostgreSQL tables.

```mermaid
erDiagram
    Workspace ||--o{ User : contains
    Workspace ||--o{ Conversation : contains
    Workspace ||--o{ AgentSwarmInstance : contains
    User ||--o{ Conversation : owns
    User ||--o{ AgentSwarmInstance : creates
    AgentSwarmInstance ||--o{ Conversation : "assigned to"

    Workspace {
        uuid id PK
        string name
        string slug
        string zerodb_project_id "ZeroDB project for workspace"
        timestamp created_at
        timestamp updated_at
    }

    User {
        uuid id PK
        string email UK "Unique email"
        string full_name
        uuid workspace_id FK
        boolean is_active
        timestamp created_at
        timestamp updated_at
    }

    AgentSwarmInstance {
        uuid id PK
        string name
        string persona
        string model
        string status "RUNNING, PAUSED, etc"
        uuid workspace_id FK
        uuid user_id FK
        string openclaw_session_key
        string openclaw_agent_id
        timestamp created_at
        timestamp updated_at
    }

    Conversation {
        uuid id PK
        uuid workspace_id FK
        uuid user_id FK
        uuid agent_swarm_instance_id FK "Nullable"
        string channel "whatsapp, telegram, slack"
        string channel_conversation_id UK "Unique with channel"
        string title
        json conversation_metadata
        string status "active, archived, deleted"
        timestamp created_at
        timestamp updated_at
        timestamp archived_at
    }
```

**Key Relationships**:
- **Workspace → User**: One-to-many (CASCADE delete)
- **Workspace → AgentSwarmInstance**: One-to-many (CASCADE delete)
- **Workspace → Conversation**: One-to-many (CASCADE delete)
- **User → Conversation**: One-to-many (CASCADE delete)
- **AgentSwarmInstance → Conversation**: One-to-many (SET NULL on delete)

**Unique Constraints**:
- `User.email` - Globally unique
- `Conversation(channel, channel_conversation_id)` - Prevents duplicate channel conversations

---

## Message Flow (Sequence Diagram)

This diagram shows the complete flow from WhatsApp message to ZeroDB storage.

```mermaid
sequenceDiagram
    participant WA as WhatsApp/Telegram/Slack
    participant Bridge as ProductionOpenClawBridge
    participant Service as ConversationService
    participant PG as PostgreSQL
    participant ZDB as ZeroDB
    participant Agent as OpenClaw Agent

    WA->>Bridge: User sends message
    Note over Bridge: Extract session_key,<br/>user_id, workspace_id, agent_id

    Bridge->>Service: get_conversation_by_session_key(session_key)
    Service->>PG: SELECT * FROM conversations<br/>WHERE openclaw_session_key = ?

    alt Conversation exists
        PG-->>Service: Return conversation
    else Conversation not found
        Bridge->>Service: create_conversation(...)
        Service->>PG: INSERT INTO conversations
        Service->>PG: INSERT INTO users (if not exists)
        PG-->>Service: Return new conversation
    end

    Service-->>Bridge: Return conversation

    Bridge->>Service: add_message(conversation_id,<br/>role="user", content="...")
    Service->>ZDB: create_table_row(project_id,<br/>table="messages", row_data={...})
    ZDB-->>Service: Return row ID
    Service->>ZDB: create_memory(content, tags=[conversation_id])

    alt Memory API available
        ZDB-->>Service: Return memory ID
    else Memory API unavailable
        Note over Service: Graceful degradation:<br/>Continue without memory storage
    end

    Service->>PG: UPDATE conversations<br/>SET message_count += 1,<br/>last_message_at = NOW()
    Service-->>Bridge: Return message details

    Bridge->>Agent: send_to_agent(message, context)
    Note over Agent: Process with<br/>conversation context
    Agent-->>Bridge: Return response

    Bridge->>Service: add_message(conversation_id,<br/>role="assistant", content="...")
    Service->>ZDB: create_table_row(...)
    Service->>ZDB: create_memory(...)
    Service->>PG: UPDATE conversations<br/>SET message_count += 1
    Service-->>Bridge: Return response message

    Bridge->>WA: Send response to user
```

**Key Steps**:
1. User sends message via channel (WhatsApp, Telegram, etc.)
2. Bridge finds or creates conversation
3. User message persisted to ZeroDB (table + memory)
4. Conversation metadata updated in PostgreSQL
5. Message sent to agent for processing
6. Agent response persisted to ZeroDB
7. Response sent back to user via channel

---

## Component Architecture (System Diagram)

This diagram shows the high-level system architecture and data flow.

```mermaid
graph TB
    subgraph "External Channels"
        WA[WhatsApp]
        TG[Telegram]
        SL[Slack]
    end

    subgraph "OpenClaw Backend"
        Bridge[ProductionOpenClawBridge<br/>Message Router]
        API[FastAPI Endpoints<br/>/conversations/*]
        Service[ConversationService<br/>Business Logic]

        Bridge --> Service
        API --> Service
    end

    subgraph "Data Storage"
        PG[(PostgreSQL<br/>Conversation Metadata)]
        ZDB_T[(ZeroDB Table<br/>Message Rows)]
        ZDB_M[(ZeroDB Memory<br/>Vector Embeddings)]

        Service --> PG
        Service --> ZDB_T
        Service --> ZDB_M
    end

    subgraph "Agent Infrastructure"
        Gateway[OpenClaw Gateway<br/>DBOS Workflows]
        Agent[Claude Agent<br/>Message Processing]

        Bridge --> Gateway
        Gateway --> Agent
        Agent --> Gateway
    end

    WA --> Bridge
    TG --> Bridge
    SL --> Bridge

    Frontend[Frontend Application] --> API

    style Bridge fill:#e1f5ff
    style Service fill:#fff4e1
    style PG fill:#e8f5e9
    style ZDB_T fill:#f3e5f5
    style ZDB_M fill:#f3e5f5
```

**Component Responsibilities**:

- **ProductionOpenClawBridge**: Routes messages from channels to agents, manages conversation persistence
- **ConversationService**: Business logic for conversation and message management
- **FastAPI Endpoints**: REST API for frontend access
- **PostgreSQL**: Stores conversation metadata (workspace, user, agent, status, counts)
- **ZeroDB Table**: Stores message content for chronological retrieval
- **ZeroDB Memory**: Stores message embeddings for semantic search
- **OpenClaw Gateway**: DBOS-backed workflow orchestration
- **Claude Agent**: Processes messages with conversation context

---

## Dual Storage Architecture

This diagram explains the dual storage model for messages.

```mermaid
graph LR
    subgraph "Message Storage Strategy"
        Msg[New Message]

        Msg --> Store1[PostgreSQL<br/>Conversation Metadata]
        Msg --> Store2[ZeroDB Table<br/>Message Rows]
        Msg --> Store3[ZeroDB Memory<br/>Vector Embeddings]

        Store1 --> Meta[message_count<br/>last_message_at<br/>status]
        Store2 --> Pagination[Chronological<br/>Retrieval with<br/>Pagination]
        Store3 --> Search[Semantic<br/>Similarity<br/>Search]
    end

    subgraph "Query Patterns"
        Q1[List messages<br/>limit/offset] --> Store2
        Q2[Search messages<br/>by meaning] --> Store3
        Q3[Get conversation<br/>metadata] --> Store1
    end

    style Store1 fill:#e8f5e9
    style Store2 fill:#f3e5f5
    style Store3 fill:#fce4ec
```

**Storage Breakdown**:

| Storage | Purpose | Data | Query Type |
|---------|---------|------|------------|
| PostgreSQL | Metadata | workspace_id, user_id, agent_id, message_count, timestamps | Structured queries, filtering, joins |
| ZeroDB Table | Message rows | conversation_id, role, content, timestamp, metadata | Pagination (limit/offset), chronological order |
| ZeroDB Memory | Embeddings | Message content as vectors, conversation_id tags | Semantic similarity search |

**Why Dual Storage?**

1. **Performance**: PostgreSQL optimized for metadata queries, ZeroDB for message content
2. **Scalability**: ZeroDB handles high-volume message storage, PostgreSQL for relationships
3. **Flexibility**: Table for pagination, Memory for semantic search
4. **Reliability**: Graceful degradation if Memory API fails (table storage continues)

---

## Conversation Lifecycle State Machine

This diagram shows the conversation status transitions.

```mermaid
stateDiagram-v2
    [*] --> active: create_conversation()

    active --> active: add_message()
    active --> archived: archive_conversation()
    active --> deleted: delete_conversation()

    archived --> active: reactivate_conversation()
    archived --> deleted: delete_conversation()

    deleted --> [*]

    note right of active
        Messages can be added
        Agent can respond
        Visible in API lists
    end note

    note right of archived
        Messages preserved
        No new messages allowed
        Filterable (status=archived)
    end note

    note right of deleted
        Soft delete
        Messages preserved in ZeroDB
        Hidden from API lists
    end note
```

**Status Definitions**:

- **active**: Conversation is ongoing, messages can be added
- **archived**: Conversation is archived (user completed task, no longer active)
- **deleted**: Soft-deleted conversation (hidden from UI, data preserved for compliance)

**Allowed Transitions**:
- `active → archived`: User archives conversation
- `archived → active`: User reactivates conversation
- `active → deleted`: User or admin deletes conversation
- `archived → deleted`: User or admin deletes archived conversation

---

## Multi-Channel Routing

This diagram shows how messages from different channels are routed to conversations.

```mermaid
graph TB
    subgraph "Channel Messages"
        WA_MSG["WhatsApp Message<br/>+1234567890<br/>session_abc"]
        TG_MSG["Telegram Message<br/>@username<br/>chat_id_123"]
        SL_MSG["Slack Message<br/>channel_id<br/>thread_ts"]
    end

    subgraph "Bridge Processing"
        Bridge[ProductionOpenClawBridge]

        WA_MSG --> Bridge
        TG_MSG --> Bridge
        SL_MSG --> Bridge

        Bridge --> Extract[Extract Session Key]
        Extract --> SK1["whatsapp:+1234567890:session_abc"]
        Extract --> SK2["telegram:@username:chat_id_123"]
        Extract --> SK3["slack:channel_id:thread_ts"]
    end

    subgraph "Conversation Lookup"
        SK1 --> Lookup1[get_conversation_by_session_key]
        SK2 --> Lookup2[get_conversation_by_session_key]
        SK3 --> Lookup3[get_conversation_by_session_key]

        Lookup1 --> Conv1[Conversation 1<br/>channel=whatsapp<br/>channel_conversation_id=+1234567890]
        Lookup2 --> Conv2[Conversation 2<br/>channel=telegram<br/>channel_conversation_id=@username]
        Lookup3 --> Conv3[Conversation 3<br/>channel=slack<br/>channel_conversation_id=channel_id]
    end

    style WA_MSG fill:#e8f5e9
    style TG_MSG fill:#e3f2fd
    style SL_MSG fill:#fff9c4
    style Conv1 fill:#e8f5e9
    style Conv2 fill:#e3f2fd
    style Conv3 fill:#fff9c4
```

**Session Key Format**:
```
{channel}:{channel_identifier}:{session_id}
```

Examples:
- WhatsApp: `whatsapp:+1234567890:session_abc`
- Telegram: `telegram:@username:chat_id_123`
- Slack: `slack:channel_id:thread_ts`

**Unique Constraint**:
```sql
UNIQUE (channel, channel_conversation_id)
```

This prevents duplicate conversations for the same channel identifier.

---

## Context Loading Flow

This diagram shows how agents load conversation history for context.

```mermaid
sequenceDiagram
    participant Agent as Claude Agent
    participant API as Conversation API
    participant Service as ConversationService
    participant ZDB as ZeroDB Table
    participant LLM as Claude API

    Agent->>API: GET /conversations/{id}/context?limit=100
    API->>Service: get_conversation_context(id, limit=100)
    Service->>ZDB: query_table(table="messages",<br/>filters={conversation_id},<br/>limit=100, order_by="timestamp ASC")
    ZDB-->>Service: Return last 100 messages

    Service->>Service: Format as LLM-compatible<br/>array: [{role, content}, ...]
    Service-->>API: Return formatted context
    API-->>Agent: Return context response

    Note over Agent: Prepare prompt with context
    Agent->>LLM: POST /messages<br/>messages=[<br/>  {role: "system", content: "..."},<br/>  {role: "user", content: "..."},<br/>  {role: "assistant", content: "..."},<br/>  ...context...,<br/>  {role: "user", content: "new message"}<br/>]

    LLM-->>Agent: Return response
    Note over Agent: Agent has full context<br/>for coherent response
```

**Context Window Management**:

- **Default**: Load last 100 messages
- **Configurable**: `limit` parameter (1-1000)
- **Optimization**: Only load what fits in LLM context window
- **Caching**: Consider caching context for active conversations

**Example Context Response**:
```json
{
  "conversation_id": "123e4567...",
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "content": "Hi! How can I help?"},
    {"role": "user", "content": "What's the weather?"}
  ],
  "total_messages": 3,
  "agent_id": "456e4567...",
  "metadata": {"model": "claude-3-5-sonnet-20241022"}
}
```

---

## Semantic Search Flow

This diagram shows how semantic search works across conversation messages.

```mermaid
sequenceDiagram
    participant User as User/Frontend
    participant API as Conversation API
    participant Service as ConversationService
    participant ZDB_M as ZeroDB Memory API

    User->>API: POST /conversations/{id}/search<br/>{query: "machine learning", limit: 5}
    API->>Service: search_conversation_semantic(id, "machine learning", 5)

    Service->>ZDB_M: search_memories(<br/>query="machine learning",<br/>type="conversation",<br/>limit=5)

    Note over ZDB_M: Generate embedding<br/>for query<br/>(vector representation)
    Note over ZDB_M: Search similar vectors<br/>using cosine similarity

    ZDB_M-->>Service: Return all matches<br/>(including from other conversations)

    Note over Service: Filter results:<br/>Only include messages where<br/>metadata.conversation_id == id

    Service-->>API: Return filtered results<br/>[{content, score, metadata}]
    API-->>User: Return search results<br/>{results: [...], total: N, query: "..."}

    Note over User: Results sorted by<br/>relevance score (0.0-1.0)
```

**Semantic Search Features**:

- **Vector Embeddings**: Messages automatically embedded on creation
- **Similarity Search**: Find messages by meaning, not keywords
- **Conversation Filtering**: Results isolated to single conversation
- **Relevance Scoring**: Results ranked by similarity (0.0-1.0)

**Use Cases**:
- Find previous discussion on a topic
- Locate specific information from long conversations
- Context retrieval for agent reasoning
- User asks "What did we discuss about X?"

---

## Workspace Isolation Architecture

This diagram shows how workspace isolation is enforced.

```mermaid
graph TB
    subgraph "Workspace A"
        WS_A[Workspace A<br/>ID: aaa-111<br/>ZeroDB Project: proj_a]
        USER_A1[User A1]
        USER_A2[User A2]
        AGENT_A[Agent A]
        CONV_A1[Conversation A1]
        CONV_A2[Conversation A2]

        WS_A --> USER_A1
        WS_A --> USER_A2
        WS_A --> AGENT_A
        WS_A --> CONV_A1
        WS_A --> CONV_A2
        USER_A1 --> CONV_A1
        USER_A2 --> CONV_A2
        AGENT_A --> CONV_A1
        AGENT_A --> CONV_A2
    end

    subgraph "Workspace B"
        WS_B[Workspace B<br/>ID: bbb-222<br/>ZeroDB Project: proj_b]
        USER_B1[User B1]
        AGENT_B[Agent B]
        CONV_B1[Conversation B1]

        WS_B --> USER_B1
        WS_B --> AGENT_B
        WS_B --> CONV_B1
        USER_B1 --> CONV_B1
        AGENT_B --> CONV_B1
    end

    subgraph "ZeroDB Projects"
        PROJ_A[(Project A<br/>Messages for<br/>Workspace A)]
        PROJ_B[(Project B<br/>Messages for<br/>Workspace B)]
    end

    CONV_A1 -.->|"messages stored in"| PROJ_A
    CONV_A2 -.->|"messages stored in"| PROJ_A
    CONV_B1 -.->|"messages stored in"| PROJ_B

    style WS_A fill:#e8f5e9
    style WS_B fill:#e3f2fd
    style PROJ_A fill:#c8e6c9
    style PROJ_B fill:#bbdefb
```

**Isolation Guarantees**:

1. **Database Level**: All queries filter by `workspace_id`
2. **ZeroDB Level**: Each workspace has separate project
3. **Cascade Deletes**: Deleting workspace removes all child entities
4. **Foreign Key Constraints**: Enforce referential integrity

**Query Pattern**:
```python
# All queries must filter by workspace_id
conversations = await db.execute(
    select(Conversation)
    .where(Conversation.workspace_id == workspace_id)
)
```

---

## Performance Optimization Architecture

This diagram shows performance optimization strategies.

```mermaid
graph TB
    subgraph "Database Optimization"
        IDX1[Composite Index:<br/>channel + channel_conversation_id]
        IDX2[Index: workspace_id]
        IDX3[Index: user_id]
        IDX4[Index: agent_id]
        IDX5[Index: status]
    end

    subgraph "Connection Pooling"
        POOL[SQLAlchemy Pool<br/>Size: 20<br/>Max Overflow: 40<br/>Pool Recycle: 3600s]
    end

    subgraph "ZeroDB Optimization"
        PAG[Pagination<br/>limit=50 default<br/>max=200]
        CACHE[Result Caching<br/>TTL: 60s for<br/>active conversations]
    end

    subgraph "API Rate Limiting"
        LIMIT1[POST /messages:<br/>100/minute per IP]
        LIMIT2[POST /search:<br/>20/minute per IP]
        LIMIT3[Other endpoints:<br/>200/minute per IP]
    end

    Query[API Query] --> IDX1
    Query --> IDX2
    Query --> IDX3
    Query --> POOL
    Query --> PAG

    style POOL fill:#fff9c4
    style PAG fill:#e1f5ff
    style LIMIT1 fill:#ffcdd2
```

**Performance Targets**:

- **Message Retrieval**: < 200ms for 50 messages
- **Conversation List**: < 300ms for 50 conversations
- **Message Creation**: < 500ms end-to-end (WhatsApp → ZeroDB)
- **Semantic Search**: < 1000ms for 5 results

---

## Deployment Architecture

```mermaid
graph TB
    subgraph "Load Balancer"
        LB[Nginx/ALB]
    end

    subgraph "Application Servers"
        APP1[FastAPI Instance 1]
        APP2[FastAPI Instance 2]
        APP3[FastAPI Instance 3]
    end

    subgraph "Database Cluster"
        PG_PRIMARY[(PostgreSQL Primary)]
        PG_REPLICA[(PostgreSQL Replica)]
    end

    subgraph "External Services"
        ZDB[ZeroDB API<br/>api.zerodb.io]
        Gateway[OpenClaw Gateway<br/>DBOS Workflows]
    end

    LB --> APP1
    LB --> APP2
    LB --> APP3

    APP1 --> PG_PRIMARY
    APP2 --> PG_PRIMARY
    APP3 --> PG_PRIMARY

    APP1 -.->|"read-only queries"| PG_REPLICA
    APP2 -.->|"read-only queries"| PG_REPLICA
    APP3 -.->|"read-only queries"| PG_REPLICA

    APP1 --> ZDB
    APP2 --> ZDB
    APP3 --> ZDB

    APP1 --> Gateway
    APP2 --> Gateway
    APP3 --> Gateway

    style LB fill:#fff9c4
    style PG_PRIMARY fill:#e8f5e9
    style PG_REPLICA fill:#c8e6c9
    style ZDB fill:#f3e5f5
```

**Deployment Considerations**:

- **Horizontal Scaling**: Multiple FastAPI instances behind load balancer
- **Database Replication**: Read replicas for read-heavy workloads
- **Connection Pooling**: Shared connection pool across instances
- **Health Checks**: `/health` endpoint for load balancer probes
- **Graceful Shutdown**: Drain connections before instance termination

---

## Additional Resources

- **Main Documentation**: [docs/CHAT_PERSISTENCE.md](../CHAT_PERSISTENCE.md)
- **API Reference**: [docs/api/CONVERSATION_API.md](../api/CONVERSATION_API.md)
- **Troubleshooting**: [docs/CHAT_PERSISTENCE_TROUBLESHOOTING.md](../CHAT_PERSISTENCE_TROUBLESHOOTING.md)

---

**Document Version**: 1.0
**Last Updated**: 2026-03-08
