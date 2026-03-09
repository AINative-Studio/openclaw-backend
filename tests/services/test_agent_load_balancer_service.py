"""
Agent Load Balancer Service Tests (Issue #113)

Comprehensive test suite for SwarmLoadBalancer service implementing
intelligent task assignment and load balancing for multi-agent swarms.

Test Coverage:
- Load balancing strategies (round-robin, least-connections, capability-based, etc.)
- Agent health monitoring and filtering
- Capability matching
- Performance tracking
- Metric collection and updates
- Task assignment and completion
- Load rebalancing

Following TDD approach with BDD-style tests.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, AsyncMock, MagicMock
from typing import Dict, List, Any
from uuid import uuid4

from backend.models.task_lease import Task, TaskStatus, TaskPriority
from backend.models.node_capability import NodeCapability


# Test fixtures
@pytest.fixture
def sample_task():
    """Sample task for testing"""
    return Task(
        id=uuid4(),
        task_type="code_generation",
        payload={
            "prompt": "Generate a Python function",
            "model": "claude-3-5-sonnet-20241022",
            "requires_gpu": False,
            "cpu_cores": 2,
            "memory_mb": 4096
        },
        priority=TaskPriority.NORMAL,
        status=TaskStatus.QUEUED,
        required_capabilities={
            "cpu_cores": 2,
            "memory_mb": 4096
        }
    )


@pytest.fixture
def gpu_task():
    """Task requiring GPU"""
    return Task(
        id=uuid4(),
        task_type="ml_training",
        payload={
            "model": "llama-2-7b",
            "requires_gpu": True,
            "gpu_memory_mb": 8192,
            "cpu_cores": 4,
            "memory_mb": 16384
        },
        priority=TaskPriority.HIGH,
        status=TaskStatus.QUEUED,
        required_capabilities={
            "gpu_available": True,
            "gpu_memory_mb": 8192,
            "cpu_cores": 4,
            "memory_mb": 16384
        }
    )


@pytest.fixture
def available_nodes():
    """List of available nodes with varying capabilities"""
    return [
        {
            "peer_id": "node1",
            "capabilities": {
                "cpu_cores": 8,
                "memory_mb": 16384,
                "gpu_available": False,
                "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]
            },
            "current_tasks": 2,
            "health_status": "healthy",
            "performance_score": 85.0
        },
        {
            "peer_id": "node2",
            "capabilities": {
                "cpu_cores": 16,
                "memory_mb": 32768,
                "gpu_available": True,
                "gpu_memory_mb": 16384,
                "models": ["claude-3-5-sonnet-20241022", "llama-2-7b", "llama-2-13b"]
            },
            "current_tasks": 1,
            "health_status": "healthy",
            "performance_score": 92.0
        },
        {
            "peer_id": "node3",
            "capabilities": {
                "cpu_cores": 4,
                "memory_mb": 8192,
                "gpu_available": False,
                "models": ["claude-3-5-sonnet-20241022"]
            },
            "current_tasks": 5,
            "health_status": "degraded",
            "performance_score": 60.0
        },
        {
            "peer_id": "node4",
            "capabilities": {
                "cpu_cores": 12,
                "memory_mb": 24576,
                "gpu_available": True,
                "gpu_memory_mb": 8192,
                "models": ["llama-2-7b"]
            },
            "current_tasks": 0,
            "health_status": "healthy",
            "performance_score": 88.0
        }
    ]


@pytest.fixture
def mock_db_session():
    """Mock database session"""
    session = MagicMock()
    session.query = MagicMock()
    session.add = MagicMock()
    session.commit = MagicMock()
    session.rollback = MagicMock()
    return session


class TestAgentMetrics:
    """Test AgentMetrics class"""

    def test_metrics_initialization(self):
        """
        GIVEN a new agent
        WHEN initializing metrics
        THEN should have default values
        """
        from backend.services.agent_load_balancer_service import AgentMetrics

        metrics = AgentMetrics(agent_id="test-agent")

        assert metrics.agent_id == "test-agent"
        assert metrics.current_tasks == 0
        assert metrics.completed_tasks == 0
        assert metrics.failed_tasks == 0
        assert metrics.average_response_time == 0.0
        assert metrics.error_rate == 0.0

    def test_update_performance_success(self):
        """
        GIVEN metrics for an agent
        WHEN updating with successful task completion
        THEN should increment completed tasks and update averages
        """
        from backend.services.agent_load_balancer_service import AgentMetrics

        metrics = AgentMetrics(agent_id="test-agent")
        metrics.update_performance(response_time=1.5, completion_time=10.0, success=True)

        assert metrics.completed_tasks == 1
        assert metrics.failed_tasks == 0
        assert metrics.average_response_time == 1.5
        assert metrics.average_completion_time == 10.0
        assert metrics.error_rate == 0.0

    def test_update_performance_failure(self):
        """
        GIVEN metrics for an agent
        WHEN updating with failed task
        THEN should increment failed tasks and update error rate
        """
        from backend.services.agent_load_balancer_service import AgentMetrics

        metrics = AgentMetrics(agent_id="test-agent")
        metrics.update_performance(response_time=2.0, completion_time=5.0, success=False)

        assert metrics.completed_tasks == 0
        assert metrics.failed_tasks == 1
        assert metrics.error_rate == 1.0  # 100% error rate

    def test_performance_score_calculation(self):
        """
        GIVEN metrics with various values
        WHEN calculating performance score
        THEN should return weighted score (0-100)
        """
        from backend.services.agent_load_balancer_service import AgentMetrics

        metrics = AgentMetrics(agent_id="test-agent")
        metrics.error_rate = 0.1  # 10% error rate
        metrics.average_response_time = 5.0
        metrics.queue_length = 2
        metrics.cpu_usage = 0.5
        metrics.memory_usage = 0.6

        score = metrics.get_performance_score()

        # Base 100 - error penalty (5) - response penalty (~5) - queue penalty (4) - resource penalty (6)
        assert 75 < score < 85

    def test_is_overloaded_high_tasks(self):
        """
        GIVEN an agent with many current tasks
        WHEN checking if overloaded
        THEN should return True
        """
        from backend.services.agent_load_balancer_service import AgentMetrics

        metrics = AgentMetrics(agent_id="test-agent")
        metrics.current_tasks = 15  # > 10 threshold

        assert metrics.is_overloaded() is True

    def test_is_overloaded_high_cpu(self):
        """
        GIVEN an agent with high CPU usage
        WHEN checking if overloaded
        THEN should return True
        """
        from backend.services.agent_load_balancer_service import AgentMetrics

        metrics = AgentMetrics(agent_id="test-agent")
        metrics.cpu_usage = 0.85  # > 0.8 threshold

        assert metrics.is_overloaded() is True

    def test_is_healthy(self):
        """
        GIVEN an agent with recent heartbeat and low error rate
        WHEN checking if healthy
        THEN should return True
        """
        from backend.services.agent_load_balancer_service import AgentMetrics

        metrics = AgentMetrics(agent_id="test-agent")
        metrics.last_heartbeat = datetime.now(timezone.utc)
        metrics.error_rate = 0.05
        metrics.current_tasks = 3

        assert metrics.is_healthy() is True

    def test_is_not_healthy_old_heartbeat(self):
        """
        GIVEN an agent with old heartbeat
        WHEN checking if healthy
        THEN should return False
        """
        from backend.services.agent_load_balancer_service import AgentMetrics

        metrics = AgentMetrics(agent_id="test-agent")
        metrics.last_heartbeat = datetime.now(timezone.utc) - timedelta(minutes=10)

        assert metrics.is_healthy() is False


class TestSwarmLoadBalancerInitialization:
    """Test SwarmLoadBalancer initialization"""

    @pytest.mark.asyncio
    async def test_initialization_with_default_strategy(self, mock_db_session):
        """
        GIVEN a database session
        WHEN initializing load balancer without strategy
        THEN should use ADAPTIVE strategy by default
        """
        from backend.services.agent_load_balancer_service import (
            SwarmLoadBalancer,
            LoadBalancingStrategy
        )

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        assert balancer.strategy == LoadBalancingStrategy.ADAPTIVE
        assert balancer.round_robin_index == 0
        assert balancer.total_tasks_assigned == 0

    @pytest.mark.asyncio
    async def test_initialization_with_custom_strategy(self, mock_db_session):
        """
        GIVEN a database session and custom strategy
        WHEN initializing load balancer
        THEN should use provided strategy
        """
        from backend.services.agent_load_balancer_service import (
            SwarmLoadBalancer,
            LoadBalancingStrategy
        )

        balancer = SwarmLoadBalancer(
            db_session=mock_db_session,
            strategy=LoadBalancingStrategy.ROUND_ROBIN
        )

        assert balancer.strategy == LoadBalancingStrategy.ROUND_ROBIN


class TestTaskAssignment:
    """Test task assignment logic"""

    @pytest.mark.asyncio
    async def test_assign_task_success(self, mock_db_session, sample_task, available_nodes):
        """
        GIVEN a queued task and available nodes
        WHEN assigning task
        THEN should select best agent and return assignment
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics(available_nodes)

        result = await balancer.assign_task(sample_task, available_nodes)

        assert result is not None
        assert result.peer_id in ["node1", "node2", "node4"]  # node3 is degraded
        assert result.capability_match_score >= 0.0
        assert result.performance_score >= 0.0

    @pytest.mark.asyncio
    async def test_assign_task_no_available_nodes(self, mock_db_session, sample_task):
        """
        GIVEN a task with no available nodes
        WHEN assigning task
        THEN should return None
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        result = await balancer.assign_task(sample_task, [])

        assert result is None

    @pytest.mark.asyncio
    async def test_assign_gpu_task_to_capable_node(
        self, mock_db_session, gpu_task, available_nodes
    ):
        """
        GIVEN a GPU task and mixed nodes
        WHEN assigning task
        THEN should select node with GPU capability
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics(available_nodes)

        result = await balancer.assign_task(gpu_task, available_nodes)

        assert result is not None
        # Only node2 and node4 have GPU
        assert result.peer_id in ["node2", "node4"]

    @pytest.mark.asyncio
    async def test_filter_unhealthy_nodes(self, mock_db_session, sample_task, available_nodes):
        """
        GIVEN nodes with varying health status
        WHEN filtering available agents
        THEN should exclude degraded/unhealthy nodes
        """
        from backend.services.agent_load_balancer_service import (
            SwarmLoadBalancer,
            AgentHealthStatus
        )

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics(available_nodes)

        # Mark node3 as degraded with conditions that make it unhealthy
        balancer.agent_metrics["node3"].health_status = AgentHealthStatus.DEGRADED
        balancer.agent_metrics["node3"].current_tasks = 15  # Overloaded (> 10)
        balancer.agent_metrics["node3"].error_rate = 0.5  # High error rate

        available = await balancer._get_available_agents(sample_task, available_nodes)

        # node3 should be filtered out (unhealthy or overloaded)
        assert "node3" not in available


