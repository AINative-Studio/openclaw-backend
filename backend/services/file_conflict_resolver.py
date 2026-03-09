"""
File Conflict Resolver Service

Provides:
- File conflict detection between tasks
- Lock-based conflict resolution
- Multiple resolution strategies
- Merge conflict detection

Extracted from core/src/backend/app/agents/swarm/llm_agent_orchestrator.py
for Issue #114
"""

import asyncio
import logging
from typing import Dict, List, Set, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict

logger = logging.getLogger(__name__)


class ConflictResolutionStrategy(Enum):
    """Strategy for resolving file conflicts"""
    LAST_WRITE_WINS = "last_write_wins"
    FIRST_COME_FIRST_SERVED = "first_come_first_served"
    PRIORITY_BASED = "priority_based"
    MERGE_CHANGES = "merge_changes"
    COORDINATOR_DECIDES = "coordinator_decides"


class LockAcquisitionError(Exception):
    """Raised when unable to acquire a file lock"""
    pass


class MergeConflictError(Exception):
    """Raised when merge conflict cannot be resolved automatically"""
    pass


@dataclass
class FileAccessRequest:
    """Request for file access"""
    task_id: str
    agent_id: str
    file_path: str
    access_type: str  # "read" or "write"
    priority: int = 5
    timestamp: datetime = field(default_factory=lambda: datetime.now())


@dataclass
class FileLock:
    """Represents a lock on a file"""
    file_path: str
    holder_task_id: str
    holder_agent_id: str
    lock_type: str = "exclusive"  # "exclusive" or "shared"
    acquired_at: datetime = field(default_factory=lambda: datetime.now())
    expires_at: Optional[datetime] = None

    def __post_init__(self):
        if self.expires_at is None:
            # Default 5 minute expiration
            self.expires_at = self.acquired_at + timedelta(minutes=5)

    def is_expired(self) -> bool:
        """Check if lock has expired"""
        return datetime.now() > self.expires_at


@dataclass
class FileConflict:
    """Represents a file conflict between tasks"""
    file_path: str
    conflicting_tasks: List[str]
    conflict_type: str  # "concurrent_write", "read_write"
    detected_at: datetime = field(default_factory=lambda: datetime.now())

    @staticmethod
    def detect_conflict(
        request1: FileAccessRequest,
        request2: FileAccessRequest
    ) -> Optional['FileConflict']:
        """
        Detect if two file access requests conflict.

        Returns:
            FileConflict if conflict detected, None otherwise
        """
        # Different files = no conflict
        if request1.file_path != request2.file_path:
            return None

        # Same task = no conflict
        if request1.task_id == request2.task_id:
            return None

        # Read-read = no conflict
        if request1.access_type == "read" and request2.access_type == "read":
            return None

        # Determine conflict type
        if request1.access_type == "write" and request2.access_type == "write":
            conflict_type = "concurrent_write"
        else:
            conflict_type = "read_write"

        return FileConflict(
            file_path=request1.file_path,
            conflicting_tasks=[request1.task_id, request2.task_id],
            conflict_type=conflict_type
        )


@dataclass
class ConflictResolutionResult:
    """Result of conflict resolution"""
    file_path: str
    resolution: str  # "preempted", "queued", "merged", "queued_for_coordinator"
    winner_task_id: str
    loser_task_id: Optional[str] = None
    requires_manual_review: bool = False
    timestamp: datetime = field(default_factory=lambda: datetime.now())


@dataclass
class MergeResult:
    """Result of attempting to merge changes"""
    success: bool
    merged_changes: Dict[str, Any] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)


