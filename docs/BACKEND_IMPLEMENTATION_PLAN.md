# OpenClaw Backend Implementation Plan

**Repository**: `openclaw-backend`
**Priority**: Phase 4 (Chat Persistence) → Phase 1 (Foundation) → Phase 2 (Workspace) → Phase 3 (Cron) → Phase 5 (Skills/Channels)
**Timeline**: 9 weeks (3 sprints per phase)

---

## Epic 1: Chat Persistence & Memory (Phase 4) - HIGHEST PRIORITY

**Goal**: Save all agent conversations in ZeroDB so context persists across sessions.

**Why First**: Context loss during dev is blocking. Every chat restart loses all history.

**Duration**: 2 weeks (Sprints 1-6)

---

### Sprint 1: ZeroDB Client & Infrastructure (Week 1, Days 1-3)

**Epic**: Chat Persistence
**Story Points**: 8

#### Story 1.1: Create ZeroDBClient Wrapper
**As a** backend developer
**I want** a reusable ZeroDB client wrapper
**So that** I can easily interact with ZeroDB API from any service

**Acceptance Criteria**:
- [ ] `backend/integrations/zerodb_client.py` created
- [ ] Methods: `create_project()`, `create_table()`, `create_table_row()`, `query_table()`, `create_memory()`, `search_memories()`
- [ ] Environment variables: `ZERODB_API_KEY`, `ZERODB_API_URL` (default: `https://api.ainative.studio`)
- [ ] Error handling with custom exceptions (`ZeroDBConnectionError`, `ZeroDBAPIError`)
- [ ] Unit tests with mocked responses (100% coverage)

**Tasks**:
```python
# File: backend/integrations/zerodb_client.py
class ZeroDBClient:
    def __init__(self, api_url: str, api_key: str)
    async def create_project(name: str, description: str) -> dict
    async def create_table(project_id: str, table_name: str) -> dict
    async def create_table_row(project_id: str, table_name: str, row_data: dict) -> dict
    async def query_table(project_id: str, table_name: str, limit: int, skip: int) -> List[dict]
    async def create_memory(title: str, content: str, type: str, tags: List[str], metadata: dict) -> dict
    async def search_memories(query: str, limit: int, type: str) -> dict
```

**Definition of Done**:
- ZeroDBClient passes all unit tests
- Can create projects/tables/rows via API
- Documented in docstrings

---

#### Story 1.2: Workspace Model with ZeroDB Integration
**As a** backend developer
**I want** a Workspace model linked to ZeroDB projects
**So that** each workspace has isolated storage

**Acceptance Criteria**:
- [ ] `backend/models/workspace.py` created
- [ ] Fields: `id`, `name`, `zerodb_project_id`, `created_at`, `updated_at`
- [ ] Relationship to `AgentSwarmInstance` (one-to-many)
- [ ] Alembic migration created and tested
- [ ] Seed script for default workspace

**Schema**:
```python
class Workspace(Base):
    __tablename__ = "workspaces"

    id = Column(UUID(), primary_key=True, default=uuid4)
    name = Column(String(255), nullable=False, unique=True, index=True)
    description = Column(Text, nullable=True)

    # ZeroDB integration
    zerodb_project_id = Column(String(255), nullable=True, unique=True, index=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    # Relationships
    agents = relationship("AgentSwarmInstance", back_populates="workspace")
    conversations = relationship("Conversation", back_populates="workspace")
```

**Definition of Done**:
- Migration runs without errors
- Can create workspaces via ORM
- Foreign keys enforced

---

#### Story 1.3: User Model (Minimal)
**As a** backend developer
**I want** a minimal User model
**So that** conversations can be attributed to users

**Acceptance Criteria**:
- [ ] `backend/models/user.py` created
- [ ] Fields: `id`, `email`, `workspace_id`, `created_at`
- [ ] Relationship to `Workspace` and `AgentSwarmInstance`
- [ ] Alembic migration
- [ ] Seed script for default user

**Schema**:
```python
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(), primary_key=True, default=uuid4)
    email = Column(String(255), nullable=False, unique=True, index=True)
    workspace_id = Column(UUID(), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)

    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    workspace = relationship("Workspace", back_populates="users")
    agents = relationship("AgentSwarmInstance", back_populates="user")
    conversations = relationship("Conversation", back_populates="user")
```

