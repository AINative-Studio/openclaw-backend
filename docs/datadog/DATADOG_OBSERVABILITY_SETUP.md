# Datadog Observability Integration for AgentClaw

## Summary

Adds full Datadog observability to the AgentClaw backend -- APM tracing, LLM Observability, custom metrics, and a pre-built dashboard. The integration is fully agentless (no local Datadog Agent required) and gated behind `DD_LLMOBS_ENABLED=1` so it has zero impact when disabled.

Three hackathon capabilities demonstrated:

1. **Datadog Dashboards** -- 10-widget dashboard with custom DogStatsD-equivalent metrics submitted via HTTP API
2. **LLM Observability** -- Auto-traced Anthropic calls + manual Agent/Workflow/LLM span hierarchy
3. **Datadog MCP** -- MCP server config for AI agents to query traces, metrics, and dashboards

## Architecture

```
WhatsApp Command
    |
    v
ClaudeOrchestrator.handle_whatsapp_command()    <-- agent_span("claude_orchestrator")
    |
    v
CommandParser._parse_llm()                       <-- workflow_span("command_parse_llm")
    |
    v
anthropic.messages.create()                      <-- auto-traced by ddtrace patch
    |
    v
MonitoringIntegrationService.on_*()              <-- custom metrics via HTTP API
    |
    +---> PrometheusMetricsService (existing)
    +---> TaskTimelineService (existing)
    +---> DatadogService (new)
              |
              +---> Datadog HTTP API (agentless metrics)
              +---> LLMObs SDK (agentless spans)
```

### Trace Hierarchy in LLM Observability UI

```
Agent: claude_orchestrator
  └── Workflow: command_parse_llm
        └── LLM: anthropic.messages.create (auto-instrumented)
```

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `backend/services/datadog_service.py` | Singleton service: HTTP API metrics + LLMObs span helpers | ~310 |
| `.env.datadog.example` | Environment variable template | ~17 |
| `docs/datadog/agentclaw-dashboard.json` | 10-widget dashboard JSON importable via Datadog API | ~197 |
| `scripts/create-datadog-dashboard.sh` | curl script to import dashboard | ~50 |
| `tests/services/test_datadog_service.py` | 32 BDD-style unit tests | ~430 |

## Files Modified

| File | Change |
|------|--------|
| `requirements.txt` | Added `ddtrace>=2.14.0` |
| `backend/main.py` | Added ddtrace auto-patching (FastAPI + Anthropic) + LLMObs singleton init at startup |
| `backend/services/monitoring_integration_service.py` | Wired DatadogService into facade -- parallel Datadog calls in 7 `on_*()` methods + `datadog` in `get_status()` |
| `backend/agents/orchestration/command_parser.py` | Wrapped `_parse_llm()` with `workflow_span("command_parse_llm")` + span annotation |
| `backend/agents/orchestration/claude_orchestrator.py` | Wrapped `handle_whatsapp_command()` with `agent_span("claude_orchestrator")` |

## Setup Guide

### Prerequisites

- Python 3.10+
- A Datadog account (free trial works)
- A Datadog API Key (Organization Settings > API Keys)
- A Datadog Application Key (Organization Settings > Application Keys)

### Step 1: Install Dependencies

```bash
cd openclaw-backend
./venv/bin/pip install "ddtrace>=2.14.0"
```

`ddtrace` bundles APM tracing, Anthropic auto-instrumentation, LLMObs SDK, and DogStatsD client. The `httpx` package (already a project dependency) handles agentless HTTP API metric submission.

### Step 2: Configure Environment Variables

