"""
Task Queue Visibility Endpoints

Provides visibility into task queue state, execution history,
and queue statistics for the UI dashboard.

Endpoints:
- GET /api/v1/tasks/queue - List tasks with filters
- GET /api/v1/tasks/active-leases - List active leases
- GET /api/v1/tasks/stats - Queue statistics
- GET /api/v1/tasks/{task_id} - Get task details
- GET /api/v1/tasks/{task_id}/history - Task execution history

Refs: Issue #86
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, and_, or_, desc

from backend.db.base import get_db
from backend.models.task_queue import Task, TaskLease, TaskStatus, TaskPriority
from backend.services.task_timeline_service import get_timeline_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["Task Queue", "Monitoring"])


def mask_token(token: str) -> str:
    """
    Mask lease token for security.

    Shows first 8 and last 4 characters with *** in the middle.
    """
    if not token or len(token) < 16:
        return "***"
    return f"{token[:8]}***{token[-4:]}"


def _ensure_timezone(dt: datetime) -> datetime:
    """
    Ensure datetime has timezone info (UTC if naive).

    Args:
        dt: Datetime object (may be naive or aware)

    Returns:
        Timezone-aware datetime in UTC
    """
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


# IMPORTANT: Define specific routes BEFORE parameterized routes
# to avoid path conflicts. E.g., /active-leases must come before /{task_id}


@router.get(
    "/queue",
    summary="List tasks in queue",
    description=(
        "List all tasks in the queue with optional filtering by status, "
        "priority, and assigned peer. Supports pagination."
    ),
)
async def list_tasks(
    status: Optional[List[TaskStatus]] = Query(None, description="Filter by task status"),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority"),
    peer_id: Optional[str] = Query(None, description="Filter by assigned peer ID"),
    limit: int = Query(100, ge=1, le=1000, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List tasks in the queue.

    Args:
        status: Filter by one or more task statuses
        priority: Filter by priority level
        peer_id: Filter by assigned peer ID
        limit: Maximum number of results to return
        offset: Number of results to skip (for pagination)
        db: Database session

    Returns:
        Dictionary containing tasks list, total count, and pagination info
    """
    # Build query
    query = db.query(Task)

    # Apply filters
    filters = []
    if status:
        filters.append(Task.status.in_(status))
    if priority:
        filters.append(Task.priority == priority)
    if peer_id:
        filters.append(Task.assigned_peer_id == peer_id)

    if filters:
        query = query.filter(and_(*filters))

    # Get total count
    total = query.count()

    # Apply ordering (newest first) and pagination
    tasks = (
        query.order_by(desc(Task.created_at))
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Serialize tasks
    tasks_data = []
    for task in tasks:
        task_dict = {
            "id": str(task.id),
            "task_type": task.task_type,
            "payload": task.payload,
            "priority": task.priority.value,
            "status": task.status.value,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "required_capabilities": task.required_capabilities,
            "assigned_peer_id": task.assigned_peer_id,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
            "duration_seconds": task.duration_seconds,
            "error_message": task.error_message,
            "error_type": task.error_type,
            "result": task.result,
            "created_at": task.created_at.isoformat() if task.created_at else None,
            "updated_at": task.updated_at.isoformat() if task.updated_at else None,
        }
        tasks_data.append(task_dict)

    return {
        "tasks": tasks_data,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/active-leases",
    summary="List active leases",
    description="List all currently active task leases with associated task information.",
)
async def list_active_leases(
    peer_id: Optional[str] = Query(None, description="Filter by peer ID"),
    limit: int = Query(100, ge=1, le=1000, description="Max results per page"),
    offset: int = Query(0, ge=0, description="Number of results to skip"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    List active leases.

    Args:
        peer_id: Optional filter by peer ID
        limit: Maximum number of results to return
        offset: Number of results to skip
        db: Database session

    Returns:
        Dictionary containing leases list, total count, and pagination info
    """
    # Build query for active leases
    query = db.query(TaskLease).filter(
        and_(
            TaskLease.is_expired == 0,
            TaskLease.is_revoked == 0,
            TaskLease.expires_at > datetime.now(timezone.utc),
        )
    )

    # Apply peer filter if provided
    if peer_id:
        query = query.filter(TaskLease.peer_id == peer_id)

    # Get total count
    total = query.count()

    # Apply ordering and pagination
    leases = (
        query.order_by(desc(TaskLease.created_at))
        .limit(limit)
        .offset(offset)
        .all()
    )

    # Serialize leases with task info
    leases_data = []
    for lease in leases:
        # Get associated task
        task = db.query(Task).filter(Task.id == lease.task_id).first()

        lease_dict = {
            "id": str(lease.id),
            "task_id": str(lease.task_id),
            "peer_id": lease.peer_id,
            "lease_token_masked": mask_token(lease.lease_token),
            "expires_at": lease.expires_at.isoformat(),
            "is_expired": bool(lease.is_expired),
            "is_revoked": bool(lease.is_revoked),
            "lease_duration_seconds": lease.lease_duration_seconds,
            "created_at": lease.created_at.isoformat() if lease.created_at else None,
            "updated_at": lease.updated_at.isoformat() if lease.updated_at else None,
        }

        # Add task info if available
        if task:
            lease_dict["task"] = {
                "task_type": task.task_type,
                "status": task.status.value,
                "priority": task.priority.value,
            }
        else:
            lease_dict["task"] = None

        leases_data.append(lease_dict)

    return {
        "leases": leases_data,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get(
    "/stats",
    summary="Get queue statistics",
    description=(
        "Get comprehensive queue statistics including status counts, "
        "time-series data for charts, and breakdowns by priority and type."
    ),
)
async def get_queue_stats(
    interval: str = Query("hourly", pattern="^(hourly|daily)$", description="Time series interval"),
    since: Optional[datetime] = Query(None, description="Only include tasks created after this time"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get queue statistics.

    Args:
        interval: Time series bucket interval (hourly or daily)
        since: Optional filter for tasks created after this time
        db: Database session

    Returns:
        Statistics including summary counts, time series, and breakdowns
    """
    # Build base query
    query = db.query(Task)
    if since:
        query = query.filter(Task.created_at >= since)

    tasks = query.all()

    # Calculate summary statistics
    status_counts = {}
    for status in TaskStatus:
        status_counts[status.value] = sum(1 for t in tasks if t.status == status)

    # Count active leases
    active_leases_count = (
        db.query(TaskLease)
        .filter(
            and_(
                TaskLease.is_expired == 0,
                TaskLease.is_revoked == 0,
                TaskLease.expires_at > datetime.now(timezone.utc),
            )
        )
        .count()
    )

    # Calculate average execution time for completed tasks
    completed_tasks = [t for t in tasks if t.status == TaskStatus.COMPLETED and t.duration_seconds is not None]
    avg_execution_time = None
    if completed_tasks:
        avg_execution_time = sum(t.duration_seconds for t in completed_tasks) / len(completed_tasks)

    summary = {
        "total_count": len(tasks),
        "queued_count": status_counts.get("queued", 0),
        "leased_count": status_counts.get("leased", 0),
        "running_count": status_counts.get("running", 0),
        "completed_count": status_counts.get("completed", 0),
        "failed_count": status_counts.get("failed", 0),
        "expired_count": status_counts.get("expired", 0),
        "permanently_failed_count": status_counts.get("permanently_failed", 0),
        "active_leases_count": active_leases_count,
        "avg_execution_time_seconds": avg_execution_time,
    }

    # Generate time series data
    now = datetime.now(timezone.utc)
    time_series = {}

    if interval == "hourly":
        # Last 24 hours, hourly buckets
        buckets = []
        for i in range(24):
            bucket_start = now - timedelta(hours=23-i)
            bucket_end = bucket_start + timedelta(hours=1)

            created = sum(
                1 for t in tasks
                if t.created_at and bucket_start <= _ensure_timezone(t.created_at) < bucket_end
            )
            completed = sum(
                1 for t in tasks
                if t.completed_at and bucket_start <= _ensure_timezone(t.completed_at) < bucket_end
                and t.status == TaskStatus.COMPLETED
            )
            failed = sum(
                1 for t in tasks
                if t.completed_at and bucket_start <= _ensure_timezone(t.completed_at) < bucket_end
                and t.status == TaskStatus.FAILED
            )

            buckets.append({
                "timestamp": bucket_start.isoformat(),
                "created": created,
                "completed": completed,
                "failed": failed,
            })

        time_series["hourly"] = buckets

    elif interval == "daily":
        # Last 30 days, daily buckets
        buckets = []
        for i in range(30):
            bucket_start = (now - timedelta(days=29-i)).replace(hour=0, minute=0, second=0, microsecond=0)
            bucket_end = bucket_start + timedelta(days=1)

            created = sum(
                1 for t in tasks
                if t.created_at and bucket_start <= _ensure_timezone(t.created_at) < bucket_end
            )
            completed = sum(
                1 for t in tasks
                if t.completed_at and bucket_start <= _ensure_timezone(t.completed_at) < bucket_end
                and t.status == TaskStatus.COMPLETED
            )
            failed = sum(
                1 for t in tasks
                if t.completed_at and bucket_start <= _ensure_timezone(t.completed_at) < bucket_end
                and t.status == TaskStatus.FAILED
            )

            buckets.append({
                "timestamp": bucket_start.isoformat(),
                "created": created,
                "completed": completed,
                "failed": failed,
            })

        time_series["daily"] = buckets

    # Breakdown by priority
    by_priority = {}
    for priority in TaskPriority:
        by_priority[priority.value] = sum(1 for t in tasks if t.priority == priority)

    # Breakdown by task type
    by_type = {}
    for task in tasks:
        task_type = task.task_type
        by_type[task_type] = by_type.get(task_type, 0) + 1

    return {
        "summary": summary,
        "time_series": time_series,
        "by_priority": by_priority,
        "by_type": by_type,
    }


@router.get(
    "/{task_id}",
    summary="Get task details",
    description="Get detailed information about a specific task, including current lease if active.",
)
async def get_task(
    task_id: UUID,
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get task details.

    Args:
        task_id: UUID of the task
        db: Database session

    Returns:
        Task details including current lease info if applicable

    Raises:
        HTTPException: 404 if task not found
    """
    task = db.query(Task).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Build task response
    task_dict = {
        "id": str(task.id),
        "task_type": task.task_type,
        "payload": task.payload,
        "priority": task.priority.value,
        "status": task.status.value,
        "retry_count": task.retry_count,
        "max_retries": task.max_retries,
        "required_capabilities": task.required_capabilities,
        "assigned_peer_id": task.assigned_peer_id,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "duration_seconds": task.duration_seconds,
        "error_message": task.error_message,
        "error_type": task.error_type,
        "result": task.result,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }

    # Include current lease if task is leased or running
    if task.status in [TaskStatus.LEASED, TaskStatus.RUNNING]:
        current_lease = (
            db.query(TaskLease)
            .filter(
                and_(
                    TaskLease.task_id == task.id,
                    TaskLease.is_expired == 0,
                    TaskLease.is_revoked == 0,
                )
            )
            .order_by(desc(TaskLease.created_at))
            .first()
        )

        if current_lease:
            task_dict["current_lease"] = {
                "id": str(current_lease.id),
                "peer_id": current_lease.peer_id,
                "lease_token_masked": mask_token(current_lease.lease_token),
                "expires_at": current_lease.expires_at.isoformat(),
                "lease_duration_seconds": current_lease.lease_duration_seconds,
                "created_at": current_lease.created_at.isoformat() if current_lease.created_at else None,
            }
        else:
            task_dict["current_lease"] = None
    else:
        task_dict["current_lease"] = None

    return task_dict


@router.get(
    "/{task_id}/history",
    summary="Get task execution history",
    description="Get timeline of events for a task from the timeline service.",
)
async def get_task_history(
    task_id: UUID,
    limit: int = Query(100, ge=1, le=1000, description="Max events to return"),
    offset: int = Query(0, ge=0, description="Number of events to skip"),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get task execution history.

    Args:
        task_id: UUID of the task
        limit: Maximum number of events to return
        offset: Number of events to skip
        db: Database session

    Returns:
        Timeline events for the task

    Raises:
        HTTPException: 404 if task not found
    """
    # Verify task exists
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")

    # Query timeline service
    timeline = get_timeline_service()
    events, total = timeline.query_events(
        task_id=str(task_id),
        limit=limit,
        offset=offset,
    )

    # Serialize events
    events_data = []
    for event in events:
        event_dict = {
            "event_type": event.event_type.value,
            "task_id": event.task_id,
            "peer_id": event.peer_id,
            "timestamp": event.timestamp.isoformat(),
            "metadata": event.metadata,
        }
        events_data.append(event_dict)

    return {
        "events": events_data,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
