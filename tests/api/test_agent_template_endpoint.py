"""
Agent Template CRUD API Endpoint Tests

Tests for all 6 template REST endpoints plus seed.
BDD style with GIVEN/WHEN/THEN docstrings.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.agent_template import router


@pytest.fixture
def app():
    """Create FastAPI test app with template router"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


def _make_mock_template(**overrides):
    """Build a mock template ORM instance"""
    now = datetime.now(timezone.utc)
    template_id = overrides.get("id", str(uuid4()))

    class MockCategory:
        def __init__(self, value):
            self.value = value

    template = MagicMock()
    template.id = template_id
    template.name = overrides.get("name", "Test Template")
    template.description = overrides.get("description", "A test template")
    template.category = MockCategory(overrides.get("category", "engineering"))
    template.icons = overrides.get("icons", ["github", "linear"])
    template.default_model = overrides.get("default_model", "anthropic/claude-opus-4-5")
    template.default_persona = overrides.get("default_persona", "You are a test agent")
    template.default_heartbeat_interval = overrides.get("default_heartbeat_interval", "5m")
    template.default_checklist = overrides.get("default_checklist", ["Check item 1"])
    template.user_id = overrides.get("user_id", str(uuid4()))
    template.created_at = overrides.get("created_at", now)
    template.updated_at = overrides.get("updated_at", None)
    return template


SERVICE_PATH = "backend.api.v1.endpoints.agent_template.AgentTemplateApiService"


class TestListTemplates:
    """Tests for GET /templates"""

    def test_returns_200_with_templates(self, client):
        """
        GIVEN templates exist in the database
        WHEN GET /api/v1/templates is called
        THEN it should return 200 with template list
        """
        templates = [
            _make_mock_template(name="Template A"),
            _make_mock_template(name="Template B"),
        ]

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.list_templates.return_value = (templates, 2)

            response = client.get("/api/v1/templates")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["templates"]) == 2
        assert data["limit"] == 50
        assert data["offset"] == 0

    def test_returns_200_with_empty_list(self, client):
        """
        GIVEN no templates exist
        WHEN GET /api/v1/templates is called
        THEN it should return 200 with empty list
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.list_templates.return_value = ([], 0)

            response = client.get("/api/v1/templates")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["templates"]) == 0

    def test_filters_by_category(self, client):
        """
        GIVEN templates exist with different categories
        WHEN GET /api/v1/templates?category=engineering is called
        THEN it should pass the category filter to the service
        """
        templates = [_make_mock_template(category="engineering")]

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.list_templates.return_value = (templates, 1)

            response = client.get("/api/v1/templates?category=engineering")

        assert response.status_code == 200
        instance.list_templates.assert_called_once_with(
            category="engineering", limit=50, offset=0
        )

    def test_supports_pagination(self, client):
        """
        GIVEN templates exist
        WHEN GET /api/v1/templates?limit=10&offset=5 is called
        THEN it should pass pagination parameters to the service
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.list_templates.return_value = ([], 0)

            response = client.get("/api/v1/templates?limit=10&offset=5")

        assert response.status_code == 200
        instance.list_templates.assert_called_once_with(
            category=None, limit=10, offset=5
        )


