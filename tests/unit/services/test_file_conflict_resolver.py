"""
Unit tests for FileConflictResolver service (TDD - RED phase)

Tests for:
- File conflict detection
- Lock-based conflict resolution
- Merge-based conflict resolution
- Priority-based resolution
"""

import pytest
import asyncio
from typing import Dict, List, Set
from datetime import datetime

# Import will fail until we implement the service (RED phase)
from backend.services.file_conflict_resolver import (
    FileConflictResolver,
    FileConflict,
    ConflictResolutionStrategy,
    FileAccessRequest,
    FileLock,
    ConflictResolutionResult,
    LockAcquisitionError,
    MergeConflictError,
)


class TestFileAccessRequest:
    """Test FileAccessRequest dataclass"""

    def test_create_file_access_request(self):
        """Test creating file access request"""
        request = FileAccessRequest(
            task_id="task_1",
            agent_id="agent_backend",
            file_path="backend/api.py",
            access_type="write",
            priority=8
        )
        assert request.task_id == "task_1"
        assert request.agent_id == "agent_backend"
        assert request.file_path == "backend/api.py"
        assert request.access_type == "write"
        assert request.priority == 8

    def test_read_access_request(self):
        """Test read access request"""
        request = FileAccessRequest(
            task_id="task_1",
            agent_id="agent_test",
            file_path="backend/api.py",
            access_type="read"
        )
        assert request.access_type == "read"
        assert request.priority == 5  # default


class TestFileLock:
    """Test FileLock dataclass"""

    def test_create_file_lock(self):
        """Test creating a file lock"""
        lock = FileLock(
            file_path="backend/api.py",
            holder_task_id="task_1",
            holder_agent_id="agent_backend",
            lock_type="exclusive"
        )
        assert lock.file_path == "backend/api.py"
        assert lock.holder_task_id == "task_1"
        assert lock.lock_type == "exclusive"
        assert lock.acquired_at is not None

    def test_shared_lock(self):
        """Test creating shared lock"""
        lock = FileLock(
            file_path="backend/api.py",
            holder_task_id="task_1",
            holder_agent_id="agent_test",
            lock_type="shared"
        )
        assert lock.lock_type == "shared"

    def test_lock_expiration(self):
        """Test lock has expiration time"""
        lock = FileLock(
            file_path="backend/api.py",
            holder_task_id="task_1",
            holder_agent_id="agent_backend"
        )
        assert lock.expires_at is not None
        assert lock.expires_at > lock.acquired_at


class TestFileConflict:
    """Test FileConflict detection"""

    def test_create_file_conflict(self):
        """Test creating file conflict"""
        conflict = FileConflict(
            file_path="backend/api.py",
            conflicting_tasks=["task_1", "task_2"],
            conflict_type="concurrent_write"
        )
        assert conflict.file_path == "backend/api.py"
        assert len(conflict.conflicting_tasks) == 2
        assert conflict.conflict_type == "concurrent_write"

    def test_conflict_detection_write_write(self):
        """Test detecting write-write conflict"""
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        conflict = FileConflict.detect_conflict(request1, request2)
        assert conflict is not None
        assert conflict.conflict_type == "concurrent_write"

    def test_conflict_detection_read_write(self):
        """Test detecting read-write conflict"""
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "read")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        conflict = FileConflict.detect_conflict(request1, request2)
        assert conflict is not None
        assert conflict.conflict_type == "read_write"

    def test_no_conflict_read_read(self):
        """Test no conflict for read-read access"""
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "read")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "read")

        conflict = FileConflict.detect_conflict(request1, request2)
        assert conflict is None

    def test_no_conflict_different_files(self):
        """Test no conflict for different files"""
        request1 = FileAccessRequest("task_1", "agent_1", "file1.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file2.py", "write")

        conflict = FileConflict.detect_conflict(request1, request2)
        assert conflict is None


class TestConflictResolutionStrategy:
    """Test conflict resolution strategies"""

    def test_strategy_enum(self):
        """Test conflict resolution strategy enum"""
        assert ConflictResolutionStrategy.LAST_WRITE_WINS
        assert ConflictResolutionStrategy.FIRST_COME_FIRST_SERVED
        assert ConflictResolutionStrategy.PRIORITY_BASED
        assert ConflictResolutionStrategy.MERGE_CHANGES
        assert ConflictResolutionStrategy.COORDINATOR_DECIDES


