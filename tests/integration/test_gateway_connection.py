"""
Integration tests for OpenClaw Gateway connection and port configuration.

TDD RED phase tests for Issue #97: Gateway not running on port 18789.

These tests verify:
1. Gateway starts on the correct port (18789)
2. Health endpoint is accessible on port 18789
3. Backend can connect to gateway on port 18789
4. Configuration consistency between .env and dbos-config.yaml
5. Gateway startup logs confirm correct port
"""

import pytest
import httpx
import asyncio
import subprocess
import time
import os
import yaml
from pathlib import Path


# Test configuration
EXPECTED_PORT = 18789
GATEWAY_DIR = Path(__file__).parent.parent.parent / "openclaw-gateway"
GATEWAY_ENV_FILE = GATEWAY_DIR / ".env"
GATEWAY_CONFIG_FILE = GATEWAY_DIR / "dbos-config.yaml"
GATEWAY_SCRIPT = GATEWAY_DIR / "dist" / "server.js"


class TestGatewayPortConfiguration:
    """Test suite for gateway port configuration (TDD RED phase)."""

    def test_env_file_has_correct_port(self):
        """
        Test 1: Verify .env file contains PORT=18789.

        EXPECTED TO PASS: .env already has PORT=18789
        """
        assert GATEWAY_ENV_FILE.exists(), f".env file not found at {GATEWAY_ENV_FILE}"

        env_content = GATEWAY_ENV_FILE.read_text()

        # Check PORT variable exists
        assert "PORT=" in env_content, ".env file missing PORT variable"

        # Extract PORT value
        for line in env_content.split('\n'):
            if line.strip().startswith('PORT='):
                port_value = line.strip().split('=', 1)[1]
                assert port_value == str(EXPECTED_PORT), \
                    f"Expected PORT={EXPECTED_PORT} in .env, got PORT={port_value}"
                return

        pytest.fail("PORT variable not found in .env file")

    def test_dbos_config_has_correct_port(self):
        """
        Test 2: Verify dbos-config.yaml has port: 18789.

        EXPECTED TO FAIL: dbos-config.yaml currently has port: 18790
        This is the bug we're fixing.
        """
        assert GATEWAY_CONFIG_FILE.exists(), \
            f"dbos-config.yaml not found at {GATEWAY_CONFIG_FILE}"

        with open(GATEWAY_CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)

        assert 'runtimeConfig' in config, "dbos-config.yaml missing runtimeConfig"
        assert 'port' in config['runtimeConfig'], \
            "dbos-config.yaml missing runtimeConfig.port"

        actual_port = config['runtimeConfig']['port']
        assert actual_port == EXPECTED_PORT, \
            f"Expected port: {EXPECTED_PORT} in dbos-config.yaml, got port: {actual_port}"

    def test_server_js_reads_port_from_env(self):
        """
        Test 3: Verify server.js reads PORT from environment variables.

        EXPECTED TO PASS: server.js already reads process.env.PORT
        """
        assert GATEWAY_SCRIPT.exists(), f"server.js not found at {GATEWAY_SCRIPT}"

        server_content = GATEWAY_SCRIPT.read_text()

        # Check that server.js reads from process.env.PORT
        assert "process.env.PORT" in server_content, \
            "server.js does not read PORT from environment"

        # Check that it parses the PORT as integer
        assert "parseInt(process.env.PORT" in server_content, \
            "server.js does not parse PORT as integer"

    def test_configuration_consistency(self):
        """
        Test 4: Verify PORT configuration is consistent across files.

        EXPECTED TO FAIL: .env has 18789 but dbos-config.yaml has 18790
        """
        # Read .env PORT
        env_port = None
        env_content = GATEWAY_ENV_FILE.read_text()
        for line in env_content.split('\n'):
            if line.strip().startswith('PORT='):
                env_port = int(line.strip().split('=', 1)[1])
                break

        # Read dbos-config.yaml port
        with open(GATEWAY_CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)
        dbos_port = config['runtimeConfig']['port']

        # Verify consistency
        assert env_port is not None, "PORT not found in .env"
        assert env_port == dbos_port, \
            f"Port mismatch: .env has PORT={env_port}, dbos-config.yaml has port={dbos_port}"


