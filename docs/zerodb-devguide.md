# ZeroDB Developer Guide

**Version:** 2.1.0
**Last Updated:** 2026-02-28
**Status:** ✅ Current & Production Ready

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Authentication](#authentication)
3. [Memory API](#memory-api)
4. [Vector Operations](#vector-operations)
5. [Table Operations](#table-operations)
6. [Event Streaming](#event-streaming)
7. [File Storage](#file-storage)
8. [ZeroLocal Development](#zerolocal-development)
9. [Code Examples](#code-examples)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

### Production API
```bash
BASE_URL="https://api.ainative.studio"
```

### ZeroLocal (Development)
```bash
BASE_URL="http://localhost:8000"
```

### 5-Minute Setup

```bash
# 1. Get API Key (from dashboard or use admin credentials)
API_KEY="your-api-key-here"

# 2. Create Project
PROJECT_ID=$(curl -s -X POST "$BASE_URL/v1/projects/" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "My ZeroDB Project", "description": "AI memory storage"}' | \
  jq -r '.id')

echo "Project Created: $PROJECT_ID"

# 3. Store your first memory
curl -X POST "$BASE_URL/v1/public/memory/" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "First Memory",
    "content": "Testing ZeroDB memory storage",
    "type": "note",
    "priority": "medium",
    "tags": ["test", "getting-started"]
  }'

# 4. Search memories
curl -X POST "$BASE_URL/v1/public/memory/search" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "testing",
    "limit": 5
  }'
```

---

## Authentication

### Method 1: API Keys (Recommended)

**Generate:** From AINative Studio dashboard
**Use:** Production applications, SDKs, long-running services

```bash
curl -X GET "https://api.ainative.studio/v1/projects/" \
  -H "X-API-Key: your-api-key-here"
```

**Advantages:**
- No expiration
- Simple to use
- Perfect for automation

### Method 2: JWT Tokens

**Use:** Web applications, temporary access, user-scoped operations

```bash
# Login to get token
TOKEN=$(curl -s -X POST "https://api.ainative.studio/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@ainative.studio","password":"Admin2025!Secure"}' | \
  jq -r '.access_token')

# Use token
curl -X GET "https://api.ainative.studio/v1/projects/" \
  -H "Authorization: Bearer $TOKEN"
```

**Token Details:**
- Expires in 24 hours (86400 seconds)
- User-scoped access
- Refresh token provided for extended sessions
- Endpoint: `/v1/auth/login` (note: NOT `/api/v1/auth/login`)

---

## Memory API

### Overview

The Enhanced Memory API provides structured, intelligent memory storage for AI agents with:
- **8 Memory Types:** `code_snippet`, `documentation`, `preference`, `conversation`, `task`, `note`, `insight`, `fact`
- **Priority Levels:** `low`, `medium`, `high`, `critical`
- **Context Linking:** Connect related memories
- **Quantum Enhancement:** Advanced memory processing (optional)
- **Semantic Search:** Find memories by meaning

### Base URL
```
POST /v1/public/memory/
```

### Create Memory

```bash
curl -X POST "https://api.ainative.studio/v1/public/memory/" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "User Authentication Implementation",
    "content": "Implemented JWT-based authentication using FastAPI dependencies. Token expires in 30 minutes.",
    "type": "code_snippet",
    "priority": "high",
    "tags": ["authentication", "security", "jwt"],
    "metadata": {
      "file": "app/api/deps.py",
      "function": "get_current_user",
      "language": "python"
    }
  }'
```

**Response:**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "User Authentication Implementation",
  "content": "Implemented JWT-based authentication...",
  "type": "code_snippet",
  "priority": "high",
  "tags": ["authentication", "security", "jwt"],
  "embedding_vector": [0.1, 0.2, ...],
  "context_links": [],
  "created_at": "2026-02-28T10:30:00Z",
  "updated_at": "2026-02-28T10:30:00Z"
}
```

### List Memories

```bash
curl -X GET "https://api.ainative.studio/v1/public/memory/?limit=10&offset=0" \
  -H "X-API-Key: your-api-key"
```

**Query Parameters:**
- `limit` (optional): Max memories to return (default: 10, max: 100)
- `offset` (optional): Pagination offset (default: 0)
- `type` (optional): Filter by memory type
- `priority` (optional): Filter by priority level
- `tags` (optional): Filter by tags (comma-separated)

### Search Memories

```bash
curl -X POST "https://api.ainative.studio/v1/public/memory/search" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "authentication implementation",
    "limit": 5,
    "type": "code_snippet",
    "priority": "high"
  }'
```

**Response:**
```json
{
  "memories": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "title": "User Authentication Implementation",
      "content": "Implemented JWT-based authentication...",
      "similarity_score": 0.92,
      "type": "code_snippet",
      "priority": "high"
    }
  ],
  "total_count": 1,
  "search_time_ms": 45.2
}
```

### Update Memory

```bash
curl -X PUT "https://api.ainative.studio/v1/public/memory/{memory_id}" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Updated Title",
    "content": "Updated content",
    "priority": "critical",
    "tags": ["updated", "important"]
  }'
```

### Delete Memory

```bash
curl -X DELETE "https://api.ainative.studio/v1/public/memory/{memory_id}" \
  -H "X-API-Key: your-api-key"
```

### Get Statistics

```bash
curl -X GET "https://api.ainative.studio/v1/public/memory/statistics" \
  -H "X-API-Key: your-api-key"
```

**Response:**
```json
{
  "total_memories": 1250,
  "by_type": {
    "code_snippet": 450,
    "documentation": 320,
    "conversation": 280,
    "note": 200
  },
  "by_priority": {
    "critical": 50,
    "high": 300,
    "medium": 600,
    "low": 300
  },
  "total_size_mb": 25.3,
  "last_created": "2026-02-28T10:30:00Z"
}
```

### Memory Types

| Type | Description | Use Case |
|------|-------------|----------|
| `code_snippet` | Code examples, functions | Store reusable code |
| `documentation` | Technical docs, guides | Reference material |
| `preference` | User preferences, settings | Remember user choices |
| `conversation` | Chat history, dialogue | Conversational context |
| `task` | To-dos, action items | Task management |
| `note` | General notes | Quick captures |
| `insight` | Learnings, discoveries | Knowledge base |
| `fact` | Verified information | Factual data |

### Priority Levels

| Priority | Description | Use Case |
|----------|-------------|----------|
| `critical` | Must not forget | Security credentials, critical bugs |
| `high` | Very important | Key features, major decisions |
| `medium` | Normal importance | Regular tasks, standard info |
| `low` | Nice to have | Optional context, references |

---

## Vector Operations

### Overview

Store and search vector embeddings with flexible dimensions:
- **Any Dimension:** Not limited to 1536 (supports all sizes)
- **Namespaces:** Organize vectors by category
- **Metadata:** Rich JSON metadata support
- **Fast Search:** Optimized semantic similarity

### Base URL
```
/v1/projects/{project_id}/database/vectors/
```

### Store Vector

```bash
curl -X POST "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/vectors/upsert" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "vector_embedding": [0.1, 0.2, 0.3, 0.4, 0.5],
    "metadata": {
      "source": "documentation",
      "title": "API Reference",
      "url": "https://example.com/api-docs"
    },
    "namespace": "documentation",
    "document": "Complete API documentation for developers"
  }'
```

**Response:**
```json
{
  "vector_id": "vec_550e8400-e29b-41d4-a716-446655440000",
  "namespace": "documentation",
  "dimension": 5,
  "created_at": "2026-02-28T10:30:00Z"
}
```

### Search Vectors

```bash
curl -X POST "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/vectors/search" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "query_vector": [0.1, 0.2, 0.3, 0.4, 0.5],
    "top_k": 5,
    "namespace": "documentation",
    "similarity_threshold": 0.7
  }'
```

**Response:**
```json
{
  "vectors": [
    {
      "vector_id": "vec_550e8400-e29b-41d4-a716-446655440000",
      "similarity_score": 0.95,
      "namespace": "documentation",
      "metadata": {
        "source": "documentation",
        "title": "API Reference"
      },
      "document": "Complete API documentation..."
    }
  ],
  "total_count": 1,
  "search_time_ms": 12.5
}
```

### Batch Upsert

```bash
curl -X POST "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/vectors/upsert-batch" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '[
    {
      "vector_embedding": [0.1, 0.2, 0.3],
      "metadata": {"index": 1},
      "namespace": "batch_test",
      "document": "First document"
    },
    {
      "vector_embedding": [0.4, 0.5, 0.6],
      "metadata": {"index": 2},
      "namespace": "batch_test",
      "document": "Second document"
    }
  ]'
