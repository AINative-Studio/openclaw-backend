"""
API Key Service - Encryption and Business Logic (Issue #83)

Handles encryption/decryption of API keys using Fernet symmetric encryption.
Provides CRUD operations and key verification against external APIs.
"""

import os
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from backend.models.api_key import APIKey
from backend.schemas.api_key import SupportedService


class APIKeyService:
    """
    Service for managing encrypted API keys.

    Encryption:
        - Uses Fernet (symmetric encryption based on AES-128-CBC + HMAC-SHA256)
        - Encryption key from environment variable API_KEY_ENCRYPTION_KEY
        - Each encryption includes random IV for security
    """

    def __init__(self, db: Session, encryption_key: Optional[str] = None):
        """
        Initialize API key service.

        Args:
            db: SQLAlchemy database session
            encryption_key: Optional encryption key (defaults to env var)

        Raises:
            ValueError: If encryption key is not configured
        """
        self.db = db

        # Get encryption key from parameter or environment
        key = encryption_key or os.getenv("API_KEY_ENCRYPTION_KEY")
        if not key:
            raise ValueError(
                "API_KEY_ENCRYPTION_KEY environment variable not set. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        # Initialize Fernet cipher
        try:
            self.cipher = Fernet(key.encode() if isinstance(key, str) else key)
        except Exception as e:
            raise ValueError(f"Invalid encryption key format: {e}")

    def encrypt_key(self, plaintext_key: str) -> bytes:
        """
        Encrypt an API key.

        Args:
            plaintext_key: Plaintext API key to encrypt

        Returns:
            Encrypted key as bytes (Fernet ciphertext)
        """
        return self.cipher.encrypt(plaintext_key.encode())

    def decrypt_key(self, encrypted_key: bytes) -> str:
        """
        Decrypt an API key.

        Args:
            encrypted_key: Fernet-encrypted key bytes

        Returns:
            Decrypted plaintext API key

        Raises:
            InvalidToken: If decryption fails (wrong key or corrupted data)
        """
        try:
            return self.cipher.decrypt(encrypted_key).decode()
        except InvalidToken:
            raise ValueError("Failed to decrypt API key - invalid encryption key or corrupted data")

    def mask_key(self, plaintext_key: str) -> str:
        """
        Mask an API key for safe display.

        Shows only the last 4 characters (e.g., "sk-...1234").

        Args:
            plaintext_key: Plaintext API key

        Returns:
            Masked key string
        """
        if not plaintext_key or len(plaintext_key) < 4:
            return "***"

        # Extract prefix and last 4 chars
        prefix = plaintext_key.split("-")[0] if "-" in plaintext_key else ""
        last_four = plaintext_key[-4:]

        return f"{prefix}-...{last_four}" if prefix else f"...{last_four}"

    def create_api_key(self, service_name: str, plaintext_key: str) -> APIKey:
        """
        Create and store an encrypted API key.

        Args:
            service_name: Service identifier (anthropic, openai, etc.)
            plaintext_key: Plaintext API key to encrypt and store

        Returns:
            Created APIKey model instance

        Raises:
            ValueError: If service_name already exists
        """
        # Check for duplicates
        existing = self.db.query(APIKey).filter_by(service_name=service_name).first()
        if existing:
            raise ValueError(f"API key for service '{service_name}' already exists")

        # Encrypt key
        encrypted_key = self.encrypt_key(plaintext_key)

        # Create database record
        api_key = APIKey(
            service_name=service_name,
            encrypted_key=encrypted_key,
            is_active=True
        )

        self.db.add(api_key)
        self.db.commit()
        self.db.refresh(api_key)

        return api_key

    def get_api_key(self, service_name: str) -> Optional[APIKey]:
        """
        Retrieve an API key record by service name.

        Args:
            service_name: Service identifier

        Returns:
            APIKey instance or None if not found
        """
        return self.db.query(APIKey).filter_by(service_name=service_name).first()

    def get_decrypted_key(self, service_name: str) -> str:
        """
        Retrieve and decrypt an API key.

        Args:
            service_name: Service identifier

        Returns:
            Decrypted plaintext API key

        Raises:
            ValueError: If key not found
        """
        api_key = self.get_api_key(service_name)
        if not api_key:
            raise ValueError(f"API key for service '{service_name}' not found")

        return self.decrypt_key(api_key.encrypted_key)

    def update_api_key(self, service_name: str, new_plaintext_key: str) -> APIKey:
        """
        Update an existing API key.

        Args:
            service_name: Service identifier
            new_plaintext_key: New plaintext API key

        Returns:
            Updated APIKey instance

        Raises:
            ValueError: If key not found
        """
        api_key = self.get_api_key(service_name)
        if not api_key:
            raise ValueError(f"API key for service '{service_name}' not found")

        # Encrypt new key
        encrypted_key = self.encrypt_key(new_plaintext_key)

        # Update record
        api_key.encrypted_key = encrypted_key

        self.db.commit()
        self.db.refresh(api_key)

        return api_key

    def delete_api_key(self, service_name: str) -> None:
        """
        Delete an API key.

        Args:
            service_name: Service identifier

        Raises:
            ValueError: If key not found
        """
        api_key = self.get_api_key(service_name)
        if not api_key:
            raise ValueError(f"API key for service '{service_name}' not found")

        self.db.delete(api_key)
        self.db.commit()

    def list_api_keys(self) -> list[APIKey]:
        """
        List all API keys.

        Returns:
            List of APIKey instances
        """
        return self.db.query(APIKey).all()

    def verify_api_key(self, service_name: SupportedService) -> tuple[bool, str]:
        """
        Verify an API key by testing it against the actual service API.

        Args:
            service_name: Service to verify (anthropic, openai, cohere, huggingface)

        Returns:
            Tuple of (is_valid: bool, message: str)

        Raises:
            ValueError: If key not found or service not supported
        """
        # Get decrypted key
        plaintext_key = self.get_decrypted_key(service_name)

        # Verify based on service
        if service_name == "anthropic":
            return self._verify_anthropic(plaintext_key)
        elif service_name == "openai":
            return self._verify_openai(plaintext_key)
        elif service_name == "cohere":
            return self._verify_cohere(plaintext_key)
        elif service_name == "huggingface":
            return self._verify_huggingface(plaintext_key)
        else:
            raise ValueError(f"Service '{service_name}' verification not supported")

    def _verify_anthropic(self, api_key: str) -> tuple[bool, str]:
        """Verify Anthropic API key."""
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            # Test API call - list models
            client.models.list()

            return True, "Anthropic API key is valid and authenticated successfully"
        except Exception as e:
            return False, f"Anthropic API key verification failed: {str(e)}"

    def _verify_openai(self, api_key: str) -> tuple[bool, str]:
        """Verify OpenAI API key."""
        try:
            import openai

            client = openai.OpenAI(api_key=api_key)
            # Test API call - list models
            client.models.list()

            return True, "OpenAI API key is valid and authenticated successfully"
        except Exception as e:
            return False, f"OpenAI API key verification failed: {str(e)}"

    def _verify_cohere(self, api_key: str) -> tuple[bool, str]:
        """Verify Cohere API key."""
        try:
            import cohere

            client = cohere.Client(api_key=api_key)
            # Test API call - check models endpoint
            client.models.list()

            return True, "Cohere API key is valid and authenticated successfully"
        except Exception as e:
            return False, f"Cohere API key verification failed: {str(e)}"

    def _verify_huggingface(self, api_key: str) -> tuple[bool, str]:
        """Verify HuggingFace API key."""
        try:
            from huggingface_hub import HfApi

            api = HfApi(token=api_key)
            # Test API call - get user info
            api.whoami()

            return True, "HuggingFace API key is valid and authenticated successfully"
        except Exception as e:
            return False, f"HuggingFace API key verification failed: {str(e)}"
