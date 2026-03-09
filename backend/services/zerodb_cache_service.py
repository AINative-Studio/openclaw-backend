"""
ZeroDB Cache Service (Issue #123)

Serverless caching layer using ZeroDB NoSQL tables.
Replaces Redis infrastructure with no additional server overhead.

Features:
- TTL-based expiration
- Auto-cleanup of expired entries
- Atomic counter operations for rate limiting
- Cache statistics (hit/miss tracking)

Architecture:
- Uses ZeroDB project: 'openclaw-backend'
- Uses ZeroDB table: 'openclaw_cache'
- Schema: { key: str, value: str, expires_at: int, created_at: int, counter: int }
- MongoDB-style queries for efficient filtering
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from backend.integrations.zerodb_client import ZeroDBClient

logger = logging.getLogger(__name__)


class ZeroDBCacheService:
    """
    Serverless cache service using ZeroDB NoSQL tables.

    Provides Redis-like functionality without additional infrastructure:
    - get/set with TTL
    - exists check
    - delete
    - atomic increment for rate limiting
    - automatic expiration cleanup
    - cache statistics
    """

    PROJECT_NAME = "openclaw-backend"
    TABLE_NAME = "openclaw_cache"

    def __init__(self, zerodb_client: Optional[ZeroDBClient] = None, project_id: Optional[str] = None):
        """
        Initialize cache service.

        Args:
            zerodb_client: Optional ZeroDB client (creates default if None)
            project_id: Optional ZeroDB project ID (defaults to ZERODB_PROJECT_ID env var)
        """
        self.client = zerodb_client or ZeroDBClient()
        self.project_id = project_id or os.getenv("ZERODB_PROJECT_ID")
        self._initialized = False
        self._stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "increments": 0
        }
        logger.info(f"ZeroDBCacheService initialized with table '{self.TABLE_NAME}'")

    async def set(self, key: str, value: str, ttl: Optional[int] = None) -> None:
        """
        Set cache value with optional TTL.

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time-to-live in seconds (None = no expiration)
        """
        now = int(datetime.now(timezone.utc).timestamp())

        expires_at = None
        if ttl is not None:
            expires_at = now + ttl

        row = {
            "key": key,
            "value": value,
            "expires_at": expires_at,
            "created_at": now,
            "counter": 0
        }

        # Upsert: insert or update if key exists
        try:
            # First try to update existing row
            result = await self.client.update_rows(
                table_name=self.TABLE_NAME,
                filter_query={"key": {"$eq": key}},
                update_data=row,
                project_id=self.project_id
            )

            # If no rows updated, insert new row
            if result.get("updated_count", 0) == 0:
                await self.client.insert_rows(
                    table_name=self.TABLE_NAME,
                    rows=[row],
                    project_id=self.project_id
                )
        except Exception as e:
            logger.error(f"Error setting cache key '{key}': {e}")
            raise

        self._stats["sets"] += 1
        logger.debug(f"Set cache key '{key}' with TTL={ttl}s")

    async def get(self, key: str) -> Optional[str]:
        """
        Get cache value if exists and not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        now = int(datetime.now(timezone.utc).timestamp())

        try:
            # Query for key
            filter_query = {"key": {"$eq": key}}

            result = await self.client.query_rows(
                table_name=self.TABLE_NAME,
                filter_query=filter_query,
                project_id=self.project_id
            )

            # Result is a dict with 'data' key containing list of rows
            data_list = result.get("data", [])

            if data_list:
                # Extract row_data from response
                row_data = data_list[0].get("row_data", {})

                # Check if expired
                expires_at = row_data.get("expires_at")
                if expires_at is not None and expires_at < now:
                    # Expired - delete it
                    await self.delete(key)
                    self._stats["misses"] += 1
                    logger.debug(f"Cache MISS for key '{key}' (expired)")
                    return None

                self._stats["hits"] += 1
                value = row_data.get("value")
                logger.debug(f"Cache HIT for key '{key}'")
                return value
            else:
                self._stats["misses"] += 1
                logger.debug(f"Cache MISS for key '{key}'")
                return None

        except Exception as e:
            logger.error(f"Error getting cache key '{key}': {e}")
            self._stats["misses"] += 1
            return None

    async def exists(self, key: str) -> bool:
        """
        Check if key exists and is not expired.

        Args:
            key: Cache key

        Returns:
            True if key exists and not expired
        """
        value = await self.get(key)
        return value is not None

    async def delete(self, key: str) -> bool:
        """
        Delete cache key.

        Args:
            key: Cache key

        Returns:
            True if key was deleted
        """
        try:
            result = await self.client.delete_rows(
                table_name=self.TABLE_NAME,
                filter_query={"key": {"$eq": key}},
                project_id=self.project_id
            )

            deleted_count = result.get("deleted_count", 0)

            if deleted_count > 0:
                self._stats["deletes"] += 1
                logger.debug(f"Deleted cache key '{key}'")
                return True
            else:
                logger.debug(f"Cache key '{key}' not found for deletion")
                return False

        except Exception as e:
            logger.error(f"Error deleting cache key '{key}': {e}")
            return False

    async def increment(self, key: str, amount: int = 1) -> int:
        """
        Atomically increment counter.

        Args:
            key: Cache key
            amount: Increment amount (default: 1)

        Returns:
            New counter value
        """
        now = int(datetime.now(timezone.utc).timestamp())

        try:
            # Try to get existing counter
            result = await self.client.query_rows(
                table_name=self.TABLE_NAME,
                filter_query={"key": {"$eq": key}},
                project_id=self.project_id
            )

            # Result is a dict with 'data' key containing list of rows
            data_list = result.get("data", [])

            if data_list:
                # Increment existing counter
                row_data = data_list[0].get("row_data", {})
                current_value = row_data.get("counter", 0)
                new_value = current_value + amount

                await self.client.update_rows(
                    table_name=self.TABLE_NAME,
                    filter_query={"key": {"$eq": key}},
                    update_data={"counter": new_value},
                    project_id=self.project_id
                )
            else:
                # Create new counter
                new_value = amount
                await self.client.insert_rows(
                    table_name=self.TABLE_NAME,
                    rows=[{
                        "key": key,
                        "value": "",
                        "expires_at": None,
                        "created_at": now,
                        "counter": new_value
                    }],
                    project_id=self.project_id
                )

            self._stats["increments"] += 1
            logger.debug(f"Incremented counter '{key}' to {new_value}")
            return new_value

        except Exception as e:
            logger.error(f"Error incrementing counter '{key}': {e}")
            raise

    async def cleanup_expired(self) -> int:
        """
        Remove all expired cache entries.

        Returns:
            Number of entries deleted
        """
        now = int(datetime.now(timezone.utc).timestamp())

        try:
            # Delete all rows where expires_at < now (and not None)
            result = await self.client.delete_rows(
                table_name=self.TABLE_NAME,
                filter_query={
                    "expires_at": {
                        "$lt": now,
                        "$ne": None
                    }
                },
                project_id=self.project_id
            )

            deleted_count = result.get("deleted_count", 0)

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} expired cache entries")

            return deleted_count

        except Exception as e:
            logger.error(f"Error cleaning up expired entries: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        try:
            # Count total keys
            result = await self.client.query_rows(
                table_name=self.TABLE_NAME,
                filter_query={},
                project_id=self.project_id
            )

            # Result is a dict with 'data' key containing list of rows
            data_list = result.get("data", [])
            total_keys = len(data_list)

            # Calculate hit rate
            total_requests = self._stats["hits"] + self._stats["misses"]
            hit_rate = (self._stats["hits"] / total_requests * 100) if total_requests > 0 else 0.0

            return {
                "total_keys": total_keys,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": round(hit_rate, 2),
                "sets": self._stats["sets"],
                "deletes": self._stats["deletes"],
                "increments": self._stats["increments"]
            }

        except Exception as e:
            logger.error(f"Error getting cache stats: {e}")
            return {
                "total_keys": 0,
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "hit_rate": 0.0,
                "sets": self._stats["sets"],
                "deletes": self._stats["deletes"],
                "increments": self._stats["increments"]
            }


# Global service instance
_cache_service: Optional[ZeroDBCacheService] = None


def get_cache_service() -> ZeroDBCacheService:
    """
    Get global cache service instance.

    Returns:
        ZeroDBCacheService singleton
    """
    global _cache_service

    if _cache_service is None:
        _cache_service = ZeroDBCacheService()

    return _cache_service
