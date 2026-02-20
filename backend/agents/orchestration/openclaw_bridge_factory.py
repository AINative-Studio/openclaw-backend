"""
Bridge Factory for Environment-Specific Instances

Creates appropriate OpenClaw bridge implementation based on environment
(production, staging, testing, development).

Refs #1094
"""

import os
import logging
from typing import Optional

from app.agents.orchestration.openclaw_bridge_protocol import IOpenClawBridge
from app.agents.orchestration.production_openclaw_bridge import ProductionOpenClawBridge
from app.agents.orchestration.mock_openclaw_bridge import MockOpenClawBridge

logger = logging.getLogger(__name__)

# Global singleton instance for production use
_bridge_instance: Optional[IOpenClawBridge] = None


def get_openclaw_bridge() -> IOpenClawBridge:
    """
    Get singleton OpenClaw bridge instance.

    Returns the global bridge instance, creating it if necessary.
    Uses environment configuration for bridge creation.

    Returns:
        IOpenClawBridge singleton instance
    """
    global _bridge_instance

    if _bridge_instance is None:
        logger.info("Creating new OpenClaw bridge singleton instance")
        _bridge_instance = OpenClawBridgeFactory.create_bridge()

    return _bridge_instance


def reset_openclaw_bridge():
    """
    Reset the singleton bridge instance.

    Primarily used for testing to ensure clean state between tests.
    """
    global _bridge_instance
    _bridge_instance = None
    logger.info("OpenClaw bridge singleton instance reset")


class OpenClawBridgeFactory:
    """Factory for creating environment-appropriate bridge instances"""

    @staticmethod
    def create_bridge(
        environment: Optional[str] = None,
        url: Optional[str] = None,
        token: Optional[str] = None,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0
    ) -> IOpenClawBridge:
        """
        Create bridge instance based on environment

        Args:
            environment: Environment name (production, staging, testing, development)
                        If None, uses ENVIRONMENT env var, defaults to 'development'
            url: Gateway URL (defaults to OPENCLAW_GATEWAY_URL env var)
            token: Auth token (defaults to OPENCLAW_GATEWAY_TOKEN env var)
            max_retries: Maximum retry attempts for connection/send
            initial_delay: Initial delay between retries in seconds
            max_delay: Maximum delay between retries in seconds

        Returns:
            IOpenClawBridge instance configured for the environment

        Raises:
            ValueError: If production/staging environment but token not provided
        """
        env = environment or os.getenv("ENVIRONMENT", "development")

        logger.info(
            f"Creating OpenClaw bridge for environment: {env}",
            extra={"environment": env}
        )

        # Use mock bridge for testing
        if env in ("testing", "test"):
            logger.info("Using MockOpenClawBridge for testing environment")
            return MockOpenClawBridge()

        # Production/staging/development use real bridge
        gateway_url = url or os.getenv(
            "OPENCLAW_GATEWAY_URL",
            "ws://127.0.0.1:18789"
        )
        gateway_token = token or os.getenv("OPENCLAW_GATEWAY_TOKEN")

        if not gateway_token:
            # Always fail if token is missing (except in explicit testing mode)
            # This prevents silent failures and false negatives
            raise ValueError(
                f"OPENCLAW_GATEWAY_TOKEN required for '{env}' environment. "
                f"Add to .env or set ENVIRONMENT=testing for unit tests."
            )

        logger.info(
            "Creating ProductionOpenClawBridge",
            extra={
                "url": gateway_url,
                "max_retries": max_retries,
                "has_token": bool(gateway_token)
            }
        )

        return ProductionOpenClawBridge(
            url=gateway_url,
            token=gateway_token,
            max_retries=max_retries,
            initial_delay=initial_delay,
            max_delay=max_delay
        )

    @staticmethod
    def create_mock_bridge(
        simulate_failures: bool = False,
        failure_rate: float = 0.0
    ) -> MockOpenClawBridge:
        """
        Create mock bridge for testing

        Args:
            simulate_failures: If True, operations may fail randomly
            failure_rate: Probability of failure (0.0 to 1.0)

        Returns:
            MockOpenClawBridge instance
        """
        logger.info(
            "Creating MockOpenClawBridge",
            extra={
                "simulate_failures": simulate_failures,
                "failure_rate": failure_rate
            }
        )

        return MockOpenClawBridge(
            simulate_failures=simulate_failures,
            failure_rate=failure_rate
        )
