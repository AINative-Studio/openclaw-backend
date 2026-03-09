"""
Unit tests for TaskDependencyOrchestrator service (TDD - RED phase)

Tests for:
- Topological sorting of task dependencies
- Parallel execution wave planning
- Circular dependency detection
- Dependency validation
"""

import pytest
from typing import Dict, List, Set
from datetime import datetime

# Import will fail until we implement the service (RED phase)
from backend.services.task_dependency_orchestrator import (
    TaskDependencyOrchestrator,
    DependencyGraph,
    ExecutionWave,
    CircularDependencyError,
    InvalidDependencyError,
    TaskNode,
)


class TestTaskNode:
    """Test TaskNode dataclass"""

    def test_task_node_creation(self):
        """Test creating a task node"""
        node = TaskNode(
            task_id="task_1",
            dependencies={"task_0"},
            priority=5,
            estimated_duration=300.0
        )
        assert node.task_id == "task_1"
        assert node.dependencies == {"task_0"}
        assert node.priority == 5
        assert node.estimated_duration == 300.0

    def test_task_node_no_dependencies(self):
        """Test task node with no dependencies"""
        node = TaskNode(task_id="task_1")
        assert node.task_id == "task_1"
        assert node.dependencies == set()
        assert node.priority == 5  # default
        assert node.estimated_duration == 0.0  # default


class TestDependencyGraph:
    """Test DependencyGraph construction and validation"""

    def test_create_empty_graph(self):
        """Test creating empty dependency graph"""
        graph = DependencyGraph()
        assert len(graph.nodes) == 0
        assert graph.is_empty()

    def test_add_node(self):
        """Test adding a node to the graph"""
        graph = DependencyGraph()
        node = TaskNode(task_id="task_1")
        graph.add_node(node)
        assert "task_1" in graph.nodes
        assert graph.nodes["task_1"] == node

    def test_add_node_with_dependencies(self):
        """Test adding a node with dependencies"""
        graph = DependencyGraph()
        node1 = TaskNode(task_id="task_1")
        node2 = TaskNode(task_id="task_2", dependencies={"task_1"})
        graph.add_node(node1)
        graph.add_node(node2)
        assert "task_2" in graph.nodes
        assert "task_1" in graph.nodes["task_2"].dependencies

    def test_get_dependencies(self):
        """Test getting dependencies for a node"""
        graph = DependencyGraph()
        node1 = TaskNode(task_id="task_1")
        node2 = TaskNode(task_id="task_2", dependencies={"task_1"})
        graph.add_node(node1)
        graph.add_node(node2)
        deps = graph.get_dependencies("task_2")
        assert deps == {"task_1"}

    def test_get_dependents(self):
        """Test getting dependents (reverse dependencies)"""
        graph = DependencyGraph()
        node1 = TaskNode(task_id="task_1")
        node2 = TaskNode(task_id="task_2", dependencies={"task_1"})
        node3 = TaskNode(task_id="task_3", dependencies={"task_1"})
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)
        dependents = graph.get_dependents("task_1")
        assert dependents == {"task_2", "task_3"}

    def test_has_node(self):
        """Test checking if node exists"""
        graph = DependencyGraph()
        node = TaskNode(task_id="task_1")
        graph.add_node(node)
        assert graph.has_node("task_1")
        assert not graph.has_node("task_2")


class TestCircularDependencyDetection:
    """Test circular dependency detection"""

    def test_simple_circular_dependency(self):
        """Test detecting simple circular dependency: A -> B -> A"""
        graph = DependencyGraph()
        node1 = TaskNode(task_id="task_a", dependencies={"task_b"})
        node2 = TaskNode(task_id="task_b", dependencies={"task_a"})
        graph.add_node(node1)
        graph.add_node(node2)

        assert graph.has_circular_dependency()
        cycle = graph.find_circular_dependency()
        assert cycle is not None
        assert set(cycle) == {"task_a", "task_b"}

    def test_complex_circular_dependency(self):
        """Test detecting complex circular dependency: A -> B -> C -> A"""
        graph = DependencyGraph()
        node1 = TaskNode(task_id="task_a", dependencies={"task_b"})
        node2 = TaskNode(task_id="task_b", dependencies={"task_c"})
        node3 = TaskNode(task_id="task_c", dependencies={"task_a"})
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        assert graph.has_circular_dependency()
        cycle = graph.find_circular_dependency()
        assert cycle is not None
        assert set(cycle) == {"task_a", "task_b", "task_c"}

    def test_self_dependency(self):
        """Test detecting self-dependency: A -> A"""
        graph = DependencyGraph()
        node = TaskNode(task_id="task_a", dependencies={"task_a"})
        graph.add_node(node)

        assert graph.has_circular_dependency()

    def test_no_circular_dependency(self):
        """Test graph with no circular dependencies"""
        graph = DependencyGraph()
        node1 = TaskNode(task_id="task_a")
        node2 = TaskNode(task_id="task_b", dependencies={"task_a"})
        node3 = TaskNode(task_id="task_c", dependencies={"task_b"})
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        assert not graph.has_circular_dependency()


