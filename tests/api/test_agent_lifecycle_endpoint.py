"""
Agent Lifecycle CRUD API Endpoint Tests

Tests for all 9 agent lifecycle REST endpoints.
BDD style with GIVEN/WHEN/THEN docstrings.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.agent_lifecycle import router


@pytest.fixture
def app():
    """Create FastAPI test app with agent lifecycle router"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


def _make_mock_agent(**overrides):
    """Build a mock agent ORM instance"""
    now = datetime.now(timezone.utc)
    agent_id = overrides.get("id", uuid4())

    class MockStatus:
        def __init__(self, value):
            self.value = value

    agent = MagicMock()
    agent.id = agent_id
    agent.name = overrides.get("name", "Test Agent")
    agent.persona = overrides.get("persona", "A test agent")
    agent.model = overrides.get("model", "anthropic/claude-opus-4-5")
    agent.user_id = overrides.get("user_id", uuid4())
    agent.status = MockStatus(overrides.get("status", "running"))
    agent.openclaw_session_key = overrides.get("openclaw_session_key", None)
    agent.openclaw_agent_id = overrides.get("openclaw_agent_id", None)
    agent.heartbeat_enabled = overrides.get("heartbeat_enabled", False)
    agent.heartbeat_interval = overrides.get("heartbeat_interval", None)
    agent.heartbeat_checklist = overrides.get("heartbeat_checklist", None)
    agent.last_heartbeat_at = overrides.get("last_heartbeat_at", None)
    agent.next_heartbeat_at = overrides.get("next_heartbeat_at", None)
    agent.configuration = overrides.get("configuration", {})
    agent.error_message = overrides.get("error_message", None)
    agent.error_count = overrides.get("error_count", 0)
    agent.created_at = overrides.get("created_at", now)
    agent.updated_at = overrides.get("updated_at", None)
    agent.provisioned_at = overrides.get("provisioned_at", None)
    agent.paused_at = overrides.get("paused_at", None)
    agent.stopped_at = overrides.get("stopped_at", None)
    return agent


def _mock_db():
    """Create a mock database session"""
    return MagicMock()


