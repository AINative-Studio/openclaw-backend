# AgentSwarm - Repository & Infrastructure Guide

**Document Type**: Infrastructure Reference
**Last Updated**: December 5, 2025
**Purpose**: Complete guide to repositories, deployment, and infrastructure

---

## 📋 Table of Contents

1. [Repository Structure](#repository-structure)
2. [GitHub Repositories](#github-repositories)
3. [Deployment Infrastructure](#deployment-infrastructure)
4. [Environment Variables](#environment-variables)
5. [Storage Architecture](#storage-architecture)
6. [CI/CD Pipelines](#cicd-pipelines)
7. [Local Development Setup](#local-development-setup)
8. [Production Deployment](#production-deployment)
9. [Monitoring & Logging](#monitoring--logging)
10. [Disaster Recovery](#disaster-recovery)

---

## 📁 Repository Structure

### Main Monorepo

**Repository**: `github.com/relycapital/core` (Private)
**Type**: Monorepo
**Purpose**: Contains all AINative platform code including AgentSwarm

```
/Users/aideveloper/core/
├── src/backend/              # FastAPI backend
│   ├── app/
│   │   ├── agents/swarm/     # AgentSwarm core (61,728 lines)
│   │   ├── api/
│   │   │   └── api_v1/endpoints/agent_swarms.py
│   │   ├── services/
│   │   │   ├── project_github_service.py
│   │   │   └── zerodb_integration_service.py
│   │   ├── models/
│   │   │   ├── agent_swarm_workflow.py
│   │   │   └── agent_swarm_rules.py
│   │   └── websocket/
│   │       └── agent_swarm_ws.py
│   ├── tests/
│   │   ├── e2e/test_agent_swarm_e2e.py
│   │   ├── integration/
│   │   └── unit/
│   ├── alembic/              # Database migrations
│   ├── AgentSwarm-Workflow.md # Official 11-stage spec (2,643 lines)
│   └── requirements.txt      # Python dependencies
│
├── AINative-website/         # React frontend (separate repo reference)
│   ├── src/
│   │   ├── pages/dashboard/AgentSwarmDashboard.tsx
│   │   ├── components/       # 8 UI components
│   │   └── services/AgentSwarmService.ts
│   └── tests/e2e/            # Playwright tests
│
├── developer-tools/sdks/     # Language SDKs
│   ├── typescript/           # TypeScript SDK
│   ├── python/               # Python SDK
│   └── go/                   # Go SDK
│
├── docs/agent-swarm/         # AgentSwarm documentation (36 files)
│   ├── README.md
│   ├── AGENTSWARM_MASTER_CONTEXT.md
│   ├── AGENTSWARM_HISTORY.md
│   ├── AGENTSWARM_FILE_MAP.md
│   ├── AGENTSWARM_REPOSITORY_GUIDE.md (this file)
│   ├── architecture/
│   ├── api/
│   ├── guides/
│   ├── planning/
│   ├── reports/
│   ├── storage/
│   ├── testing/
│   ├── troubleshooting/
│   ├── configuration/
│   └── videos/
│
└── .github/workflows/        # CI/CD pipelines
    ├── agent-swarm-ci.yml
    └── agent-swarm-deploy.yml
```

---

## 🐙 GitHub Repositories

### Primary Repositories

#### 1. Backend Repository

**Name**: `relycapital/core`
**Visibility**: Private
**Purpose**: AINative platform backend (includes AgentSwarm)
**URL**: `github.com/relycapital/core`
**Default Branch**: `main`

**Key Directories**:
```
src/backend/
├── app/agents/swarm/         # AgentSwarm implementation
├── app/api/api_v1/endpoints/ # Public API endpoints
└── tests/                    # Test suite
```

**Collaborators**:
- @aideveloper (Admin)
- @ainative-team (Write)

**Branch Protection Rules** (`main`):
- Require pull request before merging
- Require status checks to pass
- Require branches to be up to date
- Dismiss stale pull request approvals
- Require code owner reviews

---

#### 2. Frontend Repository

**Name**: `relycapital/AINative-website`
**Visibility**: Private
**Purpose**: React frontend for AINative platform
**URL**: `github.com/relycapital/AINative-website`
**Default Branch**: `main`

**Key Directories**:
```
src/
├── pages/dashboard/          # AgentSwarm dashboard
├── components/               # Reusable UI components
├── services/                 # API clients
└── tests/e2e/                # Playwright tests
```

**Deployment**: Vercel (automatic from `main` branch)
**Production URL**: `https://www.ainative.studio`

---

### Repository Access

**Cloning Repositories**:
```bash
# Clone backend (via SSH - recommended)
git clone git@github.com:relycapital/core.git

# Clone frontend
git clone git@github.com:relycapital/AINative-website.git

# Clone with HTTPS (requires PAT)
git clone https://github.com/relycapital/core.git
```

**SSH Setup** (recommended):
```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "your_email@example.com"

# Add to GitHub
cat ~/.ssh/id_ed25519.pub | pbcopy
# Paste at: github.com/settings/keys
```

**Personal Access Token** (PAT) Setup:
```bash
# Create PAT at: github.com/settings/tokens
# Required scopes:
# - repo (full control)
# - workflow (GitHub Actions)

# Configure git
git config --global credential.helper store
git config --global user.name "Your Name"
git config --global user.email "your.email@example.com"
```

---

### Git Workflow

**Feature Development**:
```bash
# Create feature branch
git checkout -b feature/agent-swarm-stage-9

# Make changes
git add .
git commit -m "feat(agent-swarm): implement GitHub issue import (Stage 9)"

# Push to remote
git push origin feature/agent-swarm-stage-9

# Create PR via GitHub CLI
gh pr create --title "feat: Stage 9 GitHub Issue Import" \
  --body "Implements missing Stage 9 functionality"
```

**Commit Message Format** (Semantic Commits):
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation only
- `style`: Code style (formatting)
- `refactor`: Code refactoring
- `test`: Adding tests
- `chore`: Maintenance tasks

**Example**:
```
feat(agent-swarm): add GitHub issue import for Stage 9

- Parse backlog.md into structured issues
- Create GitHub Issues via API
- Link issues with Epic/Story relationships
- Add milestones for sprints
- Apply labels (epic, user-story, frontend, backend)

Closes #211
Relates to #212, #213
```

---

## 🚀 Deployment Infrastructure

### Backend Deployment (Railway)

**Platform**: Railway
**Service**: `ainative-backend`
**URL**: `https://api.ainative.studio`
**Region**: US-West (Oregon)
**Plan**: Pro ($20/month)

**Railway Project Structure**:
```
ainative-production/
├── backend-service           # FastAPI application
│   ├── Build Command: pip install -r requirements.txt
│   ├── Start Command: uvicorn app.main:app --host 0.0.0.0 --port $PORT
│   └── Root Directory: /src/backend
│
├── celery-worker            # Background task worker
│   ├── Build Command: pip install -r requirements.txt
│   ├── Start Command: celery -A app.celery_app worker --loglevel=info
│   └── Root Directory: /src/backend
│
├── redis-service            # Redis for Celery
│   └── Railway Redis plugin
│
└── postgres-service         # PostgreSQL database
    └── Railway PostgreSQL plugin
```

**Railway Configuration** (`railway.toml`):
```toml
[build]
builder = "nixpacks"

[deploy]
startCommand = "uvicorn app.main:app --host 0.0.0.0 --port $PORT"
restartPolicyType = "on-failure"
restartPolicyMaxRetries = 10

[healthcheck]
path = "/health"
interval = 60
timeout = 10
```

**Deployment Process**:
1. Code merged to `main` branch
2. GitHub Actions runs tests
3. Railway auto-deploys on success
4. Health check verifies deployment
5. Slack notification sent

**Manual Deploy**:
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Link project
railway link

# Deploy
railway up
```

---

### Frontend Deployment (Vercel)

**Platform**: Vercel
**Project**: `ainative-website`
**URL**: `https://www.ainative.studio`
**Region**: Global Edge Network
**Plan**: Pro ($20/month)

**Vercel Project Structure**:
```
ainative-website/
├── Framework: Vite + React
├── Node Version: 18.x
├── Build Command: npm run build
├── Output Directory: dist
└── Install Command: npm install
```

**Environment Variables** (Vercel):
```bash
VITE_API_URL=https://api.ainative.studio/v1
VITE_API_BASE_URL=https://api.ainative.studio
NODE_ENV=production
```

**Deployment Process**:
1. Code pushed to `main` branch
2. Vercel auto-builds and deploys
3. Preview deployments for PRs
4. Production deployment on merge

**Manual Deploy**:
```bash
# Install Vercel CLI
npm install -g vercel

# Login
vercel login

# Deploy
vercel --prod
```

---

### DNS Configuration

**Domain**: `ainative.studio`
**Registrar**: Namecheap
**DNS Provider**: Cloudflare

**DNS Records**:
```
Type    Name    Value                           TTL
A       @       76.76.21.21 (Vercel)           Auto
CNAME   www     cname.vercel-dns.com           Auto
CNAME   api     oregon.railway.app             Auto
CNAME   cdn     cloudflare-cdn.com             Auto
TXT     @       "verification-code"            Auto
```

**SSL/TLS**:
- Certificates: Auto-managed by Vercel & Railway
- Mode: Full (strict)
- Min TLS Version: 1.2

---

## 🔑 Environment Variables

### Backend Environment Variables

**Location**: Railway dashboard → `backend-service` → Variables

**Required Variables**:
```bash
# ===== Database =====
DATABASE_URL=postgresql://user:pass@host:5432/ainative_prod
# Railway auto-provides this when PostgreSQL plugin added

# ===== ZeroDB Integration =====
ZERODB_API_KEY=sk_live_...
ZERODB_PROJECT_ID=proj_...
ZERODB_BASE_URL=https://api.ainative.studio

# ===== MinIO / S3 Storage =====
MINIO_URL=https://minio.ainative.studio
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=...
MINIO_BUCKET=agent-swarm-generated-code

# ===== AI Providers =====
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# ===== GitHub Integration =====
GITHUB_TOKEN=ghp_...  # Server-side GitHub PAT
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY=...

# ===== Celery / Redis =====
REDIS_URL=redis://default:password@host:6379
# Railway auto-provides this when Redis plugin added
CELERY_BROKER_URL=$REDIS_URL
CELERY_RESULT_BACKEND=$REDIS_URL

# ===== Kong API Gateway =====
KONG_ADMIN_URL=http://kong-admin:8001
KONG_API_KEY=...

# ===== Application =====
ENVIRONMENT=production
DEBUG=false
SECRET_KEY=...  # Django-style secret key
ALLOWED_HOSTS=api.ainative.studio,localhost

# ===== CORS =====
CORS_ORIGINS=https://www.ainative.studio,http://localhost:3000

# ===== Logging =====
LOG_LEVEL=INFO
SENTRY_DSN=https://...@sentry.io/...
```

**Loading .env file locally**:
```bash
# Create .env file (never commit to git!)
cp .env.example .env

# Edit .env with your values
nano .env

# Load in shell
export $(cat .env | xargs)

# Or use python-dotenv (recommended)
# FastAPI automatically loads .env
```

---

### Frontend Environment Variables

**Location**: Vercel dashboard → `ainative-website` → Settings → Environment Variables

**Required Variables**:
```bash
# ===== API Configuration =====
VITE_API_URL=https://api.ainative.studio/v1
VITE_API_BASE_URL=https://api.ainative.studio

# ===== Feature Flags =====
VITE_ENABLE_AGENT_SWARM=true
VITE_ENABLE_ZERODB=true

# ===== Analytics =====
VITE_GOOGLE_ANALYTICS_ID=G-...
VITE_MIXPANEL_TOKEN=...

# ===== Sentry Error Tracking =====
VITE_SENTRY_DSN=https://...@sentry.io/...

# ===== Environment =====
NODE_ENV=production
```

**Local Development** (`.env.local`):
```bash
VITE_API_URL=http://localhost:8000/v1
VITE_API_BASE_URL=http://localhost:8000
VITE_ENABLE_AGENT_SWARM=true
```

---

## 💾 Storage Architecture

### PostgreSQL (Metadata)

**Provider**: Railway PostgreSQL Plugin
**Version**: PostgreSQL 15
**Size**: 10 GB
**Backups**: Daily automated backups (7-day retention)

**Connection**:
```bash
# Via Railway CLI
railway connect postgres

# Direct connection
psql $DATABASE_URL
```

**Tables**:
```sql
-- AgentSwarm tables
agent_swarm_workflows
agent_swarm_rules
agent_swarm_projects (DEPRECATED - moved to ZeroDB)
sprint_plans
github_integrations
```

**Migrations**:
```bash
# Create migration
alembic revision --autogenerate -m "Add new table"

# Apply migrations
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

### ZeroDB (Primary Storage)

**Platform**: AINative ZeroDB
**Base URL**: `https://api.ainative.studio/v1/public/{project_id}/database/`
**Purpose**: Project-scoped storage for all AgentSwarm data

**Storage Types**:

**1. File Storage (MinIO)**:
```
Endpoint: /v1/public/{project_id}/database/files/upload
Backend: MinIO (S3-compatible)
Bucket: Automatically created per project
Max File Size: 50 MB
Supported Formats: .md, .pdf, .zip, .tar.gz, .mp4
```

**Stored Files**:
- PRD documents (`.md`, `.pdf`)
- Generated code archives (`.zip`, `.tar.gz`)
- Test videos (`.mp4`) from Stage 11
- Data model schemas (`.json`)
- Sprint plans (`.md`)
- Backlog files (`.md`)

**2. NoSQL Tables**:
```
Endpoint: /v1/public/{project_id}/database/tables
Backend: PostgreSQL with JSONB
Schema: Dynamic (user-defined)
Indexes: Automatic on common fields
```

**AgentSwarm Tables** (in ZeroDB):
```
agent_swarm_projects (metadata, status, created_at)
agent_swarm_workflows (current_stage, progress, outputs)
github_integration (repo_url, pat_hash, status)
sprint_plans (agent_count, timeline, assignments)
```

**3. Vector Store** (Planned):
```
Endpoint: /v1/public/{project_id}/database/vectors/search
Backend: pgvector + Qdrant
Dimensions: 1536 (OpenAI ada-002)
Distance Metric: Cosine similarity
```

**Use Cases**:
- Semantic code search
- Similar component finding
- Duplicate detection

**4. Memory Management** (Planned):
```
Endpoint: /v1/public/{project_id}/database/memory
Backend: Vector store + PostgreSQL
TTL: Configurable (default: 30 days)
```

**Use Cases**:
- Agent conversation history
- Learned patterns
- User preferences

---

### MinIO Object Storage

**Deployment**: Self-hosted on Railway
**Version**: MinIO RELEASE.2024-01-31T20-20-33Z
**Access**: S3-compatible API
**Encryption**: AES-256 (server-side)

**Configuration**:
```bash
# Environment
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=...
MINIO_REGION=us-west-1

# Bucket policy
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"AWS": ["*"]},
      "Action": ["s3:GetObject"],
      "Resource": ["arn:aws:s3:::agent-swarm-*/*"]
    }
  ]
}
```

**Bucket Structure**:
```
agent-swarm-generated-code/
├── {project_id}/
│   ├── prd/
│   │   └── prd-{timestamp}.md
│   ├── code/
│   │   ├── sprint-1-code.zip
│   │   └── sprint-2-code.zip
│   ├── videos/
│   │   ├── test-run-1.mp4
│   │   └── test-run-2.mp4
│   └── schemas/
│       └── data-model.json
```

**Access via CLI**:
```bash
# Install mc (MinIO Client)
brew install minio/stable/mc

# Configure
mc alias set ainative-minio https://minio.ainative.studio minioadmin password

# List buckets
mc ls ainative-minio

# Upload file
mc cp prd.md ainative-minio/agent-swarm-generated-code/proj-123/prd/
```

---

### Redis (Task Queue)

**Provider**: Railway Redis Plugin
**Version**: Redis 7.0
**Memory**: 512 MB
**Persistence**: RDB snapshots every 15 min

**Usage**:
- Celery broker (task queue)
- Celery result backend (task results)
- WebSocket pub/sub (real-time updates)
- Rate limiting cache

**Connection**:
```bash
# Via Railway CLI
railway connect redis

# Via redis-cli
redis-cli -u $REDIS_URL
```

**Celery Tasks**:
```python
# Queue structure
celery:agent-swarm:tasks
├── execute_agent_task:{task_id}
├── generate_data_model:{project_id}
├── generate_backlog:{project_id}
└── launch_swarm:{project_id}

# Results stored at
celery:agent-swarm:results:{task_id}
```

---

## 🔄 CI/CD Pipelines

### GitHub Actions Workflows

**Location**: `.github/workflows/`

#### 1. CI Pipeline (`agent-swarm-ci.yml`)

**Triggers**:
- Pull request to `main`
- Push to feature branches

**Jobs**:
```yaml
name: AgentSwarm CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [feature/*, fix/*]

jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r src/backend/requirements.txt
      - name: Run pytest
        run: pytest src/backend/tests/ -v --cov=app/agents/swarm

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Setup Node
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      - name: Install dependencies
        run: npm ci
        working-directory: AINative-website
      - name: Run Playwright tests
        run: npx playwright test tests/e2e/agentswarm-*.spec.ts

  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Ruff (Python linter)
        run: ruff check src/backend/
      - name: ESLint (TypeScript)
        run: npm run lint
        working-directory: AINative-website

  type-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: mypy (Python)
        run: mypy src/backend/app/agents/swarm/
      - name: tsc (TypeScript)
        run: npm run type-check
        working-directory: AINative-website
```

**Status Checks** (required for merge):
- ✅ backend-tests
- ✅ frontend-tests
- ✅ lint
- ✅ type-check

---

#### 2. Deployment Pipeline (`agent-swarm-deploy.yml`)

**Triggers**:
- Merge to `main` branch
- Manual workflow dispatch

**Jobs**:
```yaml
name: AgentSwarm Deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Railway Deploy
        uses: railway-deploy-action@v1
        with:
          railway_token: ${{ secrets.RAILWAY_TOKEN }}
          service: backend-service

  deploy-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Vercel Deploy
        uses: amondnet/vercel-action@v20
        with:
          vercel-token: ${{ secrets.VERCEL_TOKEN }}
          vercel-org-id: ${{ secrets.VERCEL_ORG_ID }}
          vercel-project-id: ${{ secrets.VERCEL_PROJECT_ID }}
          vercel-args: '--prod'

  smoke-tests:
    runs-on: ubuntu-latest
    needs: [deploy-backend, deploy-frontend]
    steps:
      - name: Health check backend
        run: curl -f https://api.ainative.studio/health
      - name: Health check frontend
        run: curl -f https://www.ainative.studio
      - name: Test AgentSwarm endpoint
        run: |
          curl -H "X-API-Key: ${{ secrets.ZERODB_API_KEY }}" \
               https://api.ainative.studio/v1/public/agent-swarms/projects

  notify:
    runs-on: ubuntu-latest
    needs: [deploy-backend, deploy-frontend, smoke-tests]
    if: always()
    steps:
      - name: Slack notification
        uses: 8398a7/action-slack@v3
        with:
          status: ${{ job.status }}
          webhook_url: ${{ secrets.SLACK_WEBHOOK }}
          text: 'AgentSwarm deployment completed'
```

---

### Deployment Secrets

**GitHub Secrets** (Settings → Secrets and variables → Actions):
```
RAILWAY_TOKEN              # Railway CLI token
VERCEL_TOKEN              # Vercel CLI token
VERCEL_ORG_ID             # Vercel organization ID
VERCEL_PROJECT_ID         # Vercel project ID
ZERODB_API_KEY            # For smoke tests
SLACK_WEBHOOK             # Notifications
SENTRY_AUTH_TOKEN         # Error tracking
```

---

## 💻 Local Development Setup

### Prerequisites

**Required Software**:
```bash
# Python 3.11+
python3 --version

# Node.js 18+
node --version

# Git
git --version

# PostgreSQL 15+ (or use Railway connection)
psql --version

# Redis (or use Railway connection)
redis-cli --version

# Docker (optional, for MinIO)
docker --version
```

---

### Backend Setup

**1. Clone Repository**:
```bash
git clone git@github.com:relycapital/core.git
cd core/src/backend
```

**2. Create Virtual Environment**:
```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

**3. Install Dependencies**:
```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Dev dependencies (pytest, ruff, mypy)
```

**4. Setup Environment**:
```bash
cp .env.example .env
nano .env  # Add your API keys
```

**5. Run Migrations**:
```bash
alembic upgrade head
```

**6. Start Development Server**:
```bash
uvicorn app.main:app --reload --port 8000
```

**7. Start Celery Worker** (separate terminal):
```bash
celery -A app.celery_app worker --loglevel=info
```

**8. Access API**:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Health: `http://localhost:8000/health`

---

### Frontend Setup

**1. Clone Repository** (if not already):
```bash
cd /Users/aideveloper/core/AINative-website
```

**2. Install Dependencies**:
```bash
npm install
```

**3. Setup Environment**:
```bash
cp .env.example .env.local
nano .env.local  # Set VITE_API_URL=http://localhost:8000
```

**4. Start Development Server**:
```bash
npm run dev
```

**5. Access Application**:
- Frontend: `http://localhost:5173`
- AgentSwarm Dashboard: `http://localhost:5173/dashboard/agent-swarm`

---

### Docker Compose (Optional)

**For local MinIO & Redis**:

`docker-compose.yml`:
```yaml
version: '3.8'

services:
  minio:
    image: minio/minio:latest
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: server /data --console-address ":9001"
    volumes:
      - minio-data:/data

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis-data:/data

volumes:
  minio-data:
  redis-data:
```

**Start Services**:
```bash
docker-compose up -d
```

---

## 📊 Monitoring & Logging

### Application Logging

**Backend Logging** (FastAPI):
```python
# File: app/core/logging_config.py
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)

# Usage in code
logger = logging.getLogger(__name__)
logger.info("Agent swarm launched for project {project_id}")
logger.error("Failed to create GitHub repo", exc_info=True)
```

**Log Locations**:
- Railway: Dashboard → Deployments → Logs
- Local: `src/backend/app.log`

---

### Error Tracking (Sentry)

**Backend Integration**:
```python
# File: app/main.py
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration

sentry_sdk.init(
    dsn=os.getenv("SENTRY_DSN"),
    integrations=[FastApiIntegration()],
    traces_sample_rate=0.1,
    environment=os.getenv("ENVIRONMENT", "development")
)
```

**Frontend Integration**:
```typescript
// File: src/main.tsx
import * as Sentry from "@sentry/react";

Sentry.init({
  dsn: import.meta.env.VITE_SENTRY_DSN,
  environment: import.meta.env.MODE,
  tracesSampleRate: 0.1,
});
```

**Accessing Sentry**:
- Dashboard: `sentry.io/organizations/ainative/projects/`
- Alerts: Slack channel `#sentry-errors`

---

### Performance Monitoring

**Railway Metrics**:
- CPU usage
- Memory usage
- Response times
- Error rates

**Custom Metrics** (Prometheus format):
```python
# File: app/metrics.py
from prometheus_client import Counter, Histogram

agent_swarm_launches = Counter(
    'agent_swarm_launches_total',
    'Total number of agent swarm launches'
)

agent_execution_time = Histogram(
    'agent_execution_seconds',
    'Time taken for agent execution',
    buckets=[1, 5, 10, 30, 60, 120, 300]
)
```

---

### Health Checks

**Backend Health Endpoint**:
```python
# File: app/api/routers/health.py
@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "version": "2.0",
        "services": {
            "database": await check_database(),
            "redis": await check_redis(),
            "zerodb": await check_zerodb(),
            "minio": await check_minio()
        }
    }
```

**Monitoring Health**:
```bash
# Local
curl http://localhost:8000/health

# Production
curl https://api.ainative.studio/health
```

---

## 🔥 Disaster Recovery

### Database Backups

**PostgreSQL** (Railway):
- Automatic daily backups (7-day retention)
- Point-in-time recovery (PITR) available
- Manual backups via Railway dashboard

**Manual Backup**:
```bash
# Via Railway CLI
railway run pg_dump > backup-$(date +%Y%m%d).sql

# Restore
railway run psql < backup-20251205.sql
```

---

### ZeroDB Backups

**Automatic Backups**:
- All data replicated across 3 zones
- Point-in-time recovery (30-day window)
- Automated snapshots every 6 hours

**Export Data**:
```bash
# Export project files
curl -H "X-API-Key: $ZERODB_API_KEY" \
  "https://api.ainative.studio/v1/public/$PROJECT_ID/database/files" > files.json

# Export tables
curl -H "X-API-Key: $ZERODB_API_KEY" \
  "https://api.ainative.studio/v1/public/$PROJECT_ID/database/tables/export" > tables.json
```

---

### Rollback Procedures

**Backend Rollback** (Railway):
```bash
# Via CLI
railway rollback

# Or via dashboard
# Railway → Deployments → Select previous deployment → Redeploy
```

**Frontend Rollback** (Vercel):
```bash
# Via CLI
vercel rollback

# Or via dashboard
# Vercel → Deployments → Select previous deployment → Promote to Production
```

**Database Rollback**:
```bash
# Alembic (downgrade 1 migration)
alembic downgrade -1

# Restore from backup
railway run psql < backup-previous.sql
```

---

## 📞 Support & Resources

### Documentation

- **This Guide**: Infrastructure & deployment reference
- **Master Context**: `/docs/agent-swarm/AGENTSWARM_MASTER_CONTEXT.md`
- **File Map**: `/docs/agent-swarm/AGENTSWARM_FILE_MAP.md`
- **Official Workflow**: `/src/backend/AgentSwarm-Workflow.md`

### Internal Resources

- **Slack Channel**: `#agent-swarm-dev`
- **GitHub Issues**: `github.com/relycapital/core/issues`
- **Wiki**: `github.com/relycapital/core/wiki`

### External Resources

- **Railway Docs**: `docs.railway.app`
- **Vercel Docs**: `vercel.com/docs`
- **FastAPI Docs**: `fastapi.tiangolo.com`
- **React Docs**: `react.dev`

---

**Document Version**: 1.0
**Last Updated**: December 5, 2025
**Maintained By**: AINative Studio DevOps Team
**Next Review**: January 1, 2026
