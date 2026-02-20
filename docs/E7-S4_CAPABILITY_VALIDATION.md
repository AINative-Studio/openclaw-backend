# E7-S4: Capability Validation Implementation

**Epic:** E7 - Security & Authorization
**Story:** E7-S4 - Capability Validation on Task Assignment
**Points:** 3
**Status:** Completed
**Issue:** #46

## Overview

Comprehensive capability validation for task assignments ensuring tasks are only assigned to nodes with appropriate capabilities, sufficient resources, and correct data access permissions.

## Implementation Summary

### Components Delivered

1. **Task Requirements Model** (`backend/models/task_requirements.py`)
   - TaskRequirements: Complete task requirement specification
   - CapabilityRequirement: Individual capability constraints
   - ResourceLimit: Resource constraints (GPU, CPU, memory)
   - DataScope: Data access scope and permissions
   - CapabilityToken: Node capability token (placeholder for E7-S1)
   - ValidationResult: Validation outcome with detailed errors

2. **Capability Validation Service** (`backend/services/capability_validation_service.py`)
   - CapabilityValidationService: Core validation logic
   - Exception classes: CapabilityMissingError, ResourceLimitExceededError, DataScopeViolationError
   - Comprehensive validation across all dimensions

3. **Test Suites**
   - Unit tests: 14 tests (100% service coverage)
   - Integration tests: 13 tests (86% model coverage)
   - Total: 27 tests, 94% overall coverage

## Validation Workflow

```
Task Assignment Request
         |
         v
+------------------+
| Validate         |
| Capabilities     |  --> Check required capabilities present
+------------------+
         |
         v
+------------------+
| Check Resource   |  --> Verify GPU minutes, memory, concurrent tasks
| Limits           |
+------------------+
         |
         v
+------------------+
| Validate Data    |  --> Ensure project scope authorization
| Scope            |
+------------------+
         |
         v
   ValidationResult
   (pass/fail + details)
```

## Validation Checks

### 1. Capability Matching
- Verifies all required capabilities present in token
- Example: `can_execute:llama-2-7b`
- Error Code: `CAPABILITY_MISSING`

### 2. Resource Limit Checking

**GPU Minutes:**
- Checks: `remaining_gpu_minutes >= task.estimated_gpu_minutes`
- Calculation: `remaining = max_gpu_minutes - gpu_minutes_used`

**GPU Memory:**
- Checks: `node.max_gpu_memory_mb >= task.min_required_gpu_memory_mb`
- Unit: MB (megabytes)

**Concurrent Tasks:**
- Checks: `current_concurrent < max_concurrent_tasks`

Error Code: `RESOURCE_LIMIT_EXCEEDED`

### 3. Data Scope Validation
- Ensures node authorized for task's project
- Checks: `task.project_id in token.data_scopes`
- Error Code: `DATA_SCOPE_VIOLATION`

## API Usage

### Basic Validation
```python
service = CapabilityValidationService()

result = service.validate(
    task_requirements=task_req,
    capability_token=token,
    node_usage={"gpu_minutes_used": 100, "concurrent_tasks": 2}
)

if result.is_valid:
    assign_task(...)
else:
    handle_error(result.error_code, result.error_message)
```

### Exception-Based Validation
```python
try:
    service.validate_and_raise(
        task_requirements=task_req,
        capability_token=token,
        node_usage=usage
    )
    assign_task(...)
except CapabilityMissingError as e:
    logger.error(f"Missing: {e.missing_capabilities}")
except ResourceLimitExceededError as e:
    logger.error(f"Resource exceeded: {e.violations}")
except DataScopeViolationError as e:
    logger.error(f"Scope violation: {e.scope_violations}")
```

## Test Coverage

### Unit Tests (14 tests)
- Capability matching: 4 tests
- Resource limit validation: 5 tests
- Data scope validation: 3 tests
- Combined validation: 2 tests
- Coverage: 100% of service code

### Integration Tests (13 tests)
- Task assignment validation: 6 tests
- Exception-based workflow: 4 tests
- Edge cases: 3 tests
- Coverage: 86% of model code

### Overall Metrics
- Total Tests: 27 (all passing)
- Overall Coverage: 94%
- Service Coverage: 100%
- Model Coverage: 86%

## Files Created

1. `backend/models/task_requirements.py` (358 lines)
2. `backend/services/capability_validation_service.py` (331 lines)
3. `tests/services/test_capability_validation_service.py` (634 lines)
4. `tests/integration/test_capability_validation.py` (906 lines)

**Total:** 2,229 lines of production and test code

## Acceptance Criteria Verification

- ✅ Check node capability token
- ✅ Verify "can_execute:llama-2-7b" present
- ✅ Check GPU resource limits not exceeded
- ✅ Validate data scope includes task project
- ✅ Reject if any check fails
- ✅ Integration tests with >=80% coverage (94% achieved)
- ✅ BDD-style tests implemented
- ✅ TDD approach followed

## Integration Points

### Task Lease Issuance
```python
validation_service = CapabilityValidationService()
result = validation_service.validate(
    task_requirements=task_req,
    capability_token=node_token,
    node_usage=get_node_usage(peer_id)
)

if result.is_valid:
    lease = await lease_service.issue_lease(lease_request)
else:
    raise CapabilityValidationError(result)
```

## Security Considerations

1. Capability token verification (E7-S1 dependency)
2. Resource exhaustion prevention
3. Data access control enforcement
4. Comprehensive audit logging

## Dependencies

- E7-S1: Capability Token Schema (placeholder implemented)
- E5-S1: Task Lease Issuance (integration point)

## References

- Issue: #46
- Epic: E7 - Security & Authorization
- Branch: `feature/e7s4-capability-validation`
