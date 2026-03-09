# LLM Provider Support

**Issue**: #119 - Add Additional LLM Providers (Groq, Mistral, Ollama)
**Status**: ✅ Feature Complete
**Last Updated**: 2026-03-08

---

## Overview

The OpenClaw backend now supports **8 LLM providers** for workspace-level API key storage with encryption:

| Provider | Type | Authentication | Use Case |
|----------|------|----------------|----------|
| **Anthropic** | Cloud API | API Key | Claude models (Sonnet, Opus, Haiku) |
| **OpenAI** | Cloud API | API Key | GPT models (4, 4-turbo, 3.5) |
| **Cohere** | Cloud API | API Key | Command models, embeddings |
| **HuggingFace** | Cloud API | API Token | Open-source models, inference |
| **Google** | Cloud API | API Key | Gemini models |
| **Groq** ⭐ | Cloud API | API Key | Ultra-fast inference (Llama, Mixtral) |
| **Mistral** ⭐ | Cloud API | API Key | Mistral models (7B, 8x7B, Large) |
| **Ollama** ⭐ | Local/Self-hosted | Connection URL | Local model deployment |

⭐ = New providers added in Issue #119

---

## Quick Start

### 1. Add API Keys via API

```bash
# Add Groq API key
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "your-workspace-uuid",
    "provider": "groq",
    "api_key": "gsk_your_groq_api_key_here",
    "validate": true
  }'

# Add Mistral API key
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "your-workspace-uuid",
    "provider": "mistral",
    "api_key": "msk_your_mistral_api_key_here",
    "validate": true
  }'

# Add Ollama connection (local deployment)
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "your-workspace-uuid",
    "provider": "ollama",
    "api_key": "http://localhost:11434",
    "validate": true
  }'
```

### 2. List API Keys for Workspace

```bash
curl http://localhost:8000/api/v1/user-api-keys?workspace_id=your-workspace-uuid
```

**Response**:
```json
[
  {
    "id": "uuid-1",
    "provider": "groq",
    "masked_key": "gsk_***...5678",
    "is_active": true,
    "last_validated_at": "2026-03-08T10:30:00Z",
    "created_at": "2026-03-08T10:30:00Z"
  },
  {
    "id": "uuid-2",
    "provider": "mistral",
    "masked_key": "msk_***...9012",
    "is_active": true,
    "last_validated_at": "2026-03-08T10:31:00Z",
    "created_at": "2026-03-08T10:31:00Z"
  },
  {
    "id": "uuid-3",
    "provider": "ollama",
    "masked_key": "***...1434",
    "is_active": true,
    "last_validated_at": null,
    "created_at": "2026-03-08T10:32:00Z"
  }
]
```

---

## Provider Details

### Groq (Fast Inference)

**What is Groq?**
Groq provides ultra-fast LLM inference using custom LPU (Language Processing Unit) hardware. Ideal for real-time applications requiring low latency.

**Supported Models**:
- Llama 3.1 (8B, 70B, 405B)
- Mixtral 8x7B
- Gemma 2 (9B, 27B)

**Getting API Key**:
1. Visit https://console.groq.com/keys
2. Sign up / log in
3. Create new API key
4. Copy key (starts with `gsk_`)

**Key Format**: `gsk_` prefix + 40 alphanumeric characters

**Validation**:
```python
# Backend validates by calling Groq models.list() API
from groq import Groq

client = Groq(api_key=api_key)
models = client.models.list()
# Returns: True if valid, False if authentication fails
```

**Example Usage**:
```bash
# Add Groq key with validation
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "workspace-123",
    "provider": "groq",
    "api_key": "gsk_abc123...",
    "validate": true
  }'
```

**Benefits**:
- ⚡ Extremely fast inference (200+ tokens/sec)
- 💰 Competitive pricing
- 🔧 OpenAI-compatible API
- 📊 Supports function calling

---

### Mistral AI

**What is Mistral?**
Mistral AI provides state-of-the-art open-weight models with commercial-friendly licenses. Focus on multilingual capabilities and reasoning.

**Supported Models**:
- Mistral Small (7B)
- Mixtral 8x7B (MoE)
- Mistral Large (latest flagship)
- Codestral (code generation)

