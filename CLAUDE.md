# OpenClaw Backend

Backend infrastructure for AgentClaw — an autonomous multi-agent development platform by AINative Studio. Enables AI agent swarms orchestrated via WhatsApp to build full-stack applications from PRDs.

## Tech Stack

- **Python 3.x / FastAPI** — API framework with Pydantic v2 models
- **SQLAlchemy 2.0 / Alembic** — ORM and migrations
- **PyJWT / cryptography / msgpack / base58** — JWT tokens, Ed25519 signing, binary serialization, peer IDs
- **PostgreSQL** — Railway-hosted (port 6432 via PgBouncer, database `ainative_app`)
- **SQLite** — Local dev/test database (fallback via `DATABASE_URL` env var) + persistent result buffering during partitions
- **httpx** — Async HTTP client for DBOS health checks and result submission
- **Node.js (compiled JS)** — OpenClaw Gateway with DBOS durable workflows
- **Go 1.21** — libp2p bootstrap node for P2P discovery
- **WireGuard** — Hub-and-spoke VPN for secure agent-to-agent communication

## Directory Structure

```
backend/
  agents/orchestration/   # WhatsApp command parsing, Claude orchestrator, notification service
  api/v1/endpoints/       # FastAPI endpoints (openclaw_status, wireguard_health, wireguard_provisioning,
                          #   metrics (E8-S1), swarm_health (E8-S2), swarm_timeline (E8-S3),
                          #   swarm_alerts (E8-S4), swarm_monitoring (E8-S5))
  db/                     # SQLAlchemy engine, session factory, Base (get_db dependency, init_db)
  models/                 # ORM models: agent_swarm_lifecycle, task_models (SQLite), task_queue (PostgreSQL),
                          #   task_lease_models (PostgreSQL — TaskLease with JWT, NodeCapability),
                          #   capability_token (E7-S1), message_envelope (E7-S2),
                          #   task_requirements (E7-S4), audit_event (E7-S6), token_revocation (E7-S5)
  networking/             # WireGuard config generation, hub manager, key management, node connector
  p2p/                    # libp2p bootstrap client, Ed25519 identity
    protocols/            # P2P message protocols: task_result, task_request, task_progress, task_failure
  schemas/                # Pydantic schemas: task_schemas, task_lease_schemas
  security/               # Security package (E7): message_signing_service, message_verification_service,
                          #   peer_key_store, token_service
  services/               # Business logic: lifecycle, DBOS monitor, IP pool, WG services,
                          #   task_assignment_orchestrator, lease_validation/issuance/expiration/revocation,
                          #   task_requeue, duplicate_prevention, result_buffer,
                          #   node_crash_detection, dbos_partition_detection, dbos_reconciliation,
                          #   recovery_orchestrator, capability_validation_service (E7-S4),
                          #   token_rotation_service (E7-S5), security_audit_logger (E7-S6),
                          #   prometheus_metrics_service (E8-S1), swarm_health_service (E8-S2),
                          #   task_timeline_service (E8-S3), alert_threshold_service (E8-S4),
                          #   monitoring_integration_service (E8-S5)
integrations/             # OpenClaw WebSocket bridge client, routing monitor CLI
cmd/bootstrap-node/       # Go libp2p DHT bootstrap node
openclaw-gateway/         # DBOS-backed WebSocket gateway (compiled JS in dist/)
tests/                    # ~690 pytest tests (unit, integration, networking, p2p, services, security, api)
docs/                     # Architecture and implementation documentation
```

## API Endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/openclaw/status` | OpenClaw connection status (optional `include_history`) |
| GET | `/wireguard/health` | WireGuard health (optional `include_peers`, `interface`) |
| GET | `/wireguard/quality` | Network quality metrics |
| POST | `/wireguard/provision` | Provision new WireGuard peer |
| GET | `/wireguard/peers` | List all provisioned peers |
| GET | `/wireguard/peers/{node_id}` | Get specific peer config |
| DELETE | `/wireguard/peers/{node_id}` | Remove provisioned peer |
| GET | `/wireguard/pool/stats` | IP pool statistics |
| GET | `/metrics` | Prometheus metrics export (E8-S1) |
| GET | `/swarm/health` | Swarm health snapshot (E8-S2) |
| GET | `/swarm/timeline` | Task execution timeline events (E8-S3) |
| GET | `/swarm/alerts/thresholds` | Alert threshold configuration (E8-S4) |
| PUT | `/swarm/alerts/thresholds` | Update alert thresholds (E8-S4) |
| GET | `/swarm/monitoring/status` | Monitoring infrastructure health (E8-S5) |