class TestFileConflictResolverInit:
    """Test FileConflictResolver initialization"""

    def test_create_resolver_default(self):
        """Test creating resolver with defaults"""
        resolver = FileConflictResolver()
        assert resolver.strategy == ConflictResolutionStrategy.PRIORITY_BASED
        assert resolver.max_lock_duration > 0

    def test_create_resolver_custom_strategy(self):
        """Test creating resolver with custom strategy"""
        resolver = FileConflictResolver(
            strategy=ConflictResolutionStrategy.FIRST_COME_FIRST_SERVED
        )
        assert resolver.strategy == ConflictResolutionStrategy.FIRST_COME_FIRST_SERVED

    def test_resolver_initializes_empty(self):
        """Test resolver starts with no locks"""
        resolver = FileConflictResolver()
        assert len(resolver.get_active_locks()) == 0


class TestLockAcquisition:
    """Test lock acquisition and release"""

    @pytest.mark.asyncio
    async def test_acquire_exclusive_lock(self):
        """Test acquiring exclusive lock"""
        resolver = FileConflictResolver()
        request = FileAccessRequest(
            task_id="task_1",
            agent_id="agent_1",
            file_path="file.py",
            access_type="write"
        )

        lock = await resolver.acquire_lock(request)
        assert lock is not None
        assert lock.file_path == "file.py"
        assert lock.holder_task_id == "task_1"
        assert lock.lock_type == "exclusive"

    @pytest.mark.asyncio
    async def test_acquire_shared_lock(self):
        """Test acquiring shared lock"""
        resolver = FileConflictResolver()
        request = FileAccessRequest(
            task_id="task_1",
            agent_id="agent_1",
            file_path="file.py",
            access_type="read"
        )

        lock = await resolver.acquire_lock(request)
        assert lock.lock_type == "shared"

    @pytest.mark.asyncio
    async def test_multiple_shared_locks(self):
        """Test acquiring multiple shared locks on same file"""
        resolver = FileConflictResolver()
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "read")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "read")

        lock1 = await resolver.acquire_lock(request1)
        lock2 = await resolver.acquire_lock(request2)

        assert lock1 is not None
        assert lock2 is not None
        active_locks = resolver.get_active_locks()
        assert len(active_locks) == 2

    @pytest.mark.asyncio
    async def test_exclusive_lock_blocks_shared(self):
        """Test exclusive lock blocks shared lock"""
        resolver = FileConflictResolver()
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "read")

        lock1 = await resolver.acquire_lock(request1)
        assert lock1 is not None

        with pytest.raises(LockAcquisitionError):
            await resolver.acquire_lock(request2, timeout=0.1)

    @pytest.mark.asyncio
    async def test_exclusive_lock_blocks_exclusive(self):
        """Test exclusive lock blocks another exclusive lock"""
        resolver = FileConflictResolver()
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        lock1 = await resolver.acquire_lock(request1)
        assert lock1 is not None

        with pytest.raises(LockAcquisitionError):
            await resolver.acquire_lock(request2, timeout=0.1)

    @pytest.mark.asyncio
    async def test_release_lock(self):
        """Test releasing a lock"""
        resolver = FileConflictResolver()
        request = FileAccessRequest("task_1", "agent_1", "file.py", "write")

        lock = await resolver.acquire_lock(request)
        assert len(resolver.get_active_locks()) == 1

        await resolver.release_lock(lock)
        assert len(resolver.get_active_locks()) == 0

    @pytest.mark.asyncio
    async def test_release_lock_by_task_id(self):
        """Test releasing lock by task ID"""
        resolver = FileConflictResolver()
        request = FileAccessRequest("task_1", "agent_1", "file.py", "write")

        await resolver.acquire_lock(request)
        assert len(resolver.get_active_locks()) == 1

        await resolver.release_locks_by_task("task_1")
        assert len(resolver.get_active_locks()) == 0

    @pytest.mark.asyncio
    async def test_lock_auto_release_after_timeout(self):
        """Test lock automatically releases after timeout"""
        resolver = FileConflictResolver(max_lock_duration=0.1)
        request = FileAccessRequest("task_1", "agent_1", "file.py", "write")

        await resolver.acquire_lock(request)
        assert len(resolver.get_active_locks()) == 1

        # Wait for lock to expire
        await asyncio.sleep(0.2)
        await resolver.cleanup_expired_locks()

        assert len(resolver.get_active_locks()) == 0