Add to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
export DD_API_KEY=<your-api-key>
export DD_APP_KEY=<your-app-key>
export DD_SITE=datadoghq.com
export DD_SERVICE=agentclaw-backend
export DD_ENV=development
export DD_VERSION=1.0.0
export DD_LLMOBS_ENABLED=1
export DD_LLMOBS_ML_APP=agentclaw
export DD_LLMOBS_AGENTLESS_ENABLED=1
```

Then reload: `source ~/.zshrc`

**Never commit API keys to version control.** The `.env.datadog.example` file is provided as a reference template only.

| Variable | Required | Description |
|----------|----------|-------------|
| `DD_API_KEY` | Yes | Datadog API key for metric submission |
| `DD_APP_KEY` | Yes | Datadog Application key (for dashboard import) |
| `DD_SITE` | No | Datadog site (default: `datadoghq.com`) |
| `DD_SERVICE` | No | Service name in APM (default: `agentclaw-backend`) |
| `DD_ENV` | No | Environment tag (default: `development`) |
| `DD_VERSION` | No | Version tag (default: `1.0.0`) |
| `DD_LLMOBS_ENABLED` | Yes | Set to `1` to enable all Datadog features. Set to `0` (or omit) to disable completely |
| `DD_LLMOBS_ML_APP` | No | ML app name in LLM Observability UI (default: `agentclaw`) |
| `DD_LLMOBS_AGENTLESS_ENABLED` | No | Set to `1` for agentless mode (no local Datadog Agent). Set to `0` if running the local Agent |

### Step 3: Start the Server

```bash
ddtrace-run uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The `ddtrace-run` wrapper enables auto-instrumentation. On startup you should see:

```
DatadogService: HTTP API metrics initialized (agentless)
DatadogService: LLMObs enabled (ml_app=agentclaw, agentless=True)
```

### Step 4: Import the Dashboard

```bash
bash scripts/create-datadog-dashboard.sh
```

This creates a 10-widget dashboard in your Datadog account and prints the URL. You need both `DD_API_KEY` and `DD_APP_KEY` set for this to work.

### Step 5: Verify

| Check | How |
|-------|-----|
| Service running | `curl http://localhost:8000/health` returns `{"status":"ok"}` |
| Metrics flowing | Go to Datadog Metrics Explorer, search for `agentclaw.*` |
| LLM Observability | Trigger a WhatsApp command parse, check LLM Observability UI |
| Dashboard | Open the URL printed by the import script |
| APM traces | Check Datadog APM > Traces, filter by `service:agentclaw-backend` |

## DatadogService API

### Metric Methods

All methods are fire-and-forget -- they never raise exceptions and silently no-op when disabled.

| Method | Metric Name | Tags | Type |
|--------|-------------|------|------|
| `record_task_assignment(status)` | `agentclaw.task_assignments_total` | `status:{status}` | count |
| `record_lease_issued(complexity)` | `agentclaw.leases_issued_total` | `complexity:{complexity}` | count |
| `record_lease_expired()` | `agentclaw.leases_expired_total` | -- | count |
| `record_lease_revoked(reason)` | `agentclaw.leases_revoked_total` | `reason:{reason}` | count |
| `record_node_crash()` | `agentclaw.node_crashes_total` | -- | count |
| `record_task_requeued(result)` | `agentclaw.tasks_requeued_total` | `result:{result}` | count |
| `record_recovery_duration(type, secs)` | `agentclaw.recovery_duration_seconds` | `type:{type}` | gauge |
| `record_recovery_operation(type, status)` | `agentclaw.recovery_operations_total` | `type:{type}`, `status:{status}` | count |

### LLMObs Span Methods

| Method | Span Type | Usage |
|--------|-----------|-------|
| `workflow_span(name)` | Workflow | Context manager. Wraps a business workflow (e.g., command parsing) |
| `agent_span(name)` | Agent | Context manager. Wraps an agent's top-level operation |
| `tool_span(name)` | Tool | Context manager. Wraps a tool invocation |
| `annotate_span(input_data, output_data)` | -- | Annotates the current active span with input/output data |

Example:

```python
dd = get_datadog_service()

with dd.agent_span("my_agent"):
    with dd.workflow_span("my_workflow"):
        result = llm_call(...)
        dd.annotate_span(input_data="prompt", output_data=str(result))
```

### Status

```python
dd.get_status()
# Returns:
# {
#     "enabled": True,
#     "ddtrace_available": True,
#     "metrics_api_ready": True,
#     "llmobs_available": True,
# }
```

## MonitoringIntegrationService Integration

