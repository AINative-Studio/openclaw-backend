"""
Test-Driven Development Workflow Service Tests

Following mandatory TDD: These tests are written FIRST (RED phase)
"""

import pytest
from datetime import datetime
from typing import Dict, Any, List
from enum import Enum


class TestTDDWorkflowService:
    """Test suite for TDD workflow enforcement service"""

    @pytest.fixture
    def tdd_service(self):
        """Create TDD workflow service instance"""
        from backend.services.tdd_workflow_service import TDDWorkflowService
        return TDDWorkflowService()

    class TestWorkflowState:
        """Test workflow state management"""

        def test_initializes_in_red_state(self, tdd_service):
            """Should initialize in RED state (tests must be written first)"""
            from backend.services.tdd_workflow_service import TDDPhase

            state = tdd_service.get_current_state()
            assert state['phase'] == TDDPhase.RED
            assert state['tests_exist'] is False
            assert state['tests_passing'] is False
            assert state['code_coverage'] == 0.0

        def test_tracks_phase_transitions(self, tdd_service):
            """Should track RED -> GREEN -> REFACTOR transitions"""
            from backend.services.tdd_workflow_service import TDDPhase

            # Start in RED
            assert tdd_service.get_current_phase() == TDDPhase.RED

            # Transition to GREEN after tests pass
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=True,
                failed=0,
                coverage=85.0
            )
            assert tdd_service.get_current_phase('test_feature.py') == TDDPhase.GREEN

            # Can transition to REFACTOR
            tdd_service.start_refactor_phase()
            assert tdd_service.get_current_phase() == TDDPhase.REFACTOR

        def test_prevents_code_without_tests(self, tdd_service):
            """Should prevent code commits when no tests exist"""
            from backend.services.tdd_workflow_service import TDDViolationError

            with pytest.raises(TDDViolationError) as exc_info:
                tdd_service.validate_code_commit(
                    file_path='backend/services/new_feature.py',
                    has_tests=False
                )

            assert 'Tests required' in str(exc_info.value)
            assert 'RED phase' in str(exc_info.value)

    class TestREDPhase:
        """Test RED phase (failing tests) enforcement"""

        def test_detects_red_state_from_failing_tests(self, tdd_service):
            """Should detect RED state when tests fail"""
            from backend.services.tdd_workflow_service import TDDPhase

            result = tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )

            assert result['phase'] == TDDPhase.RED
            assert result['is_valid_red_state'] is True
            assert result['tests_exist'] is True
            assert result['tests_passing'] is False

        def test_requires_tests_to_fail_initially(self, tdd_service):
            """Should require tests to fail before implementation"""
            from backend.services.tdd_workflow_service import TDDViolationError

            # Skip RED phase and try to go straight to GREEN
            with pytest.raises(TDDViolationError) as exc_info:
                tdd_service.record_test_execution(
                    test_file='test_feature.py',
                    passed=5,
                    failed=0,
                    coverage=90.0,
                    skip_red_validation=False
                )

            assert 'must fail first' in str(exc_info.value).lower()

        def test_validates_test_file_naming_convention(self, tdd_service):
            """Should validate test file follows naming convention"""
            from backend.services.tdd_workflow_service import TDDViolationError

            # Valid test file names
            valid_names = [
                'test_feature.py',
                'test_tdd_workflow_service.py',
                'tests/test_integration.py'
            ]

            for name in valid_names:
                result = tdd_service.validate_test_file_name(name)
                assert result['is_valid'] is True

            # Invalid test file names
            invalid_names = [
                'feature.py',
                'my_test.py',
                'integration_test.py'
            ]

            for name in invalid_names:
                result = tdd_service.validate_test_file_name(name)
                assert result['is_valid'] is False

        def test_tracks_test_execution_history(self, tdd_service):
            """Should track history of test executions"""
            # Record multiple test runs
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )

            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=3,
                failed=2,
                coverage=45.0
            )

            history = tdd_service.get_execution_history('test_feature.py')
            assert len(history) == 2
            assert history[0]['failed'] == 5
            assert history[1]['passed'] == 3

    class TestGREENPhase:
        """Test GREEN phase (passing tests) enforcement"""

        def test_validates_green_state_when_tests_pass(self, tdd_service):
            """Should validate GREEN state when all tests pass"""
            from backend.services.tdd_workflow_service import TDDPhase

            # First RED phase
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )

            # Then GREEN phase
            result = tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=85.0
            )

            assert result['phase'] == TDDPhase.GREEN
            assert result['is_valid_green_state'] is True
            assert result['tests_passing'] is True

        def test_requires_minimum_coverage_threshold(self, tdd_service):
            """Should require 80%+ coverage in GREEN phase"""
            from backend.services.tdd_workflow_service import TDDViolationError

            # First RED phase
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )

            # Try GREEN with low coverage
            with pytest.raises(TDDViolationError) as exc_info:
                tdd_service.record_test_execution(
                    test_file='test_feature.py',
                    passed=5,
                    failed=0,
                    coverage=65.0,
                    enforce_coverage=True
                )

            assert '80%' in str(exc_info.value)
            assert 'coverage' in str(exc_info.value).lower()

        def test_allows_configurable_coverage_threshold(self, tdd_service):
            """Should allow configurable coverage threshold"""
            from backend.services.tdd_workflow_service import TDDPhase

            # Set custom threshold
            tdd_service.set_coverage_threshold(75.0)

            # First RED phase
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )

            # GREEN with 75%+ coverage should pass
            result = tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=78.0,
                enforce_coverage=True
            )

            assert result['phase'] == TDDPhase.GREEN
            assert result['coverage_met'] is True

        def test_prevents_incomplete_implementations(self, tdd_service):
            """Should prevent commits with failing tests"""
            from backend.services.tdd_workflow_service import TDDViolationError

            # First RED phase
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )

            # Partial implementation (some tests still failing)
            result = tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=3,
                failed=2,
                coverage=60.0
            )

            # Should not allow commit
            with pytest.raises(TDDViolationError) as exc_info:
                tdd_service.validate_code_commit(
                    file_path='backend/services/feature.py',
                    has_tests=True
                )

            assert 'tests must pass' in str(exc_info.value).lower()

    class TestREFACTORPhase:
        """Test REFACTOR phase enforcement"""

        def test_allows_refactor_only_when_tests_green(self, tdd_service):
            """Should only allow refactor when tests are passing"""
            from backend.services.tdd_workflow_service import TDDViolationError

            # Try to refactor before tests pass
            with pytest.raises(TDDViolationError) as exc_info:
                tdd_service.start_refactor_phase()

            assert 'tests must be passing' in str(exc_info.value).lower()

        def test_maintains_green_state_during_refactor(self, tdd_service):
            """Should maintain passing tests during refactor"""
            from backend.services.tdd_workflow_service import TDDPhase, TDDViolationError

            # First RED phase
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )

            # Then GREEN phase
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=85.0
            )

            # Start refactor
            tdd_service.start_refactor_phase()
            assert tdd_service.get_current_phase() == TDDPhase.REFACTOR

            # Tests must still pass during refactor
            with pytest.raises(TDDViolationError) as exc_info:
                tdd_service.record_test_execution(
                    test_file='test_feature.py',
                    passed=3,
                    failed=2,
                    coverage=85.0
                )

            assert 'refactor broke tests' in str(exc_info.value).lower()

        def test_tracks_refactor_iterations(self, tdd_service):
            """Should track multiple refactor iterations"""
            from backend.services.tdd_workflow_service import TDDPhase

            # Setup: RED -> GREEN
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=85.0
            )

            # Refactor iteration 1
            tdd_service.start_refactor_phase()
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=88.0
            )

            # Refactor iteration 2
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=92.0
            )

            stats = tdd_service.get_refactor_statistics('test_feature.py')
            assert stats['refactor_iterations'] >= 2
            assert stats['coverage_improvement'] > 0

    class TestCoverageEnforcement:
        """Test coverage threshold enforcement"""

        def test_calculates_coverage_percentage(self, tdd_service):
            """Should calculate coverage from test results"""
            result = tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=73.5
            )

            assert result['code_coverage'] == 73.5

        def test_enforces_minimum_80_percent_coverage(self, tdd_service):
            """Should enforce 80% minimum coverage by default"""
            threshold = tdd_service.get_coverage_threshold()
            assert threshold == 80.0

        def test_validates_coverage_before_commit(self, tdd_service):
            """Should validate coverage meets threshold before commit"""
            from backend.services.tdd_workflow_service import TDDViolationError

            # Setup GREEN state with low coverage
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=70.0,
                enforce_coverage=False
            )

            # Try to commit
            with pytest.raises(TDDViolationError) as exc_info:
                tdd_service.validate_code_commit(
                    file_path='backend/services/feature.py',
                    has_tests=True,
                    enforce_coverage=True
                )

            assert '80%' in str(exc_info.value)

        def test_reports_coverage_gaps(self, tdd_service):
            """Should report which lines/files lack coverage"""
            from backend.services.tdd_workflow_service import TDDPhase

            # Record execution with coverage details
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=75.0,
                uncovered_lines=[10, 15, 20, 25, 30]
            )

            report = tdd_service.get_coverage_report('test_feature.py')
            assert report['coverage_percentage'] == 75.0
            assert len(report['uncovered_lines']) == 5
            assert report['coverage_gap'] == 5.0  # 80 - 75

    class TestWorkflowValidation:
        """Test overall TDD workflow validation"""

        def test_validates_complete_red_green_refactor_cycle(self, tdd_service):
            """Should validate complete TDD cycle"""
            from backend.services.tdd_workflow_service import TDDPhase

            # RED: Write failing tests
            red_result = tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )
            assert red_result['phase'] == TDDPhase.RED

            # GREEN: Make tests pass
            green_result = tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=85.0
            )
            assert green_result['phase'] == TDDPhase.GREEN

            # REFACTOR: Improve code
            tdd_service.start_refactor_phase()
            refactor_result = tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=90.0
            )
            assert refactor_result['phase'] == TDDPhase.REFACTOR

            # Validate complete cycle
            cycle = tdd_service.get_workflow_cycle_status('test_feature.py')
            assert cycle['red_completed'] is True
            assert cycle['green_completed'] is True
            assert cycle['refactor_completed'] is True
            assert cycle['cycle_valid'] is True

        def test_generates_workflow_report(self, tdd_service):
            """Should generate comprehensive workflow report"""
            # Execute RED -> GREEN cycle
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=85.0
            )

            report = tdd_service.generate_workflow_report('test_feature.py')

            assert 'test_file' in report
            assert 'total_executions' in report
            assert 'current_phase' in report
            assert 'coverage_history' in report
            assert 'cycle_compliance' in report
            assert report['total_executions'] == 2

        def test_detects_tdd_violations(self, tdd_service):
            """Should detect and report TDD workflow violations"""
            violations = tdd_service.detect_violations()

            # Initially no violations
            assert len(violations) == 0

            # Try to commit code without tests (violation)
            try:
                tdd_service.validate_code_commit(
                    file_path='backend/services/feature.py',
                    has_tests=False
                )
            except Exception:
                pass

            violations = tdd_service.detect_violations()
            assert len(violations) > 0
            assert any('tests required' in v.lower() for v in violations)

    class TestPreCommitValidation:
        """Test pre-commit validation hooks"""

        def test_validates_commit_readiness(self, tdd_service):
            """Should validate if code is ready to commit"""
            from backend.services.tdd_workflow_service import TDDPhase

            # Not ready: No tests
            ready = tdd_service.is_ready_to_commit('backend/services/feature.py')
            assert ready is False

            # Setup GREEN state
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=85.0
            )

            # Now ready
            ready = tdd_service.is_ready_to_commit('backend/services/feature.py')
            assert ready is True

        def test_blocks_commits_with_failing_tests(self, tdd_service):
            """Should block commits when tests are failing"""
            from backend.services.tdd_workflow_service import TDDViolationError

            # RED phase with failing tests
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=2,
                failed=3,
                coverage=50.0
            )

            with pytest.raises(TDDViolationError) as exc_info:
                tdd_service.validate_code_commit(
                    file_path='backend/services/feature.py',
                    has_tests=True
                )

            assert 'failing tests' in str(exc_info.value).lower()

        def test_generates_pre_commit_checklist(self, tdd_service):
            """Should generate pre-commit validation checklist"""
            from backend.services.tdd_workflow_service import TDDPhase

            # Setup GREEN state
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=85.0
            )

            checklist = tdd_service.get_pre_commit_checklist('backend/services/feature.py')

            assert 'tests_exist' in checklist
            assert 'tests_passing' in checklist
            assert 'coverage_met' in checklist
            assert 'tdd_cycle_complete' in checklist

            assert checklist['tests_exist'] is True
            assert checklist['tests_passing'] is True
            assert checklist['coverage_met'] is True

    class TestMetricsAndReporting:
        """Test metrics collection and reporting"""

        def test_tracks_test_execution_metrics(self, tdd_service):
            """Should track test execution metrics over time"""
            # Record multiple executions
            for i in range(5):
                tdd_service.record_test_execution(
                    test_file='test_feature.py',
                    passed=i + 1,
                    failed=5 - i,
                    coverage=(i + 1) * 20.0
                )

            metrics = tdd_service.get_test_metrics('test_feature.py')
            assert metrics['total_executions'] == 5
            assert metrics['final_passed'] == 5
            assert metrics['final_coverage'] == 100.0

        def test_calculates_workflow_compliance_score(self, tdd_service):
            """Should calculate TDD workflow compliance score"""
            # Perfect TDD cycle
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=90.0
            )

            score = tdd_service.calculate_compliance_score('test_feature.py')
            assert score >= 95.0  # High score for proper TDD cycle

        def test_exports_workflow_statistics(self, tdd_service):
            """Should export workflow statistics for analysis"""
            # Setup workflow
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=0,
                failed=5,
                coverage=0.0
            )
            tdd_service.record_test_execution(
                test_file='test_feature.py',
                passed=5,
                failed=0,
                coverage=85.0
            )

            stats = tdd_service.export_statistics()

            assert 'total_test_files' in stats
            assert 'total_executions' in stats
            assert 'average_coverage' in stats
            assert 'compliance_rate' in stats