**Getting API Key**:
1. Visit https://console.mistral.ai/api-keys
2. Create account
3. Generate API key
4. Copy key (starts with `msk_` or similar)

**Key Format**: Variable format, typically `msk_` prefix

**Validation**:
```python
# Backend validates by calling Mistral models.list() API
from mistralai import Mistral

client = Mistral(api_key=api_key)
models = client.models.list()
# Returns: True if valid, False if authentication fails
```

**Example Usage**:
```bash
# Add Mistral key with validation
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "workspace-123",
    "provider": "mistral",
    "api_key": "msk_xyz789...",
    "validate": true
  }'
```

**Benefits**:
- 🌍 Multilingual (100+ languages)
- 📝 Strong reasoning capabilities
- 🔓 Open-weight models available
- 💼 Commercial-friendly licensing

---

### Ollama (Local Deployment)

**What is Ollama?**
Ollama enables running LLMs locally on your machine. No API keys needed - perfect for privacy-sensitive workloads or offline usage.

**Supported Models** (examples):
- Llama 3.1 (8B, 70B, 405B)
- Mistral (7B, Mixtral 8x7B)
- Phi-3 (3.8B)
- Gemma 2 (2B, 9B, 27B)
- CodeLlama (7B, 13B, 34B)

**Installation**:
```bash
# macOS / Linux
curl -fsSL https://ollama.com/install.sh | sh

# Or download from https://ollama.com/download

# Pull a model
ollama pull llama3.1:8b

# Start server (runs on localhost:11434 by default)
ollama serve
```

**Connection Format**: HTTP/HTTPS URL to Ollama server

**Validation**:
```python
# Backend validates by checking /api/tags endpoint
import httpx

response = httpx.get(f"{connection_url}/api/tags")
# Returns: True if server responds, False if connection fails
```

**Example Usage**:
```bash
# Add Ollama connection
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "workspace-123",
    "provider": "ollama",
    "api_key": "http://localhost:11434",
    "validate": true
  }'

# Custom host/port
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "workspace-123",
    "provider": "ollama",
    "api_key": "http://192.168.1.100:8080",
    "validate": false
  }'
```

**Benefits**:
- 🔒 Complete privacy (runs locally)
- 💻 No API costs
- 🌐 Works offline
- ⚙️ Customizable model parameters
- 🔧 OpenAI-compatible API

**Common Endpoints**:
- Default local: `http://localhost:11434`
- Custom port: `http://localhost:8080`
- Remote server: `http://192.168.1.100:11434`
- HTTPS: `https://ollama.example.com`

---

## Security Features

### Encryption at Rest

All API keys (except Ollama URLs which are connection strings) are encrypted using **Fernet symmetric encryption**:

```python
# Algorithm: Fernet (AES-128-CBC + HMAC-SHA256)
# - Random IV per encryption
# - Authenticated encryption
# - Timestamp included

from cryptography.fernet import Fernet

# Encryption key from environment
encryption_key = os.getenv("ENCRYPTION_SECRET")

# Encrypt API key
cipher = Fernet(encryption_key)
encrypted_key = cipher.encrypt(plaintext_key.encode())

# Store in database
user_api_key.encrypted_key = encrypted_key.decode()
```

### Key Hashing

SHA-256 hash stored alongside encrypted key for quick validation:

```python
import hashlib

key_hash = hashlib.sha256(plaintext_key.encode()).hexdigest()
# Stored in key_hash column (64 hex characters)
```

### Masked Display

API keys are never returned in plain text - only masked versions:

```python
# Examples of masked keys:
"sk-ant-***...1234"  # Anthropic
"sk-proj-***...5678" # OpenAI
"gsk_***...9012"     # Groq
"msk_***...3456"     # Mistral
"***...1434"         # Ollama URL
```

### Per-Workspace Isolation

- Each workspace has separate API keys
- Unique constraint: `(workspace_id, provider)`
- One key per provider per workspace

---

## API Reference

### Create API Key

**Endpoint**: `POST /api/v1/user-api-keys`

**Request**:
```json
{
  "workspace_id": "uuid-string",
  "provider": "groq" | "mistral" | "ollama" | "anthropic" | "openai" | "cohere" | "huggingface" | "google",
  "api_key": "plaintext-api-key-or-connection-url",
  "validate": true  // Optional: validate against provider API
}
```

