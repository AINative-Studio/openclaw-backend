"""
Zalo API Client (Issue #121)

Client for interacting with Zalo Official Account API.

Zalo API Documentation:
- Base URL: https://openapi.zalo.me
- OAuth: https://developers.zalo.me/docs/api/official-account-api/bat-dau/xac-thuc-va-uy-quyen-post-4307
- Messaging: https://developers.zalo.me/docs/api/official-account-api/gui-tin-nhan
"""

import hmac
import hashlib
import secrets
from typing import Dict, Any, Optional
from urllib.parse import urlencode
import httpx


class ZaloAPIError(Exception):
    """Base exception for Zalo API errors"""
    def __init__(self, message: str, error_code: Optional[int] = None):
        super().__init__(message)
        self.error_code = error_code


class ZaloAuthError(ZaloAPIError):
    """Exception for OAuth/authentication errors"""
    pass


class ZaloRateLimitError(ZaloAPIError):
    """Exception for rate limit errors"""
    def __init__(self, message: str, retry_after: int = 60):
        super().__init__(message)
        self.retry_after = retry_after


class ZaloWebhookError(Exception):
    """Exception for webhook processing errors"""
    pass


class ZaloClient:
    """
    Zalo Official Account API Client.

    Handles OAuth flow, message sending, and webhook processing.
    """

    def __init__(self, oa_id: str, app_id: str, app_secret: str):
        """
        Initialize Zalo client.

        Args:
            oa_id: Zalo Official Account ID
            app_id: Zalo App ID
            app_secret: Zalo App Secret

        Raises:
            ValueError: If any required credential is empty
        """
        if not oa_id or not oa_id.strip():
            raise ValueError("oa_id is required")
        if not app_id or not app_id.strip():
            raise ValueError("app_id is required")
        if not app_secret or not app_secret.strip():
            raise ValueError("app_secret is required")

        self.oa_id = oa_id.strip()
        self.app_id = app_id.strip()
        self.app_secret = app_secret.strip()
        self.base_url = "https://openapi.zalo.me"
        self.access_token: Optional[str] = None

    def get_oauth_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Generate OAuth authorization URL.

        Args:
            redirect_uri: Callback URL after authorization
            state: State parameter for CSRF protection (auto-generated if not provided)

        Returns:
            OAuth authorization URL
        """
        if not state:
            state = secrets.token_urlsafe(32)

        params = {
            "app_id": self.app_id,
            "redirect_uri": redirect_uri,
            "state": state
        }

        return f"https://oauth.zaloapp.com/v4/oa/permission?{urlencode(params)}"

    async def exchange_code_for_token(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Token response dict with access_token, refresh_token, expires_in

        Raises:
            ZaloAuthError: If token exchange fails
        """
        endpoint = f"{self.base_url}/v2.0/oauth/access_token"
        payload = {
            "app_id": self.app_id,
            "code": code,
            "grant_type": "authorization_code"
        }

        try:
            response = await self._make_request("POST", endpoint, json=payload)
            return response
        except ZaloAPIError as e:
            raise ZaloAuthError(str(e))

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh expired access token.

        Args:
            refresh_token: Refresh token from previous authorization

        Returns:
            New token response dict

        Raises:
            ZaloAuthError: If token refresh fails
        """
        endpoint = f"{self.base_url}/v2.0/oauth/access_token"
        payload = {
            "app_id": self.app_id,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token"
        }

        try:
            response = await self._make_request("POST", endpoint, json=payload)
            return response
        except ZaloAPIError as e:
            raise ZaloAuthError(str(e))

    async def send_text_message(self, user_id: str, message: str) -> Dict[str, Any]:
        """
        Send text message to user.

        Args:
            user_id: Zalo user ID
            message: Message text

        Returns:
            API response dict

        Raises:
            ZaloAuthError: If access token is not set
            ValueError: If message is empty
            ZaloAPIError: If API request fails
        """
        if not self.access_token:
            raise ZaloAuthError("Access token not set")

        if not message or not message.strip():
            raise ValueError("Message cannot be empty")

        endpoint = f"{self.base_url}/v3.0/oa/message/cs"
        payload = {
            "recipient": {
                "user_id": user_id
            },
            "message": {
                "text": message.strip()
            }
        }

        return await self._make_request("POST", endpoint, json=payload, authenticated=True)

    async def send_image_message(self, user_id: str, image_url: str) -> Dict[str, Any]:
        """
        Send image message to user.

        Args:
            user_id: Zalo user ID
            image_url: URL of image to send

        Returns:
            API response dict

        Raises:
            ZaloAuthError: If access token is not set
            ValueError: If image URL is invalid
            ZaloAPIError: If API request fails
        """
        if not self.access_token:
            raise ZaloAuthError("Access token not set")

        # Basic URL validation
        if not image_url or not image_url.startswith(("http://", "https://")):
            raise ValueError("Invalid image URL")

        endpoint = f"{self.base_url}/v3.0/oa/message/cs"
        payload = {
            "recipient": {
                "user_id": user_id
            },
            "message": {
                "attachment": {
                    "type": "template",
                    "payload": {
                        "template_type": "media",
                        "elements": [{
                            "media_type": "image",
                            "url": image_url
                        }]
                    }
                }
            }
        }

        return await self._make_request("POST", endpoint, json=payload, authenticated=True)

    async def get_user_profile(self, user_id: str) -> Dict[str, Any]:
        """
        Get user profile information.

        Args:
            user_id: Zalo user ID

        Returns:
            User profile dict

        Raises:
            ZaloAuthError: If access token is not set
            ZaloAPIError: If API request fails
        """
        if not self.access_token:
            raise ZaloAuthError("Access token not set")

        endpoint = f"{self.base_url}/v2.0/oa/getprofile"
        params = {
            "data": {
                "user_id": user_id
            }
        }

        return await self._make_request("GET", endpoint, params=params, authenticated=True)

    def handle_webhook(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process incoming webhook payload.

        Args:
            payload: Webhook payload from Zalo

        Returns:
            Parsed webhook event dict

        Raises:
            ZaloWebhookError: If payload is invalid or missing required fields
        """
        if not payload:
            raise ZaloWebhookError("Invalid webhook payload")

        required_fields = ["event_name", "timestamp", "app_id", "user_id"]
        missing_fields = [field for field in required_fields if field not in payload]

        if missing_fields:
            raise ZaloWebhookError(f"Missing required fields: {', '.join(missing_fields)}")

        event_type = payload["event_name"]
        result = {
            "event_type": event_type,
            "user_id": payload["user_id"],
            "timestamp": payload["timestamp"]
        }

        # Extract message text if present
        if "message" in payload and "text" in payload["message"]:
            result["message_text"] = payload["message"]["text"]

        return result

    def verify_webhook_signature(self, payload: str, signature: str) -> bool:
        """
        Verify webhook signature.

        Args:
            payload: Raw webhook payload string
            signature: Signature from X-Zalo-Signature header

        Returns:
            True if signature is valid, False otherwise
        """
        computed_signature = self._compute_signature(payload)
        return hmac.compare_digest(computed_signature, signature)

    def _compute_signature(self, payload: str) -> str:
        """
        Compute HMAC-SHA256 signature for webhook verification.

        Args:
            payload: Raw payload string

        Returns:
            Hex-encoded signature
        """
        return hmac.new(
            self.app_secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()

    async def _make_request(
        self,
        method: str,
        url: str,
        authenticated: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Make HTTP request to Zalo API.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Request URL
            authenticated: Whether to include access token
            **kwargs: Additional httpx request arguments

        Returns:
            API response dict

        Raises:
            ZaloAPIError: If request fails
            ZaloRateLimitError: If rate limit exceeded
        """
        headers = kwargs.pop("headers", {})

        if authenticated and self.access_token:
            headers["access_token"] = self.access_token

        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=30.0,
                    **kwargs
                )
                response.raise_for_status()

                data = response.json()

                # Check for API errors in response
                if isinstance(data, dict):
                    error_code = data.get("error", 0)
                    if error_code != 0:
                        error_message = data.get("message", "Unknown error")

                        # Check for rate limiting
                        if error_code == -215:  # Rate limit error code
                            raise ZaloRateLimitError(error_message, retry_after=60)

                        raise ZaloAPIError(error_message, error_code=error_code)

                    return data
                else:
                    raise ZaloAPIError("Invalid response format")

        except httpx.ConnectError as e:
            raise ZaloAPIError(f"Network error: {str(e)}")
        except httpx.TimeoutException as e:
            raise ZaloAPIError(f"Request timeout: {str(e)}")
        except httpx.HTTPStatusError as e:
            # Handle HTTP errors
            if e.response.status_code == 429:
                raise ZaloRateLimitError("Rate limit exceeded", retry_after=60)
            raise ZaloAPIError(f"HTTP {e.response.status_code}: {str(e)}")
