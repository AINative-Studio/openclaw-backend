# Credentials Management Guide

**CRITICAL SECURITY DOCUMENT**

This document describes how to securely manage credentials for the OpenClaw Backend platform.

## Table of Contents

1. [Security Principles](#security-principles)
2. [Required Environment Variables](#required-environment-variables)
3. [Optional Environment Variables](#optional-environment-variables)
4. [Environment-Specific Configuration](#environment-specific-configuration)
5. [Credential Generation](#credential-generation)
6. [Validation](#validation)
7. [Rotation Procedures](#rotation-procedures)
8. [Emergency Response](#emergency-response)
9. [Storage Best Practices](#storage-best-practices)

---

## Security Principles

### Zero Tolerance Rules

1. **NEVER** commit credentials to version control
2. **NEVER** share credentials via email, Slack, or unencrypted channels
3. **NEVER** use production credentials in development/testing
4. **NEVER** hardcode credentials in source code
5. **NEVER** reuse credentials across environments

### Defense in Depth

- Use different credentials for each environment (dev/staging/prod)
- Rotate credentials regularly (minimum quarterly)
- Use secret management services for production (Railway Secrets, AWS Secrets Manager, etc.)
- Enable audit logging for all credential access
- Implement least-privilege access control

---

## Required Environment Variables

These variables **MUST** be set for the application to start.

### Backend (Root `.env`)

| Variable | Description | Example | Generation |
|----------|-------------|---------|------------|
| `DATABASE_URL` | PostgreSQL connection string | `postgresql+asyncpg://user:pass@host:5432/db` | Provided by Railway/database host |
| `SECRET_KEY` | JWT signing key (min 32 chars) | `a1b2c3d4e5f6...` | `openssl rand -hex 32` |
| `OPENCLAW_GATEWAY_URL` | Gateway WebSocket URL | `ws://127.0.0.1:18789` | Configuration |
| `OPENCLAW_TOKEN` | Gateway auth token | `7ae5aa8730848791...` | `openssl rand -hex 32` |
| `ENVIRONMENT` | Environment mode | `development` | Configuration |

### Gateway (`openclaw-gateway/.env`)

| Variable | Description | Example | Generation |
|----------|-------------|---------|------------|
| `PGHOST` | PostgreSQL host | `yamabiko.proxy.rlwy.net` | Railway dashboard |
| `PGPORT` | PostgreSQL port | `51955` | Railway dashboard |
| `PGUSER` | PostgreSQL username | `postgres` | Railway dashboard |
| `PGPASSWORD` | PostgreSQL password | `xDelQr...` | Railway dashboard |
| `PGDATABASE` | PostgreSQL database name | `railway` | Railway dashboard |
| `PGSSLMODE` | PostgreSQL SSL mode | `disable` | `disable` for Railway |
| `PGCONNECT_TIMEOUT` | Connection timeout | `10` | `10` |
| `AUTH_TOKEN` | Gateway auth token | `openclaw-dev-token-12345` | `openssl rand -hex 32` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-api03-...` | Anthropic Console |
| `BACKEND_URL` | Backend API URL | `http://localhost:8000` | Configuration |

---

## Optional Environment Variables

These variables enable additional features but are not required for basic operation.

### AI Provider Keys

| Provider | Variable | How to Obtain |
|----------|----------|---------------|
| OpenAI | `OPENAI_API_KEY` | https://platform.openai.com/api-keys |
| Google Gemini | `GEMINI_API_KEY` | https://makersuite.google.com/app/apikey |
| Cohere | `COHERE_API_KEY` | https://dashboard.cohere.com/api-keys |
| Mistral | `MISTRAL_API_KEY` | https://console.mistral.ai/ |
| Hume AI | `HUME_API_KEY`, `HUME_SECRET_KEY` | https://platform.hume.ai/ |

### Cloud Services

| Service | Variables | How to Obtain |
|---------|-----------|---------------|
| AWS Braket | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | AWS IAM Console |
| MinIO | `MINIO_ACCESS_KEY`, `MINIO_SECRET_KEY` | MinIO admin console |
| Stripe | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY` | https://dashboard.stripe.com/apikeys |
| GitHub | `GITHUB_TOKEN`, `AGENT_SWARM_GITHUB_TOKEN` | https://github.com/settings/tokens |

### Third-Party APIs

| Service | Variables | How to Obtain |
|---------|-----------|---------------|
| Google Places | `GOOGLE_PLACES_API_KEY` | Google Cloud Console |
| SerpAPI | `SERPAPI_API_KEY` | https://serpapi.com/manage-api-key |
| Notion | `NOTION_API_KEY` | https://www.notion.so/my-integrations |
| Trello | `TRELLO_API_KEY`, `TRELLO_TOKEN` | https://trello.com/app-key |
| ElevenLabs | `ELEVENLABS_API_KEY` | https://elevenlabs.io/ |
| Figma | `FIGMA_PERSONAL_ACCESS_TOKEN` | Figma Settings |

### ZeroDB Integration

| Variable | Description | How to Obtain |
|----------|-------------|---------------|
| `ZERODB_API_URL` | ZeroDB API endpoint | Configuration |
| `ZERODB_API_KEY` | ZeroDB API key | ZeroDB dashboard |
| `ZERODB_PROJECT_ID` | ZeroDB project ID | ZeroDB dashboard |
| `ZERODB_USERNAME` | ZeroDB username | ZeroDB account |
| `ZERODB_PASSWORD` | ZeroDB password | ZeroDB account |

---

## Environment-Specific Configuration

### Development Environment

**File:** `.env`

```bash
ENVIRONMENT=development
DATABASE_URL=postgresql+asyncpg://postgres:local-dev-password@localhost:5432/openclaw_dev
SECRET_KEY=dev-secret-key-for-local-testing-only
OPENCLAW_TOKEN=openclaw-dev-token-12345

# Use test/sandbox API keys only
STRIPE_SECRET_KEY=sk_test_...
ANTHROPIC_API_KEY=sk-ant-api03-test-...
```

### Staging Environment

**Storage:** Railway Environment Variables (not in git)

```bash
ENVIRONMENT=staging
DATABASE_URL=postgresql+asyncpg://postgres:<staging-password>@staging-host:5432/openclaw_staging
SECRET_KEY=<generated-staging-secret>
OPENCLAW_TOKEN=<generated-staging-token>

# Use test/sandbox API keys
STRIPE_SECRET_KEY=sk_test_...
```

### Production Environment

**Storage:** Railway Environment Variables (not in git)

```bash
ENVIRONMENT=production
DATABASE_URL=postgresql+asyncpg://postgres:<production-password>@yamabiko.proxy.rlwy.net:51955/railway
SECRET_KEY=<generated-production-secret>
OPENCLAW_TOKEN=<generated-production-token>

# Use live API keys (with strict rate limits and monitoring)
STRIPE_SECRET_KEY=sk_live_...
ANTHROPIC_API_KEY=sk-ant-api03-prod-...
```

---

## Credential Generation

### Secret Keys

```bash
# Generate SECRET_KEY (64 characters hex)
openssl rand -hex 32

# Generate OPENCLAW_TOKEN (64 characters hex)
openssl rand -hex 32

# Generate ENCRYPTION_SECRET (base64 encoded, 32 bytes)
openssl rand -base64 32

# Generate AUTH_TOKEN for gateway (64 characters hex)
openssl rand -hex 32
```

### Database Passwords

```bash
# Generate secure database password (32 characters)
openssl rand -base64 24 | tr -d '/+=' | head -c 32
```

### API Keys

API keys are typically generated by the service provider:

1. **Anthropic:** https://console.anthropic.com/ → Account Settings → API Keys
2. **OpenAI:** https://platform.openai.com/api-keys → Create new secret key
3. **Stripe:** https://dashboard.stripe.com/apikeys → Create restricted key
4. **AWS:** IAM Console → Users → Security credentials → Create access key

---

## Validation

### Automatic Validation on Startup

Run the validation script before starting the application:

```bash
# Validate required credentials are present
python scripts/validate_credentials.py

# Output:
# ✅ All required credentials are present
# ⚠️  Optional credentials missing: GITHUB_TOKEN, STRIPE_SECRET_KEY
```

### Manual Validation

```bash
# Check .env file exists
ls -la .env openclaw-gateway/.env

# Verify DATABASE_URL format
echo $DATABASE_URL | grep -E '^postgresql\+asyncpg://'

# Test database connection
psql "$DATABASE_URL" -c "SELECT version();"

# Test gateway connection
curl http://localhost:18789/health
```

### Validation Checklist

- [ ] `.env` file exists and is not committed to git
- [ ] `openclaw-gateway/.env` exists and is not committed to git
- [ ] `DATABASE_URL` starts with `postgresql+asyncpg://`
- [ ] `SECRET_KEY` is at least 32 characters
- [ ] `OPENCLAW_TOKEN` matches between backend and gateway
- [ ] `AUTH_TOKEN` in gateway `.env` is secure (not default)
- [ ] PostgreSQL credentials are valid and connection succeeds
- [ ] No production credentials in development environment
- [ ] No hardcoded credentials in source code

---

## Rotation Procedures

### Regular Rotation Schedule

| Credential Type | Rotation Frequency | Priority |
|-----------------|-------------------|----------|
| Database passwords | Quarterly | Critical |
| JWT signing keys | Quarterly | Critical |
| API keys (production) | Semi-annually | High |
| Gateway auth tokens | Quarterly | High |
| API keys (development) | Annually | Medium |

### Emergency Rotation (Credential Exposure)

**IMMEDIATE ACTIONS (within 1 hour):**

1. **Revoke exposed credentials** at the provider
   - Database: Reset password in Railway dashboard
   - API keys: Delete/disable in provider console
   - Gateway tokens: Generate new tokens

2. **Generate new credentials**
   ```bash
   # Generate new secrets
   NEW_SECRET_KEY=$(openssl rand -hex 32)
   NEW_OPENCLAW_TOKEN=$(openssl rand -hex 32)
   NEW_AUTH_TOKEN=$(openssl rand -hex 32)
   ```

3. **Update all environments**
   - Development: Update local `.env` files
   - Staging: Update Railway environment variables
   - Production: Update Railway environment variables

4. **Restart all services**
   ```bash
   # Backend
   systemctl restart openclaw-backend

   # Gateway
   systemctl restart openclaw-gateway
   ```

5. **Verify operation**
   ```bash
   # Check health endpoints
   curl http://localhost:8000/health
   curl http://localhost:18789/health
   ```

**FOLLOW-UP ACTIONS (within 24 hours):**

1. Audit logs for unauthorized access
2. Review git history and remove exposed credentials
3. Force push to remove credentials from git history (if committed)
4. Notify security team and stakeholders
5. Update incident response documentation
6. Schedule post-mortem review

### Rotation Steps for Each Credential Type

#### Database Password

1. Create new password: `openssl rand -base64 24 | tr -d '/+=' | head -c 32`
2. Update Railway database password
3. Update `DATABASE_URL` in all environments
4. Restart backend and gateway services
5. Verify database connectivity

#### JWT Signing Key (SECRET_KEY)

1. Generate new key: `openssl rand -hex 32`
2. Update `SECRET_KEY` in all environments
3. **NOTE:** This will invalidate all existing JWT tokens
4. Restart backend service
5. Users will need to re-authenticate

#### Gateway Auth Token (OPENCLAW_TOKEN / AUTH_TOKEN)

1. Generate new token: `openssl rand -hex 32`
2. Update `OPENCLAW_TOKEN` in backend `.env`
3. Update `AUTH_TOKEN` in gateway `.env`
4. Restart both backend and gateway services
5. Verify communication between services

#### API Keys (Anthropic, OpenAI, etc.)

1. Generate new key in provider console
2. Update environment variable in all environments
3. Optionally: Keep old key active for 24 hours (grace period)
4. Restart backend service
5. Verify API calls succeed
6. Delete old key after grace period

---

## Emergency Response

### If Credentials Are Exposed in Git

**Severity: CRITICAL (CVE-2026-25253)**

#### Step 1: Immediate Revocation (< 1 hour)

```bash
# 1. Rotate ALL exposed credentials immediately
# - Railway PostgreSQL password (Railway dashboard)
# - All API keys (provider consoles)
# - All tokens and secrets (generate new)

# 2. Update .env files with new credentials (DO NOT COMMIT)
cp .env.example .env
# Edit .env with new values

cp openclaw-gateway/.env.example openclaw-gateway/.env
# Edit openclaw-gateway/.env with new values
```

#### Step 2: Remove from Git History (< 2 hours)

```bash
# WARNING: This rewrites git history. Coordinate with team first.

# Remove .env files from all commits
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env openclaw-gateway/.env" \
  --prune-empty --tag-name-filter cat -- --all

# Alternative: Use BFG Repo-Cleaner (faster)
# Download from: https://rtyley.github.io/bfg-repo-cleaner/
java -jar bfg.jar --delete-files .env
java -jar bfg.jar --delete-files openclaw-gateway/.env
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# Force push to remote (coordinate with team!)
git push origin --force --all
git push origin --force --tags
```

#### Step 3: Verify Removal (< 3 hours)

```bash
# Search git history for exposed credentials
git log -S "xDelQrUbmzAnRtgNqtNaNbaoAfKBftHM" --all
git log -S "sk-ant-api03" --all
git log -S "ghp_" --all

# Should return no results
```

#### Step 4: Update .gitignore (< 3 hours)

```bash
# Already done in this PR:
# - .env
# - .env.*
# - !.env.example
# - openclaw-gateway/.env
# - *.env.bak
```

#### Step 5: Notify Stakeholders (< 4 hours)

- Security team
- Engineering lead
- DevOps team
- Affected service providers (if data breach suspected)

#### Step 6: Audit and Monitor (< 24 hours)

```bash
# Check Railway database logs for unauthorized access
# Check API provider dashboards for unusual usage
# Check CloudWatch/Datadog for anomalies
# Review Stripe dashboard for unauthorized charges
```

---

## Storage Best Practices

### Development Environment

**Storage:** Local `.env` files (never committed)

```bash
# Create .env from template
cp .env.example .env
cp openclaw-gateway/.env.example openclaw-gateway/.env

# Edit files with actual values
nano .env
nano openclaw-gateway/.env

# Verify .env is in .gitignore
git check-ignore .env openclaw-gateway/.env
# Should output the file paths (meaning they're ignored)

# Never commit .env files
git status
# Should NOT show .env files
```

### Staging/Production Environment

**Storage:** Railway Environment Variables

1. Navigate to Railway dashboard
2. Select project → Environment (staging/production)
3. Click "Variables" tab
4. Add each environment variable individually
5. Railway automatically injects variables at runtime

**Advantages:**
- Encrypted at rest
- Access control via Railway permissions
- Audit logging
- Easy rollback
- No risk of committing to git

### CI/CD Pipelines

**Storage:** GitHub Secrets / Railway Secrets

1. **GitHub Actions:** Repository Settings → Secrets and variables → Actions
2. **Railway:** Automatically uses Railway environment variables

**Never:**
- Print credentials in logs
- Store credentials in build artifacts
- Use credentials in test suites (use mocks/stubs)

---

## Compliance

### OWASP Top 10 (2021)

This credential management approach addresses:

- **A02:2021 - Cryptographic Failures:** Secure storage, no hardcoded credentials
- **A05:2021 - Security Misconfiguration:** Environment-specific configs
- **A07:2021 - Identification and Authentication Failures:** Strong key generation

### CWE Mitigations

- **CWE-798:** Use of Hard-coded Credentials - MITIGATED
- **CWE-259:** Use of Hard-coded Password - MITIGATED
- **CWE-321:** Use of Hard-coded Cryptographic Key - MITIGATED
- **CWE-522:** Insufficiently Protected Credentials - MITIGATED

---

## Troubleshooting

### Backend won't start

**Error:** `ValueError: DATABASE_URL environment variable is required`

**Solution:** Ensure `.env` file exists with valid `DATABASE_URL`

```bash
cp .env.example .env
# Edit .env with actual DATABASE_URL
```

### Gateway won't connect to PostgreSQL

**Error:** `DBOSInitializationError: self-signed certificate in certificate chain`

**Solution:** Add `PGSSLMODE=disable` to `openclaw-gateway/.env`

```bash
echo "PGSSLMODE=disable" >> openclaw-gateway/.env
```

### Backend and Gateway can't communicate

**Error:** `Gateway authentication failed`

**Solution:** Ensure `OPENCLAW_TOKEN` matches in both `.env` files

```bash
# Backend .env
OPENCLAW_TOKEN=same-token-value-here

# Gateway .env
AUTH_TOKEN=same-token-value-here
```

### API calls fail with authentication errors

**Error:** `401 Unauthorized`

**Solution:** Verify API keys are valid and not expired

```bash
# Test Anthropic API key
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-3-sonnet-20240229","max_tokens":10,"messages":[{"role":"user","content":"test"}]}'
```

---

## References

- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [NIST Special Publication 800-63B](https://pages.nist.gov/800-63-3/sp800-63b.html)
- [CWE-798: Use of Hard-coded Credentials](https://cwe.mitre.org/data/definitions/798.html)
- [Railway Secrets Documentation](https://docs.railway.app/deploy/deployments#environment-variables)
- [12-Factor App: Config](https://12factor.net/config)

---

**Document Version:** 1.0
**Last Updated:** March 9, 2026
**Maintained By:** AINative Studio Security Team
**Classification:** Internal Use Only