Gateway (port 18789): `GET /health`, `GET /workflows/:uuid`, `POST /messages`, `WS /`

## Key Data Models

**AgentSwarmInstance** (SQLAlchemy): UUID PK, name, persona, model, status enum (PROVISIONING/RUNNING/PAUSED/STOPPED/FAILED), OpenClaw session/agent IDs, heartbeat config, error tracking, timestamps.

**ProvisioningRequest** (Pydantic): node_id, public_key, wireguard_public_key, NodeCapabilities (GPU/CPU/memory), semver version.

**WireGuardConfig** (Pydantic): WireGuardInterface (private_key, address, listen_port) + list of WireGuardPeer (public_key, allowed_ips, endpoint).

### Task Queue Models (two implementations)

**`task_models.py`** (SQLite-oriented, used by TaskAssignmentOrchestrator):
- `Task`: Integer PK, `task_id` string (unique), status (5 values: QUEUED/LEASED/RUNNING/COMPLETED/FAILED), payload JSON, idempotency_key
- `TaskLease`: Integer PK, FK on `task_id`, `owner_peer_id`, `token`, `expires_at`

**`task_queue.py`** (PostgreSQL-oriented, used by TaskRequeueService):
- `Task`: UUID PK, task_type, priority enum (LOW/NORMAL/HIGH/CRITICAL), status (7 values: adds EXPIRED/PERMANENTLY_FAILED), `retry_count`/`max_retries`, `required_capabilities` JSON, `result` JSON, `error_message`
- `TaskLease`: UUID PK, FK on task UUID, `peer_id`, `lease_token`, `is_expired`/`is_revoked` flags, `lease_duration_seconds`

**`task_lease_models.py`** (PostgreSQL-oriented, used by TaskLeaseIssuanceService):
- `TaskLease`: UUID PK, `peer_id`, `lease_token` (JWT Text), `is_active` flag, `revoked_at`/`revoke_reason`, `heartbeat_count`/`last_heartbeat_at`, `task_complexity` enum (LOW/MEDIUM/HIGH → 5/10/15 min lease), `node_capabilities` JSON snapshot
- `NodeCapability`: UUID PK, `peer_id` (unique), hardware capabilities JSON (cpu_cores, memory_mb, gpu_available, gpu_memory_mb, storage_mb), availability tracking (`is_available`, `current_task_count`, `max_concurrent_tasks`), health metrics, success/failure counts

**Note**: Three model files (`task_models.py`, `task_queue.py`, `task_lease_models.py`) define overlapping schemas on the same table names using separate SQLAlchemy `Base` instances. They cannot coexist in one database.

### Security Models (Epic E7)

**`capability_token.py`** (E7-S1, Pydantic): `CapabilityToken` with `jti` (auto-generated urlsafe), `peer_id`, `capabilities` list, `limits` (`TokenLimits`: max_gpu_minutes, max_concurrent_tasks), `data_scope` list, `expires_at` (Unix timestamp, validated future), `parent_jti` (for rotation). Helper methods: `has_capability()`, `has_data_access()`, `is_expired()`, `expires_in_seconds()`, `should_renew(threshold)`, `create()` factory.

**`message_envelope.py`** (E7-S2, Pydantic): `MessageEnvelope` with `payload_hash` (format `sha256:<64-hex>`), `peer_id` (pattern `12D3KooW...`), `timestamp` (Unix epoch), `signature` (Base64-encoded Ed25519). Field validators enforce format constraints.

