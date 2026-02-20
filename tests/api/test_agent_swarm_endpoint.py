"""
Agent Swarm CRUD API Endpoint Tests

Tests for all 10 swarm lifecycle REST endpoints.
BDD style with GIVEN/WHEN/THEN docstrings.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.agent_swarm import router


@pytest.fixture
def app():
    """Create FastAPI test app with swarm router"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


def _make_mock_swarm(**overrides):
    """Build a mock swarm ORM instance"""
    now = datetime.now(timezone.utc)
    swarm_id = overrides.get("id", uuid4())

    class MockStatus:
        def __init__(self, value):
            self.value = value

    class MockStrategy:
        def __init__(self, value):
            self.value = value

    swarm = MagicMock()
    swarm.id = swarm_id
    swarm.name = overrides.get("name", "Test Swarm")
    swarm.description = overrides.get("description", "A test swarm")
    swarm.strategy = MockStrategy(overrides.get("strategy", "parallel"))
    swarm.goal = overrides.get("goal", "Build an app")
    swarm.status = MockStatus(overrides.get("status", "idle"))
    swarm.agent_ids = overrides.get("agent_ids", [])
    swarm.user_id = overrides.get("user_id", uuid4())
    swarm.configuration = overrides.get("configuration", {})
    swarm.error_message = overrides.get("error_message", None)
    swarm.created_at = overrides.get("created_at", now)
    swarm.updated_at = overrides.get("updated_at", None)
    swarm.started_at = overrides.get("started_at", None)
    swarm.paused_at = overrides.get("paused_at", None)
    swarm.stopped_at = overrides.get("stopped_at", None)
    return swarm


SERVICE_PATH = "backend.api.v1.endpoints.agent_swarm.AgentSwarmApiService"


class TestListSwarms:
    """Tests for GET /swarms"""

    def test_returns_200_with_swarms(self, client):
        """
        GIVEN swarms exist in the database
        WHEN GET /api/v1/swarms is called
        THEN it should return 200 with swarm list
        """
        swarms = [_make_mock_swarm(name="Swarm A"), _make_mock_swarm(name="Swarm B")]

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.list_swarms.return_value = (swarms, 2)

            response = client.get("/api/v1/swarms")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["swarms"]) == 2
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_returns_empty_list(self, client):
        """
        GIVEN no swarms exist
        WHEN GET /api/v1/swarms is called
        THEN it should return 200 with empty list
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.list_swarms.return_value = ([], 0)

            response = client.get("/api/v1/swarms")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["swarms"] == []

    def test_filters_by_status(self, client):
        """
        GIVEN swarms with different statuses
        WHEN GET /api/v1/swarms?status=running is called
        THEN it should pass status filter to service
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.list_swarms.return_value = ([], 0)

            response = client.get("/api/v1/swarms?status=running")

        assert response.status_code == 200
        instance.list_swarms.assert_called_once_with(status="running", limit=50, offset=0)

    def test_accepts_pagination_params(self, client):
        """
        GIVEN pagination parameters
        WHEN GET /api/v1/swarms?limit=10&offset=5
        THEN it should pass them to service
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.list_swarms.return_value = ([], 0)

            response = client.get("/api/v1/swarms?limit=10&offset=5")

        assert response.status_code == 200
        instance.list_swarms.assert_called_once_with(status=None, limit=10, offset=5)


class TestGetSwarm:
    """Tests for GET /swarms/{swarm_id}"""

    def test_returns_200_with_swarm(self, client):
        """
        GIVEN a swarm exists
        WHEN GET /api/v1/swarms/{id} is called
        THEN it should return 200 with swarm detail
        """
        swarm = _make_mock_swarm(name="My Swarm")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.get_swarm.return_value = swarm

            response = client.get(f"/api/v1/swarms/{swarm.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Swarm"

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN a swarm does not exist
        WHEN GET /api/v1/swarms/{id} is called
        THEN it should return 404
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.get_swarm.return_value = None

            response = client.get("/api/v1/swarms/nonexistent-id")

        assert response.status_code == 404


class TestCreateSwarm:
    """Tests for POST /swarms"""

    def test_returns_201_on_create(self, client):
        """
        GIVEN valid swarm data
        WHEN POST /api/v1/swarms is called
        THEN it should return 201 with created swarm
        """
        swarm = _make_mock_swarm(name="New Swarm", status="idle")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.create_swarm.return_value = swarm

            response = client.post(
                "/api/v1/swarms",
                json={"name": "New Swarm", "strategy": "parallel"},
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Swarm"
        assert data["status"] == "idle"

    def test_returns_201_with_agents(self, client):
        """
        GIVEN swarm data with agent IDs
        WHEN POST /api/v1/swarms is called
        THEN it should create swarm with agents
        """
        agent_ids = [str(uuid4()), str(uuid4())]
        swarm = _make_mock_swarm(agent_ids=agent_ids)

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.create_swarm.return_value = swarm

            response = client.post(
                "/api/v1/swarms",
                json={
                    "name": "Team Swarm",
                    "strategy": "sequential",
                    "agent_ids": agent_ids,
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["agent_count"] == 2

    def test_returns_422_on_missing_fields(self, client):
        """
        GIVEN missing required fields
        WHEN POST /api/v1/swarms is called
        THEN it should return 422
        """
        response = client.post("/api/v1/swarms", json={})
        assert response.status_code == 422


class TestUpdateSwarm:
    """Tests for PATCH /swarms/{swarm_id}"""

    def test_returns_200_on_update(self, client):
        """
        GIVEN valid update data
        WHEN PATCH /api/v1/swarms/{id} is called
        THEN it should return 200 with updated swarm
        """
        swarm = _make_mock_swarm(name="Updated Swarm")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.update_swarm.return_value = swarm

            response = client.patch(
                f"/api/v1/swarms/{swarm.id}",
                json={"name": "Updated Swarm"},
            )

        assert response.status_code == 200
        assert response.json()["name"] == "Updated Swarm"

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN swarm does not exist
        WHEN PATCH /api/v1/swarms/{id} is called
        THEN it should return 404
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.update_swarm.return_value = None

            response = client.patch(
                "/api/v1/swarms/nonexistent",
                json={"name": "test"},
            )

        assert response.status_code == 404


class TestAddAgents:
    """Tests for POST /swarms/{swarm_id}/agents"""

    def test_returns_200_agents_added(self, client):
        """
        GIVEN a swarm exists
        WHEN POST /api/v1/swarms/{id}/agents is called with agent IDs
        THEN it should return 200 with updated swarm
        """
        agent_id = str(uuid4())
        swarm = _make_mock_swarm(agent_ids=[agent_id])

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.add_agents.return_value = swarm

            response = client.post(
                f"/api/v1/swarms/{swarm.id}/agents",
                json={"agent_ids": [agent_id]},
            )

        assert response.status_code == 200
        assert len(response.json()["agent_ids"]) == 1

    def test_returns_404_swarm_not_found(self, client):
        """
        GIVEN swarm does not exist
        WHEN POST /api/v1/swarms/{id}/agents is called
        THEN it should return 404
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.add_agents.return_value = None

            response = client.post(
                "/api/v1/swarms/nonexistent/agents",
                json={"agent_ids": [str(uuid4())]},
            )

        assert response.status_code == 404