class TestTDDPhaseEnum:
    """Test TDD phase enumeration"""

    def test_defines_three_phases(self):
        """Should define RED, GREEN, REFACTOR phases"""
        from backend.services.tdd_workflow_service import TDDPhase

        assert hasattr(TDDPhase, 'RED')
        assert hasattr(TDDPhase, 'GREEN')
        assert hasattr(TDDPhase, 'REFACTOR')

    def test_provides_phase_descriptions(self):
        """Should provide description for each phase"""
        from backend.services.tdd_workflow_service import TDDPhase

        red_desc = TDDPhase.RED.description()
        green_desc = TDDPhase.GREEN.description()
        refactor_desc = TDDPhase.REFACTOR.description()

        assert 'fail' in red_desc.lower()
        assert 'pass' in green_desc.lower()
        assert 'improve' in refactor_desc.lower()


class TestTDDViolationError:
    """Test TDD violation exception"""

    def test_raises_custom_exception(self):
        """Should raise custom TDDViolationError exception"""
        from backend.services.tdd_workflow_service import TDDViolationError

        with pytest.raises(TDDViolationError) as exc_info:
            raise TDDViolationError("Test violation message")

        assert "Test violation message" in str(exc_info.value)

    def test_includes_violation_context(self):
        """Should include context about the violation"""
        from backend.services.tdd_workflow_service import TDDViolationError

        with pytest.raises(TDDViolationError) as exc_info:
            raise TDDViolationError(
                message="Tests required before code",
                phase="RED",
                file_path="backend/services/feature.py"
            )

        error = exc_info.value
        assert hasattr(error, 'phase')
        assert hasattr(error, 'file_path')
        assert error.phase == "RED"