**`task_requirements.py`** (E7-S4, Pydantic): `CapabilityRequirement` (capability_id format `type:value`, required flag), `ResourceLimit` (resource_type `ResourceType` enum: CPU/GPU/MEMORY/STORAGE/NETWORK, min_required, max_allowed, unit), `DataScope` (project_id, data_classification, allowed_regions), `TaskRequirements` (task_id, model_name, capabilities list, resource_limits list, data_scope, estimated_duration_minutes, max_concurrent_tasks). Also includes a simpler `CapabilityToken` placeholder (peer_id, capabilities list, limits dict, data_scopes list) and `ValidationResult` (is_valid, error_code, error_message, missing_capabilities, resource_violations, scope_violations).

**`audit_event.py`** (E7-S6): `AuditEventType` enum (9 values: AUTHENTICATION_SUCCESS/FAILURE, AUTHORIZATION_SUCCESS/FAILURE, TOKEN_ISSUED/RENEWED/REVOKED, SIGNATURE_VERIFIED/FAILED), `AuditEventResult` enum (SUCCESS/FAILURE/DENIED/VERIFIED/INVALID), `AuditEvent` (Pydantic — timestamp, event_type, peer_id, action, resource, result, reason, metadata with sensitive-key validator), `AuditLogEntry` (SQLAlchemy — table `audit_logs`, Integer PK, composite indexes on peer+timestamp, type+timestamp, result+timestamp), `AuditQuery` (Pydantic — filter params with pagination).

**`token_revocation.py`** (E7-S5, SQLAlchemy): `TokenRevocation` table `token_revocations`, PK `jti` (String 64), `revoked_at`, `expires_at`, `reason`, `replaced_by_jti`. Uses `backend.db.base_class.Base`. Methods: `create()` factory, `should_cleanup(retention_days=30)`. Composite index on `expires_at + revoked_at`.

### Task Schemas

**`task_schemas.py`**: `TaskCreateRequest`/`TaskResponse` (CRUD), `TaskLeaseRequest`/`TaskLeaseResponse` (lease issuance), `NodeCapabilitySnapshot`, `TaskResult`/`RejectionNotification`/`RejectionLogEntry`

**`task_lease_schemas.py`**: `TaskLeaseRequest` (task_id, peer_id, node_address, node_capabilities), `TaskLeaseResponse` (lease_id, lease_token JWT, timestamps, task_payload), `TaskLeaseErrorResponse` (error code + message + details)

## Core Flows

1. **Agent Lifecycle**: WhatsApp command → CommandParser (regex+LLM) → ClaudeOrchestrator → AgentSwarmLifecycleService (create → provision → heartbeat → pause/resume → delete) → OpenClawBridge (WebSocket) → Gateway (DBOS workflows)
2. **WireGuard Provisioning**: validate → check duplicates → IPPoolManager.allocate → WireGuardConfigManager.add_peer (atomic write) → WireGuardHubManager (wg syncconf) → return PeerConfiguration. Rollback on failure.
3. **P2P Discovery**: LibP2PBootstrapClient → Go bootstrap-node (Kademlia DHT) → discover_peers_via_dht
4. **Task Assignment** (`TaskAssignmentOrchestrator`): validate task (must be QUEUED) → extract capability requirements from payload → match node by capabilities (GPU, CPU, memory, model) → issue lease via DBOS → create DB lease record → send TaskRequest via libp2p → on libp2p failure: rollback lease + requeue task → update task status to LEASED
5. **Task Result Submission** (`TaskResultProtocol`, protocol `/openclaw/task/result/1.0`): check duplicate → check idempotency key → verify signature → validate lease token format → check lease expiration → validate ownership → validate execution metadata → update task in DBOS
6. **Lease Validation** (`LeaseValidationService`): validate token exists → match task_id → match peer_id (ownership) → check expiration → on late result: reject + notify peer via `/openclaw/task/notification/1.0` + log rejection
7. **Task Requeue** (`TaskRequeueService`): validate task in FAILED/EXPIRED status → check retry_count < max_retries (else mark PERMANENTLY_FAILED) → increment retry_count → clear assigned_peer → revoke all active leases → calculate backoff (`min(30 * 2^retry_count, 3600s)`) → set QUEUED. Batch mode: `requeue_expired_tasks(batch_size=100)`
8. **Lease Issuance** (`TaskLeaseIssuanceService`): validate task exists + QUEUED → fetch NodeCapability (optional) → validate node capabilities against task requirements (CPU, memory, GPU, storage) → calculate expiration from task complexity (LOW=5m, MEDIUM=10m, HIGH=15m) → generate JWT (HS256, claims: task_id, peer_id, exp, iat) → create TaskLease record → set task LEASED → commit (rollback on IntegrityError). Also: `revoke_lease()` sets expires_at to now + task back to QUEUED.
9. **Lease Expiration** (`LeaseExpirationService`): background async loop every `scan_interval` (default 10s) → query leases where `expires_at < now - grace_period` (default 2s) → for each: delete lease record → emit `lease_expired` event (if emitter configured) → requeue task via requeue_service or set status QUEUED directly. Resilient — catches per-lease errors to continue batch. `get_expiration_stats()` returns active/upcoming counts.

