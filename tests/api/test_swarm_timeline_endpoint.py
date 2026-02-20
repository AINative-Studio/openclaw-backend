"""
Swarm Timeline API Endpoint Tests

Tests for GET /swarm/timeline endpoint returning task execution
timeline events as JSON for the dashboard UI.

Epic E8-S3: Task Execution Timeline
Refs: #51
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import Mock, patch, MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.api.v1.endpoints.swarm_timeline import router


@pytest.fixture
def app():
    """Create FastAPI test app with swarm timeline router"""
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    return test_app


@pytest.fixture
def client(app):
    """Create test client"""
    return TestClient(app)


def _make_sample_events():
    """Build sample timeline events for testing"""
    return [
        {
            "event_type": "TASK_CREATED",
            "task_id": "task-001",
            "peer_id": "peer-abc",
            "timestamp": "2026-02-20T12:00:00+00:00",
            "metadata": {},
        },
        {
            "event_type": "TASK_LEASED",
            "task_id": "task-001",
            "peer_id": "peer-abc",
            "timestamp": "2026-02-20T12:00:10+00:00",
            "metadata": {"lease_duration": 300},
        },
        {
            "event_type": "TASK_COMPLETED",
            "task_id": "task-001",
            "peer_id": "peer-abc",
            "timestamp": "2026-02-20T12:05:00+00:00",
            "metadata": {"result_size": 1024},
        },
    ]


def _make_timeline_event_mocks(event_dicts):
    """Convert event dicts to mock TimelineEvent objects"""
    mocks = []
    for d in event_dicts:
        mock = Mock()
        mock.event_type = d["event_type"]
        mock.task_id = d.get("task_id")
        mock.peer_id = d.get("peer_id")
        mock.timestamp = datetime.fromisoformat(d["timestamp"])
        mock.metadata = d.get("metadata", {})
        mocks.append(mock)
    return mocks


class TestSwarmTimelineEndpoint:
    """Test GET /swarm/timeline endpoint responses"""

    def test_returns_200_with_events(self, client):
        """
        GIVEN a timeline service with recorded events
        WHEN requesting GET /api/v1/swarm/timeline
        THEN should return HTTP 200 with events list
        """
        event_dicts = _make_sample_events()
        event_mocks = _make_timeline_event_mocks(event_dicts)

        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = (event_mocks, 3)
            mock_get.return_value = mock_service

            response = client.get("/api/v1/swarm/timeline")

            assert response.status_code == 200
            data = response.json()
            assert len(data["events"]) == 3
            assert data["total_count"] == 3

    def test_returns_200_empty(self, client):
        """
        GIVEN an empty timeline service
        WHEN requesting GET /api/v1/swarm/timeline
        THEN should return HTTP 200 with empty events list
        """
        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = ([], 0)
            mock_get.return_value = mock_service

            response = client.get("/api/v1/swarm/timeline")

            assert response.status_code == 200
            data = response.json()
            assert data["events"] == []
            assert data["total_count"] == 0

    def test_response_json_structure(self, client):
        """
        GIVEN a timeline service with events
        WHEN requesting timeline endpoint
        THEN response should contain expected keys
        """
        event_dicts = _make_sample_events()[:1]
        event_mocks = _make_timeline_event_mocks(event_dicts)

        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = (event_mocks, 1)
            mock_get.return_value = mock_service

            response = client.get("/api/v1/swarm/timeline")

            data = response.json()
            assert "events" in data
            assert "total_count" in data
            assert "limit" in data
            assert "offset" in data

            event = data["events"][0]
            assert "event_type" in event
            assert "task_id" in event
            assert "peer_id" in event
            assert "timestamp" in event
            assert "metadata" in event

    def test_filter_by_task_id(self, client):
        """
        GIVEN a timeline service
        WHEN requesting with task_id query param
        THEN should pass task_id filter to service
        """
        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = ([], 0)
            mock_get.return_value = mock_service

            client.get("/api/v1/swarm/timeline?task_id=task-001")

            call_kwargs = mock_service.query_events.call_args[1]
            assert call_kwargs["task_id"] == "task-001"

    def test_filter_by_peer_id(self, client):
        """
        GIVEN a timeline service
        WHEN requesting with peer_id query param
        THEN should pass peer_id filter to service
        """
        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = ([], 0)
            mock_get.return_value = mock_service

            client.get("/api/v1/swarm/timeline?peer_id=peer-abc")

            call_kwargs = mock_service.query_events.call_args[1]
            assert call_kwargs["peer_id"] == "peer-abc"

    def test_filter_by_event_type(self, client):
        """
        GIVEN a timeline service
        WHEN requesting with event_type query param
        THEN should pass event_type filter to service
        """
        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = ([], 0)
            mock_get.return_value = mock_service

            client.get("/api/v1/swarm/timeline?event_type=TASK_LEASED")

            call_kwargs = mock_service.query_events.call_args[1]
            assert call_kwargs["event_type"].value == "TASK_LEASED"

    def test_filter_by_since(self, client):
        """
        GIVEN a timeline service
        WHEN requesting with since query param
        THEN should pass since filter to service
        """
        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = ([], 0)
            mock_get.return_value = mock_service

            client.get(
                "/api/v1/swarm/timeline?since=2026-02-20T10:00:00%2B00:00"
            )

            call_kwargs = mock_service.query_events.call_args[1]
            assert call_kwargs["since"] is not None

    def test_filter_by_until(self, client):
        """
        GIVEN a timeline service
        WHEN requesting with until query param
        THEN should pass until filter to service
        """
        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = ([], 0)
            mock_get.return_value = mock_service

            client.get(
                "/api/v1/swarm/timeline?until=2026-02-20T15:00:00%2B00:00"
            )

            call_kwargs = mock_service.query_events.call_args[1]
            assert call_kwargs["until"] is not None

    def test_invalid_event_type_returns_empty(self, client):
        """
        GIVEN a timeline service
        WHEN requesting with an invalid event_type
        THEN should return 200 with empty list (graceful degradation)
        """
        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = ([], 0)
            mock_get.return_value = mock_service

            response = client.get(
                "/api/v1/swarm/timeline?event_type=INVALID_TYPE"
            )

            assert response.status_code == 200
            data = response.json()
            assert data["events"] == []
            assert data["total_count"] == 0

    def test_pagination_defaults(self, client):
        """
        GIVEN a timeline service
        WHEN requesting without pagination params
        THEN should use default limit=100 and offset=0
        """
        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = ([], 0)
            mock_get.return_value = mock_service

            response = client.get("/api/v1/swarm/timeline")

            data = response.json()
            assert data["limit"] == 100
            assert data["offset"] == 0

            call_kwargs = mock_service.query_events.call_args[1]
            assert call_kwargs["limit"] == 100
            assert call_kwargs["offset"] == 0

    def test_custom_pagination(self, client):
        """
        GIVEN a timeline service
        WHEN requesting with custom limit and offset
        THEN should pass custom pagination to service
        """
        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = ([], 0)
            mock_get.return_value = mock_service

            response = client.get(
                "/api/v1/swarm/timeline?limit=50&offset=10"
            )

            data = response.json()
            assert data["limit"] == 50
            assert data["offset"] == 10

            call_kwargs = mock_service.query_events.call_args[1]
            assert call_kwargs["limit"] == 50
            assert call_kwargs["offset"] == 10


class TestSwarmTimelineEndpointErrorHandling:
    """Test error handling in the timeline endpoint"""

    def test_returns_503_when_service_unavailable(self):
        """
        GIVEN TaskTimelineService import fails
        WHEN requesting timeline endpoint
        THEN should return HTTP 503
        """
        from backend.api.v1.endpoints.swarm_timeline import get_swarm_timeline

        with patch(
            "backend.api.v1.endpoints.swarm_timeline.TIMELINE_AVAILABLE", False
        ):
            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_swarm_timeline())

            assert exc_info.value.status_code == 503

    def test_returns_500_on_unexpected_error(self):
        """
        GIVEN TaskTimelineService raises unexpected exception
        WHEN requesting timeline endpoint
        THEN should return HTTP 500
        """
        from backend.api.v1.endpoints.swarm_timeline import get_swarm_timeline

        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.side_effect = RuntimeError(
                "Unexpected crash"
            )
            mock_get.return_value = mock_service

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(get_swarm_timeline())

            assert exc_info.value.status_code == 500
            assert "Failed to query timeline" in str(exc_info.value.detail)


class TestSwarmTimelineEndpointIntegration:
    """Integration test with TestClient"""

    def test_full_round_trip(self):
        """
        GIVEN a FastAPI app with swarm timeline router
        WHEN performing full HTTP round-trip with seeded events
        THEN should return valid JSON response with correct data
        """
        test_app = FastAPI()
        test_app.include_router(router, prefix="/api/v1")
        test_client = TestClient(test_app)

        event_dicts = _make_sample_events()
        event_mocks = _make_timeline_event_mocks(event_dicts)

        with patch(
            "backend.api.v1.endpoints.swarm_timeline.get_timeline_service"
        ) as mock_get:
            mock_service = Mock()
            mock_service.query_events.return_value = (event_mocks, 3)
            mock_get.return_value = mock_service

            response = test_client.get("/api/v1/swarm/timeline")

            assert response.status_code == 200
            assert response.headers["content-type"] == "application/json"
            data = response.json()
            assert len(data["events"]) == 3
            assert data["total_count"] == 3
            assert data["events"][0]["event_type"] == "TASK_CREATED"
            assert data["events"][0]["task_id"] == "task-001"
            assert data["events"][1]["metadata"]["lease_duration"] == 300