class TestRemoveAgents:
    """Tests for DELETE /swarms/{swarm_id}/agents"""

    def test_returns_200_agents_removed(self, client):
        """
        GIVEN a swarm with agents
        WHEN DELETE /api/v1/swarms/{id}/agents is called
        THEN it should return 200 with updated swarm
        """
        swarm = _make_mock_swarm(agent_ids=[])

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.remove_agents.return_value = swarm

            response = client.request(
                "DELETE",
                f"/api/v1/swarms/{swarm.id}/agents",
                json={"agent_ids": [str(uuid4())]},
            )

        assert response.status_code == 200
        assert response.json()["agent_ids"] == []

    def test_returns_404_swarm_not_found(self, client):
        """
        GIVEN swarm does not exist
        WHEN DELETE /api/v1/swarms/{id}/agents is called
        THEN it should return 404
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.remove_agents.return_value = None

            response = client.request(
                "DELETE",
                "/api/v1/swarms/nonexistent/agents",
                json={"agent_ids": [str(uuid4())]},
            )

        assert response.status_code == 404


class TestStartSwarm:
    """Tests for POST /swarms/{swarm_id}/start"""

    def test_returns_200_started_from_idle(self, client):
        """
        GIVEN a swarm in idle state
        WHEN POST /api/v1/swarms/{id}/start is called
        THEN it should return 200 with running status
        """
        swarm = _make_mock_swarm(status="running")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.start_swarm.return_value = swarm

            response = client.post(f"/api/v1/swarms/{swarm.id}/start")

        assert response.status_code == 200
        assert response.json()["status"] == "running"

    def test_returns_409_wrong_status(self, client):
        """
        GIVEN swarm already running
        WHEN POST /api/v1/swarms/{id}/start is called
        THEN it should return 409
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.start_swarm.side_effect = ValueError("Cannot start")

            response = client.post("/api/v1/swarms/some-id/start")

        assert response.status_code == 409

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN swarm does not exist
        WHEN POST /api/v1/swarms/{id}/start is called
        THEN it should return 404
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.start_swarm.return_value = None

            response = client.post("/api/v1/swarms/nonexistent/start")

        assert response.status_code == 404