### P2P Protocols (`backend/p2p/protocols/`)

10. **Task Request** (`TaskRequestProtocol`, protocol `/openclaw/task/request/1.0`): coordinator signs `TaskRequestMessage` with Ed25519 key → opens libp2p stream to node → sends serialized message → node verifies signature → invokes request handler → returns `TaskAckMessage` (accepted/rejected). Supports `send_batch_requests()` with `asyncio.Semaphore(max_concurrent=10)`. Timeout: 30s default.
11. **Task Progress** (`TaskProgressService`): register lease → agent sends `TaskProgressMessage` (0-100% + intermediate results) → validate lease token → enforce rate limit (min 30s interval) → stream via libp2p → store in history. `ProgressHeartbeatScheduler` wraps async generator for periodic heartbeat updates (enforces minimum 30s).
12. **Task Failure** (`TaskFailureHandler`): agent creates `TaskFailure` message (error_message auto-sanitized for passwords/API keys/tokens) → validate lease token via DBOS → check per-peer rate limit (sliding window, default 10/60s) → update task status to failed → store failure details → categorize error (`FailureType` → `ErrorCategory`: RETRIABLE or PERMANENT) → if retriable + retries remain: increment retry count + requeue. Error categories: RETRIABLE (timeout, connection, runtime, resource_exhausted), PERMANENT (validation, permission_denied).

### Fault Tolerance (Epic E6)

13. **Node Crash Detection** (`NodeCrashDetectionService`, E6-S1): monitors peer heartbeat timeouts (configurable `crash_threshold_seconds`, default 60s) → marks peer "offline" → emits `node_crashed` PeerEvent to registered handlers → triggers `LeaseRevocationService` → starts recovery workflow. Background `start_crash_monitor()` loop with `asyncio.Lock`.
14. **Lease Revocation** (`LeaseRevocationService`, E6-S2): `revoke_leases_on_crash(peer_id)` → batch query active leases → mark `is_revoked=1`, set `revoked_at` → update tasks to EXPIRED, clear `assigned_peer_id` → optionally requeue (if `retry_count < max_retries`). Also: `revoke_lease_by_token()`, `revoke_expired_leases(batch_size)`, `get_revocation_stats()`. Uses `task_queue.py` models.
15. **DBOS Partition Detection** (`DBOSPartitionDetectionService`, E6-S3): periodic health checks against DBOS gateway via httpx → on failure: enter degraded mode → reject new tasks (`PartitionError`), allow in-progress tasks to complete → buffer results in `collections.deque(maxlen=max_buffer_size)` → on recovery: flush buffered results. Background `start_background_checks()`. Singleton via `get_partition_detection_service()`.
16. **Result Buffering** (`ResultBufferService`, E6-S4): persistent SQLite-based FIFO buffer at `/tmp/openclaw_result_buffer.db` → `buffer_result()` stores task results during partition (raises `BufferFullError` at capacity) → `flush_buffer(dbos_client)` submits pending results on reconnect → per-result retry with `max_retry_attempts` (marks `failed` when exceeded) → `start_periodic_flush()` background loop. `BufferMetrics` tracks size, utilization, age.
17. **DBOS Reconciliation** (`DBOSReconciliationService`, E6-S5): state machine (NORMAL → DEGRADED → RECONCILING → NORMAL) → `buffer_result()` converts `TaskResult` to `BufferedResult` (Pydantic validated) → `detect_reconnection()` checks DBOS health → `flush_buffered_results()` validates each result's lease token via `LeaseValidationService`, submits valid results to DBOS via HTTP POST, discards expired/invalid. Depends on E6-S3 and E6-S4.
18. **Recovery Orchestrator** (`RecoveryOrchestrator`, E6-S6): unified recovery for all failure types → `classify_failure()` determines `FailureType` (NODE_CRASH, PARTITION_HEALED, LEASE_EXPIRED, UNKNOWN) → dispatches appropriate workflow → NODE_CRASH: revoke leases + requeue tasks; PARTITION_HEALED: reconcile state + flush buffer; LEASE_EXPIRED: mark expired + requeue → `verify_recovery()` confirms success → `RecoveryResult` Pydantic model with audit trail. Depends on HeartbeatSubscriber, LeaseValidationService, TaskRequeueService.
19. **Duplicate Prevention** (`DuplicatePreventionService`, E6-S7): exactly-once task creation via idempotency keys → `create_task_with_deduplication(task_id, idempotency_key)` → checks DB unique constraint → on `IntegrityError` (race condition): rollback + re-query existing → returns `TaskCreationResult(is_new_task, duplicate_of)`. Standalone, synchronous service.

