# Chat Persistence API Reference

## Base URL

```
http://localhost:8000/api/v1
```

For production, replace with your deployed backend URL.

## Authentication

Currently, the API does not require authentication. Future versions will implement JWT-based authentication.

## Common Response Codes

| Code | Meaning | When It Occurs |
|------|---------|----------------|
| 200 | Success | Request processed successfully |
| 404 | Not Found | Resource (conversation, message) does not exist |
| 422 | Validation Error | Invalid request parameters (e.g., negative offset, invalid UUID) |
| 503 | Service Unavailable | ZeroDB client not configured (missing ZERODB_API_KEY) |

## Endpoints

### 1. List Conversations

Retrieve a list of conversations with optional filters and pagination.

**Endpoint:** `GET /conversations`

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `workspace_id` | UUID | No | None | Filter by workspace |
| `agent_id` | UUID | No | None | Filter by agent |
| `status` | string | No | None | Filter by status (`active`, `archived`, `deleted`) |
| `limit` | integer | No | 50 | Results per page (1-200) |
| `offset` | integer | No | 0 | Number of results to skip |

**Example Request:**

```bash
# List all conversations
curl -X GET "http://localhost:8000/api/v1/conversations"

# Filter by agent
curl -X GET "http://localhost:8000/api/v1/conversations?agent_id=123e4567-e89b-12d3-a456-426614174000"

# Filter by workspace and status
curl -X GET "http://localhost:8000/api/v1/conversations?workspace_id=123e4567-e89b-12d3-a456-426614174001&status=active"

# Pagination (page 2, 25 results per page)
curl -X GET "http://localhost:8000/api/v1/conversations?limit=25&offset=25"
```

**Example Response:**

```json
{
  "conversations": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "workspace_id": "223e4567-e89b-12d3-a456-426614174000",
      "agent_id": "323e4567-e89b-12d3-a456-426614174000",
      "user_id": "423e4567-e89b-12d3-a456-426614174000",
      "openclaw_session_key": "session_abc123xyz",
      "started_at": "2026-03-02T10:00:00Z",
      "last_message_at": "2026-03-02T10:15:00Z",
      "message_count": 5,
      "status": "active"
    },
    {
      "id": "123e4567-e89b-12d3-a456-426614174001",
      "workspace_id": "223e4567-e89b-12d3-a456-426614174000",
      "agent_id": "323e4567-e89b-12d3-a456-426614174000",
      "user_id": "423e4567-e89b-12d3-a456-426614174000",
      "openclaw_session_key": "session_def456uvw",
      "started_at": "2026-03-02T09:30:00Z",
      "last_message_at": "2026-03-02T09:45:00Z",
      "message_count": 3,
      "status": "active"
    }
  ],
  "total": 2,
  "limit": 50,
  "offset": 0
}
```

**Response Schema:**

```typescript
{
  conversations: Conversation[],  // Array of conversation objects
  total: number,                  // Total count (before pagination)
  limit: number,                  // Results per page
  offset: number                  // Offset used for this page
}

type Conversation = {
  id: string;                     // UUID
  workspace_id: string;           // UUID
  agent_id: string;               // UUID
  user_id: string | null;         // UUID or null
  openclaw_session_key: string;  // OpenClaw session identifier
  started_at: string;             // ISO 8601 timestamp
  last_message_at: string | null; // ISO 8601 timestamp or null
  message_count: number;          // Count of messages in conversation
  status: "active" | "archived" | "deleted";
}
```

**Error Responses:**

```json
// 422 Validation Error - Invalid limit
{
  "detail": [
    {
      "loc": ["query", "limit"],
      "msg": "ensure this value is less than or equal to 200",
      "type": "value_error.number.not_le"
    }
  ]
}

// 503 Service Unavailable - ZeroDB not configured
{
  "detail": "ZeroDB API key not configured"
}
```

---

### 2. Get Conversation

Retrieve details of a single conversation by ID.

