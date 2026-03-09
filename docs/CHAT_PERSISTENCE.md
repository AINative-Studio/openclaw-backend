# Chat Persistence Documentation

**Epic E9 - Chat Persistence**
**Version:** 1.0
**Last Updated:** 2026-03-08

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Data Models](#data-models)
4. [Setup Instructions](#setup-instructions)
5. [API Reference](#api-reference)
6. [Usage Examples](#usage-examples)
7. [Troubleshooting](#troubleshooting)
8. [Migration Guide](#migration-guide)
9. [Performance Optimization](#performance-optimization)
10. [Security Considerations](#security-considerations)

---

## Overview

### What is Chat Persistence?

Chat Persistence is a comprehensive conversation management system that enables OpenClaw agents to maintain continuous, context-aware conversations across multiple channels (WhatsApp, Telegram, Slack, etc.). The system provides:

- **Persistent Conversation History**: All messages are stored and retrievable for context continuity
- **Multi-Channel Support**: Unified conversation model across WhatsApp, Telegram, Slack, and other channels
- **Dual Storage Architecture**: PostgreSQL for metadata, ZeroDB for message content and semantic search
- **Agent Context Loading**: Agents automatically load conversation history for contextual responses
- **Workspace Isolation**: Complete data isolation at the workspace level
- **Scalable Design**: Optimized for high-throughput concurrent conversations

### Key Benefits

1. **Context Continuity**: Agents remember previous interactions across sessions
2. **Multi-Channel Conversations**: Users can switch channels while maintaining context
3. **Semantic Search**: Find relevant messages using natural language queries
4. **Workspace Isolation**: Multi-tenant architecture with secure data separation
5. **Performance**: Sub-200ms message retrieval with pagination support
6. **Reliability**: Graceful degradation on ZeroDB failures, retry mechanisms

---

## Architecture

### System Overview

The Chat Persistence system uses a **dual-storage architecture** optimized for both structured queries and semantic search:

```
┌─────────────────┐
│  WhatsApp/Slack │
│   Telegram, etc │
└────────┬────────┘
         │
         ▼
┌────────────────────────┐
│ ProductionOpenClawBridge│
│ (Message Router)        │
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ ConversationService     │
│ (Business Logic)        │
└──┬──────────────────┬──┘
   │                  │
   ▼                  ▼
┌──────────┐    ┌──────────┐
│PostgreSQL│    │  ZeroDB  │
│(Metadata)│    │(Messages)│
└──────────┘    └──────────┘
   │                  │
   │                  ├─ Table Storage (Pagination)
   │                  └─ Memory API (Semantic Search)
   │
   ▼
┌─────────────────────────┐
│  FastAPI Endpoints      │
│  (REST API)             │
└─────────────────────────┘
```

### Database Schema

```
┌──────────────┐
│  Workspace   │
│              │
│  id (PK)     │
│  name        │
│  slug        │
│  zerodb_     │
│  project_id  │
└──────┬───────┘
       │
       │ 1:N
       │
┌──────▼───────┐     ┌──────────────────┐
│    User      │     │AgentSwarmInstance│
│              │     │                  │
│  id (PK)     │     │  id (PK)         │
│  email       │     │  name            │
│  workspace_id│     │  persona         │
│  full_name   │     │  model           │
└──────┬───────┘     │  status          │
       │             │  workspace_id    │
       │             └────────┬─────────┘
       │                      │
       │ 1:N                  │ 1:N
       │                      │
┌──────▼──────────────────────▼────┐
│         Conversation              │
│                                   │
│  id (PK)                          │
│  workspace_id (FK)                │
│  user_id (FK)                     │
│  agent_swarm_instance_id (FK)     │
│  channel (whatsapp/telegram/etc)  │
│  channel_conversation_id          │
│  title                            │
│  conversation_metadata (JSON)     │
│  status (active/archived/deleted) │
│  created_at                       │
│  updated_at                       │
│  archived_at                      │
│                                   │
│  UNIQUE(channel, channel_         │
│         conversation_id)          │
└───────────────────────────────────┘
         │
         │ Messages stored in ZeroDB
         │
         ▼
┌─────────────────────────┐
│  ZeroDB Table: messages │
│                         │
│  id                     │
│  conversation_id        │
│  role                   │
│  content                │
│  timestamp              │
│  metadata               │
└─────────────────────────┘
```

### Dual Storage Model

#### PostgreSQL (Conversation Metadata)
- **Purpose**: Store conversation metadata and relationships
- **Data**: workspace_id, user_id, agent_id, status, message_count, timestamps
- **Performance**: Indexed queries for listing and filtering conversations
- **Consistency**: ACID guarantees for metadata integrity

#### ZeroDB Table Storage (Message Pagination)
- **Purpose**: Store message content for chronological retrieval
- **Data**: conversation_id, role, content, timestamp, metadata
- **Performance**: Paginated queries (limit/offset) for message history
- **Use Case**: Load last N messages for agent context

#### ZeroDB Memory API (Semantic Search)
- **Purpose**: Vector embeddings for semantic similarity search
- **Data**: Message content with conversation_id tags
- **Performance**: Sub-second similarity search across conversations
- **Use Case**: Find relevant past messages by meaning

### Component Interactions

#### Message Flow (WhatsApp → ZeroDB)

1. **User sends WhatsApp message** → Received by WhatsApp Bridge
2. **Bridge calls `ProductionOpenClawBridge.send_to_agent()`**
   - Extracts `session_key` (e.g., `whatsapp:+1234567890:session_abc`)
   - Identifies user_id, workspace_id, agent_id
3. **Bridge finds or creates conversation**
   - Calls `ConversationService.get_conversation_by_session_key()`
   - If not found, creates new conversation with `create_conversation()`
4. **User message persisted**
   - `ConversationService.add_message(conversation_id, role="user", content="...")`
   - Stores in ZeroDB table row (required)
   - Stores in ZeroDB Memory API (optional, graceful degradation)
5. **Message sent to agent via OpenClaw Gateway**
   - Agent processes with conversation context
6. **Agent response received**
   - Persisted via `add_message(role="assistant", content="...")`
7. **Conversation metadata updated**
   - `message_count` incremented
   - `last_message_at` timestamp updated
8. **Response sent back to user via WhatsApp**

#### Context Loading Flow (Agent Reads History)

1. **Agent receives new message**
2. **Agent calls `GET /conversations/{id}/context`**
3. **ConversationService.get_conversation_context()**
   - Loads last 100 messages (configurable) from ZeroDB table
   - Formats as LLM-compatible message array
4. **Agent uses context in prompt**
   - Includes conversation history in system prompt
   - Maintains continuity across turns

---

## Data Models

### User Model

**File**: `backend/models/user.py`

```python
class User(Base):
    __tablename__ = "users"

    # Primary identification
    id = Column(UUID(), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(255), nullable=True)

    # Workspace relationship
    workspace_id = Column(UUID(), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Status
    is_active = Column(Boolean, default=True, nullable=False)

    # Relationships
    workspace = relationship("Workspace", back_populates="users")
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
```

**Key Features**:
- Unique email constraint
- Workspace-level isolation (CASCADE delete)
- Active/inactive status flag
- One-to-many relationship with conversations

---

### Conversation Model

**File**: `backend/models/conversation.py`

```python
class ConversationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"

class Conversation(Base):
    __tablename__ = "conversations"

    # Primary identification
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)

    # Foreign keys
    workspace_id = Column(UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_swarm_instance_id = Column(UUID(as_uuid=True), ForeignKey("agent_swarm_instances.id", ondelete="SET NULL"), nullable=True, index=True)

    # Channel identification
    channel = Column(String(50), nullable=False)  # "whatsapp", "telegram", "slack"
    channel_conversation_id = Column(String(255), nullable=False)

    # Metadata
    title = Column(String(500), nullable=True)
    conversation_metadata = Column(JSON, default=dict, nullable=False)

    # Status
    status = Column(SQLEnum(ConversationStatus), default=ConversationStatus.ACTIVE, nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    archived_at = Column(DateTime(timezone=True), nullable=True)

    # Unique constraint on (channel, channel_conversation_id)
    __table_args__ = (
        Index('ix_conversations_channel_conversation_id', 'channel', 'channel_conversation_id', unique=True),
    )
```

**Key Features**:
- Multi-channel support (channel + channel_conversation_id)
- Unique constraint prevents duplicate conversations per channel
- Nullable agent (conversations can exist before agent assignment)
- JSON metadata field for channel-specific data
- Archival workflow with `archived_at` timestamp

---

### Message Storage (ZeroDB)

Messages are stored in ZeroDB with the following structure:

```json
{
  "id": "msg_abc123",
  "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
  "role": "user",
  "content": "Hello, how can you help?",
  "timestamp": "2024-01-15T10:00:00Z",
  "metadata": {
    "source": "whatsapp",
    "phone": "+1234567890",
    "model": "claude-3-5-sonnet-20241022",
    "tokens_used": 120
  }
}
```

**Fields**:
- `id`: ZeroDB-generated unique identifier
- `conversation_id`: UUID linking to PostgreSQL conversation
- `role`: One of `user`, `assistant`, `system`
- `content`: Message text content
- `timestamp`: ISO 8601 timestamp (UTC)
- `metadata`: Flexible JSON object for channel/model-specific data

---

## Setup Instructions

### Prerequisites

1. **PostgreSQL Database**
   - Version: 12+ (14+ recommended)
   - Running on Railway or local instance
   - Connection string format: `postgresql://user:pass@host:port/dbname`

2. **ZeroDB Account**
   - Sign up at [zerodb.io](https://zerodb.io) (or your ZeroDB provider)
   - Obtain API key
   - Create project for your workspace

3. **Python Environment**
   - Python 3.10+
   - Virtual environment recommended

### Environment Variables

Add the following to your `.env` file:

```bash
# PostgreSQL Database
DATABASE_URL=postgresql://user:password@localhost:5432/openclaw_backend

# ZeroDB Configuration
ZERODB_API_KEY=your_zerodb_api_key_here

# OpenClaw Gateway
OPENCLAW_GATEWAY_URL=ws://localhost:18789
OPENCLAW_GATEWAY_TOKEN=your_gateway_token

# Application Settings
ENVIRONMENT=production
SECRET_KEY=your_secret_key_for_jwt_signing
```

### Database Migrations

Run Alembic migrations to create the necessary tables:

```bash
# Activate virtual environment
source venv/bin/activate

# Run all pending migrations
alembic upgrade head
```

**Migrations Applied**:
1. `add_user_model` - Creates `users` table
2. `add_conversation_model` - Creates `conversations` table with relationships
3. `update_conversation_model_for_issue_103` - Adds multi-channel support
4. `add_current_conversation_id_to_agent` - Adds conversation linking to agents

### ZeroDB Project Provisioning

Each workspace must have a ZeroDB project configured:

```python
from backend.integrations.zerodb_client import ZeroDBClient
from backend.models.workspace import Workspace
from sqlalchemy.ext.asyncio import AsyncSession

async def provision_zerodb_for_workspace(workspace_id: UUID, db: AsyncSession):
    """
    Provision ZeroDB project for a workspace.

    Args:
        workspace_id: Workspace UUID
        db: Database session
    """
    # Initialize ZeroDB client
    async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
        # Create project
        project = await zerodb.create_project(
            name=f"workspace_{workspace_id}",
            description="OpenClaw workspace conversation storage"
        )

        # Update workspace with project ID
        workspace = await db.get(Workspace, workspace_id)
        workspace.zerodb_project_id = project["id"]
        await db.commit()

        print(f"✓ Provisioned ZeroDB project {project['id']} for workspace {workspace_id}")
```

**Automated Provisioning**:
For production, add ZeroDB provisioning to your workspace creation flow in `backend/services/workspace_service.py`.

### Testing the Setup

Verify your setup with this test script:

```python
import asyncio
from uuid import uuid4
from backend.db.base import get_async_db
from backend.services.conversation_service import ConversationService
from backend.integrations.zerodb_client import ZeroDBClient

async def test_chat_persistence():
    """Test basic chat persistence functionality."""

    # Get database session
    async for db in get_async_db():
        # Initialize ZeroDB client
        async with ZeroDBClient(api_key=os.getenv("ZERODB_API_KEY")) as zerodb:
            # Initialize service
            service = ConversationService(db=db, zerodb_client=zerodb)

            # Create test conversation
            conversation = await service.create_conversation(
                workspace_id=uuid4(),  # Replace with real workspace ID
                agent_id=uuid4(),      # Replace with real agent ID
                user_id=uuid4()        # Replace with real user ID
            )

            print(f"✓ Created conversation: {conversation.id}")

            # Add test message
            message = await service.add_message(
                conversation_id=conversation.id,
                role="user",
                content="Hello, this is a test message!"
            )

            print(f"✓ Added message: {message['id']}")

            # Retrieve messages
            messages = await service.get_messages(conversation.id, limit=10)

            print(f"✓ Retrieved {len(messages)} messages")
            print("Setup test successful!")

        break

# Run test
asyncio.run(test_chat_persistence())
```

Expected output:
```
✓ Created conversation: 123e4567-e89b-12d3-a456-426614174000
✓ Added message: msg_abc123
✓ Retrieved 1 messages
Setup test successful!
```

---

## API Reference

See [docs/api/CONVERSATION_API.md](api/CONVERSATION_API.md) for detailed API reference with curl examples.

### Quick Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/conversations` | List conversations with filters and pagination |
| POST | `/conversations` | Create a new conversation |
| GET | `/conversations/{id}` | Get a single conversation by ID |
| GET | `/conversations/{id}/messages` | Get messages from a conversation |
| POST | `/conversations/{id}/messages` | Add a message to a conversation |
| POST | `/conversations/{id}/search` | Semantic search within a conversation |
| POST | `/conversations/{id}/archive` | Archive a conversation |
| GET | `/conversations/{id}/context` | Get conversation context for LLM |
| POST | `/conversations/{id}/attach-agent` | Attach/replace agent for conversation |

### Common Response Codes

- `200 OK` - Successful GET request
- `201 Created` - Successful POST creation
- `404 Not Found` - Conversation or resource not found
- `422 Unprocessable Entity` - Validation error (check request body)
- `500 Internal Server Error` - Server error (check logs)
- `503 Service Unavailable` - ZeroDB connection issue

---

## Usage Examples

### Creating a Conversation

```python
from backend.services.conversation_service import ConversationService

async def create_conversation_example(db, zerodb_client):
    service = ConversationService(db=db, zerodb_client=zerodb_client)

    conversation = await service.create_conversation(
        workspace_id=UUID("789e4567-e89b-12d3-a456-426614174111"),
        agent_id=UUID("456e4567-e89b-12d3-a456-426614174222"),
        user_id=UUID("987e4567-e89b-12d3-a456-426614174333")
    )

    print(f"Created conversation: {conversation.id}")
    print(f"Status: {conversation.status}")
    print(f"Message count: {conversation.message_count}")
```

### Adding Messages to Conversation

```python
async def add_messages_example(db, zerodb_client, conversation_id):
    service = ConversationService(db=db, zerodb_client=zerodb_client)

    # Add user message
    user_msg = await service.add_message(
        conversation_id=conversation_id,
        role="user",
        content="What's the weather like today?",
        metadata={
            "source": "whatsapp",
            "phone": "+1234567890"
        }
    )

    # Add assistant response
    assistant_msg = await service.add_message(
        conversation_id=conversation_id,
        role="assistant",
        content="I don't have access to real-time weather data, but I can help you find weather information.",
        metadata={
            "model": "claude-3-5-sonnet-20241022",
            "tokens_used": 35,
            "latency_ms": 1200
        }
    )

    print(f"User message ID: {user_msg['id']}")
    print(f"Assistant message ID: {assistant_msg['id']}")
```

### Retrieving Conversation History

```python
async def retrieve_messages_example(db, zerodb_client, conversation_id):
    service = ConversationService(db=db, zerodb_client=zerodb_client)

    # Get last 50 messages
    messages = await service.get_messages(
        conversation_id=conversation_id,
        limit=50,
        offset=0
    )

    for msg in messages:
        print(f"[{msg['role']}] {msg['content'][:50]}...")
        print(f"  Timestamp: {msg['timestamp']}")
```

### Archiving Conversations

```python
async def archive_conversation_example(db, zerodb_client, conversation_id):
    service = ConversationService(db=db, zerodb_client=zerodb_client)

    # Archive conversation (idempotent)
    conversation = await service.archive_conversation(conversation_id)

    print(f"Conversation status: {conversation.status}")
    print(f"Archived at: {conversation.archived_at}")

    # Messages still retrievable
    messages = await service.get_messages(conversation_id, limit=10)
    print(f"Messages still accessible: {len(messages)}")
```

### Attaching Agents to Conversations

```python
async def attach_agent_example(db, conversation_id, new_agent_id):
    from sqlalchemy import select
    from backend.models.conversation import Conversation

    # Update conversation agent
    stmt = select(Conversation).where(Conversation.id == conversation_id)
    result = await db.execute(stmt)
    conversation = result.scalar_one()

    old_agent_id = conversation.agent_swarm_instance_id
    conversation.agent_swarm_instance_id = new_agent_id
    await db.commit()

    print(f"Switched agent from {old_agent_id} to {new_agent_id}")
```

### Getting Conversation Context for LLM

```python
async def get_context_for_llm(db, zerodb_client, conversation_id):
    service = ConversationService(db=db, zerodb_client=zerodb_client)

    # Get last 100 messages formatted for LLM
    context = await service.get_conversation_context(
        conversation_id=conversation_id,
        limit=100
    )

    # Use in LLM API call
    messages_for_llm = context["messages"]
    # messages_for_llm is ready to use in Claude API call

    print(f"Loaded {len(messages_for_llm)} messages for context")
    print(f"Total messages in conversation: {context['total_messages']}")
```

### Semantic Search in Conversation

```python
async def semantic_search_example(db, zerodb_client, conversation_id):
    service = ConversationService(db=db, zerodb_client=zerodb_client)

    # Search for relevant messages
    results = await service.search_conversation_semantic(
        conversation_id=conversation_id,
        query="machine learning concepts",
        limit=5
    )

    print(f"Found {results['total']} relevant messages:")
    for result in results['results']:
        print(f"  Score: {result.get('score', 0):.2f}")
        print(f"  Content: {result['content'][:80]}...")
```

---

## Troubleshooting

See [docs/CHAT_PERSISTENCE_TROUBLESHOOTING.md](CHAT_PERSISTENCE_TROUBLESHOOTING.md) for detailed troubleshooting guide.

### Quick Fixes

**"Conversation not found" (404 error)**
```bash
# Verify conversation exists
psql $DATABASE_URL -c "SELECT id, status FROM conversations WHERE id = 'your-uuid-here';"

# Check if it was deleted
psql $DATABASE_URL -c "SELECT id, status, archived_at FROM conversations WHERE status = 'deleted';"
```

**ZeroDB connection timeout**
```bash
# Test ZeroDB connection
curl -H "Authorization: Bearer $ZERODB_API_KEY" https://api.zerodb.io/v1/health

# Check workspace has project configured
psql $DATABASE_URL -c "SELECT id, name, zerodb_project_id FROM workspaces WHERE zerodb_project_id IS NULL;"
```

**Migration conflicts**
```bash
# Check current migration version
alembic current

# Rollback one migration
alembic downgrade -1

# Re-run migrations
alembic upgrade head
```

---

## Migration Guide

See [docs/CHAT_PERSISTENCE_MIGRATION.md](CHAT_PERSISTENCE_MIGRATION.md) for complete migration guide.

### Quick Start

**Pre-migration Checklist**:
- [ ] Backup PostgreSQL database
- [ ] Export existing conversation data (if any)
- [ ] Verify ZeroDB account and API key
- [ ] Test migrations on staging environment

**Run Migrations**:
```bash
# Backup database
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Run migrations
alembic upgrade head

# Verify tables created
psql $DATABASE_URL -c "\dt"
```

**Post-migration Validation**:
```bash
# Check users table
psql $DATABASE_URL -c "SELECT COUNT(*) FROM users;"

# Check conversations table
psql $DATABASE_URL -c "SELECT COUNT(*) FROM conversations;"

# Test conversation creation
python scripts/test_chat_persistence.py
```

---

## Performance Optimization

### Database Indexing

Ensure indexes exist for common queries:

```sql
-- Conversation lookups by workspace/agent/user
CREATE INDEX IF NOT EXISTS idx_conversations_workspace_id ON conversations(workspace_id);
CREATE INDEX IF NOT EXISTS idx_conversations_agent_id ON conversations(agent_swarm_instance_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);

-- User lookups by email
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_workspace_id ON users(workspace_id);

-- Composite index for channel uniqueness (already created by model)
CREATE UNIQUE INDEX IF NOT EXISTS ix_conversations_channel_conversation_id
ON conversations(channel, channel_conversation_id);
```

### ZeroDB Query Optimization

**Use pagination for large conversations**:
```python
# Good: Paginate messages
messages = await service.get_messages(conversation_id, limit=50, offset=0)

# Bad: Load all messages at once
messages = await service.get_messages(conversation_id, limit=10000, offset=0)
```

**Limit context window for LLM**:
```python
# Load only last 100 messages (reduces memory and improves performance)
context = await service.get_conversation_context(conversation_id, limit=100)
```

### Connection Pooling

Configure SQLAlchemy connection pool for high concurrency:

```python
# In backend/db/base.py
engine = create_async_engine(
    DATABASE_URL,
    pool_size=20,          # Increase for high concurrency
    max_overflow=40,       # Allow burst connections
    pool_pre_ping=True,    # Verify connections before use
    pool_recycle=3600      # Recycle connections every hour
)
```

### Caching

Consider caching frequently accessed conversations:

```python
from functools import lru_cache

@lru_cache(maxsize=1000)
def get_conversation_metadata(conversation_id: str):
    """Cache conversation metadata (workspace_id, agent_id, etc.)"""
    # Fetch from database
    pass
```

---

## Security Considerations

### Data Isolation

**Workspace-level isolation**:
- All queries filter by `workspace_id`
- PostgreSQL CASCADE deletes ensure cleanup
- ZeroDB projects are workspace-specific

**User authentication**:
- Verify user has access to workspace before conversation operations
- Check `user.workspace_id == conversation.workspace_id`

### Sensitive Data

**Do not store in conversation metadata**:
- API keys
- Passwords
- Credit card numbers
- PII (unless required and encrypted)

**Use metadata for**:
- Channel-specific IDs (WhatsApp phone number)
- Message source (whatsapp, telegram)
- Non-sensitive configuration

### Rate Limiting

Implement rate limits to prevent abuse:

```python
# In FastAPI endpoints
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

@app.post("/conversations/{conversation_id}/messages")
@limiter.limit("100/minute")
async def add_message(conversation_id: UUID, request: AddMessageRequest):
    # Limit to 100 messages per minute per IP
    pass
```

### Input Validation

**Always validate**:
- UUIDs are valid format
- Message content is not empty
- Role is one of: user, assistant, system
- Metadata is valid JSON (< 10KB)

```python
from pydantic import Field, validator

class AddMessageRequest(BaseModel):
    role: str = Field(..., regex="^(user|assistant|system)$")
    content: str = Field(..., min_length=1, max_length=100000)

    @validator('metadata')
    def validate_metadata_size(cls, v):
        if len(json.dumps(v)) > 10240:  # 10KB limit
            raise ValueError("Metadata too large")
        return v
```

---

## Additional Resources

- **API Reference**: [docs/api/CONVERSATION_API.md](api/CONVERSATION_API.md)
- **Architecture Diagrams**: [docs/diagrams/chat-persistence-architecture.md](diagrams/chat-persistence-architecture.md)
- **Troubleshooting Guide**: [docs/CHAT_PERSISTENCE_TROUBLESHOOTING.md](CHAT_PERSISTENCE_TROUBLESHOOTING.md)
- **Migration Guide**: [docs/CHAT_PERSISTENCE_MIGRATION.md](CHAT_PERSISTENCE_MIGRATION.md)
- **Integration Tests**: [tests/integration/test_chat_persistence_e2e.py](../tests/integration/test_chat_persistence_e2e.py)
- **Test Summary**: [tests/integration/TEST_SUMMARY_E2E_CHAT_PERSISTENCE.md](../tests/integration/TEST_SUMMARY_E2E_CHAT_PERSISTENCE.md)

---

## Support

For issues or questions:

1. Check [Troubleshooting Guide](CHAT_PERSISTENCE_TROUBLESHOOTING.md)
2. Review [Integration Tests](../tests/integration/test_chat_persistence_e2e.py) for examples
3. Contact engineering team

---

**Document Version**: 1.0
**Last Updated**: 2026-03-08
**Maintained By**: AINative Studio Engineering Team