### Security & Capability (Epic E7)

20. **Capability Token Issuance** (`TokenService`, E7-S1): `encode_token(CapabilityToken)` → builds JWT payload (jti, peer_id, capabilities, limits, data_scope, exp, parent_jti) → signs with HS256 or RS256 → returns JWT string. `decode_token(jwt_string)` → verifies signature → reconstructs `CapabilityToken` → raises `TokenExpiredError`/`InvalidTokenError`. Also: `check_capability(jwt, capability)`, `check_data_access(jwt, project_id)`, `get_token_claims(jwt)` (unverified inspection).
21. **Message Signing** (`MessageSigningService`, E7-S2): requires `LibP2PIdentity` with Ed25519 keypair → `sign_message(payload)` → canonical JSON (sorted keys, no whitespace) → SHA-256 hash → sign `"{hash}:{timestamp}"` with Ed25519 → Base64 encode → return `MessageEnvelope`. `verify_signature(envelope, payload)` → recompute hash → verify Ed25519 signature. `verify_signature_with_public_key()` for verifying other peers' messages.
22. **Message Verification** (`MessageVerificationService`, E7-S3): depends on `PeerKeyStore` → `verify_message(sender_peer_id, payload, signature, timestamp)` → validate timestamp (reject >5min old or >30s future) → lookup public key (with in-memory cache) → Ed25519 verify → track per-peer failure counts (warns at >10 failures). `clear_cache()`, `get_cache_stats()`.
23. **Peer Key Store** (`PeerKeyStore`, E7-S3): in-memory Ed25519 public key storage → `store_public_key(peer_id, key)`, `get_public_key(peer_id)`, `remove_public_key()`, `has_public_key()`, `export_public_key_bytes()` (32-byte raw), `import_public_key_bytes()`, `get_all_peer_ids()`, `clear()`, `count()`.
24. **Capability Validation** (`CapabilityValidationService`, E7-S4): `validate(task_requirements, capability_token, node_usage)` → checks capabilities (required caps present in token) → checks resource limits (concurrent tasks, GPU minutes remaining, GPU memory capacity) → checks data scope (project access) → returns `ValidationResult`. `validate_and_raise()` throws `CapabilityMissingError`/`ResourceLimitExceededError`/`DataScopeViolationError`. Uses `task_requirements.py` CapabilityToken (dict-based limits).
25. **Token Rotation** (`TokenRotationService`, E7-S5): `renew_token(token, extends_by, grace_period)` → creates new `CapabilityToken` with same caps/limits + `parent_jti` link → revokes old token in DB → returns new token. `revoke_token(jti, expires_at, reason)` → persists `TokenRevocation` record. `validate_token(token, grace_period)` → checks expiration + revocation + grace period. `is_within_grace_period(jti, grace=300s)`. `cleanup_old_revocations(retention_days=30)`. `renew_if_needed(token, threshold)` auto-renews if expiring soon. Async methods, uses SQLAlchemy Session.
26. **Security Audit Logging** (`SecurityAuditLogger`, E7-S6): `log_event(AuditEvent)` → validates (rejects sensitive metadata keys) → stores via pluggable `AuditLogStorage` backend. Two storage backends: `FileAuditLogStorage` (RotatingFileHandler, JSON lines, 100MB rotation, 30 backups, in-memory cache of 10K events for queries) and `DatabaseAuditLogStorage` (SQLAlchemy `AuditLogEntry`, composite index queries). Convenience methods: `log_authentication()`, `log_authorization()`, `log_token_event()`, `log_signature_verification()`. Thread-safe with `threading.Lock`.