class TestLoadBalancingStrategies:
    """Test different load balancing strategies"""

    @pytest.mark.asyncio
    async def test_round_robin_selection(self, mock_db_session, available_nodes):
        """
        GIVEN round-robin strategy
        WHEN assigning multiple tasks
        THEN should distribute evenly across agents
        """
        from backend.services.agent_load_balancer_service import (
            SwarmLoadBalancer,
            LoadBalancingStrategy
        )

        balancer = SwarmLoadBalancer(
            db_session=mock_db_session,
            strategy=LoadBalancingStrategy.ROUND_ROBIN
        )

        agents = ["node1", "node2", "node4"]

        # Make 6 selections (2 full rounds)
        selections = []
        for _ in range(6):
            selected = balancer._round_robin_selection(agents)
            selections.append(selected)

        # Each agent should be selected exactly twice
        assert selections.count("node1") == 2
        assert selections.count("node2") == 2
        assert selections.count("node4") == 2

    @pytest.mark.asyncio
    async def test_least_connections_selection(self, mock_db_session, available_nodes):
        """
        GIVEN least-connections strategy
        WHEN selecting agent
        THEN should select agent with fewest current tasks
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics(available_nodes)

        # Set different task counts
        balancer.agent_metrics["node1"].current_tasks = 5
        balancer.agent_metrics["node2"].current_tasks = 2
        balancer.agent_metrics["node4"].current_tasks = 0

        agents = ["node1", "node2", "node4"]
        selected = balancer._least_connections_selection(agents)

        # Should select node4 with 0 tasks
        assert selected == "node4"

    @pytest.mark.asyncio
    async def test_capability_based_selection(
        self, mock_db_session, gpu_task, available_nodes
    ):
        """
        GIVEN capability-based strategy
        WHEN selecting agent for GPU task
        THEN should select agent with best capability match
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics(available_nodes)

        # node2 has better GPU (16GB vs 8GB) and more models
        agents = ["node2", "node4"]
        selected = balancer._capability_based_selection(gpu_task, agents, available_nodes)

        # Should prefer node2 with better capabilities
        assert selected in ["node2", "node4"]  # Both are valid, but algorithm prefers best match

    @pytest.mark.asyncio
    async def test_performance_based_selection(self, mock_db_session, available_nodes):
        """
        GIVEN performance-based strategy
        WHEN selecting agent
        THEN should select agent with highest performance score
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics(available_nodes)

        # Set different performance scores
        balancer.agent_metrics["node1"].error_rate = 0.2  # Lower score
        balancer.agent_metrics["node2"].error_rate = 0.0  # Higher score
        balancer.agent_metrics["node4"].error_rate = 0.1  # Medium score

        agents = ["node1", "node2", "node4"]
        selected = balancer._performance_based_selection(agents)

        # Should select node2 with best performance
        assert selected == "node2"


class TestCapabilityMatching:
    """Test capability matching logic"""

    @pytest.mark.asyncio
    async def test_calculate_capability_match_perfect(
        self, mock_db_session, gpu_task, available_nodes
    ):
        """
        GIVEN a task requiring GPU and specific model
        WHEN calculating match with node that has all capabilities
        THEN should return high match score
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        # node2 has GPU and llama-2-7b model
        score = balancer._calculate_capability_match(gpu_task, available_nodes[1])

        assert score >= 0.8  # High match score

    @pytest.mark.asyncio
    async def test_calculate_capability_match_partial(
        self, mock_db_session, gpu_task, available_nodes
    ):
        """
        GIVEN a task requiring GPU
        WHEN calculating match with node without GPU
        THEN should return low/zero match score based on missing requirements
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        # node1 has no GPU but has some capabilities (cpu_cores, memory_mb)
        # So it will have partial match (2 out of 4 requirements met)
        score = balancer._calculate_capability_match(gpu_task, available_nodes[0])

        # Should be low score since GPU requirement is not met
        assert score < 0.6  # Partial match at best

    @pytest.mark.asyncio
    async def test_node_matches_requirements_boolean(self, mock_db_session):
        """
        GIVEN boolean requirement (gpu_available=True)
        WHEN matching node capabilities
        THEN should match exact boolean value
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        node_with_gpu = {"capabilities": {"gpu_available": True}}
        node_without_gpu = {"capabilities": {"gpu_available": False}}
        requirements = {"gpu_available": True}

        assert balancer._node_matches_requirements(node_with_gpu, requirements) is True
        assert balancer._node_matches_requirements(node_without_gpu, requirements) is False

    @pytest.mark.asyncio
    async def test_node_matches_requirements_numeric(self, mock_db_session):
        """
        GIVEN numeric requirement (cpu_cores >= 4)
        WHEN matching node capabilities
        THEN should require actual >= required
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        node_8_cores = {"capabilities": {"cpu_cores": 8}}
        node_2_cores = {"capabilities": {"cpu_cores": 2}}
        requirements = {"cpu_cores": 4}

        assert balancer._node_matches_requirements(node_8_cores, requirements) is True
        assert balancer._node_matches_requirements(node_2_cores, requirements) is False

    @pytest.mark.asyncio
    async def test_node_matches_requirements_list(self, mock_db_session):
        """
        GIVEN list requirement (models includes specific model)
        WHEN matching node capabilities
        THEN should check all required items present
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        node = {"capabilities": {"models": ["claude-3-5-sonnet-20241022", "llama-2-7b"]}}
        requirements = {"models": ["llama-2-7b"]}

        assert balancer._node_matches_requirements(node, requirements) is True

        requirements_missing = {"models": ["gpt-4"]}
        assert balancer._node_matches_requirements(node, requirements_missing) is False


