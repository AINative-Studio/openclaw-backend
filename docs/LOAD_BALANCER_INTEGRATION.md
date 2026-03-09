# Agent Load Balancer Integration Guide

**Issue #113: Migrate Load Balancer from Core**

This document describes the SwarmLoadBalancer service and its integration with the OpenClaw backend.

## Overview

The SwarmLoadBalancer provides intelligent task assignment and load balancing for multi-agent swarms. It was migrated from `/Users/aideveloper/core/src/backend/app/agents/swarm/load_balancer.py` and enhanced for the OpenClaw architecture.

## Architecture

### Core Components

1. **AgentMetrics**: Tracks per-agent performance and health
   - Performance metrics (response time, completion time, success/failure rates)
   - Resource utilization (CPU, memory, queue length)
   - Health status (healthy, degraded, overloaded, unhealthy, offline)
   - Historical data (last 100 response/completion times)

2. **SwarmLoadBalancer**: Main service orchestrating task assignment
   - Multiple load balancing strategies
   - Agent health monitoring and filtering
   - Capability matching
   - Performance tracking and adaptive optimization

3. **LoadBalancingStrategy**: Enum of available strategies
   - `ROUND_ROBIN`: Even distribution across agents
   - `LEAST_CONNECTIONS`: Prefer agents with fewer current tasks
   - `LEAST_RESPONSE_TIME`: Prefer fastest agents
   - `WEIGHTED_ROUND_ROBIN`: Weight by agent performance scores
   - `CAPABILITY_BASED`: Match task requirements to agent capabilities
   - `PERFORMANCE_BASED`: Select highest performing agents
   - `ADAPTIVE`: Weighted combination of multiple strategies (default)

4. **AgentHealthStatus**: Health classification
   - `HEALTHY`: Normal operation
   - `DEGRADED`: Reduced performance
   - `OVERLOADED`: Exceeding capacity limits
   - `UNHEALTHY`: Critical issues
   - `OFFLINE`: Not responding

## Integration with TaskAssignmentOrchestrator

The SwarmLoadBalancer is integrated into the TaskAssignmentOrchestrator to provide intelligent agent selection:

### Before (Simple First-Match):
```python
matched_node = self._match_node_to_task(requirements, available_nodes)
```

### After (Intelligent Load Balancing):
```python
await self.load_balancer.initialize_agent_metrics(available_nodes)
assignment_result = await self.load_balancer.assign_task(task, available_nodes)
peer_id = assignment_result.peer_id  # Best agent selected
```

### Benefits:
- **Health filtering**: Excludes degraded/overloaded/unhealthy agents
- **Performance tracking**: Learns from historical task completions
- **Capability matching**: Ensures agents have required capabilities
- **Adaptive optimization**: Combines multiple strategies for best results
- **Load distribution**: Prevents overloading individual agents

## Usage Examples

### Basic Usage (Default Adaptive Strategy)

```python
from backend.services.agent_load_balancer_service import SwarmLoadBalancer
from sqlalchemy.orm import Session

# Initialize
balancer = SwarmLoadBalancer(db_session=session)

# Initialize agent metrics
await balancer.initialize_agent_metrics(available_nodes)

# Assign task
result = await balancer.assign_task(task, available_nodes)
if result:
    print(f"Assigned to {result.peer_id} with score {result.performance_score}")
```

### Custom Strategy

```python
from backend.services.agent_load_balancer_service import (
    SwarmLoadBalancer,
    LoadBalancingStrategy
)

# Use capability-based strategy
balancer = SwarmLoadBalancer(
    db_session=session,
    strategy=LoadBalancingStrategy.CAPABILITY_BASED
)
```

### With TaskAssignmentOrchestrator

```python
from backend.services.task_assignment_orchestrator import TaskAssignmentOrchestrator
from backend.services.agent_load_balancer_service import LoadBalancingStrategy

# Create orchestrator with load balancing
orchestrator = TaskAssignmentOrchestrator(
    db_session=session,
    libp2p_client=client,
    dbos_service=service,
    load_balancing_strategy=LoadBalancingStrategy.PERFORMANCE_BASED
)

# Assign task (uses load balancer internally)
result = await orchestrator.assign_task(
    task_id="task-123",
    available_nodes=nodes
)
```

### Update Agent Metrics

```python
# Update metrics after receiving heartbeat
await balancer.update_agent_metrics(
    "node1",
    current_tasks=3,
    cpu_usage=0.4,
    memory_usage=0.5,
    last_heartbeat=datetime.now(timezone.utc)
)
```

### Handle Task Completion

```python
# Notify balancer when task completes
await balancer.task_completed(
    task_id="task-123",
    success=True,
    completion_time=15.5  # seconds
)
```

### Rebalance Load

```python
# Manually trigger load rebalancing
await balancer.rebalance_tasks()
```

### Get Statistics

