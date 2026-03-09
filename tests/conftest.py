"""
Pytest configuration and shared fixtures
"""

import pytest
import sys
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add backend to Python path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))

# Import Base after adding to path
from backend.db.base import Base  # noqa: E402


# Database fixtures
@pytest.fixture(scope="function")
def db_session():
    """
    Create a fresh database session for each test.

    Uses Railway PostgreSQL from .env DATABASE_URL.
    For Issue #116 schema consolidation tests.
    """
    # Load from .env file
    from dotenv import load_dotenv
    load_dotenv()

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError("DATABASE_URL not found in environment. Check .env file.")

    # Convert async driver to sync for test fixtures
    # postgresql+asyncpg:// -> postgresql+psycopg2://
    database_url = database_url.replace("+asyncpg://", "+psycopg2://")

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    # Create all tables (idempotent - won't recreate existing tables)
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        yield db
        # Rollback any test changes to keep database clean
        db.rollback()
    finally:
        db.close()


@pytest.fixture(scope="session")
def test_network():
    """Test IP network for WireGuard"""
    return "10.0.0.0/24"


@pytest.fixture(scope="session")
def test_hub_ip():
    """Test hub IP address"""
    return "10.0.0.1"


@pytest.fixture(scope="function")
def temp_config_file(tmp_path):
    """Create temporary WireGuard config file"""
    config_file = tmp_path / "wg0.conf"
    return str(config_file)
