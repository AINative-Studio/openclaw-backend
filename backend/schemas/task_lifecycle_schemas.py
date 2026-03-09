"""
Pydantic schemas for task lifecycle endpoints.

Provides request/response models for:
- Task requeue (POST /tasks/{task_id}/requeue)
- Task cancellation (POST /tasks/{task_id}/cancel)

Refs: Issue #122 - MCP Evaluation (native tools approach)
"""

from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, Field


class TaskRequeueRequest(BaseModel):
    """Request to manually requeue a task."""

    force: bool = Field(
        default=False,
        description="Force requeue even if retry limit reached"
    )
    reset_retry_count: bool = Field(
        default=False,
        description="Reset retry count to 0 (use with caution)"
    )
    reason: Optional[str] = Field(
        None,
        max_length=500,
        description="Optional reason for manual requeue"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "force": False,
                "reset_retry_count": False,
                "reason": "Manual intervention - suspected transient network issue"
            }
        }


class TaskRequeueResponse(BaseModel):
    """Response after requeueing a task."""

    task_id: UUID = Field(..., description="UUID of the requeued task")
    previous_status: str = Field(..., description="Task status before requeue")
    current_status: str = Field(..., description="Task status after requeue (should be 'queued')")
    retry_count: int = Field(..., ge=0, description="Current retry count")
    max_retries: int = Field(..., ge=0, description="Maximum retries allowed")
    requeued_at: datetime = Field(..., description="Timestamp when task was requeued")
    reason: Optional[str] = Field(None, description="Requeue reason")
    backoff_seconds: Optional[int] = Field(
        None,
        description="Backoff delay before task becomes available (exponential backoff)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "previous_status": "failed",
                "current_status": "queued",
                "retry_count": 2,
                "max_retries": 5,
                "requeued_at": "2026-03-08T12:10:00Z",
                "reason": "Manual intervention - suspected transient network issue",
                "backoff_seconds": 120
            }
        }


class TaskCancelRequest(BaseModel):
    """Request to cancel a running task."""

    reason: str = Field(..., min_length=1, max_length=500, description="Reason for cancellation")
    notify_peer: bool = Field(
        default=True,
        description="Send cancellation notification to assigned peer"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "reason": "User requested cancellation - task no longer needed",
                "notify_peer": True
            }
        }


class TaskCancelResponse(BaseModel):
    """Response after cancelling a task."""

    task_id: UUID = Field(..., description="UUID of the cancelled task")
    previous_status: str = Field(..., description="Task status before cancellation")
    current_status: str = Field(..., description="Task status after cancellation (should be 'cancelled')")
    cancelled_at: datetime = Field(..., description="Timestamp when task was cancelled")
    reason: str = Field(..., description="Cancellation reason")
    lease_revoked: bool = Field(..., description="Whether an active lease was revoked")
    peer_notified: bool = Field(..., description="Whether the assigned peer was notified")
    assigned_peer_id: Optional[str] = Field(None, description="Peer ID that was working on the task")

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "previous_status": "running",
                "current_status": "cancelled",
                "cancelled_at": "2026-03-08T12:15:00Z",
                "reason": "User requested cancellation - task no longer needed",
                "lease_revoked": True,
                "peer_notified": True,
                "assigned_peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI"
            }
        }


class TaskRetryInfoResponse(BaseModel):
    """Information about task retry configuration and history."""

    task_id: UUID = Field(..., description="UUID of the task")
    retry_count: int = Field(..., ge=0, description="Current number of retries")
    max_retries: int = Field(..., ge=0, description="Maximum retries allowed")
    retries_remaining: int = Field(..., ge=0, description="Retries remaining before permanent failure")
    current_backoff_seconds: int = Field(..., ge=0, description="Current exponential backoff delay")
    next_backoff_seconds: int = Field(..., ge=0, description="Backoff if task fails again")
    can_retry: bool = Field(..., description="Whether task can be retried")
    retry_history: list[dict] = Field(
        default_factory=list,
        description="History of retry attempts with timestamps and reasons"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "retry_count": 2,
                "max_retries": 5,
                "retries_remaining": 3,
                "current_backoff_seconds": 120,
                "next_backoff_seconds": 240,
                "can_retry": True,
                "retry_history": [
                    {
                        "attempt": 1,
                        "failed_at": "2026-03-08T10:00:00Z",
                        "reason": "Connection timeout",
                        "backoff_seconds": 30
                    },
                    {
                        "attempt": 2,
                        "failed_at": "2026-03-08T10:05:00Z",
                        "reason": "Node unavailable",
                        "backoff_seconds": 60
                    }
                ]
            }
        }
