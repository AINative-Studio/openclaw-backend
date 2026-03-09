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

app = FastAPI(
    title="AgentClaw Backend",
    description="Backend API for AgentClaw AI Agent Management Platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
