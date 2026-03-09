# Conversation API Reference

**Version:** 1.0
**Base URL:** `http://localhost:8000` (development) or `https://api.openclaw.io` (production)
**Authentication:** Bearer token (if enabled)

---

## Table of Contents

1. [List Conversations](#list-conversations)
2. [Create Conversation](#create-conversation)
3. [Get Conversation](#get-conversation)
4. [Get Conversation Messages](#get-conversation-messages)
5. [Add Message](#add-message)
6. [Search Conversation](#search-conversation)
7. [Archive Conversation](#archive-conversation)
8. [Get Conversation Context](#get-conversation-context)
9. [Attach Agent to Conversation](#attach-agent-to-conversation)

---

## List Conversations

Retrieve a paginated list of conversations with optional filters.

### Endpoint

```
GET /conversations
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `agent_id` | UUID | No | - | Filter by agent ID |
| `workspace_id` | UUID | No | - | Filter by workspace ID |
| `status` | string | No | - | Filter by status (active, archived, deleted) |
| `limit` | integer | No | 50 | Results per page (1-200) |
| `offset` | integer | No | 0 | Results to skip for pagination |

### Request Example

```bash
curl -X GET "http://localhost:8000/conversations?workspace_id=789e4567-e89b-12d3-a456-426614174111&limit=10&offset=0" \
  -H "Content-Type: application/json"
```

### Response Example

```json
{
  "conversations": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
      "agent_id": "456e4567-e89b-12d3-a456-426614174222",
      "user_id": "987e4567-e89b-12d3-a456-426614174333",
      "openclaw_session_key": "whatsapp:+1234567890:session_abc",
      "started_at": "2024-01-15T10:00:00Z",
      "last_message_at": "2024-01-15T10:30:00Z",
      "message_count": 5,
      "status": "active"
    }
  ],
  "total": 1,
  "limit": 10,
  "offset": 0
}
```

### Response Codes

- `200 OK` - Success
- `422 Unprocessable Entity` - Invalid query parameters

---

## Create Conversation

Create a new conversation.

### Endpoint

```
POST /conversations
```

### Request Body

```json
{
  "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
  "agent_id": "456e4567-e89b-12d3-a456-426614174222",
  "user_id": "987e4567-e89b-12d3-a456-426614174333"
}
```

### Request Example

```bash
curl -X POST "http://localhost:8000/conversations" \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
    "agent_id": "456e4567-e89b-12d3-a456-426614174222",
    "user_id": "987e4567-e89b-12d3-a456-426614174333"
  }'
```

### Response Example

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
  "agent_id": "456e4567-e89b-12d3-a456-426614174222",
  "user_id": "987e4567-e89b-12d3-a456-426614174333",
  "openclaw_session_key": null,
  "started_at": "2024-01-15T10:00:00Z",
  "last_message_at": null,
  "message_count": 0,
  "status": "active"
}
```

### Response Codes

- `201 Created` - Conversation created successfully
- `400 Bad Request` - Invalid workspace or agent ID
- `422 Unprocessable Entity` - Validation error

---

## Get Conversation

Retrieve a single conversation by ID.

### Endpoint

```
GET /conversations/{conversation_id}
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation UUID |

### Request Example

```bash
curl -X GET "http://localhost:8000/conversations/123e4567-e89b-12d3-a456-426614174000" \
  -H "Content-Type: application/json"
```

### Response Example

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
  "agent_id": "456e4567-e89b-12d3-a456-426614174222",
  "user_id": "987e4567-e89b-12d3-a456-426614174333",
  "openclaw_session_key": "whatsapp:+1234567890:session_abc",
  "started_at": "2024-01-15T10:00:00Z",
  "last_message_at": "2024-01-15T10:30:00Z",
  "message_count": 5,
  "status": "active"
}
```

### Response Codes

- `200 OK` - Success
- `404 Not Found` - Conversation not found
- `422 Unprocessable Entity` - Invalid UUID format

---

## Get Conversation Messages

Retrieve paginated messages from a conversation.

### Endpoint

```
GET /conversations/{conversation_id}/messages
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Messages per page (1-200) |
| `offset` | integer | No | 0 | Messages to skip for pagination |

### Request Example

```bash
curl -X GET "http://localhost:8000/conversations/123e4567-e89b-12d3-a456-426614174000/messages?limit=20&offset=0" \
  -H "Content-Type: application/json"
```

### Response Example

```json
{
  "messages": [
    {
      "role": "user",
      "content": "Hello, AI!",
      "timestamp": "2024-01-15T10:00:00Z",
      "metadata": {
        "source": "whatsapp",
        "phone": "+1234567890"
      }
    },
    {
      "role": "assistant",
      "content": "Hello! How can I help you today?",
      "timestamp": "2024-01-15T10:00:05Z",
      "metadata": {
        "model": "claude-3-5-sonnet-20241022",
        "tokens_used": 35,
        "latency_ms": 1200
      }
    }
  ],
  "total": 2
}
```

### Response Codes

- `200 OK` - Success
- `404 Not Found` - Conversation not found
- `422 Unprocessable Entity` - Invalid parameters

---

## Add Message

Add a message to a conversation.

### Endpoint

```
POST /conversations/{conversation_id}/messages
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation UUID |

### Request Body

```json
{
  "role": "user",
  "content": "What's the weather like today?",
  "metadata": {
    "source": "whatsapp",
    "phone": "+1234567890"
  }
}
```

### Request Example

```bash
curl -X POST "http://localhost:8000/conversations/123e4567-e89b-12d3-a456-426614174000/messages" \
  -H "Content-Type: application/json" \
  -d '{
    "role": "user",
    "content": "What is the weather like today?",
    "metadata": {
      "source": "whatsapp",
      "phone": "+1234567890"
    }
  }'
```

### Response Example

```json
{
  "role": "user",
  "content": "What's the weather like today?",
  "timestamp": "2024-01-15T10:05:00Z",
  "metadata": {
    "source": "whatsapp",
    "phone": "+1234567890"
  }
}
```

### Response Codes

- `201 Created` - Message added successfully
- `404 Not Found` - Conversation not found
- `422 Unprocessable Entity` - Invalid request body

### Notes

- Messages are stored in both ZeroDB table (for pagination) and Memory API (for semantic search)
- If Memory API storage fails, the message is still persisted to the table (graceful degradation)
- `message_count` and `last_message_at` are automatically updated

---

## Search Conversation

Perform semantic search within a conversation.

### Endpoint

```
POST /conversations/{conversation_id}/search
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation UUID |

### Request Body

```json
{
  "query": "machine learning concepts",
  "limit": 5
}
```

### Request Example

```bash
curl -X POST "http://localhost:8000/conversations/123e4567-e89b-12d3-a456-426614174000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "machine learning concepts",
    "limit": 5
  }'
```

### Response Example

```json
{
  "results": {
    "results": [
      {
        "id": "mem_abc123",
        "content": "Machine learning is a subset of AI that enables systems to learn from data...",
        "score": 0.95,
        "metadata": {
          "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
          "role": "assistant",
          "timestamp": "2024-01-15T10:00:00Z"
        }
      }
    ],
    "total": 1,
    "query": "machine learning concepts"
  }
}
```

### Response Codes

- `200 OK` - Success
- `404 Not Found` - Conversation not found
- `422 Unprocessable Entity` - Invalid query
- `503 Service Unavailable` - ZeroDB Memory API unavailable

### Notes

- Semantic search uses ZeroDB Memory API (vector embeddings)
- Results are filtered to only include messages from the specified conversation
- Scores range from 0.0 (no match) to 1.0 (perfect match)
- If Memory API was unavailable during message creation, search may return incomplete results

---

## Archive Conversation

Archive a conversation (idempotent operation).

### Endpoint

```
POST /conversations/{conversation_id}/archive
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation UUID |

### Request Example

```bash
curl -X POST "http://localhost:8000/conversations/123e4567-e89b-12d3-a456-426614174000/archive" \
  -H "Content-Type: application/json"
```

### Response Example

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
  "agent_id": "456e4567-e89b-12d3-a456-426614174222",
  "user_id": "987e4567-e89b-12d3-a456-426614174333",
  "openclaw_session_key": "whatsapp:+1234567890:session_abc",
  "started_at": "2024-01-15T10:00:00Z",
  "last_message_at": "2024-01-15T10:30:00Z",
  "message_count": 5,
  "status": "archived"
}
```

### Response Codes

- `200 OK` - Success (conversation archived or already archived)
- `404 Not Found` - Conversation not found

### Notes

- Archiving is idempotent (archiving an already archived conversation succeeds)
- Messages remain accessible after archival
- Archived conversations can be filtered using `GET /conversations?status=archived`
- `archived_at` timestamp is set when conversation is archived

---

## Get Conversation Context

Get conversation context formatted for LLM consumption.

### Endpoint

```
GET /conversations/{conversation_id}/context
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation UUID |

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 100 | Maximum messages to include (1-1000) |

### Request Example

```bash
curl -X GET "http://localhost:8000/conversations/123e4567-e89b-12d3-a456-426614174000/context?limit=50" \
  -H "Content-Type: application/json"
```

### Response Example

```json
{
  "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
  "messages": [
    {
      "role": "user",
      "content": "Hello, AI!"
    },
    {
      "role": "assistant",
      "content": "Hello! How can I help you today?"
    }
  ],
  "total_messages": 2,
  "agent_id": "456e4567-e89b-12d3-a456-426614174222",
  "metadata": {
    "model": "claude-3-5-sonnet-20241022"
  }
}
```

### Response Codes

- `200 OK` - Success
- `404 Not Found` - Conversation not found
- `422 Unprocessable Entity` - Invalid limit parameter

### Notes

- Returns messages in LLM-compatible format (array of `{role, content}` objects)
- Includes last N messages (default 100, configurable via `limit`)
- Use this endpoint when preparing context for Claude API calls
- Messages are sorted chronologically (oldest to newest)

---

## Attach Agent to Conversation

Attach or replace the agent assigned to a conversation.

### Endpoint

```
POST /conversations/{conversation_id}/attach-agent
```

### Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation UUID |

### Request Body

```json
{
  "agent_id": "456e4567-e89b-12d3-a456-426614174222"
}
```

### Request Example

```bash
curl -X POST "http://localhost:8000/conversations/123e4567-e89b-12d3-a456-426614174000/attach-agent" \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "456e4567-e89b-12d3-a456-426614174222"
  }'
```

### Response Example

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "workspace_id": "789e4567-e89b-12d3-a456-426614174111",
  "agent_id": "456e4567-e89b-12d3-a456-426614174222",
  "user_id": "987e4567-e89b-12d3-a456-426614174333",
  "openclaw_session_key": "whatsapp:+1234567890:session_abc",
  "started_at": "2024-01-15T10:00:00Z",
  "last_message_at": "2024-01-15T10:30:00Z",
  "message_count": 5,
  "status": "active"
}
```

### Response Codes

- `200 OK` - Agent attached successfully
- `404 Not Found` - Conversation not found
- `422 Unprocessable Entity` - Invalid agent ID

### Notes

- Use this endpoint to reassign conversations to different agents
- Useful for agent switching (e.g., from general to specialist agent)
- Previous agent assignment is overwritten
- Conversation history is preserved

---

## Error Responses

All endpoints may return standard error responses:

### 400 Bad Request

```json
{
  "detail": "Invalid workspace ID"
}
```

### 404 Not Found

```json
{
  "detail": "Conversation with ID '123e4567-e89b-12d3-a456-426614174000' not found"
}
```

### 422 Unprocessable Entity

```json
{
  "detail": [
    {
      "loc": ["body", "role"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 500 Internal Server Error

```json
{
  "detail": "Internal server error"
}
```

### 503 Service Unavailable

```json
{
  "detail": "ZeroDB service temporarily unavailable"
}
```

---

## Rate Limits

Current rate limits (subject to change):

- **POST /conversations/{id}/messages**: 100 requests/minute per IP
- **POST /conversations/{id}/search**: 20 requests/minute per IP
- **Other endpoints**: 200 requests/minute per IP

Rate limit headers:

```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 95
X-RateLimit-Reset: 1642234800
```

---

## Pagination

List endpoints support pagination via `limit` and `offset` parameters:

```bash
# Get first page (items 0-49)
curl "http://localhost:8000/conversations?limit=50&offset=0"

# Get second page (items 50-99)
curl "http://localhost:8000/conversations?limit=50&offset=50"

# Get third page (items 100-149)
curl "http://localhost:8000/conversations?limit=50&offset=100"
```

Response includes total count:

```json
{
  "conversations": [...],
  "total": 150,
  "limit": 50,
  "offset": 0
}
```

**Best Practices**:
- Use `limit=50` for most use cases (good balance of performance and UX)
- Maximum `limit=200` to prevent memory issues
- Calculate total pages: `total_pages = Math.ceil(total / limit)`

---

## Common Workflows

### Complete Message Flow (WhatsApp to API)

1. **User sends WhatsApp message** → Bridge receives
2. **Bridge creates or finds conversation**:
   ```bash
   POST /conversations
   ```
3. **Bridge adds user message**:
   ```bash
   POST /conversations/{id}/messages
   ```
4. **Agent loads context**:
   ```bash
   GET /conversations/{id}/context?limit=100
   ```
5. **Agent generates response** (via Claude API)
6. **Bridge adds assistant message**:
   ```bash
   POST /conversations/{id}/messages
   ```
7. **Frontend retrieves messages**:
   ```bash
   GET /conversations/{id}/messages?limit=50
   ```

### Conversation Archival

```bash
# List active conversations
curl "http://localhost:8000/conversations?status=active&limit=50"

# Archive specific conversation
curl -X POST "http://localhost:8000/conversations/{id}/archive"

# List archived conversations
curl "http://localhost:8000/conversations?status=archived&limit=50"
```

### Multi-Agent Switching

```bash
# Start conversation with Agent 1
curl -X POST "http://localhost:8000/conversations" \
  -d '{"agent_id": "agent-1-uuid", ...}'

# Add messages with Agent 1
curl -X POST "http://localhost:8000/conversations/{id}/messages" \
  -d '{"role": "user", "content": "Hello"}'

# Switch to Agent 2
curl -X POST "http://localhost:8000/conversations/{id}/attach-agent" \
  -d '{"agent_id": "agent-2-uuid"}'

# Continue conversation with Agent 2
curl -X POST "http://localhost:8000/conversations/{id}/messages" \
  -d '{"role": "user", "content": "Continue helping me"}'
```

---

## Testing with curl

### Set Environment Variables

```bash
export BASE_URL="http://localhost:8000"
export WORKSPACE_ID="789e4567-e89b-12d3-a456-426614174111"
export AGENT_ID="456e4567-e89b-12d3-a456-426614174222"
export USER_ID="987e4567-e89b-12d3-a456-426614174333"
```

### Create and Test Conversation

```bash
# Create conversation
CONV_ID=$(curl -s -X POST "$BASE_URL/conversations" \
  -H "Content-Type: application/json" \
  -d "{\"workspace_id\": \"$WORKSPACE_ID\", \"agent_id\": \"$AGENT_ID\", \"user_id\": \"$USER_ID\"}" \
  | jq -r '.id')

echo "Created conversation: $CONV_ID"

# Add user message
curl -X POST "$BASE_URL/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -d '{"role": "user", "content": "Hello, AI!"}'

# Add assistant message
curl -X POST "$BASE_URL/conversations/$CONV_ID/messages" \
  -H "Content-Type: application/json" \
  -d '{"role": "assistant", "content": "Hello! How can I help?"}'

# Get messages
curl "$BASE_URL/conversations/$CONV_ID/messages?limit=10"

# Search conversation
curl -X POST "$BASE_URL/conversations/$CONV_ID/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "greeting", "limit": 5}'

# Archive conversation
curl -X POST "$BASE_URL/conversations/$CONV_ID/archive"
```

---

## Python SDK Example

```python
import httpx
from uuid import UUID

class ConversationClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.client = httpx.AsyncClient()

    async def create_conversation(self, workspace_id: UUID, agent_id: UUID, user_id: UUID):
        response = await self.client.post(
            f"{self.base_url}/conversations",
            json={
                "workspace_id": str(workspace_id),
                "agent_id": str(agent_id),
                "user_id": str(user_id)
            }
        )
        response.raise_for_status()
        return response.json()

    async def add_message(self, conversation_id: UUID, role: str, content: str, metadata: dict = None):
        response = await self.client.post(
            f"{self.base_url}/conversations/{conversation_id}/messages",
            json={
                "role": role,
                "content": content,
                "metadata": metadata or {}
            }
        )
        response.raise_for_status()
        return response.json()

    async def get_messages(self, conversation_id: UUID, limit: int = 50, offset: int = 0):
        response = await self.client.get(
            f"{self.base_url}/conversations/{conversation_id}/messages",
            params={"limit": limit, "offset": offset}
        )
        response.raise_for_status()
        return response.json()
```

Usage:

```python
client = ConversationClient("http://localhost:8000")

# Create conversation
conv = await client.create_conversation(
    workspace_id=UUID("789e4567-e89b-12d3-a456-426614174111"),
    agent_id=UUID("456e4567-e89b-12d3-a456-426614174222"),
    user_id=UUID("987e4567-e89b-12d3-a456-426614174333")
)

# Add message
await client.add_message(
    conversation_id=conv["id"],
    role="user",
    content="Hello!"
)

# Get messages
messages = await client.get_messages(conv["id"], limit=10)
```

---

## Additional Resources

- **Main Documentation**: [docs/CHAT_PERSISTENCE.md](../CHAT_PERSISTENCE.md)
- **Troubleshooting**: [docs/CHAT_PERSISTENCE_TROUBLESHOOTING.md](../CHAT_PERSISTENCE_TROUBLESHOOTING.md)
- **Migration Guide**: [docs/CHAT_PERSISTENCE_MIGRATION.md](../CHAT_PERSISTENCE_MIGRATION.md)
- **Integration Tests**: [tests/integration/test_chat_persistence_e2e.py](../../tests/integration/test_chat_persistence_e2e.py)

---

**Document Version**: 1.0
**Last Updated**: 2026-03-08
