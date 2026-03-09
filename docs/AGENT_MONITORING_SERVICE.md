# Agent Monitoring Service

**Issue #112: Migrate Agent Monitoring System from Core**

## Overview

The Agent Monitoring Service provides comprehensive monitoring capabilities for multi-agent swarms in the OpenClaw backend. Migrated from `/Users/aideveloper/core/src/backend/app/agents/swarm/monitoring.py` (789 lines).

## Features

### Core Capabilities

1. **System-wide Metrics Collection**
   - Real-time agent health tracking
   - Task execution statistics
   - Resource utilization monitoring
   - Communication metrics

2. **Per-agent Health Reports**
   - Detailed agent performance metrics
   - Success rate tracking
   - Resource usage (CPU, memory)
   - Active alerts per agent

3. **Prometheus Integration**
   - Automatic metric recording to PrometheusMetricsService
   - Agent count gauges by status
   - Alert creation/resolution counters
   - Compatible with Epic E8-S1 metrics

4. **Alert Management**
   - Threshold-based monitoring rules
   - Multiple severity levels (INFO, WARNING, ERROR, CRITICAL)
   - Alert handlers for custom actions
   - Automatic alert cleanup (24-hour retention for resolved alerts)

5. **Degraded Agent Detection**
   - Automatic detection of unhealthy agents
   - Configurable thresholds for CPU, memory, error rate
   - Proactive alerting

## Architecture

### Data Models

```python
# Enumerations
MonitoringLevel: BASIC | DETAILED | COMPREHENSIVE | DEBUG
AlertSeverity: INFO | WARNING | ERROR | CRITICAL
MetricType: PERFORMANCE | HEALTH | RESOURCE | TASK | COMMUNICATION | SYSTEM

# Core Classes
Alert: System alert with severity, message, metadata
SystemMetrics: System-wide metrics snapshot
AgentReport: Detailed per-agent report
MonitoringRule: Base class for monitoring rules
ThresholdRule: Threshold-based rule implementation
```

### Key Components

```
AgentMonitoringService
├── Lifecycle Management
│   ├── start_monitoring() - Start async monitoring loop
│   └── stop_monitoring() - Stop monitoring gracefully
├── Metrics Collection
│   ├── _collect_system_metrics() - System-wide metrics
│   └── _collect_agent_metrics() - Per-agent metrics
├── Alert Management
│   ├── add_alert_handler() - Register alert callbacks
│   ├── resolve_alert() - Mark alert as resolved
│   └── _check_monitoring_rules() - Evaluate rules
├── Reporting
│   ├── get_system_health() - Overall health score
│   ├── get_agent_report() - Per-agent detailed report
│   └── get_monitoring_dashboard() - Comprehensive dashboard
└── Rule Management
    ├── add_monitoring_rule() - Register custom rule
    └── remove_monitoring_rule() - Unregister rule
```

## Usage

### Basic Setup

```python
from backend.services.agent_monitoring_service import (
    AgentMonitoringService,
    MonitoringLevel,
    get_agent_monitoring_service,
)
from backend.services.prometheus_metrics_service import get_metrics_service

# Initialize with database session
db_session = get_db()
prometheus = get_metrics_service()

monitoring = AgentMonitoringService(
    db_session=db_session,
    prometheus_metrics=prometheus,
    monitoring_level=MonitoringLevel.DETAILED,
)

# Start monitoring
await monitoring.start_monitoring()
```

### Custom Alert Handlers

```python
def alert_handler(alert: Alert):
    if alert.severity == AlertSeverity.CRITICAL:
        # Send notification
        notify_ops_team(alert)

monitoring.add_alert_handler(alert_handler)
```

### Custom Monitoring Rules

```python
from backend.services.agent_monitoring_service import (
    ThresholdRule,
    MetricType,
    AlertSeverity,
)

rule = ThresholdRule(
    name="Custom CPU Alert",
    metric_type=MetricType.RESOURCE,
    severity=AlertSeverity.WARNING,
    threshold=0.75,
    comparison="gt",
    metric_path="cpu_usage",
)

monitoring.add_monitoring_rule(rule)
```

