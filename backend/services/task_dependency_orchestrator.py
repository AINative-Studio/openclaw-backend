"""
Task Dependency Orchestrator Service

Provides:
- Topological sorting of task dependencies
- Parallel execution wave planning
- Circular dependency detection
- Dependency validation

Extracted from core/src/backend/app/agents/swarm/llm_agent_orchestrator.py
for Issue #114
"""

import logging
from typing import Dict, List, Set, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4
from collections import defaultdict, deque

logger = logging.getLogger(__name__)


class CircularDependencyError(Exception):
    """Raised when a circular dependency is detected in task graph"""
    pass


class InvalidDependencyError(Exception):
    """Raised when a task depends on a non-existent task"""
    pass


@dataclass
class TaskNode:
    """Represents a task in the dependency graph"""
    task_id: str
    dependencies: Set[str] = field(default_factory=set)
    priority: int = 5  # 1-10, higher is more important
    estimated_duration: float = 0.0  # in seconds

    def __hash__(self):
        return hash(self.task_id)

    def __eq__(self, other):
        if isinstance(other, TaskNode):
            return self.task_id == other.task_id
        return False


@dataclass
class ExecutionWave:
    """Represents a wave of tasks that can execute in parallel"""
    wave_number: int
    task_ids: List[str]
    estimated_duration: float = 0.0

    @property
    def parallelism(self) -> int:
        """Number of tasks in this wave (parallel degree)"""
        return len(self.task_ids)


@dataclass
class ExecutionPlan:
    """Complete execution plan with waves and metadata"""
    plan_id: str
    plan_name: str
    description: str = ""
    waves: List[ExecutionWave] = field(default_factory=list)
    total_tasks: int = 0
    estimated_duration: float = 0.0
    created_at: datetime = field(default_factory=lambda: datetime.now())

    def get_metrics(self) -> Dict[str, Any]:
        """Calculate execution plan metrics"""
        sequential_duration = sum(wave.estimated_duration for wave in self.waves)

        return {
            "total_tasks": self.total_tasks,
            "total_waves": len(self.waves),
            "max_parallelism": max((wave.parallelism for wave in self.waves), default=0),
            "estimated_duration": self.estimated_duration,
            "sequential_duration": sequential_duration,
            "parallel_efficiency": sequential_duration / self.estimated_duration if self.estimated_duration > 0 else 0.0,
        }


class DependencyGraph:
    """Graph data structure for task dependencies"""

    def __init__(self):
        self.nodes: Dict[str, TaskNode] = {}
        self._dependents: Dict[str, Set[str]] = defaultdict(set)

    def add_node(self, node: TaskNode) -> None:
        """Add a task node to the graph"""
        self.nodes[node.task_id] = node

        # Build reverse dependency map
        for dep in node.dependencies:
            self._dependents[dep].add(node.task_id)

    def get_dependencies(self, task_id: str) -> Set[str]:
        """Get direct dependencies of a task"""
        if task_id not in self.nodes:
            return set()
        return self.nodes[task_id].dependencies.copy()

    def get_dependents(self, task_id: str) -> Set[str]:
        """Get tasks that depend on this task (reverse dependencies)"""
        return self._dependents.get(task_id, set()).copy()

    def has_node(self, task_id: str) -> bool:
        """Check if task exists in graph"""
        return task_id in self.nodes

    def is_empty(self) -> bool:
        """Check if graph is empty"""
        return len(self.nodes) == 0

    def is_valid(self) -> bool:
        """Check if all dependencies exist"""
        errors = self.validate()
        return len(errors) == 0

    def validate(self) -> List[str]:
        """Validate that all dependencies exist, return error list"""
        errors = []
        for task_id, node in self.nodes.items():
            for dep in node.dependencies:
                if dep not in self.nodes:
                    errors.append(f"Task '{task_id}' depends on non-existent task '{dep}'")
        return errors

    def has_circular_dependency(self) -> bool:
        """Check if graph has any circular dependencies"""
        return self.find_circular_dependency() is not None

    def find_circular_dependency(self) -> Optional[List[str]]:
        """Find a circular dependency if one exists, return the cycle"""
        # Use DFS with recursion stack to detect cycles
        visited = set()
        rec_stack = set()
        path = []

        def dfs(task_id: str) -> Optional[List[str]]:
            visited.add(task_id)
            rec_stack.add(task_id)
            path.append(task_id)

            # Check for self-dependency
            node = self.nodes.get(task_id)
            if node and task_id in node.dependencies:
                return [task_id]

            # Check dependencies
            for dep in self.nodes.get(task_id, TaskNode(task_id)).dependencies:
                if dep not in self.nodes:
                    continue

                if dep not in visited:
                    cycle = dfs(dep)
                    if cycle:
                        return cycle
                elif dep in rec_stack:
                    # Found cycle - extract the cycle from path
                    cycle_start = path.index(dep)
                    return path[cycle_start:] + [dep]

            path.pop()
            rec_stack.remove(task_id)
            return None

        for task_id in self.nodes:
            if task_id not in visited:
                cycle = dfs(task_id)
                if cycle:
                    return cycle

        return None


