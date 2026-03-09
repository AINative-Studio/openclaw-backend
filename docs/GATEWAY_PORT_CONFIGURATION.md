# OpenClaw Gateway Port Configuration

**Issue**: #97 (RESOLVED)
**Date**: March 8, 2026
**Resolution**: TDD-based fix with automated validation

## Problem Summary

The OpenClaw Gateway was not starting on the expected port 18789, causing connection failures between the backend and the gateway.

## Root Cause

The gateway port configuration exists in **two separate files** that must be kept in sync:

1. **`.env` file** — `PORT=18789`
   - Used by Express HTTP server (`process.env.PORT`)
   - Controls which port the gateway's HTTP/WebSocket server binds to

2. **`dbos-config.yaml` file** — `runtimeConfig.port: 18789`
   - Used by DBOS SDK internally
   - Must match the Express server port for proper operation

**The bug**: `dbos-config.yaml` was set to `port: 18790` while `.env` had `PORT=18789`, causing a port mismatch.

## Solution (TDD Approach)

### RED Phase: Write Failing Tests

Created comprehensive test suite in `tests/integration/test_gateway_connection.py`:

1. **Configuration Tests** (4 tests):
   - `test_env_file_has_correct_port` — Verify .env has PORT=18789
   - `test_dbos_config_has_correct_port` — Verify dbos-config.yaml has port: 18789
   - `test_server_js_reads_port_from_env` — Verify server.js reads process.env.PORT
   - `test_configuration_consistency` — Verify both files have matching ports

2. **Integration Tests** (3 tests):
   - `test_health_endpoint_on_correct_port` — Health check responds on 18789
   - `test_root_endpoint_shows_correct_port` — WebSocket URL shows correct port
   - `test_wrong_port_connection_fails` — Connection to 18790 fails

3. **Startup Validation Test** (1 test):
   - `test_gateway_startup_logs_correct_port` — Logs confirm port 18789

**Results**: 2 tests failed (dbos-config port, consistency check) as expected.

### GREEN Phase: Fix the Bug

Changed `openclaw-gateway/dbos-config.yaml`:

```yaml
runtimeConfig:
  port: 18789  # Changed from 18790
```

**Results**: All 8 tests now pass.

### REFACTOR Phase: Prevent Regression

Added three safeguards:

1. **Configuration Validator Script** (`validate-config.js`):
   ```bash
   npm run validate
   ```
   - Checks port consistency between .env and dbos-config.yaml
   - Exits with code 1 if ports don't match
   - Shows clear error messages

2. **Automated Validation in package.json**:
   ```json
   {
     "scripts": {
       "start": "node validate-config.js && node dist/server.js",
       "dev": "tsc && node validate-config.js && node dist/server.js",
       "validate": "node validate-config.js"
     }
   }
   ```
   - `npm start` and `npm run dev` automatically validate before starting
   - Prevents gateway from starting with invalid configuration

3. **Documentation Updates**:
   - Added port configuration section to CLAUDE.md
   - Created this comprehensive troubleshooting guide
   - Added inline comments explaining the two-file requirement

## Configuration Files

### `.env` File

```env
# Server Configuration
PORT=18789
HOST=127.0.0.1
```

This controls the Express HTTP server port.

### `dbos-config.yaml` File

```yaml
runtimeConfig:
  entrypoints:
    - dist/workflows/agent-lifecycle-workflow.js
    - dist/workflows/agent-message-workflow.js
    - dist/workflows/chat-workflow.js
    - dist/workflows/skill-execution-workflow.js
    - dist/workflows/skill-installation-workflow.js
  port: 18789  # MUST match PORT in .env
```

This is the DBOS SDK internal port configuration.

### `dist/server.js` (Compiled TypeScript)

```javascript
const PORT = parseInt(process.env.PORT || '8080');
```

The server reads from `process.env.PORT` (from .env file).

## How to Validate Configuration

### Manual Validation

```bash
cd openclaw-gateway
npm run validate
```

**Expected output (valid)**:
```
✓ Gateway port configuration is valid
  PORT=18789 in both .env and dbos-config.yaml
```