The facade's combined methods now call both Prometheus and Datadog in parallel:

```
on_task_leased("task-1", "peer-1", complexity="high")
    ├── timeline_service.record_event(TASK_LEASED, ...)   # try/except
    ├── metrics_service.record_lease_issued("high")        # try/except
    └── datadog_service.record_lease_issued("high")        # try/except (new)
```

Methods with Datadog integration:

| Facade Method | Datadog Call |
|---------------|--------------|
| `on_task_leased` | `record_lease_issued(complexity)` |
| `on_task_requeued` | `record_task_requeued(result)` |
| `on_lease_expired` | `record_lease_expired()` |
| `on_lease_revoked` | `record_lease_revoked(reason)` |
| `on_node_crashed` | `record_node_crash()` |
| `on_task_assigned` | `record_task_assignment(status)` |
| `on_recovery_completed` | `record_recovery_operation(type, status)` + `record_recovery_duration(type, seconds)` |

## Dashboard Widgets

The `agentclaw-dashboard.json` defines 10 widgets:

| # | Widget | Type | Data Source |
|---|--------|------|-------------|
| 1 | LLM Request Latency (P95) | Timeseries | Auto-instrumented Anthropic traces |
| 2 | LLM Token Usage | Timeseries | Auto-instrumented Anthropic traces |
| 3 | Task Assignments by Status | Timeseries | Custom metric `agentclaw.task_assignments_total` |
| 4 | Lease Lifecycle (Issued vs Expired) | Timeseries | Custom metrics `agentclaw.leases_*` |
| 5 | Active Leases | Query Value | Custom metric `agentclaw.active_leases` |
| 6 | Node Crashes | Query Value | Custom metric `agentclaw.node_crashes_total` |
| 7 | Buffer Utilization (%) | Query Value | Custom metric with red/yellow/green thresholds |
| 8 | Recovery Duration (P95) | Timeseries | Custom metric `agentclaw.recovery_duration_seconds` |
| 9 | FastAPI Request Latency by Endpoint | Timeseries | Auto-instrumented FastAPI traces |
| 10 | API Error Rate by Endpoint | Timeseries | Auto-instrumented FastAPI traces |

## Agentless vs Agent Mode

This integration defaults to **agentless mode** -- metrics and LLMObs data are sent directly to the Datadog API over HTTPS. No local Datadog Agent is required.

| Feature | Agentless Mode | Agent Mode |
|---------|---------------|------------|
| Custom metrics | HTTP API (`api.datadoghq.com/api/v1/series`) | DogStatsD (UDP port 8125) |
| LLM Observability | Direct to Datadog API | Via local Agent |
| APM Traces | Direct to `trace.agent.datadoghq.com` | Via local Agent (port 8126) |
| Setup complexity | Zero -- just env vars | Must install/run Datadog Agent |
| Reliability | Depends on outbound HTTPS | Agent handles buffering/retry |

To switch to Agent mode:
1. Install the Datadog Agent: `DD_API_KEY=<key> DD_SITE=datadoghq.com bash -c "$(curl -L https://install.datadoghq.com/scripts/install_mac_os.sh)"`
2. Set `DD_LLMOBS_AGENTLESS_ENABLED=0`
3. Remove `DD_TRACE_AGENT_URL` (defaults to `localhost:8126`)

## Test Coverage

```
32 passed in 0.08s

Name                                  Stmts   Miss  Cover   Missing
-------------------------------------------------------------------
backend/services/datadog_service.py     150     26    83%
-------------------------------------------------------------------
```

### Test Breakdown

| Class | Tests | Coverage Area |
|-------|-------|---------------|
| `TestDatadogServiceInit` | 6 | Disabled/enabled states, singleton, graceful init failures |
| `TestDatadogServiceMetrics` | 11 | Each record method, noop when disabled, HTTP submission, error handling |
| `TestDatadogServiceLLMObs` | 10 | Span context managers, annotation, noop when disabled, error handling |
| `TestDatadogServiceStatus` | 3 | Status dict structure and values |
| `TestNoopContextManager` | 2 | Context manager protocol compliance |

Run tests:

