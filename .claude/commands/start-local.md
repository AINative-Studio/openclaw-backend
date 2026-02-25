---
description: Start the complete OpenClaw system locally (Gateway + Backend + Frontend)
skill: local-startup
---

# Start OpenClaw System Locally

This command starts the complete OpenClaw stack locally: Gateway, Backend API, and Frontend Dashboard.

## Complete 3-Service Startup

**Terminal 1 - OpenClaw Gateway** (port 18789):
```bash
cd openclaw-gateway/
npm start
```

**Terminal 2 - Backend API** (port 8000):
```bash
# From project root (openclaw-backend/)
export SECRET_KEY="dev-secret-key-for-local-testing"
export OPENCLAW_GATEWAY_URL="http://localhost:18789"
export OPENCLAW_GATEWAY_TOKEN="openclaw-dev-token-12345"
export ENVIRONMENT="development"
export DATABASE_URL="sqlite:///./openclaw.db"

python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 3 - Frontend Dashboard** (port 3002):
```bash
cd ../agent-swarm-monitor/
npm run dev
```

## Quick One-Command Startup

Use the automated startup script (recommended):

```bash
# Run the startup script
scripts/start-all-local.sh
```

This will start all three services in the background and open the frontend in your browser.

## Verify Running Services

```bash
# Gateway
curl http://localhost:18789/health

# Backend
curl http://localhost:8000/health

# Frontend (open in browser)
open http://localhost:3002

# API documentation
open http://localhost:8000/docs
```

## Service URLs

| Service | URL | Description |
|---------|-----|-------------|
| Frontend Dashboard | http://localhost:3002 | AgentClaw UI |
| Backend API | http://localhost:8000 | REST API |
| API Documentation | http://localhost:8000/docs | Swagger UI |
| Gateway | http://localhost:18789 | WebSocket Gateway |

## Available API Endpoints

- **Health**: `GET /health`
- **API Docs**: `GET /docs` (Swagger UI)
- **Swarm Health**: `GET /api/v1/swarm/health`
- **Metrics**: `GET /api/v1/metrics` (Prometheus format)
- **WireGuard Health**: `GET /api/v1/wireguard/health`
- **Timeline**: `GET /api/v1/swarm/timeline`
- **Alerts**: `GET /api/v1/swarm/alerts/thresholds`
- **Agent Lifecycle**: `GET/POST /api/v1/agents`

## Stopping All Services

If started manually (3 terminals):
- Press `Ctrl+C` in each terminal

If started with script:
```bash
scripts/stop-all-local.sh
```

Or manually kill by port:
```bash
# Find and kill processes
lsof -ti :18789 | xargs kill  # Gateway
lsof -ti :8000 | xargs kill   # Backend
lsof -ti :3002 | xargs kill   # Frontend
```

## Troubleshooting

Use the `local-environment-check` skill for comprehensive diagnostics:
```bash
Skill("local-environment-check")
```

Common issues:
- **Port in use**: Kill existing process with `lsof -ti :<port> | xargs kill`
- **Frontend errors**: Check `.env` in agent-swarm-monitor has `API_URL=http://localhost:8000`
- **Gateway not responding**: Restart with `cd openclaw-gateway && npm start`