class TestListAgents:
    """Tests for GET /agents"""

    def test_returns_200_with_agents(self, client):
        """
        GIVEN agents exist in the database
        WHEN GET /api/v1/agents is called
        THEN it should return 200 with agent list
        """
        agents = [_make_mock_agent(name="Agent A"), _make_mock_agent(name="Agent B")]

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.list_agents.return_value = (agents, 2)

            response = client.get("/api/v1/agents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["agents"]) == 2
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_returns_empty_list(self, client):
        """
        GIVEN no agents exist
        WHEN GET /api/v1/agents is called
        THEN it should return 200 with empty list
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.list_agents.return_value = ([], 0)

            response = client.get("/api/v1/agents")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["agents"] == []

    def test_filters_by_status(self, client):
        """
        GIVEN agents with different statuses
        WHEN GET /api/v1/agents?status=running is called
        THEN it should pass status filter to service
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.list_agents.return_value = ([], 0)

            response = client.get("/api/v1/agents?status=running")

        assert response.status_code == 200
        instance.list_agents.assert_called_once_with(status="running", limit=50, offset=0)

    def test_accepts_pagination_params(self, client):
        """
        GIVEN pagination parameters
        WHEN GET /api/v1/agents?limit=10&offset=5
        THEN it should pass them to service
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.list_agents.return_value = ([], 0)

            response = client.get("/api/v1/agents?limit=10&offset=5")

        assert response.status_code == 200
        instance.list_agents.assert_called_once_with(status=None, limit=10, offset=5)


class TestGetAgent:
    """Tests for GET /agents/{agent_id}"""

    def test_returns_200_with_agent(self, client):
        """
        GIVEN an agent exists
        WHEN GET /api/v1/agents/{id} is called
        THEN it should return 200 with agent detail
        """
        agent = _make_mock_agent(name="My Agent")

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_agent.return_value = agent

            response = client.get(f"/api/v1/agents/{agent.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Agent"

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN an agent does not exist
        WHEN GET /api/v1/agents/{id} is called
        THEN it should return 404
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_agent.return_value = None

            response = client.get("/api/v1/agents/nonexistent-id")

        assert response.status_code == 404


class TestCreateAgent:
    """Tests for POST /agents"""

    def test_returns_201_on_create(self, client):
        """
        GIVEN valid agent data
        WHEN POST /api/v1/agents is called
        THEN it should return 201 with created agent
        """
        agent = _make_mock_agent(name="New Agent", status="provisioning")

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.create_agent.return_value = agent

            response = client.post(
                "/api/v1/agents",
                json={"name": "New Agent", "model": "anthropic/claude-opus-4-5"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Agent"
        assert data["status"] == "provisioning"

    def test_returns_422_on_missing_fields(self, client):
        """
        GIVEN missing required fields
        WHEN POST /api/v1/agents is called
        THEN it should return 422
        """
        response = client.post("/api/v1/agents", json={})
        assert response.status_code == 422

    def test_creates_with_heartbeat_config(self, client):
        """
        GIVEN agent data with heartbeat config
        WHEN POST /api/v1/agents is called
        THEN it should create with heartbeat settings
        """
        agent = _make_mock_agent(heartbeat_enabled=True)

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.create_agent.return_value = agent

            response = client.post(
                "/api/v1/agents",
                json={
                    "name": "Agent",
                    "model": "claude",
                    "heartbeat": {"enabled": True, "interval": "5m"},
                },
            )

        assert response.status_code == 201


class TestProvisionAgent:
    """Tests for POST /agents/{agent_id}/provision"""

    def test_returns_200_on_provision(self, client):
        """
        GIVEN an agent in provisioning state
        WHEN POST /api/v1/agents/{id}/provision is called
        THEN it should return 200 with running status
        """
        agent = _make_mock_agent(status="running")

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.provision_agent.return_value = agent

            response = client.post(f"/api/v1/agents/{agent.id}/provision")

        assert response.status_code == 200
        assert response.json()["status"] == "running"

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN agent does not exist
        WHEN POST /api/v1/agents/{id}/provision is called
        THEN it should return 404
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.provision_agent.return_value = None

            response = client.post("/api/v1/agents/nonexistent/provision")

        assert response.status_code == 404

    def test_returns_409_on_invalid_state(self, client):
        """
        GIVEN agent already running
        WHEN POST /api/v1/agents/{id}/provision is called
        THEN it should return 409
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.provision_agent.side_effect = ValueError("Cannot provision")

            response = client.post("/api/v1/agents/some-id/provision")

        assert response.status_code == 409


class TestPauseAgent:
    """Tests for POST /agents/{agent_id}/pause"""

    def test_returns_200_on_pause(self, client):
        """
        GIVEN an agent in running state
        WHEN POST /api/v1/agents/{id}/pause is called
        THEN it should return 200 with paused status
        """
        agent = _make_mock_agent(status="paused")

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.pause_agent.return_value = agent

            response = client.post(f"/api/v1/agents/{agent.id}/pause")

        assert response.status_code == 200
        assert response.json()["status"] == "paused"

    def test_returns_409_on_invalid_state(self, client):
        """
        GIVEN agent not in running state
        WHEN POST /api/v1/agents/{id}/pause is called
        THEN it should return 409
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.pause_agent.side_effect = ValueError("Cannot pause")

            response = client.post("/api/v1/agents/some-id/pause")

        assert response.status_code == 409


class TestResumeAgent:
    """Tests for POST /agents/{agent_id}/resume"""

    def test_returns_200_on_resume(self, client):
        """
        GIVEN an agent in paused state
        WHEN POST /api/v1/agents/{id}/resume is called
        THEN it should return 200 with running status
        """
        agent = _make_mock_agent(status="running")

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.resume_agent.return_value = agent

            response = client.post(f"/api/v1/agents/{agent.id}/resume")

        assert response.status_code == 200
        assert response.json()["status"] == "running"

    def test_returns_409_on_invalid_state(self, client):
        """
        GIVEN agent not in paused state
        WHEN POST /api/v1/agents/{id}/resume is called
        THEN it should return 409
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.resume_agent.side_effect = ValueError("Cannot resume")

            response = client.post("/api/v1/agents/some-id/resume")

        assert response.status_code == 409


class TestUpdateSettings:
    """Tests for PATCH /agents/{agent_id}/settings"""

    def test_returns_200_on_update(self, client):
        """
        GIVEN valid update data
        WHEN PATCH /api/v1/agents/{id}/settings is called
        THEN it should return 200 with updated agent
        """
        agent = _make_mock_agent(persona="Updated persona")

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.update_settings.return_value = agent

            response = client.patch(
                f"/api/v1/agents/{agent.id}/settings",
                json={"persona": "Updated persona"},
            )

        assert response.status_code == 200
        assert response.json()["persona"] == "Updated persona"

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN agent does not exist
        WHEN PATCH /api/v1/agents/{id}/settings is called
        THEN it should return 404
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.update_settings.return_value = None

            response = client.patch(
                "/api/v1/agents/nonexistent/settings",
                json={"persona": "test"},
            )

        assert response.status_code == 404


class TestDeleteAgent:
    """Tests for DELETE /agents/{agent_id}"""

    def test_returns_204_on_delete(self, client):
        """
        GIVEN an agent exists
        WHEN DELETE /api/v1/agents/{id} is called
        THEN it should return 204
        """
        agent = _make_mock_agent(status="stopped")

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.delete_agent.return_value = agent

            response = client.delete(f"/api/v1/agents/{agent.id}")

        assert response.status_code == 204

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN agent does not exist
        WHEN DELETE /api/v1/agents/{id} is called
        THEN it should return 404
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.delete_agent.return_value = None

            response = client.delete("/api/v1/agents/nonexistent")

        assert response.status_code == 404


class TestExecuteHeartbeat:
    """Tests for POST /agents/{agent_id}/heartbeat"""

    def test_returns_200_on_heartbeat(self, client):
        """
        GIVEN a running agent
        WHEN POST /api/v1/agents/{id}/heartbeat is called
        THEN it should return 200 with completion status
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.execute_heartbeat.return_value = {
                "status": "completed",
                "message": "Heartbeat executed for agent 'Test'",
            }

            response = client.post("/api/v1/agents/some-id/heartbeat")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN agent does not exist
        WHEN POST /api/v1/agents/{id}/heartbeat is called
        THEN it should return 404
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.execute_heartbeat.return_value = None

            response = client.post("/api/v1/agents/nonexistent/heartbeat")

        assert response.status_code == 404

    def test_returns_409_on_invalid_state(self, client):
        """
        GIVEN agent not in running state
        WHEN POST /api/v1/agents/{id}/heartbeat is called
        THEN it should return 409
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.execute_heartbeat.side_effect = ValueError("Agent not running")

            response = client.post("/api/v1/agents/some-id/heartbeat")

        assert response.status_code == 409


class TestServiceUnavailable:
    """Tests for service unavailability"""

    def test_returns_503_when_service_unavailable(self, client):
        """
        GIVEN agent lifecycle service is not available
        WHEN any endpoint is called
        THEN it should return 503
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AGENT_LIFECYCLE_AVAILABLE",
            False,
        ):
            response = client.get("/api/v1/agents")

        assert response.status_code == 503

    def test_returns_503_for_post_when_unavailable(self, client):
        """
        GIVEN agent lifecycle service is not available
        WHEN POST /agents is called
        THEN it should return 503
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AGENT_LIFECYCLE_AVAILABLE",
            False,
        ):
            response = client.post(
                "/api/v1/agents",
                json={"name": "Test", "model": "claude"},
            )

        assert response.status_code == 503