**Response** (201 Created):
```json
{
  "id": "uuid",
  "workspace_id": "workspace-uuid",
  "provider": "groq",
  "masked_key": "gsk_***...1234",
  "is_active": true,
  "last_validated_at": "2026-03-08T10:30:00Z",
  "created_at": "2026-03-08T10:30:00Z",
  "updated_at": "2026-03-08T10:30:00Z"
}
```

**Error** (400 Bad Request):
```json
{
  "detail": "API key validation failed: Invalid Groq API key"
}
```

---

### List API Keys

**Endpoint**: `GET /api/v1/user-api-keys?workspace_id={uuid}`

**Response** (200 OK):
```json
[
  {
    "id": "uuid",
    "provider": "groq",
    "masked_key": "gsk_***...1234",
    "is_active": true,
    "last_validated_at": "2026-03-08T10:30:00Z",
    "created_at": "2026-03-08T10:30:00Z"
  }
]
```

---

### Update API Key

**Endpoint**: `PUT /api/v1/user-api-keys/{workspace_id}/{provider}`

**Request**:
```json
{
  "api_key": "new-api-key",
  "validate": true
}
```

**Response** (200 OK):
```json
{
  "id": "uuid",
  "workspace_id": "workspace-uuid",
  "provider": "groq",
  "masked_key": "gsk_***...5678",
  "is_active": true,
  "last_validated_at": "2026-03-08T11:00:00Z",
  "created_at": "2026-03-08T10:30:00Z",
  "updated_at": "2026-03-08T11:00:00Z"
}
```

---

### Delete API Key

**Endpoint**: `DELETE /api/v1/user-api-keys/{workspace_id}/{provider}`

**Response** (200 OK):
```json
{
  "success": true,
  "message": "API key deleted successfully",
  "deleted_id": "uuid"
}
```

---

### Test API Key

**Endpoint**: `POST /api/v1/user-api-keys/test`

**Request**:
```json
{
  "provider": "groq",
  "api_key": "gsk_test_key_12345"
}
```

**Response** (200 OK):
```json
{
  "provider": "groq",
  "is_valid": true,
  "message": "Groq API key is valid and authenticated successfully"
}
```

**Response** (200 OK - Invalid):
```json
{
  "provider": "groq",
  "is_valid": false,
  "message": "Invalid Groq API key"
}
```

---

## Testing

### Unit Tests

52 tests covering all 3 new providers:

```bash
# Run all user API key service tests
python -m pytest tests/services/test_user_api_key_service.py -v

# Run only new provider tests
python -m pytest tests/services/test_user_api_key_service.py::TestGroqProviderSupport -v
python -m pytest tests/services/test_user_api_key_service.py::TestMistralProviderSupport -v
python -m pytest tests/services/test_user_api_key_service.py::TestOllamaProviderSupport -v
```

**Test Coverage**:
- ✅ API key encryption/decryption
- ✅ Key masking (prefix detection)
- ✅ CRUD operations (add, get, update, delete)
- ✅ Validation against provider APIs
- ✅ Multi-provider support in same workspace
- ✅ Error handling for invalid keys
- ✅ Custom Ollama ports and hosts

### Integration Tests

```bash
# Test with real API keys (optional)
export GROQ_API_KEY="your-real-groq-key"
export MISTRAL_API_KEY="your-real-mistral-key"

# Run integration tests
python -m pytest tests/services/test_user_api_key_service.py \
  -k "test_validate_groq_key_valid or test_validate_mistral_key_valid" -v
```

### Manual Testing

```bash
# 1. Add Groq key
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "test-workspace",
    "provider": "groq",
    "api_key": "gsk_test_key",
    "validate": false
  }'

# 2. Verify it's encrypted in database
psql $DATABASE_URL -c \
  "SELECT provider, masked_key, left(encrypted_key, 20) as preview
   FROM user_api_keys
   WHERE workspace_id = 'test-workspace';"

# Expected output:
# provider | masked_key      | preview
# ---------|-----------------|--------------------
# groq     | gsk_***...tkey  | gAAAAABl5Qj2mK7c...
```

---

## Migration Guide