class TestPauseSwarm:
    """Tests for POST /swarms/{swarm_id}/pause"""

    def test_returns_200_on_pause(self, client):
        """
        GIVEN a swarm in running state
        WHEN POST /api/v1/swarms/{id}/pause is called
        THEN it should return 200 with paused status
        """
        swarm = _make_mock_swarm(status="paused")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.pause_swarm.return_value = swarm

            response = client.post(f"/api/v1/swarms/{swarm.id}/pause")

        assert response.status_code == 200
        assert response.json()["status"] == "paused"

    def test_returns_409_on_invalid_state(self, client):
        """
        GIVEN swarm not in running state
        WHEN POST /api/v1/swarms/{id}/pause is called
        THEN it should return 409
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.pause_swarm.side_effect = ValueError("Cannot pause")

            response = client.post("/api/v1/swarms/some-id/pause")

        assert response.status_code == 409


class TestResumeSwarm:
    """Tests for POST /swarms/{swarm_id}/resume"""

    def test_returns_200_on_resume(self, client):
        """
        GIVEN a swarm in paused state
        WHEN POST /api/v1/swarms/{id}/resume is called
        THEN it should return 200 with running status
        """
        swarm = _make_mock_swarm(status="running")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.resume_swarm.return_value = swarm

            response = client.post(f"/api/v1/swarms/{swarm.id}/resume")

        assert response.status_code == 200
        assert response.json()["status"] == "running"

    def test_returns_409_on_invalid_state(self, client):
        """
        GIVEN swarm not in paused state
        WHEN POST /api/v1/swarms/{id}/resume is called
        THEN it should return 409
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.resume_swarm.side_effect = ValueError("Cannot resume")

            response = client.post("/api/v1/swarms/some-id/resume")

        assert response.status_code == 409


class TestStopSwarm:
    """Tests for DELETE /swarms/{swarm_id}"""

    def test_returns_204_on_delete(self, client):
        """
        GIVEN a swarm exists
        WHEN DELETE /api/v1/swarms/{id} is called
        THEN it should return 204
        """
        swarm = _make_mock_swarm(status="stopped")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.stop_swarm.return_value = swarm

            response = client.delete(f"/api/v1/swarms/{swarm.id}")

        assert response.status_code == 204

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN swarm does not exist
        WHEN DELETE /api/v1/swarms/{id} is called
        THEN it should return 404
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.stop_swarm.return_value = None

            response = client.delete("/api/v1/swarms/nonexistent")

        assert response.status_code == 404


class TestServiceUnavailable:
    """Tests for service unavailability"""

    def test_returns_503_when_service_unavailable(self, client):
        """
        GIVEN agent swarm service is not available
        WHEN any endpoint is called
        THEN it should return 503
        """
        with patch(
            "backend.api.v1.endpoints.agent_swarm.AGENT_SWARM_AVAILABLE",
            False,
        ):
            response = client.get("/api/v1/swarms")

        assert response.status_code == 503

    def test_returns_503_for_post_when_unavailable(self, client):
        """
        GIVEN agent swarm service is not available
        WHEN POST /swarms is called
        THEN it should return 503
        """
        with patch(
            "backend.api.v1.endpoints.agent_swarm.AGENT_SWARM_AVAILABLE",
            False,
        ):
            response = client.post(
                "/api/v1/swarms",
                json={"name": "Test", "strategy": "parallel"},
            )

        assert response.status_code == 503


class TestSwarmResponseSchema:
    """Tests for response schema correctness"""

    def test_response_contains_all_fields(self, client):
        """
        GIVEN a complete swarm record
        WHEN GET /api/v1/swarms/{id} is called
        THEN response should contain all expected fields
        """
        swarm = _make_mock_swarm()

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.get_swarm.return_value = swarm

            response = client.get(f"/api/v1/swarms/{swarm.id}")

        assert response.status_code == 200
        data = response.json()
        expected_keys = {
            "id", "name", "description", "strategy", "goal",
            "status", "agent_ids", "agent_count", "user_id",
            "configuration", "error_message",
            "created_at", "updated_at", "started_at", "paused_at", "stopped_at",
        }
        assert set(data.keys()) == expected_keys

    def test_list_response_structure(self, client):
        """
        GIVEN swarms in the database
        WHEN GET /api/v1/swarms is called
        THEN response should have correct list structure
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.list_swarms.return_value = ([_make_mock_swarm()], 1)

            response = client.get("/api/v1/swarms")

        data = response.json()
        assert "swarms" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert isinstance(data["swarms"], list)
