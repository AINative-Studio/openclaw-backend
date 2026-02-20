"""
Unit Tests for Capability Validation Service

BDD-style tests for capability matching, resource limit checking,
and data scope validation.

Refs #46 (E7-S4: Capability Validation on Task Assignment)
"""

import pytest
from datetime import datetime, timezone
from typing import Dict, Any

from backend.services.capability_validation_service import (
    CapabilityValidationService,
    CapabilityMissingError,
    ResourceLimitExceededError,
    DataScopeViolationError,
    InvalidCapabilityTokenError,
)
from backend.models.task_requirements import (
    TaskRequirements,
    CapabilityRequirement,
    ResourceLimit,
    ResourceType,
    DataScope,
    CapabilityToken,
)


class TestCapabilityMatching:
    """Test capability matching logic"""

    @pytest.fixture
    def validation_service(self):
        """Create capability validation service instance"""
        return CapabilityValidationService()

    @pytest.fixture
    def simple_task_requirements(self):
        """Create simple task requirements for testing"""
        return TaskRequirements(
            task_id="task-123",
            model_name="llama-2-7b",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=True
                )
            ],
            resource_limits=[
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=8192,
                    max_allowed=16384,
                    unit="MB"
                )
            ],
            data_scope=DataScope(
                project_id="project-alpha",
                data_classification="internal"
            ),
            estimated_duration_minutes=30
        )

    @pytest.fixture
    def valid_capability_token(self):
        """Create valid capability token matching requirements"""
        return CapabilityToken(
            peer_id="QmYwAPJzv5CZsnA625s3Xf2nemtYgPpHdWEz79ojWnPbdG",
            capabilities=[
                "can_execute:llama-2-7b",
                "can_execute:stable-diffusion"
            ],
            limits={
                "max_gpu_minutes": 1000,
                "max_concurrent_tasks": 5,
                "max_gpu_memory_mb": 16384
            },
            data_scopes=["project-alpha", "project-beta"]
        )

    def test_validate_with_all_capabilities_present(
        self,
        validation_service,
        simple_task_requirements,
        valid_capability_token
    ):
        """
        Given node with required capability,
        when validating capabilities,
        then should return valid result
        """
        # Given: node usage stats showing no current usage
        node_usage = {
            "gpu_minutes_used": 0,
            "concurrent_tasks": 0
        }

        # When: validating capabilities
        result = validation_service.validate(
            task_requirements=simple_task_requirements,
            capability_token=valid_capability_token,
            node_usage=node_usage
        )

        # Then: validation should pass
        assert result.is_valid is True
        assert result.error_code is None
        assert result.error_message is None
        assert len(result.missing_capabilities) == 0
        assert len(result.resource_violations) == 0
        assert len(result.scope_violations) == 0

    def test_reject_when_capability_missing(
        self,
        validation_service,
        simple_task_requirements
    ):
        """
        Given node without required capability,
        when validating capabilities,
        then should reject with capability error
        """
        # Given: token without required capability
        insufficient_token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=["can_execute:gpt-3.5"],  # Missing llama-2-7b
            limits={
                "max_gpu_minutes": 1000,
                "max_concurrent_tasks": 5,
                "max_gpu_memory_mb": 16384
            },
            data_scopes=["project-alpha"]
        )

        node_usage = {
            "gpu_minutes_used": 0,
            "concurrent_tasks": 0
        }

        # When: validating capabilities
        result = validation_service.validate(
            task_requirements=simple_task_requirements,
            capability_token=insufficient_token,
            node_usage=node_usage
        )

        # Then: validation should fail with missing capability
        assert result.is_valid is False
        assert result.error_code == "CAPABILITY_MISSING"
        assert "can_execute:llama-2-7b" in result.missing_capabilities
        assert "llama-2-7b" in result.error_message.lower()

    def test_validate_multiple_capabilities(self, validation_service):
        """
        Given task requiring multiple capabilities,
        when node has all capabilities,
        then should pass validation
        """
        # Given: task with multiple capability requirements
        task_req = TaskRequirements(
            task_id="task-456",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=True
                ),
                CapabilityRequirement(
                    capability_id="supports:gpu-compute",
                    required=True
                ),
                CapabilityRequirement(
                    capability_id="supports:inference-optimization",
                    required=True
                )
            ],
            resource_limits=[],
            estimated_duration_minutes=15
        )

        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=[
                "can_execute:llama-2-7b",
                "supports:gpu-compute",
                "supports:inference-optimization",
                "can_execute:stable-diffusion"  # Extra capability
            ],
            limits={"max_concurrent_tasks": 5},
            data_scopes=[]
        )

        node_usage = {"concurrent_tasks": 0}

        # When: validating capabilities
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: validation should pass
        assert result.is_valid is True
        assert len(result.missing_capabilities) == 0

    def test_identify_all_missing_capabilities(self, validation_service):
        """
        Given task requiring multiple capabilities,
        when node missing several capabilities,
        then should list all missing capabilities
        """
        # Given: task requiring 3 capabilities
        task_req = TaskRequirements(
            task_id="task-789",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=True
                ),
                CapabilityRequirement(
                    capability_id="supports:gpu-compute",
                    required=True
                ),
                CapabilityRequirement(
                    capability_id="supports:inference-optimization",
                    required=True
                )
            ],
            resource_limits=[],
            estimated_duration_minutes=20
        )

        # Node has only 1 of 3 required capabilities
        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=["supports:gpu-compute"],  # Missing 2 capabilities
            limits={"max_concurrent_tasks": 5},
            data_scopes=[]
        )

        node_usage = {"concurrent_tasks": 0}

        # When: validating capabilities
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should identify all missing capabilities
        assert result.is_valid is False
        assert result.error_code == "CAPABILITY_MISSING"
        assert len(result.missing_capabilities) == 2
        assert "can_execute:llama-2-7b" in result.missing_capabilities
        assert "supports:inference-optimization" in result.missing_capabilities


