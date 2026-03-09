# Monitoring Coverage Analysis & Agent Isolation Strategy

**Created:** 2026-03-07
**Context:** Sprint planning for DBOS migration + TDD enforcement for code-writing agents
**Status:** Architecture Design Document

---

## Executive Summary

This document addresses four critical questions:

1. **Schema Fix Timeline:** ✅ IMMEDIATE (done in this session)
2. **DBOS Migration Scope:** ✅ ALL schema/monitoring issues tackled together in next sprint
3. **TDD Enforcement:** ✅ ALWAYS - mandatory for all code-writing agents
4. **Monitoring Coverage:** We currently monitor **SYSTEMS** but NOT **AGENTS** individually
5. **Agent Isolation:** Dagger containers required for TDD enforcement and multi-agent safety

---

## Part 1: Current Monitoring Coverage Analysis

### What We Monitor TODAY

#### ✅ SYSTEM-LEVEL Monitoring (Infrastructure)

**Source:** `PrometheusMetricsService` (E8-S1)

```
┌─────────────────────────────────────────────────────────────┐
│ SYSTEM METRICS (15 Counters + 4 Gauges + 1 Histogram)      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ Task System:                                                │
│   • task_assignments_total [status: success/failure]       │
│   • tasks_requeued_total [result: success/failure]         │
│   • active_leases (gauge)                                  │
│                                                             │
│ Lease System:                                               │
│   • leases_issued_total [complexity: LOW/MEDIUM/HIGH]      │
│   • leases_expired_total                                   │
│   • leases_revoked_total [reason: crash/timeout/manual]    │
│                                                             │
│ Fault Tolerance:                                            │
│   • node_crashes_total                                     │
│   • partition_events_total [type: detected/healed]         │
│   • recovery_duration_seconds (histogram)                  │
│                                                             │
│ Buffer System:                                              │
│   • results_buffered_total                                 │
│   • results_flushed_total [result: success/failure]        │
│   • buffer_size (gauge)                                    │
│   • buffer_utilization_percent (gauge)                     │
│                                                             │
│ Security:                                                   │
│   • capability_validations_total [result: valid/invalid]   │
│   • tokens_issued_total                                    │
│   • tokens_revoked_total [reason: rotation/compromise]     │
│   • signatures_verified_total [result: valid/invalid]      │
│   • signature_failures_total                               │
│                                                             │
│ Health:                                                     │
│   • partition_degraded (gauge, 0 or 1)                     │
│   • build_info (info metric with version/platform)         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Source:** `SwarmHealthService` (E8-S2)

```
┌─────────────────────────────────────────────────────────────┐
│ SUBSYSTEM HEALTH (8 Services)                               │
├─────────────────────────────────────────────────────────────┤
│ 1. lease_expiration        → get_expiration_stats()        │
│ 2. result_buffer           → get_buffer_metrics()          │
│ 3. partition_detection     → get_health_status()           │
│ 4. node_crash_detection    → get_crash_stats()             │
│ 5. lease_revocation        → get_revocation_stats()        │
│ 6. duplicate_prevention    → get_duplicate_statistics()    │
│ 7. ip_pool                 → get_pool_stats()              │
│ 8. message_verification    → get_cache_stats()             │
└─────────────────────────────────────────────────────────────┘
```

**Source:** `TaskTimelineService` (E8-S3)

```
┌─────────────────────────────────────────────────────────────┐
│ EVENT TIMELINE (13 Event Types, 10K bounded deque)          │
├─────────────────────────────────────────────────────────────┤
│ • TASK_CREATED, TASK_QUEUED, TASK_LEASED                   │
│ • TASK_RUNNING, TASK_COMPLETED, TASK_FAILED                │
│ • TASK_EXPIRED, TASK_REQUEUED                              │
│ • LEASE_ISSUED, LEASE_EXPIRED, LEASE_REVOKED               │
│ • PARTITION_DETECTED, NODE_CRASHED                          │
└─────────────────────────────────────────────────────────────┘
```

#### ❌ AGENT-LEVEL Monitoring (MISSING)

**What's NOT Monitored:**

```
┌─────────────────────────────────────────────────────────────┐
│ AGENT METRICS (NOT IMPLEMENTED)                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│ ❌ Per-Agent Performance:                                   │
│    • agent_task_duration_seconds [agent_id, task_type]     │
│    • agent_task_success_rate [agent_id]                    │
│    • agent_active_duration [agent_id]                      │
│    • agent_idle_duration [agent_id]                        │
│                                                             │
│ ❌ Per-Agent Resource Usage:                                │
│    • agent_cpu_usage_percent [agent_id]                    │
│    • agent_memory_usage_bytes [agent_id]                   │
│    • agent_gpu_usage_percent [agent_id]  (if applicable)   │
│    • agent_network_bytes_sent [agent_id]                   │
│    • agent_network_bytes_received [agent_id]               │
│                                                             │
│ ❌ Per-Agent Lifecycle:                                     │
│    • agent_status [agent_id, status: RUNNING/PAUSED/etc]   │
│    • agent_heartbeats_total [agent_id, result]             │
│    • agent_errors_total [agent_id, error_type]             │
│    • agent_restarts_total [agent_id, reason]               │
│                                                             │
│ ❌ Per-Agent Quality (for code-writing agents):             │
│    • agent_tests_run_total [agent_id, result]              │
│    • agent_test_coverage_percent [agent_id]                │
│    • agent_code_quality_score [agent_id]                   │
│    • agent_build_failures_total [agent_id]                 │
│                                                             │
│ ❌ Per-Agent Behavior:                                      │
│    • agent_skill_invocations_total [agent_id, skill_name]  │
│    • agent_api_calls_total [agent_id, endpoint]            │
│    • agent_file_operations_total [agent_id, operation]     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### Current Agent Models

