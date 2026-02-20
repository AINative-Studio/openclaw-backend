# Datadog Observability Integration for AgentClaw

## Summary

Adds full Datadog observability to the AgentClaw backend -- APM tracing, LLM Observability, custom metrics, and a pre-built dashboard. The integration is fully agentless (no local Datadog Agent required) and gated behind `DD_LLMOBS_ENABLED=1` so it has zero impact when disabled.

Three capabilities demonstrated:

1. **Datadog Dashboards** -- 10-widget dashboard with custom metrics submitted via HTTP API
2. **LLM Observability** -- Auto-traced Anthropic calls + manual Agent/Workflow/LLM span hierarchy
3. **Datadog MCP** -- MCP server config for AI agents to query traces, metrics, and dashboards

---

## Quick Start (Don't Need Datadog?)

If you are working on parts of the codebase that do not involve Datadog, you can skip this entirely. The integration is fully gated:

- **Without `ddtrace` installed:** All Datadog imports use `try/except ImportError` -- the app runs normally.
- **Without `DD_LLMOBS_ENABLED=1`:** All DatadogService methods are no-ops. Zero overhead.
- **Standard server start (no Datadog):**

```bash
cd openclaw-backend
./venv/bin/pip install -r requirements.txt
./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

The `ddtrace` package is in `requirements.txt` but does nothing unless the env var is set. You can run the full test suite without any Datadog configuration.

---

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
  +-- Workflow: command_parse_llm
        +-- LLM: anthropic.messages.create (auto-instrumented)
```

### How It Fits Into Existing Monitoring

AgentClaw already has a `MonitoringIntegrationService` facade (E8-S5) that wraps Prometheus, Timeline, and Health services. DatadogService is wired into this facade as a parallel subsystem. Each `on_*()` method calls all three monitoring backends in separate `try/except` blocks -- a Datadog failure never affects Prometheus or Timeline recording.

---

## Files Overview

### Files Created

| File | Purpose |
|------|---------|
| `backend/services/datadog_service.py` | Singleton service: HTTP API metrics + LLMObs span helpers (~310 lines) |
| `.env.datadog.example` | Environment variable template |
| `docs/datadog/agentclaw-dashboard.json` | 10-widget dashboard JSON importable via Datadog API |
| `scripts/create-datadog-dashboard.sh` | curl script to import the dashboard |
| `tests/services/test_datadog_service.py` | 32 BDD-style unit tests (~430 lines) |

### Files Modified

| File | Change |
|------|--------|
| `requirements.txt` | Added `ddtrace>=2.14.0` |
| `backend/main.py` | Added ddtrace auto-patching (FastAPI + Anthropic) + agentless trace URL + LLMObs singleton init at startup |
| `backend/services/monitoring_integration_service.py` | Wired DatadogService into facade -- parallel Datadog calls in 7 `on_*()` methods + `datadog` in `get_status()` |
| `backend/agents/orchestration/command_parser.py` | Wrapped `_parse_llm()` with `workflow_span("command_parse_llm")` + span annotation |
| `backend/agents/orchestration/claude_orchestrator.py` | Wrapped `handle_whatsapp_command()` with `agent_span("claude_orchestrator")` |

---

## Setup Guide

### Prerequisites

