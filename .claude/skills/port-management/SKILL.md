# Port Management Skill

**USE THIS SKILL** when you need automated port conflict resolution for local development across ANY application.

## Overview

This is a **GENERIC, REUSABLE** port management framework that can be used by any AINative application. It provides intelligent port conflict detection and resolution for multi-service applications.

## 🎯 Design Philosophy

**Reusable Across All Apps** - Not specific to any single project:
- Drop into any project's `.claude/skills/` directory
- Configure via `.claude/port-config.json`
- Works for any stack (Node, Python, Go, Java, etc.)
- Supports any number of services

**Zero Manual Configuration** - Works out of the box:
- Auto-detects port conflicts
- Auto-resolves based on configured mode
- Auto-updates environment variables
- Auto-starts all configured services

## Configuration

Each application defines its services and ports in `.claude/port-config.json`:

```json
{
  "project_name": "MyApp",
  "services": [
    {
      "name": "API",
      "port": 3000,
      "directory": "./api",
      "start_command": "npm start",
      "health_check": "http://localhost:{port}/health",
      "can_reassign": true,
      "required": true,
      "env_vars": {
        "PORT": "{port}",
        "NODE_ENV": "development"
      }
    },
    {
      "name": "Frontend",
      "port": 3001,
      "directory": "./frontend",
      "start_command": "npm run dev",
      "health_check": "http://localhost:{port}",
      "can_reassign": true,
      "depends_on": ["API"],
      "env_updates": {
        "NEXT_PUBLIC_API_URL": "http://localhost:{API_port}"
      }
    }
  ],
  "defaults": {
    "port_conflict_mode": "ask",
    "log_directory": "/tmp",
    "startup_timeout": 30,
    "health_check_retries": 30
  }
}
```

## Configuration Schema

### Service Definition

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | Yes | Service display name |
| `port` | number | Yes | Default port number |
| `directory` | string | No | Working directory for service |
| `start_command` | string | Yes | Command to start service |
| `health_check` | string | No | URL to check if service is healthy |
| `can_reassign` | boolean | No | Whether service supports alternative ports (default: true) |
| `required` | boolean | No | Whether startup should fail if service can't start (default: true) |
| `env_vars` | object | No | Environment variables to set when starting |
| `env_updates` | object | No | Environment variables to update in dotenv files |
| `depends_on` | array | No | List of service names this depends on |
| `pre_start` | string | No | Command to run before starting (e.g., "npm install") |

### Variable Substitution

Use `{port}` or `{SERVICE_NAME_port}` in any string field for dynamic port substitution:

```json
{
  "health_check": "http://localhost:{port}/health",
  "env_updates": {
    "API_URL": "http://localhost:{Backend_port}"
  }
}
```

## Port Conflict Resolution Modes

### 1. Ask Mode (Default - Interactive)

```bash
# Prompts user for each conflict
scripts/start-all-local.sh
```

User chooses:
- **[k]ill** - Terminate conflicting process
- **[r]eassign** - Use alternative port (if supported)
- **[a]bort** - Cancel startup

### 2. Kill Mode (CI/CD)

```bash
# Automatically kills conflicting processes
PORT_CONFLICT_MODE=kill scripts/start-all-local.sh
```

Perfect for:
- Continuous Integration pipelines
- Automated deployments
- Docker container startups

### 3. Reassign Mode (Multi-Instance)

```bash
# Automatically uses alternative ports
PORT_CONFLICT_MODE=reassign scripts/start-all-local.sh
```

Perfect for:
- Running multiple environments simultaneously
- QA testing with parallel instances
- Development with multiple branches

### 4. Error Mode (Strict)

```bash
# Fails immediately on any conflict
PORT_CONFLICT_MODE=error scripts/start-all-local.sh
```

Perfect for:
- Production-like environments
- Strict port enforcement policies
- Debugging port allocation issues

## How Port Reassignment Works

When `can_reassign: true`:
1. Service tries default port (e.g., 3000)
2. If occupied, tries 3001, 3002, 3003...
3. Scans up to 100 ports from base
4. Updates all dependent services automatically
5. Updates environment variables with new port

Services with `can_reassign: false`:
- Only "kill" mode works
- User must resolve conflict manually in "ask" mode
- "reassign" mode will fail for this service
- "error" mode will always fail

## Service Dependencies

Use `depends_on` to ensure services start in correct order:

```json
{
  "services": [
    {
      "name": "Database",
      "port": 5432,
      "can_reassign": false
    },
    {
      "name": "API",
      "port": 3000,
      "depends_on": ["Database"]
    },
    {
      "name": "Frontend",
      "port": 3001,
      "depends_on": ["API"]
    }
  ]
}
```

Startup order: Database → API → Frontend

## Examples

### Simple API Server

```json
{
  "project_name": "SimpleAPI",
  "services": [
    {
      "name": "API",
      "port": 8080,
      "start_command": "go run main.go",
      "health_check": "http://localhost:{port}/health",
      "can_reassign": true
    }
  ]
}
```

### Full Stack Application

