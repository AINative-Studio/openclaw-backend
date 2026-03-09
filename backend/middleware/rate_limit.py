"""
Rate Limiting Middleware for OpenClaw Backend

Implements configurable rate limiting using slowapi with support for:
- Global rate limits per IP address
- Endpoint-specific rate limits
- Stricter limits for authentication/sensitive endpoints
- Custom error responses with rate limit headers
- Optional Redis backend for distributed rate limiting
- Environment-based configuration

Security: Prevents DoS attacks, credential stuffing, and API abuse.
"""

import os
from typing import Callable, Optional
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request, Response
from starlette.status import HTTP_429_TOO_MANY_REQUESTS
import redis.asyncio as redis


class RateLimitConfig:
    """
    Centralized rate limit configuration.

    Environment Variables:
    - RATE_LIMIT_ENABLED: Enable/disable rate limiting (default: 1/true)
    - RATE_LIMIT_GLOBAL: Global rate limit (default: 100/minute)
    - RATE_LIMIT_AUTH: Authentication endpoint limit (default: 5/minute)
    - RATE_LIMIT_POST: POST/PUT/DELETE endpoint limit (default: 30/minute)
    - RATE_LIMIT_GET: GET endpoint limit (default: 100/minute)
    - REDIS_URL: Redis connection URL for distributed rate limiting
    - RATE_LIMIT_STRATEGY: 'fixed-window' or 'moving-window' (default: moving-window)
    """

    def __init__(self):
        self.enabled = os.getenv("RATE_LIMIT_ENABLED", "1") in ("1", "true", "True")
        self.global_limit = os.getenv("RATE_LIMIT_GLOBAL", "100/minute")
        self.auth_limit = os.getenv("RATE_LIMIT_AUTH", "5/minute")
        self.post_limit = os.getenv("RATE_LIMIT_POST", "30/minute")
        self.get_limit = os.getenv("RATE_LIMIT_GET", "100/minute")
        self.redis_url = os.getenv("REDIS_URL")
        self.strategy = os.getenv("RATE_LIMIT_STRATEGY", "moving-window")

    def get_storage_uri(self) -> str:
        """
        Get storage URI for rate limit backend.

        Returns:
        - Redis URI if REDIS_URL is configured
        - In-memory storage otherwise
        """
        if self.redis_url:
            return self.redis_url
        return "memory://"


# Global configuration instance
rate_limit_config = RateLimitConfig()


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get Redis client for distributed rate limiting.

    Returns:
    - Redis client if REDIS_URL is configured
    - None otherwise (falls back to in-memory storage)
    """
    if rate_limit_config.redis_url:
        try:
            return redis.from_url(
                rate_limit_config.redis_url,
                encoding="utf-8",
                decode_responses=True
            )
        except Exception as e:
            print(f"Warning: Failed to connect to Redis for rate limiting: {e}")
            print("Falling back to in-memory rate limiting")
            return None
    return None


def get_request_identifier(request: Request) -> str:
    """
    Extract unique identifier from request for rate limiting.

    Priority:
    1. Authenticated user ID (if available)
    2. API key (if present)
    3. Client IP address

    This allows rate limiting per user rather than per IP when authenticated.
    """
    # Check for authenticated user
    if hasattr(request.state, "user_id") and request.state.user_id:
        return f"user:{request.state.user_id}"

    # Check for API key
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # Use hash to avoid logging full API key
        import hashlib
        key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        return f"apikey:{key_hash}"

    # Fall back to IP address
    return get_remote_address(request)


# Initialize limiter with configuration
limiter = Limiter(
    key_func=get_request_identifier,
    storage_uri=rate_limit_config.get_storage_uri(),
    strategy=rate_limit_config.strategy,
    headers_enabled=True,  # Add X-RateLimit-* headers to responses
)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Custom handler for rate limit exceeded errors.

    Returns structured JSON response with rate limit information and retry-after header.
    """
    from fastapi.responses import JSONResponse

    # Extract rate limit details from exception
    limit = exc.detail if hasattr(exc, "detail") else "Unknown"

    # Calculate retry-after from rate limit window
    retry_after = 60  # Default to 60 seconds
    if "/" in str(limit):
        try:
            window = str(limit).split("/")[1]
            if "minute" in window:
                retry_after = 60
            elif "hour" in window:
                retry_after = 3600
            elif "second" in window:
                retry_after = int(window.split()[0])
        except (IndexError, ValueError):
            pass

    return JSONResponse(
        status_code=HTTP_429_TOO_MANY_REQUESTS,
        content={
            "error": "rate_limit_exceeded",
            "message": f"Rate limit exceeded. Please try again later.",
            "limit": str(limit),
            "retry_after_seconds": retry_after,
        },
        headers={
            "Retry-After": str(retry_after),
            "X-RateLimit-Limit": str(limit),
        }
    )