**Expected output (invalid)**:
```
✗ Gateway port configuration is INVALID:
  - PORT mismatch in dbos-config.yaml: expected 18789, got 18790

Expected: PORT=18789 in both .env and dbos-config.yaml
```

### Automated Validation (Recommended)

Always use `npm start` or `npm run dev` to start the gateway. These commands automatically validate configuration before starting.

```bash
cd openclaw-gateway
npm start
```

If configuration is invalid, the gateway will not start.

### Test Suite Validation

Run the integration tests to verify port configuration:

```bash
cd openclaw-backend
python3 -m pytest tests/integration/test_gateway_connection.py::TestGatewayPortConfiguration -v
```

All 4 tests should pass.

## Troubleshooting

### Gateway starts on wrong port (18790)

**Symptom**: Backend cannot connect to gateway, or health check fails.

**Diagnosis**:
```bash
cd openclaw-gateway
npm run validate
```

**Fix**:
1. Edit `dbos-config.yaml` and set `runtimeConfig.port: 18789`
2. Verify with `npm run validate`
3. Restart gateway with `npm start`

### Configuration validation fails

**Symptom**: `npm start` exits with validation errors.

**Diagnosis**: Check both configuration files:
```bash
# Check .env
grep "^PORT=" .env

# Check dbos-config.yaml
grep "port:" dbos-config.yaml
```

**Fix**: Ensure both files have port `18789`:
- `.env`: `PORT=18789`
- `dbos-config.yaml`: `port: 18789`

### Backend connection errors

**Symptom**: Backend logs show connection refused to gateway.

**Diagnosis**: Check which port gateway is actually listening on:
```bash
# In gateway logs, look for:
✓ OpenClaw Gateway listening on port 18789

# Or check with curl:
curl http://localhost:18789/health
```

**Fix**: If gateway is on wrong port, see "Gateway starts on wrong port" above.

## Testing

### Running Tests

```bash
# All configuration tests (fast, no gateway startup)
python3 -m pytest tests/integration/test_gateway_connection.py::TestGatewayPortConfiguration -v

# All integration tests (requires gateway to start)
python3 -m pytest tests/integration/test_gateway_connection.py::TestGatewayConnection -v -m integration

# Quick validation helper
python3 tests/integration/test_gateway_connection.py
```

### Test Coverage

- **Configuration validation**: 4 tests
- **HTTP connectivity**: 3 integration tests
- **Startup logging**: 1 test
- **Total**: 8 tests

All tests use TDD principles:
1. Tests written FIRST (RED phase)
2. Bug fixed to make tests pass (GREEN phase)
3. Validation added to prevent regression (REFACTOR phase)

## Prevention Checklist

Before modifying gateway configuration:

- [ ] Run `npm run validate` to check current state
- [ ] Update BOTH `.env` and `dbos-config.yaml` if changing port
- [ ] Run `npm run validate` to verify changes
- [ ] Run test suite to confirm no regressions
- [ ] Start gateway with `npm start` (validates automatically)
- [ ] Verify health endpoint: `curl http://localhost:18789/health`

## References

- **Issue**: #97 - OpenClaw Gateway not running on port 18789
- **Test file**: `tests/integration/test_gateway_connection.py`
- **Validator**: `openclaw-gateway/validate-config.js`
- **Documentation**: `CLAUDE.md` (Gateway Port Configuration section)

## Lessons Learned

1. **Dual configuration files are error-prone**: When the same value must be set in multiple files, automated validation is essential.

2. **TDD catches configuration bugs**: Writing tests first revealed the exact nature of the port mismatch.

3. **Fail-fast validation prevents runtime issues**: Validating configuration at startup prevents gateway from starting in an invalid state.

4. **DBOS SDK has its own port configuration**: The `runtimeConfig.port` in `dbos-config.yaml` is separate from the Express server port and must match.

5. **Automated validation in CI/CD**: The `validate-config.js` script can be integrated into CI/CD pipelines to catch configuration errors before deployment.