**Source:** `AgentSwarmInstance` (ORM Model)

```python
class AgentSwarmInstance:
    """
    Represents an agent in the swarm

    Tracked Fields:
    - id (UUID)
    - name, persona, model
    - status (PROVISIONING/RUNNING/PAUSED/STOPPED/FAILED)
    - openclaw_session_id, openclaw_agent_id
    - heartbeat_interval
    - last_heartbeat_at
    - consecutive_heartbeat_failures
    - error_message, error_count
    - created_at, updated_at
    """
```

**Source:** `AgentHeartbeatExecution` (ORM Model)

```python
class AgentHeartbeatExecution:
    """
    Records heartbeat execution history

    Tracked Fields:
    - id (UUID)
    - agent_id (FK to AgentSwarmInstance)
    - status (PENDING/SUCCESS/FAILED)
    - started_at, completed_at
    - error_message
    - response_data
    """
```

**What We Track vs What We DON'T:**

```
✅ Currently Tracked:
   • Agent existence (created, deleted)
   • Agent status changes (RUNNING → PAUSED → STOPPED)
   • Heartbeat success/failure (per execution)
   • Error messages and counts

❌ NOT Tracked:
   • Individual task assignments PER AGENT
   • Task completion time PER AGENT
   • Resource consumption PER AGENT
   • Code quality metrics PER AGENT (critical for TDD!)
   • Test execution results PER AGENT
   • Skill usage patterns PER AGENT
   • Container isolation metrics (not containerized yet!)
```

---

## Part 2: Recommended Agent-Level Monitoring

### New Metrics to Add

**Priority 1: Agent Performance Tracking**

```python
# Add to PrometheusMetricsService

# Agent task metrics
self._agent_tasks_assigned_total = Counter(
    f"{ns}_agent_tasks_assigned_total",
    "Total tasks assigned per agent",
    ["agent_id", "agent_name", "task_type"],
    registry=reg,
)

self._agent_tasks_completed_total = Counter(
    f"{ns}_agent_tasks_completed_total",
    "Total tasks completed per agent",
    ["agent_id", "agent_name", "result"],  # result: success/failure
    registry=reg,
)

self._agent_task_duration_seconds = Histogram(
    f"{ns}_agent_task_duration_seconds",
    "Task execution duration per agent",
    ["agent_id", "agent_name", "task_type"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600],
    registry=reg,
)

# Agent resource metrics (gauges pulled from container stats)
self._agent_cpu_usage_percent = Gauge(
    f"{ns}_agent_cpu_usage_percent",
    "CPU usage per agent",
    ["agent_id", "agent_name"],
    registry=reg,
)

self._agent_memory_usage_bytes = Gauge(
    f"{ns}_agent_memory_usage_bytes",
    "Memory usage per agent",
    ["agent_id", "agent_name"],
    registry=reg,
)

self._agent_active_tasks = Gauge(
    f"{ns}_agent_active_tasks",
    "Current active tasks per agent",
    ["agent_id", "agent_name"],
    registry=reg,
)
```

**Priority 2: Code Quality Metrics (TDD Enforcement)**

```python
# TDD and code quality metrics
self._agent_tests_run_total = Counter(
    f"{ns}_agent_tests_run_total",
    "Total tests run by code-writing agents",
    ["agent_id", "agent_name", "result"],  # result: passed/failed
    registry=reg,
)

self._agent_test_coverage_percent = Gauge(
    f"{ns}_agent_test_coverage_percent",
    "Test coverage percentage per agent",
    ["agent_id", "agent_name", "project"],
    registry=reg,
)

self._agent_build_failures_total = Counter(
    f"{ns}_agent_build_failures_total",
    "Total build failures per agent",
    ["agent_id", "agent_name", "failure_type"],
    registry=reg,
)

self._agent_code_quality_violations_total = Counter(
    f"{ns}_agent_code_quality_violations_total",
    "Code quality violations detected",
    ["agent_id", "agent_name", "violation_type"],  # type: lint/format/security
    registry=reg,
)
```

