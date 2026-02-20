"""
Token Service (E7-S1)

JWT encoding/decoding service for capability tokens.
Supports both HS256 (symmetric) and RS256 (asymmetric) algorithms.

Refs: OpenCLAW P2P Swarm PRD Section on Security, Backlog E7-S1
"""

import jwt
from typing import Optional
from datetime import datetime

from backend.models.capability_token import CapabilityToken, TokenLimits


class TokenExpiredError(Exception):
    """Raised when token has expired"""
    pass


class InvalidTokenError(Exception):
    """Raised when token signature or format is invalid"""
    pass


class TokenService:
    """
    JWT token encoding and decoding service

    Handles capability token signing, verification, and validation.
    Supports both symmetric (HS256) and asymmetric (RS256) algorithms.

    Attributes:
        secret_key: Secret key or private key for signing
        algorithm: JWT algorithm (HS256 or RS256)
        public_key: Public key for RS256 verification (optional)
    """

    def __init__(
        self,
        secret_key: str,
        algorithm: str = "HS256",
        public_key: Optional[str] = None
    ):
        """
        Initialize token service

        Args:
            secret_key: Secret key (HS256) or private key PEM (RS256)
            algorithm: JWT algorithm (default: HS256)
            public_key: Public key PEM for RS256 verification (optional)
        """
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.public_key = public_key

        # Validate algorithm
        if algorithm not in ["HS256", "RS256"]:
            raise ValueError(f"Unsupported algorithm: {algorithm}")

        # For RS256, public_key is required for verification
        if algorithm == "RS256" and not public_key:
            raise ValueError("public_key is required for RS256 algorithm")

    def encode_token(self, token_model: CapabilityToken) -> str:
        """
        Encode capability token to JWT

        Args:
            token_model: CapabilityToken instance to encode

        Returns:
            Signed JWT string
        """
        # Convert Pydantic model to dict
        payload = {
            "jti": token_model.jti,
            "peer_id": token_model.peer_id,
            "capabilities": token_model.capabilities,
            "limits": {
                "max_gpu_minutes": token_model.limits.max_gpu_minutes,
                "max_concurrent_tasks": token_model.limits.max_concurrent_tasks,
            },
            "data_scope": token_model.data_scope,
            "exp": token_model.expires_at,
        }

        # Add parent_jti if present
        if token_model.parent_jti:
            payload["parent_jti"] = token_model.parent_jti

        # Encode JWT
        encoded = jwt.encode(
            payload,
            self.secret_key,
            algorithm=self.algorithm
        )

        return encoded

    def decode_token(self, encoded_token: str) -> CapabilityToken:
        """
        Decode and verify JWT token

        Args:
            encoded_token: JWT string to decode

        Returns:
            CapabilityToken instance

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token signature or format is invalid
        """
        try:
            # For RS256, use public key for verification
            verify_key = self.public_key if self.algorithm == "RS256" else self.secret_key

            # Decode and verify JWT
            payload = jwt.decode(
                encoded_token,
                verify_key,
                algorithms=[self.algorithm]
            )

            # Convert payload to CapabilityToken
            token_model = CapabilityToken(
                jti=payload.get("jti"),
                peer_id=payload["peer_id"],
                capabilities=payload["capabilities"],
                limits=TokenLimits(
                    max_gpu_minutes=payload["limits"]["max_gpu_minutes"],
                    max_concurrent_tasks=payload["limits"]["max_concurrent_tasks"],
                ),
                data_scope=payload.get("data_scope", []),
                expires_at=payload["exp"],
                parent_jti=payload.get("parent_jti"),
            )

            return token_model

        except jwt.ExpiredSignatureError as e:
            raise TokenExpiredError(f"Token has expired: {str(e)}")
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token: {str(e)}")
        except ValueError as e:
            # Check if it's an expiration validation error
            if "expires_at must be in the future" in str(e):
                raise TokenExpiredError(f"Token has expired: {str(e)}")
            raise InvalidTokenError(f"Invalid token format: {str(e)}")
        except (KeyError, TypeError) as e:
            raise InvalidTokenError(f"Invalid token format: {str(e)}")

    def check_capability(self, encoded_token: str, capability: str) -> bool:
        """
        Check if token has a specific capability

        Args:
            encoded_token: JWT string
            capability: Capability to check (e.g., "can_execute:llama-2-7b")

        Returns:
            True if token has capability, False otherwise

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token is invalid
        """
        try:
            token_model = self.decode_token(encoded_token)
            return token_model.has_capability(capability)
        except TokenExpiredError:
            raise
        except InvalidTokenError:
            raise

    def check_data_access(self, encoded_token: str, project_id: str) -> bool:
        """
        Check if token has access to a specific project

        Args:
            encoded_token: JWT string
            project_id: Project ID to check access for

        Returns:
            True if token has access, False otherwise

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token is invalid
        """
        try:
            token_model = self.decode_token(encoded_token)
            return token_model.has_data_access(project_id)
        except TokenExpiredError:
            raise
        except InvalidTokenError:
            raise

    def get_token_claims(self, encoded_token: str) -> dict:
        """
        Get token payload without full verification

        Useful for inspecting token contents without strict validation.
        WARNING: Does not verify signature - use only for non-security-critical inspection.

        Args:
            encoded_token: JWT string

        Returns:
            Token payload as dictionary
        """
        try:
            # Decode without verification (for inspection only)
            payload = jwt.decode(
                encoded_token,
                options={"verify_signature": False}
            )
            return payload
        except jwt.InvalidTokenError as e:
            raise InvalidTokenError(f"Invalid token format: {str(e)}")
