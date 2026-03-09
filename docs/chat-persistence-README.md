# Chat Persistence Documentation

Complete documentation for the OpenClaw Backend chat persistence system.

## Documentation Overview

The chat persistence system provides durable storage for agent-user conversations with dual storage architecture (PostgreSQL + ZeroDB) enabling both efficient pagination and powerful semantic search.

### Documentation Files

| File | Description | Target Audience | Size |
|------|-------------|----------------|------|
| [**Architecture**](chat-persistence-architecture.md) | System design, data flow, components | Architects, Senior Developers | 24 KB |
| [**Setup Guide**](chat-persistence-setup.md) | Installation and configuration | DevOps, Developers | 24 KB |
| [**API Reference**](chat-persistence-api.md) | Endpoint documentation with examples | Frontend Developers, API Consumers | 20 KB |
| [**Semantic Search**](chat-persistence-semantic-search.md) | Natural language search guide | Developers, Product Managers | 21 KB |
| [**Troubleshooting**](chat-persistence-troubleshooting.md) | Common issues and solutions | Support Engineers, Developers | 30 KB |
| [**Migration Guide**](chat-persistence-migration.md) | Upgrade from non-persistent deployment | DevOps, Senior Developers | 24 KB |

**Total:** 5,109 lines of production-ready documentation

## Quick Start

### New Installation

1. **Read Architecture** → [chat-persistence-architecture.md](chat-persistence-architecture.md)
   - Understand dual storage design
   - Review data flow diagrams
   - Learn key design decisions

2. **Follow Setup Guide** → [chat-persistence-setup.md](chat-persistence-setup.md)
   - Configure environment variables
   - Run database migrations
   - Provision ZeroDB projects
   - Verify installation

3. **Test API** → [chat-persistence-api.md](chat-persistence-api.md)
   - Try example requests
   - Understand response schemas
   - Implement pagination

4. **Enable Search** → [chat-persistence-semantic-search.md](chat-persistence-semantic-search.md)
   - Learn query formulation
   - Understand score thresholds
   - Implement search features

### Existing Deployment

1. **Plan Migration** → [chat-persistence-migration.md](chat-persistence-migration.md)
   - Review pre-migration checklist
   - Backup existing data
   - Follow step-by-step migration
   - Verify post-migration

2. **Troubleshoot Issues** → [chat-persistence-troubleshooting.md](chat-persistence-troubleshooting.md)
   - Diagnose common problems
   - Apply proven solutions
   - Monitor system health

## Key Features

### Dual Storage Architecture

- **PostgreSQL:** Conversation metadata (workspaces, users, agents, message counts)
- **ZeroDB Tables:** Message content for efficient pagination
- **ZeroDB Memory:** Vector embeddings for semantic search

### Core Capabilities

- ✓ **Workspace Isolation:** Multi-tenant architecture with workspace-level data separation
- ✓ **Automatic Persistence:** Messages auto-persisted through OpenClaw Gateway bridge
- ✓ **Semantic Search:** Natural language queries using vector embeddings
- ✓ **Paginated Retrieval:** Efficient message pagination for long conversations
- ✓ **Graceful Degradation:** Continues working even if Memory API unavailable
- ✓ **RESTful API:** Complete API with filters, pagination, and search

## Architecture Highlights

```
User Message
    │
    ▼
ProductionOpenClawBridge (Auto-Persistence)
    │
    ├──► OpenClaw Gateway (WebSocket) ─────► Agent Processing
    │
    └──► ConversationService
            │
            ├──► PostgreSQL (Metadata)
            │      - Workspace, User, Conversation
            │      - Message count, timestamps
            │
            └──► ZeroDB (Content)
                   - Table: Paginated messages
                   - Memory: Semantic search vectors
```

## Common Use Cases

### 1. List All Conversations for an Agent

```bash
curl -X GET "http://localhost:8000/api/v1/conversations?agent_id={uuid}&status=active"
```