```bash
./venv/bin/python -m pytest tests/services/test_datadog_service.py -v \
    --cov=backend.services.datadog_service --cov-report=term-missing
```

## Design Decisions

1. **Agentless by default** -- Hackathon setup should not require installing a separate daemon. HTTP API submission works with just env vars.

2. **Fire-and-forget metrics in daemon threads** -- Metric HTTP POSTs run in background daemon threads (`threading.Thread(daemon=True)`) so they never block the request path. If the Datadog API is unreachable, the metric is silently dropped.

3. **Gated on DD_LLMOBS_ENABLED** -- A single env var controls the entire integration. When set to `0` (or omitted), all Datadog code paths are completely skipped -- zero overhead.

4. **Conditional imports** -- The service uses `try/except ImportError` for all `ddtrace` and `httpx` imports. The application starts and runs normally without these packages installed.

5. **Mirror Prometheus counter names** -- DatadogService record methods intentionally match the Prometheus counter names (`task_assignments_total`, `leases_issued_total`, etc.) so the facade can call both services symmetrically.

6. **Separate try/except per subsystem** -- Following the established MonitoringIntegrationService pattern, each Datadog call is in its own try/except block so a Datadog failure never affects Prometheus or Timeline recording.

7. **NoopContextManager for span helpers** -- When disabled, span methods return a no-op context manager so callers can always use the `with service.workflow_span(...):` pattern without conditional logic.

## Troubleshooting

### Metrics not appearing in dashboard

**Symptom:** Dashboard widgets show "No data" after submitting metrics.

**Causes:**
- Custom metrics take 2-3 minutes to appear in Datadog after submission.
- `DD_API_KEY` not set or invalid. Check: `echo $DD_API_KEY | cut -c1-8`
- `DD_LLMOBS_ENABLED` not set to `1`. The DatadogService is completely disabled without it.
- `httpx` not installed. Verify: `python -c "import httpx; print('ok')"`

**Debug:** Check the service status:
```python
from backend.services.datadog_service import get_datadog_service
dd = get_datadog_service()
print(dd.get_status())
# Expected: {'enabled': True, 'ddtrace_available': True, 'metrics_api_ready': True, 'llmobs_available': True}
```

### "failed to send traces to localhost:8126" in logs

**Symptom:** Log shows `failed to send, dropping N traces to intake at http://localhost:8126`.

**Cause:** The ddtrace APM tracer defaults to sending traces to a local Agent on port 8126. In agentless mode, this is expected and can be ignored -- custom metrics go via HTTP API, LLMObs goes directly to Datadog.

**Fix (optional):** Set `DD_TRACE_AGENT_URL=https://trace.agent.datadoghq.com` to route APM traces agentlessly. Or install the local Datadog Agent to receive them.

### LLM Observability spans not appearing

**Symptom:** No Agent/Workflow/LLM traces in the LLM Observability UI.

**Causes:**
- `DD_LLMOBS_AGENTLESS_ENABLED` not set to `1`. LLMObs needs either agentless mode or a local Agent.
- `DD_LLMOBS_ML_APP` not set. LLMObs requires an ML app name.
- No LLM calls triggered. Spans only appear when `_parse_llm()` is actually called (natural language commands that fail regex parsing).

### Server won't start with ddtrace-run

**Symptom:** `ddtrace-run: command not found`.

**Fix:** Use the full venv path: `./venv/bin/ddtrace-run ./venv/bin/uvicorn backend.main:app`

## Datadog MCP (for AI Agent Access)

To enable AI agents (e.g., Claude Code) to query Datadog data via natural language, add the Datadog MCP server to your Claude Code configuration:

```json
{
    "mcpServers": {
        "datadog": {
            "command": "npx",
            "args": ["-y", "@anthropic/mcp-datadog"],
            "env": {
                "DD_API_KEY": "<your-api-key>",
                "DD_APP_KEY": "<your-app-key>",
                "DD_SITE": "datadoghq.com"
            }
        }
    }
}
```

This gives AI agents access to query traces, metrics, logs, monitors, and dashboards via the MCP protocol.
