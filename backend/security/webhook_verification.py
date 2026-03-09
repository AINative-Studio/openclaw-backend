"""
Webhook Authentication & Verification

Provides HMAC-based webhook signature verification for secure webhook endpoints.
Implements industry-standard webhook security patterns with timestamp validation
and replay attack prevention.
"""

import hmac
import hashlib
import time
from typing import Optional
from fastapi import HTTPException, status


class WebhookVerifier:
    """
    Webhook signature verifier using HMAC-SHA256

    Validates webhook signatures to ensure requests originate from trusted sources.
    Implements timestamp-based replay attack prevention.
    """

    def __init__(self, secret_key: str, tolerance_seconds: int = 300):
        """
        Initialize webhook verifier

        Args:
            secret_key: Shared secret key for HMAC signature generation
            tolerance_seconds: Maximum age of webhook timestamp (default 5 minutes)
        """
        self.secret_key = secret_key.encode('utf-8')
        self.tolerance_seconds = tolerance_seconds

    def generate_signature(self, payload: bytes, timestamp: str) -> str:
        """
        Generate HMAC-SHA256 signature for webhook payload

        Args:
            payload: Raw webhook payload bytes
            timestamp: Unix timestamp as string

        Returns:
            Hex-encoded HMAC signature
        """
        message = f"{timestamp}.{payload.decode('utf-8')}"
        signature = hmac.new(
            self.secret_key,
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def verify_signature(
        self,
        payload: bytes,
        signature: str,
        timestamp: str
    ) -> bool:
        """
        Verify webhook signature and timestamp

        Args:
            payload: Raw webhook payload bytes
            signature: Provided signature to verify
            timestamp: Unix timestamp as string

        Returns:
            True if signature is valid and timestamp is within tolerance

        Raises:
            HTTPException: If verification fails
        """
        # Validate timestamp is within tolerance
        try:
            webhook_time = int(timestamp)
            current_time = int(time.time())

            if abs(current_time - webhook_time) > self.tolerance_seconds:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Webhook timestamp outside tolerance window (replay attack prevention)"
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid timestamp format"
            )

        # Generate expected signature
        expected_signature = self.generate_signature(payload, timestamp)

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(signature, expected_signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature"
            )

        return True

    def extract_signature_header(self, signature_header: Optional[str]) -> tuple[str, str]:
        """
        Extract timestamp and signature from webhook signature header

        Expected format: "t=<timestamp>,v1=<signature>"

        Args:
            signature_header: Signature header value

        Returns:
            Tuple of (timestamp, signature)

        Raises:
            HTTPException: If header format is invalid
        """
        if not signature_header:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing webhook signature header"
            )

        parts = dict(part.split('=', 1) for part in signature_header.split(','))

        timestamp = parts.get('t')
        signature = parts.get('v1')

        if not timestamp or not signature:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid signature header format"
            )

        return timestamp, signature