class TestInvalidDependencies:
    """Test invalid dependency detection"""

    def test_missing_dependency_node(self):
        """Test detecting missing dependency node"""
        graph = DependencyGraph()
        node = TaskNode(task_id="task_a", dependencies={"task_missing"})
        graph.add_node(node)

        assert not graph.is_valid()
        errors = graph.validate()
        assert len(errors) > 0
        assert "task_missing" in errors[0]

    def test_multiple_missing_dependencies(self):
        """Test detecting multiple missing dependencies"""
        graph = DependencyGraph()
        node = TaskNode(task_id="task_a", dependencies={"task_b", "task_c"})
        graph.add_node(node)

        assert not graph.is_valid()
        errors = graph.validate()
        assert len(errors) == 2

    def test_valid_dependencies(self):
        """Test valid dependency graph"""
        graph = DependencyGraph()
        node1 = TaskNode(task_id="task_a")
        node2 = TaskNode(task_id="task_b", dependencies={"task_a"})
        graph.add_node(node1)
        graph.add_node(node2)

        assert graph.is_valid()
        errors = graph.validate()
        assert len(errors) == 0


class TestTopologicalSort:
    """Test topological sorting"""

    def test_simple_linear_sort(self):
        """Test simple linear dependency: A -> B -> C"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a"),
            TaskNode(task_id="task_b", dependencies={"task_a"}),
            TaskNode(task_id="task_c", dependencies={"task_b"}),
        ]

        sorted_order = orchestrator.topological_sort(nodes)
        assert sorted_order == ["task_a", "task_b", "task_c"]

    def test_parallel_tasks_sort(self):
        """Test tasks with no dependencies can be in any order"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a"),
            TaskNode(task_id="task_b"),
            TaskNode(task_id="task_c"),
        ]

        sorted_order = orchestrator.topological_sort(nodes)
        # All should be in sorted order, but exact order doesn't matter
        assert len(sorted_order) == 3
        assert set(sorted_order) == {"task_a", "task_b", "task_c"}

    def test_diamond_dependency_sort(self):
        """Test diamond dependency: A -> B,C -> D"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a"),
            TaskNode(task_id="task_b", dependencies={"task_a"}),
            TaskNode(task_id="task_c", dependencies={"task_a"}),
            TaskNode(task_id="task_d", dependencies={"task_b", "task_c"}),
        ]

        sorted_order = orchestrator.topological_sort(nodes)
        assert sorted_order[0] == "task_a"
        assert sorted_order[3] == "task_d"
        assert set(sorted_order[1:3]) == {"task_b", "task_c"}

    def test_sort_with_circular_dependency_raises(self):
        """Test that circular dependency raises error during sort"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a", dependencies={"task_b"}),
            TaskNode(task_id="task_b", dependencies={"task_a"}),
        ]

        with pytest.raises(CircularDependencyError) as exc_info:
            orchestrator.topological_sort(nodes)
        assert "Circular dependency detected" in str(exc_info.value)


