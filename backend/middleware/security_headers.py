"""
Security Headers Middleware

Implements comprehensive security headers for FastAPI application following OWASP best practices.
Addresses Issue #134: Missing Security Headers.

Headers implemented:
- Strict-Transport-Security (HSTS): Enforces HTTPS connections
- X-Content-Type-Options: Prevents MIME-type sniffing
- X-Frame-Options: Prevents clickjacking attacks
- X-XSS-Protection: Enables browser XSS filters (legacy support)
- Content-Security-Policy (CSP): Controls resource loading
- Referrer-Policy: Controls referrer information leakage
- Permissions-Policy: Controls browser feature access
- X-Permitted-Cross-Domain-Policies: Restricts cross-domain policies
"""

import os
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware that adds comprehensive security headers to all HTTP responses.

    Configurable via environment variables:
    - SECURITY_HEADERS_ENABLED: Enable/disable security headers (default: 1)
    - ENVIRONMENT: Determines HSTS and CSP strictness
    - FRONTEND_ORIGIN: Allowed origin for CSP (default: http://localhost:3000)
    """

    def __init__(self, app, environment: str = None):
        super().__init__(app)
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.enabled = os.getenv("SECURITY_HEADERS_ENABLED", "1") == "1"
        self.frontend_origin = os.getenv("FRONTEND_ORIGIN", "http://localhost:3000")

        # Configure CSP based on environment
        self.csp_policy = self._build_csp_policy()

    def _build_csp_policy(self) -> str:
        """
        Build Content-Security-Policy based on environment.

        Production: Strict policy with specific origins
        Development: More permissive for local development
        """
        if self.environment == "production":
            # Strict CSP for production
            return (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "img-src 'self' data: https: blob:; "
                "connect-src 'self' wss: https:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'; "
                "upgrade-insecure-requests"
            )
        else:
            # More permissive CSP for development/testing
            return (
                "default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://cdn.jsdelivr.net; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
                "font-src 'self' https://fonts.gstatic.com data:; "
                "img-src 'self' data: https: blob: http:; "
                "connect-src 'self' ws: wss: http: https:; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request and add security headers to response.

        Skip header addition for:
        - Health check endpoints
        - Metrics endpoints (may conflict with Prometheus scrapers)
        """
        if not self.enabled:
            return await call_next(request)

        # Process request
        response = await call_next(request)

        # Skip security headers for certain endpoints to avoid conflicts
        skip_paths = ["/health", "/metrics"]
        if any(request.url.path.startswith(path) for path in skip_paths):
            return response

        # HSTS (HTTP Strict Transport Security)
        # Enforces HTTPS connections for 1 year, including all subdomains
        if self.environment == "production":
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )
        else:
            # Shorter duration for non-production to avoid HSTS issues in development
            response.headers["Strict-Transport-Security"] = "max-age=300; includeSubDomains"

        # X-Content-Type-Options
        # Prevents browsers from MIME-sniffing responses away from declared content-type
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options
        # Prevents page from being embedded in frames/iframes to protect against clickjacking
        response.headers["X-Frame-Options"] = "DENY"

        # X-XSS-Protection
        # Enables browser's XSS filtering (legacy header, but still useful for older browsers)
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Content-Security-Policy (CSP)
        # Controls which resources the browser is allowed to load
        response.headers["Content-Security-Policy"] = self.csp_policy

        # Referrer-Policy
        # Controls how much referrer information is sent with requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy (formerly Feature-Policy)
        # Controls which browser features and APIs can be used
        response.headers["Permissions-Policy"] = (
            "geolocation=(), "
            "microphone=(), "
            "camera=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "speaker=()"
        )

        # X-Permitted-Cross-Domain-Policies
        # Restricts Adobe Flash and PDF cross-domain policies
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # Cache-Control for sensitive endpoints
        # Prevent caching of potentially sensitive API responses
        if request.url.path.startswith("/api/"):
            if "Cache-Control" not in response.headers:
                response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                response.headers["Pragma"] = "no-cache"

        return response


def add_security_headers_middleware(app, environment: str = None) -> None:
    """
    Helper function to add security headers middleware to FastAPI app.

    Args:
        app: FastAPI application instance
        environment: Environment name (production, staging, development, testing)

    Example:
        from backend.middleware.security_headers import add_security_headers_middleware

        app = FastAPI()
        add_security_headers_middleware(app, environment="production")
    """
    app.add_middleware(SecurityHeadersMiddleware, environment=environment)
