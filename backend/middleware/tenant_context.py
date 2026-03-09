"""
Tenant Context Middleware

Implements database-enforced multi-tenant isolation using PostgreSQL Row-Level Security (RLS).
Sets tenant context for each request based on authenticated user's workspace.

Epic: E9 - Database Security
Story: S1 - Row-Level Security
Issue: #120

CRITICAL: This middleware is essential for tenant isolation. Zero tolerance for data leaks.
"""

import logging
from typing import Optional
from uuid import UUID
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.base import AsyncSessionLocal

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware to set PostgreSQL session variable for RLS

    For each request:
    1. Extract authenticated user from request state
    2. Get user's workspace_id
    3. Set app.current_tenant_id session variable
    4. Process request with tenant context active
    5. Clean up session variable after request

    RLS policies use this session variable to filter queries by workspace.
    """

    async def dispatch(self, request: Request, call_next):
        """
        Process request with tenant context

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/endpoint in chain

        Returns:
            HTTP response with tenant context applied
        """
        tenant_id: Optional[UUID] = None
        db_session: Optional[AsyncSession] = None

        try:
            # Extract tenant context from request
            # Priority order:
            # 1. User's workspace_id (from authenticated user)
            # 2. Header X-Tenant-ID (for system/service accounts)
            # 3. No context (RLS will deny all queries - secure by default)

            # Check if user is authenticated and has workspace
            if hasattr(request.state, "user") and request.state.user:
                user = request.state.user
                if hasattr(user, "workspace_id") and user.workspace_id:
                    tenant_id = user.workspace_id
                    logger.debug(f"Tenant context from user: {tenant_id}")

            # Fallback: Check X-Tenant-ID header (for service accounts)
            if not tenant_id:
                tenant_id_header = request.headers.get("X-Tenant-ID")
                if tenant_id_header:
                    try:
                        tenant_id = UUID(tenant_id_header)
                        logger.debug(f"Tenant context from header: {tenant_id}")
                    except ValueError:
                        logger.warning(f"Invalid X-Tenant-ID header: {tenant_id_header}")

            # Set tenant context in database session if tenant identified
            if tenant_id:
                db_session = AsyncSessionLocal()
                await set_tenant_context(db_session, tenant_id)
                logger.debug(f"Set tenant context: {tenant_id}")
            else:
                # No tenant context - RLS will deny queries (secure by default)
                logger.debug("No tenant context set - RLS will deny queries")

            # Store tenant context in request state for convenience
            request.state.tenant_id = tenant_id

            # Process request
            response = await call_next(request)
            return response

        except Exception as e:
            logger.error(f"Error in TenantContextMiddleware: {str(e)}", exc_info=True)
            # Don't leak error details to client
            return Response(
                content="Internal server error",
                status_code=500
            )

        finally:
            # Clean up: Reset tenant context and close session
            if db_session:
                try:
                    await db_session.execute(text("RESET app.current_tenant_id"))
                    await db_session.close()
                except Exception as e:
                    logger.error(f"Error cleaning up tenant context: {str(e)}")


async def set_tenant_context(db_session: AsyncSession, tenant_id: UUID) -> None:
    """
    Set tenant context in PostgreSQL session

    Sets the app.current_tenant_id session variable that RLS policies use
    to filter queries by workspace.

    Args:
        db_session: SQLAlchemy async session
        tenant_id: Workspace UUID to set as current tenant

    Raises:
        ValueError: If tenant_id is None or invalid
        SQLAlchemyError: If database operation fails

    Example:
        >>> async with AsyncSessionLocal() as session:
        ...     await set_tenant_context(session, workspace_id)
        ...     # All queries in this session are now filtered by workspace_id
    """
    if not tenant_id:
        raise ValueError("tenant_id cannot be None")

    if not isinstance(tenant_id, UUID):
        raise ValueError(f"tenant_id must be UUID, got {type(tenant_id)}")

    # Set PostgreSQL session variable
    # RLS policies check: current_setting('app.current_tenant_id', TRUE)
    await db_session.execute(
        text("SET LOCAL app.current_tenant_id = :tenant_id"),
        {"tenant_id": str(tenant_id)}
    )

    logger.debug(f"Tenant context set to: {tenant_id}")


async def get_current_tenant_id(db_session: AsyncSession) -> Optional[UUID]:
    """
    Get current tenant context from PostgreSQL session

    Retrieves the app.current_tenant_id session variable.

    Args:
        db_session: SQLAlchemy async session

    Returns:
        Current tenant UUID or None if not set

    Example:
        >>> async with AsyncSessionLocal() as session:
        ...     tenant_id = await get_current_tenant_id(session)
        ...     print(f"Current tenant: {tenant_id}")
    """
    try:
        result = await db_session.execute(
            text("SELECT current_setting('app.current_tenant_id', TRUE)")
        )
        tenant_id_str = result.scalar_one_or_none()

        if tenant_id_str:
            return UUID(tenant_id_str)
        return None

    except Exception as e:
        logger.warning(f"Error getting current tenant ID: {str(e)}")
        return None


async def reset_tenant_context(db_session: AsyncSession) -> None:
    """
    Reset tenant context in PostgreSQL session

    Clears the app.current_tenant_id session variable.
    After calling this, RLS will deny all queries (secure by default).

    Args:
        db_session: SQLAlchemy async session

    Example:
        >>> async with AsyncSessionLocal() as session:
        ...     await reset_tenant_context(session)
        ...     # All queries will now be denied by RLS
    """
    await db_session.execute(text("RESET app.current_tenant_id"))
    logger.debug("Tenant context reset")


def bypass_rls_for_admin(db_session: AsyncSession) -> None:
    """
    Bypass RLS for admin operations

    WARNING: USE WITH EXTREME CAUTION
    This disables RLS for the current session, allowing access to all tenants.
    Only use for legitimate admin operations (migrations, reports, debugging).

    Args:
        db_session: SQLAlchemy async session (must be synchronous for this operation)

    Security Note:
        - Only callable by superuser database role
        - Normal application role cannot bypass RLS
        - Audit all calls to this function
    """
    # This requires superuser privileges
    # Normal application role will get permission denied
    db_session.execute(text("SET LOCAL row_security = off"))
    logger.warning("RLS BYPASSED - Admin operation in progress")