**Definition of Done**:
- User model exists
- Can create users via ORM
- Default user seeded

---

### Sprint 2: Conversation & Message Models (Week 1, Days 4-5)

**Epic**: Chat Persistence
**Story Points**: 5

#### Story 2.1: Conversation Model
**As a** backend developer
**I want** a Conversation model to track agent chat sessions
**So that** I can group messages by session

**Acceptance Criteria**:
- [ ] `backend/models/conversation.py` created
- [ ] Fields: `id`, `workspace_id`, `agent_id`, `user_id`, `openclaw_session_key`, `zerodb_table_name`, `zerodb_conversation_row_id`, `started_at`, `last_message_at`, `message_count`, `status`
- [ ] Alembic migration
- [ ] Unit tests

**Schema**:
```python
class ConversationStatus(str, Enum):
    ACTIVE = "active"
    ARCHIVED = "archived"
    DELETED = "deleted"

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(UUID(), primary_key=True, default=uuid4)
    workspace_id = Column(UUID(), ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_id = Column(UUID(), ForeignKey("agent_swarm_instances.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)

    # OpenClaw session tracking
    openclaw_session_key = Column(String(255), nullable=True, unique=True, index=True)

    # ZeroDB integration (messages stored in ZeroDB, not PostgreSQL)
    zerodb_table_name = Column(String(100), default="messages")
    zerodb_conversation_row_id = Column(String(255), nullable=True)  # UUID from ZeroDB

    started_at = Column(DateTime(timezone=True), server_default=func.now())
    last_message_at = Column(DateTime(timezone=True), nullable=True)
    message_count = Column(Integer, default=0)

    status = Column(
        SQLEnum(ConversationStatus, name="conversation_status"),
        default=ConversationStatus.ACTIVE,
        index=True
    )

    # Relationships
    workspace = relationship("Workspace", back_populates="conversations")
    agent = relationship("AgentSwarmInstance", back_populates="conversations")
    user = relationship("User", back_populates="conversations")
```

**Definition of Done**:
- Conversation model exists
- Migration successful
- Can create conversations with relationships

---

#### Story 2.2: Extend AgentSwarmInstance for Conversations
**As a** backend developer
**I want** AgentSwarmInstance linked to Workspace and Conversations
**So that** agents can have persistent chat history

**Acceptance Criteria**:
- [ ] Add `workspace_id` foreign key to `AgentSwarmInstance`
- [ ] Add `conversations` relationship
- [ ] Alembic migration
- [ ] Update seed data to link agents to default workspace

**Migration**:
```python
# Add to agent_swarm_lifecycle.py
workspace_id = Column(
    UUID(),
    ForeignKey("workspaces.id", ondelete="CASCADE"),
    nullable=True,  # Nullable for migration, then make NOT NULL after data migration
    index=True
)

# Relationships
workspace = relationship("Workspace", back_populates="agents")
conversations = relationship("Conversation", back_populates="agent", cascade="all, delete-orphan")
```

**Definition of Done**:
- `workspace_id` added
- Existing agents linked to default workspace
- Relationships working

---

### Sprint 3: Conversation Service (Week 2, Days 1-2)

**Epic**: Chat Persistence
**Story Points**: 5

#### Story 3.1: ConversationService - Create & Track
**As a** backend developer
**I want** a ConversationService to manage chat sessions
**So that** I can create/update conversations with ZeroDB integration

**Acceptance Criteria**:
- [ ] `backend/services/conversation_service.py` created
- [ ] Methods: `create_conversation()`, `get_conversation_by_session_key()`, `add_message()`, `get_messages()`, `archive_conversation()`
- [ ] Integrates with ZeroDBClient
- [ ] Unit tests with mocked ZeroDB (90%+ coverage)