class TestAgentResponseSchema:
    """Tests for response schema correctness"""

    def test_response_contains_all_fields(self, client):
        """
        GIVEN a complete agent record
        WHEN GET /api/v1/agents/{id} is called
        THEN response should contain all expected fields
        """
        agent = _make_mock_agent()

        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.get_agent.return_value = agent

            response = client.get(f"/api/v1/agents/{agent.id}")

        assert response.status_code == 200
        data = response.json()
        expected_keys = {
            "id", "name", "persona", "model", "user_id", "status",
            "openclaw_session_key", "openclaw_agent_id",
            "heartbeat_enabled", "heartbeat_interval", "heartbeat_checklist",
            "last_heartbeat_at", "next_heartbeat_at",
            "configuration", "error_message", "error_count",
            "created_at", "updated_at", "provisioned_at", "paused_at", "stopped_at",
        }
        assert set(data.keys()) == expected_keys

    def test_list_response_structure(self, client):
        """
        GIVEN agents in the database
        WHEN GET /api/v1/agents is called
        THEN response should have correct list structure
        """
        with patch(
            "backend.api.v1.endpoints.agent_lifecycle.AgentLifecycleApiService"
        ) as MockService:
            instance = MockService.return_value
            instance.list_agents.return_value = ([_make_mock_agent()], 1)

            response = client.get("/api/v1/agents")

        data = response.json()
        assert "agents" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["agents"], list)