- Python 3.10+ with a virtual environment (`./venv`)
- The project cloned and `pip install -r requirements.txt` completed
- A Datadog account ([free 14-day trial](https://www.datadoghq.com/free-datadog-trial/) works)

### Step 1: Get Your Datadog Keys

You need two keys from your Datadog account:

1. **API Key** -- used for metric submission and trace ingestion
   - Go to [Datadog > Organization Settings > API Keys](https://app.datadoghq.com/organization-settings/api-keys)
   - Click "New Key", name it (e.g., `agentclaw-dev`), copy the key

2. **Application Key** -- used for dashboard creation via the API
   - Go to [Datadog > Organization Settings > Application Keys](https://app.datadoghq.com/organization-settings/application-keys)
   - Click "New Key", name it (e.g., `agentclaw-dev`), copy the key

**Never commit these keys to version control.** The `.env.datadog.example` file is a reference template only.

### Step 2: Configure Environment Variables

Add to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
# Datadog -- AgentClaw Observability
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

Then reload your shell:

```bash
source ~/.zshrc
```

Verify the variables are set:

```bash
echo $DD_API_KEY | cut -c1-8    # Should print first 8 chars of your key
echo $DD_LLMOBS_ENABLED          # Should print: 1
```

### Environment Variable Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `DD_API_KEY` | Yes | -- | Datadog API key for metric submission and trace ingestion |
| `DD_APP_KEY` | No | -- | Datadog Application key (only needed for dashboard import script) |
| `DD_SITE` | No | `datadoghq.com` | Datadog site. Use `datadoghq.eu` for EU, `us5.datadoghq.com` for US5, etc. |
| `DD_SERVICE` | No | `agentclaw-backend` | Service name shown in APM |
| `DD_ENV` | No | `development` | Environment tag (development/staging/production) |
| `DD_VERSION` | No | `1.0.0` | Version tag for deployment tracking |
| `DD_LLMOBS_ENABLED` | Yes | `0` | Master switch. Set to `1` to enable all Datadog features. Set to `0` or omit to disable completely. |
| `DD_LLMOBS_ML_APP` | No | `agentclaw` | ML app name in LLM Observability UI |
| `DD_LLMOBS_AGENTLESS_ENABLED` | No | `0` | Set to `1` for agentless mode (no local Datadog Agent). Set to `0` if running the local Agent. |

### Step 3: Install Dependencies

If you haven't already:

```bash
cd openclaw-backend
./venv/bin/pip install -r requirements.txt
```

This installs `ddtrace>=2.14.0` (APM tracing, Anthropic auto-instrumentation, LLMObs SDK) and `httpx` (used for agentless HTTP API metric submission).

### Step 4: Start the Server

```bash
cd openclaw-backend
./venv/bin/ddtrace-run ./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

**Important:** Use the full `./venv/bin/` paths. Running bare `ddtrace-run` or `uvicorn` may fail if your system Python differs from the venv.

On startup you should see these lines in the logs:

```
DatadogService: HTTP API metrics initialized (agentless)
DatadogService: LLMObs enabled (ml_app=agentclaw, agentless=True)
```

Verify the server is running:

```bash
curl http://localhost:8000/health
# Expected: {"status":"ok"}
```

### Step 5: Import the Dashboard

```bash
bash scripts/create-datadog-dashboard.sh
```

This POSTs `docs/datadog/agentclaw-dashboard.json` to the Datadog API and prints the dashboard URL. Requires both `DD_API_KEY` and `DD_APP_KEY` to be set.

Example output:

```
Creating AgentClaw dashboard on datadoghq.com...
Dashboard created successfully (HTTP 200)
URL: https://app.datadoghq.com/dashboard/abc-def-ghi/agentclaw-observability-dashboard
```

### Step 6: Verify End-to-End

| Check | How | Expected |
|-------|-----|----------|
| Server running | `curl http://localhost:8000/health` | `{"status":"ok"}` |
| Datadog status | See "Verify from Python" below | All 4 fields `True` |
| APM traces | Hit any endpoint, then check [Datadog APM > Traces](https://app.datadoghq.com/apm/traces), filter by `service:agentclaw-backend` | FastAPI request traces appear within 1 minute |
| Custom metrics | Hit endpoints to trigger `on_*()` methods, then check [Metrics Explorer](https://app.datadoghq.com/metric/explorer), search `agentclaw.*` | Metrics appear within **2-3 minutes** (Datadog ingestion delay) |
| LLM Observability | Trigger a WhatsApp command parse (calls Anthropic API), then check [LLM Observability](https://app.datadoghq.com/llm/traces) | Agent > Workflow > LLM span hierarchy |
| Dashboard | Open the URL printed by the import script | 10 widgets (some may show "No data" until metrics flow) |

#### Verify from Python

Open a Python shell to programmatically check the service status:

```bash
DD_LLMOBS_ENABLED=1 DD_API_KEY=$DD_API_KEY ./venv/bin/python -c "
from backend.services.datadog_service import get_datadog_service
dd = get_datadog_service()
print(dd.get_status())
"
```

Expected output:

```python
{'enabled': True, 'ddtrace_available': True, 'metrics_api_ready': True, 'llmobs_available': True}
```

If any field is `False`, check:
- `enabled: False` -- `DD_LLMOBS_ENABLED` not set to `1`, or `ddtrace` not installed
- `metrics_api_ready: False` -- `DD_API_KEY` not set, or `httpx` not installed
- `llmobs_available: False` -- `ddtrace.llmobs` import failed (check ddtrace version >= 2.14.0)

#### Submit a Test Metric

```bash
DD_LLMOBS_ENABLED=1 DD_API_KEY=$DD_API_KEY ./venv/bin/python -c "
from backend.services.datadog_service import get_datadog_service
import time
dd = get_datadog_service()
dd.record_task_assignment('success')
dd.record_lease_issued('high')
dd.record_node_crash()
time.sleep(2)  # Wait for background threads to complete
print('Metrics submitted. Check Datadog Metrics Explorer in 2-3 minutes.')
"
```

---

## DatadogService API

### Import

```python
from backend.services.datadog_service import get_datadog_service

dd = get_datadog_service()  # Returns the singleton instance
```

### Metric Methods

All methods are fire-and-forget -- they never raise exceptions and silently no-op when disabled. Metrics are submitted via HTTP POST to `https://api.{DD_SITE}/api/v1/series` in background daemon threads, so they never block the request path.

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
from backend.services.datadog_service import get_datadog_service

dd = get_datadog_service()

with dd.agent_span("my_agent"):
    with dd.workflow_span("my_workflow"):
        result = llm_call(...)
        dd.annotate_span(input_data="prompt", output_data=str(result))
```

When Datadog is disabled, span methods return a `_NoopContextManager` -- callers can always use the `with` pattern without conditional logic.

### Status

```python
dd = get_datadog_service()
dd.get_status()
# Returns:
# {
#     "enabled": True,
#     "ddtrace_available": True,
#     "metrics_api_ready": True,
#     "llmobs_available": True,
# }
```

Also available via the monitoring endpoint: `GET /api/v1/swarm/monitoring/status` includes a `datadog` key in the subsystems dict.

---

## MonitoringIntegrationService Integration

The facade's combined methods now call Prometheus, Timeline, and Datadog in parallel:

```
on_task_leased("task-1", "peer-1", complexity="high")
    +-- timeline_service.record_event(TASK_LEASED, ...)   # try/except
    +-- metrics_service.record_lease_issued("high")        # try/except
    +-- datadog_service.record_lease_issued("high")        # try/except (new)
```

Each subsystem call is in its own `try/except` block -- a Datadog failure never affects Prometheus or Timeline recording.

| Facade Method | Datadog Call |
|---------------|--------------|
| `on_task_leased` | `record_lease_issued(complexity)` |
| `on_task_requeued` | `record_task_requeued(result)` |
| `on_lease_expired` | `record_lease_expired()` |
| `on_lease_revoked` | `record_lease_revoked(reason)` |
| `on_node_crashed` | `record_node_crash()` |
| `on_task_assigned` | `record_task_assignment(status)` |
| `on_recovery_completed` | `record_recovery_operation(type, status)` + `record_recovery_duration(type, seconds)` |

---

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

Widgets 1-2 and 9-10 populate automatically from APM traces (just hit endpoints). Widgets 3-8 require custom metric submission (triggered by `MonitoringIntegrationService.on_*()` calls during real task lifecycle events, or manually via the DatadogService API).

---

## Agentless vs Agent Mode

This integration defaults to **agentless mode** -- all data is sent directly to the Datadog API over HTTPS. No local Datadog Agent daemon is required.

| Feature | Agentless Mode (default) | Agent Mode |
|---------|--------------------------|------------|
| Custom metrics | HTTP API (`api.datadoghq.com/api/v1/series`) | DogStatsD (UDP port 8125) |
| LLM Observability | Direct to Datadog API | Via local Agent |
| APM Traces | Direct to `trace.agent.datadoghq.com` | Via local Agent (port 8126) |
| Setup complexity | Zero -- just env vars | Must install/run Datadog Agent |
| Reliability | Depends on outbound HTTPS | Agent handles buffering/retry |

### How Agentless Works

1. **Custom metrics**: `DatadogService._submit_metric()` POSTs JSON payloads to `https://api.{DD_SITE}/api/v1/series` using `httpx` in background daemon threads.
2. **APM traces**: `backend/main.py` sets `dd_config._trace_agent_url` to `https://trace.agent.{DD_SITE}` so the ddtrace tracer sends traces directly to the Datadog intake instead of `localhost:8126`.
3. **LLM Observability**: The `LLMObs.enable(agentless_enabled=True)` call tells the LLMObs SDK to submit spans directly to the Datadog API.

### Switching to Agent Mode

If you need the reliability of a local Datadog Agent (buffering, retry, lower latency):

1. Install the Datadog Agent:
   ```bash
   DD_API_KEY=<key> DD_SITE=datadoghq.com bash -c "$(curl -L https://install.datadoghq.com/scripts/install_mac_os.sh)"
   ```
2. Set `DD_LLMOBS_AGENTLESS_ENABLED=0` in your shell profile
3. Remove the `dd_config._trace_agent_url` override from `backend/main.py` (line 19) -- the tracer will default to `localhost:8126`

---

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

### Running Tests

```bash
cd openclaw-backend
./venv/bin/python -m pytest tests/services/test_datadog_service.py -v \
    --cov=backend.services.datadog_service --cov-report=term-missing
```

Tests mock all `ddtrace` imports -- they run without a Datadog account or any env vars set.

**Note on coverage module path:** Use dots (`backend.services.datadog_service`), not slashes. The `--cov` flag requires Python module notation.

---

## Design Decisions

1. **Agentless by default** -- Setup should not require installing a separate daemon. HTTP API submission works with just env vars.

2. **Fire-and-forget metrics in daemon threads** -- Metric HTTP POSTs run in background daemon threads (`threading.Thread(daemon=True)`) so they never block the request path. If the Datadog API is unreachable, the metric is silently dropped.

3. **Gated on `DD_LLMOBS_ENABLED`** -- A single env var controls the entire integration. When set to `0` (or omitted), all Datadog code paths are completely skipped -- zero overhead, zero log noise.

4. **Conditional imports** -- The service uses `try/except ImportError` for all `ddtrace` and `httpx` imports. The application starts and runs normally without these packages installed.

5. **Mirror Prometheus counter names** -- DatadogService record methods intentionally match the Prometheus counter names (`task_assignments_total`, `leases_issued_total`, etc.) so the facade can call both services symmetrically.

6. **Separate try/except per subsystem** -- Following the established MonitoringIntegrationService pattern, each Datadog call is in its own try/except block so a Datadog failure never affects Prometheus or Timeline recording.

7. **NoopContextManager for span helpers** -- When disabled, span methods return a no-op context manager so callers can always use the `with service.workflow_span(...):` pattern without conditional logic. A `_noop_ctx()` helper is also used in `command_parser.py` and `claude_orchestrator.py` for the same purpose.

8. **Singleton with double-checked locking** -- `get_datadog_service()` uses `threading.Lock` with double-checked locking to ensure exactly one instance, matching the `PrometheusMetricsService` pattern.

---

## Troubleshooting

### Metrics not appearing in dashboard

**Symptom:** Dashboard widgets show "No data" after submitting metrics.

**Causes:**
- **Ingestion delay:** Custom metrics take **2-3 minutes** to appear in Datadog after submission. APM traces appear faster (~30 seconds). Wait and refresh.
- `DD_API_KEY` not set or invalid. Check: `echo $DD_API_KEY | cut -c1-8`
- `DD_LLMOBS_ENABLED` not set to `1`. The DatadogService is completely disabled without it.
- `httpx` not installed. Verify: `./venv/bin/python -c "import httpx; print('ok')"`

**Debug:** Check the service status (see "Verify from Python" section above).

### "failed to send traces to localhost:8126" in logs

**Symptom:** Log shows `failed to send, dropping N traces to intake at http://localhost:8126`.

**Cause:** This typically means the agentless trace URL override in `backend/main.py` (line 19) is not being applied. This can happen if:
- The server was started without `ddtrace-run` (the `patch()` call requires the ddtrace runtime)
- `DD_LLMOBS_ENABLED` is not set to `1` (the patching block is gated on this env var)
- The `ddtrace` package is not installed

**Fix:** Ensure you start the server with the full command:
```bash
DD_LLMOBS_ENABLED=1 ./venv/bin/ddtrace-run ./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

If the message persists and you want to suppress it, you can also set the env var directly:
```bash
export DD_TRACE_AGENT_URL=https://trace.agent.datadoghq.com
```

### LLM Observability spans not appearing

**Symptom:** No Agent/Workflow/LLM traces in the LLM Observability UI.

**Causes:**
- `DD_LLMOBS_AGENTLESS_ENABLED` not set to `1`. LLMObs needs either agentless mode or a local Agent.
- `DD_LLMOBS_ML_APP` not set. LLMObs requires an ML app name (defaults to `agentclaw` in code).
- No LLM calls triggered. Spans only appear when `_parse_llm()` is actually called (natural language commands that fail regex parsing).

### `ddtrace-run: command not found`

**Symptom:** Running `ddtrace-run uvicorn ...` fails.

**Fix:** Use the full venv path:
```bash
./venv/bin/ddtrace-run ./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

This happens because `ddtrace-run` is installed inside the virtual environment, not globally. If you use `pyenv` or similar, the bare `python`/`ddtrace-run` commands may resolve to the wrong Python installation.

### `python` command not found / wrong Python

**Symptom:** `python -c "..."` fails or uses the wrong Python version.

**Fix:** Always use the venv-qualified path:
```bash
./venv/bin/python -c "import ddtrace; print(ddtrace.__version__)"
```

This is especially common with `pyenv` setups where `python` may not be linked.

### Env vars not available in subprocesses

**Symptom:** Running a Python one-liner to test DatadogService shows `enabled: False` even though `echo $DD_LLMOBS_ENABLED` prints `1`.

**Cause:** If you added the exports to `~/.zshrc` but didn't reload, or if you're running from a script that doesn't source your profile.

**Fix:** Pass env vars explicitly:
```bash
DD_LLMOBS_ENABLED=1 DD_API_KEY=$DD_API_KEY ./venv/bin/python -c "
from backend.services.datadog_service import get_datadog_service
print(get_datadog_service().get_status())
"
```

---

## Datadog MCP (for AI Agent Access)

To enable AI agents (e.g., Claude Code) to query Datadog data via natural language, add the Datadog MCP server to your Claude Code configuration.

**File:** `~/.claude/settings.json` (or project-level `.claude/settings.json`)

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

This gives AI agents access to query traces, metrics, logs, monitors, and dashboards via the MCP protocol. Once configured, you can ask Claude Code questions like:
- "Show me the P95 latency for the agentclaw-backend service"
- "Are there any errors in the last hour?"
- "What does the agentclaw dashboard look like?"

---

## Adding New Metrics

To add a new custom metric to the Datadog integration:

1. **Add a record method** to `backend/services/datadog_service.py`:
   ```python
   def record_my_new_event(self, label: str) -> None:
       self._submit_metric(
           "my_new_event_total", 1, tags=[f"label:{label}"]
       )
   ```

2. **Wire it into the facade** in `backend/services/monitoring_integration_service.py`:
   ```python
   # Inside the relevant on_*() method, add a new try/except block:
   try:
       if self._datadog_service:
           self._datadog_service.record_my_new_event(label)
   except Exception:
       pass
   ```

3. **Add a test** in `tests/services/test_datadog_service.py` following the existing pattern.

4. **(Optional) Add a dashboard widget** -- edit `docs/datadog/agentclaw-dashboard.json` or add it directly in the Datadog UI.

### Adding New LLMObs Spans

To trace a new LLM workflow:

```python
from backend.services.datadog_service import get_datadog_service
from contextlib import contextmanager

try:
    from backend.services.datadog_service import get_datadog_service
except ImportError:
    get_datadog_service = None

@contextmanager
def _noop_ctx():
    yield

# In your method:
dd = get_datadog_service() if get_datadog_service else None
with (dd.workflow_span("my_new_workflow") if dd else _noop_ctx()):
    result = some_llm_call(...)
    if dd:
        dd.annotate_span(input_data=prompt, output_data=str(result))
```

---

## Disabling Datadog

To completely disable Datadog without removing any code:

```bash
# Option 1: Unset the env var
unset DD_LLMOBS_ENABLED

# Option 2: Set to 0
export DD_LLMOBS_ENABLED=0
```

Then restart the server **without** `ddtrace-run`:

```bash
./venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

When disabled:
- All `DatadogService` methods are no-ops (zero overhead)
- No HTTP requests are made to Datadog
- No log output from the DatadogService
- The server runs exactly as it did before the integration
