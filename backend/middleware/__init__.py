"""
Middleware package for OpenClaw Backend

Contains middleware components for request processing, security, and context management.
"""

from .tenant_context import TenantContextMiddleware, get_current_tenant_id, set_tenant_context
from .security_headers import SecurityHeadersMiddleware, add_security_headers_middleware
from .rate_limit import (
    limiter,
    get_limiter,
    rate_limit_auth,
    rate_limit_write,
    rate_limit_read,
    rate_limit_global,
    custom_rate_limit,
    rate_limit_exceeded_handler,
    is_rate_limiting_enabled,
    get_rate_limit_stats,
    RATE_LIMIT_PROFILES,
)

__all__ = [
    "TenantContextMiddleware",
    "get_current_tenant_id",
    "set_tenant_context",
    "SecurityHeadersMiddleware",
    "add_security_headers_middleware",
    "limiter",
    "get_limiter",
    "rate_limit_auth",
    "rate_limit_write",
    "rate_limit_read",
    "rate_limit_global",
    "custom_rate_limit",
    "rate_limit_exceeded_handler",
    "is_rate_limiting_enabled",
    "get_rate_limit_stats",
    "RATE_LIMIT_PROFILES",
]
