"""
Test ZeroDB Cache Service (Issue #123)

Tests serverless caching layer using ZeroDB NoSQL tables.
Tests MUST fail initially (RED state) before implementation.

TDD Workflow:
1. RED: Write failing tests
2. GREEN: Implement minimal code to pass
3. REFACTOR: Improve code quality

Issue #123: Implement ZeroDB Cache Service with Auto-Cleanup
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone


class TestZeroDBCacheService:
    """Test suite for ZeroDB cache service"""

    @pytest.mark.asyncio
    async def test_set_and_get_value(self):
        """Test basic cache set and get"""
        from backend.services.zerodb_cache_service import ZeroDBCacheService

        cache = ZeroDBCacheService()

        await cache.set("test_key", "test_value", ttl=60)
        value = await cache.get("test_key")

        assert value == "test_value"

    @pytest.mark.asyncio
    async def test_get_expired_value_returns_none(self):
        """Test that expired values return None"""
        from backend.services.zerodb_cache_service import ZeroDBCacheService

        cache = ZeroDBCacheService()

        # Set with 1 second TTL
        await cache.set("temp_key", "temp_value", ttl=1)

        # Wait for expiration
        await asyncio.sleep(2)

        value = await cache.get("temp_key")
        assert value is None

    @pytest.mark.asyncio
    async def test_delete_key(self):
        """Test cache key deletion"""
        from backend.services.zerodb_cache_service import ZeroDBCacheService

        cache = ZeroDBCacheService()

        await cache.set("delete_me", "value")
        await cache.delete("delete_me")

        value = await cache.get("delete_me")
        assert value is None

    @pytest.mark.asyncio
    async def test_exists_check(self):
        """Test checking if key exists"""
        from backend.services.zerodb_cache_service import ZeroDBCacheService

        cache = ZeroDBCacheService()

        assert await cache.exists("nonexistent") is False

        await cache.set("exists_key", "value")
        assert await cache.exists("exists_key") is True

    @pytest.mark.asyncio
    async def test_cleanup_expired_entries(self):
        """Test background cleanup of expired entries"""
        from backend.services.zerodb_cache_service import ZeroDBCacheService

        cache = ZeroDBCacheService()

        # Create 3 entries: 1 expired, 2 valid
        await cache.set("expired1", "val1", ttl=1)
        await asyncio.sleep(2)
        await cache.set("valid1", "val2", ttl=3600)
        await cache.set("valid2", "val3", ttl=3600)

        # Run cleanup
        deleted_count = await cache.cleanup_expired()

        assert deleted_count >= 1
        assert await cache.get("expired1") is None
        assert await cache.get("valid1") == "val2"
        assert await cache.get("valid2") == "val3"

    @pytest.mark.asyncio
    async def test_increment_counter(self):
        """Test atomic counter increment for rate limiting"""
        from backend.services.zerodb_cache_service import ZeroDBCacheService

        cache = ZeroDBCacheService()

        # Clean up any existing counter from previous test runs
        await cache.delete("counter_key")

        # First increment creates counter
        count = await cache.increment("counter_key")
        assert count == 1

        # Second increment
        count = await cache.increment("counter_key")
        assert count == 2

    @pytest.mark.asyncio
    async def test_get_stats(self):
        """Test cache statistics"""
        from backend.services.zerodb_cache_service import ZeroDBCacheService

        cache = ZeroDBCacheService()

        await cache.set("key1", "val1")
        await cache.get("key1")  # hit
        await cache.get("nonexistent")  # miss

        stats = await cache.get_stats()

        assert "total_keys" in stats
        assert "hits" in stats
        assert "misses" in stats
        assert "hit_rate" in stats
        assert stats["hits"] >= 1
        assert stats["misses"] >= 1
