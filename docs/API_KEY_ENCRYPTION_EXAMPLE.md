# API Key Encryption - Storage Example

## Database Schema

The `api_keys` table structure:

```sql
CREATE TABLE api_keys (
    id UUID PRIMARY KEY,
    service_name VARCHAR(50) UNIQUE NOT NULL,
    encrypted_key BYTEA NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE INDEX ix_api_keys_service_name ON api_keys (service_name);
```

## Example Database Record

When storing an Anthropic API key `sk-ant-test-key-12345678`, the database record looks like:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "service_name": "anthropic",
  "encrypted_key": "gAAAAABl1234...random_ciphertext_bytes...5678==",
  "created_at": "2024-01-15T10:30:00.000Z",
  "updated_at": "2024-01-15T10:30:00.000Z",
  "is_active": true
}
```

**Key Security Features:**

1. **Fernet Encryption**: Uses AES-128-CBC + HMAC-SHA256
2. **Random IV**: Each encryption produces different ciphertext (even for same plaintext)
3. **Binary Storage**: `encrypted_key` stored as BYTEA (PostgreSQL) or BLOB (SQLite)
4. **Masked Responses**: API responses show only `sk-...5678` (last 4 chars)
5. **No Plaintext Logging**: Service layer never logs decrypted keys

## API Response Format

When retrieving API keys, responses are always masked:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "service_name": "anthropic",
  "masked_key": "sk-...5678",
  "created_at": "2024-01-15T10:30:00.000Z",
  "updated_at": "2024-01-15T10:30:00.000Z",
  "is_active": true
}
```

## Encryption Key Setup

Generate encryption key:

```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Set as environment variable:

```bash
export API_KEY_ENCRYPTION_KEY="G4BrVtXIG0Vog2InKO3yb_iuXuaMuBso_nFxxREqFFc="
```

**IMPORTANT**: Store this key securely (e.g., AWS Secrets Manager, HashiCorp Vault). Losing this key means all encrypted API keys become unrecoverable.

## Supported Services

- `anthropic` - Anthropic Claude API
- `openai` - OpenAI GPT API
- `cohere` - Cohere API
- `huggingface` - HuggingFace Hub API

## Security Guarantees

1. ✅ Keys encrypted at rest using Fernet symmetric encryption
2. ✅ Decrypted keys never appear in API responses
3. ✅ Decrypted keys never logged to stdout/stderr
4. ✅ Each service can only have one active key (enforced by unique constraint)
5. ✅ Key verification tests against actual service APIs without storing results
6. ✅ Database contains only ciphertext - no plaintext keys
7. ✅ Encryption includes authentication (HMAC prevents tampering)