**Endpoint:** `GET /conversations/{conversation_id}`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation ID |

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/v1/conversations/123e4567-e89b-12d3-a456-426614174000"
```

**Example Response:**

```json
{
  "id": "123e4567-e89b-12d3-a456-426614174000",
  "workspace_id": "223e4567-e89b-12d3-a456-426614174000",
  "agent_id": "323e4567-e89b-12d3-a456-426614174000",
  "user_id": "423e4567-e89b-12d3-a456-426614174000",
  "openclaw_session_key": "session_abc123xyz",
  "started_at": "2026-03-02T10:00:00Z",
  "last_message_at": "2026-03-02T10:15:00Z",
  "message_count": 5,
  "status": "active"
}
```

**Response Schema:** Same as `Conversation` type above

**Error Responses:**

```json
// 404 Not Found
{
  "detail": "Conversation with ID '123e4567-e89b-12d3-a456-426614174000' not found"
}

// 422 Validation Error - Invalid UUID
{
  "detail": [
    {
      "loc": ["path", "conversation_id"],
      "msg": "value is not a valid uuid",
      "type": "type_error.uuid"
    }
  ]
}
```

---

### 3. Get Conversation Messages

Retrieve messages from a conversation with pagination.

**Endpoint:** `GET /conversations/{conversation_id}/messages`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation ID |

**Query Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `limit` | integer | No | 50 | Messages per page (1-200) |
| `offset` | integer | No | 0 | Number of messages to skip |

**Example Request:**

```bash
# Get first 50 messages
curl -X GET "http://localhost:8000/api/v1/conversations/123e4567-e89b-12d3-a456-426614174000/messages"

# Get messages 20-40
curl -X GET "http://localhost:8000/api/v1/conversations/123e4567-e89b-12d3-a456-426614174000/messages?limit=20&offset=20"

# Get all messages (if less than 200)
curl -X GET "http://localhost:8000/api/v1/conversations/123e4567-e89b-12d3-a456-426614174000/messages?limit=200&offset=0"
```

**Example Response:**

```json
{
  "messages": [
    {
      "id": "msg_abc123",
      "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
      "role": "user",
      "content": "Hello, how are you?",
      "timestamp": "2026-03-02T10:00:00Z",
      "metadata": null
    },
    {
      "id": "msg_def456",
      "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
      "role": "assistant",
      "content": "I'm doing well, thank you! How can I help you today?",
      "timestamp": "2026-03-02T10:00:15Z",
      "metadata": {
        "model": "claude-3-5-sonnet-20241022",
        "tokens": 18
      }
    },
    {
      "id": "msg_ghi789",
      "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
      "role": "user",
      "content": "Can you explain async/await in Python?",
      "timestamp": "2026-03-02T10:01:00Z",
      "metadata": null
    }
  ],
  "total": 5
}
```

**Response Schema:**

```typescript
{
  messages: Message[],  // Array of message objects
  total: number         // Total message count in conversation
}

type Message = {
  id: string;                // ZeroDB row ID
  conversation_id: string;   // UUID of conversation
  role: "user" | "assistant" | "system";
  content: string;           // Message text
  timestamp: string;         // ISO 8601 timestamp
  metadata?: object | null;  // Optional metadata (model, tokens, etc.)
}
```

**Notes:**

- Messages are returned in chronological order (oldest first)
- `total` reflects the total message count from conversation metadata
- Use `limit` and `offset` for pagination through long conversations
- Messages are retrieved from ZeroDB tables (fast, indexed queries)

**Error Responses:**

```json
// 404 Not Found - Conversation doesn't exist
{
  "detail": "Conversation with ID '123e4567-e89b-12d3-a456-426614174000' not found"
}

// 422 Validation Error - Invalid pagination
{
  "detail": [
    {
      "loc": ["query", "offset"],
      "msg": "ensure this value is greater than or equal to 0",
      "type": "value_error.number.not_ge"
    }
  ]
}
```

---

### 4. Search Conversation (Semantic)

Perform semantic search within a conversation using natural language queries.

**Endpoint:** `POST /conversations/{conversation_id}/search`

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `conversation_id` | UUID | Yes | Conversation ID |

**Request Body:**

```json
{
  "query": "string",   // Natural language search query (required)
  "limit": 5           // Maximum results to return (optional, default: 5)
}
```

**Example Request:**

```bash
# Search for Python-related messages
curl -X POST "http://localhost:8000/api/v1/conversations/123e4567-e89b-12d3-a456-426614174000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Python async programming",
    "limit": 5
  }'

# Search for error-related messages
curl -X POST "http://localhost:8000/api/v1/conversations/123e4567-e89b-12d3-a456-426614174000/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "database connection errors",
    "limit": 3
  }'
