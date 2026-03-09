"""
Tests for API documentation security configuration.

Verifies that API documentation endpoints (/docs, /redoc, /openapi.json)
are disabled in production environments and enabled in development environments.
"""

import os
import pytest
from fastapi.testclient import TestClient


def test_docs_disabled_in_production(monkeypatch):
    """Test that /docs returns 404 in production environment"""
    # Set production environment
    monkeypatch.setenv("ENVIRONMENT", "production")
    # Set required ALLOWED_ORIGINS and ALLOWED_HOSTS for production
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")
    monkeypatch.setenv("ALLOWED_HOSTS", "api.example.com,app.example.com")

    # Clear any cached modules to force reimport with new environment
    import sys
    if "backend.main" in sys.modules:
        del sys.modules["backend.main"]

    # Import after environment is set
    from backend.main import app
    client = TestClient(app, base_url="http://api.example.com")

    # Test that /docs returns 404
    response = client.get("/docs")
    assert response.status_code == 404

    # Test that /redoc returns 404
    response = client.get("/redoc")
    assert response.status_code == 404

    # Test that /openapi.json returns 404
    response = client.get("/openapi.json")
    assert response.status_code == 404


def test_docs_enabled_in_development(monkeypatch):
    """Test that /docs works in development environment"""
    # Set development environment
    monkeypatch.setenv("ENVIRONMENT", "development")

    # Clear any cached modules to force reimport with new environment
    import sys
    if "backend.main" in sys.modules:
        del sys.modules["backend.main"]

    # Import after environment is set
    from backend.main import app
    # Use localhost as base URL to match allowed hosts
    client = TestClient(app, base_url="http://localhost")

    # Test that /docs returns 200
    response = client.get("/docs")
    assert response.status_code == 200
    assert b"Swagger UI" in response.content or b"swagger" in response.content.lower()

    # Test that /redoc returns 200
    response = client.get("/redoc")
    assert response.status_code == 200

    # Test that /openapi.json returns 200
    response = client.get("/openapi.json")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"


def test_docs_enabled_in_staging(monkeypatch):
    """Test that /docs works in staging environment"""
    # Set staging environment
    monkeypatch.setenv("ENVIRONMENT", "staging")

    # Clear any cached modules to force reimport with new environment
    import sys
    if "backend.main" in sys.modules:
        del sys.modules["backend.main"]

    # Import after environment is set
    from backend.main import app
    client = TestClient(app, base_url="http://localhost")

    # Test that /docs returns 200
    response = client.get("/docs")
    assert response.status_code == 200


def test_docs_enabled_in_testing(monkeypatch):
    """Test that /docs works in testing environment"""
    # Set testing environment
    monkeypatch.setenv("ENVIRONMENT", "testing")

    # Clear any cached modules to force reimport with new environment
    import sys
    if "backend.main" in sys.modules:
        del sys.modules["backend.main"]

    # Import after environment is set
    from backend.main import app
    client = TestClient(app)

    # Test that /docs returns 200
    response = client.get("/docs")
    assert response.status_code == 200


def test_docs_enabled_by_default(monkeypatch):
    """Test that /docs works when ENVIRONMENT is not set (defaults to development)"""
    # Unset ENVIRONMENT variable
    monkeypatch.delenv("ENVIRONMENT", raising=False)

    # Clear any cached modules to force reimport with new environment
    import sys
    if "backend.main" in sys.modules:
        del sys.modules["backend.main"]

    # Import after environment is set
    from backend.main import app
    client = TestClient(app)

    # Test that /docs returns 200 (default is development)
    response = client.get("/docs")
    assert response.status_code == 200


def test_case_insensitive_environment_variable(monkeypatch):
    """Test that environment variable is case-insensitive"""
    # Set environment with uppercase PRODUCTION
    monkeypatch.setenv("ENVIRONMENT", "PRODUCTION")
    # Set required ALLOWED_ORIGINS for production
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://app.example.com")

    # Clear any cached modules to force reimport with new environment
    import sys
    if "backend.main" in sys.modules:
        del sys.modules["backend.main"]

    # Import after environment is set
    from backend.main import app
    client = TestClient(app)

    # Test that /docs returns 404 (case-insensitive check)
    response = client.get("/docs")
    assert response.status_code == 404
