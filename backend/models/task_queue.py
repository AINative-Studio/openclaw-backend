"""
DEPRECATED: Task Queue Models (Issue #116)

This file is DEPRECATED and will be removed in a future release.
All imports have been consolidated into backend.models.task_lease

DO NOT import Task or TaskLease from this file. Use:
    from backend.models.task_lease import Task, TaskLease, TaskStatus, TaskPriority

Migration: Issue #116 - Consolidate PostgreSQL Schema Models
"""

# Allow importing TaskStatus and TaskPriority for backward compatibility during migration
from backend.models.task_lease import TaskStatus, TaskPriority  # noqa: F401

# Prevent importing Task and TaskLease from this deprecated location
def __getattr__(name):
    if name in ("Task", "TaskLease"):
        raise ImportError(
            f"backend.models.task_queue.{name} is DEPRECATED. "
            "Import from backend.models.task_lease instead:\n"
            f"  from backend.models.task_lease import {name}\n"
            "See Issue #116 for migration details."
        )
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