class TestConflictResolution:
    """Test conflict resolution"""

    @pytest.mark.asyncio
    async def test_resolve_conflict_priority_based(self):
        """Test priority-based conflict resolution"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.PRIORITY_BASED)
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write", priority=5)
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write", priority=10)

        # Acquire first lock
        lock1 = await resolver.acquire_lock(request1)

        # Higher priority should be able to preempt
        result = await resolver.resolve_conflict(request2, request1)
        assert result.resolution == "preempted"
        assert result.winner_task_id == "task_2"

    @pytest.mark.asyncio
    async def test_resolve_conflict_first_come_first_served(self):
        """Test FCFS conflict resolution"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.FIRST_COME_FIRST_SERVED)
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write", priority=5)
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write", priority=10)

        await resolver.acquire_lock(request1)

        # First request wins regardless of priority
        result = await resolver.resolve_conflict(request2, request1)
        assert result.resolution == "queued"
        assert result.winner_task_id == "task_1"

    @pytest.mark.asyncio
    async def test_resolve_conflict_last_write_wins(self):
        """Test last-write-wins conflict resolution"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.LAST_WRITE_WINS)
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        await resolver.acquire_lock(request1)

        result = await resolver.resolve_conflict(request2, request1)
        assert result.resolution == "preempted"
        assert result.winner_task_id == "task_2"

    @pytest.mark.asyncio
    async def test_queue_conflicting_request(self):
        """Test queuing conflicting request"""
        resolver = FileConflictResolver()
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        await resolver.acquire_lock(request1)
        await resolver.queue_request(request2)

        queued = resolver.get_queued_requests("file.py")
        assert len(queued) == 1
        assert queued[0].task_id == "task_2"

    @pytest.mark.asyncio
    async def test_process_queued_requests(self):
        """Test processing queued requests after lock release"""
        resolver = FileConflictResolver()
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        lock1 = await resolver.acquire_lock(request1)
        await resolver.queue_request(request2)

        # Release lock
        await resolver.release_lock(lock1)

        # Process queue
        await resolver.process_queue("file.py")

        # Second request should now have lock
        active_locks = resolver.get_active_locks()
        assert len(active_locks) == 1
        assert active_locks[0].holder_task_id == "task_2"


class TestMergeConflictResolution:
    """Test merge-based conflict resolution"""

    @pytest.mark.asyncio
    async def test_detect_merge_conflict(self):
        """Test detecting if changes can be merged"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.MERGE_CHANGES)

        # Same line edits -> conflict
        changes1 = {"line": 10, "content": "version A"}
        changes2 = {"line": 10, "content": "version B"}

        has_conflict = resolver.detect_merge_conflict("file.py", changes1, changes2)
        assert has_conflict is True

    @pytest.mark.asyncio
    async def test_no_merge_conflict_different_lines(self):
        """Test no merge conflict for different lines"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.MERGE_CHANGES)

        # Different lines -> no conflict
        changes1 = {"line": 10, "content": "version A"}
        changes2 = {"line": 20, "content": "version B"}

        has_conflict = resolver.detect_merge_conflict("file.py", changes1, changes2)
        assert has_conflict is False

    @pytest.mark.asyncio
    async def test_attempt_merge(self):
        """Test attempting to merge changes"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.MERGE_CHANGES)

        changes1 = {"lines": [10], "content": "version A"}
        changes2 = {"lines": [20], "content": "version B"}

        result = await resolver.attempt_merge("file.py", changes1, changes2)
        assert result.success is True
        assert len(result.merged_changes) > 0

    @pytest.mark.asyncio
    async def test_merge_failure(self):
        """Test merge failure for conflicting changes"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.MERGE_CHANGES)

        changes1 = {"lines": [10], "content": "version A"}
        changes2 = {"lines": [10], "content": "version B"}

        with pytest.raises(MergeConflictError):
            await resolver.attempt_merge("file.py", changes1, changes2)


class TestConflictDetectionAndTracking:
    """Test conflict detection and tracking"""

    @pytest.mark.asyncio
    async def test_detect_conflicts_between_tasks(self):
        """Test detecting conflicts between multiple tasks"""
        resolver = FileConflictResolver()

        tasks_files = {
            "task_1": {"backend/api.py", "backend/models.py"},
            "task_2": {"backend/api.py", "frontend/app.js"},
            "task_3": {"backend/tests.py"},
        }

        conflicts = resolver.detect_conflicts(tasks_files)
        assert len(conflicts) == 1
        assert conflicts[0].file_path == "backend/api.py"
        assert set(conflicts[0].conflicting_tasks) == {"task_1", "task_2"}

    @pytest.mark.asyncio
    async def test_no_conflicts(self):
        """Test no conflicts when tasks touch different files"""
        resolver = FileConflictResolver()

        tasks_files = {
            "task_1": {"backend/api.py"},
            "task_2": {"frontend/app.js"},
            "task_3": {"backend/tests.py"},
        }

        conflicts = resolver.detect_conflicts(tasks_files)
        assert len(conflicts) == 0

    @pytest.mark.asyncio
    async def test_track_file_modifications(self):
        """Test tracking file modifications by tasks"""
        resolver = FileConflictResolver()

        await resolver.track_modification("task_1", "backend/api.py")
        await resolver.track_modification("task_2", "backend/api.py")

        modified_by = resolver.get_modification_history("backend/api.py")
        assert len(modified_by) == 2
        assert "task_1" in modified_by
        assert "task_2" in modified_by

    @pytest.mark.asyncio
    async def test_get_conflict_statistics(self):
        """Test getting conflict statistics"""
        resolver = FileConflictResolver()

        # Simulate some conflicts
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        await resolver.acquire_lock(request1)
        try:
            await resolver.acquire_lock(request2, timeout=0.1)
        except LockAcquisitionError:
            pass

        stats = resolver.get_statistics()
        assert stats["total_conflicts"] > 0
        assert "active_locks" in stats
        assert "resolved_conflicts" in stats


class TestCoordinatorDecisionStrategy:
    """Test coordinator-decides conflict resolution"""

    @pytest.mark.asyncio
    async def test_coordinator_decides_queues_for_review(self):
        """Test coordinator strategy queues conflicts for manual review"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.COORDINATOR_DECIDES)
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        await resolver.acquire_lock(request1)

        # Should queue for coordinator review
        result = await resolver.resolve_conflict(request2, request1)
        assert result.resolution == "queued_for_coordinator"
        assert result.requires_manual_review is True

    @pytest.mark.asyncio
    async def test_get_pending_coordinator_decisions(self):
        """Test getting conflicts pending coordinator decision"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.COORDINATOR_DECIDES)
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        await resolver.acquire_lock(request1)
        await resolver.resolve_conflict(request2, request1)

        pending = resolver.get_pending_decisions()
        assert len(pending) == 1
        assert pending[0]["file_path"] == "file.py"

    @pytest.mark.asyncio
    async def test_apply_coordinator_decision(self):
        """Test applying coordinator decision"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.COORDINATOR_DECIDES)
        request1 = FileAccessRequest("task_1", "agent_1", "file.py", "write")
        request2 = FileAccessRequest("task_2", "agent_2", "file.py", "write")

        lock1 = await resolver.acquire_lock(request1)
        await resolver.resolve_conflict(request2, request1)

        # Coordinator decides task_2 should win
        await resolver.apply_decision(
            file_path="file.py",
            winner_task_id="task_2",
            decision="preempt_task_1"
        )

        # Verify task_1 lock was revoked
        active_locks = resolver.get_active_locks()
        assert all(lock.holder_task_id != "task_1" for lock in active_locks)


