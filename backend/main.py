"""
FastAPI application entrypoint

Registers all API routers and initializes the database.
"""

import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from backend.middleware.security_headers import add_security_headers_middleware
from backend.middleware.rate_limit import (
    limiter,
    rate_limit_exceeded_handler,
    is_rate_limiting_enabled,
    get_rate_limit_stats,
)
from slowapi.errors import RateLimitExceeded

from backend.db.base import init_db

# Auto-instrument FastAPI + Anthropic with Datadog APM when enabled
if os.getenv("DD_LLMOBS_ENABLED", "0") == "1":
    try:
        from ddtrace import config as dd_config, patch
        # Enable agentless trace submission (no local DD Agent required)
        dd_config._trace_agent_url = f"https://trace.agent.{os.getenv('DD_SITE', 'datadoghq.com')}"
        patch(fastapi=True, anthropic=True)
    except ImportError:
        pass

# Security: Disable API documentation in production environments
# Docs are enabled in development, staging, and testing environments
environment = os.getenv("ENVIRONMENT", "development").lower()
enable_docs = environment in ("development", "staging", "testing", "test")

docs_url = "/docs" if enable_docs else None
redoc_url = "/redoc" if enable_docs else None
openapi_url = "/openapi.json" if enable_docs else None

app = FastAPI(
    title="AgentClaw Backend",
    description="Backend API for AgentClaw AI Agent Management Platform",
    version="1.0.0",
    docs_url=docs_url,
    redoc_url=redoc_url,
    openapi_url=openapi_url,
)

# Register rate limiter with FastAPI app
if is_rate_limiting_enabled():
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
    print(f"✅ Rate limiting enabled: {get_rate_limit_stats()}")
else:
    print("⚠️ Rate limiting is disabled")

# Configure CORS with explicit origin whitelist
# Parse allowed origins from environment
ALLOWED_ORIGINS_STR = os.getenv("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS = [origin.strip() for origin in ALLOWED_ORIGINS_STR.split(",") if origin.strip()]

# Development fallback with explicit localhost origins
if not ALLOWED_ORIGINS:
    if environment in ("development", "staging", "testing", "test"):
        # Development/testing: Allow localhost on common ports
        ALLOWED_ORIGINS = [
            "http://localhost:3000",
            "http://localhost:3002",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:3002",
        ]
        print(f"CORS: Using development fallback origins: {ALLOWED_ORIGINS}")
    else:
        # Production: ALLOWED_ORIGINS is required
        raise ValueError(
            "ALLOWED_ORIGINS environment variable must be set in production. "
            "Example: ALLOWED_ORIGINS=https://app.example.com,https://api.example.com"
        )

# Add CORS middleware with security hardening
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,  # Explicit whitelist (no wildcards)
    allow_credentials=True,  # Allow cookies/auth headers
    allow_methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],  # Specific methods only
    allow_headers=[
        "Authorization",
        "Content-Type",
        "Accept",
        "Origin",
        "User-Agent",
        "DNT",
        "Cache-Control",
        "X-Requested-With",
    ],  # Specific headers only
    max_age=600,  # Cache preflight requests for 10 minutes
)

# Add Security Headers Middleware (OWASP best practices)
# Implements: HSTS, X-Content-Type-Options, X-Frame-Options, CSP, etc.
add_security_headers_middleware(app, environment=environment)

# Add TrustedHostMiddleware to prevent Host header attacks
# Parse allowed hosts from environment
ALLOWED_HOSTS_STR = os.getenv("ALLOWED_HOSTS", "")
ALLOWED_HOSTS = [host.strip() for host in ALLOWED_HOSTS_STR.split(",") if host.strip()]

# Development fallback with localhost
if not ALLOWED_HOSTS:
    if environment in ("development", "staging", "testing", "test"):
        ALLOWED_HOSTS = [
            "localhost",
            "127.0.0.1",
            "*.localhost",
            "*.127.0.0.1",
        ]
        print(f"TrustedHost: Using development fallback hosts: {ALLOWED_HOSTS}")
    else:
        # Production: ALLOWED_HOSTS is required
        raise ValueError(
            "ALLOWED_HOSTS environment variable must be set in production. "
            "Example: ALLOWED_HOSTS=api.example.com,app.example.com"
        )

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=ALLOWED_HOSTS
)