```json
{
  "project_name": "MyApp",
  "services": [
    {
      "name": "PostgreSQL",
      "port": 5432,
      "start_command": "docker run -p {port}:5432 postgres:15",
      "can_reassign": false,
      "required": true
    },
    {
      "name": "Backend",
      "port": 8000,
      "directory": "./backend",
      "start_command": "python -m uvicorn main:app --port {port}",
      "health_check": "http://localhost:{port}/health",
      "can_reassign": true,
      "depends_on": ["PostgreSQL"],
      "env_vars": {
        "DATABASE_URL": "postgresql://localhost:{PostgreSQL_port}/myapp"
      }
    },
    {
      "name": "Frontend",
      "port": 3000,
      "directory": "./frontend",
      "start_command": "npm run dev",
      "can_reassign": true,
      "depends_on": ["Backend"],
      "env_updates": {
        "NEXT_PUBLIC_API_URL": "http://localhost:{Backend_port}"
      }
    }
  ]
}
```

### Microservices Architecture

```json
{
  "project_name": "Microservices",
  "services": [
    {
      "name": "AuthService",
      "port": 8001,
      "start_command": "node auth-service/index.js",
      "can_reassign": true
    },
    {
      "name": "UserService",
      "port": 8002,
      "start_command": "node user-service/index.js",
      "can_reassign": true,
      "env_updates": {
        "AUTH_SERVICE_URL": "http://localhost:{AuthService_port}"
      }
    },
    {
      "name": "APIGateway",
      "port": 8000,
      "start_command": "node gateway/index.js",
      "can_reassign": true,
      "depends_on": ["AuthService", "UserService"],
      "env_vars": {
        "AUTH_URL": "http://localhost:{AuthService_port}",
        "USER_URL": "http://localhost:{UserService_port}"
      }
    }
  ]
}
```

## Usage

### 1. Install Skill

Copy the `port-management` skill to your project:

```bash
cp -r /path/to/port-management .claude/skills/
```

### 2. Create Configuration

Create `.claude/port-config.json` with your services:

```bash
cat > .claude/port-config.json << 'EOF'
{
  "project_name": "MyApp",
  "services": [
    {
      "name": "API",
      "port": 3000,
      "start_command": "npm start"
    }
  ]
}
EOF
```

### 3. Generate Startup Script

```bash
# Generate from template
.claude/skills/port-management/generate-startup.sh > scripts/start-all-local.sh
chmod +x scripts/start-all-local.sh
```

### 4. Run Your App

```bash
scripts/start-all-local.sh
```

## Integration with Claude Code

This skill integrates with Claude Code's skill system:

```bash
# Via slash command
/start-local

# Via skill invocation
Skill("port-management")

# With custom mode
PORT_CONFLICT_MODE=kill /start-local
```

## Advanced Features

### Pre-Start Commands

Run setup commands before starting services:

```json
{
  "name": "API",
  "port": 3000,
  "pre_start": "npm install && npm run build",
  "start_command": "npm start"
}
```

### Custom Health Checks

Support any health check mechanism:

```json
{
  "name": "Database",
  "port": 5432,
  "health_check": "pg_isready -h localhost -p {port}",
  "start_command": "postgres -p {port}"
}
```

### Conditional Service Startup

Skip optional services automatically:

```json
{
  "name": "Analytics",
  "port": 9000,
  "required": false,
  "start_command": "analytics-server"
}
```

## Troubleshooting

### Port Still Showing as In Use

```bash
# Check what's using the port
lsof -i :3000

# Force kill all processes on port
lsof -ti :3000 | xargs kill -9
```

### Service Won't Start on Alternative Port

Some services hardcode their ports. Options:
1. Set `can_reassign: false` in config
2. Add port parameter to `start_command`: `"node app.js --port {port}"`
3. Use environment variable: `"env_vars": {"PORT": "{port}"}`

### Dependencies Not Starting in Order

Check `depends_on` array and ensure:
- Service names match exactly
- No circular dependencies
- All dependencies are defined

## Best Practices

1. **Always set `can_reassign`** explicitly for clarity
2. **Use health checks** when available for reliable startup detection
3. **Set reasonable timeouts** based on your services' startup time
4. **Document port ranges** if services must use specific ports
5. **Use `required: false`** for optional services like analytics
6. **Test all conflict modes** to ensure your app works in all scenarios

## Project-Specific Implementations

See `examples/` directory for:
- **OpenClaw**: Full-stack with Gateway, Backend, Frontend
- **SimpleAPI**: Single service API server
- **Microservices**: Multi-service architecture
- **Docker Compose**: Integration with Docker services

## ZERO TOLERANCE Rules

1. **NEVER hardcode app-specific logic** in the generic skill
2. **ALWAYS use port-config.json** for app-specific configuration
3. **NEVER commit port-config.json** with production credentials
4. **ALWAYS test with all 4 conflict modes** (ask/kill/reassign/error)
5. **ALWAYS document port requirements** in project README

## Contributing

To add support for a new use case:
1. Create example config in `examples/`
2. Update this SKILL.md with example
3. Test with all conflict modes
4. Submit PR with test results
