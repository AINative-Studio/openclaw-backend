# How to Add API Keys for Skills

**Status**: ✅ Feature Complete
**Last Updated**: 2026-03-04

---

## 📍 Where to Add API Keys

### Option 1: UI (Recommended) ✨

**NEW!** You can now add API keys directly from the frontend:

1. **Navigate to Agent Details**
   - Go to: `http://localhost:3000/agents/{agent-id}`
   - Example: `http://localhost:3000/agents/97b602d6-7ac2-422e-8c78-a073c9336fe2`

2. **Click the "Skills" Tab**
   - You'll see all 65 skills (49 CLI + 16 project)
   - Skills are filtered into: All / Ready / Missing

3. **Find Skills with "Configure" Button**
   - Skills needing API keys will have a blue **"Configure"** button
   - These are the 14 skills with missing environment variables:
     - **notion** - Notion API key
     - **goplaces** - Google Places API key
     - **local-places** - Google Places API key
     - **nano-banana-pro** - Gemini API key
     - **sag** - ElevenLabs API key
     - **sherpa-onnx-tts** - Sherpa ONNX runtime paths
     - **trello** - Trello API key + token
     - (and 7 more...)

4. **Click "Configure"**
   - A modal will open with an API key input field
   - Enter your API key
   - Click "Save Configuration"

5. **API Key is Encrypted and Stored**
   - Your API key is encrypted with Fernet (AES-128) before storage
   - The encryption key is derived from `SECRET_KEY` in `.env`
   - Nobody can read the plain-text key from the database ✅

---

## Option 2: API (Direct)

If you prefer to use the API directly:

```bash
# Configure Notion skill with API key
curl -X POST http://localhost:8000/api/v1/agents/{agent_id}/skills/notion/configure \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "secret_notionkey123456789",
    "enabled": true,
    "config": {
      "workspace_name": "My Workspace"
    }
  }'
```

**Response**:
```json
{
  "id": "uuid-here",
  "agent_id": "97b602d6-7ac2-422e-8c78-a073c9336fe2",
  "skill_name": "notion",
  "enabled": true,
  "has_credentials": true,
  "config": {
    "workspace_name": "My Workspace"
  },
  "created_at": "2026-03-04T12:00:00Z",
  "updated_at": null
}
```

Notice: The actual API key is **NOT** returned - only `has_credentials: true` flag.

---

## 🔐 Security Features

### Fernet Encryption

**Algorithm**: Fernet (symmetric encryption)
- Uses AES-128 in CBC mode
- HMAC (SHA-256) for authentication
- IV generated per encryption
- Timestamp included to prevent replay attacks

**Key Derivation**:
```python
# From SECRET_KEY environment variable
key_bytes = hashlib.sha256(SECRET_KEY.encode()).digest()
fernet_key = urlsafe_b64encode(key_bytes)
```

**Storage Format**:
```
credentials column (TEXT): "gAAAAABl..."  # Base64-encoded encrypted data
                           ^ 140 characters
```

### What's Encrypted vs Plain

**Encrypted** (in `credentials` column):
- API keys
- OAuth access tokens
- OAuth refresh tokens
- Passwords
- Client secrets

**Plain Text** (in `config` column):
- Workspace names
- Non-sensitive settings
- UI preferences
- Feature flags

---

## 📋 Skills That Need API Keys

### Auto-Detect Logic

The frontend detects skills needing API keys by checking:
```typescript
const needsApiKey = (skill: Skill): boolean => {
  // Skills with missing env variables need API keys
  return !!(skill.missing?.env && skill.missing.env.length > 0);
};
```

### Complete List (14 skills)

| Skill Name | Required API Key | How to Get |
|------------|------------------|------------|
| **notion** | NOTION_API_KEY | https://www.notion.so/my-integrations |
| **goplaces** | GOOGLE_PLACES_API_KEY | https://console.cloud.google.com/apis/credentials |
| **local-places** | GOOGLE_PLACES_API_KEY | Same as goplaces |
| **nano-banana-pro** | GEMINI_API_KEY | https://makersuite.google.com/app/apikey |
| **sag** | ELEVENLABS_API_KEY | https://elevenlabs.io/app/settings/api-keys |
| **sherpa-onnx-tts** | SHERPA_ONNX_RUNTIME_DIR<br>SHERPA_ONNX_MODEL_DIR | Install Sherpa-ONNX locally |
| **trello** | TRELLO_API_KEY<br>TRELLO_TOKEN | https://trello.com/app-key |
| **voice-call** | VOICE_CALL_PROVIDER | Slack/Teams/Zoom credentials |
| **summarize** | LLM_API_KEY | OpenAI/Anthropic API key |
| **oracle** | ORACLE_API_KEY | Oracle Cloud credentials |
| **model-usage** | PROVIDER_API_KEY | Various LLM providers |
| **nano-pdf** | PDF_API_KEY | PDF processing service |
| **obsidian** | OBSIDIAN_VAULT_PATH | Local Obsidian vault path |
| **gog** | GOG_API_KEY | GOG.com API credentials |

---

## 🧪 Testing

### Test Configuration

