"""
Ralph Safety Service - Circuit Breakers and Safety Limits

Implements safety mechanisms to prevent runaway autonomous loops:
- Max iterations enforcement (default 20, hard limit 100)
- Token budget tracking and limits
- Time limit monitoring with progressive alerts (50%, 75%, 90%)
- Stuck detection (same error 3+ times triggers pause)
- Quality regression detection (test count decrease or coverage drop)

Refs #143
"""

import logging
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from difflib import SequenceMatcher
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Custom Exceptions

class CircuitBreakerError(Exception):
    """Base exception for circuit breaker violations."""
    pass


class TokenBudgetExceededError(CircuitBreakerError):
    """Raised when token budget is exceeded."""
    pass


class TimeLimitExceededError(CircuitBreakerError):
    """Raised when time limit is exceeded."""
    pass


class StuckLoopError(CircuitBreakerError):
    """Raised when loop is detected as stuck with repeated errors."""
    pass


class QualityRegressionError(CircuitBreakerError):
    """Raised when quality metrics regress significantly."""
    pass


# Data Model

@dataclass
class SafetyLimits:
    """Configuration for safety limits and thresholds."""
    max_iterations: int = 20
    hard_max_iterations: int = 100
    token_budget: int = 1_000_000  # 1M tokens, 0 = unlimited
    time_limit_hours: float = 4.0
    stuck_error_threshold: int = 3
    quality_regression_threshold: float = 0.1  # 10% drop


# Service Implementation

