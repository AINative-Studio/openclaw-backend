"""
BDD-style tests for Ralph Wiggum convergence detection.

Tests convergence strategies:
1. Tests Passing: All tests pass + no new failures
2. No Changes: No file changes in last iteration
3. Explicit DONE: Agent says "DONE" in self-review
4. Quality Plateau: Metrics unchanged for 3 iterations
5. Max Iterations: Hard limit reached

Refs #143
"""

import pytest
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass, field


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


class DescribeConvergenceDetection:
    """BDD-style test suite for convergence detection."""

    class DescribeTestsPassingStrategy:
        """Tests for the tests_passing convergence strategy."""

        def test_it_converges_when_all_tests_pass(self):
            """Should detect convergence when all tests pass."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=5,
                tests_passed=25,
                tests_failed=0,
                tests_total=25
            )

            result = service.check_tests_passing(iteration)

            assert result.converged is True
            assert result.reason == "All tests passing, no new failures"
            assert result.strategy == "tests_passing"
            assert result.details["tests_passed"] == 25
            assert result.details["tests_failed"] == 0

        def test_it_does_not_converge_when_tests_fail(self):
            """Should not converge when tests are failing."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=5,
                tests_passed=20,
                tests_failed=5,
                tests_total=25
            )

            result = service.check_tests_passing(iteration)

            assert result.converged is False
            assert result.reason is None

        def test_it_does_not_converge_when_no_tests_exist(self):
            """Should not converge when there are no tests."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=5,
                tests_total=0
            )

            result = service.check_tests_passing(iteration)

            assert result.converged is False
            assert result.reason is None

        def test_it_detects_new_test_failures_from_previous_iteration(self):
            """Should not converge if new tests started failing."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            previous = IterationData(
                iteration_number=4,
                tests_passed=25,
                tests_failed=0,
                tests_total=25
            )

            current = IterationData(
                iteration_number=5,
                tests_passed=25,
                tests_failed=0,
                tests_total=25
            )

            # Store previous iteration
            service.add_iteration(previous)

            result = service.check_tests_passing(current)

            assert result.converged is True
            assert "no new failures" in result.reason.lower()

        def test_it_does_not_converge_with_regression(self):
            """Should not converge if test count decreased."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            previous = IterationData(
                iteration_number=4,
                tests_passed=25,
                tests_failed=0,
                tests_total=25
            )

            current = IterationData(
                iteration_number=5,
                tests_passed=20,
                tests_failed=0,
                tests_total=20
            )

            service.add_iteration(previous)
            result = service.check_tests_passing(current)

            assert result.converged is False
            assert result.reason is None

    class DescribeNoChangesStrategy:
        """Tests for the no_changes convergence strategy."""

        def test_it_converges_when_no_files_changed(self):
            """Should detect convergence when no files were modified."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=5,
                files_changed=[]
            )

            result = service.check_no_changes(iteration)

            assert result.converged is True
            assert result.reason == "No files changed"
            assert result.strategy == "no_changes"
            assert result.details["files_changed"] == 0

        def test_it_does_not_converge_when_files_changed(self):
            """Should not converge when files were modified."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=5,
                files_changed=["backend/services/ralph_loop_service.py"]
            )

            result = service.check_no_changes(iteration)

            assert result.converged is False
            assert result.reason is None

        def test_it_ignores_first_iteration(self):
            """Should not converge on first iteration even with no changes."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=1,
                files_changed=[]
            )

            result = service.check_no_changes(iteration)

            assert result.converged is False
            assert result.reason is None

        def test_it_tracks_file_paths_in_details(self):
            """Should include file paths in convergence details."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=5,
                files_changed=["file1.py", "file2.py"]
            )

            result = service.check_no_changes(iteration)

            assert result.converged is False
            assert result.details["files_changed"] == 2

    class DescribeExplicitDoneStrategy:
        """Tests for the explicit_done convergence strategy."""

        def test_it_converges_when_agent_says_done(self):
            """Should detect convergence when agent explicitly says DONE."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=5,
                self_review="I've completed all tasks. Tests are passing. DONE"
            )

            result = service.check_explicit_done(iteration)

            assert result.converged is True
            assert result.reason == "Agent explicitly marked DONE"
            assert result.strategy == "explicit_done"

        def test_it_detects_done_case_insensitive(self):
            """Should detect DONE in any case."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            test_cases = [
                "Everything is done",
                "I'm DONE with this task",
                "Done! All tests passing.",
                "done"
            ]

            for review_text in test_cases:
                iteration = IterationData(
                    iteration_number=5,
                    self_review=review_text
                )
                result = service.check_explicit_done(iteration)
                assert result.converged is True, f"Failed for: {review_text}"

        def test_it_does_not_converge_without_done_keyword(self):
            """Should not converge if DONE keyword is missing."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=5,
                self_review="Tests are passing, code looks good, moving forward"
            )

            result = service.check_explicit_done(iteration)

            assert result.converged is False
            assert result.reason is None

        def test_it_handles_empty_self_review(self):
            """Should not converge with empty self-review."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=5,
                self_review=""
            )

            result = service.check_explicit_done(iteration)

            assert result.converged is False

    class DescribeQualityPlateauStrategy:
        """Tests for the quality_plateau convergence strategy."""

        def test_it_converges_when_metrics_unchanged_for_3_iterations(self):
            """Should detect plateau after 3 iterations with same metrics."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            # Add 3 iterations with identical metrics
            for i in range(3, 6):
                iteration = IterationData(
                    iteration_number=i,
                    tests_passed=25,
                    tests_total=25,
                    coverage_percent=85.0
                )
                service.add_iteration(iteration)

            current = IterationData(
                iteration_number=6,
                tests_passed=25,
                tests_total=25,
                coverage_percent=85.0
            )

            result = service.check_quality_plateau(current)

            assert result.converged is True
            assert result.reason == "Quality metrics plateaued for 3 iterations"
            assert result.strategy == "quality_plateau"

        def test_it_does_not_converge_with_improving_metrics(self):
            """Should not converge when metrics are improving."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            # Add iterations with improving coverage
            iterations = [
                IterationData(iteration_number=3, coverage_percent=75.0),
                IterationData(iteration_number=4, coverage_percent=80.0),
                IterationData(iteration_number=5, coverage_percent=85.0),
            ]

            for it in iterations:
                service.add_iteration(it)

            current = IterationData(
                iteration_number=6,
                coverage_percent=90.0
            )

            result = service.check_quality_plateau(current)

            assert result.converged is False

        def test_it_does_not_converge_with_insufficient_history(self):
            """Should not converge with less than 3 previous iterations."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            # Only 2 previous iterations
            service.add_iteration(IterationData(iteration_number=1, coverage_percent=85.0))
            service.add_iteration(IterationData(iteration_number=2, coverage_percent=85.0))

            current = IterationData(
                iteration_number=3,
                coverage_percent=85.0
            )

            result = service.check_quality_plateau(current)

            assert result.converged is False

        def test_it_considers_multiple_metrics_for_plateau(self):
            """Should check tests_passed, tests_total, and coverage together."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            # Same tests but different coverage - no plateau
            iterations = [
                IterationData(iteration_number=3, tests_total=25, coverage_percent=80.0),
                IterationData(iteration_number=4, tests_total=25, coverage_percent=82.0),
                IterationData(iteration_number=5, tests_total=25, coverage_percent=85.0),
            ]

            for it in iterations:
                service.add_iteration(it)

            current = IterationData(
                iteration_number=6,
                tests_total=25,
                coverage_percent=85.0
            )

            result = service.check_quality_plateau(current)

            # Should not converge because coverage was changing
            assert result.converged is False

        def test_it_includes_plateau_window_in_details(self):
            """Should include plateau window size in result details."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            for i in range(3, 6):
                service.add_iteration(IterationData(
                    iteration_number=i,
                    coverage_percent=85.0
                ))

            current = IterationData(
                iteration_number=6,
                coverage_percent=85.0
            )

            result = service.check_quality_plateau(current)

            assert result.details["plateau_window"] == 3

    class DescribeMaxIterationsLimit:
        """Tests for max_iterations safety limit."""

        def test_it_converges_when_max_iterations_reached(self):
            """Should force convergence at max iterations."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService(max_iterations=20)
            iteration = IterationData(iteration_number=20)

            result = service.check_max_iterations(iteration)

            assert result.converged is True
            assert result.reason == "Maximum iterations reached"
            assert result.strategy == "max_iterations"

        def test_it_does_not_converge_before_max_iterations(self):
            """Should not converge before reaching max iterations."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService(max_iterations=20)
            iteration = IterationData(iteration_number=19)

            result = service.check_max_iterations(iteration)

            assert result.converged is False

        def test_it_uses_default_max_iterations_of_20(self):
            """Should default to 20 max iterations."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            assert service.max_iterations == 20

        def test_it_allows_custom_max_iterations(self):
            """Should allow configurable max iterations."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService(max_iterations=10)
            iteration = IterationData(iteration_number=10)

            result = service.check_max_iterations(iteration)

            assert result.converged is True

        def test_it_includes_max_in_details(self):
            """Should include max_iterations in result details."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService(max_iterations=15)
            iteration = IterationData(iteration_number=15)

            result = service.check_max_iterations(iteration)

            assert result.details["max_iterations"] == 15
            assert result.details["current_iteration"] == 15

    class DescribeCombinedConvergenceCheck:
        """Tests for combined convergence check using all strategies."""

        def test_it_checks_all_strategies_in_order(self):
            """Should check strategies in priority order."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            # Setup iteration that satisfies multiple strategies
            iteration = IterationData(
                iteration_number=5,
                files_changed=[],
                tests_passed=25,
                tests_failed=0,
                tests_total=25,
                self_review="DONE"
            )

            result = service.check_convergence(iteration)

            assert result.converged is True
            # Should use highest priority strategy that matched
            assert result.strategy in ["tests_passing", "no_changes", "explicit_done"]

        def test_it_returns_first_matching_strategy(self):
            """Should return immediately when first strategy matches."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService(max_iterations=5)

            iteration = IterationData(
                iteration_number=5,
                tests_passed=25,
                tests_total=25,
                self_review="DONE"
            )

            result = service.check_convergence(iteration)

            assert result.converged is True
            # Should match one of the strategies before max_iterations
            assert result.strategy in ["tests_passing", "explicit_done"]

        def test_it_continues_when_no_strategy_matches(self):
            """Should not converge if no strategy matches."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService(max_iterations=20)

            iteration = IterationData(
                iteration_number=5,
                files_changed=["some_file.py"],
                tests_failed=5,
                tests_total=25,
                self_review="Still working on it"
            )

            result = service.check_convergence(iteration)

            assert result.converged is False
            assert result.reason is None

        def test_it_uses_max_iterations_as_fallback(self):
            """Should converge at max_iterations even if other strategies fail."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService(max_iterations=10)

            iteration = IterationData(
                iteration_number=10,
                files_changed=["file.py"],
                tests_failed=5,
                self_review="Still working on this"
            )

            result = service.check_convergence(iteration)

            assert result.converged is True
            assert result.strategy == "max_iterations"

        def test_it_includes_all_checked_strategies_in_details(self):
            """Should log which strategies were evaluated."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            iteration = IterationData(
                iteration_number=5,
                self_review="DONE"
            )

            result = service.check_convergence(iteration)

            assert "strategies_checked" in result.details
            assert len(result.details["strategies_checked"]) > 0

    class DescribeIterationHistory:
        """Tests for iteration history management."""

        def test_it_stores_iteration_data(self):
            """Should store iteration data for history tracking."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(
                iteration_number=1,
                files_changed=["file1.py"],
                coverage_percent=75.0
            )

            service.add_iteration(iteration)

            assert len(service.get_iterations()) == 1
            assert service.get_iterations()[0].iteration_number == 1

        def test_it_retrieves_previous_iteration(self):
            """Should retrieve the most recent previous iteration."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            service.add_iteration(IterationData(iteration_number=1))
            service.add_iteration(IterationData(iteration_number=2))
            service.add_iteration(IterationData(iteration_number=3))

            previous = service.get_previous_iteration()

            assert previous is not None
            assert previous.iteration_number == 3

        def test_it_returns_none_when_no_previous_iteration(self):
            """Should return None when no iterations stored."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            previous = service.get_previous_iteration()

            assert previous is None

        def test_it_retrieves_last_n_iterations(self):
            """Should retrieve last N iterations for plateau detection."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            for i in range(1, 6):
                service.add_iteration(IterationData(iteration_number=i))

            last_three = service.get_last_n_iterations(3)

            assert len(last_three) == 3
            assert [it.iteration_number for it in last_three] == [3, 4, 5]

        def test_it_handles_request_for_more_iterations_than_exist(self):
            """Should return all available iterations if N is too large."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            service.add_iteration(IterationData(iteration_number=1))
            service.add_iteration(IterationData(iteration_number=2))

            last_five = service.get_last_n_iterations(5)

            assert len(last_five) == 2

    class DescribeEdgeCases:
        """Tests for edge cases and error handling."""

        def test_it_handles_none_iteration_data(self):
            """Should handle None iteration data gracefully."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()

            with pytest.raises(ValueError, match="Iteration data cannot be None"):
                service.check_convergence(None)

        def test_it_handles_negative_iteration_number(self):
            """Should reject negative iteration numbers."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService()
            iteration = IterationData(iteration_number=-1)

            with pytest.raises(ValueError, match="Iteration number must be positive"):
                service.check_convergence(iteration)

        def test_it_handles_zero_max_iterations(self):
            """Should reject zero max_iterations."""
            with pytest.raises(ValueError, match="max_iterations must be positive"):
                from backend.services.ralph_loop_service import RalphLoopService
                RalphLoopService(max_iterations=0)

        def test_it_handles_negative_max_iterations(self):
            """Should reject negative max_iterations."""
            with pytest.raises(ValueError, match="max_iterations must be positive"):
                from backend.services.ralph_loop_service import RalphLoopService
                RalphLoopService(max_iterations=-5)

        def test_it_handles_extremely_large_iteration_number(self):
            """Should handle very large iteration numbers."""
            from backend.services.ralph_loop_service import RalphLoopService

            service = RalphLoopService(max_iterations=1000000)
            iteration = IterationData(
                iteration_number=999999,
                files_changed=["file.py"],
                self_review="Still working"
            )

            result = service.check_convergence(iteration)

            assert result.converged is False