**Priority 3: Container Isolation Metrics**

```python
# Dagger container metrics
self._agent_container_starts_total = Counter(
    f"{ns}_agent_container_starts_total",
    "Total container starts per agent",
    ["agent_id", "agent_name"],
    registry=reg,
)

self._agent_container_failures_total = Counter(
    f"{ns}_agent_container_failures_total",
    "Total container failures per agent",
    ["agent_id", "agent_name", "failure_reason"],
    registry=reg,
)

self._agent_container_runtime_seconds = Histogram(
    f"{ns}_agent_container_runtime_seconds",
    "Container runtime duration per agent task",
    ["agent_id", "agent_name"],
    buckets=[10, 30, 60, 300, 600, 1800, 3600],
    registry=reg,
)
```

### New Service: AgentMetricsCollector

```python
"""
Agent-level metrics collection service

Collects per-agent metrics for:
- Task performance (assignment, completion, duration)
- Resource usage (CPU, memory, network)
- Code quality (tests, coverage, builds)
- Container isolation (Dagger runtime)

Integrates with PrometheusMetricsService for unified export.
"""

class AgentMetricsCollector:
    """
    Collects and reports metrics for individual agents
    """

    def __init__(
        self,
        db: Session,
        metrics_service: PrometheusMetricsService,
        container_client: Optional["DaggerClient"] = None
    ):
        self.db = db
        self.metrics_service = metrics_service
        self.container_client = container_client

    async def record_task_assigned(
        self,
        agent_id: str,
        agent_name: str,
        task_type: str
    ) -> None:
        """Record task assignment to specific agent"""
        self.metrics_service._agent_tasks_assigned_total.labels(
            agent_id=agent_id,
            agent_name=agent_name,
            task_type=task_type
        ).inc()

    async def record_task_completed(
        self,
        agent_id: str,
        agent_name: str,
        result: str,  # "success" or "failure"
        duration_seconds: float
    ) -> None:
        """Record task completion with duration"""
        # Count completion
        self.metrics_service._agent_tasks_completed_total.labels(
            agent_id=agent_id,
            agent_name=agent_name,
            result=result
        ).inc()

        # Record duration
        self.metrics_service._agent_task_duration_seconds.labels(
            agent_id=agent_id,
            agent_name=agent_name,
            task_type="unknown"  # TODO: pass task_type
        ).observe(duration_seconds)

    async def collect_resource_stats(self, agent_id: str) -> None:
        """
        Collect resource usage from agent's container

        Pulls CPU, memory, network stats from Dagger container
        """
        if not self.container_client:
            return

        agent = self.db.query(AgentSwarmInstance).filter_by(id=agent_id).first()
        if not agent:
            return

        # Get container stats from Dagger
        stats = await self.container_client.get_container_stats(agent_id)

        # Update gauges
        self.metrics_service._agent_cpu_usage_percent.labels(
            agent_id=str(agent_id),
            agent_name=agent.name
        ).set(stats.get("cpu_percent", 0))

        self.metrics_service._agent_memory_usage_bytes.labels(
            agent_id=str(agent_id),
            agent_name=agent.name
        ).set(stats.get("memory_bytes", 0))

    async def record_test_execution(
        self,
        agent_id: str,
        agent_name: str,
        result: str,  # "passed" or "failed"
        coverage_percent: Optional[float] = None
    ) -> None:
        """Record test execution results for code-writing agents"""
        self.metrics_service._agent_tests_run_total.labels(
            agent_id=agent_id,
            agent_name=agent_name,
            result=result
        ).inc()

        if coverage_percent is not None:
            self.metrics_service._agent_test_coverage_percent.labels(
                agent_id=agent_id,
                agent_name=agent_name,
                project="unknown"  # TODO: track project context
            ).set(coverage_percent)
```

---

## Part 3: Dagger Container Isolation Strategy

### Why Dagger for Agent Isolation?

**Problem:** Code-writing agents running tests directly on host can:
- Conflict with other agents' processes
- Pollute shared dependency caches
- Interfere with system Python/Node environments
- Cause port conflicts (e.g., multiple test servers on same port)
- Leave orphaned processes after crashes

**Solution:** Dagger provides:
- ✅ Isolated containers per agent task
- ✅ Reproducible build environments
- ✅ Automatic cleanup after task completion
- ✅ Built-in caching for dependencies
- ✅ Multi-language support (Python, Node, Go, etc.)
- ✅ Programmatic API (no Dockerfile required)

