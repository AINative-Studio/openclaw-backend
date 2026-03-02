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

    try:
        from backend.api.v1.endpoints.openclaw_skills import router as openclaw_skills_router
        app.include_router(openclaw_skills_router, prefix=prefix)
    except Exception as e:
        print(f"Warning: openclaw_skills router not loaded: {e}")

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


@app.get("/health")
async def health():
    return {"status": "ok"}