# Register routers — each uses try/except so unavailable services don't block startup
def _register_routers() -> None:
    prefix = "/api/v1"

    try:
        from backend.api.v1.endpoints.agent_lifecycle import router as agent_router
        app.include_router(agent_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: agent_lifecycle router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.agent_personality import router as personality_router
        app.include_router(personality_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: agent_personality router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.agent_swarm import router as swarm_router
        app.include_router(swarm_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: agent_swarm router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.swarm_health import router as health_router
        app.include_router(health_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: swarm_health router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.swarm_timeline import router as timeline_router
        app.include_router(timeline_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: swarm_timeline router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.swarm_alerts import router as alerts_router
        app.include_router(alerts_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: swarm_alerts router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.swarm_monitoring import router as monitoring_router
        app.include_router(monitoring_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: swarm_monitoring router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.metrics import router as metrics_router
        app.include_router(metrics_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: metrics router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.wireguard_health import router as wg_health_router
        app.include_router(wg_health_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: wireguard_health router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.wireguard_provisioning import router as wg_prov_router
        app.include_router(wg_prov_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: wireguard_provisioning router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.agent_template import router as template_router
        app.include_router(template_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: agent_template router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.skill_installation_audit import router as skill_audit_router
        app.include_router(skill_audit_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: skill_installation_audit router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.workspace_settings import router as workspace_settings_router
        app.include_router(workspace_settings_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: workspace_settings router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.team import router as team_router
        app.include_router(team_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: team router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.network_management import router as network_mgmt_router
        app.include_router(network_mgmt_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: network_management router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.task_queue import router as task_queue_router
        app.include_router(task_queue_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: task_queue router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.api_keys import router as api_keys_router
        app.include_router(api_keys_router)
    except Exception as e:
        print(f"Warning: api_keys router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.user_api_keys import router as user_api_keys_router
        app.include_router(user_api_keys_router)
    except Exception as e:
        print(f"Warning: user_api_keys router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.security import router as security_router
        app.include_router(security_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: security router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.channels import router as channels_router
        app.include_router(channels_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: channels router not loaded: {e}")

    # IMPORTANT: Register skill_installation_router BEFORE openclaw_skills_router
    # to avoid /skills/installable being caught by /skills/{skill_name}
    try:
        from backend.api.v1.endpoints.skill_installation import router as skill_installation_router
        app.include_router(skill_installation_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: skill_installation router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.openclaw_skills import router as openclaw_skills_router
        app.include_router(openclaw_skills_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: openclaw_skills router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.conversations import router as conversations_router
        app.include_router(conversations_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: conversations router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.agent_skill_config import router as agent_skill_config_router
        app.include_router(agent_skill_config_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: agent_skill_config router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.agent_channels import router as agent_channels_router
        app.include_router(agent_channels_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: agent_channels router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.zalo import router as zalo_router
        app.include_router(zalo_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: zalo router not loaded: {e}")

    try:
        from backend.api.v1.endpoints.openclaw_channels import router as openclaw_channels_router
        app.include_router(openclaw_channels_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: openclaw_channels router not loaded: {e}")


    # Legacy compatibility routes (DISABLED - causing redirect loop)
    # TODO: Re-enable with proper path exclusion if needed
    # try:
    #     from backend.api.v1.endpoints.legacy_routes import router as legacy_router
    #     app.include_router(legacy_router)  # NO PREFIX - proxies to /api/v1
    # except Exception as e:
    #     print(f"Warning: legacy_routes router not loaded: {e}")
_register_routers()


@app.on_event("startup")
async def startup():
    # Validate CORS configuration on startup
    if "*" in ALLOWED_ORIGINS:
        raise ValueError(
            "CRITICAL SECURITY ERROR: Wildcard CORS origins (*) are not allowed. "
            "This creates a security vulnerability allowing any domain to make authenticated requests. "
            "Set ALLOWED_ORIGINS environment variable with explicit domain whitelist."
        )

    for origin in ALLOWED_ORIGINS:
        if not origin.startswith(("http://", "https://")):
            raise ValueError(
                f"Invalid origin format: {origin}. "
                f"Origins must start with http:// or https://. "
                f"Example: https://app.example.com"
            )

    print(f"CORS: Configured with {len(ALLOWED_ORIGINS)} allowed origins")

    init_db()

    try:
        from backend.services.agent_template_api_service import AgentTemplateApiService
        from backend.db.base import SessionLocal
        db = SessionLocal()
        try:
            service = AgentTemplateApiService(db)
            service.seed_templates("default-user")
        finally:
            db.close()
    except Exception as e:
        print(f"Warning: template seeding failed: {e}")

    # Initialize default agents (main agent with Haiku model)
    try:
        from backend.services.agent_initialization_service import initialize_agents_on_startup
        from backend.db.base import SessionLocal
        db = SessionLocal()
        try:
            result = await initialize_agents_on_startup(db)
            print(f"✅ Agent initialization: {result.get('main_agent', {}).get('status', 'unknown')}")
        finally:
            db.close()
    except Exception as e:
        print(f"Warning: agent initialization failed: {e}")

    # Initialize Datadog LLMObs singleton when enabled
    if os.getenv("DD_LLMOBS_ENABLED", "0") == "1":
        try:
            from backend.services.datadog_service import get_datadog_service
            get_datadog_service()
        except Exception:
            pass

    # Register monitoring services for health dashboard
    try:
        from backend.services.swarm_health_service import get_swarm_health_service
        from backend.services.prometheus_metrics_service import get_metrics_service
        from backend.services.monitoring_integration_service import get_monitoring_integration_service

        health_service = get_swarm_health_service()
        metrics_service = get_metrics_service()
        monitoring_service = get_monitoring_integration_service()

        # Instantiate subsystem services for monitoring
        subsystems = {}

        # Lease expiration service
        try:
            from backend.services.lease_expiration_service import get_lease_expiration_service
            subsystems["lease_expiration"] = get_lease_expiration_service()
        except Exception as e:
            print(f"Warning: lease_expiration service not available: {e}")

        # Result buffer service
        try:
            from backend.services.result_buffer_service import get_result_buffer_service
            subsystems["result_buffer"] = get_result_buffer_service()
        except Exception as e:
            print(f"Warning: result_buffer service not available: {e}")

        # Partition detection service
        try:
            from backend.services.dbos_partition_detection_service import get_partition_detection_service
            subsystems["partition_detection"] = get_partition_detection_service()
        except Exception as e:
            print(f"Warning: partition_detection service not available: {e}")

        # Node crash detection service
        try:
            from backend.services.node_crash_detection_service import get_node_crash_detection_service
            subsystems["node_crash_detection"] = get_node_crash_detection_service()
        except Exception as e:
            print(f"Warning: node_crash_detection service not available: {e}")

        # Lease revocation service
        try:
            from backend.services.lease_revocation_service import get_lease_revocation_service
            subsystems["lease_revocation"] = get_lease_revocation_service()
        except Exception as e:
            print(f"Warning: lease_revocation service not available: {e}")

        # Duplicate prevention service
        try:
            from backend.services.duplicate_prevention_service import get_duplicate_prevention_service
            subsystems["duplicate_prevention"] = get_duplicate_prevention_service()
        except Exception as e:
            print(f"Warning: duplicate_prevention service not available: {e}")

        # Message verification service
        try:
            from backend.security.message_verification_service import get_message_verification_service
            subsystems["message_verification"] = get_message_verification_service()
        except Exception as e:
            print(f"Warning: message_verification service not available: {e}")

        # Bootstrap monitoring - registers all subsystems
        # Note: IP pool service requires network configuration, so it's registered separately when needed
        monitoring_service.bootstrap(subsystems)

        print(f"✅ Monitoring services initialized with {len(subsystems)}/7 subsystems")
    except Exception as e:
        print(f"Warning: monitoring services initialization failed: {e}")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/rate-limit-status")
async def rate_limit_status():
    """
    Get rate limiting configuration and status.

    Returns current rate limit configuration, backend type,
    and active rate limit profiles.
    """
    return get_rate_limit_stats()


@app.get("/metrics")
async def root_metrics():
    """
    Root-level /metrics endpoint for Prometheus scraping.

    This endpoint is provided at the root level (without /api/v1 prefix)
    for compatibility with Prometheus and other monitoring tools that
    expect metrics at the conventional /metrics path.
    """
    from fastapi.responses import Response
    from backend.services.prometheus_metrics_service import get_metrics_service

    PROMETHEUS_CONTENT_TYPE = "text/plain; version=0.0.4; charset=utf-8"

    service = get_metrics_service()
    service.collect_service_stats()
    content = service.generate_metrics()
    return Response(content=content, media_type=PROMETHEUS_CONTENT_TYPE)