class RalphSafetyService:
    """
    Service for enforcing safety limits on Ralph autonomous loops.

    Responsibilities:
    - Enforce iteration limits
    - Track and limit token usage
    - Monitor time limits with progressive alerts
    - Detect stuck loops with repeated errors
    - Detect quality regressions
    - Coordinate circuit breakers
    """

    def __init__(
        self,
        db: Optional[Session] = None,
        safety_limits: Optional[SafetyLimits] = None,
    ):
        """
        Initialize Ralph Safety Service.

        Args:
            db: Database session (optional, for persistence)
            safety_limits: Safety configuration (uses defaults if None)

        Raises:
            ValueError: If safety limits configuration is invalid
        """
        self.db = db
        self.safety_limits = safety_limits or SafetyLimits()

        # Validate configuration
        self._validate_safety_limits()

        # Circuit breaker state (in-memory, should be persisted in production)
        self._circuit_breakers: Dict[UUID, bool] = {}

        logger.info(
            f"RalphSafetyService initialized with limits: "
            f"max_iterations={self.safety_limits.max_iterations}, "
            f"hard_max={self.safety_limits.hard_max_iterations}, "
            f"token_budget={self.safety_limits.token_budget:,}, "
            f"time_limit={self.safety_limits.time_limit_hours}h"
        )

    def _validate_safety_limits(self) -> None:
        """
        Validate safety limits configuration.

        Raises:
            ValueError: If configuration is invalid
        """
        if self.safety_limits.max_iterations <= 0:
            raise ValueError("max_iterations must be positive")

        if self.safety_limits.hard_max_iterations < self.safety_limits.max_iterations:
            raise ValueError(
                "hard_max_iterations must be >= max_iterations"
            )

        if self.safety_limits.time_limit_hours <= 0:
            raise ValueError("time_limit_hours must be positive")

        if self.safety_limits.stuck_error_threshold <= 0:
            raise ValueError("stuck_error_threshold must be positive")

        if not 0 <= self.safety_limits.quality_regression_threshold <= 1:
            raise ValueError(
                "quality_regression_threshold must be between 0 and 1"
            )

    # Max Iterations Enforcement

    def check_iteration_limit(self, loop_session: Dict) -> bool:
        """
        Check if iteration limit has been reached.

        Args:
            loop_session: Ralph loop session data

        Returns:
            True if within limits

        Raises:
            CircuitBreakerError: If iteration limit exceeded
        """
        current = loop_session.get("current_iteration", 0)
        max_iter = min(
            loop_session.get("max_iterations", self.safety_limits.max_iterations),
            self.safety_limits.hard_max_iterations,
        )

        # Check hard limit first
        if current >= self.safety_limits.hard_max_iterations:
            self._trigger_circuit_breaker(loop_session["id"])
            raise CircuitBreakerError(
                f"Hard limit of {self.safety_limits.hard_max_iterations} iterations exceeded"
            )

        # Check configured limit
        if current >= max_iter:
            self._trigger_circuit_breaker(loop_session["id"])
            raise CircuitBreakerError(
                f"Max iterations limit reached: {current}/{max_iter}"
            )

        # Emit warning at 90%
        if current >= max_iter * 0.9:
            logger.warning(
                f"Loop {loop_session['id']} at 90% of max iterations "
                f"({current}/{max_iter})"
            )

        return True

    # Token Budget Tracking

    def record_token_usage(
        self,
        loop_session: Dict,
        tokens_used: int,
    ) -> None:
        """
        Record token usage for an iteration.

        Args:
            loop_session: Ralph loop session data
            tokens_used: Number of tokens consumed
        """
        loop_session["token_usage"] = loop_session.get("token_usage", 0) + tokens_used

        logger.debug(
            f"Loop {loop_session['id']}: Added {tokens_used:,} tokens, "
            f"total: {loop_session['token_usage']:,}"
        )

    def check_token_budget(self, loop_session: Dict) -> bool:
        """
        Check if token budget has been exceeded.

        Args:
            loop_session: Ralph loop session data

        Returns:
            True if within budget

        Raises:
            TokenBudgetExceededError: If budget exceeded
        """
        # 0 budget means unlimited
        if self.safety_limits.token_budget == 0:
            return True

        usage = loop_session.get("token_usage", 0)
        budget = self.safety_limits.token_budget

        # Check if exceeded
        if usage > budget:
            self._trigger_circuit_breaker(loop_session["id"])
            raise TokenBudgetExceededError(
                f"Token budget exceeded: {usage:,} > {budget:,} tokens"
            )

        # Emit warning at 75%
        usage_percent = (usage / budget) * 100
        if usage_percent >= 75:
            logger.warning(
                f"Loop {loop_session['id']} at {usage_percent:.0f}% of token budget "
                f"({usage:,}/{budget:,})"
            )

        return True

    def get_remaining_token_budget(self, loop_session: Dict) -> int:
        """
        Calculate remaining token budget.

        Args:
            loop_session: Ralph loop session data

        Returns:
            Remaining tokens (0 if budget is 0/unlimited)
        """
        if self.safety_limits.token_budget == 0:
            return 0  # Unlimited

        usage = loop_session.get("token_usage", 0)
        return max(0, self.safety_limits.token_budget - usage)

    def estimate_iterations_remaining(self, loop_session: Dict) -> int:
        """
        Estimate iterations remaining based on token budget.

        Args:
            loop_session: Ralph loop session data

        Returns:
            Estimated iterations remaining (999 if unlimited budget)
        """
        if self.safety_limits.token_budget == 0:
            return 999  # Unlimited

        usage = loop_session.get("token_usage", 0)
        iteration = loop_session.get("current_iteration", 0)

        if iteration == 0:
            return 999  # Can't estimate without data

        avg_tokens_per_iteration = usage / iteration
        remaining_budget = self.get_remaining_token_budget(loop_session)

        if avg_tokens_per_iteration == 0:
            return 999

        return int(remaining_budget / avg_tokens_per_iteration)

    # Time Limit Monitoring

    def check_time_limit(self, loop_session: Dict) -> bool:
        """
        Check if time limit has been exceeded and emit progressive alerts.

        Args:
            loop_session: Ralph loop session data

        Returns:
            True if within time limit

        Raises:
            TimeLimitExceededError: If time limit exceeded
        """
        elapsed = self.get_elapsed_hours(loop_session)
        limit = self.safety_limits.time_limit_hours

        # Check if exceeded
        if elapsed > limit:
            self._trigger_circuit_breaker(loop_session["id"])
            raise TimeLimitExceededError(
                f"Time limit exceeded: {elapsed:.1f}h > {limit:.1f}h"
            )

        # Progressive alerts
        percent = (elapsed / limit) * 100

        if percent >= 90:
            logger.critical(
                f"Loop {loop_session['id']} at 90% of time limit "
                f"({elapsed:.1f}h / {limit:.1f}h) - CRITICAL"
            )
        elif percent >= 75:
            logger.warning(
                f"Loop {loop_session['id']} at 75% of time limit "
                f"({elapsed:.1f}h / {limit:.1f}h)"
            )
        elif percent >= 50:
            logger.info(
                f"Loop {loop_session['id']} at 50% of time limit "
                f"({elapsed:.1f}h / {limit:.1f}h)"
            )

        return True

    def get_elapsed_hours(self, loop_session: Dict) -> float:
        """
        Calculate elapsed time since loop started.

        Args:
            loop_session: Ralph loop session data

        Returns:
            Elapsed time in hours
        """
        started_at = loop_session.get("started_at")
        if not started_at:
            return 0.0

        now = datetime.now(timezone.utc)

        # Handle future timestamps (defensive)
        if started_at > now:
            return 0.0

        elapsed = now - started_at
        return elapsed.total_seconds() / 3600

    def get_remaining_hours(self, loop_session: Dict) -> float:
        """
        Calculate remaining time until limit.

        Args:
            loop_session: Ralph loop session data

        Returns:
            Remaining time in hours
        """
        elapsed = self.get_elapsed_hours(loop_session)
        remaining = self.safety_limits.time_limit_hours - elapsed
        return max(0.0, remaining)

    # Stuck Detection

    def record_error(
        self,
        loop_session: Dict,
        error: str,
        iteration: int,
    ) -> None:
        """
        Record an error that occurred during an iteration.

        Args:
            loop_session: Ralph loop session data
            error: Error message
            iteration: Iteration number when error occurred
        """
        if "error_history" not in loop_session:
            loop_session["error_history"] = []

        loop_session["error_history"].append({
            "error": error,
            "iteration": iteration,
            "timestamp": datetime.now(timezone.utc),
        })

        logger.debug(
            f"Loop {loop_session['id']}: Recorded error at iteration {iteration}: {error}"
        )

    def detect_stuck_loop(
        self,
        loop_session: Dict,
        fuzzy_threshold: float = 0.8,
    ) -> bool:
        """
        Detect if loop is stuck with repeated errors.

        Args:
            loop_session: Ralph loop session data
            fuzzy_threshold: Similarity threshold for fuzzy matching (0-1)

        Returns:
            True if loop is stuck
        """
        error_history = loop_session.get("error_history", [])

        if len(error_history) < self.safety_limits.stuck_error_threshold:
            return False

        # Get recent errors (last N where N = threshold)
        recent_errors = error_history[-self.safety_limits.stuck_error_threshold:]
        error_messages = [e["error"] for e in recent_errors]

        # Check for exact matches
        error_counts = Counter(error_messages)
        most_common = error_counts.most_common(1)[0]

        if most_common[1] >= self.safety_limits.stuck_error_threshold:
            return True

        # Check for fuzzy matches
        if self._has_similar_errors(error_messages, fuzzy_threshold):
            return True

        return False

    def _has_similar_errors(
        self,
        errors: List[str],
        threshold: float,
    ) -> bool:
        """
        Check if errors are similar using fuzzy string matching.

        Args:
            errors: List of error messages
            threshold: Similarity threshold (0-1)

        Returns:
            True if errors are similar
        """
        if len(errors) < 2:
            return False

        # Compare first error with others
        base_error = errors[0]
        similar_count = 1  # Base error counts as 1

        for error in errors[1:]:
            similarity = SequenceMatcher(None, base_error, error).ratio()
            if similarity >= threshold:
                similar_count += 1

        return similar_count >= self.safety_limits.stuck_error_threshold

    def check_stuck_condition(self, loop_session: Dict) -> bool:
        """
        Check if loop is stuck and raise error if detected.

        Args:
            loop_session: Ralph loop session data

        Returns:
            True if not stuck

        Raises:
            StuckLoopError: If stuck condition detected
        """
        if self.detect_stuck_loop(loop_session):
            # Get the repeated error
            error_history = loop_session.get("error_history", [])
            recent_errors = error_history[-self.safety_limits.stuck_error_threshold:]
            error_msg = recent_errors[0]["error"]

            # Escalate to human
            self.escalate_to_human(
                loop_session_id=loop_session["id"],
                reason="stuck_loop",
                details=f"Same error repeated {self.safety_limits.stuck_error_threshold}+ times",
            )

            raise StuckLoopError(
                f"Loop stuck with repeated error: {error_msg}"
            )

        return True

    def escalate_to_human(
        self,
        loop_session_id: UUID,
        reason: str,
        details: str,
    ) -> None:
        """
        Escalate issue to human operator.

        Args:
            loop_session_id: Loop session ID
            reason: Escalation reason
            details: Additional details
        """
        logger.error(
            f"ESCALATION: Loop {loop_session_id} - {reason}: {details}"
        )
        # TODO: Implement notification system (email, Slack, WhatsApp, etc.)

    # Quality Regression Detection

    def record_quality_metrics(
        self,
        loop_session: Dict,
        metrics: Dict,
        iteration: int,
    ) -> None:
        """
        Record quality metrics for an iteration.

        Args:
            loop_session: Ralph loop session data
            metrics: Quality metrics (test_count, coverage, etc.)
            iteration: Iteration number
        """
        if "quality_history" not in loop_session:
            loop_session["quality_history"] = []

        metrics_with_meta = {
            **metrics,
            "iteration": iteration,
            "timestamp": datetime.now(timezone.utc),
        }

        loop_session["quality_history"].append(metrics_with_meta)

        logger.debug(
            f"Loop {loop_session['id']}: Recorded quality metrics at iteration {iteration}"
        )

    def check_quality_regression(self, loop_session: Dict) -> bool:
        """
        Check for quality regressions in recent iterations.

        Args:
            loop_session: Ralph loop session data

        Returns:
            True if no regression detected

        Raises:
            QualityRegressionError: If quality regression detected
        """
        quality_history = loop_session.get("quality_history", [])

        if len(quality_history) < 2:
            return True  # Need at least 2 data points

        # Compare last two iterations
        previous = quality_history[-2]
        current = quality_history[-1]

        # Check test count decrease
        prev_tests = previous.get("test_count", 0)
        curr_tests = current.get("test_count", 0)

        if curr_tests < prev_tests:
            self.pause_loop(
                loop_session_id=loop_session["id"],
                reason="quality_regression",
            )
            self.send_alert(
                loop_session_id=loop_session["id"],
                alert_type="quality_regression",
                message=f"Test count decreased from {prev_tests} to {curr_tests}",
            )
            raise QualityRegressionError(
                f"Test count decreased: {prev_tests} → {curr_tests}"
            )

        # Check coverage drop
        prev_coverage = previous.get("coverage", 0.0)
        curr_coverage = current.get("coverage", 0.0)

        if prev_coverage > 0:
            coverage_drop = (prev_coverage - curr_coverage) / prev_coverage

            if coverage_drop > self.safety_limits.quality_regression_threshold:
                self.pause_loop(
                    loop_session_id=loop_session["id"],
                    reason="quality_regression",
                )
                self.send_alert(
                    loop_session_id=loop_session["id"],
                    alert_type="quality_regression",
                    message=f"Coverage dropped {coverage_drop:.1%}: {prev_coverage:.1%} → {curr_coverage:.1%}",
                )
                raise QualityRegressionError(
                    f"Coverage dropped {coverage_drop:.1%}: "
                    f"{prev_coverage:.1%} → {curr_coverage:.1%}"
                )

        return True

    def pause_loop(self, loop_session_id: UUID, reason: str) -> None:
        """
        Pause a Ralph loop.

        Args:
            loop_session_id: Loop session ID
            reason: Reason for pausing
        """
        logger.warning(f"Pausing loop {loop_session_id}: {reason}")
        # TODO: Implement database update to set status=PAUSED

    def send_alert(
        self,
        loop_session_id: UUID,
        alert_type: str,
        message: str,
    ) -> None:
        """
        Send alert notification.

        Args:
            loop_session_id: Loop session ID
            alert_type: Type of alert
            message: Alert message
        """
        logger.error(
            f"ALERT [{alert_type}] for loop {loop_session_id}: {message}"
        )
        # TODO: Implement notification system

    # Circuit Breaker Coordination

    def validate_safety_checks(self, loop_session: Dict) -> bool:
        """
        Run all safety checks before allowing iteration.

        Args:
            loop_session: Ralph loop session data

        Returns:
            True if all checks pass

        Raises:
            CircuitBreakerError: If any check fails
        """
        violations = []

        # Check iteration limit
        try:
            self.check_iteration_limit(loop_session)
        except CircuitBreakerError as e:
            violations.append(str(e))

        # Check token budget
        try:
            self.check_token_budget(loop_session)
        except TokenBudgetExceededError as e:
            violations.append(str(e))

        # Check time limit
        try:
            self.check_time_limit(loop_session)
        except TimeLimitExceededError as e:
            violations.append(str(e))

        # Check stuck condition
        try:
            self.check_stuck_condition(loop_session)
        except StuckLoopError as e:
            violations.append(str(e))

        # Check quality regression
        try:
            self.check_quality_regression(loop_session)
        except QualityRegressionError as e:
            violations.append(str(e))

        # Raise if any violations
        if violations:
            raise CircuitBreakerError(
                f"Safety violations detected: {'; '.join(violations)}"
            )

        return True

    def is_circuit_broken(self, loop_session_id: UUID) -> bool:
        """
        Check if circuit breaker is active for a loop.

        Args:
            loop_session_id: Loop session ID

        Returns:
            True if circuit breaker is active
        """
        return self._circuit_breakers.get(loop_session_id, False)

    def _trigger_circuit_breaker(self, loop_session_id: UUID) -> None:
        """
        Trigger circuit breaker for a loop.

        Args:
            loop_session_id: Loop session ID
        """
        self._circuit_breakers[loop_session_id] = True
        if self.db:
            self.db.commit()
        logger.error(f"Circuit breaker TRIGGERED for loop {loop_session_id}")

    def reset_circuit_breaker(
        self,
        loop_session_id: UUID,
        authorized_user_id: UUID,
    ) -> None:
        """
        Reset circuit breaker (requires authorization).

        Args:
            loop_session_id: Loop session ID
            authorized_user_id: User authorizing the reset
        """
        self._circuit_breakers[loop_session_id] = False
        logger.warning(
            f"Circuit breaker RESET for loop {loop_session_id} "
            f"by user {authorized_user_id}"
        )