class TestGetTemplate:
    """Tests for GET /templates/{template_id}"""

    def test_returns_200_with_template(self, client):
        """
        GIVEN a template exists
        WHEN GET /api/v1/templates/{id} is called
        THEN it should return 200 with the template
        """
        template = _make_mock_template(name="My Template")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.get_template.return_value = template

            response = client.get(f"/api/v1/templates/{template.id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "My Template"

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN no template with the given ID exists
        WHEN GET /api/v1/templates/{id} is called
        THEN it should return 404
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.get_template.return_value = None

            response = client.get("/api/v1/templates/nonexistent-id")

        assert response.status_code == 404


class TestCreateTemplate:
    """Tests for POST /templates"""

    def test_returns_201_on_create(self, client):
        """
        GIVEN valid template data
        WHEN POST /api/v1/templates is called
        THEN it should return 201 with the created template
        """
        template = _make_mock_template(name="New Template")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.create_template.return_value = template

            response = client.post(
                "/api/v1/templates",
                json={
                    "name": "New Template",
                    "category": "engineering",
                    "icons": ["github"],
                },
            )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "New Template"

    def test_returns_422_on_missing_fields(self, client):
        """
        GIVEN incomplete template data (missing required fields)
        WHEN POST /api/v1/templates is called
        THEN it should return 422 validation error
        """
        response = client.post("/api/v1/templates", json={})
        assert response.status_code == 422


class TestUpdateTemplate:
    """Tests for PATCH /templates/{template_id}"""

    def test_returns_200_on_update(self, client):
        """
        GIVEN a template exists
        WHEN PATCH /api/v1/templates/{id} is called with updates
        THEN it should return 200 with the updated template
        """
        template = _make_mock_template(name="Updated Template")

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.update_template.return_value = template

            response = client.patch(
                f"/api/v1/templates/{template.id}",
                json={"name": "Updated Template"},
            )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "Updated Template"

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN no template with the given ID exists
        WHEN PATCH /api/v1/templates/{id} is called
        THEN it should return 404
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.update_template.return_value = None

            response = client.patch(
                "/api/v1/templates/nonexistent-id",
                json={"name": "Updated"},
            )

        assert response.status_code == 404


class TestDeleteTemplate:
    """Tests for DELETE /templates/{template_id}"""

    def test_returns_204_on_delete(self, client):
        """
        GIVEN a template exists
        WHEN DELETE /api/v1/templates/{id} is called
        THEN it should return 204 with no content
        """
        template = _make_mock_template()

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.delete_template.return_value = template

            response = client.delete(f"/api/v1/templates/{template.id}")

        assert response.status_code == 204

    def test_returns_404_when_not_found(self, client):
        """
        GIVEN no template with the given ID exists
        WHEN DELETE /api/v1/templates/{id} is called
        THEN it should return 404
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.delete_template.return_value = None

            response = client.delete("/api/v1/templates/nonexistent-id")

        assert response.status_code == 404


class TestSeedTemplates:
    """Tests for POST /templates/seed"""

    def test_returns_200_with_seeded_templates(self, client):
        """
        GIVEN no templates have been seeded yet
        WHEN POST /api/v1/templates/seed is called
        THEN it should return 200 with the seeded templates
        """
        seeded = [
            _make_mock_template(name="Linear Ticket Solver"),
            _make_mock_template(name="PR Review Bot"),
        ]

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.seed_templates.return_value = seeded

            response = client.post("/api/v1/templates/seed")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["templates"]) == 2

    def test_idempotent_reseed_returns_empty(self, client):
        """
        GIVEN all templates have already been seeded
        WHEN POST /api/v1/templates/seed is called again
        THEN it should return 200 with empty list (no duplicates)
        """
        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.seed_templates.return_value = []

            response = client.post("/api/v1/templates/seed")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert len(data["templates"]) == 0


class TestTemplateResponseSchema:
    """Tests for template response shape"""

    def test_response_contains_all_fields(self, client):
        """
        GIVEN a template exists
        WHEN the template is fetched
        THEN the response should contain all expected fields
        """
        template = _make_mock_template(
            name="Full Template",
            description="Full description",
            category="engineering",
            icons=["github", "linear"],
            default_model="anthropic/claude-opus-4-5",
            default_persona="You are a test agent",
            default_heartbeat_interval="5m",
            default_checklist=["Check item"],
        )

        with patch(SERVICE_PATH) as MockService:
            instance = MockService.return_value
            instance.get_template.return_value = template

            response = client.get(f"/api/v1/templates/{template.id}")

        assert response.status_code == 200
        data = response.json()

        expected_keys = {
            "id", "name", "description", "category", "icons",
            "default_model", "default_persona", "default_heartbeat_interval",
            "default_checklist", "user_id", "created_at", "updated_at",
        }
        assert set(data.keys()) == expected_keys
        assert data["name"] == "Full Template"
        assert data["category"] == "engineering"
        assert data["icons"] == ["github", "linear"]
        assert data["default_model"] == "anthropic/claude-opus-4-5"
        assert data["default_checklist"] == ["Check item"]


class TestServiceUnavailable:
    """Tests for 503 when service is not available"""

    def test_returns_503_when_unavailable(self, client):
        """
        GIVEN the template service module failed to import
        WHEN any template endpoint is called
        THEN it should return 503
        """
        with patch(
            "backend.api.v1.endpoints.agent_template.AGENT_TEMPLATE_AVAILABLE",
            False,
        ):
            response = client.get("/api/v1/templates")

        assert response.status_code == 503