```python
# Load balancer statistics
stats = balancer.get_load_balancer_stats()
print(f"Total tasks assigned: {stats['total_tasks_assigned']}")
print(f"Healthy agents: {stats['healthy_agents']}")
print(f"Strategy: {stats['current_strategy']}")

# Per-agent metrics
metrics = balancer.get_agent_metrics_summary()
for agent_id, agent_stats in metrics.items():
    print(f"{agent_id}: {agent_stats['health_status']}, score={agent_stats['performance_score']}")
```

## Capability Matching

The load balancer supports three types of capability requirements:

### Boolean Requirements
```python
task.required_capabilities = {"gpu_available": True}
# Node must have gpu_available=True
```

### Numeric Requirements (Greater-Than-Equal)
```python
task.required_capabilities = {
    "cpu_cores": 4,
    "memory_mb": 8192
}
# Node must have cpu_cores >= 4 AND memory_mb >= 8192
```

### List Requirements (Subset Matching)
```python
task.required_capabilities = {
    "models": ["llama-2-7b", "claude-3-5-sonnet-20241022"]
}
# Node must support both models
```

## Performance Scoring

Agents are scored on a 0-100 scale based on:

- **Error Rate** (max -50 points): High failure rates heavily penalized
- **Response Time** (max -20 points): Slow response times penalized
- **Queue Length** (max -20 points): High queue depth penalized
- **Resource Utilization** (max -10 points): CPU/memory usage penalized

Example calculation:
```
Base Score: 100
- Error rate penalty: 10% error rate → -5 points
- Response time penalty: 5 second avg → -5 points
- Queue length penalty: 2 tasks → -4 points
- Resource penalty: 50% max(cpu, memory) → -5 points
---------------------------------------------------
Final Score: 81/100
```

## Health Status Determination

### Healthy
- Recent heartbeat (< 5 minutes)
- Low error rate (< 10%)
- Not overloaded

### Overloaded
Any of:
- More than 10 current tasks
- Queue length > 20
- CPU usage > 80%
- Memory usage > 80%
- Average response time > 30s

### Degraded
- Not healthy but not overloaded
- May have moderate error rates or resource usage

### Unhealthy
- High error rate (>= 10%)
- Or overloaded conditions persist

### Offline
- No heartbeat in > 5 minutes

## Adaptive Strategy Weights

The default ADAPTIVE strategy combines multiple approaches with these weights:

- **LEAST_CONNECTIONS**: 25%
- **LEAST_RESPONSE_TIME**: 25%
- **CAPABILITY_BASED**: 30%
- **PERFORMANCE_BASED**: 20%

Each strategy votes for an agent, and votes are weighted. The agent with the highest weighted vote is selected.

## Testing

Comprehensive test suite with 31 tests covering:

- Agent metrics initialization and updates
- Performance score calculation
- Health status determination
- All load balancing strategies
- Capability matching (boolean, numeric, list)
- Task assignment and completion
- Load rebalancing
- Statistics collection

**Test Coverage**: 82% (exceeds 80% requirement)

Run tests:
```bash
pytest tests/services/test_agent_load_balancer_service.py -v --cov
```

## Migration Notes

### Changes from Original Implementation

1. **Database Integration**: Uses SQLAlchemy Session instead of in-memory SwarmAgent objects
2. **Model Compatibility**: Works with OpenClaw's Task and NodeCapability models
3. **Async/Await**: Fully async for integration with FastAPI endpoints
4. **Simplified Dependencies**: Removed SwarmAgent/SwarmTask/SwarmMessage dependencies
5. **Enhanced Logging**: Better structured logging for production debugging

### Removed Features

- `SwarmAgent` references (replaced with node dictionaries)
- `SwarmTask` type (uses `Task` model)
- `TaskType` enum (uses task_type string field)
- Direct swarm integration (decoupled for flexibility)

### Added Features

- Integration with TaskAssignmentOrchestrator
- Support for OpenClaw NodeCapability model
- Configurable strategy injection
- Enhanced metrics tracking

## Performance Considerations

### Memory Usage

- Agent metrics: ~1KB per agent
- Assignment history: Bounded deque (max 1000 entries)
- Response/completion times: Last 100 per agent

### Computational Complexity

- Round-robin: O(1)
- Least connections/response time: O(n) where n = available agents
- Capability matching: O(n * m) where m = requirements
- Adaptive: O(n * s) where s = number of strategies (4)

For typical deployments (< 100 agents), all strategies complete in < 1ms.

## Future Enhancements

1. **Predictive Load Balancing**: Use ML to predict task duration and agent performance
2. **Geographic Awareness**: Prefer agents in same region for latency reduction
3. **Cost Optimization**: Factor in node costs for economic optimization
4. **Auto-Scaling**: Trigger node provisioning when all agents overloaded
5. **Real-Time Monitoring**: WebSocket updates for live load balancer dashboard

## References

- Issue #113: Migrate Load Balancer from Core
- Original implementation: `/Users/aideveloper/core/src/backend/app/agents/swarm/load_balancer.py`
- Test file: `tests/services/test_agent_load_balancer_service.py`
- Integration file: `backend/services/task_assignment_orchestrator.py`
