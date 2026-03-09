# IDOR (Insecure Direct Object References) Prevention - Issue #130

## Overview

This document describes the comprehensive authorization framework implemented to prevent IDOR vulnerabilities across all API endpoints in the OpenClaw backend.

**Status**: HIGH PRIORITY SECURITY FIX
**Date**: 2026-03-09
**Issue**: #130

## Problem Statement

Prior to this fix, many endpoints accepted resource IDs without verifying that the authenticated user had permission to access those resources. This allowed potential attackers to access or modify resources belonging to other users by simply guessing or enumerating UUIDs.

**Example Vulnerable Code** (BEFORE):
```python
@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: UUID, db: Session = Depends(get_db)):
    # Anyone can access any conversation if they know the UUID
    conversation = await service.get_conversation(conversation_id)
    return conversation
```

## Solution Architecture

### 1. Authorization Service (`backend/security/authorization_service.py`)

A centralized authorization service provides:

- **Workspace-level access control**: Verify user belongs to the correct workspace
- **User-level ownership verification**: Verify user owns the resource
- **Query filtering enforcement**: Prevent users from listing resources outside their scope
- **Resource-specific authorization**: Conversation, Agent, API Key, Swarm access checks

### 2. Authorization Helper Functions

**Standalone Functions** (for quick inline checks):
- `verify_conversation_access(conversation, current_user, require_ownership=True)`
- `verify_agent_access(agent, current_user, require_ownership=False)`
- `verify_workspace_access(resource_workspace_id, current_user, resource_type="resource")`

**Service-Based Methods** (for complex authorization):
- `AuthorizationService.verify_conversation_access()`
- `AuthorizationService.verify_agent_access()`
- `AuthorizationService.verify_user_api_key_access()`
- `AuthorizationService.verify_swarm_access()`
- `AuthorizationService.enforce_workspace_filter()`
- `AuthorizationService.enforce_user_filter()`

### 3. Custom Exception Types

```python
class AuthorizationError(HTTPException):
    """Base exception for authorization failures (403)"""

class WorkspaceAccessDeniedError(AuthorizationError):
    """Raised when user attempts to access resource from different workspace"""

class OwnershipDeniedError(AuthorizationError):
    """Raised when user attempts to access resource they don't own"""

class InsufficientPermissionsError(AuthorizationError):
    """Raised when user lacks required permissions"""
```

## Implementation Patterns

### Pattern 1: Read Operations (GET endpoints)

**For single resource retrieval**:
```python
@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),  # ✅ Require authentication
    service = Depends(get_conversation_service)
):
    # Fetch resource
    conversation = await service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Not found")

    # ✅ IDOR Prevention: Verify access
    verify_conversation_access(conversation, current_user, require_ownership=True)

    return ConversationResponse.model_validate(conversation)
```

### Pattern 2: List Operations (GET with filters)

**Enforce workspace/user filtering**:
```python
@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    workspace_id: Optional[UUID] = Query(None),
    current_user: User = Depends(get_current_active_user),  # ✅ Require authentication
    service = Depends(get_conversation_service)
):
    # ✅ IDOR Prevention: Enforce workspace filtering
    auth_service = AuthorizationService(db=await service.db)
    enforced_workspace_id = auth_service.enforce_workspace_filter(workspace_id, current_user)

    # Always use enforced workspace ID (prevents listing other workspaces)
    conversations, total = await service.list_conversations(
        workspace_id=enforced_workspace_id,  # ✅ Enforced, not user-provided
        limit=limit,
        offset=offset
    )

    return ConversationListResponse(conversations=conversations, total=total)
```

### Pattern 3: Create Operations (POST endpoints)

**Override user_id with authenticated user**:
```python
@router.post("", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    request: CreateConversationRequest,
    current_user: User = Depends(get_current_active_user),  # ✅ Require authentication
    service = Depends(get_conversation_service)
):
    # ✅ IDOR Prevention: Verify workspace access
    auth_service = AuthorizationService(db=await service.db)
    auth_service.verify_workspace_access(request.workspace_id, current_user, resource_type="workspace")

    # ✅ IDOR Prevention: Override user_id to prevent privilege escalation
    conversation = await service.create_conversation(
        workspace_id=request.workspace_id,
        agent_id=request.agent_id,
        user_id=current_user.id  # ✅ Always use authenticated user's ID, ignore request
    )

    return ConversationResponse.model_validate(conversation)
```

### Pattern 4: Update/Delete Operations (PUT/PATCH/DELETE endpoints)

**Require ownership for mutations**:
```python
@router.post("/{conversation_id}/archive", response_model=ConversationResponse)
async def archive_conversation(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),  # ✅ Require authentication
    service = Depends(get_conversation_service)
):
    # Fetch resource
    conversation = await service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Not found")

    # ✅ IDOR Prevention: Require ownership for mutations
    verify_conversation_access(conversation, current_user, require_ownership=True)

    # Now perform mutation
    conversation = await service.archive_conversation(conversation_id)
    return ConversationResponse.model_validate(conversation)
```

### Pattern 5: Nested Resource Access

