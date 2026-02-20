"""
Capability Validation Service

Validates node capabilities against task requirements including capability
matching, resource limit checking, and data scope validation.

Refs #46 (E7-S4: Capability Validation on Task Assignment)
"""

import logging
from typing import Dict, Any, Optional

from backend.models.task_requirements import (
    TaskRequirements,
    CapabilityToken,
    ValidationResult,
    ResourceType,
)


logger = logging.getLogger(__name__)


class CapabilityMissingError(Exception):
    """Raised when required capability is not present in token"""

    def __init__(self, message: str, missing_capabilities: list):
        super().__init__(message)
        self.missing_capabilities = missing_capabilities


class ResourceLimitExceededError(Exception):
    """Raised when resource limits are exceeded"""

    def __init__(self, message: str, violations: list):
        super().__init__(message)
        self.violations = violations


class DataScopeViolationError(Exception):
    """Raised when data scope requirements are not met"""

    def __init__(self, message: str, scope_violations: list):
        super().__init__(message)
        self.scope_violations = scope_violations


class InvalidCapabilityTokenError(Exception):
    """Raised when capability token is invalid or malformed"""
    pass


class CapabilityValidationService:
    """
    Service for validating node capabilities against task requirements

    Responsibilities:
    - Match required capabilities against token capabilities
    - Validate resource limits (GPU minutes, memory, concurrent tasks)
    - Check data scope permissions
    - Return comprehensive validation results
    """

    def validate(
        self,
        task_requirements: TaskRequirements,
        capability_token: CapabilityToken,
        node_usage: Dict[str, Any]
    ) -> ValidationResult:
        """
        Validate node capabilities against task requirements

        Args:
            task_requirements: Task capability and resource requirements
            capability_token: Node's capability token with permissions
            node_usage: Current node resource usage stats

        Returns:
            ValidationResult with detailed validation outcome

        Validation checks performed:
        1. Capability matching - all required capabilities present
        2. Resource limits - GPU minutes, memory, concurrent tasks
        3. Data scope - project/data access permissions
        """
        missing_capabilities = []
        resource_violations = []
        scope_violations = []

        # 1. Validate capability matching
        missing_capabilities = self._check_capabilities(
            task_requirements=task_requirements,
            capability_token=capability_token
        )

        # 2. Validate resource limits
        resource_violations = self._check_resource_limits(
            task_requirements=task_requirements,
            capability_token=capability_token,
            node_usage=node_usage
        )

        # 3. Validate data scope
        scope_violations = self._check_data_scope(
            task_requirements=task_requirements,
            capability_token=capability_token
        )

        # Determine overall validation result
        is_valid = (
            len(missing_capabilities) == 0 and
            len(resource_violations) == 0 and
            len(scope_violations) == 0
        )

        # Build error message and code if validation failed
        error_code = None
        error_message = None

        if not is_valid:
            if missing_capabilities:
                error_code = "CAPABILITY_MISSING"
                error_message = (
                    f"Node missing required capabilities: "
                    f"{', '.join(missing_capabilities)}"
                )
            elif resource_violations:
                error_code = "RESOURCE_LIMIT_EXCEEDED"
                # Get first violation for primary error message
                first_violation = resource_violations[0]
                error_message = first_violation.get(
                    "message",
                    "Resource limits exceeded"
                )
            elif scope_violations:
                error_code = "DATA_SCOPE_VIOLATION"
                error_message = (
                    f"Data scope violation: task requires access to "
                    f"{', '.join(scope_violations)}"
                )

        logger.info(
            f"Capability validation for task {task_requirements.task_id}: "
            f"valid={is_valid}, error_code={error_code}",
            extra={
                "task_id": task_requirements.task_id,
                "peer_id": capability_token.peer_id,
                "is_valid": is_valid,
                "missing_capabilities": missing_capabilities,
                "resource_violations": resource_violations,
                "scope_violations": scope_violations
            }
        )

        return ValidationResult(
            is_valid=is_valid,
            error_code=error_code,
            error_message=error_message,
            missing_capabilities=missing_capabilities,
            resource_violations=resource_violations,
            scope_violations=scope_violations
        )

    def _check_capabilities(
        self,
        task_requirements: TaskRequirements,
        capability_token: CapabilityToken
    ) -> list:
        """
        Check if all required capabilities are present in token

        Args:
            task_requirements: Task requirements
            capability_token: Node capability token

        Returns:
            List of missing capability IDs (empty if all present)
        """
        missing = []

        # Get required capabilities from task
        required_capabilities = task_requirements.get_required_capabilities()

        # Check each required capability
        for required_cap in required_capabilities:
            if required_cap not in capability_token.capabilities:
                missing.append(required_cap)
                logger.debug(
                    f"Missing capability: {required_cap}",
                    extra={
                        "task_id": task_requirements.task_id,
                        "peer_id": capability_token.peer_id,
                        "required_capability": required_cap
                    }
                )

        return missing

    def _check_resource_limits(
        self,
        task_requirements: TaskRequirements,
        capability_token: CapabilityToken,
        node_usage: Dict[str, Any]
    ) -> list:
        """
        Check if node has sufficient resources for task

        Validates:
        - GPU minutes remaining
        - GPU memory capacity
        - Concurrent task limits
        - Other resource constraints

        Args:
            task_requirements: Task resource requirements
            capability_token: Node capability limits
            node_usage: Current node resource usage

        Returns:
            List of resource violations (empty if all checks pass)
        """
        violations = []

        # Check concurrent task limit
        max_concurrent = capability_token.limits.get("max_concurrent_tasks", 999)
        current_concurrent = node_usage.get("concurrent_tasks", 0)

        if current_concurrent >= max_concurrent:
            violations.append({
                "resource_type": "concurrent_tasks",
                "limit": max_concurrent,
                "current": current_concurrent,
                "message": (
                    f"Node at maximum concurrent tasks "
                    f"({current_concurrent}/{max_concurrent})"
                )
            })

        # Check GPU minutes
        gpu_minutes_violations = self._check_gpu_minutes(
            task_requirements=task_requirements,
            capability_token=capability_token,
            node_usage=node_usage
        )
        violations.extend(gpu_minutes_violations)

        # Check GPU memory
        gpu_memory_violations = self._check_gpu_memory(
            task_requirements=task_requirements,
            capability_token=capability_token
        )
        violations.extend(gpu_memory_violations)

        return violations

    def _check_gpu_minutes(
        self,
        task_requirements: TaskRequirements,
        capability_token: CapabilityToken,
        node_usage: Dict[str, Any]
    ) -> list:
        """
        Check GPU minutes availability

        Args:
            task_requirements: Task requirements
            capability_token: Node capability token
            node_usage: Current usage stats

        Returns:
            List of GPU minute violations
        """
        violations = []

        # Find GPU minutes requirement
        gpu_minutes_required = None
        for limit in task_requirements.resource_limits:
            if (limit.resource_type == ResourceType.GPU and
                limit.unit.lower() == "minutes"):
                gpu_minutes_required = limit.min_required
                break

        if gpu_minutes_required is None:
            return violations  # No GPU minutes requirement

        # Check token limits
        max_gpu_minutes = capability_token.limits.get("max_gpu_minutes")
        if max_gpu_minutes is None:
            return violations  # No GPU minutes limit in token

        # Calculate remaining GPU minutes
        gpu_minutes_used = node_usage.get("gpu_minutes_used", 0)
        gpu_minutes_remaining = max_gpu_minutes - gpu_minutes_used

        if gpu_minutes_remaining < gpu_minutes_required:
            violations.append({
                "resource_type": "gpu_minutes",
                "required": gpu_minutes_required,
                "available": gpu_minutes_remaining,
                "limit": max_gpu_minutes,
                "used": gpu_minutes_used,
                "message": (
                    f"Insufficient GPU minutes: task requires "
                    f"{gpu_minutes_required} minutes, only "
                    f"{gpu_minutes_remaining} minutes remaining"
                )
            })

        return violations

    def _check_gpu_memory(
        self,
        task_requirements: TaskRequirements,
        capability_token: CapabilityToken
    ) -> list:
        """
        Check GPU memory capacity

        Args:
            task_requirements: Task requirements
            capability_token: Node capability token

        Returns:
            List of GPU memory violations
        """
        violations = []

        # Find GPU memory requirement (in MB)
        gpu_memory_required = None
        for limit in task_requirements.resource_limits:
            if (limit.resource_type == ResourceType.GPU and
                limit.unit.upper() == "MB"):
                gpu_memory_required = limit.min_required
                break

        if gpu_memory_required is None:
            return violations  # No GPU memory requirement

        # Check token limits
        max_gpu_memory = capability_token.limits.get("max_gpu_memory_mb")
        if max_gpu_memory is None:
            return violations  # No GPU memory limit specified

        if max_gpu_memory < gpu_memory_required:
            violations.append({
                "resource_type": "gpu_memory",
                "required": gpu_memory_required,
                "available": max_gpu_memory,
                "unit": "MB",
                "message": (
                    f"Insufficient GPU memory: task requires "
                    f"{gpu_memory_required}MB, node has "
                    f"{max_gpu_memory}MB"
                )
            })

        return violations

    def _check_data_scope(
        self,
        task_requirements: TaskRequirements,
        capability_token: CapabilityToken
    ) -> list:
        """
        Check data scope permissions

        Args:
            task_requirements: Task requirements with data scope
            capability_token: Node capability token with authorized scopes

        Returns:
            List of scope violations (project IDs node cannot access)
        """
        violations = []

        # If task has no data scope requirement, skip check
        if task_requirements.data_scope is None:
            return violations

        required_project = task_requirements.data_scope.project_id

        # Check if node has access to required project
        if required_project not in capability_token.data_scopes:
            violations.append(required_project)
            logger.debug(
                f"Data scope violation: task requires {required_project}, "
                f"node authorized for {capability_token.data_scopes}",
                extra={
                    "task_id": task_requirements.task_id,
                    "peer_id": capability_token.peer_id,
                    "required_scope": required_project,
                    "authorized_scopes": capability_token.data_scopes
                }
            )

        return violations

    def validate_and_raise(
        self,
        task_requirements: TaskRequirements,
        capability_token: CapabilityToken,
        node_usage: Dict[str, Any]
    ) -> None:
        """
        Validate capabilities and raise exception if validation fails

        This is a convenience method for integration with task assignment
        workflows that expect exceptions on validation failure.

        Args:
            task_requirements: Task requirements
            capability_token: Node capability token
            node_usage: Current node usage stats

        Raises:
            CapabilityMissingError: If required capabilities missing
            ResourceLimitExceededError: If resource limits exceeded
            DataScopeViolationError: If data scope requirements not met
        """
        result = self.validate(
            task_requirements=task_requirements,
            capability_token=capability_token,
            node_usage=node_usage
        )

        if not result.is_valid:
            if result.missing_capabilities:
                raise CapabilityMissingError(
                    result.error_message,
                    result.missing_capabilities
                )
            elif result.resource_violations:
                raise ResourceLimitExceededError(
                    result.error_message,
                    result.resource_violations
                )
            elif result.scope_violations:
                raise DataScopeViolationError(
                    result.error_message,
                    result.scope_violations
                )