```

**Performance Tips:**
- Batch up to 100 vectors per request
- Use namespaces to organize vectors
- Include meaningful metadata for filtering
- Dimension is automatically detected

---

## Table Operations

### Overview

NoSQL table storage with flexible JSON schemas:
- **Dynamic Schema:** Store any JSON structure
- **Full CRUD:** Create, Read, Update, Delete
- **UUID Keys:** Automatic row IDs
- **Pagination:** Skip/limit support

### Base URL
```
/v1/projects/{project_id}/database/tables/
```

### Create Table

```bash
curl -X POST "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/tables" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "table_name": "customers",
    "description": "Customer information table"
  }'
```

### Create Row

```bash
curl -X POST "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/tables/customers/rows" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "row_data": {
      "name": "John Doe",
      "email": "john@example.com",
      "plan": "premium",
      "metadata": {
        "signup_date": "2026-02-28",
        "referral_code": "FRIEND2026"
      }
    }
  }'
```

**Response:**
```json
{
  "row_id": "92b8a0dc-9a4d-46ff-af25-86a5f87a82c5",
  "project_id": "f8be918b-9738-4e09-b18e-e5fd701e553d",
  "table_name": "customers",
  "row_data": {
    "name": "John Doe",
    "email": "john@example.com",
    "plan": "premium"
  },
  "created_at": "2026-02-28T10:30:00Z",
  "updated_at": "2026-02-28T10:30:00Z"
}
```

### List Rows

```bash
curl -X GET "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/tables/customers/rows?limit=10&skip=0" \
  -H "X-API-Key: your-api-key"
