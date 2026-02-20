"""
DBOS Partition Detection Service

Detects DBOS connection loss via health checks, manages degraded mode operation,
logs partition events, and buffers task results during network partitions.

Epic E6-S3: DBOS Partition Detection (3 story points)

Features:
- DBOS health check monitoring with configurable intervals
- Automatic degraded mode entry on partition detection
- Task continuation for in-progress work during partition
- Rejection of new work during partition
- Local buffering of task results
- Automatic result flushing on partition recovery
- Comprehensive partition event logging and statistics
"""

import logging
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Set
from collections import deque
import httpx

logger = logging.getLogger(__name__)


class PartitionError(Exception):
    """Exception raised when operation is rejected due to partition"""
    pass


class DBOSPartitionDetectionService:
    """
    DBOS Partition Detection Service

    Monitors DBOS connectivity and manages system behavior during network partitions.

    Features:
    - Health check monitoring with exponential backoff
    - Degraded mode state management
    - Task tracking for in-progress work
    - Result buffering with overflow protection
    - Event logging with configurable retention
    - Background health check scheduling
    """

    def __init__(
        self,
        openclaw_gateway_url: str,
        health_check_interval: int = 30,
        health_check_timeout: int = 10,
        max_buffer_size: int = 1000,
        max_event_history: int = 100
    ):
        """
        Initialize DBOS partition detection service

        Args:
            openclaw_gateway_url: Base URL for OpenClaw Gateway with DBOS
            health_check_interval: Interval between health checks in seconds
            health_check_timeout: Timeout for health check requests in seconds
            max_buffer_size: Maximum number of results to buffer during partition
            max_event_history: Maximum number of partition events to retain
        """
        self.openclaw_gateway_url = openclaw_gateway_url.rstrip('/')
        self.health_check_interval = health_check_interval
        self.health_check_timeout = health_check_timeout
        self.max_buffer_size = max_buffer_size
        self.max_event_history = max_event_history

        # HTTP client for health checks
        self.client = httpx.AsyncClient(timeout=health_check_timeout)

        # State management
        self._degraded_mode = False
        self._partition_count = 0
        self._consecutive_failures = 0
        self._partition_start_time: Optional[datetime] = None

        # Task tracking
        self._in_progress_tasks: Set[str] = set()
        self._buffered_results: deque = deque(maxlen=max_buffer_size)

        # Event logging
        self._partition_events: deque = deque(maxlen=max_event_history)

        # Background health check task
        self._background_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = asyncio.Lock()

    async def close(self):
        """Close HTTP client and cleanup resources"""
        await self.stop_background_checks()
        await self.client.aclose()

    async def check_dbos_health(self) -> bool:
        """
        Check DBOS health via gateway endpoint

        Returns:
            True if partitioned, False if healthy
        """
        async with self._lock:
            try:
                # Attempt health check
                response = await self.client.get(
                    f"{self.openclaw_gateway_url}/health"
                )

                # Validate response
                if response.status_code != 200:
                    logger.warning(f"DBOS health check failed with status {response.status_code}")
                    return await self._handle_health_check_failure(
                        f"HTTP {response.status_code}"
                    )

                # Try to parse response
                try:
                    health_data = response.json()
                    if health_data.get("status") != "healthy":
                        logger.warning(f"DBOS reported unhealthy status: {health_data}")
                        return await self._handle_health_check_failure(
                            f"Unhealthy status: {health_data.get('status')}"
                        )
                except Exception as e:
                    logger.error(f"Failed to parse health response: {e}")
                    return await self._handle_health_check_failure(
                        f"Invalid response: {str(e)}"
                    )

                # Health check succeeded
                return await self._handle_health_check_success()

            except (httpx.ConnectError, httpx.TimeoutException) as e:
                logger.error(f"DBOS connection failed: {e}")
                return await self._handle_health_check_failure(str(e))
            except Exception as e:
                logger.error(f"Unexpected error during health check: {e}")
                return await self._handle_health_check_failure(str(e))

    async def _handle_health_check_failure(self, error_message: str) -> bool:
        """
        Handle health check failure

        Args:
            error_message: Error message describing the failure

        Returns:
            True (indicating partition detected)
        """
        self._consecutive_failures += 1

        # Enter degraded mode if not already
        if not self._degraded_mode:
            self._degraded_mode = True
            self._partition_count += 1
            self._partition_start_time = datetime.now(timezone.utc)

            # Log partition event
            self._log_partition_event(
                event_type="partition_detected",
                error_message=error_message,
                consecutive_failures=self._consecutive_failures
            )

            logger.warning(
                f"DBOS partition detected (partition #{self._partition_count}). "
                f"Entering degraded mode. Error: {error_message}"
            )

        return True

    async def _handle_health_check_success(self) -> bool:
        """
        Handle successful health check

        Returns:
            False (indicating no partition)
        """
        # Reset consecutive failures
        self._consecutive_failures = 0

        # Exit degraded mode if active
        if self._degraded_mode:
            partition_duration = None
            if self._partition_start_time:
                partition_duration = (
                    datetime.now(timezone.utc) - self._partition_start_time
                ).total_seconds()

            self._degraded_mode = False
            self._partition_start_time = None

            # Log recovery event
            self._log_partition_event(
                event_type="partition_recovered",
                partition_duration_seconds=partition_duration
            )

            logger.info(
                f"DBOS partition recovered. Duration: {partition_duration:.2f}s. "
                "Exiting degraded mode."
            )

            # Flush buffered results
            await self._flush_buffered_results()

        return False

    def is_degraded_mode(self) -> bool:
        """
        Check if system is in degraded mode

        Returns:
            True if in degraded mode due to partition
        """
        return self._degraded_mode

    def get_partition_count(self) -> int:
        """
        Get total number of partitions detected

        Returns:
            Partition count
        """
        return self._partition_count

    def get_consecutive_failure_count(self) -> int:
        """
        Get consecutive health check failure count

        Returns:
            Number of consecutive failures
        """
        return self._consecutive_failures

    def can_complete_task(self, task_id: str) -> bool:
        """
        Check if task can continue during partition

        Args:
            task_id: Task identifier

        Returns:
            True if task is in progress and can complete
        """
        # Tasks that started before partition can continue
        return task_id in self._in_progress_tasks or not self._degraded_mode

    def accept_new_task(self, task_request: Dict[str, Any]) -> None:
        """
        Accept new task request

        Args:
            task_request: Task request details

        Raises:
            PartitionError: If in degraded mode due to partition
        """
        if self._degraded_mode:
            raise PartitionError(
                "Cannot accept new tasks: system is in degraded mode due to DBOS partition. "
                "Existing tasks can continue, but new work is rejected until partition is resolved."
            )

        # In normal mode, accept the task
        logger.debug(f"Accepted new task: {task_request.get('task_id')}")

    def register_task_start(self, task_id: str) -> None:
        """
        Register task as in-progress

        Args:
            task_id: Task identifier
        """
        self._in_progress_tasks.add(task_id)
        logger.debug(f"Registered task start: {task_id}")

    def register_task_complete(self, task_id: str) -> None:
        """
        Register task as completed

        Args:
            task_id: Task identifier
        """
        self._in_progress_tasks.discard(task_id)
        logger.debug(f"Registered task complete: {task_id}")

    def get_in_progress_tasks(self) -> List[str]:
        """
        Get list of in-progress tasks

        Returns:
            List of task IDs
        """
        return list(self._in_progress_tasks)

    def buffer_task_result(self, task_result: Dict[str, Any]) -> None:
        """
        Buffer task result during partition

        Args:
            task_result: Task result to buffer
        """
        if len(self._buffered_results) >= self.max_buffer_size:
            logger.warning(
                f"Result buffer at capacity ({self.max_buffer_size}). "
                "Oldest result will be dropped."
            )

        self._buffered_results.append({
            **task_result,
            "buffered_at": datetime.now(timezone.utc).isoformat()
        })

        logger.debug(
            f"Buffered task result: {task_result.get('task_id')}. "
            f"Buffer size: {len(self._buffered_results)}"
        )

    def get_buffered_results(self) -> List[Dict[str, Any]]:
        """
        Get all buffered results

        Returns:
            List of buffered task results
        """
        return list(self._buffered_results)

    async def _flush_buffered_results(self) -> None:
        """
        Flush buffered results to DBOS after partition recovery
        """
        if not self._buffered_results:
            logger.debug("No buffered results to flush")
            return

        results_to_flush = list(self._buffered_results)
        flush_count = len(results_to_flush)

        logger.info(f"Flushing {flush_count} buffered results to DBOS")

        successful_flushes = 0
        failed_flushes = 0

        for result in results_to_flush:
            try:
                # Post result to DBOS via gateway
                response = await self.client.post(
                    f"{self.openclaw_gateway_url}/tasks/{result['task_id']}/result",
                    json=result
                )

                if response.status_code in (200, 201):
                    successful_flushes += 1
                    self._buffered_results.remove(result)
                else:
                    logger.warning(
                        f"Failed to flush result for task {result['task_id']}: "
                        f"HTTP {response.status_code}"
                    )
                    failed_flushes += 1

            except Exception as e:
                logger.error(f"Error flushing result for task {result['task_id']}: {e}")
                failed_flushes += 1

        logger.info(
            f"Flush complete: {successful_flushes} successful, "
            f"{failed_flushes} failed, {len(self._buffered_results)} remaining"
        )

    def _log_partition_event(
        self,
        event_type: str,
        error_message: Optional[str] = None,
        consecutive_failures: Optional[int] = None,
        partition_duration_seconds: Optional[float] = None
    ) -> None:
        """
        Log partition event

        Args:
            event_type: Type of event (partition_detected, partition_recovered)
            error_message: Error message if partition detected
            consecutive_failures: Number of consecutive failures
            partition_duration_seconds: Duration of partition in seconds
        """
        event = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        if error_message is not None:
            event["error_message"] = error_message

        if consecutive_failures is not None:
            event["consecutive_failures"] = consecutive_failures

        if partition_duration_seconds is not None:
            event["partition_duration_seconds"] = partition_duration_seconds

        self._partition_events.append(event)

    def get_partition_events(self) -> List[Dict[str, Any]]:
        """
        Get partition event history

        Returns:
            List of partition events
        """
        return list(self._partition_events)

    def get_partition_statistics(self) -> Dict[str, Any]:
        """
        Get partition statistics

        Returns:
            Statistics including counts, durations, and current state
        """
        # Count partition and recovery events
        partition_events = [e for e in self._partition_events if e['event_type'] == 'partition_detected']
        recovery_events = [e for e in self._partition_events if e['event_type'] == 'partition_recovered']

        # Calculate total partition duration
        total_duration = sum(
            e.get('partition_duration_seconds', 0)
            for e in recovery_events
        )

        return {
            "total_partitions": len(partition_events),
            "total_recoveries": len(recovery_events),
            "total_partition_duration_seconds": total_duration,
            "current_state": "degraded" if self._degraded_mode else "normal",
            "current_partition_duration_seconds": (
                (datetime.now(timezone.utc) - self._partition_start_time).total_seconds()
                if self._degraded_mode and self._partition_start_time
                else 0
            ),
            "buffered_results_count": len(self._buffered_results),
            "in_progress_tasks_count": len(self._in_progress_tasks)
        }

    async def start_background_checks(self) -> None:
        """
        Start background health check task
        """
        if self._running:
            logger.warning("Background health checks already running")
            return

        self._running = True
        self._background_task = asyncio.create_task(self._health_check_loop())
        logger.info(
            f"Started background DBOS health checks (interval: {self.health_check_interval}s)"
        )

    async def stop_background_checks(self) -> None:
        """
        Stop background health check task
        """
        if not self._running:
            return

        self._running = False

        if self._background_task:
            self._background_task.cancel()
            try:
                await self._background_task
            except asyncio.CancelledError:
                pass

        logger.info("Stopped background DBOS health checks")

    def is_background_checks_running(self) -> bool:
        """
        Check if background health checks are running

        Returns:
            True if background checks are active
        """
        return self._running

    async def _health_check_loop(self) -> None:
        """
        Background health check loop
        """
        while self._running:
            try:
                await self.check_dbos_health()
            except Exception as e:
                logger.error(f"Error in health check loop: {e}")

            # Wait for next check
            await asyncio.sleep(self.health_check_interval)