**Implementation**:
```python
# backend/services/conversation_service.py

class ConversationService:
    def __init__(self, db: AsyncSession, zerodb_client: ZeroDBClient):
        self.db = db
        self.zerodb = zerodb_client

    async def create_conversation(
        self,
        workspace_id: UUID,
        agent_id: UUID,
        user_id: UUID,
        openclaw_session_key: str
    ) -> Conversation:
        """Create new conversation + ZeroDB conversation entry"""

        # 1. Get workspace ZeroDB project
        workspace = await self.db.get(Workspace, workspace_id)
        if not workspace.zerodb_project_id:
            raise ValueError("Workspace missing ZeroDB project")

        # 2. Create conversation record
        conversation = Conversation(
            workspace_id=workspace_id,
            agent_id=agent_id,
            user_id=user_id,
            openclaw_session_key=openclaw_session_key
        )
        self.db.add(conversation)
        await self.db.flush()  # Get ID before ZeroDB call

        # 3. Create conversation metadata in ZeroDB (optional tracking)
        # This is metadata only - actual messages go in messages table

        await self.db.commit()
        return conversation

    async def get_conversation_by_session_key(self, session_key: str) -> Optional[Conversation]:
        """Get conversation by OpenClaw session key"""
        result = await self.db.execute(
            select(Conversation).where(Conversation.openclaw_session_key == session_key)
        )
        return result.scalar_one_or_none()

    async def add_message(
        self,
        conversation_id: UUID,
        role: str,  # "user" or "assistant"
        content: str,
        metadata: dict = None
    ) -> dict:
        """Store message in ZeroDB"""

        conversation = await self.db.get(Conversation, conversation_id)
        if not conversation:
            raise ValueError(f"Conversation {conversation_id} not found")

        workspace = await self.db.get(Workspace, conversation.workspace_id)

        # 1. Store in ZeroDB messages table (structured)
        message_row = await self.zerodb.create_table_row(
            project_id=workspace.zerodb_project_id,
            table_name="messages",
            row_data={
                "conversation_id": str(conversation.id),
                "role": role,
                "content": content,
                "agent_id": str(conversation.agent_id),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {}
            }
        )

        # 2. ALSO store in ZeroDB Memory API (semantic search)
        agent = await self.db.get(AgentSwarmInstance, conversation.agent_id)
        await self.zerodb.create_memory(
            title=f"Chat with {agent.name} - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            content=content,
            type="conversation",
            priority="medium",
            tags=[
                f"conversation:{conversation.id}",
                f"agent:{agent.name}",
                f"role:{role}"
            ],
            metadata={
                "conversation_id": str(conversation.id),
                "message_id": message_row["row_id"],
                "agent_id": str(agent.id)
            }
        )

        # 3. Update conversation metadata
        conversation.message_count += 1
        conversation.last_message_at = datetime.now(timezone.utc)
        await self.db.commit()

        return message_row

    async def get_messages(
        self,
        conversation_id: UUID,
        limit: int = 50,
        offset: int = 0
    ) -> List[dict]:
        """Get messages from ZeroDB"""

        conversation = await self.db.get(Conversation, conversation_id)
        workspace = await self.db.get(Workspace, conversation.workspace_id)

        # Query ZeroDB messages table
        messages = await self.zerodb.query_table(
            project_id=workspace.zerodb_project_id,
            table_name="messages",
            limit=limit,
            skip=offset,
            filter={"conversation_id": str(conversation_id)}  # If ZeroDB supports filtering
        )

        return messages

    async def search_conversation_semantic(
        self,
        conversation_id: UUID,
        query: str,
        limit: int = 5
    ) -> dict:
        """Semantic search within conversation using ZeroDB Memory"""

        results = await self.zerodb.search_memories(
            query=query,
            limit=limit,
            type="conversation",
            tags=[f"conversation:{conversation_id}"]
        )

        return results
```

**Definition of Done**:
- ConversationService passes all tests
- Can create conversations
- Can add messages (dual storage: Table + Memory)
- Can retrieve messages

---

### Sprint 4: OpenClaw Bridge Integration (Week 2, Days 3-4)

**Epic**: Chat Persistence
**Story Points**: 5

#### Story 4.1: Integrate ConversationService into OpenClaw Bridge
**As a** backend developer
**I want** the OpenClaw bridge to auto-save all messages
**So that** chats persist without manual intervention

**Acceptance Criteria**:
- [ ] Modify `ProductionOpenClawBridge` to inject `ConversationService`
- [ ] On `send_message()`: create conversation if new, store user message
- [ ] On message received: store assistant response
- [ ] No breaking changes to existing bridge interface
- [ ] Integration tests

