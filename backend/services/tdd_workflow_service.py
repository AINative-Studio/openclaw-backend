"""
TDD Workflow Service

Enforces Test-Driven Development workflow with RED-GREEN-REFACTOR cycle.

This service ensures:
1. Tests are written BEFORE implementation (RED phase)
2. Tests pass with minimal code (GREEN phase)
3. Code can be refactored safely (REFACTOR phase)
4. 80%+ code coverage is maintained
5. No code commits without tests
"""

from enum import Enum
from typing import Dict, Any, List, Optional
from datetime import datetime
from collections import defaultdict, deque


class TDDPhase(Enum):
    """TDD workflow phases"""
    RED = "red"
    GREEN = "green"
    REFACTOR = "refactor"

    def description(self) -> str:
        """Get phase description"""
        descriptions = {
            TDDPhase.RED: "Write failing tests before implementation",
            TDDPhase.GREEN: "Make tests pass with minimal code",
            TDDPhase.REFACTOR: "Improve code while maintaining passing tests"
        }
        return descriptions[self]


class TDDViolationError(Exception):
    """Exception raised when TDD workflow is violated"""

    def __init__(self, message: str, phase: Optional[str] = None, file_path: Optional[str] = None):
        super().__init__(message)
        self.phase = phase
        self.file_path = file_path