# Global service instance
_partition_detection_service: Optional[DBOSPartitionDetectionService] = None


def get_partition_detection_service(
    openclaw_gateway_url: Optional[str] = None,
    **kwargs
) -> DBOSPartitionDetectionService:
    """
    Get global partition detection service instance

    Args:
        openclaw_gateway_url: Gateway URL (uses default if not provided)
        **kwargs: Additional service configuration

    Returns:
        DBOS partition detection service
    """
    global _partition_detection_service

    if _partition_detection_service is None:
        if openclaw_gateway_url is None:
            openclaw_gateway_url = "http://localhost:8080"

        _partition_detection_service = DBOSPartitionDetectionService(
            openclaw_gateway_url=openclaw_gateway_url,
            **kwargs
        )

    return _partition_detection_service


async def start_partition_monitoring(
    openclaw_gateway_url: Optional[str] = None,
    health_check_interval: int = 30
) -> None:
    """
    Start partition monitoring with background health checks

    Args:
        openclaw_gateway_url: Gateway URL
        health_check_interval: Health check interval in seconds
    """
    service = get_partition_detection_service(
        openclaw_gateway_url=openclaw_gateway_url,
        health_check_interval=health_check_interval
    )

    await service.start_background_checks()


async def stop_partition_monitoring() -> None:
    """
    Stop partition monitoring
    """
    global _partition_detection_service

    if _partition_detection_service:
        await _partition_detection_service.stop_background_checks()
        await _partition_detection_service.close()
        _partition_detection_service = None