class TestResourceLimitValidation:
    """Test resource limit checking"""

    @pytest.fixture
    def validation_service(self):
        """Create capability validation service instance"""
        return CapabilityValidationService()

    def test_enforce_max_concurrent_tasks_limit(self, validation_service):
        """
        Given node at max_concurrent_tasks,
        when assigning new task,
        then should reject with limit error
        """
        # Given: task requirements
        task_req = TaskRequirements(
            task_id="task-concurrent",
            capabilities=[],
            resource_limits=[],
            max_concurrent_tasks=3,
            estimated_duration_minutes=10
        )

        # Node token allows max 3 concurrent tasks
        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=[],
            limits={"max_concurrent_tasks": 3},
            data_scopes=[]
        )

        # Node currently running 3 tasks (at limit)
        node_usage = {
            "concurrent_tasks": 3,
            "gpu_minutes_used": 0
        }

        # When: validating for new task assignment
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should reject due to concurrent task limit
        assert result.is_valid is False
        assert result.error_code == "RESOURCE_LIMIT_EXCEEDED"
        assert "concurrent" in result.error_message.lower()
        assert len(result.resource_violations) > 0
        assert any(
            v.get("resource_type") == "concurrent_tasks"
            for v in result.resource_violations
        )

    def test_allow_assignment_below_concurrent_limit(self, validation_service):
        """
        Given node below max_concurrent_tasks,
        when assigning new task,
        then should allow assignment
        """
        # Given: task requirements
        task_req = TaskRequirements(
            task_id="task-concurrent-ok",
            capabilities=[],
            resource_limits=[],
            max_concurrent_tasks=5,
            estimated_duration_minutes=10
        )

        # Node allows up to 5 concurrent tasks
        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=[],
            limits={"max_concurrent_tasks": 5},
            data_scopes=[]
        )

        # Node currently running 2 tasks (below limit)
        node_usage = {
            "concurrent_tasks": 2,
            "gpu_minutes_used": 0
        }

        # When: validating for new task assignment
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should allow assignment
        assert result.is_valid is True

    def test_check_gpu_minutes_remaining(self, validation_service):
        """
        Given node with 10 GPU minutes left,
        when task needs 100 GPU minutes,
        then should reject with insufficient resources
        """
        # Given: task requiring 100 GPU minutes
        task_req = TaskRequirements(
            task_id="task-gpu-intensive",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=True
                )
            ],
            resource_limits=[
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=100,  # Task needs 100 GPU minutes
                    max_allowed=200,
                    unit="minutes"
                )
            ],
            estimated_duration_minutes=100
        )

        # Node has 1000 max GPU minutes total
        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=["can_execute:llama-2-7b"],
            limits={
                "max_gpu_minutes": 1000,
                "max_concurrent_tasks": 5
            },
            data_scopes=[]
        )

        # Node has already used 990 GPU minutes (only 10 left)
        node_usage = {
            "gpu_minutes_used": 990,
            "concurrent_tasks": 0
        }

        # When: validating GPU resource requirements
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should reject due to insufficient GPU minutes
        assert result.is_valid is False
        assert result.error_code == "RESOURCE_LIMIT_EXCEEDED"
        assert "gpu" in result.error_message.lower()
        assert "minutes" in result.error_message.lower()
        assert any(
            v.get("resource_type") == "gpu_minutes"
            for v in result.resource_violations
        )

    def test_allow_gpu_assignment_with_sufficient_minutes(self, validation_service):
        """
        Given node with sufficient GPU minutes,
        when task needs GPU resources,
        then should allow assignment
        """
        # Given: task requiring 50 GPU minutes
        task_req = TaskRequirements(
            task_id="task-gpu-ok",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=True
                )
            ],
            resource_limits=[
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=50,
                    max_allowed=100,
                    unit="minutes"
                )
            ],
            estimated_duration_minutes=50
        )

        # Node has 1000 max GPU minutes
        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=["can_execute:llama-2-7b"],
            limits={
                "max_gpu_minutes": 1000,
                "max_concurrent_tasks": 5
            },
            data_scopes=[]
        )

        # Node used 100 GPU minutes (900 remaining)
        node_usage = {
            "gpu_minutes_used": 100,
            "concurrent_tasks": 0
        }

        # When: validating GPU resources
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should allow assignment
        assert result.is_valid is True

    def test_validate_gpu_memory_requirements(self, validation_service):
        """
        Given task requiring 16GB GPU memory,
        when node has only 8GB GPU memory,
        then should reject
        """
        # Given: task requiring 16GB GPU memory
        task_req = TaskRequirements(
            task_id="task-gpu-memory",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:stable-diffusion-xl",
                    required=True
                )
            ],
            resource_limits=[
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=16384,  # 16GB in MB
                    max_allowed=32768,
                    unit="MB"
                )
            ],
            estimated_duration_minutes=20
        )

        # Node has only 8GB GPU memory
        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=["can_execute:stable-diffusion-xl"],
            limits={
                "max_gpu_memory_mb": 8192,  # 8GB in MB
                "max_concurrent_tasks": 5
            },
            data_scopes=[]
        )

        node_usage = {
            "concurrent_tasks": 0,
            "gpu_minutes_used": 0
        }

        # When: validating GPU memory
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should reject due to insufficient GPU memory
        assert result.is_valid is False
        assert result.error_code == "RESOURCE_LIMIT_EXCEEDED"
        assert any(
            "memory" in str(v).lower() for v in result.resource_violations
        )