class TestExecutionWavePlanning:
    """Test parallel execution wave planning"""

    def test_create_execution_waves_linear(self):
        """Test creating waves for linear dependencies"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a"),
            TaskNode(task_id="task_b", dependencies={"task_a"}),
            TaskNode(task_id="task_c", dependencies={"task_b"}),
        ]

        waves = orchestrator.create_execution_waves(nodes)
        assert len(waves) == 3
        assert waves[0].task_ids == ["task_a"]
        assert waves[1].task_ids == ["task_b"]
        assert waves[2].task_ids == ["task_c"]

    def test_create_execution_waves_parallel(self):
        """Test creating waves for parallel tasks"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a"),
            TaskNode(task_id="task_b"),
            TaskNode(task_id="task_c"),
        ]

        waves = orchestrator.create_execution_waves(nodes)
        assert len(waves) == 1
        assert set(waves[0].task_ids) == {"task_a", "task_b", "task_c"}

    def test_create_execution_waves_diamond(self):
        """Test creating waves for diamond dependency"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a"),
            TaskNode(task_id="task_b", dependencies={"task_a"}),
            TaskNode(task_id="task_c", dependencies={"task_a"}),
            TaskNode(task_id="task_d", dependencies={"task_b", "task_c"}),
        ]

        waves = orchestrator.create_execution_waves(nodes)
        assert len(waves) == 3
        assert waves[0].task_ids == ["task_a"]
        assert set(waves[1].task_ids) == {"task_b", "task_c"}
        assert waves[2].task_ids == ["task_d"]

    def test_execution_wave_properties(self):
        """Test execution wave has correct properties"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a", priority=10, estimated_duration=100.0),
            TaskNode(task_id="task_b", priority=5, estimated_duration=200.0),
        ]

        waves = orchestrator.create_execution_waves(nodes)
        wave = waves[0]
        assert wave.wave_number == 0
        assert wave.parallelism == 2
        assert wave.estimated_duration > 0

    def test_waves_respect_max_parallelism(self):
        """Test waves respect max parallelism constraint"""
        orchestrator = TaskDependencyOrchestrator(max_parallel_tasks=2)
        nodes = [
            TaskNode(task_id="task_a"),
            TaskNode(task_id="task_b"),
            TaskNode(task_id="task_c"),
            TaskNode(task_id="task_d"),
        ]

        waves = orchestrator.create_execution_waves(nodes)
        # With max_parallel=2, should split into multiple waves
        for wave in waves:
            assert len(wave.task_ids) <= 2


class TestTaskPrioritization:
    """Test task prioritization within waves"""

    def test_tasks_sorted_by_priority(self):
        """Test tasks within wave are sorted by priority"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_low", priority=1),
            TaskNode(task_id="task_high", priority=10),
            TaskNode(task_id="task_medium", priority=5),
        ]

        waves = orchestrator.create_execution_waves(nodes, sort_by_priority=True)
        # Higher priority should come first
        assert waves[0].task_ids[0] == "task_high"
        assert waves[0].task_ids[1] == "task_medium"
        assert waves[0].task_ids[2] == "task_low"

    def test_priority_preserves_dependencies(self):
        """Test priority sorting preserves dependencies"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a", priority=1),  # Low priority but no deps
            TaskNode(task_id="task_b", priority=10, dependencies={"task_a"}),
        ]

        waves = orchestrator.create_execution_waves(nodes, sort_by_priority=True)
        # Despite lower priority, task_a must come first
        assert waves[0].task_ids == ["task_a"]
        assert waves[1].task_ids == ["task_b"]


