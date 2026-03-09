"""
Pydantic schemas for recovery and fault tolerance endpoints.

Provides request/response models for:
- Partition status (GET /partitions/status)
- Recovery trigger (POST /recovery/trigger)
- Result buffer stats (GET /buffer/stats)

Refs: Issue #122 - MCP Evaluation (native tools approach)
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class PartitionStatusResponse(BaseModel):
    """DBOS partition detection status."""

    is_partitioned: bool = Field(..., description="Whether system is currently partitioned from DBOS")
    mode: str = Field(..., description="Current mode (NORMAL/DEGRADED/RECONCILING)")
    dbos_gateway_url: str = Field(..., description="DBOS Gateway URL being monitored")
    last_successful_check: Optional[datetime] = Field(None, description="Last successful health check")
    last_failed_check: Optional[datetime] = Field(None, description="Last failed health check")
    consecutive_failures: int = Field(..., ge=0, description="Number of consecutive health check failures")
    failure_threshold: int = Field(..., ge=1, description="Failures before entering degraded mode")
    check_interval_seconds: int = Field(..., ge=1, description="Health check interval")
    buffered_results_count: int = Field(..., ge=0, description="Number of results buffered during partition")
    uptime_seconds: int = Field(..., ge=0, description="Service uptime in seconds")

    class Config:
        json_schema_extra = {
            "example": {
                "is_partitioned": True,
                "mode": "DEGRADED",
                "dbos_gateway_url": "http://localhost:18789",
                "last_successful_check": "2026-03-08T11:45:00Z",
                "last_failed_check": "2026-03-08T12:15:00Z",
                "consecutive_failures": 5,
                "failure_threshold": 3,
                "check_interval_seconds": 10,
                "buffered_results_count": 23,
                "uptime_seconds": 3600
            }
        }


class RecoveryTriggerRequest(BaseModel):
    """Request to manually trigger recovery workflow."""

    peer_id: str = Field(..., description="Peer ID of the failed node")
    failure_type: str = Field(
        ...,
        description="Type of failure (NODE_CRASH/PARTITION_HEALED/LEASE_EXPIRED)"
    )
    reason: Optional[str] = Field(None, max_length=500, description="Reason for manual recovery trigger")
    force: bool = Field(default=False, description="Force recovery even if node appears healthy")

    class Config:
        json_schema_extra = {
            "example": {
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "failure_type": "NODE_CRASH",
                "reason": "Manual intervention - node not responding to pings",
                "force": False
            }
        }


class RecoveryAction(BaseModel):
    """A single recovery action taken."""

    action_type: str = Field(..., description="Type of action (REVOKE_LEASE/REQUEUE_TASK/FLUSH_BUFFER)")
    target_id: str = Field(..., description="ID of the target entity (lease_id, task_id, etc.)")
    status: str = Field(..., description="Action status (SUCCESS/FAILED/SKIPPED)")
    timestamp: datetime = Field(..., description="When action was performed")
    details: Optional[str] = Field(None, description="Additional details about the action")

    class Config:
        json_schema_extra = {
            "example": {
                "action_type": "REVOKE_LEASE",
                "target_id": "660e8400-e29b-41d4-a716-446655440000",
                "status": "SUCCESS",
                "timestamp": "2026-03-08T12:15:30Z",
                "details": "Lease revoked successfully, task requeued"
            }
        }


class RecoveryTriggerResponse(BaseModel):
    """Response after triggering recovery workflow."""

    recovery_id: str = Field(..., description="Unique ID for this recovery operation")
    peer_id: str = Field(..., description="Peer ID that was recovered")
    failure_type: str = Field(..., description="Type of failure handled")
    started_at: datetime = Field(..., description="When recovery started")
    completed_at: datetime = Field(..., description="When recovery completed")
    success: bool = Field(..., description="Whether recovery was successful")
    actions_taken: List[RecoveryAction] = Field(..., description="List of recovery actions performed")
    leases_revoked: int = Field(..., ge=0, description="Number of leases revoked")
    tasks_requeued: int = Field(..., ge=0, description="Number of tasks requeued")
    results_flushed: int = Field(..., ge=0, description="Number of buffered results flushed")
    error_message: Optional[str] = Field(None, description="Error message if recovery failed")

    class Config:
        json_schema_extra = {
            "example": {
                "recovery_id": "rec_770e8400-e29b-41d4-a716-446655440000",
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "failure_type": "NODE_CRASH",
                "started_at": "2026-03-08T12:15:00Z",
                "completed_at": "2026-03-08T12:15:35Z",
                "success": True,
                "actions_taken": [
                    {
                        "action_type": "REVOKE_LEASE",
                        "target_id": "660e8400-e29b-41d4-a716-446655440000",
                        "status": "SUCCESS",
                        "timestamp": "2026-03-08T12:15:30Z",
                        "details": "Lease revoked successfully"
                    },
                    {
                        "action_type": "REQUEUE_TASK",
                        "target_id": "550e8400-e29b-41d4-a716-446655440000",
                        "status": "SUCCESS",
                        "timestamp": "2026-03-08T12:15:32Z",
                        "details": "Task requeued with retry count incremented"
                    }
                ],
                "leases_revoked": 3,
                "tasks_requeued": 3,
                "results_flushed": 0,
                "error_message": None
            }
        }


class BufferedResult(BaseModel):
    """A single buffered task result."""

    buffer_id: str = Field(..., description="Unique buffer entry ID")
    task_id: str = Field(..., description="Task UUID")
    peer_id: str = Field(..., description="Peer ID that submitted the result")
    buffered_at: datetime = Field(..., description="When result was buffered")
    retry_count: int = Field(..., ge=0, description="Number of flush attempts")
    last_retry_at: Optional[datetime] = Field(None, description="Last flush attempt timestamp")
    status: str = Field(..., description="Buffer entry status (PENDING/SUBMITTED/FAILED)")

    class Config:
        json_schema_extra = {
            "example": {
                "buffer_id": "buf_880e8400-e29b-41d4-a716-446655440000",
                "task_id": "550e8400-e29b-41d4-a716-446655440000",
                "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                "buffered_at": "2026-03-08T12:10:00Z",
                "retry_count": 2,
                "last_retry_at": "2026-03-08T12:12:00Z",
                "status": "PENDING"
            }
        }


class BufferStatsResponse(BaseModel):
    """Result buffer statistics."""

    total_buffered: int = Field(..., ge=0, description="Total results currently buffered")
    pending_submission: int = Field(..., ge=0, description="Results pending submission to DBOS")
    submitted: int = Field(..., ge=0, description="Results successfully submitted")
    failed: int = Field(..., ge=0, description="Results that failed to submit")
    max_buffer_size: int = Field(..., ge=1, description="Maximum buffer capacity")
    utilization_percent: float = Field(..., ge=0.0, le=100.0, description="Buffer utilization percentage")
    oldest_entry_age_seconds: Optional[int] = Field(None, description="Age of oldest buffered result")
    newest_entry_age_seconds: Optional[int] = Field(None, description="Age of newest buffered result")
    avg_retry_count: Optional[float] = Field(None, description="Average retry count for buffered results")
    flush_in_progress: bool = Field(..., description="Whether buffer flush is currently running")
    last_flush_at: Optional[datetime] = Field(None, description="Last buffer flush timestamp")
    buffered_results: List[BufferedResult] = Field(
        default_factory=list,
        description="List of currently buffered results (limited to 100)"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "total_buffered": 23,
                "pending_submission": 18,
                "submitted": 5,
                "failed": 0,
                "max_buffer_size": 1000,
                "utilization_percent": 2.3,
                "oldest_entry_age_seconds": 1800,
                "newest_entry_age_seconds": 120,
                "avg_retry_count": 1.5,
                "flush_in_progress": False,
                "last_flush_at": "2026-03-08T12:10:00Z",
                "buffered_results": [
                    {
                        "buffer_id": "buf_880e8400-e29b-41d4-a716-446655440000",
                        "task_id": "550e8400-e29b-41d4-a716-446655440000",
                        "peer_id": "12D3KooWD3bfqG7cRv5n2JhLz5gQ3r7Xx8YyZ9aA1bC2dE3fG4hI",
                        "buffered_at": "2026-03-08T12:10:00Z",
                        "retry_count": 2,
                        "last_retry_at": "2026-03-08T12:12:00Z",
                        "status": "PENDING"
                    }
                ]
            }
        }


class FlushBufferRequest(BaseModel):
    """Request to manually flush result buffer."""

    max_results: int = Field(
        default=100,
        ge=1,
        le=1000,
        description="Maximum number of results to flush in this operation"
    )
    force: bool = Field(
        default=False,
        description="Force flush even if DBOS appears unhealthy"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "max_results": 100,
                "force": False
            }
        }


class FlushBufferResponse(BaseModel):
    """Response after flushing buffer."""

    flushed_count: int = Field(..., ge=0, description="Number of results successfully flushed")
    failed_count: int = Field(..., ge=0, description="Number of results that failed to flush")
    remaining_buffered: int = Field(..., ge=0, description="Number of results still buffered")
    started_at: datetime = Field(..., description="When flush started")
    completed_at: datetime = Field(..., description="When flush completed")
    duration_seconds: float = Field(..., ge=0.0, description="Flush duration")

    class Config:
        json_schema_extra = {
            "example": {
                "flushed_count": 95,
                "failed_count": 5,
                "remaining_buffered": 120,
                "started_at": "2026-03-08T12:15:00Z",
                "completed_at": "2026-03-08T12:15:45Z",
                "duration_seconds": 45.3
            }
        }