**Verify parent resource access before child operations**:
```python
@router.get("/{conversation_id}/messages", response_model=MessageListResponse)
async def get_conversation_messages(
    conversation_id: UUID,
    current_user: User = Depends(get_current_active_user),  # ✅ Require authentication
    service = Depends(get_conversation_service)
):
    # ✅ IDOR Prevention: Verify parent resource access first
    conversation = await service.get_conversation(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    verify_conversation_access(conversation, current_user, require_ownership=True)

    # Now fetch child resources (messages)
    messages = await service.get_messages(conversation_id, limit, offset)
    total = await service.get_message_count(conversation_id)

    return MessageListResponse(messages=messages, total=total)
```

## Endpoints Fixed

### ✅ Fully Protected

#### `/conversations/*` (Issue #130)
- `GET /conversations` - Workspace filtering enforced
- `GET /conversations/{conversation_id}` - Ownership verification
- `GET /conversations/{conversation_id}/messages` - Ownership verification
- `POST /conversations/{conversation_id}/search` - Ownership verification
- `POST /conversations` - Workspace access + user_id override
- `POST /conversations/{conversation_id}/messages` - Ownership verification
- `POST /conversations/{conversation_id}/archive` - Ownership verification
- `GET /conversations/{conversation_id}/context` - Ownership verification
- `POST /conversations/{conversation_id}/attach-agent` - Ownership verification

#### `/agents/*` (Partially Protected - Issue #130)
- `GET /agents` - User/workspace filtering added
- `GET /agents/{agent_id}` - Workspace verification
- `POST /agents` - User ID override (authenticated user)
- `POST /agents/{agent_id}/provision` - Ownership verification

### ⚠️ Needs Protection

The following endpoints require similar authorization patterns:

#### `/api-keys/*` (System-level API keys)
**Authorization Logic**:
- System API keys should be admin-only (RBAC not yet implemented)
- For now, log warning but allow access (TODO: Add admin roles)

#### `/user-api-keys/*` (Workspace-scoped API keys)
**Authorization Logic**:
- List: Filter by workspace_id = current_user.workspace_id
- Get/Update/Delete: Verify workspace_id matches current_user.workspace_id
- Create: Always use current_user.workspace_id

#### `/swarms/*` (Agent Swarms)
**Authorization Logic**:
- List: Filter by user_id = current_user.id
- Get: Verify user_id matches current_user.id
- Create/Update/Delete: Verify user_id matches current_user.id
- Add/Remove Agents: Verify user_id matches current_user.id

#### `/agents/{agent_id}/pause` and other lifecycle endpoints
**Authorization Logic**:
- Fetch agent first
- Verify workspace access (workspace_id)
- Require ownership for mutations (user_id)

#### `/channels/*` (Channel configurations)
**Authorization Logic**:
- If workspace-scoped: Verify workspace_id
- If user-scoped: Verify user_id

## Testing Approach

### Unit Tests

Test the authorization service in isolation:

```python
def test_verify_workspace_access_denies_different_workspace(db_session):
    """User A cannot access resources from workspace B"""
    user_a = User(id=uuid4(), workspace_id=uuid4())
    resource_workspace_id = uuid4()  # Different workspace

    auth_service = AuthorizationService(db_session)

    with pytest.raises(WorkspaceAccessDeniedError):
        auth_service.verify_workspace_access(
            resource_workspace_id,
            user_a,
            resource_type="conversation"
        )

def test_verify_user_ownership_denies_different_owner(db_session):
    """User A cannot access resources owned by user B"""
    user_a = User(id=uuid4())
    resource_user_id = uuid4()  # Different user

    auth_service = AuthorizationService(db_session)

    with pytest.raises(OwnershipDeniedError):
        auth_service.verify_user_ownership(
            resource_user_id,
            user_a,
            resource_type="conversation"
        )
```

### Integration Tests

Test endpoint authorization end-to-end:

```python
async def test_get_conversation_blocks_unauthorized_access(client, db_session):
    """User A cannot access user B's conversation"""
    # Create user A with workspace 1
    user_a = await create_user(workspace_id=workspace1_id)
    token_a = create_access_token({"sub": str(user_a.id)})

    # Create user B with workspace 1
    user_b = await create_user(workspace_id=workspace1_id)

    # Create conversation owned by user B
    conversation = await create_conversation(
        user_id=user_b.id,
        workspace_id=workspace1_id
    )

    # User A attempts to access user B's conversation
    response = await client.get(
        f"/conversations/{conversation.id}",
        headers={"Authorization": f"Bearer {token_a}"}
    )

    # Should return 403 Forbidden (not 200 or 404)
    assert response.status_code == 403
    assert "Access denied" in response.json()["detail"]


async def test_list_conversations_filters_by_workspace(client, db_session):
    """Users only see conversations from their workspace"""
    # Create two workspaces
    workspace1 = await create_workspace()
    workspace2 = await create_workspace()

    # Create user in workspace 1
    user1 = await create_user(workspace_id=workspace1.id)
    token1 = create_access_token({"sub": str(user1.id)})

    # Create conversations in workspace 1 and 2
    conv1 = await create_conversation(workspace_id=workspace1.id, user_id=user1.id)
    conv2 = await create_conversation(workspace_id=workspace2.id)

    # User 1 lists conversations
    response = await client.get(
        "/conversations",
        headers={"Authorization": f"Bearer {token1}"}
    )

    assert response.status_code == 200
    conversations = response.json()["conversations"]

    # Should only see conversation from workspace 1
    assert len(conversations) == 1
    assert conversations[0]["id"] == str(conv1.id)
    assert str(conv2.id) not in [c["id"] for c in conversations]
```

