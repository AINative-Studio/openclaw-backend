# E8-S3: Task Execution Timeline

## Summary

Implements an in-memory task execution timeline service and REST endpoint (`GET /swarm/timeline`) for tracking and querying task state transitions, lease events, failures, and recoveries across the agent swarm. Provides structured JSON for the agent-swarm-monitor Next.js dashboard.

**Issue:** #51
**Branch:** `feature/51-task-execution-timeline`

## Files Created

| File | Purpose | Lines |
|------|---------|-------|
| `backend/services/task_timeline_service.py` | In-memory timeline service with bounded deque, enum, model, singleton | ~170 |
| `backend/api/v1/endpoints/swarm_timeline.py` | FastAPI endpoint with Pydantic response models, query params | ~160 |
| `tests/services/test_task_timeline_service.py` | 29 BDD-style tests (7 classes) | ~350 |
| `tests/api/test_swarm_timeline_endpoint.py` | 14 BDD-style tests (3 classes) | ~250 |

## Architecture

### TaskTimelineService

- **Bounded deque**: `deque(maxlen=10000)` — oldest events auto-evicted when capacity reached. Matches `node_crash_detection_service` crash_history and `dbos_partition_detection_service` partition_events patterns.
- **Thread-safe**: `threading.Lock` on all read/write operations
- **Singleton**: Double-checked locking via `get_timeline_service()`, consistent with `get_swarm_health_service()`
- **AND-filter queries**: All query parameters are ANDed (matching `AuditQuery` pattern from `audit_event.py`)
- **Newest-first sort**: Query results sorted by timestamp descending for dashboard display
- **Pagination**: Returns `(events, total_count)` tuple where total_count is count before limit/offset

### TimelineEventType Enum (13 types)

| Category | Event Types |
|----------|------------|
| Task lifecycle | TASK_CREATED, TASK_QUEUED, TASK_LEASED, TASK_STARTED, TASK_PROGRESS, TASK_COMPLETED |
| Task failure/recovery | TASK_FAILED, TASK_EXPIRED, TASK_REQUEUED |
| Lease events | LEASE_ISSUED, LEASE_EXPIRED, LEASE_REVOKED |
| Node events | NODE_CRASHED |

### GET /swarm/timeline Endpoint

- **Router prefix**: `/swarm` — shared with E8-S2's `/swarm/health` for API consistency
- **Query parameters**: task_id, peer_id, event_type, since, until, limit (1-1000, default 100), offset (>=0, default 0)
- **Graceful degradation**: Invalid event_type returns empty results (200), not 422
- **Conditional import**: Falls back gracefully if timeline service unavailable (503)
- **Error handling**: Unexpected errors return 500 with detail message

### Response Schema

```json
{
  "events": [
    {
      "event_type": "TASK_LEASED",
      "task_id": "task-001",
      "peer_id": "peer-abc",
      "timestamp": "2026-02-20T12:00:10+00:00",
      "metadata": {"lease_duration": 300}
    }
  ],
  "total_count": 42,
  "limit": 100,
  "offset": 0
}
```

## Design Decisions

1. **In-memory only**: No database persistence (future story). Bounded deque matches existing patterns and provides fast queries without DB overhead.
2. **No existing service modifications**: Standalone service, same principle as E8-S1/S2. Services will call `record_event()` in a future integration story (E8-S5).
3. **String-based event_type in API**: Endpoint accepts raw string and converts to enum internally, enabling graceful degradation for invalid values.
4. **TimelineEvent as Pydantic model**: Enables validation and serialization, consistent with `AuditEvent` pattern.

## Test Coverage

```
Name                                         Stmts   Miss  Cover   Missing
--------------------------------------------------------------------------
backend/api/v1/endpoints/swarm_timeline.py      44      3    93%   30-32
backend/services/task_timeline_service.py       70      0   100%
--------------------------------------------------------------------------
TOTAL                                          114      3    97%
```

- 43 tests total (29 service + 14 endpoint)
- 97% combined coverage
- Only uncovered: conditional import fallback path (lines 30-32)
- All tests passing, no regressions in existing test suite