### Dagger Architecture for OpenClaw

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      OpenClaw Backend (FastAPI)                         │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  AgentSwarmLifecycleService                                      │  │
│  │  • Receives task assignment for code-writing agent               │  │
│  │  • Checks if agent requires container isolation                  │  │
│  │  • Delegates to DaggerOrchestrationService                       │  │
│  └────────────────────┬─────────────────────────────────────────────┘  │
│                       │                                                 │
│                       ▼                                                 │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  DaggerOrchestrationService                                      │  │
│  │  • Creates isolated Dagger container for agent task              │  │
│  │  • Mounts code repository (read-only or read-write)              │  │
│  │  • Installs dependencies (cached by Dagger)                      │  │
│  │  • Runs TDD workflow: test → code → test → repeat               │  │
│  │  • Enforces test-first policy (fail task if tests not run)      │  │
│  │  • Collects metrics (test results, coverage, build status)      │  │
│  │  • Cleans up container after task completion/failure            │  │
│  └────────────────────┬─────────────────────────────────────────────┘  │
│                       │                                                 │
└───────────────────────┼─────────────────────────────────────────────────┘
                        │
                        ▼
              ┌──────────────────┐
              │  Dagger Engine   │
              │  (local daemon)  │
              └─────────┬────────┘
                        │
        ┌───────────────┼───────────────┐
        │               │               │
        ▼               ▼               ▼
  ┌─────────┐    ┌─────────┐    ┌─────────┐
  │ Agent 1 │    │ Agent 2 │    │ Agent 3 │
  │Container│    │Container│    │Container│
  │         │    │         │    │         │
  │ Python  │    │ Node.js │    │ Go      │
  │ pytest  │    │ jest    │    │ go test │
  │ /workspace│  │ /workspace│  │ /workspace│
  └─────────┘    └─────────┘    └─────────┘
      Isolated       Isolated       Isolated
      filesystem     filesystem     filesystem
      processes      processes      processes
      network        network        network