```bash
# 1. Configure a skill
curl -X POST http://localhost:8000/api/v1/agents/YOUR_AGENT_ID/skills/notion/configure \
  -H "Content-Type: application/json" \
  -d '{"api_key": "test_key_123", "enabled": true}'

# 2. Verify it's stored
curl http://localhost:8000/api/v1/agents/YOUR_AGENT_ID/skills/notion

# Expected response:
# {
#   "skill_name": "notion",
#   "enabled": true,
#   "has_credentials": true  ← API key is set (but not exposed)
# }

# 3. Check in database (should be encrypted)
# Connect to Railway PostgreSQL and run:
SELECT skill_name, enabled,
       LENGTH(credentials) as cred_length,
       LEFT(credentials, 20) as cred_preview
FROM agent_skill_configurations
WHERE agent_id = 'YOUR_AGENT_ID';

# Output:
# skill_name | enabled | cred_length | cred_preview
# -----------|---------|-------------|----------------------
# notion     | true    | 140         | gAAAAABl5Qj2mK7c...
```

### Verify Encryption

```bash
# The encrypted value should:
# - Start with "gAAAAAB" (Fernet format)
# - Be ~140 characters long
# - Change every time you update the key (new IV)
```

---

## 🎨 UI Components

### Files Created

1. **`/Users/aideveloper/agent-swarm-monitor/components/openclaw/SkillConfigureModal.tsx`**
   - Modal dialog for API key input
   - Password field (hidden input)
   - Success animation
   - Error handling

2. **`/Users/aideveloper/agent-swarm-monitor/components/openclaw/AgentSkillsTab.tsx`** (modified)
   - Added "Configure" button to skill cards
   - Added modal state management
   - Added `needsApiKey()` detection logic

### Component Tree

```
OpenClawAgentDetailClient
  └─ Tabs
      └─ TabsContent (Skills)
          └─ AgentSkillsTab ← agentId prop
              ├─ Skill Cards
              │   └─ Configure Button (if needsApiKey)
              └─ SkillConfigureModal
                  ├─ API Key Input (password)
                  ├─ Save Button
                  └─ Success/Error State
```

---

## 🔄 Data Flow

```
User clicks "Configure" button
    ↓
Modal opens with API key input
    ↓
User enters API key
    ↓
POST /api/v1/agents/{id}/skills/{skill}/configure
    ↓
Backend: Fernet.encrypt(api_key)
    ↓
Store in PostgreSQL (encrypted)
    ↓
Return response with has_credentials: true
    ↓
Modal shows success ✅
    ↓
Skills list refreshes
```

---

## 🚨 Common Issues

### Issue 1: "Configure" Button Not Showing

**Cause**: Skill doesn't have missing env variables

**Solution**: Check `skill.missing.env` array - only skills with env dependencies show the button

**Verify**:
```bash
curl http://localhost:8000/api/v1/skills/{skill_name} | jq '.missing.env'
```

### Issue 2: "Failed to configure skill"

**Cause**: Backend not running or SECRET_KEY missing

**Solution**:
```bash
# 1. Check backend is running
curl http://localhost:8000/health

# 2. Verify SECRET_KEY in .env
grep SECRET_KEY /Users/aideveloper/openclaw-backend/.env

# 3. Restart backend if needed
cd /Users/aideveloper/openclaw-backend
python3 -m uvicorn backend.main:app --reload --port 8000
```

### Issue 3: API Key Not Working in Skill

**Cause**: Skill needs to be reloaded or agent restarted

**Solution**: Restart the agent after configuring credentials

---

## 📱 Frontend Integration Checklist

- [x] SkillConfigureModal component created
- [x] Configure button added to skill cards
- [x] Modal state management
- [x] API integration (POST /configure)
- [x] Success/error handling
- [x] Encryption indicator in UI
- [x] Skills list refresh after config

---

## 🎯 What's Next

### Phase 2: Install Button (CLI Skills)

After API keys, the next phase is adding "Install" buttons for the 13 auto-installable CLI skills:

```
├─ bear-notes    → go install github.com/bearclaw/grizzly@latest
├─ bird          → go install github.com/openclaw/bird@latest
├─ blucli        → npm install -g blu
└─ ... (10 more)
```

### Phase 4: OAuth for Channels

Email/Slack OAuth flow for communication channels (already implemented in backend).

---

## 💡 Tips

1. **Test with Notion first** - It's the simplest (just one API key)
2. **Use `.env.example`** - All required keys are documented there
3. **Check logs** - Backend logs show encryption operations: `/tmp/uvicorn.log`
4. **Database inspection** - Connect to Railway PostgreSQL to verify encryption

---

## 📚 References

- Backend API Docs: `/Users/aideveloper/openclaw-backend/docs/PARALLEL_AGENTS_COMPLETION_SUMMARY.md`
- Encryption Implementation: `/Users/aideveloper/openclaw-backend/backend/models/agent_skill_configuration.py:86-112`
- Frontend Component: `/Users/aideveloper/agent-swarm-monitor/components/openclaw/SkillConfigureModal.tsx`

---

**You can now add API keys directly from the UI! 🎉**

Just click the "Configure" button on any skill card that needs an API key.
