"""
Result Buffer Service

Local SQLite-based buffer for storing task results during DBOS partition scenarios.
Implements FIFO queue with periodic flush attempts and retry logic.

Refs #E6-S4
"""

import logging
import asyncio
import sqlite3
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class BufferFullError(Exception):
    """Raised when buffer capacity is exceeded"""
    pass


@dataclass
class BufferMetrics:
    """Buffer metrics for monitoring"""
    current_size: int
    max_capacity: int
    utilization_percent: float
    oldest_result_age_seconds: Optional[float]
    newest_result_age_seconds: Optional[float]


class ResultBufferService:
    """
    Local SQLite buffer for task results during DBOS partition

    Features:
    - SQLite-based persistent storage
    - FIFO buffer management
    - Capacity limits with overflow protection
    - Periodic flush attempts
    - Retry mechanism with exponential backoff
    - Lease token tracking
    - Metadata preservation
    """

    def __init__(
        self,
        db_path: str = "/tmp/openclaw_result_buffer.db",
        max_buffer_size: int = 10000,
        flush_interval: int = 30,
        max_retry_attempts: int = 3
    ):
        """
        Initialize result buffer service

        Args:
            db_path: Path to SQLite database file
            max_buffer_size: Maximum number of buffered results
            flush_interval: Interval between flush attempts (seconds)
            max_retry_attempts: Maximum retry attempts for failed flushes
        """
        self.db_path = db_path
        self.max_buffer_size = max_buffer_size
        self.flush_interval = flush_interval
        self.max_retry_attempts = max_retry_attempts

        self._flush_task: Optional[asyncio.Task] = None
        self._flush_running = False

        # Initialize database
        self._init_database()

        logger.info(
            f"ResultBufferService initialized: "
            f"db={db_path}, capacity={max_buffer_size}, "
            f"flush_interval={flush_interval}s"
        )

    def _init_database(self):
        """Initialize SQLite database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Create buffered_results table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS buffered_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                lease_token TEXT NOT NULL,
                result_data TEXT NOT NULL,
                metadata TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                retry_count INTEGER DEFAULT 0,
                last_retry_at TIMESTAMP,
                status TEXT DEFAULT 'pending',
                UNIQUE(task_id)
            )
        """)

        # Create index for efficient FIFO retrieval
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_created_at
            ON buffered_results(created_at)
        """)

        # Create index for status queries
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_status
            ON buffered_results(status)
        """)

        conn.commit()
        conn.close()

        logger.debug(f"Database initialized at {self.db_path}")

    async def buffer_result(
        self,
        task_id: str,
        agent_id: str,
        lease_token: str,
        result: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Buffer a task result during partition

        Args:
            task_id: Task unique identifier
            agent_id: Agent unique identifier
            lease_token: Task lease token
            result: Task result data
            metadata: Additional metadata

        Returns:
            Buffer entry ID

        Raises:
            BufferFullError: If buffer is at capacity
        """
        # Check capacity
        current_size = await self.get_buffer_size()
        if current_size >= self.max_buffer_size:
            raise BufferFullError(
                f"Buffer capacity exceeded (current={current_size}, max={self.max_buffer_size})"
            )

        # Serialize data
        result_json = json.dumps(result)
        metadata_json = json.dumps(metadata) if metadata else None

        # Insert into database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        try:
            cursor.execute("""
                INSERT INTO buffered_results
                (task_id, agent_id, lease_token, result_data, metadata)
                VALUES (?, ?, ?, ?, ?)
            """, (task_id, agent_id, lease_token, result_json, metadata_json))

            buffer_id = cursor.lastrowid
            conn.commit()

            logger.info(
                f"Buffered result: task_id={task_id}, agent_id={agent_id}, "
                f"buffer_id={buffer_id}, size={current_size + 1}/{self.max_buffer_size}"
            )

            return buffer_id

        except sqlite3.IntegrityError as e:
            logger.error(f"Failed to buffer result (duplicate task_id?): {e}")
            raise
        finally:
            conn.close()

    async def get_buffer_size(self) -> int:
        """
        Get current buffer size

        Returns:
            Number of buffered results
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*) FROM buffered_results
            WHERE status = 'pending'
        """)

        count = cursor.fetchone()[0]
        conn.close()

        return count

    async def get_buffered_result(self, buffer_id: int) -> Optional[Dict[str, Any]]:
        """
        Get a specific buffered result by ID

        Args:
            buffer_id: Buffer entry ID

        Returns:
            Buffered result details or None if not found
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, task_id, agent_id, lease_token, result_data,
                   metadata, created_at, retry_count, last_retry_at, status
            FROM buffered_results
            WHERE id = ?
        """, (buffer_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_dict(row)

    async def get_all_buffered_results(self) -> List[Dict[str, Any]]:
        """
        Get all buffered results in FIFO order

        Returns:
            List of buffered results (oldest first)
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, task_id, agent_id, lease_token, result_data,
                   metadata, created_at, retry_count, last_retry_at, status
            FROM buffered_results
            WHERE status = 'pending'
            ORDER BY created_at ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    async def flush_buffer(self, dbos_client) -> int:
        """
        Flush buffered results to DBOS

        Args:
            dbos_client: DBOS client for sending results

        Returns:
            Number of results successfully flushed
        """
        buffered = await self.get_all_buffered_results()

        if not buffered:
            logger.debug("Buffer is empty, nothing to flush")
            return 0

        flushed_count = 0

        for result_entry in buffered:
            buffer_id = result_entry["id"]
            task_id = result_entry["task_id"]

            # Check retry limit
            if result_entry["retry_count"] >= self.max_retry_attempts:
                logger.warning(
                    f"Max retry attempts exceeded for task {task_id}, "
                    f"marking as failed"
                )
                await self._mark_as_failed(buffer_id)
                continue

            try:
                # Prepare result data
                result_data = {
                    "task_id": task_id,
                    "agent_id": result_entry["agent_id"],
                    "lease_token": result_entry["lease_token"],
                    "result": json.loads(result_entry["result_data"]),
                    "metadata": result_entry["metadata"]  # Already parsed in _row_to_dict
                }

                # Send to DBOS
                await dbos_client.send_result(result_data)

                # Remove from buffer on success
                await self._remove_from_buffer(buffer_id)
                flushed_count += 1

                logger.info(f"Flushed result for task {task_id}")

            except Exception as e:
                logger.error(f"Failed to flush result for task {task_id}: {e}")

                # Increment retry count
                await self._increment_retry_count(buffer_id)

        logger.info(f"Flush complete: {flushed_count}/{len(buffered)} results sent")

        return flushed_count

    async def start_periodic_flush(self, dbos_client):
        """
        Start periodic flush attempts

        Args:
            dbos_client: DBOS client for sending results
        """
        if self._flush_running:
            logger.warning("Periodic flush already running")
            return

        self._flush_running = True
        self._flush_task = asyncio.create_task(
            self._periodic_flush_loop(dbos_client)
        )

        logger.info(f"Started periodic flush (interval={self.flush_interval}s)")

    async def stop_periodic_flush(self):
        """Stop periodic flush attempts"""
        self._flush_running = False

        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
            self._flush_task = None

        logger.info("Stopped periodic flush")

    def is_flushing_active(self) -> bool:
        """Check if periodic flushing is active"""
        return self._flush_running

    async def _periodic_flush_loop(self, dbos_client):
        """Background task for periodic flush attempts"""
        while self._flush_running:
            try:
                # Check if DBOS is connected
                is_connected = True
                if hasattr(dbos_client, 'is_connected'):
                    is_connected = await dbos_client.is_connected()

                if is_connected:
                    # Attempt to flush buffer
                    await self.flush_buffer(dbos_client)
                else:
                    logger.debug("DBOS not connected, skipping flush")

            except Exception as e:
                logger.error(f"Error in periodic flush loop: {e}")

            # Wait for next interval
            await asyncio.sleep(self.flush_interval)

    async def get_failed_results(self) -> List[Dict[str, Any]]:
        """
        Get results that failed after max retry attempts

        Returns:
            List of failed results
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, task_id, agent_id, lease_token, result_data,
                   metadata, created_at, retry_count, last_retry_at, status
            FROM buffered_results
            WHERE status = 'failed'
            ORDER BY created_at ASC
        """)

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    async def get_buffer_metrics(self) -> Dict[str, Any]:
        """
        Get buffer metrics for monitoring

        Returns:
            Buffer metrics including size, utilization, and age statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # Get current size
        cursor.execute("""
            SELECT COUNT(*) FROM buffered_results
            WHERE status = 'pending'
        """)
        current_size = cursor.fetchone()[0]

        # Get age statistics
        cursor.execute("""
            SELECT
                MIN(created_at) as oldest,
                MAX(created_at) as newest
            FROM buffered_results
            WHERE status = 'pending'
        """)

        row = cursor.fetchone()
        conn.close()

        oldest_str, newest_str = row

        # Calculate ages
        now = datetime.now(timezone.utc)
        oldest_age = None
        newest_age = None

        if oldest_str:
            oldest = datetime.fromisoformat(oldest_str.replace('Z', '+00:00'))
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=timezone.utc)
            oldest_age = (now - oldest).total_seconds()

        if newest_str:
            newest = datetime.fromisoformat(newest_str.replace('Z', '+00:00'))
            if newest.tzinfo is None:
                newest = newest.replace(tzinfo=timezone.utc)
            newest_age = (now - newest).total_seconds()

        utilization = (current_size / self.max_buffer_size * 100) if self.max_buffer_size > 0 else 0

        return {
            "current_size": current_size,
            "max_capacity": self.max_buffer_size,
            "utilization_percent": round(utilization, 2),
            "oldest_result_age_seconds": oldest_age,
            "newest_result_age_seconds": newest_age
        }

    async def _remove_from_buffer(self, buffer_id: int):
        """Remove result from buffer"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            DELETE FROM buffered_results
            WHERE id = ?
        """, (buffer_id,))

        conn.commit()
        conn.close()

    async def _increment_retry_count(self, buffer_id: int):
        """Increment retry count for a buffered result"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = datetime.now(timezone.utc).isoformat()

        cursor.execute("""
            UPDATE buffered_results
            SET retry_count = retry_count + 1,
                last_retry_at = ?
            WHERE id = ?
        """, (now, buffer_id))

        conn.commit()
        conn.close()

    async def _mark_as_failed(self, buffer_id: int):
        """Mark result as failed after max retries"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            UPDATE buffered_results
            SET status = 'failed'
            WHERE id = ?
        """, (buffer_id,))

        conn.commit()
        conn.close()

    def _row_to_dict(self, row) -> Dict[str, Any]:
        """Convert database row to dictionary"""
        return {
            "id": row[0],
            "task_id": row[1],
            "agent_id": row[2],
            "lease_token": row[3],
            "result_data": row[4],
            "metadata": json.loads(row[5]) if row[5] else None,
            "created_at": row[6],
            "retry_count": row[7],
            "last_retry_at": row[8],
            "status": row[9]
        }

    def close(self):
        """Close service and cleanup resources"""
        # Stop periodic flush if running
        if self._flush_running:
            self._flush_running = False
            if self._flush_task:
                self._flush_task.cancel()

        logger.info("ResultBufferService closed")

    def __del__(self):
        """Cleanup on deletion"""
        if hasattr(self, '_flush_running') and self._flush_running:
            self._flush_running = False


# Global service instance
_buffer_service: Optional[ResultBufferService] = None


def get_result_buffer_service(
    db_path: str = "/tmp/openclaw_result_buffer.db",
    max_buffer_size: int = 10000,
    flush_interval: int = 30,
    max_retry_attempts: int = 3
) -> ResultBufferService:
    """
    Get global result buffer service instance

    Args:
        db_path: Path to SQLite database file
        max_buffer_size: Maximum number of buffered results
        flush_interval: Interval between flush attempts (seconds)
        max_retry_attempts: Maximum retry attempts for failed flushes

    Returns:
        ResultBufferService instance
    """
    global _buffer_service

    if _buffer_service is None:
        _buffer_service = ResultBufferService(
            db_path=db_path,
            max_buffer_size=max_buffer_size,
            flush_interval=flush_interval,
            max_retry_attempts=max_retry_attempts
        )

    return _buffer_service