class TestDependencyOrchestrator:
    """Test main TaskDependencyOrchestrator functionality"""

    def test_orchestrator_initialization(self):
        """Test orchestrator initialization"""
        orchestrator = TaskDependencyOrchestrator(max_parallel_tasks=4)
        assert orchestrator.max_parallel_tasks == 4

    def test_build_execution_plan(self):
        """Test building complete execution plan"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="design", priority=10, estimated_duration=100.0),
            TaskNode(task_id="backend", dependencies={"design"}, priority=8, estimated_duration=200.0),
            TaskNode(task_id="frontend", dependencies={"design"}, priority=8, estimated_duration=150.0),
            TaskNode(task_id="test", dependencies={"backend", "frontend"}, priority=7, estimated_duration=50.0),
        ]

        plan = orchestrator.build_execution_plan(nodes, plan_name="Test Plan")
        assert plan.plan_name == "Test Plan"
        assert len(plan.waves) == 3
        assert plan.total_tasks == 4
        assert plan.estimated_duration > 0

    def test_validate_execution_plan(self):
        """Test validating execution plan"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a"),
            TaskNode(task_id="task_b", dependencies={"task_a"}),
        ]

        plan = orchestrator.build_execution_plan(nodes)
        is_valid, errors = orchestrator.validate_plan(plan)
        assert is_valid
        assert len(errors) == 0

    def test_invalid_plan_with_circular_dependency(self):
        """Test invalid plan with circular dependency"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a", dependencies={"task_b"}),
            TaskNode(task_id="task_b", dependencies={"task_a"}),
        ]

        with pytest.raises(CircularDependencyError):
            orchestrator.build_execution_plan(nodes)

    def test_invalid_plan_with_missing_dependency(self):
        """Test invalid plan with missing dependency"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a", dependencies={"task_missing"}),
        ]

        with pytest.raises(InvalidDependencyError):
            orchestrator.build_execution_plan(nodes)

    def test_get_ready_tasks(self):
        """Test getting tasks ready for execution"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a"),
            TaskNode(task_id="task_b", dependencies={"task_a"}),
            TaskNode(task_id="task_c"),
        ]

        ready = orchestrator.get_ready_tasks(nodes, completed_tasks=set())
        assert set(ready) == {"task_a", "task_c"}

        ready = orchestrator.get_ready_tasks(nodes, completed_tasks={"task_a"})
        assert set(ready) == {"task_b", "task_c"}

    def test_estimate_completion_time(self):
        """Test estimating plan completion time"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a", estimated_duration=100.0),
            TaskNode(task_id="task_b", estimated_duration=200.0),
            TaskNode(task_id="task_c", dependencies={"task_a", "task_b"}, estimated_duration=50.0),
        ]

        plan = orchestrator.build_execution_plan(nodes)
        # Parallel execution: max(100, 200) + 50 = 250
        assert plan.estimated_duration == 250.0

    def test_complex_dependency_graph(self):
        """Test complex real-world dependency graph"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            # Architecture phase
            TaskNode(task_id="architect", priority=10, estimated_duration=600.0),

            # Implementation phase (parallel)
            TaskNode(task_id="backend", dependencies={"architect"}, priority=8, estimated_duration=900.0),
            TaskNode(task_id="frontend", dependencies={"architect"}, priority=8, estimated_duration=900.0),

            # Testing phase
            TaskNode(task_id="test", dependencies={"backend", "frontend"}, priority=7, estimated_duration=600.0),

            # Final phase (parallel)
            TaskNode(task_id="devops", dependencies={"test"}, priority=6, estimated_duration=600.0),
            TaskNode(task_id="docs", dependencies={"backend", "frontend"}, priority=5, estimated_duration=600.0),
        ]

        plan = orchestrator.build_execution_plan(nodes)
        # Wave structure:
        # Wave 0: architect (no deps)
        # Wave 1: backend, frontend (depend on architect)
        # Wave 2: test, docs (both depend on backend+frontend, can run in parallel)
        # Wave 3: devops (depends on test)
        assert len(plan.waves) == 4
        assert plan.waves[0].task_ids == ["architect"]
        assert set(plan.waves[1].task_ids) == {"backend", "frontend"}
        assert set(plan.waves[2].task_ids) == {"test", "docs"}
        assert plan.waves[3].task_ids == ["devops"]


class TestExecutionPlanMetrics:
    """Test execution plan metrics and statistics"""

    def test_plan_has_metadata(self):
        """Test execution plan has metadata"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [TaskNode(task_id="task_a")]

        plan = orchestrator.build_execution_plan(nodes, plan_name="Test", description="Test plan")
        assert plan.plan_name == "Test"
        assert plan.description == "Test plan"
        assert plan.plan_id is not None
        assert plan.created_at is not None

    def test_plan_calculates_metrics(self):
        """Test plan calculates execution metrics"""
        orchestrator = TaskDependencyOrchestrator()
        nodes = [
            TaskNode(task_id="task_a", estimated_duration=100.0),
            TaskNode(task_id="task_b", estimated_duration=200.0),
        ]

        plan = orchestrator.build_execution_plan(nodes)
        metrics = plan.get_metrics()
        assert metrics["total_tasks"] == 2
        assert metrics["total_waves"] == 1
        assert metrics["max_parallelism"] == 2
        assert metrics["estimated_duration"] == 200.0  # max of parallel tasks
        # sequential_duration is sum of wave durations (both tasks in one wave = 200)
        assert metrics["sequential_duration"] == 200.0
        # parallel_efficiency = sequential/parallel = 200/200 = 1.0 (no speedup when already parallel)
        assert metrics["parallel_efficiency"] == 1.0