### Monitoring & Observability (Epic E8)

27. **Prometheus Metrics** (`PrometheusMetricsService`, E8-S1): 15 counter methods (`record_task_assignment()`, `record_lease_issued()`, `record_lease_expired()`, etc.), 4 gauges (active_leases, buffer_size, buffer_utilization_percent, partition_degraded), 1 histogram (recovery_duration_seconds), 1 info (build_info). Gauge pull model via `register_service()` + `collect_service_stats()`. `generate_metrics()` returns Prometheus text format. Singleton via `get_metrics_service()`. Exposed at `GET /metrics`.
28. **Swarm Health Dashboard** (`SwarmHealthService`, E8-S2): `register_service()` for 8 subsystems (lease_expiration, result_buffer, partition_detection, node_crash_detection, lease_revocation, duplicate_prevention, ip_pool, message_verification). `collect_health_snapshot()` calls each subsystem's stats method (async-aware), derives overall status ("healthy"/"degraded"/"unhealthy") based on availability and configurable thresholds. Singleton via `get_swarm_health_service()`. Exposed at `GET /swarm/health`.
29. **Task Execution Timeline** (`TaskTimelineService`, E8-S3): `record_event()` stores `TimelineEvent` (Pydantic) in bounded `deque(maxlen=10000)`. 13 `TimelineEventType` enum values (TASK_CREATED through NODE_CRASHED). `query_events()` with AND filters (task_id, peer_id, event_type, since/until), pagination, newest-first. Thread-safe. Singleton via `get_timeline_service()`. Exposed at `GET /swarm/timeline`.
30. **Alert Threshold Configuration** (`AlertThresholdService`, E8-S4): `AlertThresholdConfig` Pydantic model with 4 tunable thresholds (buffer_utilization=80%, crash_count=3, revocation_rate=50%, ip_pool_utilization=90%). `get_thresholds()` returns copy, `update_thresholds()` with allowed-fields filter, `reset_to_defaults()`. Wired into `SwarmHealthService._derive_health_status()`. Singleton via `get_alert_threshold_service()`. Exposed at `GET/PUT /swarm/alerts/thresholds`.
31. **Monitoring Integration** (`MonitoringIntegrationService`, E8-S5): Unified facade combining E8-S1/S2/S3. 17 `on_*()` fire-and-forget methods (e.g. `on_task_leased()` records both timeline event and Prometheus metric). Separate try/except per subsystem ensures fault isolation. `bootstrap()` registers subsystem services with health and metrics. `get_status()` returns infrastructure health ("operational"/"partial"/"unavailable"). Singleton via `get_monitoring_integration_service()`. Exposed at `GET /swarm/monitoring/status`.

## Environment Variables

```
DATABASE_URL          # PostgreSQL connection string (falls back to sqlite:///./openclaw.db)
OPENCLAW_GATEWAY_URL  # ws://localhost:18789
OPENCLAW_GATEWAY_TOKEN # Gateway auth token
ENVIRONMENT           # production|staging|development|testing|test
ANTHROPIC_API_KEY     # For NL command parsing fallback
SECRET_KEY            # HS256 signing key for JWT lease tokens (required by TaskLeaseIssuanceService)
```

