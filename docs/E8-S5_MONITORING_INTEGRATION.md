# E8-S5: Monitoring Integration with Agent Swarm Monitor

## Summary

Creates a unified facade (`MonitoringIntegrationService`) combining PrometheusMetricsService (E8-S1), TaskTimelineService (E8-S3), and SwarmHealthService (E8-S2) into a single fire-and-forget API. Adds a `GET /swarm/monitoring/status` endpoint for the Agent Swarm Monitor dashboard to verify the monitoring infrastructure itself is operational.

**Issue:** #53
**Branch:** `feature/53-monitoring-integration`

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `backend/services/monitoring_integration_service.py` | Unified facade with 17 `on_*()` methods, bootstrap, get_status, singleton | ~270 |
| `backend/api/v1/endpoints/swarm_monitoring.py` | FastAPI GET endpoint with response models and error handling | ~100 |
| `tests/services/test_monitoring_integration_service.py` | 38 BDD-style tests (8 classes) | ~530 |
| `tests/api/test_swarm_monitoring_endpoint.py` | 9 BDD-style tests (3 classes) | ~150 |

## Files Modified

None. E8-S5 is a pure addition — no existing files were changed.

## Architecture

### MonitoringIntegrationService (Facade)

Services call a single `on_*()` method which internally delegates to both timeline and metrics subsystems in separate try/except blocks:

```
on_task_leased("task-1", "peer-1", complexity="high")
    ├── timeline_service.record_event(TASK_LEASED, ...)   # try/except
    └── metrics_service.record_lease_issued("high")        # try/except
```

### 17 Facade Methods

| # | Method | Timeline Event | Prometheus Call |
|---|--------|---------------|-----------------|
| 1 | `on_task_created(task_id, peer_id, metadata)` | TASK_CREATED | -- |
| 2 | `on_task_queued(task_id, metadata)` | TASK_QUEUED | -- |
| 3 | `on_task_leased(task_id, peer_id, complexity, metadata)` | TASK_LEASED | `record_lease_issued(complexity)` |
| 4 | `on_task_started(task_id, peer_id, metadata)` | TASK_STARTED | -- |
| 5 | `on_task_progress(task_id, peer_id, metadata)` | TASK_PROGRESS | -- |
| 6 | `on_task_completed(task_id, peer_id, metadata)` | TASK_COMPLETED | -- |
| 7 | `on_task_failed(task_id, peer_id, metadata)` | TASK_FAILED | -- |
| 8 | `on_task_expired(task_id, metadata)` | TASK_EXPIRED | -- |
| 9 | `on_task_requeued(task_id, result, metadata)` | TASK_REQUEUED | `record_task_requeued(result)` |
| 10 | `on_lease_expired(task_id, peer_id, metadata)` | LEASE_EXPIRED | `record_lease_expired()` |
| 11 | `on_lease_revoked(task_id, peer_id, reason, metadata)` | LEASE_REVOKED | `record_lease_revoked(reason)` |
| 12 | `on_node_crashed(peer_id, metadata)` | NODE_CRASHED | `record_node_crash()` |
| 13 | `on_task_assigned(task_id, peer_id, status)` | -- | `record_task_assignment(status)` |
| 14 | `on_partition_event(event_type)` | -- | `record_partition_event(type)` |
| 15 | `on_result_buffered(task_id)` | -- | `record_result_buffered()` |
| 16 | `on_result_flushed(task_id, result)` | -- | `record_result_flushed(result)` |
| 17 | `on_recovery_completed(type, status, duration)` | -- | `record_recovery_operation()` + `observe_recovery_duration()` |

### Bootstrap

`bootstrap(services: Dict[str, Any])` registers subsystem service instances with both SwarmHealthService and PrometheusMetricsService for gauge/health collection:

```python
monitor = get_monitoring_integration_service()
monitor.bootstrap({
    "lease_expiration": lease_expiration_service,
    "result_buffer": result_buffer_service,
    "partition_detection": partition_detection_service,
    # ... 8 subsystems
})
```

### API Endpoint

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/swarm/monitoring/status` | Return monitoring infrastructure health |

**Response fields:**
- `status`: `"operational"` / `"partial"` / `"unavailable"`
- `timestamp`: ISO 8601
- `subsystems`: `{metrics/timeline/health: {available: bool}}`
- `registered_health_subsystems`: count of registered services
- `timeline_event_count`: total events recorded
- `bootstrapped`: whether `bootstrap()` has been called

### Singleton

Double-checked locking via `get_monitoring_integration_service()`, consistent with all E8 services.

## Test Coverage

```
Name                                                 Stmts   Miss  Cover
---------------------------------------------------------------------------
backend/services/monitoring_integration_service.py     235     22    91%
backend/api/v1/endpoints/swarm_monitoring.py            34      4    88%
---------------------------------------------------------------------------
TOTAL                                                  269     26    90%
```

### Test Breakdown

| Test File | Tests | Classes |
|-----------|-------|---------|
| `test_monitoring_integration_service.py` | 38 | TestMonitoringIntegrationInit (4), TestBootstrap (4), TestTimelineOnlyMethods (7), TestCombinedMethods (5), TestMetricsOnlyMethods (5), TestFireAndForget (8), TestGetStatus (3), TestSingleton (2) |
| `test_swarm_monitoring_endpoint.py` | 9 | TestMonitoringStatusEndpoint (4), TestMonitoringStatusErrorHandling (3), TestMonitoringStatusIntegration (2) |
| **Total** | **47** | |

## Design Decisions

1. **Unified facade** -- Services depend on one import instead of three separate monitoring singletons
2. **Separate try/except per subsystem** -- Timeline failure doesn't prevent metrics call (and vice versa)
3. **No modification to existing services** -- Pure addition; wiring `on_*()` calls into existing services is a follow-up
4. **Lazy initialization with caching** -- `_initialize_services()` imports singletons with try/except; `TimelineEventType` cached
5. **In-memory only** -- Matches E8 pattern; no database persistence
6. **`bootstrap()` for startup registration** -- Single method to register all subsystem service instances
7. **Monitoring its own health** -- `get_status()` + endpoint lets the dashboard verify monitoring is working
8. **Conditional import in endpoint** -- Falls back gracefully with 503 if service unavailable
