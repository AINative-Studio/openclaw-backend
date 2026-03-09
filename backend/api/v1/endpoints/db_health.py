"""
Database Health Check Endpoint

Provides monitoring and diagnostics for database connection pools,
including async and sync session statistics, connection health,
and pool utilization metrics.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.base import get_async_db, async_engine, engine
from backend.security.auth_service import get_current_user
from backend.models.user import User


router = APIRouter(tags=["Database Health"])


class PoolStats(BaseModel):
    """Database connection pool statistics"""
    size: int = Field(..., description="Current pool size")
    checked_in: int = Field(..., description="Number of connections currently checked in (available)")
    checked_out: int = Field(..., description="Number of connections currently checked out (in use)")
    overflow: int = Field(..., description="Number of overflow connections beyond pool size")
    max_overflow: int = Field(..., description="Maximum allowed overflow connections")
    utilization_percent: float = Field(..., description="Pool utilization percentage")


class DatabaseHealthResponse(BaseModel):
    """Database health check response"""
    status: str = Field(..., description="Overall health status: healthy, degraded, unhealthy")
    timestamp: datetime = Field(..., description="Health check timestamp")
    async_pool: PoolStats = Field(..., description="Async connection pool statistics")
    sync_pool: PoolStats = Field(..., description="Sync connection pool statistics")
    async_connection_test: bool = Field(..., description="Async connection test successful")
    sync_connection_test: bool = Field(..., description="Sync connection test successful")
    database_name: str = Field(..., description="Connected database name")
    database_host: str = Field(..., description="Database host")
    warnings: list = Field(default_factory=list, description="Health warnings if any")


def _get_pool_stats(pool) -> PoolStats:
    """
    Extract statistics from a SQLAlchemy connection pool

    Args:
        pool: SQLAlchemy connection pool

    Returns:
        PoolStats object with pool metrics
    """
    checked_in = pool.size() - pool.checkedout()
    checked_out = pool.checkedout()
    size = pool.size()
    overflow = pool.overflow()
    max_overflow = pool._max_overflow if hasattr(pool, '_max_overflow') else 0

    utilization = (checked_out / size * 100) if size > 0 else 0

    return PoolStats(
        size=size,
        checked_in=checked_in,
        checked_out=checked_out,
        overflow=overflow,
        max_overflow=max_overflow,
        utilization_percent=round(utilization, 2)
    )


def _derive_health_status(
    async_ok: bool,
    sync_ok: bool,
    async_pool: PoolStats,
    sync_pool: PoolStats,
    warnings: list
) -> str:
    """
    Derive overall health status from pool stats and connection tests

    Args:
        async_ok: Async connection test passed
        sync_ok: Sync connection test passed
        async_pool: Async pool statistics
        sync_pool: Sync pool statistics
        warnings: List of warning messages

    Returns:
        Status string: "healthy", "degraded", or "unhealthy"
    """
    # Unhealthy: Both connection tests failed
    if not async_ok and not sync_ok:
        return "unhealthy"

    # Unhealthy: Pool utilization >= 95% (critical)
    if async_pool.utilization_percent >= 95 or sync_pool.utilization_percent >= 95:
        return "unhealthy"

    # Degraded: One connection test failed
    if not async_ok or not sync_ok:
        return "degraded"

    # Degraded: Pool utilization >= 80% (warning threshold)
    if async_pool.utilization_percent >= 80 or sync_pool.utilization_percent >= 80:
        return "degraded"

    # Degraded: Any warnings present
    if warnings:
        return "degraded"

    return "healthy"


@router.get(
    "/db/health",
    response_model=DatabaseHealthResponse,
    summary="Database Health Check",
    description="Get comprehensive database health metrics including connection pool statistics"
)
async def get_database_health(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(get_current_user)
) -> DatabaseHealthResponse:
    """
    Check database health and connection pool statistics

    Requires authentication. Returns detailed metrics about:
    - Async and sync connection pool utilization
    - Connection test results
    - Overall health status

    **Health Status:**
    - `healthy`: All tests pass, pool utilization < 80%
    - `degraded`: One test failed OR pool utilization 80-95%
    - `unhealthy`: Both tests failed OR pool utilization >= 95%
    """
    warnings = []

    # Test async connection
    async_ok = False
    try:
        result = await db.execute(text("SELECT 1"))
        result.fetchone()
        async_ok = True
    except Exception as e:
        warnings.append(f"Async connection test failed: {str(e)}")

    # Test sync connection
    sync_ok = False
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        sync_ok = True
    except Exception as e:
        warnings.append(f"Sync connection test failed: {str(e)}")

    # Get pool statistics
    async_pool = _get_pool_stats(async_engine.pool)
    sync_pool = _get_pool_stats(engine.pool)

    # Check for high utilization
    if async_pool.utilization_percent >= 80:
        warnings.append(f"Async pool utilization high: {async_pool.utilization_percent}%")
    if sync_pool.utilization_percent >= 80:
        warnings.append(f"Sync pool utilization high: {sync_pool.utilization_percent}%")

    # Derive overall status
    health_status = _derive_health_status(
        async_ok, sync_ok, async_pool, sync_pool, warnings
    )

    return DatabaseHealthResponse(
        status=health_status,
        timestamp=datetime.now(timezone.utc),
        async_pool=async_pool,
        sync_pool=sync_pool,
        async_connection_test=async_ok,
        sync_connection_test=sync_ok,
        database_name=str(async_engine.url.database),
        database_host=str(async_engine.url.host),
        warnings=warnings
    )


@router.get(
    "/db/pool-stats",
    response_model=Dict[str, PoolStats],
    summary="Database Pool Statistics",
    description="Get raw connection pool statistics for async and sync pools"
)
async def get_pool_statistics(
    current_user: User = Depends(get_current_user)
) -> Dict[str, PoolStats]:
    """
    Get raw database connection pool statistics

    Requires authentication. Returns detailed pool metrics without health derivation.
    Useful for monitoring dashboards and alerting systems.
    """
    return {
        "async_pool": _get_pool_stats(async_engine.pool),
        "sync_pool": _get_pool_stats(engine.pool),
    }