```

### Update Row

```bash
curl -X PUT "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/tables/customers/rows/$ROW_ID" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "row_data": {
      "name": "John Doe",
      "email": "john@example.com",
      "plan": "enterprise"
    }
  }'
```

### Delete Row

```bash
curl -X DELETE "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/tables/customers/rows/$ROW_ID" \
  -H "X-API-Key: your-api-key"
```

---

## Event Streaming

### Overview

Real-time event publishing and streaming:
- **Server-Sent Events (SSE):** Live event streams
- **Topic-Based:** Filter by event topics
- **Historical Replay:** Stream from specific timestamp
- **Keep-Alive:** 30-second ping intervals

### Base URL
```
/v1/projects/{project_id}/database/events/
```

### Publish Event

```bash
curl -X POST "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/events/publish" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "user_activity",
    "event_payload": {
      "action": "login",
      "user_id": "user-123",
      "ip_address": "192.168.1.1",
      "timestamp": "2026-02-28T10:30:00Z"
    }
  }'
```

### List Events

```bash
curl -X GET "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/events?topic=user_activity&limit=10" \
  -H "X-API-Key: your-api-key"
```

### Stream Events (SSE)

```bash
curl -N "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/events/stream?topic=user_activity" \
  -H "X-API-Key: your-api-key" \
  -H "Accept: text/event-stream" \
  -H "Cache-Control: no-cache"
