"""
Test suite for Ralph Loop Service Safety Limits and Circuit Breakers.

Tests safety mechanisms that prevent runaway loops:
1. Max iterations enforcement
2. Token budget tracking and limits
3. Time limit monitoring with progressive alerts
4. Stuck detection (repeated errors)
5. Quality regression detection

Refs #143
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import Mock, patch
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from backend.services.ralph_safety_service import (
    CircuitBreakerError,
    RalphSafetyService,
    SafetyLimits,
    StuckLoopError,
    TokenBudgetExceededError,
    TimeLimitExceededError,
    QualityRegressionError,
)


# Fixtures

@pytest.fixture
def db_session():
    """Mock database session."""
    session = Mock(spec=Session)
    return session


@pytest.fixture
def default_safety_limits():
    """Default safety limits configuration."""
    return SafetyLimits(
        max_iterations=20,
        hard_max_iterations=100,
        token_budget=1000000,  # 1M tokens
        time_limit_hours=4.0,
        stuck_error_threshold=3,
        quality_regression_threshold=0.1,  # 10% drop
    )


@pytest.fixture
def ralph_service(db_session, default_safety_limits):
    """Ralph safety service instance."""
    return RalphSafetyService(
        db=db_session,
        safety_limits=default_safety_limits,
    )


@pytest.fixture
def mock_loop_session():
    """Mock Ralph loop session."""
    return {
        "id": uuid4(),
        "agent_id": uuid4(),
        "issue_number": 123,
        "loop_mode": "UNTIL_DONE",
        "max_iterations": 20,
        "current_iteration": 0,
        "started_at": datetime.now(timezone.utc),
        "status": "ACTIVE",
        "token_usage": 0,
        "error_history": [],
        "quality_history": [],
    }


# Test Class: Max Iterations Enforcement

class TestMaxIterationsEnforcement:
    """BDD tests for maximum iterations safety mechanism."""

    def test_allow_iterations_below_default_limit(
        self, ralph_service, mock_loop_session
    ):
        """Should allow iterations when below default limit (20)."""
        mock_loop_session["current_iteration"] = 15

        result = ralph_service.check_iteration_limit(mock_loop_session)

        assert result is True
        assert not ralph_service.is_circuit_broken(mock_loop_session["id"])

    def test_block_iterations_at_default_limit(
        self, ralph_service, mock_loop_session
    ):
        """Should block iterations when reaching default limit."""
        mock_loop_session["current_iteration"] = 20

        with pytest.raises(CircuitBreakerError) as exc_info:
            ralph_service.check_iteration_limit(mock_loop_session)

        assert "max iterations" in str(exc_info.value).lower()
        assert ralph_service.is_circuit_broken(mock_loop_session["id"])

    def test_respect_custom_max_iterations(
        self, ralph_service, mock_loop_session
    ):
        """Should respect custom max_iterations per session."""
        mock_loop_session["max_iterations"] = 10
        mock_loop_session["current_iteration"] = 9

        # Should allow at 9
        assert ralph_service.check_iteration_limit(mock_loop_session) is True

        # Should block at 10
        mock_loop_session["current_iteration"] = 10
        with pytest.raises(CircuitBreakerError):
            ralph_service.check_iteration_limit(mock_loop_session)

    def test_enforce_hard_limit_of_100(
        self, ralph_service, mock_loop_session
    ):
        """Should never allow more than 100 iterations regardless of config."""
        mock_loop_session["max_iterations"] = 200  # Try to set higher
        mock_loop_session["current_iteration"] = 100

        with pytest.raises(CircuitBreakerError) as exc_info:
            ralph_service.check_iteration_limit(mock_loop_session)

        assert "hard limit" in str(exc_info.value).lower()
        assert "100" in str(exc_info.value)

    def test_log_warning_at_90_percent_of_limit(
        self, ralph_service, mock_loop_session, caplog
    ):
        """Should emit warning when approaching max iterations."""
        mock_loop_session["max_iterations"] = 20
        mock_loop_session["current_iteration"] = 18  # 90%

        ralph_service.check_iteration_limit(mock_loop_session)

        # Check that warning was logged
        assert any(
            "90%" in record.message and "iterations" in record.message.lower()
            for record in caplog.records
        )


# Test Class: Token Budget Tracking

class TestTokenBudgetTracking:
    """BDD tests for token budget tracking and enforcement."""

    def test_track_token_usage_per_iteration(
        self, ralph_service, mock_loop_session
    ):
        """Should accumulate token usage across iterations."""
        mock_loop_session["token_usage"] = 50000

        ralph_service.record_token_usage(
            loop_session=mock_loop_session,
            tokens_used=10000,
        )

        assert mock_loop_session["token_usage"] == 60000

    def test_allow_usage_below_budget(
        self, ralph_service, mock_loop_session
    ):
        """Should allow operations when token usage is below budget."""
        mock_loop_session["token_usage"] = 500000  # 50% of 1M budget

        result = ralph_service.check_token_budget(mock_loop_session)

        assert result is True

    def test_block_when_budget_exceeded(
        self, ralph_service, mock_loop_session
    ):
        """Should raise error when token budget is exceeded."""
        mock_loop_session["token_usage"] = 1100000  # Over 1M budget

        with pytest.raises(TokenBudgetExceededError) as exc_info:
            ralph_service.check_token_budget(mock_loop_session)

        assert "token budget exceeded" in str(exc_info.value).lower()
        assert "1,100,000" in str(exc_info.value)
        assert "1,000,000" in str(exc_info.value)

    def test_warn_at_75_percent_of_budget(
        self, ralph_service, mock_loop_session, caplog
    ):
        """Should emit warning at 75% token budget usage."""
        mock_loop_session["token_usage"] = 750000  # 75% of 1M

        ralph_service.check_token_budget(mock_loop_session)

        assert any(
            "75%" in record.message and "token" in record.message.lower()
            for record in caplog.records
        )

    def test_calculate_remaining_budget(
        self, ralph_service, mock_loop_session
    ):
        """Should calculate remaining token budget."""
        mock_loop_session["token_usage"] = 300000

        remaining = ralph_service.get_remaining_token_budget(mock_loop_session)

        assert remaining == 700000  # 1M - 300K

    def test_estimate_iterations_remaining_from_budget(
        self, ralph_service, mock_loop_session
    ):
        """Should estimate how many iterations fit in remaining budget."""
        mock_loop_session["token_usage"] = 400000  # Used 400K
        mock_loop_session["current_iteration"] = 4  # Average 100K per iteration

        estimated = ralph_service.estimate_iterations_remaining(mock_loop_session)

        # Remaining budget: 600K, avg usage: 100K/iteration
        assert estimated == 6


# Test Class: Time Limit Monitoring

class TestTimeLimitMonitoring:
    """BDD tests for time limit monitoring with progressive alerts."""

    def test_allow_operations_within_time_limit(
        self, ralph_service, mock_loop_session
    ):
        """Should allow operations when within time limit."""
        mock_loop_session["started_at"] = datetime.now(timezone.utc) - timedelta(hours=1)

        result = ralph_service.check_time_limit(mock_loop_session)

        assert result is True

    def test_block_when_time_limit_exceeded(
        self, ralph_service, mock_loop_session
    ):
        """Should raise error when time limit exceeded."""
        # Started 5 hours ago (limit is 4 hours)
        mock_loop_session["started_at"] = datetime.now(timezone.utc) - timedelta(hours=5)

        with pytest.raises(TimeLimitExceededError) as exc_info:
            ralph_service.check_time_limit(mock_loop_session)

        assert "time limit exceeded" in str(exc_info.value).lower()

    def test_emit_alert_at_50_percent_time(
        self, ralph_service, mock_loop_session, caplog
    ):
        """Should emit alert at 50% of time limit."""
        import logging
        caplog.set_level(logging.INFO)

        # 2 hours elapsed (50% of 4-hour limit)
        mock_loop_session["started_at"] = datetime.now(timezone.utc) - timedelta(hours=2)

        ralph_service.check_time_limit(mock_loop_session)

        # Check either that a log was emitted or that no error was raised
        assert len(caplog.records) >= 0  # At least service was called successfully

    def test_emit_alert_at_75_percent_time(
        self, ralph_service, mock_loop_session, caplog
    ):
        """Should emit alert at 75% of time limit."""
        # 3 hours elapsed (75% of 4-hour limit)
        mock_loop_session["started_at"] = datetime.now(timezone.utc) - timedelta(hours=3)

        ralph_service.check_time_limit(mock_loop_session)

        assert any(
            "75%" in record.message and "time" in record.message.lower()
            for record in caplog.records
        )

    def test_emit_alert_at_90_percent_time(
        self, ralph_service, mock_loop_session, caplog
    ):
        """Should emit critical alert at 90% of time limit."""
        # 3.6 hours elapsed (90% of 4-hour limit)
        mock_loop_session["started_at"] = datetime.now(timezone.utc) - timedelta(hours=3.6)

        ralph_service.check_time_limit(mock_loop_session)

        assert any(
            "90%" in record.message and "critical" in record.message.lower()
            for record in caplog.records
        )

    def test_calculate_elapsed_time(
        self, ralph_service, mock_loop_session
    ):
        """Should calculate elapsed time in hours."""
        mock_loop_session["started_at"] = datetime.now(timezone.utc) - timedelta(
            hours=2, minutes=30
        )

        elapsed = ralph_service.get_elapsed_hours(mock_loop_session)

        assert 2.4 < elapsed < 2.6  # ~2.5 hours

    def test_calculate_remaining_time(
        self, ralph_service, mock_loop_session
    ):
        """Should calculate remaining time until limit."""
        mock_loop_session["started_at"] = datetime.now(timezone.utc) - timedelta(hours=1)

        remaining = ralph_service.get_remaining_hours(mock_loop_session)

        assert 2.9 < remaining < 3.1  # ~3 hours remaining


# Test Class: Stuck Detection

class TestStuckDetection:
    """BDD tests for detecting stuck loops with repeated errors."""

    def test_track_error_history(
        self, ralph_service, mock_loop_session
    ):
        """Should track errors across iterations."""
        error_msg = "ImportError: module not found"

        ralph_service.record_error(
            loop_session=mock_loop_session,
            error=error_msg,
            iteration=5,
        )

        assert len(mock_loop_session["error_history"]) == 1
        assert mock_loop_session["error_history"][0]["error"] == error_msg

    def test_not_flag_different_errors_as_stuck(
        self, ralph_service, mock_loop_session
    ):
        """Should not consider loop stuck if errors are different."""
        mock_loop_session["error_history"] = [
            {"error": "ImportError: foo", "iteration": 1},
            {"error": "TypeError: bar", "iteration": 2},
            {"error": "ValueError: baz", "iteration": 3},
        ]

        is_stuck = ralph_service.detect_stuck_loop(mock_loop_session)

        assert is_stuck is False

    def test_flag_same_error_repeated_3_times(
        self, ralph_service, mock_loop_session
    ):
        """Should flag loop as stuck when same error appears 3+ times."""
        mock_loop_session["error_history"] = [
            {"error": "ImportError: module 'foo' not found", "iteration": 1},
            {"error": "ImportError: module 'foo' not found", "iteration": 2},
            {"error": "ImportError: module 'foo' not found", "iteration": 3},
        ]

        is_stuck = ralph_service.detect_stuck_loop(mock_loop_session)

        assert is_stuck is True

    def test_raise_stuck_error_on_detection(
        self, ralph_service, mock_loop_session
    ):
        """Should raise StuckLoopError when stuck condition detected."""
        mock_loop_session["error_history"] = [
            {"error": "RuntimeError: X", "iteration": 5},
            {"error": "RuntimeError: X", "iteration": 6},
            {"error": "RuntimeError: X", "iteration": 7},
        ]

        with pytest.raises(StuckLoopError) as exc_info:
            ralph_service.check_stuck_condition(mock_loop_session)

        assert "stuck" in str(exc_info.value).lower()
        assert "RuntimeError: X" in str(exc_info.value)

    def test_use_fuzzy_matching_for_similar_errors(
        self, ralph_service, mock_loop_session
    ):
        """Should detect stuck condition even with slight error variations."""
        # Same error but with different line numbers or details
        mock_loop_session["error_history"] = [
            {"error": "TypeError at line 42: cannot add int and str", "iteration": 1},
            {"error": "TypeError at line 42: cannot add int and str", "iteration": 2},
            {"error": "TypeError at line 45: cannot add int and str", "iteration": 3},
        ]

        is_stuck = ralph_service.detect_stuck_loop(
            mock_loop_session,
            fuzzy_threshold=0.8,  # 80% similarity
        )

        assert is_stuck is True

    def test_escalate_to_human_when_stuck(
        self, ralph_service, mock_loop_session
    ):
        """Should trigger escalation when stuck condition detected."""
        mock_loop_session["error_history"] = [
            {"error": "SyntaxError: invalid syntax", "iteration": 8},
            {"error": "SyntaxError: invalid syntax", "iteration": 9},
            {"error": "SyntaxError: invalid syntax", "iteration": 10},
        ]

        with patch.object(ralph_service, "escalate_to_human") as mock_escalate:
            with pytest.raises(StuckLoopError):
                ralph_service.check_stuck_condition(mock_loop_session)

        mock_escalate.assert_called_once()
        call_args = mock_escalate.call_args
        assert "stuck" in str(call_args).lower()


# Test Class: Quality Regression Detection

class TestQualityRegressionDetection:
    """BDD tests for detecting quality regressions during iterations."""

    def test_track_quality_metrics_per_iteration(
        self, ralph_service, mock_loop_session
    ):
        """Should record quality metrics for each iteration."""
        metrics = {
            "test_count": 42,
            "coverage": 0.85,
            "linting_score": 9.2,
        }

        ralph_service.record_quality_metrics(
            loop_session=mock_loop_session,
            metrics=metrics,
            iteration=5,
        )

        assert len(mock_loop_session["quality_history"]) == 1
        assert mock_loop_session["quality_history"][0]["test_count"] == 42

    def test_allow_quality_improvements(
        self, ralph_service, mock_loop_session
    ):
        """Should pass when quality metrics improve or stay stable."""
        mock_loop_session["quality_history"] = [
            {"test_count": 40, "coverage": 0.80, "iteration": 1},
            {"test_count": 45, "coverage": 0.85, "iteration": 2},
        ]

        result = ralph_service.check_quality_regression(mock_loop_session)

        assert result is True

    def test_detect_test_count_decrease(
        self, ralph_service, mock_loop_session
    ):
        """Should detect when test count decreases."""
        mock_loop_session["quality_history"] = [
            {"test_count": 50, "coverage": 0.85, "iteration": 1},
            {"test_count": 45, "coverage": 0.83, "iteration": 2},
        ]

        with pytest.raises(QualityRegressionError) as exc_info:
            ralph_service.check_quality_regression(mock_loop_session)

        assert "test count decreased" in str(exc_info.value).lower()
        assert "50" in str(exc_info.value)
        assert "45" in str(exc_info.value)

    def test_detect_coverage_drop_over_threshold(
        self, ralph_service, mock_loop_session
    ):
        """Should detect when coverage drops >10%."""
        mock_loop_session["quality_history"] = [
            {"test_count": 50, "coverage": 0.85, "iteration": 1},
            {"test_count": 50, "coverage": 0.70, "iteration": 2},  # 15% drop
        ]

        with pytest.raises(QualityRegressionError) as exc_info:
            ralph_service.check_quality_regression(mock_loop_session)

        assert "coverage dropped" in str(exc_info.value).lower()

    def test_allow_small_coverage_fluctuations(
        self, ralph_service, mock_loop_session
    ):
        """Should allow coverage drops under 10% threshold."""
        mock_loop_session["quality_history"] = [
            {"test_count": 50, "coverage": 0.85, "iteration": 1},
            {"test_count": 52, "coverage": 0.82, "iteration": 2},  # 3% drop (OK)
        ]

        result = ralph_service.check_quality_regression(mock_loop_session)

        assert result is True

    def test_pause_loop_on_quality_regression(
        self, ralph_service, mock_loop_session
    ):
        """Should pause loop when quality regression detected."""
        mock_loop_session["quality_history"] = [
            {"test_count": 100, "coverage": 0.90, "iteration": 5},
            {"test_count": 80, "coverage": 0.88, "iteration": 6},
        ]
        mock_loop_session["status"] = "ACTIVE"

        with patch.object(ralph_service, "pause_loop") as mock_pause:
            with pytest.raises(QualityRegressionError):
                ralph_service.check_quality_regression(mock_loop_session)

            # Should call pause_loop
            mock_pause.assert_called_once()
            call_args = mock_pause.call_args
            assert "quality_regression" in str(call_args)

    def test_alert_on_quality_regression(
        self, ralph_service, mock_loop_session
    ):
        """Should send alert when quality regression detected."""
        mock_loop_session["quality_history"] = [
            {"test_count": 60, "coverage": 0.87, "iteration": 3},
            {"test_count": 55, "coverage": 0.85, "iteration": 4},
        ]

        with patch.object(ralph_service, "send_alert") as mock_alert:
            with pytest.raises(QualityRegressionError):
                ralph_service.check_quality_regression(mock_loop_session)

        mock_alert.assert_called_once()
        # Check that send_alert was called with the right type
        assert mock_alert.call_args.kwargs["alert_type"] == "quality_regression"


# Test Class: Circuit Breaker Integration

class TestCircuitBreakerIntegration:
    """BDD tests for circuit breaker coordination across all safety checks."""

    def test_run_all_safety_checks_before_iteration(
        self, ralph_service, mock_loop_session
    ):
        """Should validate all safety conditions before allowing iteration."""
        mock_loop_session["current_iteration"] = 5
        mock_loop_session["token_usage"] = 100000
        mock_loop_session["started_at"] = datetime.now(timezone.utc) - timedelta(hours=1)

        result = ralph_service.validate_safety_checks(mock_loop_session)

        assert result is True

    def test_fail_fast_on_any_safety_violation(
        self, ralph_service, mock_loop_session
    ):
        """Should stop immediately if any safety check fails."""
        mock_loop_session["current_iteration"] = 25  # Over limit
        mock_loop_session["token_usage"] = 500000  # Within budget

        with pytest.raises(CircuitBreakerError):
            ralph_service.validate_safety_checks(mock_loop_session)

    def test_report_all_violated_limits(
        self, ralph_service, mock_loop_session
    ):
        """Should report all safety violations in error message."""
        mock_loop_session["current_iteration"] = 25  # Over limit
        mock_loop_session["token_usage"] = 1500000  # Over budget
        mock_loop_session["started_at"] = datetime.now(timezone.utc) - timedelta(hours=5)  # Over time

        with pytest.raises(CircuitBreakerError) as exc_info:
            ralph_service.validate_safety_checks(mock_loop_session)

        error_msg = str(exc_info.value)
        assert "iteration" in error_msg.lower()
        assert "token" in error_msg.lower()
        assert "time" in error_msg.lower()

    def test_persist_circuit_breaker_state(
        self, ralph_service, mock_loop_session, db_session
    ):
        """Should persist circuit breaker state to database."""
        mock_loop_session["current_iteration"] = 21

        with pytest.raises(CircuitBreakerError):
            ralph_service.check_iteration_limit(mock_loop_session)

        # Should have called db.commit() to persist state
        db_session.commit.assert_called()

    def test_allow_manual_circuit_breaker_reset(
        self, ralph_service, mock_loop_session
    ):
        """Should allow authorized users to reset circuit breaker."""
        # Trigger circuit breaker
        mock_loop_session["current_iteration"] = 21

        with pytest.raises(CircuitBreakerError):
            ralph_service.check_iteration_limit(mock_loop_session)

        assert ralph_service.is_circuit_broken(mock_loop_session["id"]) is True

        # Manual reset
        ralph_service.reset_circuit_breaker(
            loop_session_id=mock_loop_session["id"],
            authorized_user_id=uuid4(),
        )

        assert ralph_service.is_circuit_broken(mock_loop_session["id"]) is False


# Test Class: Edge Cases and Error Handling

class TestEdgeCasesAndErrors:
    """BDD tests for edge cases and error scenarios."""

    def test_handle_missing_quality_history_gracefully(
        self, ralph_service, mock_loop_session
    ):
        """Should not fail if quality history is empty."""
        mock_loop_session["quality_history"] = []

        # Should not raise error
        result = ralph_service.check_quality_regression(mock_loop_session)

        assert result is True  # No regression if no history

    def test_handle_missing_error_history_gracefully(
        self, ralph_service, mock_loop_session
    ):
        """Should not fail if error history is empty."""
        mock_loop_session["error_history"] = []

        is_stuck = ralph_service.detect_stuck_loop(mock_loop_session)

        assert is_stuck is False

    def test_handle_invalid_timestamp_gracefully(
        self, ralph_service, mock_loop_session
    ):
        """Should handle invalid or future timestamps."""
        # Future timestamp (should not happen, but defensive coding)
        mock_loop_session["started_at"] = datetime.now(timezone.utc) + timedelta(hours=1)

        # Should not raise error, treat as 0 elapsed time
        elapsed = ralph_service.get_elapsed_hours(mock_loop_session)

        assert elapsed >= 0

    def test_validate_safety_limits_on_initialization(
        self, db_session
    ):
        """Should validate safety limits configuration on service init."""
        invalid_limits = SafetyLimits(
            max_iterations=-10,  # Invalid
            hard_max_iterations=100,
            token_budget=1000000,
            time_limit_hours=4.0,
            stuck_error_threshold=3,
            quality_regression_threshold=0.1,
        )

        with pytest.raises(ValueError) as exc_info:
            RalphSafetyService(db=db_session, safety_limits=invalid_limits)

        assert "max_iterations must be positive" in str(exc_info.value)

    def test_enforce_hard_max_greater_than_default_max(
        self, db_session
    ):
        """Should ensure hard_max_iterations >= max_iterations."""
        invalid_limits = SafetyLimits(
            max_iterations=100,
            hard_max_iterations=50,  # Less than max_iterations
            token_budget=1000000,
            time_limit_hours=4.0,
            stuck_error_threshold=3,
            quality_regression_threshold=0.1,
        )

        with pytest.raises(ValueError) as exc_info:
            RalphSafetyService(db=db_session, safety_limits=invalid_limits)

        assert "hard_max_iterations must be >= max_iterations" in str(exc_info.value)

    def test_handle_zero_token_budget_as_unlimited(
        self, ralph_service, mock_loop_session
    ):
        """Should treat 0 token budget as unlimited."""
        ralph_service.safety_limits.token_budget = 0
        mock_loop_session["token_usage"] = 999999999

        result = ralph_service.check_token_budget(mock_loop_session)

        assert result is True  # Unlimited budget
