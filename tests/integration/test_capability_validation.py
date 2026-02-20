"""
Integration Tests for Capability Validation

End-to-end tests for capability validation workflow integrated with
task assignment and lease issuance.

Refs #46 (E7-S4: Capability Validation on Task Assignment)
"""

import pytest
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from backend.services.capability_validation_service import (
    CapabilityValidationService,
    CapabilityMissingError,
    ResourceLimitExceededError,
    DataScopeViolationError,
)
from backend.models.task_requirements import (
    TaskRequirements,
    CapabilityRequirement,
    ResourceLimit,
    ResourceType,
    DataScope,
    CapabilityToken,
)


class TestTaskAssignmentWithCapabilityValidation:
    """Integration tests for task assignment with capability validation"""

    @pytest.fixture
    def validation_service(self):
        """Create capability validation service instance"""
        return CapabilityValidationService()

    @pytest.fixture
    def gpu_task_requirements(self):
        """Create GPU task requirements for testing"""
        return TaskRequirements(
            task_id="task-gpu-001",
            model_name="llama-2-7b",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=True
                ),
                CapabilityRequirement(
                    capability_id="supports:gpu-compute",
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
                    min_required=60,
                    max_allowed=120,
                    unit="minutes"
                )
            ],
            data_scope=DataScope(
                project_id="project-alpha",
                data_classification="internal",
                allowed_regions=["us-west-2"]
            ),
            estimated_duration_minutes=60,
            max_concurrent_tasks=3
        )

    @pytest.fixture
    def valid_gpu_node_token(self):
        """Create valid GPU node capability token"""
        return CapabilityToken(
            peer_id="QmGpuNode1234567890abcdef",
            capabilities=[
                "can_execute:llama-2-7b",
                "can_execute:stable-diffusion",
                "supports:gpu-compute",
                "supports:inference-optimization"
            ],
            limits={
                "max_gpu_minutes": 1000,
                "max_concurrent_tasks": 5,
                "max_gpu_memory_mb": 16384
            },
            data_scopes=["project-alpha", "project-beta"]
        )

    @pytest.fixture
    def cpu_only_node_token(self):
        """Create CPU-only node capability token"""
        return CapabilityToken(
            peer_id="QmCpuNode0987654321fedcba",
            capabilities=[
                "can_execute:gpt-3.5",
                "supports:cpu-compute"
            ],
            limits={
                "max_concurrent_tasks": 10,
                "max_cpu_cores": 16,
                "max_memory_mb": 32768
            },
            data_scopes=["project-alpha"]
        )

    def test_assign_task_with_valid_capability(
        self,
        validation_service,
        gpu_task_requirements,
        valid_gpu_node_token
    ):
        """
        Given node with GPU capability,
        when assigning GPU task,
        then should allow assignment
        """
        # Given: node with minimal usage
        node_usage = {
            "gpu_minutes_used": 100,
            "concurrent_tasks": 1
        }

        # When: validating for task assignment
        result = validation_service.validate(
            task_requirements=gpu_task_requirements,
            capability_token=valid_gpu_node_token,
            node_usage=node_usage
        )

        # Then: validation should pass
        assert result.is_valid is True
        assert result.error_code is None
        assert result.error_message is None

        # And: no violations detected
        assert len(result.missing_capabilities) == 0
        assert len(result.resource_violations) == 0
        assert len(result.scope_violations) == 0

    def test_reject_task_missing_capability(
        self,
        validation_service,
        gpu_task_requirements,
        cpu_only_node_token
    ):
        """
        Given node without GPU,
        when assigning GPU task,
        then should reject with capability error
        """
        # Given: CPU-only node
        node_usage = {
            "concurrent_tasks": 2
        }

        # When: attempting to assign GPU task
        result = validation_service.validate(
            task_requirements=gpu_task_requirements,
            capability_token=cpu_only_node_token,
            node_usage=node_usage
        )

        # Then: validation should fail
        assert result.is_valid is False
        assert result.error_code == "CAPABILITY_MISSING"

        # And: should identify missing GPU capabilities
        assert len(result.missing_capabilities) > 0
        assert "can_execute:llama-2-7b" in result.missing_capabilities
        assert "supports:gpu-compute" in result.missing_capabilities

        # And: error message should be informative
        assert "llama-2-7b" in result.error_message.lower()

    def test_enforce_resource_limits(
        self,
        validation_service,
        gpu_task_requirements,
        valid_gpu_node_token
    ):
        """
        Given node at max_concurrent_tasks,
        when assigning,
        then should reject with limit error
        """
        # Given: node at maximum concurrent task limit
        node_usage = {
            "gpu_minutes_used": 100,
            "concurrent_tasks": 5  # At max (limit is 5)
        }

        # When: attempting to assign another task
        result = validation_service.validate(
            task_requirements=gpu_task_requirements,
            capability_token=valid_gpu_node_token,
            node_usage=node_usage
        )

        # Then: validation should fail
        assert result.is_valid is False
        assert result.error_code == "RESOURCE_LIMIT_EXCEEDED"

        # And: should identify concurrent task violation
        assert len(result.resource_violations) > 0
        concurrent_violation = next(
            (v for v in result.resource_violations
             if v.get("resource_type") == "concurrent_tasks"),
            None
        )
        assert concurrent_violation is not None
        assert concurrent_violation["current"] >= concurrent_violation["limit"]

    def test_validate_data_scope(
        self,
        validation_service,
        gpu_task_requirements
    ):
        """
        Given task in project-alpha, node has project-beta scope,
        then should reject with scope error
        """
        # Given: node authorized only for project-beta
        wrong_scope_token = CapabilityToken(
            peer_id="QmWrongScopeNode",
            capabilities=[
                "can_execute:llama-2-7b",
                "supports:gpu-compute"
            ],
            limits={
                "max_gpu_minutes": 1000,
                "max_concurrent_tasks": 5,
                "max_gpu_memory_mb": 16384
            },
            data_scopes=["project-beta", "project-gamma"]  # Missing project-alpha
        )

        node_usage = {
            "gpu_minutes_used": 0,
            "concurrent_tasks": 0
        }

        # When: validating for project-alpha task
        result = validation_service.validate(
            task_requirements=gpu_task_requirements,
            capability_token=wrong_scope_token,
            node_usage=node_usage
        )

        # Then: validation should fail on scope
        assert result.is_valid is False
        assert result.error_code == "DATA_SCOPE_VIOLATION"

        # And: should identify project-alpha as violation
        assert len(result.scope_violations) > 0
        assert "project-alpha" in result.scope_violations

    def test_check_gpu_minutes_remaining(
        self,
        validation_service,
        gpu_task_requirements,
        valid_gpu_node_token
    ):
        """
        Given node with 10 GPU minutes left, task needs 60,
        then should reject with insufficient resources
        """
        # Given: node has used 990 of 1000 GPU minutes
        node_usage = {
            "gpu_minutes_used": 990,  # Only 10 minutes left
            "concurrent_tasks": 1
        }

        # Task requires 60 GPU minutes
        assert any(
            limit.resource_type == ResourceType.GPU and
            limit.unit.lower() == "minutes" and
            limit.min_required == 60
            for limit in gpu_task_requirements.resource_limits
        )

        # When: validating GPU resources
        result = validation_service.validate(
            task_requirements=gpu_task_requirements,
            capability_token=valid_gpu_node_token,
            node_usage=node_usage
        )

        # Then: validation should fail
        assert result.is_valid is False
        assert result.error_code == "RESOURCE_LIMIT_EXCEEDED"

        # And: should identify GPU minutes violation
        assert len(result.resource_violations) > 0
        gpu_violation = next(
            (v for v in result.resource_violations
             if v.get("resource_type") == "gpu_minutes"),
            None
        )
        assert gpu_violation is not None
        assert gpu_violation["required"] == 60
        assert gpu_violation["available"] == 10

    def test_comprehensive_validation_workflow(
        self,
        validation_service
    ):
        """
        Test complete validation workflow with realistic scenario
        """
        # Given: complex task with multiple requirements
        task = TaskRequirements(
            task_id="task-complex-001",
            model_name="stable-diffusion-xl",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:stable-diffusion-xl",
                    required=True
                ),
                CapabilityRequirement(
                    capability_id="supports:image-generation",
                    required=True
                ),
                CapabilityRequirement(
                    capability_id="supports:gpu-compute",
                    required=True
                )
            ],
            resource_limits=[
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=16384,  # 16GB GPU memory
                    max_allowed=24576,
                    unit="MB"
                ),
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=30,  # 30 GPU minutes
                    max_allowed=60,
                    unit="minutes"
                )
            ],
            data_scope=DataScope(
                project_id="project-creative",
                data_classification="confidential"
            ),
            estimated_duration_minutes=30,
            max_concurrent_tasks=2
        )

        # And: well-equipped node
        node = CapabilityToken(
            peer_id="QmHighEndGpuNode",
            capabilities=[
                "can_execute:stable-diffusion-xl",
                "can_execute:stable-diffusion",
                "can_execute:llama-2-7b",
                "supports:image-generation",
                "supports:gpu-compute",
                "supports:inference-optimization"
            ],
            limits={
                "max_gpu_minutes": 500,
                "max_concurrent_tasks": 3,
                "max_gpu_memory_mb": 24576  # 24GB GPU
            },
            data_scopes=["project-alpha", "project-creative", "project-research"]
        )

        usage = {
            "gpu_minutes_used": 100,
            "concurrent_tasks": 1
        }

        # When: validating comprehensive requirements
        result = validation_service.validate(
            task_requirements=task,
            capability_token=node,
            node_usage=usage
        )

        # Then: all checks should pass
        assert result.is_valid is True
        assert len(result.missing_capabilities) == 0
        assert len(result.resource_violations) == 0
        assert len(result.scope_violations) == 0