## Running Tests

```bash
source venv/bin/activate
python -m pytest tests/ -v --cov=backend --cov-report=term-missing
```

Markers: `@pytest.mark.integration`, `@pytest.mark.unit`, `@pytest.mark.slow`
Some tests require `DATABASE_URL` for live PostgreSQL access (skipped otherwise).
Several integration tests create file-based SQLite DBs (`test_task_requeue.db`, `test_lease_revocation.db`, `test_recovery_orchestrator.db`).

## Architecture Patterns

- **Protocol/Interface**: `IOpenClawBridge` with Mock and Production implementations
- **Factory + Singleton**: `get_openclaw_bridge()` selects impl by environment
- **Service Layer**: Business logic in services/, endpoints are thin controllers
- **Thread-safe pools**: `threading.Lock` on IPPoolManager and WireGuardConfigManager
- **Atomic file writes**: Temp file + rename for crash-safe config updates
- **Exponential backoff with jitter**: Retries (bridge, connector, notifications) and task requeue backoff
- **DBOS Durable Workflows**: Gateway uses @Workflow/@Step decorators for crash-recoverable agent lifecycle
- **Capability matching**: TaskAssignmentOrchestrator matches node capabilities (bool exact, numeric >=, list subset) to task requirements
- **Lease-based task ownership**: Tasks are leased with expiration; late results are rejected and peers notified
- **JWT lease tokens**: TaskLeaseIssuanceService signs lease tokens with HS256 (claims: task_id, peer_id, exp, iat)
- **Background lease expiration**: LeaseExpirationService runs async loop with configurable scan interval and grace period
- **Idempotent requeue**: Already-QUEUED tasks return success without incrementing retry count
- **Ed25519 message signing**: TaskRequestProtocol signs/verifies messages using Ed25519 keys via `cryptography` library
- **Per-peer rate limiting**: TaskFailureHandler uses sliding window (default 10 reports/60s); TaskProgressService enforces minimum 30s interval per task
- **Error categorization**: FailureType enum maps to RETRIABLE/PERMANENT categories; `categorize_error()` maps Python exception types to categories
- **Sensitive data sanitization**: TaskFailure auto-redacts passwords, API keys, tokens, and connection strings from error messages
- **Degraded mode**: Partition detection rejects new tasks but allows in-progress tasks to complete during DBOS outages
- **Dual buffering**: In-memory deque (partition detection) + persistent SQLite (result buffer) for fault tolerance
- **State machine reconciliation**: NORMAL → DEGRADED → RECONCILING → NORMAL with lease validation before result submission
- **Recovery classification**: RecoveryOrchestrator classifies failures and dispatches appropriate recovery workflows with audit trails
- **Idempotent task creation**: DuplicatePreventionService uses DB unique constraints + IntegrityError catch for race conditions
- **Crash → revocation pipeline**: NodeCrashDetection → LeaseRevocation → RecoveryOrchestrator → TaskRequeue
- **Capability-based authorization**: CapabilityToken grants specific capabilities, resource limits, and data scopes; validated before task assignment
- **Canonical JSON hashing**: MessageSigningService uses sorted keys + no-whitespace JSON for deterministic SHA-256 payload hashing
- **PeerKeyStore with cache**: MessageVerificationService caches Ed25519 public keys in-memory after first lookup from PeerKeyStore
- **Timestamp freshness validation**: Messages rejected if >5 minutes old or >30 seconds in the future (clock skew tolerance)
- **Token rotation with grace period**: Revoked tokens remain valid during configurable grace period (default 5 min) for smooth transition
- **Revocation list with cleanup**: TokenRevocation records kept 30 days post-expiration for audit, then cleaned up
- **Pluggable audit storage**: SecurityAuditLogger accepts any AuditLogStorage backend (file or database) via Strategy pattern
- **Sensitive data prevention in audit logs**: AuditEvent validator blocks metadata keys containing token/password/secret/api_key/PII terms
- **Dual CapabilityToken models**: `capability_token.py` (structured with TokenLimits Pydantic model) vs `task_requirements.py` (dict-based limits) — used by different services
- **Prometheus pull model**: PrometheusMetricsService uses `register_service()` + `collect_service_stats()` to pull gauge values from registered subsystems; counters are pushed via `record_*()` methods
- **Bounded in-memory timeline**: TaskTimelineService uses `deque(maxlen=10000)` — oldest events evicted when capacity exceeded
- **Configurable health thresholds**: AlertThresholdService externalizes 4 hardcoded thresholds from SwarmHealthService; defaults match original values for zero behavioral change
- **Monitoring facade with fault isolation**: MonitoringIntegrationService wraps 3 monitoring singletons; each `on_*()` method uses separate try/except blocks so timeline failure doesn't prevent metrics recording
- **Conditional endpoint imports**: All `/swarm/*` endpoints use `try/except` import with `*_AVAILABLE` flag; return 503 if the backing service is unavailable