**Implementation**:
```python
# backend/agents/orchestration/production_openclaw_bridge.py

class ProductionOpenClawBridge:
    def __init__(
        self,
        url: str,
        token: str,
        db: AsyncSession,  # NEW
        zerodb_client: ZeroDBClient,  # NEW
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0
    ):
        self._base_bridge = BaseOpenClawBridge(url=url, token=token)
        self._db = db
        self._zerodb = zerodb_client
        self._conversation_service = ConversationService(db, zerodb_client)
        # ... existing init ...

    async def send_message(
        self,
        session_key: str,
        message: str,
        agent_id: UUID,  # NEW: need to track which agent
        user_id: UUID,  # NEW: need to track which user
        workspace_id: UUID  # NEW: need workspace context
    ) -> Dict[str, Any]:
        """Send message to OpenClaw Gateway + persist in ZeroDB"""

        # 1. Get or create conversation
        conversation = await self._conversation_service.get_conversation_by_session_key(session_key)

        if not conversation:
            # First message in this session - create conversation
            conversation = await self._conversation_service.create_conversation(
                workspace_id=workspace_id,
                agent_id=agent_id,
                user_id=user_id,
                openclaw_session_key=session_key
            )
            logger.info(f"Created conversation {conversation.id} for session {session_key}")

        # 2. Store user message in ZeroDB
        await self._conversation_service.add_message(
            conversation_id=conversation.id,
            role="user",
            content=message,
            metadata={"session_key": session_key}
        )

        # 3. Send to OpenClaw Gateway (existing logic)
        response = await self._base_bridge.send_message(session_key, message)

        # 4. Store assistant response in ZeroDB
        if response.get("success") and response.get("response"):
            await self._conversation_service.add_message(
                conversation_id=conversation.id,
                role="assistant",
                content=response["response"],
                metadata={
                    "session_key": session_key,
                    "model": response.get("model"),
                    "tokens_used": response.get("tokens_used")
                }
            )

        return response
```

**Definition of Done**:
- All messages auto-saved to ZeroDB
- No manual save calls needed
- Integration tests pass

---

#### Story 4.2: Update Agent Lifecycle Service
**As a** backend developer
**I want** AgentSwarmLifecycleService to pass context to bridge
**So that** agent/user/workspace IDs are available for conversation tracking

**Acceptance Criteria**:
- [ ] Modify `AgentSwarmLifecycleService` to inject `db` and `zerodb_client` into bridge
- [ ] Pass `agent_id`, `user_id`, `workspace_id` when calling `bridge.send_message()`
- [ ] Update provision workflow to create workspace if missing
- [ ] Tests updated

**Definition of Done**:
- Lifecycle service passes required context
- Bridge gets all needed IDs
- Tests pass

---

### Sprint 5: API Endpoints for Chat History (Week 2, Day 5)

**Epic**: Chat Persistence
**Story Points**: 3

#### Story 5.1: Conversation API Endpoints
**As a** frontend developer
**I want** API endpoints to retrieve chat history
**So that** I can display conversations in the UI

**Acceptance Criteria**:
- [ ] `backend/api/v1/endpoints/conversations.py` created
- [ ] Endpoints: `GET /conversations`, `GET /conversations/{id}`, `GET /conversations/{id}/messages`, `POST /conversations/{id}/search`
- [ ] Pydantic schemas for request/response
- [ ] OpenAPI docs auto-generated
- [ ] Tests (100% coverage)

**Endpoints**:
```python
# backend/api/v1/endpoints/conversations.py

from fastapi import APIRouter, Depends, Query
from backend.services.conversation_service import ConversationService

router = APIRouter(prefix="/conversations", tags=["Conversations"])

@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    agent_id: Optional[UUID] = Query(None),
    workspace_id: Optional[UUID] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: ConversationService = Depends(get_conversation_service)
):
    """List conversations with filters"""
    conversations, total = await service.list_conversations(
        agent_id=agent_id,
        workspace_id=workspace_id,
        status=status,
        limit=limit,
        offset=offset
    )
    return ConversationListResponse(
        conversations=[ConversationResponse.from_orm(c) for c in conversations],
        total=total,
        limit=limit,
        offset=offset
    )

@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    service: ConversationService = Depends(get_conversation_service)
):
    """Get conversation details"""
    conversation = await service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return ConversationResponse.from_orm(conversation)

@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    conversation_id: UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    service: ConversationService = Depends(get_conversation_service)
):
    """Get messages for conversation"""
    messages = await service.get_messages(conversation_id, limit, offset)
    return MessageListResponse(messages=messages, total=len(messages))

@router.post("/{conversation_id}/search", response_model=SearchResultsResponse)
async def search_conversation(
    conversation_id: UUID,
    request: SearchRequest,
    service: ConversationService = Depends(get_conversation_service)
):
    """Semantic search within conversation"""
    results = await service.search_conversation_semantic(
        conversation_id,
        request.query,
        request.limit or 5
    )
    return SearchResultsResponse(results=results)
```