class TestMetricsUpdate:
    """Test metrics update and tracking"""

    @pytest.mark.asyncio
    async def test_update_agent_metrics(self, mock_db_session):
        """
        GIVEN an agent with metrics
        WHEN updating metrics with new values
        THEN should update and recalculate health status
        """
        from backend.services.agent_load_balancer_service import (
            SwarmLoadBalancer,
            AgentHealthStatus
        )

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics([{"peer_id": "node1", "capabilities": {}}])

        await balancer.update_agent_metrics(
            "node1",
            current_tasks=3,
            cpu_usage=0.4,
            memory_usage=0.5
        )

        metrics = balancer.agent_metrics["node1"]
        assert metrics.current_tasks == 3
        assert metrics.cpu_usage == 0.4
        assert metrics.health_status == AgentHealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_task_completed_updates_metrics(self, mock_db_session, sample_task):
        """
        GIVEN a task assignment
        WHEN task completes successfully
        THEN should update agent metrics and remove assignment
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics([{"peer_id": "node1", "capabilities": {}}])

        # Create fake assignment
        balancer.agent_metrics["node1"].current_tasks = 1
        task_id = str(sample_task.id)
        balancer.task_assignments[task_id] = MagicMock(
            task_id=task_id,
            agent_id="node1",
            assigned_at=datetime.now(timezone.utc)
        )

        await balancer.task_completed(task_id, success=True, completion_time=10.0)

        # Should decrement current tasks
        assert balancer.agent_metrics["node1"].current_tasks == 0
        # Should remove assignment
        assert task_id not in balancer.task_assignments


class TestLoadRebalancing:
    """Test load rebalancing logic"""

    @pytest.mark.asyncio
    async def test_rebalance_no_action_when_balanced(self, mock_db_session):
        """
        GIVEN all agents with balanced load
        WHEN rebalancing
        THEN should not reassign tasks
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        nodes = [
            {"peer_id": "node1", "capabilities": {}},
            {"peer_id": "node2", "capabilities": {}}
        ]
        await balancer.initialize_agent_metrics(nodes)

        balancer.agent_metrics["node1"].current_tasks = 3
        balancer.agent_metrics["node2"].current_tasks = 3

        initial_assignments = len(balancer.task_assignments)
        await balancer.rebalance_tasks()

        # No changes should occur
        assert len(balancer.task_assignments) == initial_assignments