class TestDataScopeValidation:
    """Test data scope validation"""

    @pytest.fixture
    def validation_service(self):
        """Create capability validation service instance"""
        return CapabilityValidationService()

    def test_validate_data_scope_match(self, validation_service):
        """
        Given task in project-alpha,
        when node has project-alpha scope,
        then should allow assignment
        """
        # Given: task in project-alpha
        task_req = TaskRequirements(
            task_id="task-scope-match",
            capabilities=[],
            resource_limits=[],
            data_scope=DataScope(
                project_id="project-alpha",
                data_classification="internal"
            ),
            estimated_duration_minutes=15
        )

        # Node authorized for project-alpha
        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=[],
            limits={"max_concurrent_tasks": 5},
            data_scopes=["project-alpha", "project-beta"]
        )

        node_usage = {"concurrent_tasks": 0}

        # When: validating data scope
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should allow assignment
        assert result.is_valid is True
        assert len(result.scope_violations) == 0

    def test_reject_data_scope_mismatch(self, validation_service):
        """
        Given task in project-alpha,
        when node has only project-beta scope,
        then should reject with scope error
        """
        # Given: task in project-alpha
        task_req = TaskRequirements(
            task_id="task-scope-violation",
            capabilities=[],
            resource_limits=[],
            data_scope=DataScope(
                project_id="project-alpha",
                data_classification="confidential"
            ),
            estimated_duration_minutes=15
        )

        # Node authorized only for project-beta (not alpha)
        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=[],
            limits={"max_concurrent_tasks": 5},
            data_scopes=["project-beta", "project-gamma"]
        )

        node_usage = {"concurrent_tasks": 0}

        # When: validating data scope
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should reject due to scope violation
        assert result.is_valid is False
        assert result.error_code == "DATA_SCOPE_VIOLATION"
        assert "project-alpha" in result.scope_violations
        assert "scope" in result.error_message.lower()

    def test_allow_task_without_data_scope(self, validation_service):
        """
        Given task without data scope requirement,
        when validating,
        then should skip scope validation
        """
        # Given: task without data scope
        task_req = TaskRequirements(
            task_id="task-no-scope",
            capabilities=[],
            resource_limits=[],
            data_scope=None,  # No scope requirement
            estimated_duration_minutes=10
        )

        # Node with limited scopes
        token = CapabilityToken(
            peer_id="QmTestPeer",
            capabilities=[],
            limits={"max_concurrent_tasks": 5},
            data_scopes=["project-beta"]
        )

        node_usage = {"concurrent_tasks": 0}

        # When: validating
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should pass (no scope check needed)
        assert result.is_valid is True
        assert len(result.scope_violations) == 0