class FileConflictResolver:
    """
    Resolves file conflicts between concurrent tasks.

    Features:
    - Multiple conflict resolution strategies
    - Lock-based access control
    - Merge conflict detection
    - Priority-based resolution
    """

    def __init__(
        self,
        strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.PRIORITY_BASED,
        max_lock_duration: float = 300.0  # 5 minutes in seconds
    ):
        self.strategy = strategy
        self.max_lock_duration = max_lock_duration

        # Active locks
        self._locks: Dict[str, List[FileLock]] = defaultdict(list)
        self._lock_mutex = asyncio.Lock()

        # Queued requests
        self._queued_requests: Dict[str, List[FileAccessRequest]] = defaultdict(list)

        # Modification tracking
        self._modification_history: Dict[str, List[str]] = defaultdict(list)

        # Pending coordinator decisions
        self._pending_decisions: List[Dict[str, Any]] = []

        # Statistics
        self._stats = {
            "total_conflicts": 0,
            "resolved_conflicts": 0,
            "active_locks": 0,
            "expired_locks": 0
        }

        logger.info(f"FileConflictResolver initialized with strategy={strategy.value}")

    async def acquire_lock(
        self,
        request: FileAccessRequest,
        timeout: float = 30.0
    ) -> FileLock:
        """
        Acquire a lock on a file.

        Args:
            request: File access request
            timeout: Timeout in seconds

        Returns:
            FileLock if acquired

        Raises:
            LockAcquisitionError: If unable to acquire lock within timeout
        """
        start_time = asyncio.get_event_loop().time()

        while True:
            async with self._lock_mutex:
                # Check for existing locks
                existing_locks = self._locks.get(request.file_path, [])

                # Remove expired locks
                existing_locks = [lock for lock in existing_locks if not lock.is_expired()]
                self._locks[request.file_path] = existing_locks

                # Determine if we can acquire lock
                can_acquire = False

                if len(existing_locks) == 0:
                    can_acquire = True
                elif request.access_type == "read":
                    # Can acquire shared lock if all existing are shared
                    can_acquire = all(lock.lock_type == "shared" for lock in existing_locks)
                # else: write access with existing locks = cannot acquire

                if can_acquire:
                    # Create lock
                    lock_type = "shared" if request.access_type == "read" else "exclusive"
                    lock = FileLock(
                        file_path=request.file_path,
                        holder_task_id=request.task_id,
                        holder_agent_id=request.agent_id,
                        lock_type=lock_type,
                        expires_at=datetime.now() + timedelta(seconds=self.max_lock_duration)
                    )
                    self._locks[request.file_path].append(lock)
                    self._stats["active_locks"] += 1

                    logger.info(
                        f"Lock acquired: {request.file_path} by {request.task_id} "
                        f"({lock_type})"
                    )
                    return lock

            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                self._stats["total_conflicts"] += 1
                raise LockAcquisitionError(
                    f"Unable to acquire lock on {request.file_path} within {timeout}s"
                )

            # Wait before retry
            await asyncio.sleep(0.1)

    async def release_lock(self, lock: FileLock) -> None:
        """Release a file lock"""
        async with self._lock_mutex:
            locks = self._locks.get(lock.file_path, [])
            if lock in locks:
                locks.remove(lock)
                self._stats["active_locks"] -= 1
                logger.info(f"Lock released: {lock.file_path} by {lock.holder_task_id}")

    async def release_locks_by_task(self, task_id: str) -> None:
        """Release all locks held by a task"""
        async with self._lock_mutex:
            for file_path, locks in self._locks.items():
                locks_to_remove = [lock for lock in locks if lock.holder_task_id == task_id]
                for lock in locks_to_remove:
                    locks.remove(lock)
                    self._stats["active_locks"] -= 1
                    logger.info(f"Lock released: {file_path} by {task_id}")

    async def cleanup_expired_locks(self) -> int:
        """Clean up expired locks, return count cleaned"""
        count = 0
        async with self._lock_mutex:
            for file_path, locks in list(self._locks.items()):
                expired = [lock for lock in locks if lock.is_expired()]
                for lock in expired:
                    locks.remove(lock)
                    count += 1
                    self._stats["active_locks"] -= 1
                    self._stats["expired_locks"] += 1

                if len(locks) == 0:
                    del self._locks[file_path]

        if count > 0:
            logger.info(f"Cleaned up {count} expired locks")
        return count

    def get_active_locks(self) -> List[FileLock]:
        """Get all active locks"""
        all_locks = []
        for locks in self._locks.values():
            all_locks.extend([lock for lock in locks if not lock.is_expired()])
        return all_locks

    async def queue_request(self, request: FileAccessRequest) -> None:
        """Queue a file access request"""
        self._queued_requests[request.file_path].append(request)
        logger.info(f"Request queued: {request.file_path} by {request.task_id}")

    def get_queued_requests(self, file_path: str) -> List[FileAccessRequest]:
        """Get queued requests for a file"""
        return self._queued_requests.get(file_path, []).copy()

    async def process_queue(self, file_path: str) -> None:
        """Process queued requests for a file"""
        queued = self._queued_requests.get(file_path, [])
        if not queued:
            return

        # Try to acquire lock for first queued request
        request = queued[0]
        try:
            await self.acquire_lock(request, timeout=0.1)
            # Success - remove from queue
            queued.pop(0)
            logger.info(f"Processed queued request: {file_path} by {request.task_id}")
        except LockAcquisitionError:
            # Still locked, leave in queue
            pass

    async def resolve_conflict(
        self,
        request: FileAccessRequest,
        conflicting_request: FileAccessRequest
    ) -> ConflictResolutionResult:
        """
        Resolve conflict between two file access requests.

        Args:
            request: New request
            conflicting_request: Existing conflicting request

        Returns:
            ConflictResolutionResult
        """
        self._stats["total_conflicts"] += 1

        # Apply resolution strategy
        if self.strategy == ConflictResolutionStrategy.PRIORITY_BASED:
            return await self._resolve_priority_based(request, conflicting_request)
        elif self.strategy == ConflictResolutionStrategy.FIRST_COME_FIRST_SERVED:
            return await self._resolve_first_come_first_served(request, conflicting_request)
        elif self.strategy == ConflictResolutionStrategy.LAST_WRITE_WINS:
            return await self._resolve_last_write_wins(request, conflicting_request)
        elif self.strategy == ConflictResolutionStrategy.MERGE_CHANGES:
            return await self._resolve_merge_changes(request, conflicting_request)
        elif self.strategy == ConflictResolutionStrategy.COORDINATOR_DECIDES:
            return await self._resolve_coordinator_decides(request, conflicting_request)
        else:
            # Default to FCFS
            return await self._resolve_first_come_first_served(request, conflicting_request)

    async def _resolve_priority_based(
        self,
        request: FileAccessRequest,
        conflicting_request: FileAccessRequest
    ) -> ConflictResolutionResult:
        """Resolve based on task priority"""
        if request.priority > conflicting_request.priority:
            # New request has higher priority - preempt
            await self.release_locks_by_task(conflicting_request.task_id)
            self._stats["resolved_conflicts"] += 1
            return ConflictResolutionResult(
                file_path=request.file_path,
                resolution="preempted",
                winner_task_id=request.task_id,
                loser_task_id=conflicting_request.task_id
            )
        else:
            # Existing request has higher/equal priority - queue new request
            return ConflictResolutionResult(
                file_path=request.file_path,
                resolution="queued",
                winner_task_id=conflicting_request.task_id,
                loser_task_id=request.task_id
            )

    async def _resolve_first_come_first_served(
        self,
        request: FileAccessRequest,
        conflicting_request: FileAccessRequest
    ) -> ConflictResolutionResult:
        """First request wins, queue new request"""
        return ConflictResolutionResult(
            file_path=request.file_path,
            resolution="queued",
            winner_task_id=conflicting_request.task_id,
            loser_task_id=request.task_id
        )

    async def _resolve_last_write_wins(
        self,
        request: FileAccessRequest,
        conflicting_request: FileAccessRequest
    ) -> ConflictResolutionResult:
        """Last request wins, preempt existing"""
        await self.release_locks_by_task(conflicting_request.task_id)
        self._stats["resolved_conflicts"] += 1
        return ConflictResolutionResult(
            file_path=request.file_path,
            resolution="preempted",
            winner_task_id=request.task_id,
            loser_task_id=conflicting_request.task_id
        )

    async def _resolve_merge_changes(
        self,
        request: FileAccessRequest,
        conflicting_request: FileAccessRequest
    ) -> ConflictResolutionResult:
        """Attempt to merge changes"""
        # This is a simplified implementation
        # In production, would need actual file content analysis
        return ConflictResolutionResult(
            file_path=request.file_path,
            resolution="queued",  # Conservative - queue for now
            winner_task_id=conflicting_request.task_id,
            loser_task_id=request.task_id
        )

    async def _resolve_coordinator_decides(
        self,
        request: FileAccessRequest,
        conflicting_request: FileAccessRequest
    ) -> ConflictResolutionResult:
        """Queue for coordinator decision"""
        self._pending_decisions.append({
            "file_path": request.file_path,
            "request": request,
            "conflicting_request": conflicting_request,
            "timestamp": datetime.now()
        })

        return ConflictResolutionResult(
            file_path=request.file_path,
            resolution="queued_for_coordinator",
            winner_task_id=conflicting_request.task_id,
            loser_task_id=request.task_id,
            requires_manual_review=True
        )

    def detect_merge_conflict(
        self,
        file_path: str,
        changes1: Dict[str, Any],
        changes2: Dict[str, Any]
    ) -> bool:
        """
        Detect if two sets of changes conflict.

        Args:
            file_path: File being modified
            changes1: First set of changes
            changes2: Second set of changes

        Returns:
            True if changes conflict
        """
        # Check for same-line conflicts
        line1 = changes1.get("line")
        line2 = changes2.get("line")

        if line1 is not None and line2 is not None:
            return line1 == line2

        # Check for overlapping line ranges
        lines1 = set(changes1.get("lines", []))
        lines2 = set(changes2.get("lines", []))

        if lines1 and lines2:
            return bool(lines1 & lines2)

        return False

    async def attempt_merge(
        self,
        file_path: str,
        changes1: Dict[str, Any],
        changes2: Dict[str, Any]
    ) -> MergeResult:
        """
        Attempt to merge two sets of changes.

        Args:
            file_path: File being modified
            changes1: First set of changes
            changes2: Second set of changes

        Returns:
            MergeResult

        Raises:
            MergeConflictError: If changes cannot be merged
        """
        if self.detect_merge_conflict(file_path, changes1, changes2):
            raise MergeConflictError(
                f"Cannot merge conflicting changes to {file_path}"
            )

        # Non-conflicting changes can be merged
        merged_changes = {
            **changes1,
            **changes2
        }

        return MergeResult(
            success=True,
            merged_changes=merged_changes
        )

    def detect_conflicts(
        self,
        tasks_files: Dict[str, Set[str]]
    ) -> List[FileConflict]:
        """
        Detect conflicts between multiple tasks.

        Args:
            tasks_files: Map of task_id -> set of file paths

        Returns:
            List of FileConflict objects
        """
        conflicts = []
        file_to_tasks: Dict[str, List[str]] = defaultdict(list)

        # Build reverse mapping
        for task_id, files in tasks_files.items():
            for file_path in files:
                file_to_tasks[file_path].append(task_id)

        # Find conflicts
        for file_path, tasks in file_to_tasks.items():
            if len(tasks) > 1:
                conflicts.append(FileConflict(
                    file_path=file_path,
                    conflicting_tasks=tasks,
                    conflict_type="concurrent_write"  # Assume write conflicts
                ))

        return conflicts

    async def track_modification(self, task_id: str, file_path: str) -> None:
        """Track file modification by a task"""
        self._modification_history[file_path].append(task_id)
        logger.debug(f"Tracked modification: {file_path} by {task_id}")

    def get_modification_history(self, file_path: str) -> List[str]:
        """Get modification history for a file"""
        return self._modification_history.get(file_path, []).copy()

    def get_statistics(self) -> Dict[str, Any]:
        """Get conflict resolution statistics"""
        return {
            **self._stats,
            "pending_decisions": len(self._pending_decisions),
            "queued_requests": sum(len(q) for q in self._queued_requests.values())
        }

    def get_pending_decisions(self) -> List[Dict[str, Any]]:
        """Get conflicts pending coordinator decision"""
        return [
            {
                "file_path": d["file_path"],
                "request_task": d["request"].task_id,
                "conflicting_task": d["conflicting_request"].task_id,
                "timestamp": d["timestamp"]
            }
            for d in self._pending_decisions
        ]

    async def apply_decision(
        self,
        file_path: str,
        winner_task_id: str,
        decision: str
    ) -> None:
        """
        Apply coordinator decision to a conflict.

        Args:
            file_path: File with conflict
            winner_task_id: Task that wins the conflict
            decision: Decision type (e.g., "preempt_task_1")
        """
        # Remove from pending
        self._pending_decisions = [
            d for d in self._pending_decisions
            if d["file_path"] != file_path
        ]

        # Apply decision based on type
        if "preempt" in decision:
            # Find task to preempt (extract from decision string)
            for lock in self._locks.get(file_path, []):
                if lock.holder_task_id != winner_task_id:
                    await self.release_lock(lock)

        self._stats["resolved_conflicts"] += 1
        logger.info(f"Applied coordinator decision: {file_path} -> {winner_task_id}")

    async def cleanup_task(self, task_id: str) -> None:
        """Clean up all resources for a task"""
        await self.release_locks_by_task(task_id)

        # Remove from queued requests
        for file_path, queue in self._queued_requests.items():
            self._queued_requests[file_path] = [
                req for req in queue if req.task_id != task_id
            ]

        logger.info(f"Cleaned up resources for task {task_id}")

    async def acquire_locks_bulk(
        self,
        task_id: str,
        agent_id: str,
        file_paths: List[str],
        access_type: str = "write",
        priority: int = 5
    ) -> List[FileLock]:
        """
        Acquire locks for multiple files.

        Args:
            task_id: Task ID
            agent_id: Agent ID
            file_paths: List of file paths
            access_type: Access type
            priority: Priority

        Returns:
            List of acquired locks
        """
        locks = []
        for file_path in file_paths:
            request = FileAccessRequest(
                task_id=task_id,
                agent_id=agent_id,
                file_path=file_path,
                access_type=access_type,
                priority=priority
            )
            lock = await self.acquire_lock(request)
            locks.append(lock)

        return locks