**Schemas**:
```python
# backend/schemas/conversation.py

class ConversationResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    agent_id: UUID
    user_id: Optional[UUID]
    openclaw_session_key: Optional[str]
    started_at: datetime
    last_message_at: Optional[datetime]
    message_count: int
    status: str

    class Config:
        from_attributes = True

class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]
    total: int
    limit: int
    offset: int

class MessageResponse(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: str
    metadata: dict

class MessageListResponse(BaseModel):
    messages: List[MessageResponse]
    total: int

class SearchRequest(BaseModel):
    query: str
    limit: Optional[int] = 5

class SearchResultsResponse(BaseModel):
    results: dict  # ZeroDB Memory search results
```

**Definition of Done**:
- All endpoints implemented
- Schemas validated
- Tests pass (100%)
- OpenAPI docs generated

---

### Sprint 6: Testing & Documentation (Week 3, Days 1-2)

**Epic**: Chat Persistence
**Story Points**: 3

#### Story 6.1: Integration Tests for Chat Persistence
**As a** QA engineer
**I want** end-to-end integration tests
**So that** I can verify chat persistence works correctly

**Acceptance Criteria**:
- [ ] Test: Create workspace → Create agent → Send message → Retrieve message
- [ ] Test: Multiple messages in sequence
- [ ] Test: Semantic search finds relevant messages
- [ ] Test: Conversation archival
- [ ] Test: Error handling (ZeroDB down, invalid IDs)
- [ ] All tests pass

**Test File**:
```python
# tests/integration/test_chat_persistence_e2e.py

@pytest.mark.asyncio
async def test_complete_chat_persistence_flow():
    """End-to-end test: workspace → agent → chat → retrieve"""

    # 1. Create workspace with ZeroDB project
    workspace = await workspace_service.create_workspace("Test Workspace")
    assert workspace.zerodb_project_id is not None

    # 2. Create agent in workspace
    agent = await agent_service.create_agent(
        workspace_id=workspace.id,
        name="Test Agent",
        persona="Helpful assistant"
    )

    # 3. Send messages via OpenClaw bridge
    bridge = ProductionOpenClawBridge(url, token, db, zerodb_client)

    response1 = await bridge.send_message(
        session_key="test-session-1",
        message="Hello, agent!",
        agent_id=agent.id,
        user_id=default_user.id,
        workspace_id=workspace.id
    )

    response2 = await bridge.send_message(
        session_key="test-session-1",
        message="How are you?",
        agent_id=agent.id,
        user_id=default_user.id,
        workspace_id=workspace.id
    )

    # 4. Retrieve conversation
    conversation = await conversation_service.get_conversation_by_session_key("test-session-1")
    assert conversation is not None
    assert conversation.message_count == 4  # 2 user + 2 assistant

    # 5. Get messages
    messages = await conversation_service.get_messages(conversation.id)
    assert len(messages) == 4
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "Hello, agent!"

    # 6. Semantic search
    search_results = await conversation_service.search_conversation_semantic(
        conversation.id,
        query="greeting",
        limit=5
    )
    assert len(search_results["memories"]) > 0
```

**Definition of Done**:
- E2E test passes
- All edge cases covered
- Test coverage >90%

---

#### Story 6.2: Documentation for Chat Persistence
**As a** developer
**I want** clear documentation for chat persistence
**So that** I understand how it works

**Acceptance Criteria**:
- [ ] Update `CLAUDE.md` with chat persistence architecture
- [ ] Create `docs/CHAT_PERSISTENCE_GUIDE.md`
- [ ] API endpoint documentation (auto-generated from FastAPI)
- [ ] ZeroDB integration diagram