def get_limiter() -> Limiter:
    """
    Get the configured limiter instance.

    Used for dependency injection in endpoints.
    """
    return limiter


# Decorator shortcuts for common rate limit patterns
def rate_limit_auth(func: Callable) -> Callable:
    """
    Decorator for authentication endpoints (stricter limits).

    Default: 5 requests per minute
    """
    return limiter.limit(rate_limit_config.auth_limit)(func)


def rate_limit_write(func: Callable) -> Callable:
    """
    Decorator for write operations (POST/PUT/DELETE).

    Default: 30 requests per minute
    """
    return limiter.limit(rate_limit_config.post_limit)(func)


def rate_limit_read(func: Callable) -> Callable:
    """
    Decorator for read operations (GET).

    Default: 100 requests per minute
    """
    return limiter.limit(rate_limit_config.get_limit)(func)


def rate_limit_global(func: Callable) -> Callable:
    """
    Decorator for global rate limit.

    Default: 100 requests per minute
    """
    return limiter.limit(rate_limit_config.global_limit)(func)


def custom_rate_limit(limit: str) -> Callable:
    """
    Decorator for custom rate limits.

    Args:
        limit: Rate limit string (e.g., "10/minute", "100/hour", "5/second")

    Example:
        @custom_rate_limit("20/minute")
        async def my_endpoint():
            ...
    """
    def decorator(func: Callable) -> Callable:
        return limiter.limit(limit)(func)
    return decorator


# Rate limit profiles for different endpoint types
RATE_LIMIT_PROFILES = {
    "auth": rate_limit_config.auth_limit,           # Authentication: 5/minute
    "write": rate_limit_config.post_limit,          # Write ops: 30/minute
    "read": rate_limit_config.get_limit,            # Read ops: 100/minute
    "global": rate_limit_config.global_limit,       # Global: 100/minute

    # Specialized profiles for high-risk endpoints
    "api_key_create": "3/minute",                   # API key creation
    "password_reset": "3/minute",                   # Password reset
    "webhook": "50/minute",                          # Webhook callbacks
    "bulk_operations": "10/minute",                 # Bulk data operations
    "export": "5/minute",                            # Data export
    "agent_provision": "10/minute",                 # Agent provisioning
    "wireguard_provision": "10/minute",             # Network provisioning
}


def get_rate_limit_for_endpoint(endpoint_type: str) -> str:
    """
    Get rate limit configuration for specific endpoint type.

    Args:
        endpoint_type: Type of endpoint (auth, write, read, etc.)

    Returns:
        Rate limit string (e.g., "5/minute")
    """
    return RATE_LIMIT_PROFILES.get(endpoint_type, rate_limit_config.global_limit)


async def add_rate_limit_headers(request: Request, call_next):
    """
    Middleware to add rate limit headers to all responses.

    Headers added:
    - X-RateLimit-Limit: Maximum requests allowed in window
    - X-RateLimit-Remaining: Requests remaining in current window
    - X-RateLimit-Reset: Unix timestamp when limit resets
    """
    response = await call_next(request)

    # Rate limit headers are automatically added by slowapi when rate limiting is active
    # This middleware ensures they're present even when rate limiting isn't triggered
    if not response.headers.get("X-RateLimit-Limit"):
        response.headers["X-RateLimit-Limit"] = rate_limit_config.global_limit

    return response


def is_rate_limiting_enabled() -> bool:
    """
    Check if rate limiting is enabled.

    Returns:
        True if rate limiting is enabled, False otherwise
    """
    return rate_limit_config.enabled


def get_rate_limit_stats() -> dict:
    """
    Get rate limiting configuration and statistics.

    Returns:
        Dictionary with rate limit configuration
    """
    return {
        "enabled": rate_limit_config.enabled,
        "backend": "redis" if rate_limit_config.redis_url else "memory",
        "strategy": rate_limit_config.strategy,
        "limits": {
            "global": rate_limit_config.global_limit,
            "auth": rate_limit_config.auth_limit,
            "post": rate_limit_config.post_limit,
            "get": rate_limit_config.get_limit,
        },
        "profiles": RATE_LIMIT_PROFILES,
    }