**See:** [API Reference - List Conversations](chat-persistence-api.md#1-list-conversations)

### 2. Retrieve Conversation Messages (Paginated)

```bash
curl -X GET "http://localhost:8000/api/v1/conversations/{id}/messages?limit=50&offset=0"
```

**See:** [API Reference - Get Messages](chat-persistence-api.md#3-get-conversation-messages)

### 3. Search Conversation with Natural Language

```bash
curl -X POST "http://localhost:8000/api/v1/conversations/{id}/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "How do I handle database errors?", "limit": 5}'
```

**See:** [Semantic Search Guide](chat-persistence-semantic-search.md)

### 4. Enable Persistence in Bridge

```python
from backend.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge

bridge = ProductionOpenClawBridge(
    url=gateway_url,
    token=gateway_token,
    db=db_session,           # Required for persistence
    zerodb_client=zerodb     # Required for persistence
)
```

**See:** [Setup Guide - Enable Persistence](chat-persistence-setup.md#step-7-update-backend-code)

## Troubleshooting Quick Links

| Issue | Documentation |
|-------|---------------|
| Messages not persisting | [Troubleshooting #1](chat-persistence-troubleshooting.md#1-messages-not-persisting) |
| Workspace missing ZeroDB project | [Troubleshooting #2](chat-persistence-troubleshooting.md#2-workspace-missing-zerodb-project) |
| ZeroDB connection failures | [Troubleshooting #3](chat-persistence-troubleshooting.md#3-zerodb-connection-failures) |
| Semantic search not working | [Troubleshooting #4](chat-persistence-troubleshooting.md#4-semantic-search-not-working) |
| Database connection issues | [Troubleshooting #5](chat-persistence-troubleshooting.md#5-database-connection-issues) |
| API 503 errors | [Troubleshooting #7](chat-persistence-troubleshooting.md#7-api-endpoint-503-errors) |

## Environment Requirements

### Required

- **Python:** 3.11+
- **PostgreSQL:** 14+ (async driver: asyncpg)
- **ZeroDB Account:** API key from [ainative.studio](https://ainative.studio)
- **OpenClaw Gateway:** DBOS-based WebSocket server

### Environment Variables

```bash
DATABASE_URL=postgresql+asyncpg://user:password@host:port/db
ZERODB_API_KEY=zdb_your_api_key_here
ZERODB_API_URL=https://api.ainative.studio
OPENCLAW_GATEWAY_URL=ws://localhost:18789
OPENCLAW_GATEWAY_TOKEN=your_token
```

**See:** [Setup Guide - Environment Variables](chat-persistence-setup.md#environment-variables)

## Database Schema

### Core Tables

- **workspaces:** Organizational boundaries (links to ZeroDB projects)
- **users:** Workspace members
- **conversations:** Conversation metadata (links workspace, agent, user, session)
- **agent_swarm_instances:** Extended with workspace relationship

**See:** [Architecture - PostgreSQL Storage](chat-persistence-architecture.md#1-postgresql-storage-layer)

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/conversations` | List conversations with filters |
| GET | `/api/v1/conversations/{id}` | Get single conversation |
| GET | `/api/v1/conversations/{id}/messages` | Get messages (paginated) |
| POST | `/api/v1/conversations/{id}/search` | Semantic search |

**See:** [API Reference](chat-persistence-api.md)

## Testing

### Unit Tests

```bash
pytest tests/services/test_conversation_service.py -v
pytest tests/api/v1/endpoints/test_conversations.py -v
```

### Integration Tests

```bash
pytest tests/agents/orchestration/test_production_openclaw_bridge_persistence.py -v
```

### End-to-End Test

```bash
python scripts/test_chat_persistence_e2e.py
```

**See:** [Setup Guide - Verification](chat-persistence-setup.md#verification)

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Message send (total) | ~140-270ms | Including gateway + persistence |
| Message pagination (50 msgs) | ~55-110ms | ZeroDB table query |
| Semantic search (5 results) | ~106-215ms | Vector similarity computation |

**See:** [Architecture - Performance](chat-persistence-architecture.md#performance-characteristics)

## Key Design Decisions

1. **Why Dual Storage?**
   - Table storage: Optimized for pagination (chronological display)
   - Memory storage: Optimized for semantic search (vector similarity)
   - Single storage can't efficiently support both use cases

2. **Why PostgreSQL + ZeroDB?**
   - PostgreSQL: ACID transactions, relational integrity, proven reliability
   - ZeroDB: Flexible schema, vector embeddings, scalable document storage

3. **Why Graceful Degradation?**
   - Gateway communication must never fail due to persistence issues
   - Memory API failures logged but don't block message delivery
   - Partial persistence better than no persistence

**See:** [Architecture - Design Decisions](chat-persistence-architecture.md#key-design-decisions)

## Security Considerations

- **Workspace Isolation:** All queries filtered by workspace_id
- **API Key Protection:** ZERODB_API_KEY in environment (never in code)
- **SQL Injection Prevention:** SQLAlchemy ORM prevents injection attacks
- **Cascading Deletes:** No orphaned data on workspace deletion

**See:** [Architecture - Security](chat-persistence-architecture.md#security-considerations)

## Monitoring

### Key Metrics

- Message persistence success rate
- ZeroDB API latency (p50, p95, p99)
- Memory storage degradation events
- Semantic search query performance

### Log Events

- `INFO`: Persistence enabled/disabled on bridge init
- `WARNING`: Memory storage failures (graceful degradation)
- `ERROR`: Table storage failures (hard failures)
- `DEBUG`: Message writes, conversation lookups

**See:** [Architecture - Monitoring](chat-persistence-architecture.md#monitoring-and-observability)

## Migration Checklist

For existing deployments upgrading to chat persistence:

- [ ] Backup database
- [ ] Provision ZeroDB account
- [ ] Update environment variables
- [ ] Run Alembic migrations
- [ ] Seed workspaces and users
- [ ] Link existing agents to workspaces
- [ ] Provision ZeroDB projects
- [ ] Update bridge initialization code
- [ ] Restart backend service
- [ ] Verify with test script
- [ ] Monitor for 24 hours

**See:** [Migration Guide](chat-persistence-migration.md)

## Support and Resources

### Documentation

- **Architecture:** Design decisions and data flow
- **Setup:** Installation and configuration
- **API:** Endpoint reference with examples
- **Search:** Semantic search usage guide
- **Troubleshooting:** Common issues and solutions
- **Migration:** Upgrade existing deployments

### External Resources

- [ZeroDB Documentation](https://ainative.studio/docs)
- [PostgreSQL Async Guide](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

### Getting Help

1. Check [Troubleshooting Guide](chat-persistence-troubleshooting.md)
2. Review relevant architecture documentation
3. Search GitHub issues for similar problems
4. Open new issue with diagnostic information

## Development Roadmap

### Implemented (v1.0)

- ✓ Dual storage architecture (PostgreSQL + ZeroDB)
- ✓ Automatic message persistence
- ✓ Semantic search with vector embeddings
- ✓ RESTful API with pagination
- ✓ Graceful degradation on failures
- ✓ Multi-workspace support

### Planned (v2.0)

- Message edit/delete with audit trail
- Conversation forking and branching
- Export to PDF/Markdown
- Full-text keyword search
- Message reactions and annotations
- Thread support (sub-conversations)
- Read receipts and delivery status
- Real-time WebSocket notifications

**See:** [Architecture - Future Enhancements](chat-persistence-architecture.md#future-enhancements)

## License

This documentation is part of the OpenClaw Backend project.

---

**Last Updated:** 2026-03-02
**Documentation Version:** 1.0
**Total Documentation:** 5,109 lines across 6 files
