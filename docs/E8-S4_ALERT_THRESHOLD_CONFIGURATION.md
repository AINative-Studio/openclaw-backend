# E8-S4: Alert Threshold Configuration

## Summary

Externalizes the 4 hardcoded alert thresholds in `SwarmHealthService._derive_health_status()` into a configurable service with REST API. Operators can adjust thresholds at runtime via `GET/PUT /swarm/alerts/thresholds` without redeployment.

**Issue:** #52
**Branch:** `feature/52-alert-threshold-configuration`

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `backend/services/alert_threshold_service.py` | In-memory threshold config service with Pydantic model, singleton | ~130 |
| `backend/api/v1/endpoints/swarm_alerts.py` | FastAPI GET/PUT endpoints with request/response models | ~140 |
| `tests/services/test_alert_threshold_service.py` | 20 BDD-style tests (6 classes) | ~250 |
| `tests/api/test_swarm_alerts_endpoint.py` | 15 BDD-style tests (5 classes) | ~220 |

## Files Modified

| File | Change |
|------|--------|
| `backend/services/swarm_health_service.py` | Import `get_alert_threshold_service`, replace 4 hardcoded thresholds with configurable values |
| `tests/services/test_swarm_health_service.py` | Add `TestHealthStatusDerivationWithCustomThresholds` class (6 tests) |

## Architecture

### AlertThresholdConfig (Pydantic Model)

| Field | Type | Default | Validation |
|-------|------|---------|------------|
| `buffer_utilization` | `float` | `80.0` | `ge=0.0, le=100.0` |
| `crash_count` | `int` | `3` | `ge=0` |
| `revocation_rate` | `float` | `50.0` | `ge=0.0, le=100.0` |
| `ip_pool_utilization` | `float` | `90.0` | `ge=0.0, le=100.0` |
| `updated_at` | `datetime` | `now(UTC)` | auto-set |

Defaults exactly match the original hardcoded values for zero behavioral change on deployment.

### AlertThresholdService

- **Thread-safe**: `threading.Lock` on all read/write operations
- **Singleton**: Double-checked locking via `get_alert_threshold_service()`, consistent with `get_swarm_health_service()` and `get_timeline_service()`
- **Copy-on-read**: `get_thresholds()` returns `model_copy()` to prevent mutation of internal state
- **Allowed-fields filter**: `update_thresholds()` only accepts the 4 threshold fields, blocking `updated_at` override or unknown key injection
- **In-memory only**: Matches E8-S3 pattern; no database persistence (future story)

### API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/swarm/alerts/thresholds` | Return current threshold configuration |
| `PUT` | `/swarm/alerts/thresholds` | Partial update (only provided fields change) |

- **Router prefix**: `/swarm` — shared with E8-S2 (`/swarm/health`) and E8-S3 (`/swarm/timeline`)
- **Partial update**: `ThresholdUpdateRequest` has all Optional fields; only non-None values applied
- **Empty body**: Returns current config unchanged (graceful)
- **Validation**: Out-of-range values return 422 via Pydantic
- **Error handling**: Service unavailable returns 503; unexpected errors return 500

### SwarmHealthService Integration

The `_derive_health_status()` method now reads thresholds from `AlertThresholdService` instead of using hardcoded constants:

```python
# Before (hardcoded)
if buffer.get("utilization_percent", 0) > 80:

# After (configurable)
thresholds = get_alert_threshold_service().get_thresholds()
if buffer.get("utilization_percent", 0) > thresholds.buffer_utilization:
```

Operators remain identical (`>` for float thresholds, `>=` for crash_count).

## Test Coverage

```
Name                                          Stmts   Miss  Cover
---------------------------------------------------------------------------
backend/services/alert_threshold_service.py      43      0   100%
backend/api/v1/endpoints/swarm_alerts.py         52      3    94%
backend/services/swarm_health_service.py         84      2    98%
---------------------------------------------------------------------------
TOTAL                                           179      5    97%
```

### Test Breakdown

| Test File | Tests | Classes |
|-----------|-------|---------|
| `test_alert_threshold_service.py` | 20 | TestAlertThresholdConfigModel (7), TestGetThresholds (2), TestUpdateThresholds (7), TestResetToDefaults (1), TestThreadSafety (1), TestSingleton (2) |
| `test_swarm_alerts_endpoint.py` | 15 | TestGetAlertThresholds (3), TestUpdateAlertThresholds (7), TestErrorHandling (4), TestIntegration (1) |
| `test_swarm_health_service.py` (new) | 6 | TestHealthStatusDerivationWithCustomThresholds (6) |
| **Total** | **41** | |

All 19 existing `test_swarm_health_service.py` tests pass unchanged (backward compatibility verified).

## Design Decisions

1. **Defaults match hardcoded values** — Zero behavioral change on deployment
2. **In-memory only** — Consistent with E8-S3 pattern; database persistence deferred
3. **Partial updates via PUT** — All fields Optional; only provided fields change
4. **`model_copy()` on return** — Prevents callers from mutating internal state
5. **Allowed-fields filter** — Blocks injection of `updated_at` or unknown keys
6. **Direct import** — Both files in `backend/services/`; no import cycle risk
7. **Conditional import in endpoint** — Falls back gracefully with 503 if service unavailable