class TestValidationWithExceptionRaising:
    """Test validation service with exception-based error handling"""

    @pytest.fixture
    def validation_service(self):
        """Create capability validation service instance"""
        return CapabilityValidationService()

    def test_raise_capability_missing_error(self, validation_service):
        """
        Test validate_and_raise method with missing capability
        """
        task = TaskRequirements(
            task_id="task-exception-test",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=True
                )
            ],
            resource_limits=[],
            estimated_duration_minutes=10
        )

        token = CapabilityToken(
            peer_id="QmTestNode",
            capabilities=["can_execute:gpt-3.5"],  # Wrong capability
            limits={"max_concurrent_tasks": 5},
            data_scopes=[]
        )

        usage = {"concurrent_tasks": 0}

        # When/Then: should raise CapabilityMissingError
        with pytest.raises(CapabilityMissingError) as exc_info:
            validation_service.validate_and_raise(
                task_requirements=task,
                capability_token=token,
                node_usage=usage
            )

        # Verify exception details
        assert "can_execute:llama-2-7b" in exc_info.value.missing_capabilities

    def test_raise_resource_limit_exceeded_error(self, validation_service):
        """
        Test validate_and_raise method with resource limit exceeded
        """
        task = TaskRequirements(
            task_id="task-resource-test",
            capabilities=[],
            resource_limits=[
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=100,
                    max_allowed=200,
                    unit="minutes"
                )
            ],
            estimated_duration_minutes=100
        )

        token = CapabilityToken(
            peer_id="QmTestNode",
            capabilities=[],
            limits={
                "max_gpu_minutes": 50,  # Insufficient
                "max_concurrent_tasks": 5
            },
            data_scopes=[]
        )

        usage = {
            "gpu_minutes_used": 40,  # Only 10 minutes left
            "concurrent_tasks": 0
        }

        # When/Then: should raise ResourceLimitExceededError
        with pytest.raises(ResourceLimitExceededError) as exc_info:
            validation_service.validate_and_raise(
                task_requirements=task,
                capability_token=token,
                node_usage=usage
            )

        # Verify exception details
        assert len(exc_info.value.violations) > 0

    def test_raise_data_scope_violation_error(self, validation_service):
        """
        Test validate_and_raise method with data scope violation
        """
        task = TaskRequirements(
            task_id="task-scope-test",
            capabilities=[],
            resource_limits=[],
            data_scope=DataScope(
                project_id="project-secure",
                data_classification="confidential"
            ),
            estimated_duration_minutes=10
        )

        token = CapabilityToken(
            peer_id="QmTestNode",
            capabilities=[],
            limits={"max_concurrent_tasks": 5},
            data_scopes=["project-public"]  # Wrong scope
        )

        usage = {"concurrent_tasks": 0}

        # When/Then: should raise DataScopeViolationError
        with pytest.raises(DataScopeViolationError) as exc_info:
            validation_service.validate_and_raise(
                task_requirements=task,
                capability_token=token,
                node_usage=usage
            )

        # Verify exception details
        assert "project-secure" in exc_info.value.scope_violations

    def test_no_exception_on_valid_request(self, validation_service):
        """
        Test validate_and_raise does not raise exception on valid request
        """
        task = TaskRequirements(
            task_id="task-valid",
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
            data_scope=DataScope(project_id="project-alpha"),
            estimated_duration_minutes=30
        )

        token = CapabilityToken(
            peer_id="QmValidNode",
            capabilities=["can_execute:llama-2-7b"],
            limits={
                "max_gpu_memory_mb": 16384,
                "max_concurrent_tasks": 5
            },
            data_scopes=["project-alpha"]
        )

        usage = {
            "concurrent_tasks": 1,
            "gpu_minutes_used": 0
        }

        # When/Then: should not raise exception
        try:
            validation_service.validate_and_raise(
                task_requirements=task,
                capability_token=token,
                node_usage=usage
            )
        except Exception as e:
            pytest.fail(f"Unexpected exception raised: {e}")


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.fixture
    def validation_service(self):
        """Create capability validation service instance"""
        return CapabilityValidationService()

    def test_empty_requirements(self, validation_service):
        """
        Test validation with minimal/empty requirements
        """
        task = TaskRequirements(
            task_id="task-minimal",
            capabilities=[],
            resource_limits=[],
            estimated_duration_minutes=5
        )

        token = CapabilityToken(
            peer_id="QmMinimalNode",
            capabilities=[],
            limits={"max_concurrent_tasks": 1},
            data_scopes=[]
        )

        usage = {"concurrent_tasks": 0}

        result = validation_service.validate(
            task_requirements=task,
            capability_token=token,
            node_usage=usage
        )

        # Should pass with no requirements
        assert result.is_valid is True

    def test_optional_capabilities_not_required(self, validation_service):
        """
        Test that optional capabilities don't fail validation
        """
        task = TaskRequirements(
            task_id="task-optional",
            capabilities=[
                CapabilityRequirement(
                    capability_id="can_execute:llama-2-7b",
                    required=False  # Optional
                )
            ],
            resource_limits=[],
            estimated_duration_minutes=10
        )

        token = CapabilityToken(
            peer_id="QmTestNode",
            capabilities=[],  # Missing optional capability
            limits={"max_concurrent_tasks": 5},
            data_scopes=[]
        )

        usage = {"concurrent_tasks": 0}

        result = validation_service.validate(
            task_requirements=task,
            capability_token=token,
            node_usage=usage
        )

        # Should pass since capability is optional
        assert result.is_valid is True

    def test_exact_resource_boundary(self, validation_service):
        """
        Test validation at exact resource boundary
        """
        task = TaskRequirements(
            task_id="task-boundary",
            capabilities=[],
            resource_limits=[
                ResourceLimit(
                    resource_type=ResourceType.GPU,
                    min_required=100,
                    max_allowed=200,
                    unit="minutes"
                )
            ],
            estimated_duration_minutes=100
        )

        token = CapabilityToken(
            peer_id="QmBoundaryNode",
            capabilities=[],
            limits={
                "max_gpu_minutes": 200,  # Exactly 200
                "max_concurrent_tasks": 5
            },
            data_scopes=[]
        )

        usage = {
            "gpu_minutes_used": 100,  # Exactly 100 remaining
            "concurrent_tasks": 0
        }

        result = validation_service.validate(
            task_requirements=task,
            capability_token=token,
            node_usage=usage
        )

        # Should pass at exact boundary
        assert result.is_valid is True
