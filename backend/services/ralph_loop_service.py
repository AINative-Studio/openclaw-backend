"""
Ralph Wiggum Loop Service - Convergence Detection

Manages convergence detection for Ralph autonomous loops with multiple strategies:
1. Tests Passing: All tests pass + no new failures
2. No Changes: No file changes in last iteration
3. Explicit DONE: Agent says "DONE" in self-review
4. Quality Plateau: Metrics unchanged for 3 iterations
5. Max Iterations: Hard limit reached

Refs #143
"""

from typing import List, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class IterationData:
    """Data from a single Ralph iteration."""
    iteration_number: int
    files_changed: List[str] = field(default_factory=list)
    tests_passed: int = 0
    tests_failed: int = 0
    tests_total: int = 0
    coverage_percent: float = 0.0
    self_review: str = ""
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ConvergenceResult:
    """Result of convergence check."""
    converged: bool
    reason: Optional[str] = None
    strategy: Optional[str] = None
    details: Dict = field(default_factory=dict)


class RalphLoopService:
    """
    Service for detecting convergence in Ralph Wiggum autonomous loops.

    Convergence Strategies (checked in priority order):
    1. tests_passing: All tests pass + no new failures
    2. explicit_done: Agent explicitly says "DONE"
    3. no_changes: No file changes in iteration
    4. quality_plateau: Metrics unchanged for 3 iterations
    5. max_iterations: Hard limit reached (always checked last)

    Usage:
        service = RalphLoopService(max_iterations=20)

        # Add iterations as they complete
        service.add_iteration(iteration_data)

        # Check convergence
        result = service.check_convergence(current_iteration)
        if result.converged:
            print(f"Converged: {result.reason}")
    """

    def __init__(self, max_iterations: int = 20):
        """
        Initialize Ralph loop service.

        Args:
            max_iterations: Maximum iterations before forced convergence (default: 20)

        Raises:
            ValueError: If max_iterations is not positive
        """
        if max_iterations <= 0:
            raise ValueError("max_iterations must be positive")

        self.max_iterations = max_iterations
        self._iteration_history: List[IterationData] = []

    def check_convergence(self, iteration: IterationData) -> ConvergenceResult:
        """
        Check if convergence has been reached using all strategies.

        Strategies are checked in priority order. Returns immediately
        when first strategy detects convergence.

        Args:
            iteration: Current iteration data

        Returns:
            ConvergenceResult with converged flag and details

        Raises:
            ValueError: If iteration is None or has invalid data
        """
        if iteration is None:
            raise ValueError("Iteration data cannot be None")

        if iteration.iteration_number <= 0:
            raise ValueError("Iteration number must be positive")

        strategies_checked = []

        # Strategy 1: Tests Passing
        result = self.check_tests_passing(iteration)
        strategies_checked.append("tests_passing")
        if result.converged:
            result.details["strategies_checked"] = strategies_checked
            return result

        # Strategy 2: Explicit DONE
        result = self.check_explicit_done(iteration)
        strategies_checked.append("explicit_done")
        if result.converged:
            result.details["strategies_checked"] = strategies_checked
            return result

        # Strategy 3: No Changes
        result = self.check_no_changes(iteration)
        strategies_checked.append("no_changes")
        if result.converged:
            result.details["strategies_checked"] = strategies_checked
            return result

        # Strategy 4: Quality Plateau
        result = self.check_quality_plateau(iteration)
        strategies_checked.append("quality_plateau")
        if result.converged:
            result.details["strategies_checked"] = strategies_checked
            return result

        # Strategy 5: Max Iterations (always last)
        result = self.check_max_iterations(iteration)
        strategies_checked.append("max_iterations")
        if result.converged:
            result.details["strategies_checked"] = strategies_checked
            return result

        # No convergence
        return ConvergenceResult(
            converged=False,
            details={"strategies_checked": strategies_checked}
        )

    def check_tests_passing(self, iteration: IterationData) -> ConvergenceResult:
        """
        Check if all tests are passing with no regressions.

        Convergence criteria:
        - tests_total > 0 (tests exist)
        - tests_failed == 0 (all tests pass)
        - tests_total >= previous iteration (no test deletion)

        Args:
            iteration: Current iteration data

        Returns:
            ConvergenceResult indicating if tests passing strategy matched
        """
        # Need at least some tests
        if iteration.tests_total == 0:
            return ConvergenceResult(converged=False)

        # All tests must pass
        if iteration.tests_failed > 0:
            return ConvergenceResult(converged=False)

        # Check for regression (test deletion)
        previous = self.get_previous_iteration()
        if previous is not None:
            if iteration.tests_total < previous.tests_total:
                # Test count decreased - regression
                return ConvergenceResult(converged=False)

        return ConvergenceResult(
            converged=True,
            reason="All tests passing, no new failures",
            strategy="tests_passing",
            details={
                "tests_passed": iteration.tests_passed,
                "tests_failed": iteration.tests_failed,
                "tests_total": iteration.tests_total
            }
        )

    def check_no_changes(self, iteration: IterationData) -> ConvergenceResult:
        """
        Check if no files were changed in this iteration.

        Convergence criteria:
        - Not first iteration
        - files_changed list is empty

        Args:
            iteration: Current iteration data

        Returns:
            ConvergenceResult indicating if no_changes strategy matched
        """
        # Don't converge on first iteration
        if iteration.iteration_number == 1:
            return ConvergenceResult(converged=False)

        # Check if any files changed
        files_changed_count = len(iteration.files_changed)

        if files_changed_count == 0:
            return ConvergenceResult(
                converged=True,
                reason="No files changed",
                strategy="no_changes",
                details={"files_changed": 0}
            )

        return ConvergenceResult(
            converged=False,
            details={"files_changed": files_changed_count}
        )

    def check_explicit_done(self, iteration: IterationData) -> ConvergenceResult:
        """
        Check if agent explicitly said "DONE" in self-review.

        Convergence criteria:
        - self_review contains "done" (case-insensitive)

        Args:
            iteration: Current iteration data

        Returns:
            ConvergenceResult indicating if explicit_done strategy matched
        """
        self_review = iteration.self_review.lower()

        if "done" in self_review:
            return ConvergenceResult(
                converged=True,
                reason="Agent explicitly marked DONE",
                strategy="explicit_done",
                details={"self_review_length": len(iteration.self_review)}
            )

        return ConvergenceResult(converged=False)

    def check_quality_plateau(self, iteration: IterationData) -> ConvergenceResult:
        """
        Check if quality metrics have plateaued for 3 iterations.

        Convergence criteria:
        - Have at least 3 previous iterations
        - tests_total unchanged for last 3 iterations
        - coverage_percent unchanged for last 3 iterations

        Args:
            iteration: Current iteration data

        Returns:
            ConvergenceResult indicating if quality_plateau strategy matched
        """
        # Need at least 3 previous iterations
        last_three = self.get_last_n_iterations(3)
        if len(last_three) < 3:
            return ConvergenceResult(converged=False)

        # Check if all metrics are identical for last 3 + current
        all_iterations = last_three + [iteration]

        # Extract metrics
        test_counts = [it.tests_total for it in all_iterations]
        coverages = [it.coverage_percent for it in all_iterations]

        # Check if all identical
        tests_plateaued = len(set(test_counts)) == 1
        coverage_plateaued = len(set(coverages)) == 1

        if tests_plateaued and coverage_plateaued:
            return ConvergenceResult(
                converged=True,
                reason="Quality metrics plateaued for 3 iterations",
                strategy="quality_plateau",
                details={
                    "plateau_window": 3,
                    "tests_total": iteration.tests_total,
                    "coverage_percent": iteration.coverage_percent
                }
            )

        return ConvergenceResult(converged=False)

    def check_max_iterations(self, iteration: IterationData) -> ConvergenceResult:
        """
        Check if maximum iterations reached (safety limit).

        Convergence criteria:
        - iteration_number >= max_iterations

        Args:
            iteration: Current iteration data

        Returns:
            ConvergenceResult indicating if max_iterations limit reached
        """
        if iteration.iteration_number >= self.max_iterations:
            return ConvergenceResult(
                converged=True,
                reason="Maximum iterations reached",
                strategy="max_iterations",
                details={
                    "max_iterations": self.max_iterations,
                    "current_iteration": iteration.iteration_number
                }
            )

        return ConvergenceResult(converged=False)

    def add_iteration(self, iteration: IterationData) -> None:
        """
        Add iteration to history for tracking.

        Args:
            iteration: Iteration data to store
        """
        self._iteration_history.append(iteration)

    def get_iterations(self) -> List[IterationData]:
        """
        Get all stored iterations.

        Returns:
            List of all iteration data in chronological order
        """
        return self._iteration_history.copy()

    def get_previous_iteration(self) -> Optional[IterationData]:
        """
        Get the most recent iteration from history.

        Returns:
            Most recent IterationData or None if no history
        """
        if not self._iteration_history:
            return None
        return self._iteration_history[-1]

    def get_last_n_iterations(self, n: int) -> List[IterationData]:
        """
        Get the last N iterations from history.

        Args:
            n: Number of iterations to retrieve

        Returns:
            List of up to N most recent iterations
        """
        if n <= 0:
            return []

        if len(self._iteration_history) < n:
            return self._iteration_history.copy()

        return self._iteration_history[-n:]

    def reset(self) -> None:
        """
        Reset service state and clear iteration history.

        Used for starting a new loop session.
        """
        self._iteration_history.clear()
