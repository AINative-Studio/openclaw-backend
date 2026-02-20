# E8-S2: Swarm Health Dashboard Data API

## Summary

Implements a unified JSON REST endpoint (`GET /swarm/health`) that aggregates health stats from all 8 backend subsystems into a single dashboard-friendly response. Complementary to E8-S1's Prometheus text format `/metrics` endpoint.

**Issue:** #50
**Branch:** `feature/50-swarm-health-dashboard-api`

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `backend/services/swarm_health_service.py` | Aggregation service with registration, snapshot collection, health derivation, singleton | ~180 |
| `backend/api/v1/endpoints/swarm_health.py` | FastAPI endpoint with Pydantic response models | ~240 |
| `tests/services/test_swarm_health_service.py` | 19 BDD-style tests (4 classes) | ~340 |
| `tests/api/test_swarm_health_endpoint.py` | 9 BDD-style tests (3 classes) | ~280 |

## Architecture

### SwarmHealthService

- **Registration pattern**: Same as `PrometheusMetricsService` — `register_service(name, service)` / `unregister_service(name)` with `threading.Lock`
- **Pull model**: `collect_health_snapshot()` triggers stat collection from all registered services on each request
- **Async-aware dispatch**: Uses `ASYNC_SUBSYSTEMS` set to determine which methods need `await` (result_buffer, lease_revocation)
- **Fault-tolerant**: Individual subsystem failures are caught and reported as `available: false` with error message
- **Singleton**: Double-checked locking via `get_swarm_health_service()`

### Health Status Algorithm

Evaluated in order:
1. `partition_detection.current_state == "degraded"` -> **UNHEALTHY**
2. `available_count == 0` -> **UNHEALTHY**
3. `available_count < total` -> **DEGRADED**
4. Domain thresholds exceeded -> **DEGRADED**:
   - `result_buffer.utilization_percent > 80`
   - `node_crash_detection.recent_crashes >= 3`
   - `lease_revocation.revocation_rate > 50.0`
   - `ip_pool.utilization_percent > 90`
5. Otherwise -> **HEALTHY**

### 8 Registered Subsystems

| Subsystem | Method | Sync/Async |
|-----------|--------|------------|
| lease_expiration | `get_expiration_stats()` | sync |
| result_buffer | `get_buffer_metrics()` | async |
| partition_detection | `get_partition_statistics()` | sync |
| node_crash_detection | `get_crash_statistics()` | sync |
| lease_revocation | `get_revocation_stats()` | async |
| duplicate_prevention | `get_duplicate_statistics()` | sync |
| ip_pool | `get_pool_stats()` | sync |
| message_verification | `get_cache_stats()` | sync |

## API Response

```json
{
  "status": "healthy",
  "timestamp": "2026-02-20T12:00:00+00:00",
  "subsystems_available": 8,
  "subsystems_total": 8,
  "lease_expiration": { "available": true, "active_leases": 10, ... },
  "result_buffer": { "available": true, "utilization_percent": 5.0, ... },
  "partition_detection": { "available": true, "current_state": "normal", ... },
  "node_crash_detection": { "available": true, "recent_crashes": 0, ... },
  "lease_revocation": { "available": true, "revocation_rate": 10.0, ... },
  "duplicate_prevention": { "available": true, "total_tasks": 100, ... },
  "ip_pool": { "available": true, "utilization_percent": 11, ... },
  "message_verification": { "available": true, "cache_size": 5, ... }
}
```

## Test Results

```
28 passed in 0.15s

Coverage:
  backend/api/v1/endpoints/swarm_health.py    97%
  backend/services/swarm_health_service.py     98%
  TOTAL                                        97%
```

## Design Decisions

1. **No existing service modifications** — Only creates the aggregation layer. Services are registered externally.
2. **JSON, not Prometheus** — Complementary to E8-S1. This endpoint serves the dashboard UI; `/metrics` serves Prometheus scrapers.
3. **Fault-tolerant partial responses** — Never returns 500 for individual subsystem failures. Each section shows `available: false` + error.
4. **Pydantic models with `extra="allow"`** — Accommodates subsystem stat dicts that may add fields in future without breaking the endpoint.
