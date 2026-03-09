"""
DEPRECATED: Task Models (Issue #116)

This file is DEPRECATED and will be removed in a future release.
All imports have been consolidated into backend.models.task_lease

DO NOT import from this file. Use:
    from backend.models.task_lease import Task, TaskLease, TaskStatus, TaskPriority

Migration: Issue #116 - Consolidate PostgreSQL Schema Models
"""

raise ImportError(
    "backend.models.task_models is DEPRECATED. "
    "Import from backend.models.task_lease instead:\n"
    "  from backend.models.task_lease import Task, TaskLease, TaskStatus, TaskPriority\n"
    "See Issue #116 for migration details."
)