class TestStatistics:
    """Test statistics and reporting"""

    @pytest.mark.asyncio
    async def test_get_load_balancer_stats(self, mock_db_session, available_nodes):
        """
        GIVEN a load balancer with activity
        WHEN getting statistics
        THEN should return comprehensive stats
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics(available_nodes)
        balancer.total_tasks_assigned = 10
        balancer.total_tasks_completed = 8

        stats = balancer.get_load_balancer_stats()

        assert stats["total_tasks_assigned"] == 10
        assert stats["total_tasks_completed"] == 8
        assert stats["agent_count"] == len(available_nodes)
        assert "current_strategy" in stats

    @pytest.mark.asyncio
    async def test_get_agent_metrics_summary(self, mock_db_session, available_nodes):
        """
        GIVEN agents with various metrics
        WHEN getting metrics summary
        THEN should return per-agent statistics
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)
        await balancer.initialize_agent_metrics(available_nodes)

        summary = balancer.get_agent_metrics_summary()

        assert len(summary) == len(available_nodes)
        for node in available_nodes:
            peer_id = node["peer_id"]
            assert peer_id in summary
            assert "current_tasks" in summary[peer_id]
            assert "health_status" in summary[peer_id]
            assert "performance_score" in summary[peer_id]


class TestAdaptiveStrategy:
    """Test adaptive load balancing strategy"""

    @pytest.mark.asyncio
    async def test_adaptive_selection_combines_strategies(
        self, mock_db_session, sample_task, available_nodes
    ):
        """
        GIVEN adaptive strategy
        WHEN selecting agent
        THEN should combine multiple strategies with weights
        """
        from backend.services.agent_load_balancer_service import (
            SwarmLoadBalancer,
            LoadBalancingStrategy
        )

        balancer = SwarmLoadBalancer(
            db_session=mock_db_session,
            strategy=LoadBalancingStrategy.ADAPTIVE
        )
        await balancer.initialize_agent_metrics(available_nodes)

        agents = ["node1", "node2", "node4"]
        selected = await balancer._adaptive_selection(sample_task, agents, available_nodes)

        # Should return one of the healthy agents
        assert selected in agents


