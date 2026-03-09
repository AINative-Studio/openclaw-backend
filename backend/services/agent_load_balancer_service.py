"""
Agent Load Balancer Service (Issue #113)

Migrated from /Users/aideveloper/core/src/backend/app/agents/swarm/load_balancer.py

Provides intelligent load balancing and task assignment for multi-agent swarms:
- Multiple load balancing strategies (round-robin, least-connections, capability-based, etc.)
- Agent health monitoring and filtering
- Capability matching for task-to-agent assignment
- Performance tracking and adaptive optimization
- Load rebalancing

Key Features:
- Select best agent by load/health/capabilities
- Capability matching with boolean/numeric/list requirements
- Health status filtering (exclude degraded/overloaded nodes)
- Round-robin for equal load distribution
- Adaptive strategy combining multiple approaches

Architecture:
- AgentMetrics: Tracks per-agent performance and health
- SwarmLoadBalancer: Main service orchestrating task assignment
- LoadBalancingStrategy: Enum of available strategies
- AgentHealthStatus: Health classification

Integration Points:
- TaskAssignmentOrchestrator: Uses load balancer for node selection
- NodeCapability: Sources capability data from database
- Task: Extracts requirements from task payload
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from enum import Enum
import statistics
from collections import defaultdict, deque
from sqlalchemy.orm import Session

from backend.models.task_lease import Task, TaskPriority
from backend.models.node_capability import NodeCapability

logger = logging.getLogger(__name__)


class LoadBalancingStrategy(Enum):
    """Load balancing strategies"""
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    LEAST_RESPONSE_TIME = "least_response_time"
    WEIGHTED_ROUND_ROBIN = "weighted_round_robin"
    CAPABILITY_BASED = "capability_based"
    PERFORMANCE_BASED = "performance_based"
    ADAPTIVE = "adaptive"


class AgentHealthStatus(Enum):
    """Agent health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OVERLOADED = "overloaded"
    UNHEALTHY = "unhealthy"
    OFFLINE = "offline"


@dataclass
class AgentMetrics:
    """
    Agent performance and health metrics

    Tracks performance, resource utilization, and health indicators
    for intelligent task assignment decisions.
    """
    agent_id: str

    # Performance metrics
    current_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    average_response_time: float = 0.0
    average_completion_time: float = 0.0

    # Resource utilization
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    queue_length: int = 0

    # Health indicators
    health_status: AgentHealthStatus = AgentHealthStatus.HEALTHY
    last_heartbeat: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    error_rate: float = 0.0

    # Capability metrics
    specialization_match_rate: float = 0.0
    capability_utilization: Dict[str, float] = field(default_factory=dict)

    # Historical data
    response_times: deque = field(default_factory=lambda: deque(maxlen=100))
    completion_times: deque = field(default_factory=lambda: deque(maxlen=100))

    def update_performance(self, response_time: float, completion_time: float, success: bool):
        """Update performance metrics after task completion"""
        self.response_times.append(response_time)
        self.completion_times.append(completion_time)

        if success:
            self.completed_tasks += 1
        else:
            self.failed_tasks += 1

        # Recalculate averages
        if self.response_times:
            self.average_response_time = statistics.mean(self.response_times)
        if self.completion_times:
            self.average_completion_time = statistics.mean(self.completion_times)

        # Update error rate
        total_tasks = self.completed_tasks + self.failed_tasks
        if total_tasks > 0:
            self.error_rate = self.failed_tasks / total_tasks

    def get_performance_score(self) -> float:
        """
        Calculate overall performance score (0-100)

        Scoring factors:
        - Error rate (max -50 points)
        - Response time (max -20 points)
        - Queue length (max -20 points)
        - Resource utilization (max -10 points)
        """
        base_score = 100.0

        # Penalize high error rates
        base_score -= (self.error_rate * 50)

        # Penalize slow response times (normalized to 0-20 penalty)
        if self.average_response_time > 0:
            response_penalty = min(self.average_response_time / 10, 20)
            base_score -= response_penalty

        # Penalize high queue length
        queue_penalty = min(self.queue_length * 2, 20)
        base_score -= queue_penalty

        # Penalize resource utilization
        resource_penalty = max(self.cpu_usage, self.memory_usage) * 10
        base_score -= resource_penalty

        return max(base_score, 0.0)

    def is_overloaded(self) -> bool:
        """
        Check if agent is overloaded

        Overload conditions:
        - More than 10 current tasks
        - Queue length > 20
        - CPU usage > 80%
        - Memory usage > 80%
        - Average response time > 30s
        """
        return (
            self.current_tasks > 10 or
            self.queue_length > 20 or
            self.cpu_usage > 0.8 or
            self.memory_usage > 0.8 or
            self.average_response_time > 30.0
        )

    def is_healthy(self) -> bool:
        """
        Check if agent is healthy

        Healthy conditions:
        - Recent heartbeat (< 5 minutes)
        - Low error rate (< 10%)
        - Not overloaded
        """
        time_since_heartbeat = datetime.now(timezone.utc) - self.last_heartbeat
        return (
            time_since_heartbeat < timedelta(minutes=5) and
            self.error_rate < 0.1 and
            not self.is_overloaded()
        )


