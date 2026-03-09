"""
Legacy route compatibility layer

Provides backward-compatible routes without /api/v1 prefix for frontend
that expects the old API structure. All requests are proxied to the
proper /api/v1 endpoints.
"""

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
import httpx

router = APIRouter(tags=["Legacy Compatibility"])

PROXY_BASE = "http://localhost:8000/api/v1"


@router.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def legacy_proxy(path: str, request: Request):
    """Proxy all legacy routes to /api/v1 endpoints"""
    # CRITICAL: Don't proxy if path already starts with api/v1 (prevents infinite loop)
    if path.startswith("api/v1/"):
        return JSONResponse(
            status_code=404,
            content={"detail": "Not found - this should have been handled by a specific router"},
        )

    # Allow specific top-level routes (health, docs, etc.) to pass through
    # These are defined directly on the app, not under /api/v1
    top_level_routes = {"health", "docs", "redoc", "openapi.json"}
    if path in top_level_routes or path.split("/")[0] in top_level_routes:
        return JSONResponse(
            status_code=404,
            content={"detail": "Not found - this should have been handled by app-level router"},
        )

    # Build target URL
    target_url = f"{PROXY_BASE}/{path}"
    if request.url.query:
        target_url += f"?{request.url.query}"
    
    # Forward request
    async with httpx.AsyncClient() as client:
        try:
            # Get request body if present
            body = await request.body()
            
            # Forward the request with the same method, headers, and body
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=dict(request.headers),
                content=body,
                timeout=30.0,
            )
            
            # Return the proxied response
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
        except httpx.RequestError as e:
            return JSONResponse(
                status_code=503,
                content={"detail": f"Proxy error: {str(e)}"},
            )
