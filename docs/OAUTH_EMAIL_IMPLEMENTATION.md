# OAuth Email Channel Implementation

**Status**: ✅ Complete - Ready for Google OAuth App Registration
**Date**: March 4, 2026

## Overview

Implements Phase 4 of the Skills & OAuth roadmap: OAuth authentication flow for agent email channels. When users add an email to their agent configuration, the system now initiates a Google OAuth flow to securely obtain Gmail API access.

## Architecture

### Components Created

1. **AgentChannelCredentials Model** (`backend/models/agent_channel_credentials.py`)
   - Stores encrypted OAuth tokens for communication channels
   - Supports email, Slack, SMS, Discord channels
   - Fernet encryption for access/refresh tokens
   - JSONB metadata for non-sensitive data

2. **Pydantic Schemas** (`backend/schemas/agent_channel_auth.py`)
   - `OAuthStartRequest` / `OAuthStartResponse` - Initiate flow
   - `OAuthCallbackRequest` - Handle OAuth callback
   - `ChannelCredentialInfo` - Response without exposing tokens
   - `OAuthSuccessResponse` / `OAuthErrorResponse` - Status responses

3. **OAuth Endpoints** (`backend/api/v1/endpoints/agent_channels.py`)
   - `POST /api/v1/agents/{agent_id}/channels/email/authorize` - Start OAuth
   - `GET /api/v1/oauth/callback` - OAuth callback handler
   - `GET /api/v1/agents/{agent_id}/channels` - List channels
   - `DELETE /api/v1/agents/{agent_id}/channels/{channel_type}` - Revoke
   - `GET /api/v1/agents/{agent_id}/channels/{channel_type}` - Get channel

4. **Database Migration** (`alembic/versions/8cd88863aba6_add_agent_channel_credentials_table.py`)
   - Creates `agent_channel_credentials` table
   - Composite unique constraint on (agent_id, channel_type, provider)
   - Indexes on agent_id, channel_type, provider

## OAuth Flow

### Step 1: User Initiates OAuth

Frontend calls:
```typescript
POST /api/v1/agents/{agent_id}/channels/email/authorize
{
  "scopes": ["gmail.send", "gmail.readonly"] // optional
}
```

Backend returns:
```json
{
  "oauth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...",
  "state": "random-csrf-token"
}
```

### Step 2: User Grants Permissions

- Frontend opens `oauth_url` in popup or redirect
- User logs into Google and grants permissions
- Google redirects to `http://localhost:8000/api/v1/oauth/callback?code=...&state=...`

### Step 3: Backend Exchanges Code for Tokens

Callback handler:
1. Validates state token (CSRF protection)
2. Exchanges authorization code for access/refresh tokens
3. Fetches user email from Google
4. Stores encrypted tokens in database
5. Redirects to frontend: `http://localhost:3000/agents/{agent_id}?oauth=success`

### Step 4: Agent Uses Credentials

Agent runtime:
1. Queries `AgentChannelCredentials` by agent_id + channel_type
2. Decrypts access token
3. Makes Gmail API calls
4. Refreshes token if expired (using refresh_token)

## Database Schema

```sql
CREATE TABLE agent_channel_credentials (
    id UUID PRIMARY KEY,
    agent_id UUID REFERENCES agent_swarm_instances(id) ON DELETE CASCADE,
    channel_type VARCHAR(50) NOT NULL,  -- 'email', 'slack', etc.
    provider VARCHAR(50) NOT NULL,       -- 'google', 'microsoft', etc.
    credentials TEXT,                     -- Encrypted JSON (access_token, refresh_token)
    channel_metadata JSONB,               -- Non-sensitive (email address, scopes)
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ,
    UNIQUE (agent_id, channel_type, provider)
);

CREATE INDEX idx_agent_channel ON agent_channel_credentials(agent_id, channel_type);
CREATE INDEX idx_channel_provider ON agent_channel_credentials(channel_type, provider);
```

## Security Features

### 1. Fernet Encryption

Credentials are encrypted using `cryptography.fernet`:
- Symmetric encryption with key derived from `SECRET_KEY` env var
- SHA-256 hash of SECRET_KEY for consistent 32-byte key
- Base64-encoded ciphertext stored in database

### 2. CSRF Protection

OAuth state tokens:
- 32-byte random tokens via `secrets.token_urlsafe()`
- Stored in-memory with 5-minute TTL
- Validated on callback before token exchange
- One-time use (deleted after validation)

### 3. Token Storage

- Access tokens: Encrypted in `credentials` column
- Refresh tokens: Encrypted in `credentials` column (same blob)
- Metadata: Stored in plaintext JSONB (email address, scopes)
- Never logged or exposed in API responses

### 4. Least Privilege

OAuth scopes requested:
- `https://www.googleapis.com/auth/gmail.send` - Send emails only
- `https://www.googleapis.com/auth/gmail.readonly` - Read emails
- `https://www.googleapis.com/auth/userinfo.email` - Get user email address

## Environment Variables

Required in `.env`:

```bash
# OAuth Configuration
GOOGLE_CLIENT_ID=your-client-id-from-google-cloud-console
GOOGLE_CLIENT_SECRET=your-client-secret-from-google-cloud-console
BACKEND_URL=http://localhost:8000
FRONTEND_URL=http://localhost:3000

# Encryption Key (32+ characters)
SECRET_KEY=your-secret-key-here-32-chars-minimum
```

## Google OAuth App Setup

### Step 1: Create OAuth Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project or select existing
3. Enable Gmail API:
   - Go to "APIs & Services" > "Library"
   - Search "Gmail API"
   - Click "Enable"

### Step 2: Configure OAuth Consent Screen

1. Go to "OAuth consent screen"
2. Select "External" (for testing) or "Internal" (for organization)
3. Fill in:
   - App name: "AgentClaw"
   - User support email: your email
   - Developer contact: your email
4. Add scopes:
   - `https://www.googleapis.com/auth/gmail.send`
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/userinfo.email`
5. Add test users (if in testing mode)

### Step 3: Create OAuth Client

1. Go to "Credentials" > "Create Credentials" > "OAuth client ID"
2. Application type: "Web application"
3. Name: "AgentClaw Backend"
4. Authorized redirect URIs:
   - `http://localhost:8000/api/v1/oauth/callback` (development)
   - `https://your-domain.com/api/v1/oauth/callback` (production)
5. Click "Create"
6. Copy Client ID and Client Secret to `.env`

### Step 4: Test OAuth Flow

1. Start backend: `uvicorn backend.main:app --reload`
2. Call authorize endpoint:
   ```bash
   curl -X POST http://localhost:8000/api/v1/agents/{agent_id}/channels/email/authorize
   ```
3. Open returned `oauth_url` in browser
4. Grant permissions
5. Check database for stored credentials:
   ```sql
   SELECT id, agent_id, channel_type, provider, expires_at, created_at
   FROM agent_channel_credentials;
   ```

## API Examples

### Start OAuth Flow

```bash
curl -X POST http://localhost:8000/api/v1/agents/123e4567-e89b-12d3-a456-426614174000/channels/email/authorize \
  -H "Content-Type: application/json" \
  -d '{
    "scopes": [
      "https://www.googleapis.com/auth/gmail.send",
      "https://www.googleapis.com/auth/gmail.readonly"
    ]
  }'
```

Response:
```json
{
  "oauth_url": "https://accounts.google.com/o/oauth2/v2/auth?client_id=...",
  "state": "abc123..."
}
```

### List Configured Channels

```bash
curl http://localhost:8000/api/v1/agents/123e4567-e89b-12d3-a456-426614174000/channels
```

Response:
```json
{
  "credentials": [
    {
      "id": "550e8400-e29b-41d4-a716-446655440000",
      "agent_id": "123e4567-e89b-12d3-a456-426614174000",
      "channel_type": "email",
      "provider": "google",
      "has_credentials": true,
      "is_expired": false,
      "metadata": {
        "email_address": "agent@example.com",
        "scopes": ["gmail.send", "gmail.readonly"]
      },
      "expires_at": "2026-04-04T12:00:00Z",
      "created_at": "2026-03-04T12:00:00Z",
      "updated_at": "2026-03-04T12:00:00Z"
    }
  ]
}
```

### Get Channel Configuration

```bash
curl http://localhost:8000/api/v1/agents/123e4567-e89b-12d3-a456-426614174000/channels/email?provider=google
```

### Revoke Channel Access

```bash
curl -X DELETE http://localhost:8000/api/v1/agents/123e4567-e89b-12d3-a456-426614174000/channels/email?provider=google
```

## Token Refresh Implementation

When access token expires, implement refresh flow:

```python
from backend.models.agent_channel_credentials import AgentChannelCredentials
from backend.db.base import SessionLocal
import httpx
from datetime import datetime, timedelta, timezone

async def refresh_access_token(credential: AgentChannelCredentials) -> str:
    """
    Refresh expired access token using refresh token
    
    Returns:
        New access token
    """
    credentials = credential.get_credentials()
    refresh_token = credentials.get('refresh_token')
    
    if not refresh_token:
        raise ValueError("No refresh token available")
    
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10.0,
        )
        
        if response.status_code != 200:
            raise ValueError(f"Token refresh failed: {response.text}")
        
        token_data = response.json()
        new_access_token = token_data["access_token"]
        expires_in = token_data.get("expires_in", 3600)
        
        # Update stored credentials
        credentials["access_token"] = new_access_token
        credential.set_credentials(credentials)
        credential.expires_at = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
        
        db = SessionLocal()
        try:
            db.commit()
        finally:
            db.close()
        
        return new_access_token
```

## Frontend Integration

### React Example