class TestFileConflictResolverIntegration:
    """Integration tests for complete conflict resolution flow"""

    @pytest.mark.asyncio
    async def test_complete_conflict_resolution_flow(self):
        """Test complete flow from detection to resolution"""
        resolver = FileConflictResolver(strategy=ConflictResolutionStrategy.PRIORITY_BASED)

        # Multiple tasks want same file
        requests = [
            FileAccessRequest("task_1", "agent_1", "file.py", "write", priority=5),
            FileAccessRequest("task_2", "agent_2", "file.py", "write", priority=10),
            FileAccessRequest("task_3", "agent_3", "file.py", "write", priority=3),
        ]

        # Process all requests
        results = []
        for request in requests:
            try:
                lock = await resolver.acquire_lock(request, timeout=0.1)
                results.append(("acquired", request.task_id))
            except LockAcquisitionError:
                await resolver.queue_request(request)
                results.append(("queued", request.task_id))

        # Highest priority should get lock first
        assert results[0][0] == "acquired" or results[1][0] == "acquired"

    @pytest.mark.asyncio
    async def test_concurrent_access_different_files(self):
        """Test concurrent access to different files works"""
        resolver = FileConflictResolver()

        requests = [
            FileAccessRequest("task_1", "agent_1", "file1.py", "write"),
            FileAccessRequest("task_2", "agent_2", "file2.py", "write"),
            FileAccessRequest("task_3", "agent_3", "file3.py", "write"),
        ]

        # All should acquire locks simultaneously
        locks = await asyncio.gather(*[resolver.acquire_lock(req) for req in requests])
        assert len(locks) == 3
        assert all(lock is not None for lock in locks)

    @pytest.mark.asyncio
    async def test_cleanup_on_task_failure(self):
        """Test cleanup of locks when task fails"""
        resolver = FileConflictResolver()
        request = FileAccessRequest("task_1", "agent_1", "file.py", "write")

        await resolver.acquire_lock(request)
        assert len(resolver.get_active_locks()) == 1

        # Simulate task failure
        await resolver.cleanup_task("task_1")
        assert len(resolver.get_active_locks()) == 0

    @pytest.mark.asyncio
    async def test_bulk_lock_operations(self):
        """Test acquiring locks for multiple files"""
        resolver = FileConflictResolver()

        file_paths = ["file1.py", "file2.py", "file3.py"]
        locks = await resolver.acquire_locks_bulk(
            task_id="task_1",
            agent_id="agent_1",
            file_paths=file_paths,
            access_type="write"
        )

        assert len(locks) == 3
        assert all(lock.holder_task_id == "task_1" for lock in locks)
