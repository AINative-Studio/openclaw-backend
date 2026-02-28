# OpenClaw Local Startup Guide

Complete guide for running the full OpenClaw stack locally.

## Quick Status Check

Run this command to check all services:

```bash
# Gateway
curl http://localhost:18789/health

# Backend API
curl http://localhost:8000/health

# Frontend Dashboard
curl http://localhost:3002
```

## The Complete Stack

OpenClaw consists of three services that must all be running:

| Service | Port | Technology | Purpose |
|---------|------|------------|---------|
| OpenClaw Gateway | 18789 | Node.js / DBOS | WebSocket gateway for agent communication |
| Backend API | 8000 | Python / FastAPI | REST API for agent management |
| Frontend Dashboard | 3002 | Next.js 15 | Web UI for monitoring and control |

## Starting All Services

### Option 1: Manual Startup (3 Terminals)

**Terminal 1 - Gateway**:
```bash
cd openclaw-gateway/
npm start
```

**Terminal 2 - Backend**:
```bash
# From openclaw-backend/
export SECRET_KEY="dev-secret-key-for-local-testing"
export OPENCLAW_GATEWAY_URL="http://localhost:18789"
export OPENCLAW_GATEWAY_TOKEN="openclaw-dev-token-12345"
export ENVIRONMENT="development"
export DATABASE_URL="sqlite:///./openclaw.db"

python3 -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 3 - Frontend**:
```bash
cd ../agent-swarm-monitor/
npm run dev
```

### Option 2: Automated Startup (Recommended)

Use the automated startup script:

```bash
./start-all-local.sh
```

This starts all three services in the background and opens the frontend in your browser.

## Accessing the Services

| URL | Description |
|-----|-------------|
| http://localhost:3002 | **Frontend Dashboard** - Main UI for managing agents |
| http://localhost:8000 | **Backend API** - Direct API access |
| http://localhost:8000/docs | **API Documentation** - Interactive Swagger UI |
| http://localhost:18789 | **Gateway** - WebSocket gateway (HTML response) |

## Key API Endpoints

### Health & Status
- `GET /health` - Backend health check
- `GET /api/v1/swarm/health` - Swarm health snapshot
- `GET /api/v1/swarm/monitoring/status` - Monitoring infrastructure status

### Metrics & Monitoring
- `GET /api/v1/metrics` - Prometheus metrics
- `GET /api/v1/swarm/timeline` - Task execution timeline
- `GET /api/v1/swarm/alerts/thresholds` - Alert configuration

### Agent Management
- `GET /api/v1/agents` - List all agents
- `POST /api/v1/agents` - Create new agent
- `GET /api/v1/agents/{id}` - Get agent details
- `PATCH /api/v1/agents/{id}` - Update agent
- `DELETE /api/v1/agents/{id}` - Delete agent

### WireGuard Networking
- `GET /api/v1/wireguard/health` - WireGuard health
- `POST /api/v1/wireguard/provision` - Provision peer
- `GET /api/v1/wireguard/peers` - List peers

## Frontend Features

The agent-swarm-monitor dashboard includes:

- **Home Dashboard** - Overview with stats and agent list
- **Agents** - Full agent management interface
- **Templates** - Pre-built agent templates
- **Channels** - Communication channel management (Slack, WhatsApp, etc.)
- **Integrations** - Third-party integrations (Gmail, LinkedIn)
- **Team** - Team member management
- **Monitoring** - Real-time monitoring and alerts

Note: The frontend currently uses mock data. Real API integration is in progress.

## Stopping Services

### If started manually:
Press `Ctrl+C` in each terminal

### If started with script:
```bash
./stop-all-local.sh
```

### Manual cleanup:
```bash
# Kill by port
lsof -ti :18789 | xargs kill  # Gateway
lsof -ti :8000 | xargs kill   # Backend
lsof -ti :3002 | xargs kill   # Frontend
```

## Troubleshooting

### Port Already in Use

```bash
# Find what's using the port
lsof -i :8000

# Kill it
kill -9 <PID>
```

### Frontend Not Loading

1. Check backend is running: `curl http://localhost:8000/health`
2. Check frontend `.env` file exists in `agent-swarm-monitor/` with:
   ```
   API_URL=http://localhost:8000
   ```
3. Clear browser cache (Cmd+Shift+R)

### Backend Import Errors

```bash
# Reinstall dependencies
pip install -r requirements.txt --upgrade
```

### Gateway Not Responding

```bash
cd openclaw-gateway/
npm install  # If node_modules missing
npm start
```

## Environment Variables

### Backend Required:
- `SECRET_KEY` - JWT signing key
- `OPENCLAW_GATEWAY_URL` - Gateway URL (default: http://localhost:18789)
- `OPENCLAW_GATEWAY_TOKEN` - Auth token (default: openclaw-dev-token-12345)
- `ENVIRONMENT` - Set to "development"
- `DATABASE_URL` - Database connection (default: sqlite:///./openclaw.db)

### Frontend Required:
- `API_URL` - Backend API URL (default: http://localhost:8000)

## Development Tips

1. **Backend Auto-reload**: Uvicorn's `--reload` flag automatically restarts on code changes
2. **Frontend Hot Reload**: Next.js dev server hot-reloads on file changes
3. **API Testing**: Use http://localhost:8000/docs for interactive API testing
4. **Logs**: Check `/tmp/openclaw-*.log` if using automated startup script
5. **Database**: SQLite database file is at `./openclaw.db` in backend directory

## Project Structure

```
openclaw-backend/           # Backend API (FastAPI)
├── backend/
│   ├── main.py            # FastAPI app entrypoint
│   ├── api/v1/endpoints/  # API endpoints
│   ├── services/          # Business logic
│   └── models/            # Data models
├── openclaw-gateway/      # Gateway (Node.js/DBOS)
└── docs/                  # Documentation

../agent-swarm-monitor/    # Frontend (Next.js)
├── app/                   # Next.js app router pages
├── components/            # React components
├── lib/                   # Services and utilities
└── hooks/                 # React hooks
```

## Additional Resources

- `/start-local` command - Quick startup reference
- `Skill("local-startup")` - Comprehensive startup guide
- `Skill("local-environment-check")` - Environment diagnostics
- `.claude/skills/` - All available skills

## Support

For issues or questions:
- Check the skills: `Skill("local-environment-check")` for diagnostics
- Review logs in `/tmp/openclaw-*.log`
- Verify all services are running with the status check above