## Security Best Practices

### 1. Always Require Authentication

Every endpoint that accesses resources MUST require authentication:

```python
# ✅ Good
async def get_resource(
    resource_id: UUID,
    current_user: User = Depends(get_current_active_user),  # Required
    db: Session = Depends(get_db)
):
    ...

# ❌ Bad - Missing authentication
async def get_resource(
    resource_id: UUID,
    db: Session = Depends(get_db)
):
    ...
```

### 2. Verify Before Mutate

Always fetch and verify ownership BEFORE performing mutations:

```python
# ✅ Good - Check ownership first
conversation = await service.get_conversation(conversation_id)
verify_conversation_access(conversation, current_user, require_ownership=True)
await service.archive_conversation(conversation_id)

# ❌ Bad - Mutate without checking
await service.archive_conversation(conversation_id)
```

### 3. Override User-Provided IDs

Never trust user_id or workspace_id from request body:

```python
# ✅ Good - Override with authenticated user
conversation = await service.create_conversation(
    workspace_id=request.workspace_id,  # Verify this matches user's workspace
    user_id=current_user.id  # Always use authenticated user's ID
)

# ❌ Bad - Trust user-provided ID
conversation = await service.create_conversation(
    workspace_id=request.workspace_id,
    user_id=request.user_id  # Attacker can impersonate other users!
)
```

### 4. Enforce Filtering on List Endpoints

Never let users specify workspace/user filters without validation:

```python
# ✅ Good - Enforce workspace filter
auth_service = AuthorizationService(db)
enforced_workspace_id = auth_service.enforce_workspace_filter(
    requested_workspace_id,
    current_user
)
conversations = await service.list_conversations(workspace_id=enforced_workspace_id)

# ❌ Bad - Trust user-provided filter
conversations = await service.list_conversations(workspace_id=request.workspace_id)
```

### 5. Return 403 for Authorization Failures

When authorization fails, return 403 Forbidden (not 404):

```python
# ✅ Good - Explicit 403 on authorization failure
conversation = await service.get_conversation(conversation_id)
if not conversation:
    raise HTTPException(status_code=404, detail="Not found")

verify_conversation_access(conversation, current_user)  # Raises 403 on failure

# ❌ Bad - Returns 404 for both missing and unauthorized
conversation = await service.get_conversation_with_access_check(
    conversation_id, current_user
)
if not conversation:
    raise HTTPException(status_code=404, detail="Not found")  # Ambiguous
```

## Migration Checklist

For each endpoint that accepts resource IDs:

- [ ] Add `current_user: User = Depends(get_current_active_user)` parameter
- [ ] Import authorization functions: `from backend.security.authorization_service import ...`
- [ ] For GET (single resource): Add `verify_{resource}_access()` after fetching
- [ ] For GET (list): Add `enforce_workspace_filter()` or `enforce_user_filter()`
- [ ] For POST (create): Override `user_id` with `current_user.id`
- [ ] For POST/PUT/PATCH/DELETE (mutate): Verify ownership with `require_ownership=True`
- [ ] Add integration tests verifying IDOR protection
- [ ] Update API documentation with authorization requirements

## Related Files

- `/backend/security/authorization_service.py` - Core authorization logic
- `/backend/security/auth_service.py` - Authentication (JWT, passwords)
- `/backend/security/auth_dependencies.py` - FastAPI dependencies
- `/backend/models/user.py` - User model with workspace relationship
- `/backend/models/workspace.py` - Workspace model
- `/docs/IDOR_PREVENTION.md` - This document

## Future Enhancements

1. **Role-Based Access Control (RBAC)**
   - Add `role` field to User model (OWNER, ADMIN, MEMBER, VIEWER)
   - Implement role-based permission checks
   - System-level API keys should require ADMIN role

2. **Team-Level Access Control**
   - Allow users to share conversations/agents with team members
   - Implement `TeamMember` relationships for fine-grained sharing
   - Add "shared with me" filters

3. **Audit Logging**
   - Log all authorization failures for security monitoring
   - Track access patterns to detect anomalies
   - Use `SecurityAuditLogger` from Epic E7

4. **Rate Limiting**
   - Implement rate limiting per user/IP to prevent enumeration attacks
   - Throttle failed authorization attempts

## Conclusion

This IDOR prevention framework provides comprehensive protection against unauthorized resource access. All endpoints MUST follow these patterns to maintain security. When adding new endpoints, always apply the appropriate authorization pattern from this document.

**Priority**: HIGH - This is a critical security fix that prevents unauthorized data access and modification.