@pytest.mark.integration
@pytest.mark.asyncio
class TestGatewayConnection:
    """Integration tests for gateway HTTP connectivity (requires gateway running)."""

    @pytest.fixture(scope="class")
    async def gateway_process(self):
        """
        Start gateway process for integration tests.

        This fixture starts the gateway in a subprocess and ensures it's ready.
        """
        # Set environment variables
        env = os.environ.copy()
        env['PORT'] = str(EXPECTED_PORT)

        # Start gateway process
        process = subprocess.Popen(
            ['node', str(GATEWAY_SCRIPT)],
            cwd=str(GATEWAY_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        # Wait for gateway to start (max 30 seconds)
        max_wait = 30
        start_time = time.time()
        gateway_ready = False

        while time.time() - start_time < max_wait:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"http://localhost:{EXPECTED_PORT}/health",
                        timeout=2.0
                    )
                    if response.status_code == 200:
                        gateway_ready = True
                        break
            except (httpx.ConnectError, httpx.TimeoutException):
                await asyncio.sleep(1)

        if not gateway_ready:
            process.terminate()
            stdout, stderr = process.communicate(timeout=5)
            pytest.fail(
                f"Gateway failed to start on port {EXPECTED_PORT} within {max_wait}s.\n"
                f"stdout: {stdout}\n"
                f"stderr: {stderr}"
            )

        yield process

        # Cleanup: terminate gateway
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()

    async def test_health_endpoint_on_correct_port(self, gateway_process):
        """
        Test 5: Verify /health endpoint responds on port 18789.

        EXPECTED TO FAIL: Gateway will likely start on port 18790 (dbos-config.yaml value)
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://localhost:{EXPECTED_PORT}/health",
                timeout=5.0
            )

            assert response.status_code == 200, \
                f"Health endpoint returned {response.status_code}, expected 200"

            data = response.json()
            assert data['status'] == 'healthy', \
                f"Gateway health status is {data['status']}, expected 'healthy'"
            assert data['service'] == 'openclaw-gateway', \
                f"Service name is {data['service']}, expected 'openclaw-gateway'"

    async def test_root_endpoint_shows_correct_port(self, gateway_process):
        """
        Test 6: Verify root endpoint (/) reports correct WebSocket port.

        EXPECTED TO FAIL: Will likely show port 18790 in WebSocket URL
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://localhost:{EXPECTED_PORT}/",
                timeout=5.0
            )

            assert response.status_code == 200, \
                f"Root endpoint returned {response.status_code}, expected 200"

            data = response.json()
            assert 'endpoints' in data, "Root response missing 'endpoints' field"
            assert 'websocket' in data['endpoints'], \
                "Root response missing 'endpoints.websocket' field"

            ws_url = data['endpoints']['websocket']
            expected_ws_url = f"ws://localhost:{EXPECTED_PORT}"
            assert ws_url == expected_ws_url, \
                f"WebSocket URL is {ws_url}, expected {expected_ws_url}"

    async def test_wrong_port_connection_fails(self, gateway_process):
        """
        Test 7: Verify connection to wrong port (18790) fails.

        EXPECTED TO FAIL IF BUG NOT FIXED: If gateway runs on 18790, this test fails.
        EXPECTED TO PASS AFTER FIX: Connection to 18790 should fail.
        """
        wrong_port = 18790

        with pytest.raises(httpx.ConnectError):
            async with httpx.AsyncClient() as client:
                await client.get(
                    f"http://localhost:{wrong_port}/health",
                    timeout=2.0
                )


@pytest.mark.integration
def test_gateway_startup_logs_correct_port():
    """
    Test 8: Verify gateway startup logs show port 18789.

    EXPECTED TO FAIL: Logs will likely show port 18790
    """
    # Set environment variables
    env = os.environ.copy()
    env['PORT'] = str(EXPECTED_PORT)

    # Start gateway and capture logs
    process = subprocess.Popen(
        ['node', str(GATEWAY_SCRIPT)],
        cwd=str(GATEWAY_DIR),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    # Read first few lines of output (max 10 seconds)
    startup_logs = []
    start_time = time.time()

    while time.time() - start_time < 10:
        line = process.stdout.readline()
        if not line:
            break
        startup_logs.append(line.strip())

        # Stop when we see the "ready" message
        if "OpenClaw Gateway is ready" in line or "listening on port" in line:
            break

    # Terminate process
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()

    # Verify logs contain correct port
    logs_text = '\n'.join(startup_logs)
    assert f"port {EXPECTED_PORT}" in logs_text or f":{EXPECTED_PORT}" in logs_text, \
        f"Startup logs do not show port {EXPECTED_PORT}:\n{logs_text}"


# Configuration validation helper (for REFACTOR phase)
def validate_gateway_port_configuration():
    """
    Helper function to validate gateway port configuration.

    Returns:
        tuple: (is_valid, error_message)
    """
    errors = []

    # Check .env file
    if not GATEWAY_ENV_FILE.exists():
        errors.append(f".env file not found at {GATEWAY_ENV_FILE}")
    else:
        env_content = GATEWAY_ENV_FILE.read_text()
        port_found = False
        for line in env_content.split('\n'):
            if line.strip().startswith('PORT='):
                port_value = line.strip().split('=', 1)[1]
                if port_value != str(EXPECTED_PORT):
                    errors.append(
                        f".env has PORT={port_value}, expected PORT={EXPECTED_PORT}"
                    )
                port_found = True
                break
        if not port_found:
            errors.append(".env file missing PORT variable")

    # Check dbos-config.yaml
    if not GATEWAY_CONFIG_FILE.exists():
        errors.append(f"dbos-config.yaml not found at {GATEWAY_CONFIG_FILE}")
    else:
        with open(GATEWAY_CONFIG_FILE, 'r') as f:
            config = yaml.safe_load(f)

        if 'runtimeConfig' not in config:
            errors.append("dbos-config.yaml missing runtimeConfig")
        elif 'port' not in config['runtimeConfig']:
            errors.append("dbos-config.yaml missing runtimeConfig.port")
        elif config['runtimeConfig']['port'] != EXPECTED_PORT:
            errors.append(
                f"dbos-config.yaml has port: {config['runtimeConfig']['port']}, "
                f"expected port: {EXPECTED_PORT}"
            )

    # Check server.js
    if not GATEWAY_SCRIPT.exists():
        errors.append(f"server.js not found at {GATEWAY_SCRIPT}")
    else:
        server_content = GATEWAY_SCRIPT.read_text()
        if "process.env.PORT" not in server_content:
            errors.append("server.js does not read PORT from environment")

    if errors:
        return False, "\n".join(errors)
    return True, "All port configuration checks passed"


if __name__ == "__main__":
    # Quick validation for debugging
    is_valid, message = validate_gateway_port_configuration()
    if is_valid:
        print(f"✓ {message}")
    else:
        print(f"✗ Configuration errors found:\n{message}")
