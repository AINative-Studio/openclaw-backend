"""
Pytest configuration and shared fixtures
"""

import pytest
import sys
from pathlib import Path

# Add backend to Python path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))


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