class TaskDependencyOrchestrator:
    """
    Orchestrates task execution based on dependencies.

    Features:
    - Topological sorting
    - Parallel execution wave planning
    - Circular dependency detection
    - Dependency validation
    """

    def __init__(self, max_parallel_tasks: int = 6):
        self.max_parallel_tasks = max_parallel_tasks
        logger.info(f"TaskDependencyOrchestrator initialized with max_parallel_tasks={max_parallel_tasks}")

    def topological_sort(self, nodes: List[TaskNode]) -> List[str]:
        """
        Perform topological sort on tasks using Kahn's algorithm.

        Args:
            nodes: List of task nodes with dependencies

        Returns:
            List of task IDs in topologically sorted order

        Raises:
            CircularDependencyError: If circular dependency detected
            InvalidDependencyError: If task depends on non-existent task
        """
        # Build dependency graph
        graph = DependencyGraph()
        for node in nodes:
            graph.add_node(node)

        # Validate graph
        if not graph.is_valid():
            errors = graph.validate()
            raise InvalidDependencyError(f"Invalid dependencies: {errors[0]}")

        if graph.has_circular_dependency():
            cycle = graph.find_circular_dependency()
            raise CircularDependencyError(f"Circular dependency detected: {' -> '.join(cycle)}")

        # Kahn's algorithm for topological sort
        in_degree = {node.task_id: len(node.dependencies) for node in nodes}
        queue = deque([node.task_id for node in nodes if len(node.dependencies) == 0])
        sorted_order = []

        while queue:
            task_id = queue.popleft()
            sorted_order.append(task_id)

            # Reduce in-degree for dependents
            for dependent in graph.get_dependents(task_id):
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

        if len(sorted_order) != len(nodes):
            # This shouldn't happen if we checked for cycles, but safety check
            raise CircularDependencyError("Unable to sort tasks - possible circular dependency")

        return sorted_order

    def create_execution_waves(
        self,
        nodes: List[TaskNode],
        sort_by_priority: bool = False
    ) -> List[ExecutionWave]:
        """
        Create execution waves for parallel task execution.

        Tasks in the same wave can execute in parallel.

        Args:
            nodes: List of task nodes
            sort_by_priority: If True, sort tasks within waves by priority

        Returns:
            List of ExecutionWave objects
        """
        # Build dependency graph
        graph = DependencyGraph()
        for node in nodes:
            graph.add_node(node)

        # Validate graph
        if not graph.is_valid():
            errors = graph.validate()
            raise InvalidDependencyError(f"Invalid dependencies: {errors[0]}")

        if graph.has_circular_dependency():
            cycle = graph.find_circular_dependency()
            raise CircularDependencyError(f"Circular dependency detected: {' -> '.join(cycle)}")

        # Calculate in-degree for each node
        in_degree = {node.task_id: len(node.dependencies) for node in nodes}
        node_map = {node.task_id: node for node in nodes}

        waves = []
        wave_number = 0
        completed = set()

        while len(completed) < len(nodes):
            # Find all tasks with no unsatisfied dependencies
            ready_tasks = [
                task_id for task_id in node_map.keys()
                if task_id not in completed and
                all(dep in completed for dep in node_map[task_id].dependencies)
            ]

            if not ready_tasks:
                # No progress made - shouldn't happen with valid graph
                break

            # Apply max parallelism constraint
            if len(ready_tasks) > self.max_parallel_tasks:
                # Sort by priority if requested
                if sort_by_priority:
                    ready_tasks.sort(key=lambda tid: node_map[tid].priority, reverse=True)

                # Split into multiple waves
                for i in range(0, len(ready_tasks), self.max_parallel_tasks):
                    batch = ready_tasks[i:i + self.max_parallel_tasks]
                    wave_duration = max(
                        (node_map[tid].estimated_duration for tid in batch),
                        default=0.0
                    )
                    waves.append(ExecutionWave(
                        wave_number=wave_number,
                        task_ids=batch,
                        estimated_duration=wave_duration
                    ))
                    wave_number += 1
                    completed.update(batch)
            else:
                # Sort by priority if requested
                if sort_by_priority:
                    ready_tasks.sort(key=lambda tid: node_map[tid].priority, reverse=True)

                # Single wave
                wave_duration = max(
                    (node_map[tid].estimated_duration for tid in ready_tasks),
                    default=0.0
                )
                waves.append(ExecutionWave(
                    wave_number=wave_number,
                    task_ids=ready_tasks,
                    estimated_duration=wave_duration
                ))
                wave_number += 1
                completed.update(ready_tasks)

        return waves

    def build_execution_plan(
        self,
        nodes: List[TaskNode],
        plan_name: str = "Execution Plan",
        description: str = ""
    ) -> ExecutionPlan:
        """
        Build a complete execution plan with waves.

        Args:
            nodes: List of task nodes
            plan_name: Name of the plan
            description: Plan description

        Returns:
            ExecutionPlan with waves and metadata
        """
        # Create execution waves
        waves = self.create_execution_waves(nodes)

        # Calculate total estimated duration (sum of wave durations)
        estimated_duration = sum(wave.estimated_duration for wave in waves)

        # Re-number waves
        for i, wave in enumerate(waves):
            wave.wave_number = i

        plan = ExecutionPlan(
            plan_id=f"plan_{uuid4().hex[:8]}",
            plan_name=plan_name,
            description=description,
            waves=waves,
            total_tasks=len(nodes),
            estimated_duration=estimated_duration
        )

        logger.info(
            f"Execution plan created: {len(nodes)} tasks, {len(waves)} waves, "
            f"estimated_duration={estimated_duration:.1f}s"
        )

        return plan

    def validate_plan(self, plan: ExecutionPlan) -> Tuple[bool, List[str]]:
        """
        Validate an execution plan.

        Args:
            plan: Execution plan to validate

        Returns:
            Tuple of (is_valid, error_list)
        """
        errors = []

        # Check that all waves have tasks
        for wave in plan.waves:
            if len(wave.task_ids) == 0:
                errors.append(f"Wave {wave.wave_number} has no tasks")

        # Check that total tasks matches
        wave_task_count = sum(len(wave.task_ids) for wave in plan.waves)
        if wave_task_count != plan.total_tasks:
            errors.append(
                f"Total tasks mismatch: plan says {plan.total_tasks}, "
                f"waves contain {wave_task_count}"
            )

        return len(errors) == 0, errors

    def get_ready_tasks(
        self,
        nodes: List[TaskNode],
        completed_tasks: Set[str]
    ) -> List[str]:
        """
        Get tasks that are ready to execute (all dependencies satisfied).

        Args:
            nodes: List of all task nodes
            completed_tasks: Set of completed task IDs

        Returns:
            List of task IDs ready for execution
        """
        ready = []
        for node in nodes:
            # Skip if already completed
            if node.task_id in completed_tasks:
                continue

            # Check if all dependencies are satisfied
            if all(dep in completed_tasks for dep in node.dependencies):
                ready.append(node.task_id)

        return ready