## Known Issues

- **Duplicate TaskStatus enums**: Defined in 4 places with different values (5/6/6/7 states) — `task_models.py`, `task_queue.py`, `task_result.py`, `task_schemas.py`
- **Three incompatible ORM model sets**: `task_models.py` (Integer PKs, SQLite), `task_queue.py` (UUID PKs, PostgreSQL), and `task_lease_models.py` (UUID PKs, PostgreSQL) all define `TaskLease` on the same table name with different schemas and different `Base` instances
- **Broken import paths**: `task_lease_issuance_service.py` imports from `backend.models.task` and `backend.models.task_lease` — neither exists as a file (actual files are `task_models.py`, `task_lease_models.py`)
- **Missing async test markers**: `test_task_lease_issuance.py` has 9 async tests without `@pytest.mark.asyncio` — they may not execute unless `asyncio_mode = "auto"` is configured
- **Placeholder validation**: `task_result.py` signature/lease/ownership checks use string pattern matching (e.g., rejecting tokens containing "expired") — not production-ready
- **In-memory stores**: `LeaseValidationService` and `TaskResultProtocol` use Python dicts/sets for lease and idempotency tracking — need to be backed by database in production
- **Missing model file**: `backend/models/task_request_message.py` does not exist — `task_request.py` imports `TaskRequestMessage`/`TaskAckMessage` from it; 13 tests in `test_task_request.py` will fail with ImportError
- **Wrong import name in `protocols/__init__.py`**: Imports `TaskFailureMessage` but the class is actually named `TaskFailure`
- **Pydantic version inconsistency**: `task_failure.py` uses v1-style `@validator`, `task_progress.py` uses v2-style `@field_validator`
- **Unused custom exceptions**: `TaskRequestTimeoutError` and `TaskRequestValidationError` defined but never raised (code uses built-in `asyncio.TimeoutError`/`ValueError`)
- `backend/p2p/__init__.py` imports from `.noise_protocol` which doesn't exist (wrapped in try/except)
- Import paths mix `app.` and `backend.` prefixes depending on deployment context
- Gateway only has compiled JS — no TypeScript source in this repo
- `openclaw-gateway/.env` has a dev token committed (`openclaw-dev-token-12345`)
- **Dual CapabilityToken models**: `capability_token.py` uses structured `TokenLimits` Pydantic model (max_gpu_minutes, max_concurrent_tasks); `task_requirements.py` uses plain dict for limits — `CapabilityValidationService` uses dict-based version, `TokenService`/`TokenRotationService` use structured version; they don't interoperate
- **InvalidCapabilityTokenError defined but never raised**: Declared in `capability_validation_service.py` but no code path raises it
- **AuditLogEntry uses separate Base**: `audit_event.py` creates its own `declarative_base()` instead of using `backend.db.base_class.Base` (unlike `token_revocation.py` which uses the shared Base)
- **TokenRevocation uses `datetime.utcnow()`**: Deprecated in Python 3.12+; `AuditEvent` correctly uses `datetime.now(timezone.utc)` but `TokenRevocation` does not
- **In-memory PeerKeyStore**: Not persisted — all peer keys lost on restart; needs database backing for production