**Documentation Sections**:
- Architecture overview (PostgreSQL + ZeroDB hybrid)
- Data flow diagrams
- API endpoint reference
- ZeroDB table schemas
- Troubleshooting guide

**Definition of Done**:
- Documentation complete
- Diagrams created
- CLAUDE.md updated

---

## Epic 2: Foundation - Data Models & ZeroDB (Phase 1)

**Goal**: Build foundational data models and ZeroDB integration layer.

**Duration**: 2 weeks (Sprints 7-12)

---

### Sprint 7: Workspace Initialization Service (Week 3, Days 3-5)

**Epic**: Foundation
**Story Points**: 5

#### Story 7.1: WorkspaceService - CRUD Operations
**As a** backend developer
**I want** a WorkspaceService to manage workspaces
**So that** I can create/update/delete workspaces with ZeroDB projects

**Acceptance Criteria**:
- [ ] `backend/services/workspace_service.py` created
- [ ] Methods: `create_workspace()`, `get_workspace()`, `list_workspaces()`, `delete_workspace()`
- [ ] On create: auto-create ZeroDB project and messages table
- [ ] On delete: optionally delete ZeroDB project (with confirmation)
- [ ] Unit tests (90%+ coverage)

**Implementation**:
```python
# backend/services/workspace_service.py

class WorkspaceService:
    def __init__(self, db: AsyncSession, zerodb_client: ZeroDBClient):
        self.db = db
        self.zerodb = zerodb_client

    async def create_workspace(self, name: str, description: str = None) -> Workspace:
        """Create workspace + ZeroDB project"""

        # 1. Create ZeroDB project
        zerodb_project = await self.zerodb.create_project(
            name=f"Workspace: {name}",
            description=description or f"Agent workspace for {name}"
        )

        # 2. Create messages table in ZeroDB
        await self.zerodb.create_table(
            project_id=zerodb_project["id"],
            table_name="messages",
            description="Chat messages with agents"
        )

        # 3. Create workspace record
        workspace = Workspace(
            name=name,
            description=description,
            zerodb_project_id=zerodb_project["id"]
        )
        self.db.add(workspace)
        await self.db.commit()

        logger.info(f"Created workspace {workspace.id} with ZeroDB project {zerodb_project['id']}")
        return workspace

    async def get_workspace(self, workspace_id: UUID) -> Optional[Workspace]:
        return await self.db.get(Workspace, workspace_id)

    async def list_workspaces(self, limit: int = 50, offset: int = 0) -> Tuple[List[Workspace], int]:
        result = await self.db.execute(
            select(Workspace).limit(limit).offset(offset)
        )
        workspaces = result.scalars().all()

        count_result = await self.db.execute(select(func.count(Workspace.id)))
        total = count_result.scalar()

        return workspaces, total

    async def delete_workspace(self, workspace_id: UUID, delete_zerodb: bool = False) -> None:
        workspace = await self.db.get(Workspace, workspace_id)
        if not workspace:
            raise ValueError(f"Workspace {workspace_id} not found")

        # Optionally delete ZeroDB project (DANGEROUS - deletes all data)
        if delete_zerodb and workspace.zerodb_project_id:
            logger.warning(f"Deleting ZeroDB project {workspace.zerodb_project_id}")
            # await self.zerodb.delete_project(workspace.zerodb_project_id)
            # NOTE: Implement this carefully - data loss!

        await self.db.delete(workspace)
        await self.db.commit()
```

**Definition of Done**:
- WorkspaceService passes tests
- Can create/read/delete workspaces
- ZeroDB projects auto-created

---

### Sprint 8-12: Additional Foundation Work

**Remaining Stories** (detailed in separate issues):
- Agent workspace file metadata model (AgentWorkspaceFile)
- Cron job model (AgentCronJob) - preparation for Phase 3
- Skill model (AgentSkill) - preparation for Phase 5
- API endpoints for workspaces

---

## Epic 3: Workspace Files (Phase 2)

**Duration**: 1 week
**Stories**: AgentWorkspaceFile CRUD, file editor API, content sync with ZeroDB

---

## Epic 4: Cron Jobs (Phase 3)

**Duration**: 1 week
**Stories**: AgentCronJob CRUD, APScheduler integration, execution logging