```typescript
// Start OAuth flow
const startEmailOAuth = async (agentId: string) => {
  const response = await fetch(`/api/v1/agents/${agentId}/channels/email/authorize`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      scopes: [
        'https://www.googleapis.com/auth/gmail.send',
        'https://www.googleapis.com/auth/gmail.readonly',
      ],
    }),
  });
  
  const { oauth_url, state } = await response.json();
  
  // Open OAuth popup
  const width = 500;
  const height = 600;
  const left = (screen.width - width) / 2;
  const top = (screen.height - height) / 2;
  
  const popup = window.open(
    oauth_url,
    'Google OAuth',
    `width=${width},height=${height},left=${left},top=${top}`
  );
  
  // Wait for OAuth callback
  const checkClosed = setInterval(() => {
    if (popup?.closed) {
      clearInterval(checkClosed);
      // Refresh agent channels list
      fetchChannels(agentId);
    }
  }, 1000);
};

// List configured channels
const fetchChannels = async (agentId: string) => {
  const response = await fetch(`/api/v1/agents/${agentId}/channels`);
  const { credentials } = await response.json();
  setChannels(credentials);
};

// Revoke channel
const revokeChannel = async (agentId: string, channelType: string, provider: string) => {
  await fetch(`/api/v1/agents/${agentId}/channels/${channelType}?provider=${provider}`, {
    method: 'DELETE',
  });
  fetchChannels(agentId);
};
```

## Testing

Run test suite:
```bash
python3 /tmp/test_oauth_flow.py
```

Expected output:
```
✓ AgentChannelCredentials model imported successfully
✓ All OAuth schemas imported successfully
✓ agent_channels router imported successfully
✓ Credentials encrypted successfully
✓ Credentials decrypted successfully
✓ Metadata stored and retrieved successfully
✓ OAuth scopes configured correctly

✅ All tests passed! OAuth flow implementation is ready.
```

## Production Considerations

### 1. State Storage

Current implementation uses in-memory dict (`_oauth_state_store`). For production:

```python
# Replace with Redis
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

def _store_oauth_state(state: str, agent_id: UUID, channel_type: str, provider: str):
    redis_client.setex(
        f"oauth_state:{state}",
        300,  # 5 minutes TTL
        json.dumps({
            "agent_id": str(agent_id),
            "channel_type": channel_type,
            "provider": provider,
        })
    )

def _get_oauth_state(state: str) -> Optional[dict]:
    data = redis_client.get(f"oauth_state:{state}")
    if data:
        redis_client.delete(f"oauth_state:{state}")  # One-time use
        return json.loads(data)
    return None
```

### 2. HTTPS Required

- OAuth callback must use HTTPS in production
- Update redirect URI in Google Cloud Console
- Set `BACKEND_URL=https://api.your-domain.com` in production `.env`

### 3. Token Rotation

Implement background job to refresh tokens before expiration:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job('interval', hours=1)
async def refresh_expiring_tokens():
    """Refresh tokens expiring within 30 minutes"""
    db = SessionLocal()
    try:
        expiring_soon = db.query(AgentChannelCredentials).filter(
            AgentChannelCredentials.expires_at <= datetime.now(timezone.utc) + timedelta(minutes=30),
            AgentChannelCredentials.expires_at > datetime.now(timezone.utc),
        ).all()
        
        for credential in expiring_soon:
            try:
                await refresh_access_token(credential)
            except Exception as e:
                logger.error(f"Failed to refresh token for {credential.id}: {e}")
    finally:
        db.close()

scheduler.start()
```

### 4. Error Handling

- Handle token revocation (user revokes access in Google)
- Implement retry logic for transient failures
- Log OAuth errors for debugging
- Show user-friendly error messages in frontend

## Troubleshooting

### Error: "redirect_uri_mismatch"

- Check that redirect URI in Google Cloud Console exactly matches backend URL
- Common mistake: `http://localhost:8000` vs `http://localhost:8000/`
- Must include `/api/v1/oauth/callback` path

### Error: "invalid_client"

- Verify GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET are correct
- Check that OAuth client is not deleted in Google Cloud Console
- Ensure client secret hasn't been rotated

### Error: "access_denied"

- User denied permissions or closed OAuth popup
- Check that required scopes are authorized in Google Cloud Console
- Verify app is not in "testing" mode with user not added to test users

### Error: "TOKEN_EXCHANGE_FAILED"

- Check backend has internet access to reach Google OAuth servers
- Verify authorization code hasn't expired (10 minutes)
- Ensure client secret matches the one in Google Cloud Console

## Future Enhancements

1. **Microsoft OAuth** - Add support for Outlook/Office 365
2. **Slack OAuth** - Agent communication via Slack
3. **Discord OAuth** - Agent communication via Discord
4. **SMS via Twilio** - Agent sends SMS notifications
5. **Token Refresh UI** - Frontend button to manually refresh expired tokens
6. **Multi-Provider Support** - Allow multiple email providers per agent
7. **Webhook Support** - Receive emails via Gmail push notifications

## References

- [Google OAuth 2.0 Documentation](https://developers.google.com/identity/protocols/oauth2)
- [Gmail API Scopes](https://developers.google.com/gmail/api/auth/scopes)
- [Fernet Encryption](https://cryptography.io/en/latest/fernet/)
- [Implementation Plan](./SKILLS_AND_OAUTH_IMPLEMENTATION_PLAN.md)