```

**Example Response:**

```json
{
  "results": {
    "results": [
      {
        "id": "mem_xyz789",
        "title": "Message in conversation 123e4567-e89b-12d3-a456-426614174000",
        "content": "Can you explain async/await in Python?",
        "type": "conversation",
        "score": 0.89,
        "metadata": {
          "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
          "role": "user",
          "timestamp": "2026-03-02T10:01:00Z"
        }
      },
      {
        "id": "mem_uvw456",
        "title": "Message in conversation 123e4567-e89b-12d3-a456-426614174000",
        "content": "Async/await in Python allows you to write concurrent code using the async def syntax...",
        "type": "conversation",
        "score": 0.85,
        "metadata": {
          "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
          "role": "assistant",
          "timestamp": "2026-03-02T10:01:15Z",
          "model": "claude-3-5-sonnet-20241022"
        }
      }
    ],
    "total": 2,
    "query": "Python async programming"
  }
}
```

**Response Schema:**

```typescript
{
  results: SearchResults
}

type SearchResults = {
  results: SearchResult[],  // Array of matching messages
  total: number,            // Count of results (after filtering to this conversation)
  query: string             // Original search query
}

type SearchResult = {
  id: string;              // ZeroDB memory ID
  title: string;           // Memory title
  content: string;         // Message text
  type: "conversation";    // Memory type
  score: number;           // Similarity score (0.0 to 1.0, higher is better)
  metadata: {
    conversation_id: string;   // UUID
    role: string;              // "user" | "assistant" | "system"
    timestamp: string;         // ISO 8601 timestamp
    [key: string]: any;        // Additional metadata
  }
}
```

**Notes:**

- Uses ZeroDB Memory API for vector-based semantic search
- Results ranked by similarity score (higher = more relevant)
- Only returns messages from the specified conversation
- Requires messages to have been stored in Memory API (graceful degradation may cause some messages to be missing)
- Query should be natural language (not keywords)

**Example Queries:**

- **Good:** "How do I handle database connection errors?"
- **Good:** "Python async programming concepts"
- **Good:** "User authentication best practices"
- **Avoid:** "database error" (too short, prefer natural language)
- **Avoid:** "python+async+await" (not natural language)

**Error Responses:**

```json
// 404 Not Found
{
  "detail": "Conversation with ID '123e4567-e89b-12d3-a456-426614174000' not found"
}