### Dashboard Access

```python
# Get system health
health = monitoring.get_system_health()
# Returns: {
#   'status': 'excellent',
#   'health_score': 95.0,
#   'healthy_agents': 10,
#   'total_agents': 10,
#   'active_alerts': 0,
#   'error_rate': 0.01
# }

# Get agent report
report = monitoring.get_agent_report("agent_001")
# Returns: AgentReport with detailed metrics

# Get full dashboard
dashboard = monitoring.get_monitoring_dashboard()
# Returns: {
#   'system_health': {...},
#   'system_metrics': {...},
#   'active_alerts': [...],
#   'monitoring_status': {...},
#   'historical_data': {...}
# }
```

## Default Monitoring Rules

The service comes with 5 pre-configured rules:

1. **High Error Rate** (ERROR) - Triggers when error_rate > 10%
2. **High Response Time** (WARNING) - Triggers when avg_response_time > 30s
3. **High CPU Usage** (WARNING) - Triggers when cpu_usage > 80%
4. **High Memory Usage** (WARNING) - Triggers when memory_usage > 80%
5. **Large Queue Length** (WARNING) - Triggers when queue_length > 20

## Prometheus Metrics Integration

The service automatically records metrics to PrometheusMetricsService:

- `record_agent_count(status, count)` - Agent counts by status
- `record_alert_created(severity, metric_type)` - Alert creation events
- `record_alert_resolved(severity)` - Alert resolution events

## Configuration

### Monitoring Interval

Default: 30 seconds

```python
monitoring.monitoring_interval = 60  # Change to 60 seconds
```

### History Limits

- System metrics: 1000 entries (bounded deque)
- Agent metrics: 500 entries per agent
- Alert history: 1000 entries

### Alert Cleanup

Resolved alerts are automatically removed after 24 hours.

## Testing

Comprehensive test suite with 54 tests:

```bash
python3 -m pytest tests/services/test_agent_monitoring_service.py -v
```

**Coverage: 82%** (exceeds 80% requirement)

Test categories:
- Enumeration types
- Data model serialization
- Threshold rule logic
- Service lifecycle
- Metrics collection
- Alert management
- Monitoring rules
- System health calculation
- Agent reporting
- Prometheus integration
- Degraded agent detection
- Error handling

## Integration Points

### Database Models

- `AgentSwarmInstance` - Agent lifecycle state
- `AgentSwarmStatus` - Agent status enumeration

### Services

- `PrometheusMetricsService` - Metrics recording
- `get_db()` - Database session dependency

### Dependencies

```python
sqlalchemy.orm.Session  # Database access
asyncio                 # Async monitoring loop
collections.deque       # Bounded history
statistics              # Metric aggregation
```

## Performance Characteristics

- **Async monitoring loop** - Non-blocking background task
- **Bounded memory** - Fixed-size deque collections
- **Graceful degradation** - Continues on database errors
- **Thread-safe** - Safe for concurrent access
- **Low overhead** - 30s default interval

## Future Enhancements

Potential improvements identified during migration:

1. Persistent metric storage (currently in-memory)
2. Custom metric aggregation functions
3. Webhook notifications for alerts
4. SLA tracking and reporting
5. Predictive health scoring
6. Multi-tenant monitoring support
7. Export to external monitoring systems

## Files

- **Implementation**: `/Users/aideveloper/openclaw-backend/backend/services/agent_monitoring_service.py` (800 lines)
- **Tests**: `/Users/aideveloper/openclaw-backend/tests/services/test_agent_monitoring_service.py` (1407 lines)
- **Documentation**: `/Users/aideveloper/openclaw-backend/docs/AGENT_MONITORING_SERVICE.md`

## References

- **Source**: `/Users/aideveloper/core/src/backend/app/agents/swarm/monitoring.py`
- **Issue**: #112 - Migrate Agent Monitoring System from Core
- **Epic**: Agent Swarm Lifecycle Management
- **Related**: Epic E8 (Monitoring & Observability)