@dataclass
class TaskAssignmentResult:
    """Result of task assignment operation"""
    peer_id: str
    capability_match_score: float
    performance_score: float
    assigned_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class TaskAssignment:
    """Task assignment record"""
    task_id: str
    agent_id: str
    assigned_at: datetime
    expected_completion: datetime
    priority: TaskPriority
    capability_match_score: float
    performance_score: float

    def is_overdue(self) -> bool:
        """Check if task is overdue"""
        return datetime.now(timezone.utc) > self.expected_completion


class SwarmLoadBalancer:
    """
    Intelligent Load Balancer for Multi-Agent Swarms

    Provides advanced task assignment and load balancing capabilities
    with performance monitoring and adaptive optimization.

    Usage:
        balancer = SwarmLoadBalancer(db_session=session)
        await balancer.initialize_agent_metrics(available_nodes)
        result = await balancer.assign_task(task, available_nodes)

    Strategies:
        - ROUND_ROBIN: Even distribution
        - LEAST_CONNECTIONS: Prefer agents with fewer tasks
        - LEAST_RESPONSE_TIME: Prefer fastest agents
        - CAPABILITY_BASED: Match task requirements to capabilities
        - PERFORMANCE_BASED: Select highest performing agents
        - ADAPTIVE: Weighted combination of multiple strategies
    """

    def __init__(
        self,
        db_session: Session,
        strategy: LoadBalancingStrategy = LoadBalancingStrategy.ADAPTIVE
    ):
        """
        Initialize SwarmLoadBalancer

        Args:
            db_session: SQLAlchemy database session
            strategy: Load balancing strategy (default: ADAPTIVE)
        """
        self.db_session = db_session
        self.strategy = strategy

        # Agent monitoring
        self.agent_metrics: Dict[str, AgentMetrics] = {}
        self.agent_weights: Dict[str, float] = {}

        # Task tracking
        self.task_assignments: Dict[str, TaskAssignment] = {}

        # Load balancing state
        self.round_robin_index = 0
        self.assignment_history: deque = deque(maxlen=1000)

        # Performance tracking
        self.total_tasks_assigned = 0
        self.total_tasks_completed = 0
        self.average_assignment_time = 0.0

        # Adaptive strategy parameters
        self.strategy_weights = {
            LoadBalancingStrategy.LEAST_CONNECTIONS: 0.25,
            LoadBalancingStrategy.LEAST_RESPONSE_TIME: 0.25,
            LoadBalancingStrategy.CAPABILITY_BASED: 0.3,
            LoadBalancingStrategy.PERFORMANCE_BASED: 0.2
        }

        logger.info(f"Initialized SwarmLoadBalancer with strategy: {strategy.value}")

    async def initialize_agent_metrics(self, available_nodes: List[Dict[str, Any]]):
        """
        Initialize metrics for all agents

        Args:
            available_nodes: List of node dictionaries with peer_id and capabilities
        """
        for node in available_nodes:
            agent_id = node.get("peer_id")
            if agent_id and agent_id not in self.agent_metrics:
                self.agent_metrics[agent_id] = AgentMetrics(agent_id=agent_id)
                self.agent_weights[agent_id] = 1.0

        logger.info(f"Initialized metrics for {len(self.agent_metrics)} agents")

    async def assign_task(
        self,
        task: Task,
        available_nodes: List[Dict[str, Any]]
    ) -> Optional[TaskAssignmentResult]:
        """
        Assign a task to the best available agent

        Args:
            task: Task to assign
            available_nodes: List of available nodes with capabilities

        Returns:
            TaskAssignmentResult if successful, None otherwise
        """
        start_time = datetime.now(timezone.utc)

        # Get available agents
        available_agents = await self._get_available_agents(task, available_nodes)

        if not available_agents:
            logger.warning(f"No available agents for task {task.id}")
            return None

        # Select best agent based on strategy
        selected_agent = await self._select_agent(task, available_agents, available_nodes)

        if not selected_agent:
            logger.warning(f"Failed to select agent for task {task.id}")
            return None

        # Calculate scores
        capability_match_score = self._calculate_capability_match(task, self._get_node_by_id(selected_agent, available_nodes))
        performance_score = self.agent_metrics[selected_agent].get_performance_score()

        # Create assignment record
        assignment = TaskAssignment(
            task_id=str(task.id),
            agent_id=selected_agent,
            assigned_at=datetime.now(timezone.utc),
            expected_completion=datetime.now(timezone.utc) + timedelta(minutes=10),  # Default 10 min
            priority=task.priority,
            capability_match_score=capability_match_score,
            performance_score=performance_score
        )

        # Update tracking
        self.task_assignments[str(task.id)] = assignment
        self.agent_metrics[selected_agent].current_tasks += 1
        self.total_tasks_assigned += 1

        # Update assignment time
        assignment_time = (datetime.now(timezone.utc) - start_time).total_seconds()
        self.average_assignment_time = (
            (self.average_assignment_time * (self.total_tasks_assigned - 1) + assignment_time) /
            self.total_tasks_assigned
        )

        # Record assignment history
        self.assignment_history.append({
            'task_id': str(task.id),
            'agent_id': selected_agent,
            'timestamp': datetime.now(timezone.utc),
            'strategy': self.strategy.value,
            'assignment_time': assignment_time
        })

        logger.info(f"Assigned task {task.id} to agent {selected_agent} (strategy: {self.strategy.value})")

        return TaskAssignmentResult(
            peer_id=selected_agent,
            capability_match_score=capability_match_score,
            performance_score=performance_score
        )

    async def _get_available_agents(
        self,
        task: Task,
        available_nodes: List[Dict[str, Any]]
    ) -> List[str]:
        """
        Get list of available agents for the task

        Filters based on:
        - Health status (must be healthy)
        - Capability match (must have required capabilities)
        - Load limits (must not be overloaded)

        Args:
            task: Task requiring assignment
            available_nodes: List of available nodes

        Returns:
            List of agent IDs that can handle the task
        """
        available_agents = []

        for node in available_nodes:
            agent_id = node.get("peer_id")
            if not agent_id:
                continue

            metrics = self.agent_metrics.get(agent_id)
            if not metrics:
                # Initialize metrics if not present
                await self.initialize_agent_metrics([node])
                metrics = self.agent_metrics.get(agent_id)
                if not metrics:
                    continue

            # Check basic availability
            if not metrics.is_healthy():
                continue

            # Check capability match
            if not self._has_required_capabilities(task, node):
                continue

            # Check load limits
            if metrics.is_overloaded():
                continue

            available_agents.append(agent_id)

        return available_agents

    async def _select_agent(
        self,
        task: Task,
        available_agents: List[str],
        available_nodes: List[Dict[str, Any]]
    ) -> Optional[str]:
        """
        Select the best agent from available agents

        Args:
            task: Task to assign
            available_agents: List of agent IDs
            available_nodes: List of node dictionaries

        Returns:
            Selected agent ID or None
        """
        if not available_agents:
            return None

        if len(available_agents) == 1:
            return available_agents[0]

        # Apply load balancing strategy
        if self.strategy == LoadBalancingStrategy.ROUND_ROBIN:
            return self._round_robin_selection(available_agents)

        elif self.strategy == LoadBalancingStrategy.LEAST_CONNECTIONS:
            return self._least_connections_selection(available_agents)

        elif self.strategy == LoadBalancingStrategy.LEAST_RESPONSE_TIME:
            return self._least_response_time_selection(available_agents)

        elif self.strategy == LoadBalancingStrategy.WEIGHTED_ROUND_ROBIN:
            return self._weighted_round_robin_selection(available_agents)

        elif self.strategy == LoadBalancingStrategy.CAPABILITY_BASED:
            return self._capability_based_selection(task, available_agents, available_nodes)

        elif self.strategy == LoadBalancingStrategy.PERFORMANCE_BASED:
            return self._performance_based_selection(available_agents)

        elif self.strategy == LoadBalancingStrategy.ADAPTIVE:
            return await self._adaptive_selection(task, available_agents, available_nodes)

        else:
            # Fallback to round robin
            return self._round_robin_selection(available_agents)

    def _round_robin_selection(self, available_agents: List[str]) -> str:
        """Round robin selection"""
        selected = available_agents[self.round_robin_index % len(available_agents)]
        self.round_robin_index += 1
        return selected

    def _least_connections_selection(self, available_agents: List[str]) -> str:
        """Select agent with least current connections"""
        return min(available_agents, key=lambda agent_id: self.agent_metrics[agent_id].current_tasks)

    def _least_response_time_selection(self, available_agents: List[str]) -> str:
        """Select agent with least average response time"""
        return min(available_agents, key=lambda agent_id: self.agent_metrics[agent_id].average_response_time)

    def _weighted_round_robin_selection(self, available_agents: List[str]) -> str:
        """Weighted round robin based on agent weights"""
        # Build weighted list
        weighted_agents = []
        for agent_id in available_agents:
            weight = int(self.agent_weights.get(agent_id, 1.0) * 10)
            weighted_agents.extend([agent_id] * weight)

        if not weighted_agents:
            return available_agents[0]

        selected = weighted_agents[self.round_robin_index % len(weighted_agents)]
        self.round_robin_index += 1
        return selected

    def _capability_based_selection(
        self,
        task: Task,
        available_agents: List[str],
        available_nodes: List[Dict[str, Any]]
    ) -> str:
        """Select agent based on capability match"""
        scores = []
        for agent_id in available_agents:
            node = self._get_node_by_id(agent_id, available_nodes)
            if node:
                score = self._calculate_capability_match(task, node)
                scores.append((score, agent_id))

        # Sort by score descending
        scores.sort(reverse=True)
        return scores[0][1] if scores else available_agents[0]

    def _performance_based_selection(self, available_agents: List[str]) -> str:
        """Select agent based on performance score"""
        return max(available_agents, key=lambda agent_id: self.agent_metrics[agent_id].get_performance_score())

    async def _adaptive_selection(
        self,
        task: Task,
        available_agents: List[str],
        available_nodes: List[Dict[str, Any]]
    ) -> str:
        """
        Adaptive selection using multiple strategies

        Combines results from multiple strategies with weighted voting.
        """
        # Calculate scores for each strategy
        strategy_scores = {}

        # Least connections
        lc_agent = self._least_connections_selection(available_agents)
        strategy_scores[LoadBalancingStrategy.LEAST_CONNECTIONS] = lc_agent

        # Least response time
        lrt_agent = self._least_response_time_selection(available_agents)
        strategy_scores[LoadBalancingStrategy.LEAST_RESPONSE_TIME] = lrt_agent

        # Capability based
        cb_agent = self._capability_based_selection(task, available_agents, available_nodes)
        strategy_scores[LoadBalancingStrategy.CAPABILITY_BASED] = cb_agent

        # Performance based
        pb_agent = self._performance_based_selection(available_agents)
        strategy_scores[LoadBalancingStrategy.PERFORMANCE_BASED] = pb_agent

        # Weight the selections
        agent_votes = defaultdict(float)
        for strategy, agent_id in strategy_scores.items():
            weight = self.strategy_weights.get(strategy, 0.25)
            agent_votes[agent_id] += weight

        # Return agent with highest weighted vote
        return max(agent_votes.items(), key=lambda x: x[1])[0]

    def _calculate_capability_match(self, task: Task, node: Dict[str, Any]) -> float:
        """
        Calculate how well node capabilities match task requirements

        Args:
            task: Task with requirements
            node: Node with capabilities

        Returns:
            Match score (0.0 to 1.0)
        """
        required_capabilities = task.required_capabilities or {}
        if not required_capabilities:
            return 1.0  # Perfect match if no requirements

        node_capabilities = node.get("capabilities", {})
        if not node_capabilities:
            return 0.0

        # Check each requirement
        matched = 0
        total = len(required_capabilities)

        for key, required_value in required_capabilities.items():
            if key in node_capabilities:
                actual_value = node_capabilities[key]

                # Check if requirement is satisfied
                if isinstance(required_value, bool):
                    if actual_value == required_value:
                        matched += 1
                elif isinstance(required_value, (int, float)):
                    if actual_value >= required_value:
                        matched += 1
                elif isinstance(required_value, list):
                    if isinstance(actual_value, list) and all(item in actual_value for item in required_value):
                        matched += 1
                elif actual_value == required_value:
                    matched += 1

        return matched / total if total > 0 else 0.0

    def _has_required_capabilities(self, task: Task, node: Dict[str, Any]) -> bool:
        """
        Check if node has all required capabilities for task

        Args:
            task: Task with requirements
            node: Node with capabilities

        Returns:
            True if node has all required capabilities
        """
        required_capabilities = task.required_capabilities or {}
        if not required_capabilities:
            return True  # No requirements

        node_capabilities = node.get("capabilities", {})
        if not node_capabilities:
            return False

        # Check each requirement
        for key, required_value in required_capabilities.items():
            if key not in node_capabilities:
                return False

            actual_value = node_capabilities[key]

            # Validate based on type
            if not self._requirement_satisfied(required_value, actual_value):
                return False

        return True

    def _requirement_satisfied(self, required_value: Any, actual_value: Any) -> bool:
        """Check if a single requirement is satisfied"""
        if isinstance(required_value, bool):
            return actual_value == required_value
        elif isinstance(required_value, (int, float)):
            return actual_value >= required_value
        elif isinstance(required_value, list):
            return isinstance(actual_value, list) and all(item in actual_value for item in required_value)
        else:
            return actual_value == required_value

    def _node_matches_requirements(self, node: Dict[str, Any], requirements: Dict[str, Any]) -> bool:
        """
        Check if node capabilities match requirements

        Args:
            node: Node dictionary with capabilities
            requirements: Required capabilities

        Returns:
            True if node matches all requirements
        """
        capabilities = node.get("capabilities", {})

        for key, required_value in requirements.items():
            if key not in capabilities:
                return False

            actual_value = capabilities[key]

            if not self._requirement_satisfied(required_value, actual_value):
                return False

        return True

    def _get_node_by_id(self, peer_id: str, available_nodes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Get node dictionary by peer_id"""
        for node in available_nodes:
            if node.get("peer_id") == peer_id:
                return node
        return None

    async def update_agent_metrics(self, agent_id: str, **kwargs):
        """
        Update agent metrics

        Args:
            agent_id: Agent identifier
            **kwargs: Metrics to update (current_tasks, cpu_usage, etc.)
        """
        if agent_id not in self.agent_metrics:
            self.agent_metrics[agent_id] = AgentMetrics(agent_id=agent_id)

        metrics = self.agent_metrics[agent_id]

        # Update provided metrics
        for key, value in kwargs.items():
            if hasattr(metrics, key):
                setattr(metrics, key, value)

        # Update health status
        if metrics.is_healthy():
            metrics.health_status = AgentHealthStatus.HEALTHY
        elif metrics.is_overloaded():
            metrics.health_status = AgentHealthStatus.OVERLOADED
        else:
            metrics.health_status = AgentHealthStatus.DEGRADED

        # Update agent weights based on performance
        performance_score = metrics.get_performance_score()
        self.agent_weights[agent_id] = max(performance_score / 100.0, 0.1)

    async def task_completed(self, task_id: str, success: bool, completion_time: float):
        """
        Handle task completion

        Args:
            task_id: Task identifier
            success: Whether task succeeded
            completion_time: Time to complete task in seconds
        """
        assignment = self.task_assignments.get(task_id)
        if not assignment:
            return

        # Update agent metrics
        response_time = (datetime.now(timezone.utc) - assignment.assigned_at).total_seconds()
        metrics = self.agent_metrics[assignment.agent_id]
        metrics.update_performance(response_time, completion_time, success)
        metrics.current_tasks = max(0, metrics.current_tasks - 1)

        # Update global stats
        if success:
            self.total_tasks_completed += 1

        # Remove assignment
        del self.task_assignments[task_id]

        logger.info(f"Task {task_id} completed by agent {assignment.agent_id} (success: {success})")

    async def rebalance_tasks(self):
        """
        Rebalance tasks across agents

        Identifies overloaded agents and attempts to reassign tasks
        to underutilized agents.
        """
        # Find overloaded agents
        overloaded_agents = [
            agent_id for agent_id, metrics in self.agent_metrics.items()
            if metrics.is_overloaded()
        ]

        if not overloaded_agents:
            return

        # Find underutilized agents
        underutilized_agents = [
            agent_id for agent_id, metrics in self.agent_metrics.items()
            if metrics.current_tasks < 3 and metrics.is_healthy()
        ]

        if not underutilized_agents:
            return

        # Attempt to redistribute tasks
        for overloaded_agent in overloaded_agents:
            # Find tasks that can be reassigned
            reassignable_tasks = [
                assignment for assignment in self.task_assignments.values()
                if assignment.agent_id == overloaded_agent and not assignment.is_overdue()
            ]

            # Sort by priority (lowest first for reassignment)
            reassignable_tasks.sort(key=lambda x: x.priority.value)

            for assignment in reassignable_tasks[:2]:  # Limit reassignments
                # Find best target agent
                target_agent = min(underutilized_agents,
                                 key=lambda agent_id: self.agent_metrics[agent_id].current_tasks)

                # Update assignment
                assignment.agent_id = target_agent
                assignment.assigned_at = datetime.now(timezone.utc)

                # Update metrics
                self.agent_metrics[overloaded_agent].current_tasks -= 1
                self.agent_metrics[target_agent].current_tasks += 1

                logger.info(f"Reassigned task {assignment.task_id} from {overloaded_agent} to {target_agent}")

    def get_load_balancer_stats(self) -> Dict[str, Any]:
        """
        Get load balancer statistics

        Returns:
            Dictionary with comprehensive stats
        """
        return {
            'total_tasks_assigned': self.total_tasks_assigned,
            'total_tasks_completed': self.total_tasks_completed,
            'average_assignment_time': self.average_assignment_time,
            'current_strategy': self.strategy.value,
            'active_assignments': len(self.task_assignments),
            'agent_count': len(self.agent_metrics),
            'healthy_agents': len([m for m in self.agent_metrics.values() if m.is_healthy()]),
            'overloaded_agents': len([m for m in self.agent_metrics.values() if m.is_overloaded()]),
            'strategy_weights': {k.value: v for k, v in self.strategy_weights.items()}
        }

    def get_agent_metrics_summary(self) -> Dict[str, Dict[str, Any]]:
        """
        Get summary of all agent metrics

        Returns:
            Dictionary mapping agent_id to metrics summary
        """
        summary = {}
        for agent_id, metrics in self.agent_metrics.items():
            summary[agent_id] = {
                'current_tasks': metrics.current_tasks,
                'completed_tasks': metrics.completed_tasks,
                'failed_tasks': metrics.failed_tasks,
                'average_response_time': metrics.average_response_time,
                'average_completion_time': metrics.average_completion_time,
                'health_status': metrics.health_status.value,
                'performance_score': metrics.get_performance_score(),
                'error_rate': metrics.error_rate,
                'last_heartbeat': metrics.last_heartbeat.isoformat()
            }
        return summary