// 422 Validation Error - Missing query
{
  "detail": [
    {
      "loc": ["body", "query"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}

// 503 Service Unavailable - ZeroDB Memory API issue
{
  "detail": "ZeroDB Memory API unavailable"
}
```

---

## Request/Response Examples

### Python (httpx)

```python
import httpx
import asyncio
from uuid import UUID


async def list_conversations():
    """List all active conversations for an agent."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            "http://localhost:8000/api/v1/conversations",
            params={
                "agent_id": "323e4567-e89b-12d3-a456-426614174000",
                "status": "active",
                "limit": 10
            }
        )
        response.raise_for_status()
        data = response.json()
        print(f"Found {data['total']} conversations")
        return data["conversations"]


async def get_conversation_messages(conversation_id: UUID):
    """Retrieve messages from a conversation."""
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"http://localhost:8000/api/v1/conversations/{conversation_id}/messages",
            params={"limit": 50, "offset": 0}
        )
        response.raise_for_status()
        data = response.json()
        return data["messages"]


async def search_conversation(conversation_id: UUID, query: str):
    """Search conversation using semantic similarity."""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"http://localhost:8000/api/v1/conversations/{conversation_id}/search",
            json={"query": query, "limit": 5}
        )
        response.raise_for_status()
        data = response.json()
        return data["results"]["results"]


# Run examples
asyncio.run(list_conversations())
```

### JavaScript (fetch)

```javascript
// List conversations
async function listConversations(agentId) {
  const params = new URLSearchParams({
    agent_id: agentId,
    status: 'active',
    limit: 10
  });

  const response = await fetch(
    `http://localhost:8000/api/v1/conversations?${params}`
  );

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  console.log(`Found ${data.total} conversations`);
  return data.conversations;
}

// Get messages
async function getMessages(conversationId, limit = 50, offset = 0) {
  const params = new URLSearchParams({ limit, offset });

  const response = await fetch(
    `http://localhost:8000/api/v1/conversations/${conversationId}/messages?${params}`
  );

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  return data.messages;
}

// Semantic search
async function searchConversation(conversationId, query, limit = 5) {
  const response = await fetch(
    `http://localhost:8000/api/v1/conversations/${conversationId}/search`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, limit })
    }
  );

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }

  const data = await response.json();
  return data.results.results;
}

// Usage
listConversations('323e4567-e89b-12d3-a456-426614174000')
  .then(conversations => console.log(conversations))
  .catch(err => console.error(err));
```

### curl (Shell)

```bash
#!/bin/bash

# Configuration
BASE_URL="http://localhost:8000/api/v1"
AGENT_ID="323e4567-e89b-12d3-a456-426614174000"
CONVERSATION_ID="123e4567-e89b-12d3-a456-426614174000"

# List conversations
echo "Listing conversations..."
curl -s -X GET "$BASE_URL/conversations?agent_id=$AGENT_ID&status=active" | jq .

# Get conversation details
echo "Getting conversation details..."
curl -s -X GET "$BASE_URL/conversations/$CONVERSATION_ID" | jq .

# Get messages (page 1)
echo "Getting messages..."
curl -s -X GET "$BASE_URL/conversations/$CONVERSATION_ID/messages?limit=20&offset=0" | jq .

# Semantic search
echo "Searching conversation..."
curl -s -X POST "$BASE_URL/conversations/$CONVERSATION_ID/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "Python async programming", "limit": 5}' | jq .
```

## Pagination Best Practices

### Standard Pagination

```python
async def fetch_all_messages(conversation_id: UUID, page_size: int = 50):
    """Fetch all messages from a conversation using pagination."""
    all_messages = []
    offset = 0

    async with httpx.AsyncClient() as client:
        while True:
            response = await client.get(
                f"http://localhost:8000/api/v1/conversations/{conversation_id}/messages",
                params={"limit": page_size, "offset": offset}
            )
            response.raise_for_status()
            data = response.json()

            messages = data["messages"]
            all_messages.extend(messages)

            # Stop if we got fewer messages than requested (last page)
            if len(messages) < page_size:
                break

            offset += page_size

    return all_messages
```

### Efficient Pagination (Use Total Count)

```python
async def fetch_all_messages_efficient(conversation_id: UUID, page_size: int = 50):
    """Fetch all messages using total count to avoid extra request."""
    all_messages = []
    offset = 0

    async with httpx.AsyncClient() as client:
        # First request to get total
        response = await client.get(
            f"http://localhost:8000/api/v1/conversations/{conversation_id}/messages",
            params={"limit": page_size, "offset": 0}
        )
        response.raise_for_status()
        data = response.json()

        all_messages.extend(data["messages"])
        total = data["total"]

        # Fetch remaining pages
        offset = page_size
        while offset < total:
            response = await client.get(
                f"http://localhost:8000/api/v1/conversations/{conversation_id}/messages",
                params={"limit": page_size, "offset": offset}
            )
            response.raise_for_status()
            data = response.json()
            all_messages.extend(data["messages"])
            offset += page_size

    return all_messages
```

## Rate Limiting

Currently, no rate limiting is enforced. Future versions may implement:

- **Per-IP rate limit:** 100 requests/minute
- **Per-workspace rate limit:** 1000 requests/hour
- **Semantic search rate limit:** 10 queries/minute (due to vector computation cost)

## Versioning

API version is included in the URL path (`/api/v1/`). Breaking changes will be released under new version paths (`/api/v2/`).

**Current Version:** v1

## Error Handling Best Practices

```python
import httpx
from typing import Optional


async def safe_get_conversation(conversation_id: str) -> Optional[dict]:
    """Get conversation with comprehensive error handling."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"http://localhost:8000/api/v1/conversations/{conversation_id}"
            )
            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            print(f"Conversation {conversation_id} not found")
            return None
        elif e.response.status_code == 503:
            print("Service unavailable - ZeroDB not configured")
            return None
        else:
            print(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise

    except httpx.TimeoutException:
        print("Request timed out")
        return None

    except httpx.ConnectError:
        print("Could not connect to backend - is it running?")
        return None

    except Exception as e:
        print(f"Unexpected error: {e}")
        raise
```

## Support

For issues or questions:

1. Check [Troubleshooting Guide](chat-persistence-troubleshooting.md)
2. Review [Architecture Documentation](chat-persistence-architecture.md)
3. Search existing issues on GitHub
4. Open new issue with API request/response examples