```

**SSE Stream Output:**
```
data: {"type": "connection", "status": "connected", "project_id": "..."}

data: {"event_id": "...", "topic": "user_activity", "event_payload": {...}, "published_at": "..."}

data: {"type": "ping", "timestamp": "...", "events_since_start": 30}
```

**JavaScript Client:**
```javascript
const eventSource = new EventSource(
  'https://api.ainative.studio/v1/projects/PROJECT_ID/database/events/stream',
  {
    headers: { 'X-API-Key': 'your-api-key' }
  }
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('Event:', data);
};

eventSource.onerror = (error) => {
  console.error('SSE Error:', error);
  eventSource.close();
};
```

---

## File Storage

### Overview

S3-compatible object storage powered by MinIO:
- **Pre-signed URLs:** Direct client uploads (no server proxy)
- **Any File Type:** Images, videos, documents, archives
- **Metadata:** Rich file metadata support
- **Secure:** Signed URLs with expiration

### Documentation

See dedicated guide: [`docs/api/ZERODB_FILE_STORAGE_GUIDE.md`](../api/ZERODB_FILE_STORAGE_GUIDE.md)

### Quick Example

```bash
# 1. Upload file metadata
curl -X POST "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/files/upload" \
  -H "X-API-Key: your-api-key" \
  -H "Content-Type: application/json" \
  -d '{
    "file_key": "uploads/image.png",
    "file_name": "image.png",
    "file_size": 102400,
    "mime_type": "image/png"
  }'

# 2. List files
curl -X GET "https://api.ainative.studio/v1/projects/$PROJECT_ID/database/files" \
  -H "X-API-Key: your-api-key"
```

---

## ZeroLocal Development

### Overview

ZeroLocal is the local development environment for ZeroDB with:
- **< 60 Second Setup:** From download to running
- **7 Docker Services:** PostgreSQL, Qdrant, MinIO, RedPanda, Embeddings, API, Dashboard
- **Perfect Parity:** Same API as production
- **Zero Cost:** Free local embeddings (BAAI BGE models)

### Quick Start

```bash
# 1. Download ZeroLocal
git clone https://github.com/ainative/zerodb-local.git
cd zerodb-local

# 2. Start services
./zerodb init

# 3. Open dashboard
# Browser opens automatically at http://localhost:3000

# 4. Use local API
BASE_URL="http://localhost:8000"
```

### Documentation

- **[Architecture](../zerodb-local/ARCHITECTURE.md)** - Complete system design (1,582 lines)
- **[Implementation Summary](../zerodb-local/IMPLEMENTATION_SUMMARY.md)** - Quick overview (445 lines)
- **[CLI Wizard](../zerodb-local/CLI_WIZARD_DESIGN.md)** - Interactive CLI (961 lines)
- **[Installers](../zerodb-local/INSTALLER_SPECS.md)** - Native installers (886 lines)

### Services

| Service | Port | Purpose |
|---------|------|---------|
| API Server | 8000 | FastAPI backend (128 endpoints) |
| Dashboard | 3000 | Next.js UI |
| PostgreSQL | 5432 | Relational data + pgvector |
| Qdrant | 6333 | Vector search |
| MinIO | 9000 | Object storage |
| RedPanda | 9092 | Event streaming |
| Embeddings | 8001 | Local BAAI BGE models |

### Vision

Make developers love ZeroLocal so much they choose ZeroDB Cloud in production:
- **LocalStack Model:** Just as LocalStack drives AWS adoption
- **World-Class UX:** Native installers, beautiful dashboard, perfect parity
- **Agent-First:** Designed for AI agent integration (AgentX)

---

## Code Examples

### Python SDK

```python
import requests
import uuid