```

### Implementation: DaggerOrchestrationService

**File:** `backend/services/dagger_orchestration_service.py`

```python
"""
Dagger Orchestration Service

Provides container isolation for code-writing agents using Dagger.
Enforces TDD workflows and collects agent-level metrics.

Dependencies:
- dagger-io (pip install dagger-io)
- Docker daemon running locally

Epic: Agent Isolation & TDD Enforcement
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path
from datetime import datetime, timezone

# Dagger Python SDK
import dagger
from dagger import Client, Container, Directory

from backend.models.agent_swarm_lifecycle import AgentSwarmInstance
from backend.services.prometheus_metrics_service import get_metrics_service

logger = logging.getLogger(__name__)


class DaggerOrchestrationService:
    """
    Orchestrates isolated container execution for agents using Dagger

    Features:
    - Per-agent container isolation
    - TDD workflow enforcement
    - Automatic dependency caching
    - Resource limit enforcement
    - Metrics collection
    """

    def __init__(self):
        self.metrics = get_metrics_service()
        self._active_containers: Dict[str, Container] = {}

    async def execute_agent_task(
        self,
        agent: AgentSwarmInstance,
        task_payload: Dict[str, Any],
        workspace_path: Path,
        enforce_tdd: bool = True
    ) -> Dict[str, Any]:
        """
        Execute agent task in isolated Dagger container

        Args:
            agent: AgentSwarmInstance to execute task
            task_payload: Task configuration and requirements
            workspace_path: Local path to code repository
            enforce_tdd: If True, fail task if tests not run first

        Returns:
            Task execution result with metrics

        Raises:
            DaggerExecutionError: If container execution fails
            TDDViolationError: If TDD not followed (when enforce_tdd=True)
        """
        start_time = datetime.now(timezone.utc)
        agent_id = str(agent.id)
        agent_name = agent.name

        logger.info(
            f"Starting Dagger container for agent {agent_name} (ID: {agent_id})"
        )

        try:
            # Initialize Dagger client
            async with dagger.Connection() as client:
                # Record container start
                self.metrics.record_agent_container_start(agent_id, agent_name)

                # Build isolated container based on agent language/framework
                container = await self._build_agent_container(
                    client=client,
                    agent=agent,
                    workspace_path=workspace_path,
                    task_payload=task_payload
                )

                # Store active container reference
                self._active_containers[agent_id] = container

                # Execute TDD workflow
                if enforce_tdd:
                    result = await self._execute_tdd_workflow(
                        container=container,
                        agent=agent,
                        task_payload=task_payload
                    )
                else:
                    result = await self._execute_standard_workflow(
                        container=container,
                        agent=agent,
                        task_payload=task_payload
                    )

                # Collect container metrics
                duration = (datetime.now(timezone.utc) - start_time).total_seconds()
                self.metrics.record_agent_container_runtime(
                    agent_id, agent_name, duration
                )

                # Cleanup
                del self._active_containers[agent_id]

                return result

        except Exception as e:
            # Record failure
            self.metrics.record_agent_container_failure(
                agent_id, agent_name, type(e).__name__
            )

            # Cleanup on error
            if agent_id in self._active_containers:
                del self._active_containers[agent_id]

            logger.error(
                f"Dagger execution failed for agent {agent_name}: {e}",
                exc_info=True
            )
            raise DaggerExecutionError(
                f"Container execution failed for agent {agent_name}"
            ) from e

    async def _build_agent_container(
        self,
        client: Client,
        agent: AgentSwarmInstance,
        workspace_path: Path,
        task_payload: Dict[str, Any]
    ) -> Container:
        """
        Build isolated container for agent with dependencies

        Language detection based on agent.model or task_payload
        """
        # Detect language/framework from agent model or task
        language = task_payload.get("language", "python")

        if language == "python":
            return await self._build_python_container(
                client, workspace_path, task_payload
            )
        elif language == "node":
            return await self._build_node_container(
                client, workspace_path, task_payload
            )
        elif language == "go":
            return await self._build_go_container(
                client, workspace_path, task_payload
            )
        else:
            raise ValueError(f"Unsupported language: {language}")

    async def _build_python_container(
        self,
        client: Client,
        workspace_path: Path,
        task_payload: Dict[str, Any]
    ) -> Container:
        """Build Python container with pytest and dependencies"""

        # Start from Python base image
        python_version = task_payload.get("python_version", "3.11")
        container = client.container().from_(f"python:{python_version}-slim")

        # Mount workspace (read-write for code generation)
        workspace_dir = client.host().directory(
            str(workspace_path),
            exclude=[".git", "__pycache__", "*.pyc", ".pytest_cache", "venv"]
        )
        container = container.with_mounted_directory("/workspace", workspace_dir)
        container = container.with_workdir("/workspace")

        # Install dependencies (cached by Dagger)
        requirements_file = task_payload.get("requirements_file", "requirements.txt")
        if Path(workspace_path / requirements_file).exists():
            container = container.with_exec([
                "pip", "install", "-r", requirements_file
            ])

        # Install test dependencies
        container = container.with_exec([
            "pip", "install", "pytest", "pytest-cov", "pytest-timeout"
        ])

        return container

    async def _build_node_container(
        self,
        client: Client,
        workspace_path: Path,
        task_payload: Dict[str, Any]
    ) -> Container:
        """Build Node.js container with jest and dependencies"""

        node_version = task_payload.get("node_version", "20")
        container = client.container().from_(f"node:{node_version}-slim")

        # Mount workspace
        workspace_dir = client.host().directory(
            str(workspace_path),
            exclude=[".git", "node_modules", ".next", "dist"]
        )
        container = container.with_mounted_directory("/workspace", workspace_dir)
        container = container.with_workdir("/workspace")

        # Install dependencies
        if Path(workspace_path / "package.json").exists():
            container = container.with_exec(["npm", "install"])

        return container

    async def _build_go_container(
        self,
        client: Client,
        workspace_path: Path,
        task_payload: Dict[str, Any]
    ) -> Container:
        """Build Go container with go test"""

        go_version = task_payload.get("go_version", "1.21")
        container = client.container().from_(f"golang:{go_version}")

        # Mount workspace
        workspace_dir = client.host().directory(
            str(workspace_path),
            exclude=[".git", "vendor"]
        )
        container = container.with_mounted_directory("/workspace", workspace_dir)
        container = container.with_workdir("/workspace")

        # Download Go modules
        if Path(workspace_path / "go.mod").exists():
            container = container.with_exec(["go", "mod", "download"])

        return container

    async def _execute_tdd_workflow(
        self,
        container: Container,
        agent: AgentSwarmInstance,
        task_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute TDD workflow: test → code → test → repeat

        ENFORCES:
        1. Tests must be run BEFORE code changes
        2. Tests must pass AFTER code changes
        3. Coverage threshold must be met (configurable)

        Raises:
            TDDViolationError: If workflow not followed
        """
        language = task_payload.get("language", "python")
        min_coverage = task_payload.get("min_coverage_percent", 80)

        # STEP 1: Run tests BEFORE code changes (baseline)
        logger.info(f"TDD Step 1: Running baseline tests for {agent.name}")
        baseline_result = await self._run_tests(
            container, language, check_coverage=False
        )

        if not baseline_result["executed"]:
            raise TDDViolationError(
                "TDD violation: No tests found or executed before code changes"
            )

        # Record baseline test execution
        self.metrics.record_agent_test_execution(
            agent_id=str(agent.id),
            agent_name=agent.name,
            result="passed" if baseline_result["passed"] else "failed"
        )

        # STEP 2: Agent writes code (simulated here - in reality, agent modifies files)
        logger.info(f"TDD Step 2: Agent {agent.name} writing code")
        # This would call agent's code generation logic
        # For now, assume code is written by agent

        # STEP 3: Run tests AFTER code changes (verification)
        logger.info(f"TDD Step 3: Running verification tests for {agent.name}")
        verification_result = await self._run_tests(
            container, language, check_coverage=True
        )

        if not verification_result["passed"]:
            raise TDDViolationError(
                f"TDD violation: Tests failed after code changes\n"
                f"Failures: {verification_result['failures']}"
            )

        # Check coverage threshold
        coverage = verification_result.get("coverage_percent", 0)
        if coverage < min_coverage:
            raise TDDViolationError(
                f"TDD violation: Coverage {coverage}% below threshold {min_coverage}%"
            )

        # Record successful verification
        self.metrics.record_agent_test_execution(
            agent_id=str(agent.id),
            agent_name=agent.name,
            result="passed"
        )
        self.metrics.record_agent_test_coverage(
            agent_id=str(agent.id),
            agent_name=agent.name,
            coverage_percent=coverage
        )

        return {
            "success": True,
            "baseline_tests": baseline_result,
            "verification_tests": verification_result,
            "coverage_percent": coverage,
            "tdd_enforced": True
        }

    async def _run_tests(
        self,
        container: Container,
        language: str,
        check_coverage: bool = False
    ) -> Dict[str, Any]:
        """
        Run tests in container and parse results

        Returns:
            {
                "executed": bool,
                "passed": bool,
                "total": int,
                "failures": int,
                "coverage_percent": float (if check_coverage=True)
            }
        """
        try:
            if language == "python":
                # Run pytest with coverage
                if check_coverage:
                    test_output = await container.with_exec([
                        "pytest",
                        "--cov=.",
                        "--cov-report=term-missing",
                        "-v"
                    ]).stdout()
                else:
                    test_output = await container.with_exec([
                        "pytest", "-v"
                    ]).stdout()

                return self._parse_pytest_output(test_output)

            elif language == "node":
                # Run jest with coverage
                if check_coverage:
                    test_output = await container.with_exec([
                        "npm", "test", "--", "--coverage"
                    ]).stdout()
                else:
                    test_output = await container.with_exec([
                        "npm", "test"
                    ]).stdout()

                return self._parse_jest_output(test_output)

            elif language == "go":
                # Run go test with coverage
                if check_coverage:
                    test_output = await container.with_exec([
                        "go", "test", "-v", "-coverprofile=coverage.out", "./..."
                    ]).stdout()
                    coverage_output = await container.with_exec([
                        "go", "tool", "cover", "-func=coverage.out"
                    ]).stdout()
                else:
                    test_output = await container.with_exec([
                        "go", "test", "-v", "./..."
                    ]).stdout()
                    coverage_output = None

                return self._parse_go_test_output(test_output, coverage_output)

        except Exception as e:
            logger.error(f"Test execution failed: {e}")
            return {
                "executed": False,
                "passed": False,
                "total": 0,
                "failures": 0,
                "error": str(e)
            }

    def _parse_pytest_output(self, output: str) -> Dict[str, Any]:
        """Parse pytest output for test results and coverage"""
        # Example: "5 passed, 2 failed in 1.23s"
        # Example: "TOTAL ... 85%"

        result = {
            "executed": True,
            "passed": "failed" not in output.lower(),
            "total": 0,
            "failures": 0,
            "coverage_percent": 0.0
        }

        # Parse test counts
        import re
        passed_match = re.search(r"(\d+) passed", output)
        failed_match = re.search(r"(\d+) failed", output)

        if passed_match:
            result["total"] += int(passed_match.group(1))
        if failed_match:
            result["failures"] = int(failed_match.group(1))
            result["total"] += result["failures"]

        # Parse coverage
        coverage_match = re.search(r"TOTAL\s+\d+\s+\d+\s+(\d+)%", output)
        if coverage_match:
            result["coverage_percent"] = float(coverage_match.group(1))

        return result

    def _parse_jest_output(self, output: str) -> Dict[str, Any]:
        """Parse jest output for test results and coverage"""
        # Similar to pytest parsing
        result = {
            "executed": True,
            "passed": "failed" not in output.lower(),
            "total": 0,
            "failures": 0,
            "coverage_percent": 0.0
        }

        # Parse jest summary
        import re
        summary_match = re.search(r"Tests:\s+(\d+) passed,\s+(\d+) total", output)
        if summary_match:
            result["total"] = int(summary_match.group(2))
            result["failures"] = result["total"] - int(summary_match.group(1))

        # Parse coverage
        coverage_match = re.search(r"All files\s+\|\s+([\d.]+)", output)
        if coverage_match:
            result["coverage_percent"] = float(coverage_match.group(1))

        return result

    def _parse_go_test_output(
        self,
        test_output: str,
        coverage_output: Optional[str] = None
    ) -> Dict[str, Any]:
        """Parse go test output for results and coverage"""
        result = {
            "executed": True,
            "passed": "FAIL" not in test_output,
            "total": 0,
            "failures": 0,
            "coverage_percent": 0.0
        }

        # Count PASS/FAIL lines
        import re
        for line in test_output.split("\n"):
            if line.startswith("--- PASS:"):
                result["total"] += 1
            elif line.startswith("--- FAIL:"):
                result["total"] += 1
                result["failures"] += 1

        # Parse coverage from "total: (statements) X.X%"
        if coverage_output:
            coverage_match = re.search(r"total:\s+\(statements\)\s+([\d.]+)%", coverage_output)
            if coverage_match:
                result["coverage_percent"] = float(coverage_match.group(1))

        return result

    async def _execute_standard_workflow(
        self,
        container: Container,
        agent: AgentSwarmInstance,
        task_payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute standard workflow (non-TDD)

        For agents that don't write code (e.g., data processing, API calls)
        """
        # Execute agent's primary command
        command = task_payload.get("command", [])
        if not command:
            raise ValueError("No command specified in task_payload")

        output = await container.with_exec(command).stdout()

        return {
            "success": True,
            "output": output,
            "tdd_enforced": False
        }


class DaggerExecutionError(Exception):
    """Raised when Dagger container execution fails"""
    pass


class TDDViolationError(Exception):
    """Raised when TDD workflow is violated"""
    pass


# Singleton instance
_dagger_orchestration_service: Optional[DaggerOrchestrationService] = None


def get_dagger_orchestration_service() -> DaggerOrchestrationService:
    """Get global Dagger orchestration service instance"""
    global _dagger_orchestration_service

    if _dagger_orchestration_service is None:
        _dagger_orchestration_service = DaggerOrchestrationService()

    return _dagger_orchestration_service
```

---

## Part 4: Integration Plan

### Phase 1: Add Agent-Level Monitoring (Week 1)

**Tasks:**
1. Extend `PrometheusMetricsService` with agent metrics (20+ new metrics)
2. Create `AgentMetricsCollector` service
3. Modify `AgentSwarmLifecycleService` to record agent-level events
4. Update `/metrics` endpoint to include agent metrics
5. Add agent metrics to Grafana dashboard

**Deliverables:**
- Per-agent task performance tracking
- Per-agent resource usage (CPU, memory)
- Per-agent error rates

### Phase 2: Dagger Integration (Week 2-3)

**Tasks:**
1. Add `dagger-io` dependency to `requirements.txt`
2. Implement `DaggerOrchestrationService`
3. Add TDD workflow enforcement logic
4. Integrate with `TaskAssignmentOrchestrator`
5. Create Dagger container templates for Python/Node/Go
6. Add container metrics to Prometheus

**Deliverables:**
- Code-writing agents run in isolated containers
- TDD workflow enforced for all code tasks
- Automatic cleanup after task completion

### Phase 3: DBOS Migration (Week 4-6)

**Tasks:**
1. Fix schema inconsistencies (consolidate TaskLease models)
2. Migrate Lease Expiration Service to DBOS scheduled workflow
3. Migrate Node Crash Detection to DBOS scheduled workflow
4. Migrate Duplicate Prevention to DBOS workflow ID deduplication
5. Update monitoring to track DBOS workflow metrics

**Deliverables:**
- 75% code reduction in background services
- Improved reliability through durable workflows
- Unified monitoring across FastAPI and DBOS

---

## Part 5: TDD Enforcement Policy

### Mandatory TDD for Code-Writing Agents

**Policy:**

```
╔═══════════════════════════════════════════════════════════════╗
║ TDD ENFORCEMENT POLICY                                        ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║ ALL code-writing agents MUST:                                ║
║                                                               ║
║ 1. Run existing tests BEFORE making code changes             ║
║    → Establishes baseline (all tests must pass)              ║
║                                                               ║
║ 2. Write NEW tests BEFORE implementing new features          ║
║    → Tests define expected behavior                          ║
║                                                               ║
║ 3. Write minimal code to make tests pass                     ║
║    → Red → Green → Refactor cycle                            ║
║                                                               ║
║ 4. Run ALL tests AFTER code changes                          ║
║    → Verification (all tests must still pass)                ║
║                                                               ║
║ 5. Meet minimum coverage threshold (default: 80%)            ║
║    → Configurable per project via task_payload               ║
║                                                               ║
║ 6. Execute in isolated Dagger container                      ║
║    → Prevents conflicts with other agents                    ║
║                                                               ║
║ FAILURE CONDITIONS:                                           ║
║ • Task FAILS if no tests exist before code changes           ║
║ • Task FAILS if tests don't pass after code changes          ║
║ • Task FAILS if coverage below threshold                     ║
║ • Task FAILS if container execution errors                   ║
║                                                               ║
║ METRICS TRACKED:                                              ║
║ • agent_tests_run_total [result: passed/failed]              ║
║ • agent_test_coverage_percent                                ║
║ • agent_build_failures_total                                 ║
║ • agent_tdd_violations_total [violation_type]                ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
```

### Example Task Payload with TDD Requirements

```json
{
  "task_id": "uuid-here",
  "task_type": "code_generation",
  "language": "python",
  "workspace_path": "/path/to/project",
  "requirements": {
    "feature": "Add user authentication endpoint",
    "tests_required": true,
    "min_coverage_percent": 85,
    "enforce_tdd": true
  },
  "container_config": {
    "python_version": "3.11",
    "requirements_file": "requirements.txt",
    "test_command": "pytest",
    "resource_limits": {
      "cpu": "2.0",
      "memory": "4Gi"
    }
  }
}
```

---

## Part 6: Answers to Your Questions

### Q1: Schema Consolidation Timeline?
**Answer:** ✅ IMMEDIATE - Fixed in this session

Changed `lease_expiration_service.py` line 22:
```python
from backend.models.task_queue import TaskLease, Task, TaskStatus
```

### Q2: Tackle All Issues Together?
**Answer:** ✅ YES - Next Sprint

**Sprint Plan:**
- Week 1: Schema consolidation + Agent monitoring
- Week 2-3: Dagger integration + TDD enforcement
- Week 4-6: DBOS migration (scheduled workflows first)

### Q3: TDD Enforcement?
**Answer:** ✅ ALWAYS - Mandatory

- TDD enforced via `DaggerOrchestrationService`
- `enforce_tdd=True` parameter (default)
- Task fails if TDD workflow violated
- Metrics track violations per agent

### Q4: Current Monitoring Coverage?
**Answer:**

**SYSTEMS:** ✅ YES (comprehensive)
- Infrastructure metrics (Prometheus)
- Subsystem health (8 services)
- Event timeline (13 event types)

**AGENTS:** ❌ NO (missing)
- No per-agent performance tracking
- No per-agent resource usage
- No per-agent code quality metrics
- No container isolation metrics

**Recommendation:** Add `AgentMetricsCollector` service in Phase 1

### Q5: Dagger for Agent Isolation?
**Answer:** ✅ REQUIRED

**Why:**
- Prevents conflicts between agents
- Enforces TDD workflow
- Automatic cleanup
- Resource isolation
- Multi-language support

**Implementation:** `DaggerOrchestrationService` in Phase 2

---

## Part 7: Next Steps

**IMMEDIATE (Today):**
- ✅ Schema fix applied (lease_expiration_service.py)
- Review this document
- Approve sprint plan

**WEEK 1 (Agent Monitoring):**
1. Extend PrometheusMetricsService with 20+ agent metrics
2. Implement AgentMetricsCollector
3. Update /metrics endpoint
4. Test agent-level metrics collection

**WEEK 2-3 (Dagger Integration):**
1. Install dagger-io dependency
2. Implement DaggerOrchestrationService
3. Test TDD workflow with sample agent
4. Integrate with TaskAssignmentOrchestrator

**WEEK 4-6 (DBOS Migration):**
1. Consolidate TaskLease models
2. Migrate Lease Expiration to DBOS
3. Migrate Node Crash Detection to DBOS
4. Migrate Duplicate Prevention to DBOS

---

## Appendix: Required Dependencies

### Python Dependencies

```txt
# Add to requirements.txt

# Dagger Python SDK
dagger-io>=0.9.0

# Additional test dependencies (for agents)
pytest>=7.4.0
pytest-cov>=4.1.0
pytest-timeout>=2.1.0
coverage>=7.3.0
```

### System Requirements

```bash
# Docker (required for Dagger)
docker --version  # Docker version 20.10+

# Dagger CLI (optional, for debugging)
curl -L https://dl.dagger.io/dagger/install.sh | sh
```

### Installation

```bash
# Install Python dependencies
pip install dagger-io pytest pytest-cov

# Verify Docker is running
docker ps

# Test Dagger connection
python -c "import dagger; import asyncio; asyncio.run(dagger.Connection().close())"
```

---

**Document Status:** ✅ READY FOR REVIEW
**Next Action:** Approve sprint plan and begin Week 1 implementation