class TestCombinedValidation:
    """Test combined validation scenarios"""

    @pytest.fixture
    def validation_service(self):
        """Create capability validation service instance"""
        return CapabilityValidationService()

    def test_comprehensive_validation_all_checks_pass(self, validation_service):
        """
        Given valid capability, sufficient resources, and correct scope,
        when validating,
        then all checks should pass
        """
        # Given: comprehensive task requirements
        task_req = TaskRequirements(
            task_id="task-comprehensive",
            model_name="llama-2-7b",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=True
                )
            ],
            resource_limits=[
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=8192,
                    max_allowed=16384,
                    unit="MB"
                ),
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=50,
                    max_allowed=100,
                    unit="minutes"
                )
            ],
            data_scope=DataScope(
                project_id="project-alpha",
                data_classification="internal"
            ),
            estimated_duration_minutes=50,
            max_concurrent_tasks=3
        )

        # Fully compliant token
        token = CapabilityToken(
            peer_id="QmValidPeer",
            capabilities=["can_execute:llama-2-7b"],
            limits={
                "max_gpu_minutes": 1000,
                "max_concurrent_tasks": 3,
                "max_gpu_memory_mb": 16384
            },
            data_scopes=["project-alpha"]
        )

        # Healthy node usage
        node_usage = {
            "gpu_minutes_used": 100,
            "concurrent_tasks": 1
        }

        # When: validating all aspects
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: validation passes completely
        assert result.is_valid is True
        assert result.error_code is None
        assert len(result.missing_capabilities) == 0
        assert len(result.resource_violations) == 0
        assert len(result.scope_violations) == 0

    def test_fail_on_multiple_violations(self, validation_service):
        """
        Given missing capability AND insufficient resources AND wrong scope,
        when validating,
        then should report all violations
        """
        # Given: task with multiple requirements
        task_req = TaskRequirements(
            task_id="task-multi-fail",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=True
                )
            ],
            resource_limits=[
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=100,
                    max_allowed=200,
                    unit="minutes"
                )
            ],
            data_scope=DataScope(
                project_id="project-alpha",
                data_classification="confidential"
            ),
            estimated_duration_minutes=100
        )

        # Token with multiple issues
        token = CapabilityToken(
            peer_id="QmInvalidPeer",
            capabilities=["can_execute:gpt-3.5"],  # Wrong capability
            limits={
                "max_gpu_minutes": 50,  # Insufficient
                "max_concurrent_tasks": 5
            },
            data_scopes=["project-beta"]  # Wrong scope
        )

        node_usage = {
            "gpu_minutes_used": 40,  # Only 10 minutes left
            "concurrent_tasks": 0
        }

        # When: validating
        result = validation_service.validate(
            task_requirements=task_req,
            capability_token=token,
            node_usage=node_usage
        )

        # Then: should report all violations
        assert result.is_valid is False
        assert len(result.missing_capabilities) > 0
        assert len(result.resource_violations) > 0
        assert len(result.scope_violations) > 0