class ZeroDBClient:
    def __init__(self, api_url, api_key):
        self.api_url = api_url
        self.api_key = api_key
        self.headers = {
            "X-API-Key": api_key,
            "Content-Type": "application/json"
        }

    def create_memory(self, title, content, memory_type="note", priority="medium", tags=None):
        """Create a new memory"""
        url = f"{self.api_url}/v1/public/memory/"
        data = {
            "title": title,
            "content": content,
            "type": memory_type,
            "priority": priority,
            "tags": tags or []
        }
        response = requests.post(url, json=data, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def search_memories(self, query, limit=5, memory_type=None):
        """Search memories by semantic similarity"""
        url = f"{self.api_url}/v1/public/memory/search"
        data = {
            "query": query,
            "limit": limit
        }
        if memory_type:
            data["type"] = memory_type

        response = requests.post(url, json=data, headers=self.headers)
        response.raise_for_status()
        return response.json()

    def store_vector(self, project_id, embedding, namespace="default", metadata=None, document=None):
        """Store vector embedding"""
        url = f"{self.api_url}/v1/projects/{project_id}/database/vectors/upsert"
        data = {
            "vector_embedding": embedding,
            "namespace": namespace,
            "metadata": metadata or {},
            "document": document
        }
        response = requests.post(url, json=data, headers=self.headers)
        response.raise_for_status()
        return response.json()

# Usage
client = ZeroDBClient(
    api_url="https://api.ainative.studio",
    api_key="your-api-key-here"
)

# Create memory
memory = client.create_memory(
    title="Python Best Practices",
    content="Always use type hints for better code clarity",
    memory_type="code_snippet",
    priority="high",
    tags=["python", "best-practices"]
)
print(f"Memory created: {memory['id']}")

# Search memories
results = client.search_memories(
    query="python type hints",
    limit=5,
    memory_type="code_snippet"
)
print(f"Found {results['total_count']} memories")
```

### JavaScript/Node.js SDK

```javascript
const axios = require('axios');

class ZeroDBClient {
    constructor(apiUrl, apiKey) {
        this.apiUrl = apiUrl;
        this.headers = {
            'X-API-Key': apiKey,
            'Content-Type': 'application/json'
        };
    }

    async createMemory(title, content, type = 'note', priority = 'medium', tags = []) {
        const url = `${this.apiUrl}/v1/public/memory/`;
        const data = { title, content, type, priority, tags };
        const response = await axios.post(url, data, { headers: this.headers });
        return response.data;
    }

    async searchMemories(query, limit = 5, type = null) {
        const url = `${this.apiUrl}/v1/public/memory/search`;
        const data = { query, limit };
        if (type) data.type = type;

        const response = await axios.post(url, data, { headers: this.headers });
        return response.data;
    }

    async storeVector(projectId, embedding, namespace = 'default', metadata = {}, document = null) {
        const url = `${this.apiUrl}/v1/projects/${projectId}/database/vectors/upsert`;
        const data = {
            vector_embedding: embedding,
            namespace,
            metadata,
            document
        };
        const response = await axios.post(url, data, { headers: this.headers });
        return response.data;
    }
}

// Usage
const client = new ZeroDBClient(
    'https://api.ainative.studio',
    'your-api-key-here'
);

// Create memory
const memory = await client.createMemory(
    'JavaScript Best Practices',
    'Use const and let instead of var',
    'code_snippet',
    'high',
    ['javascript', 'best-practices']
);
console.log(`Memory created: ${memory.id}`);

// Search memories
const results = await client.searchMemories(
    'javascript const let',
    5,
    'code_snippet'
);
console.log(`Found ${results.total_count} memories`);
```

---

## Troubleshooting

### Authentication Issues

**Problem:** `401 Unauthorized`

**Solutions:**
1. Check API key is valid
2. Verify key is in correct header: `X-API-Key`
3. For JWT: Check token hasn't expired (30 min)
4. Try admin credentials: `admin@ainative.studio` / `Admin2025!Secure`

### Project Not Found

**Problem:** `404 Project not found`

**Solutions:**
1. Create project first before using endpoints
2. Verify project ID is correct UUID
3. Check user has access to project
4. List projects to find correct ID

### Vector Dimension Mismatch

**Problem:** Vector search returns no results

**Solutions:**
1. Ensure query vector has same dimensions as stored vectors
2. Check namespace matches
3. Lower similarity threshold
4. Verify vectors were stored successfully

### Event Stream Connection

**Problem:** SSE stream disconnects

**Solutions:**
1. Implement auto-reconnection on client
2. Check network stability
3. Monitor for keep-alive pings (every 30s)
4. Verify API key hasn't expired

### ZeroLocal Startup Issues

**Problem:** Services won't start

**Solutions:**
1. Check Docker is running: `docker ps`
2. Verify ports are available: `lsof -i :8000`
3. Run diagnostics: `zerodb doctor`
4. Check logs: `docker-compose logs`

---

## API Endpoints Summary

### Memory API (Enhanced)
- `POST /v1/public/memory/` - Create memory
- `GET /v1/public/memory/` - List memories
- `GET /v1/public/memory/{id}` - Get memory
- `PUT /v1/public/memory/{id}` - Update memory
- `DELETE /v1/public/memory/{id}` - Delete memory
- `POST /v1/public/memory/search` - Search memories
- `GET /v1/public/memory/statistics` - Get stats

### Vector Operations
- `POST /v1/projects/{id}/database/vectors/upsert` - Store vector
- `POST /v1/projects/{id}/database/vectors/search` - Search vectors
- `POST /v1/projects/{id}/database/vectors/upsert-batch` - Batch upsert
- `GET /v1/projects/{id}/database/vectors` - List vectors

### Table Operations
- `POST /v1/projects/{id}/database/tables` - Create table
- `GET /v1/projects/{id}/database/tables` - List tables
- `POST /v1/projects/{project_id}/database/tables/{table_name}/rows` - Create row
- `GET /v1/projects/{project_id}/database/tables/{table_name}/rows` - List rows
- `GET /v1/projects/{project_id}/database/tables/{table_name}/rows/{row_id}` - Get row
- `PUT /v1/projects/{project_id}/database/tables/{table_name}/rows/{row_id}` - Update row
- `DELETE /v1/projects/{project_id}/database/tables/{table_name}/rows/{row_id}` - Delete row

### Event Streaming
- `POST /v1/projects/{id}/database/events/publish` - Publish event
- `GET /v1/projects/{id}/database/events` - List events
- `GET /v1/projects/{id}/database/events/stream` - Stream events (SSE)

### Project Management
- `POST /v1/projects/` - Create project
- `GET /v1/projects/` - List projects
- `GET /v1/projects/{id}` - Get project
- `PUT /v1/projects/{id}` - Update project
- `DELETE /v1/projects/{id}` - Delete project

---

## Additional Resources

### Documentation
- **[Documentation Index](./ZERODB_DOCS_INDEX.md)** - Master index
- **[File Storage Guide](../api/ZERODB_FILE_STORAGE_GUIDE.md)** - S3-compatible storage
- **[Batch Operations](../api/ZERODB_BATCH_ENDPOINTS.md)** - Bulk operations
- **[MCP Integration](./ZBMCP.md)** - AI editor integration

### ZeroLocal
- **[Architecture](../zerodb-local/ARCHITECTURE.md)** - System design
- **[Quick Start](../zerodb-local/IMPLEMENTATION_SUMMARY.md)** - Setup guide
- **[CLI Reference](../zerodb-local/CLI_WIZARD_DESIGN.md)** - CLI commands

### Support
- **GitHub:** Create issue with `zerodb` label
- **Documentation:** Check index for specific topics
- **Community:** Join Discord for discussions

---

**Version:** 2.1.0
**Last Updated:** 2026-02-28
**Related Issues:** #1133, #1015, #1247
**Status:** ✅ Production Ready

