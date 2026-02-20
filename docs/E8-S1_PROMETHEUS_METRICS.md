# E8-S1: Prometheus Metrics Exporter

Epic E8 — Observability & Monitoring (Phase 4 — Hardening)
Refs: #49

## Overview

Foundational metrics infrastructure for the OpenClaw backend. Instruments the system with Prometheus-compatible counters, gauges, histograms, and info metrics, exposed via a standard `/metrics` endpoint.

## Files Created

| File | Purpose |
|------|---------|
| `backend/services/prometheus_metrics_service.py` | Core metrics registry service with record/observe/collect methods |
| `backend/api/v1/endpoints/metrics.py` | `GET /metrics` endpoint returning Prometheus text format |
| `tests/services/test_prometheus_metrics_service.py` | 40 BDD-style unit tests for the service |
| `tests/api/test_metrics_endpoint.py` | 8 API-level tests for the endpoint |

## Files Modified

| File | Change |
|------|--------|
| `requirements.txt` | Added `prometheus_client>=0.20.0` |

## Metrics Defined

### Counters
- `openclaw_task_assignments_total{status}` — success/failed/no_capable_nodes
- `openclaw_leases_issued_total{complexity}` — low/medium/high
- `openclaw_leases_expired_total`
- `openclaw_leases_revoked_total{reason}` — crash/manual/expired
- `openclaw_node_crashes_total`
- `openclaw_tasks_requeued_total{result}` — success/permanently_failed
- `openclaw_partition_events_total{type}` — detected/recovered
- `openclaw_results_buffered_total`
- `openclaw_results_flushed_total{result}` — success/failed
- `openclaw_capability_validations_total{result}` — valid/capability_missing/resource_exceeded/scope_violation
- `openclaw_tokens_issued_total`
- `openclaw_tokens_revoked_total{reason}` — rotation/compromise/manual
- `openclaw_audit_events_total{type}` — the 9 AuditEventType values
- `openclaw_messages_verified_total{result}` — success/failed
- `openclaw_recovery_operations_total{type,status}`

### Gauges
- `openclaw_active_leases` — pulled from LeaseExpirationService
- `openclaw_buffer_size` — pulled from ResultBufferService
- `openclaw_buffer_utilization_percent` — pulled from ResultBufferService
- `openclaw_partition_degraded` — 0 or 1, pulled from DBOSPartitionDetectionService

### Histograms
- `openclaw_recovery_duration_seconds{type}` — recovery operation durations

### Info
- `openclaw_build_info{version,python_version}`

## Architecture

### Push Model (Counters/Histograms)
Services call `metrics_service.record_*()` at the point of action. Fire-and-forget — the metrics service is optional and services work without it.

### Pull Model (Gauges)
`collect_service_stats()` calls `get_*_stats()` / `get_*_statistics()` on registered services to update gauge values. Called automatically when `/metrics` is scraped.

### Singleton
`get_metrics_service()` returns a thread-safe singleton instance using double-checked locking.

### Isolated Registries in Tests
Each test fixture creates a fresh `CollectorRegistry` to avoid global state pollution between tests.

## Test Results

```
48 passed in 0.15s

Coverage:
  backend/api/v1/endpoints/metrics.py          13      0   100%
  backend/services/prometheus_metrics_service.py 109     4    96%
  TOTAL                                        122      4    97%
```

## Endpoint

```
GET /metrics
Content-Type: text/plain; version=0.0.4; charset=utf-8
```

Compatible with Prometheus, Grafana Agent, Victoria Metrics, or any OpenMetrics-compatible scraper.

## Next Steps (E8-S2+)

- Wire existing services to call `record_*()` methods
- Add Grafana dashboard definitions
- Set up alerting rules
- Add request latency histograms for API endpoints