### From Environment Variables to Database Storage

**Before** (`.env` file):
```bash
GROQ_API_KEY=gsk_your_key_here
MISTRAL_API_KEY=msk_your_key_here
OLLAMA_URL=http://localhost:11434
```

**After** (Database):
```bash
# Add keys via API
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -H "Content-Type: application/json" \
  -d '{
    "workspace_id": "default-workspace",
    "provider": "groq",
    "api_key": "gsk_your_key_here"
  }'
```

**Benefits**:
- ✅ Per-workspace isolation
- ✅ Encryption at rest
- ✅ Easy rotation
- ✅ Audit trail (created_at, updated_at, last_validated_at)

---

## Troubleshooting

### SDK Not Installed

**Error**: `Groq SDK not installed. Install with: pip install groq`

**Solution**:
```bash
# Install Groq SDK
pip install groq

# Install Mistral SDK
pip install mistralai

# httpx already installed (used for Ollama)
```

### Connection Refused (Ollama)

**Error**: `Failed to connect to Ollama server at http://localhost:11434`

**Solution**:
```bash
# 1. Check if Ollama is running
curl http://localhost:11434/api/tags

# 2. Start Ollama if not running
ollama serve

# 3. Verify server is accessible
lsof -i :11434
```

### Invalid API Key

**Error**: `Invalid Groq API key`

**Solution**:
1. Verify key format (should start with `gsk_` for Groq, `msk_` for Mistral)
2. Check key is active in provider console
3. Test key directly with provider SDK
4. Ensure no trailing spaces or newlines

---

## Dependencies

### Python Packages

```bash
# Core encryption
cryptography>=40.0.0

# Provider SDKs (optional - for validation)
groq>=0.4.0              # Groq API
mistralai>=0.1.0         # Mistral AI API
httpx>=0.25.0            # Ollama connection (already installed)
```

### Installation

```bash
# Install all provider SDKs
pip install groq mistralai httpx

# Or add to requirements.txt
echo "groq>=0.4.0" >> requirements.txt
echo "mistralai>=0.1.0" >> requirements.txt
```

---

## Best Practices

### 1. Always Validate Keys

```python
# Use validate=True when adding keys
user_api_key_service.add_key(
    workspace_id="workspace-123",
    provider="groq",
    plaintext_key="gsk_...",
    validate=True  # ← Validates against Groq API
)
```

### 2. Rotate Keys Regularly

```bash
# Update existing key
curl -X PUT http://localhost:8000/api/v1/user-api-keys/workspace-123/groq \
  -H "Content-Type: application/json" \
  -d '{
    "api_key": "new-groq-key",
    "validate": true
  }'
```

### 3. Monitor Validation Timestamps

```sql
-- Check last validation times
SELECT provider, last_validated_at,
       AGE(NOW(), last_validated_at) as time_since_validation
FROM user_api_keys
WHERE workspace_id = 'workspace-123';
```

### 4. Use Ollama for Development

```bash
# Free, local, no API costs
ollama pull llama3.1:8b

# Add to workspace
curl -X POST http://localhost:8000/api/v1/user-api-keys \
  -d '{
    "workspace_id": "dev-workspace",
    "provider": "ollama",
    "api_key": "http://localhost:11434"
  }'
```

---

## Roadmap

### Future Enhancements

- [ ] Token usage tracking per provider
- [ ] Cost estimation and limits
- [ ] Automatic key rotation
- [ ] Provider health monitoring
- [ ] Fallback provider chains
- [ ] Model-specific routing

---

## References

- **Issue**: https://github.com/AINative-Studio/openclaw-backend/issues/119
- **Groq Docs**: https://console.groq.com/docs
- **Mistral Docs**: https://docs.mistral.ai/
- **Ollama Docs**: https://ollama.com/docs
- **Backend Service**: `/backend/services/user_api_key_service.py`
- **Database Model**: `/backend/models/user_api_key.py`
- **API Schema**: `/backend/schemas/user_api_key.py`
- **Tests**: `/tests/services/test_user_api_key_service.py`

---

**All 3 new LLM providers are now fully supported! 🎉**

Use `groq` for ultra-fast inference, `mistral` for multilingual reasoning, and `ollama` for local/private deployments.