---

## Epic 5: Skills & Channels (Phase 5)

**Duration**: 2 weeks
**Stories**: AgentSkill CRUD, channel bindings, logs endpoint, nodes endpoint

---

## Backlog Issues (GitHub Format)

### Issue #1: Create ZeroDBClient Wrapper
**Labels**: `enhancement`, `backend`, `epic:chat-persistence`, `sprint-1`
**Assignee**: Backend Team
**Story Points**: 3

**Description**:
Create a reusable ZeroDB client wrapper to interact with ZeroDB API.

**Acceptance Criteria**:
- [ ] `backend/integrations/zerodb_client.py` created
- [ ] Methods: create_project, create_table, create_table_row, query_table, create_memory, search_memories
- [ ] Environment variables configured
- [ ] Unit tests (100% coverage)

**Related**: Epic 1 - Chat Persistence

---

### Issue #2: Create Workspace Model with ZeroDB Integration
**Labels**: `enhancement`, `backend`, `database`, `epic:chat-persistence`, `sprint-1`
**Story Points**: 2

**Description**:
Create Workspace model with `zerodb_project_id` field to link workspaces to ZeroDB projects.

**Acceptance Criteria**:
- [ ] `backend/models/workspace.py` created
- [ ] Alembic migration tested
- [ ] Relationship to AgentSwarmInstance

**Related**: Epic 1 - Chat Persistence

---

### Issue #3: Create User Model (Minimal)
**Labels**: `enhancement`, `backend`, `database`, `epic:chat-persistence`, `sprint-1`
**Story Points**: 2

**Description**:
Create minimal User model for conversation attribution.

**Related**: Epic 1 - Chat Persistence

---

### Issue #4: Create Conversation Model
**Labels**: `enhancement`, `backend`, `database`, `epic:chat-persistence`, `sprint-2`
**Story Points**: 3

**Description**:
Create Conversation model to track agent chat sessions.

**Related**: Epic 1 - Chat Persistence

---

### Issue #5: Create ConversationService
**Labels**: `enhancement`, `backend`, `service`, `epic:chat-persistence`, `sprint-3`
**Story Points**: 5

**Description**:
Create ConversationService to manage chat sessions with dual storage (ZeroDB Table + Memory API).

**Related**: Epic 1 - Chat Persistence

---

### Issue #6: Integrate ConversationService into OpenClaw Bridge
**Labels**: `enhancement`, `backend`, `integration`, `epic:chat-persistence`, `sprint-4`
**Story Points**: 5

**Description**:
Modify ProductionOpenClawBridge to auto-save messages via ConversationService.

**Related**: Epic 1 - Chat Persistence

---

### Issue #7: Create Conversation API Endpoints
**Labels**: `enhancement`, `backend`, `api`, `epic:chat-persistence`, `sprint-5`
**Story Points**: 3

**Description**:
Create REST API endpoints for conversation retrieval and semantic search.

**Related**: Epic 1 - Chat Persistence

---

### Issue #8: Integration Tests for Chat Persistence
**Labels**: `testing`, `backend`, `epic:chat-persistence`, `sprint-6`
**Story Points**: 3

**Description**:
End-to-end integration tests for complete chat persistence flow.

**Related**: Epic 1 - Chat Persistence

---

### Issue #9: Documentation for Chat Persistence
**Labels**: `documentation`, `backend`, `epic:chat-persistence`, `sprint-6`
**Story Points**: 2

**Description**:
Create comprehensive documentation for chat persistence architecture.

**Related**: Epic 1 - Chat Persistence

---

## Summary

**Total Epics**: 5
**Total Sprints**: 18 (9 weeks)
**Total Story Points**: ~80

**Phase Priority**:
1. ✅ **Phase 4 (Chat Persistence)** - Weeks 1-3 (Critical for dev experience)
2. **Phase 1 (Foundation)** - Weeks 3-5
3. **Phase 2 (Workspace Files)** - Week 6
4. **Phase 3 (Cron Jobs)** - Week 7
5. **Phase 5 (Skills/Channels)** - Weeks 8-9

**Next Steps**:
1. Create issues in GitHub from backlog above
2. Assign Sprint 1 stories to dev team
3. Begin implementation of ZeroDBClient wrapper