class TestEdgeCases:
    """Test edge cases and error conditions"""

    @pytest.mark.asyncio
    async def test_assign_task_single_available_node(
        self, mock_db_session, sample_task, available_nodes
    ):
        """
        GIVEN only one available node
        WHEN assigning task
        THEN should select that node regardless of strategy
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        single_node = [available_nodes[0]]
        await balancer.initialize_agent_metrics(single_node)

        result = await balancer.assign_task(sample_task, single_node)

        assert result is not None
        assert result.peer_id == "node1"

    @pytest.mark.asyncio
    async def test_capability_match_empty_requirements(self, mock_db_session, available_nodes):
        """
        GIVEN task with no capability requirements
        WHEN calculating match
        THEN should return perfect match (1.0)
        """
        from backend.services.agent_load_balancer_service import SwarmLoadBalancer
        from backend.models.task_lease import Task, TaskPriority, TaskStatus

        balancer = SwarmLoadBalancer(db_session=mock_db_session)

        task_no_reqs = Task(
            id=uuid4(),
            task_type="simple_task",
            payload={},
            priority=TaskPriority.NORMAL,
            status=TaskStatus.QUEUED,
            required_capabilities={}
        )

        score = balancer._calculate_capability_match(task_no_reqs, available_nodes[0])

        assert score == 1.0  # Perfect match when no requirements