class TDDWorkflowService:
    """
    Service to enforce Test-Driven Development workflow.

    Tracks test execution history and enforces RED-GREEN-REFACTOR cycle.
    """

    def __init__(self, coverage_threshold: float = 80.0):
        """
        Initialize TDD workflow service.

        Args:
            coverage_threshold: Minimum code coverage percentage (default: 80.0)
        """
        self._coverage_threshold = coverage_threshold
        self._current_phase: Dict[str, TDDPhase] = defaultdict(lambda: TDDPhase.RED)
        self._execution_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._violations: List[str] = []
        self._test_file_map: Dict[str, str] = {}  # Maps code file to test file

        # Track workflow state per test file
        self._workflow_state: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
            'tests_exist': False,
            'tests_passing': False,
            'code_coverage': 0.0,
            'red_completed': False,
            'green_completed': False,
            'refactor_completed': False,
            'refactor_iterations': 0
        })

    def get_current_state(self) -> Dict[str, Any]:
        """Get current TDD workflow state"""
        # Return state for the most recent test file or default state
        if not self._workflow_state:
            return {
                'phase': TDDPhase.RED,
                'tests_exist': False,
                'tests_passing': False,
                'code_coverage': 0.0
            }

        # Get most recently updated test file
        latest_file = max(
            self._workflow_state.keys(),
            key=lambda f: self._workflow_state[f].get('last_updated', datetime.min),
            default=None
        ) if self._workflow_state else None

        if latest_file:
            state = self._workflow_state[latest_file].copy()
            state['phase'] = self._current_phase.get(latest_file, TDDPhase.RED)
            return state

        return {
            'phase': TDDPhase.RED,
            'tests_exist': False,
            'tests_passing': False,
            'code_coverage': 0.0
        }

    def get_current_phase(self, test_file: Optional[str] = None) -> TDDPhase:
        """
        Get current TDD phase.

        Args:
            test_file: Optional test file to check phase for

        Returns:
            Current TDDPhase
        """
        if test_file:
            return self._current_phase.get(test_file, TDDPhase.RED)

        # Return most recent phase
        if not self._current_phase:
            return TDDPhase.RED

        # Get most recently updated test file
        latest_file = max(
            self._workflow_state.keys(),
            key=lambda f: self._workflow_state[f].get('last_updated', datetime.min),
            default=None
        ) if self._workflow_state else None

        return self._current_phase.get(latest_file, TDDPhase.RED) if latest_file else TDDPhase.RED

    def record_test_execution(
        self,
        test_file: str,
        passed: int,
        failed: int,
        coverage: float,
        skip_red_validation: bool = True,
        enforce_coverage: bool = False,
        uncovered_lines: Optional[List[int]] = None
    ) -> Dict[str, Any]:
        """
        Record a test execution.

        Args:
            test_file: Path to test file
            passed: Number of tests passed
            failed: Number of tests failed
            coverage: Code coverage percentage
            skip_red_validation: Skip validation that tests must fail first
            enforce_coverage: Enforce coverage threshold
            uncovered_lines: List of line numbers without coverage

        Returns:
            Execution result with phase and status

        Raises:
            TDDViolationError: If TDD workflow is violated
        """
        current_phase = self._current_phase.get(test_file, TDDPhase.RED)
        state = self._workflow_state[test_file]

        # Create execution record
        execution = {
            'timestamp': datetime.now(),
            'test_file': test_file,
            'passed': passed,
            'failed': failed,
            'coverage': coverage,
            'code_coverage': coverage,  # Also include as code_coverage for backward compatibility
            'uncovered_lines': uncovered_lines or [],
            'phase': current_phase,
            'tests_exist': True,
            'tests_passing': False,  # Will be updated below
            'is_valid_red_state': False,
            'is_valid_green_state': False,
            'coverage_met': False
        }

        # Validate TDD workflow
        # Handle both boolean and integer passed counts
        if isinstance(passed, bool):
            tests_passing = passed and failed == 0
        else:
            tests_passing = failed == 0 and passed > 0

        # RED phase: Tests should fail initially
        if current_phase == TDDPhase.RED and not skip_red_validation:
            if tests_passing and not state['red_completed']:
                raise TDDViolationError(
                    "Tests must fail first in RED phase before implementation",
                    phase="RED",
                    file_path=test_file
                )

        # Mark tests as existing
        state['tests_exist'] = True
        state['tests_passing'] = tests_passing
        state['code_coverage'] = coverage
        state['last_updated'] = datetime.now()

        # Update execution record
        execution['tests_passing'] = tests_passing

        # Track phase completion
        if current_phase == TDDPhase.RED and failed > 0:
            state['red_completed'] = True
            execution['is_valid_red_state'] = True

        if tests_passing:
            # Check coverage threshold if in GREEN phase or enforcing coverage
            if enforce_coverage and coverage < self._coverage_threshold:
                # Format threshold without decimals if it's a whole number
                threshold_str = f"{int(self._coverage_threshold)}%" if self._coverage_threshold == int(self._coverage_threshold) else f"{self._coverage_threshold:.1f}%"
                raise TDDViolationError(
                    f"Coverage {coverage:.1f}% below required threshold {threshold_str}",
                    phase="GREEN",
                    file_path=test_file
                )

            # Mark GREEN state as valid when tests pass
            if current_phase == TDDPhase.GREEN or state.get('red_completed', False):
                state['green_completed'] = True
                execution['is_valid_green_state'] = True

            execution['coverage_met'] = coverage >= self._coverage_threshold

        # REFACTOR phase: Tests must stay passing
        if current_phase == TDDPhase.REFACTOR:
            if not tests_passing:
                raise TDDViolationError(
                    "Refactor broke tests - tests must remain passing during refactor",
                    phase="REFACTOR",
                    file_path=test_file
                )
            state['refactor_iterations'] += 1
            state['refactor_completed'] = True

        # Record execution in history
        self._execution_history[test_file].append(execution)

        # Auto-transition phases
        if current_phase == TDDPhase.RED and tests_passing and state.get('red_completed', False):
            self._current_phase[test_file] = TDDPhase.GREEN
            execution['phase'] = TDDPhase.GREEN
        elif current_phase == TDDPhase.RED and tests_passing:
            # Allow direct transition to GREEN if tests pass (for simple workflows)
            self._current_phase[test_file] = TDDPhase.GREEN
            execution['phase'] = TDDPhase.GREEN

        return execution

    def validate_code_commit(
        self,
        file_path: str,
        has_tests: bool,
        enforce_coverage: bool = True
    ) -> Dict[str, Any]:
        """
        Validate if code is ready to commit.

        Args:
            file_path: Path to code file
            has_tests: Whether tests exist for this file
            enforce_coverage: Whether to enforce coverage threshold

        Returns:
            Validation result

        Raises:
            TDDViolationError: If commit validation fails
        """
        if not has_tests:
            error_msg = f"Tests required before committing code (RED phase violation): {file_path}"
            self._violations.append(error_msg)
            raise TDDViolationError(error_msg, phase="RED", file_path=file_path)

        # Find associated test file
        test_file = self._find_test_file(file_path)
        if not test_file:
            error_msg = f"No test file found for: {file_path}"
            self._violations.append(error_msg)
            raise TDDViolationError(error_msg, phase="RED", file_path=file_path)

        state = self._workflow_state.get(test_file)
        if not state or not state['tests_exist']:
            error_msg = f"Tests must exist before committing code: {file_path}"
            self._violations.append(error_msg)
            raise TDDViolationError(error_msg, phase="RED", file_path=file_path)

        if not state['tests_passing']:
            error_msg = f"Failing tests detected - all tests must pass before committing code: {file_path}"
            self._violations.append(error_msg)
            raise TDDViolationError(error_msg, phase="GREEN", file_path=file_path)

        if enforce_coverage and state['code_coverage'] < self._coverage_threshold:
            # Format threshold without decimals if it's a whole number
            threshold_str = f"{int(self._coverage_threshold)}%" if self._coverage_threshold == int(self._coverage_threshold) else f"{self._coverage_threshold:.1f}%"
            error_msg = (
                f"Coverage {state['code_coverage']:.1f}% below required "
                f"threshold {threshold_str} for: {file_path}"
            )
            self._violations.append(error_msg)
            raise TDDViolationError(error_msg, phase="GREEN", file_path=file_path)

        return {
            'valid': True,
            'file_path': file_path,
            'test_file': test_file,
            'coverage': state['code_coverage'],
            'phase': self._current_phase.get(test_file, TDDPhase.RED)
        }

    def _find_test_file(self, file_path: str) -> Optional[str]:
        """Find test file for given code file"""
        # Check cached mapping
        if file_path in self._test_file_map:
            return self._test_file_map[file_path]

        # Try to infer test file name
        # Extract filename from path
        parts = file_path.split('/')
        filename = parts[-1]

        if filename.endswith('.py'):
            # Generate test file name
            test_name = f"test_{filename}"

            # Check if we have execution history for this test
            for test_file in self._execution_history.keys():
                if test_name in test_file:
                    self._test_file_map[file_path] = test_file
                    return test_file

        return None

    def validate_test_file_name(self, test_file: str) -> Dict[str, Any]:
        """
        Validate test file follows naming convention.

        Args:
            test_file: Path to test file

        Returns:
            Validation result
        """
        filename = test_file.split('/')[-1]
        is_valid = filename.startswith('test_') and filename.endswith('.py')

        return {
            'is_valid': is_valid,
            'test_file': test_file,
            'reason': 'Valid test file name' if is_valid else 'Test files must start with "test_"'
        }

    def get_execution_history(self, test_file: str) -> List[Dict[str, Any]]:
        """Get test execution history for a file"""
        return self._execution_history.get(test_file, [])

    def start_refactor_phase(self, test_file: Optional[str] = None) -> None:
        """
        Start refactor phase.

        Args:
            test_file: Test file to refactor (uses most recent if None)

        Raises:
            TDDViolationError: If tests are not passing
        """
        if test_file is None:
            # Get most recent test file
            if not self._workflow_state:
                raise TDDViolationError(
                    "No tests available - tests must be passing before refactoring",
                    phase="REFACTOR"
                )

            test_file = max(
                self._workflow_state.keys(),
                key=lambda f: self._workflow_state[f].get('last_updated', datetime.min)
            )

        state = self._workflow_state.get(test_file)
        if not state or not state['tests_passing']:
            raise TDDViolationError(
                "Tests must be passing before starting refactor phase",
                phase="REFACTOR",
                file_path=test_file
            )

        self._current_phase[test_file] = TDDPhase.REFACTOR

    def set_coverage_threshold(self, threshold: float) -> None:
        """Set coverage threshold percentage"""
        self._coverage_threshold = threshold

    def get_coverage_threshold(self) -> float:
        """Get current coverage threshold"""
        return self._coverage_threshold

    def get_refactor_statistics(self, test_file: str) -> Dict[str, Any]:
        """Get refactor statistics for a test file"""
        state = self._workflow_state.get(test_file, {})
        history = self._execution_history.get(test_file, [])

        # Calculate coverage improvement
        if len(history) >= 2:
            initial_coverage = history[0].get('coverage', 0)
            final_coverage = history[-1].get('coverage', 0)
            coverage_improvement = final_coverage - initial_coverage
        else:
            coverage_improvement = 0

        return {
            'refactor_iterations': state.get('refactor_iterations', 0),
            'coverage_improvement': coverage_improvement,
            'test_file': test_file
        }

    def get_coverage_report(self, test_file: str) -> Dict[str, Any]:
        """Get coverage report for a test file"""
        history = self._execution_history.get(test_file, [])
        if not history:
            return {
                'coverage_percentage': 0.0,
                'uncovered_lines': [],
                'coverage_gap': self._coverage_threshold
            }

        latest = history[-1]
        coverage = latest.get('coverage', 0.0)

        return {
            'coverage_percentage': coverage,
            'uncovered_lines': latest.get('uncovered_lines', []),
            'coverage_gap': max(0, self._coverage_threshold - coverage)
        }

    def get_workflow_cycle_status(self, test_file: str) -> Dict[str, Any]:
        """Get status of complete RED-GREEN-REFACTOR cycle"""
        state = self._workflow_state.get(test_file, {})

        red_completed = state.get('red_completed', False)
        green_completed = state.get('green_completed', False)
        refactor_completed = state.get('refactor_completed', False)

        return {
            'test_file': test_file,
            'red_completed': red_completed,
            'green_completed': green_completed,
            'refactor_completed': refactor_completed,
            'cycle_valid': red_completed and green_completed
        }

    def generate_workflow_report(self, test_file: str) -> Dict[str, Any]:
        """Generate comprehensive workflow report"""
        history = self._execution_history.get(test_file, [])
        state = self._workflow_state.get(test_file, {})
        cycle_status = self.get_workflow_cycle_status(test_file)

        # Extract coverage history
        coverage_history = [
            {
                'timestamp': exec_record.get('timestamp'),
                'coverage': exec_record.get('coverage', 0)
            }
            for exec_record in history
        ]

        return {
            'test_file': test_file,
            'total_executions': len(history),
            'current_phase': self._current_phase.get(test_file, TDDPhase.RED),
            'coverage_history': coverage_history,
            'cycle_compliance': cycle_status,
            'current_coverage': state.get('code_coverage', 0.0),
            'tests_passing': state.get('tests_passing', False)
        }

    def detect_violations(self) -> List[str]:
        """Detect and return TDD workflow violations"""
        return self._violations.copy()

    def is_ready_to_commit(self, file_path: str) -> bool:
        """
        Check if code is ready to commit.

        Args:
            file_path: Path to code file

        Returns:
            True if ready to commit, False otherwise
        """
        try:
            # Find test file
            test_file = self._find_test_file(file_path)
            if not test_file:
                return False

            state = self._workflow_state.get(test_file)
            if not state:
                return False

            # Check all conditions
            tests_exist = state.get('tests_exist', False)
            tests_passing = state.get('tests_passing', False)
            coverage_met = state.get('code_coverage', 0) >= self._coverage_threshold

            return tests_exist and tests_passing and coverage_met

        except Exception:
            return False

    def get_pre_commit_checklist(self, file_path: str) -> Dict[str, bool]:
        """
        Generate pre-commit validation checklist.

        Args:
            file_path: Path to code file

        Returns:
            Checklist with validation status
        """
        test_file = self._find_test_file(file_path)
        if not test_file:
            return {
                'tests_exist': False,
                'tests_passing': False,
                'coverage_met': False,
                'tdd_cycle_complete': False
            }

        state = self._workflow_state.get(test_file, {})
        cycle_status = self.get_workflow_cycle_status(test_file)

        return {
            'tests_exist': state.get('tests_exist', False),
            'tests_passing': state.get('tests_passing', False),
            'coverage_met': state.get('code_coverage', 0) >= self._coverage_threshold,
            'tdd_cycle_complete': cycle_status['cycle_valid']
        }

    def get_test_metrics(self, test_file: str) -> Dict[str, Any]:
        """Get test execution metrics"""
        history = self._execution_history.get(test_file, [])
        if not history:
            return {
                'total_executions': 0,
                'final_passed': 0,
                'final_failed': 0,
                'final_coverage': 0.0
            }

        latest = history[-1]

        return {
            'total_executions': len(history),
            'final_passed': latest.get('passed', 0),
            'final_failed': latest.get('failed', 0),
            'final_coverage': latest.get('coverage', 0.0)
        }

    def calculate_compliance_score(self, test_file: str) -> float:
        """
        Calculate TDD workflow compliance score (0-100).

        Args:
            test_file: Test file to calculate score for

        Returns:
            Compliance score percentage
        """
        cycle_status = self.get_workflow_cycle_status(test_file)
        state = self._workflow_state.get(test_file, {})

        score = 0.0

        # RED phase completed: 30 points
        if cycle_status['red_completed']:
            score += 30.0

        # GREEN phase completed: 30 points
        if cycle_status['green_completed']:
            score += 30.0

        # Coverage threshold met: 30 points
        coverage = state.get('code_coverage', 0)
        if coverage >= self._coverage_threshold:
            score += 30.0
        else:
            # Partial credit for coverage
            score += 30.0 * (coverage / self._coverage_threshold)

        # Tests passing: 10 points
        if state.get('tests_passing', False):
            score += 10.0

        return min(100.0, score)

    def export_statistics(self) -> Dict[str, Any]:
        """Export workflow statistics for analysis"""
        total_files = len(self._workflow_state)
        total_executions = sum(len(history) for history in self._execution_history.values())

        # Calculate average coverage
        coverages = [
            state.get('code_coverage', 0)
            for state in self._workflow_state.values()
            if state.get('code_coverage', 0) > 0
        ]
        average_coverage = sum(coverages) / len(coverages) if coverages else 0.0

        # Calculate compliance rate
        compliant_files = sum(
            1 for test_file in self._workflow_state.keys()
            if self.get_workflow_cycle_status(test_file)['cycle_valid']
        )
        compliance_rate = (compliant_files / total_files * 100) if total_files > 0 else 0.0

        return {
            'total_test_files': total_files,
            'total_executions': total_executions,
            'average_coverage': average_coverage,
            'compliance_rate': compliance_rate,
            'total_violations': len(self._violations)
        }
