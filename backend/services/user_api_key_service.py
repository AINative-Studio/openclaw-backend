"""
User API Key Service - Encryption and Business Logic (Issue #96)

Handles encryption/decryption of workspace-level API keys using Fernet symmetric encryption.
Provides CRUD operations and key verification against external APIs.

Security Features:
- Fernet (AES-128-CBC + HMAC-SHA256) encryption
- Keys encrypted at rest using ENCRYPTION_SECRET from environment
- SHA-256 hashing for key validation
- Masked key display (shows only last 4 characters)
- Rate limiting on validation attempts (via endpoint)
- Never logs or exposes plaintext keys
"""

import os
from typing import Optional
from datetime import datetime, timezone
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.models.user_api_key import UserAPIKey


class UserAPIKeyService:
    """
    Service for managing encrypted workspace-level API keys.

    Encryption:
        - Uses Fernet (symmetric encryption based on AES-128-CBC + HMAC-SHA256)
        - Encryption key from environment variable ENCRYPTION_SECRET
        - Each encryption includes random IV for security
        - Keys are also hashed with SHA-256 for validation

    Supported Providers:
        - anthropic: Claude API
        - openai: GPT API
        - cohere: Cohere API
        - huggingface: HuggingFace API
        - google: Gemini API
    """

    SUPPORTED_PROVIDERS = ["anthropic", "openai", "cohere", "huggingface", "google"]

    def __init__(self, db: Session, encryption_secret: Optional[str] = None):
        """
        Initialize user API key service.

        Args:
            db: SQLAlchemy database session
            encryption_secret: Optional encryption key (defaults to env var ENCRYPTION_SECRET)

        Raises:
            ValueError: If encryption secret is not configured
        """
        self.db = db

        # Get encryption secret from parameter or environment
        secret = encryption_secret or os.getenv("ENCRYPTION_SECRET")
        if not secret:
            raise ValueError(
                "ENCRYPTION_SECRET environment variable not set. "
                "Generate one with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
            )

        # Initialize Fernet cipher
        try:
            self.cipher = Fernet(secret.encode() if isinstance(secret, str) else secret)
        except Exception as e:
            raise ValueError(f"Invalid encryption secret format: {e}")

    def encrypt_key(self, plaintext_key: str) -> str:
        """
        Encrypt an API key.

        Args:
            plaintext_key: Plaintext API key to encrypt

        Returns:
            Encrypted key as string (Fernet ciphertext, base64-encoded)
        """
        return self.cipher.encrypt(plaintext_key.encode()).decode()

    def decrypt_key(self, encrypted_key: str) -> str:
        """
        Decrypt an API key.

        Args:
            encrypted_key: Fernet-encrypted key string

        Returns:
            Decrypted plaintext API key

        Raises:
            ValueError: If decryption fails (wrong key or corrupted data)
        """
        try:
            return self.cipher.decrypt(encrypted_key.encode()).decode()
        except InvalidToken:
            raise ValueError(
                "Failed to decrypt API key - invalid encryption secret or corrupted data"
            )

    def mask_key(self, plaintext_key: str) -> str:
        """
        Mask an API key for safe display.

        Shows only the last 4 characters (e.g., "sk-ant-***...1234").

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

        return f"{prefix}-***...{last_four}" if prefix else f"***...{last_four}"

    def add_key(
        self,
        workspace_id: str,
        provider: str,
        plaintext_key: str,
        validate: bool = False
    ) -> UserAPIKey:
        """
        Add and encrypt a user API key.

        Args:
            workspace_id: Workspace UUID
            provider: Provider name (anthropic, openai, cohere, huggingface, google)
            plaintext_key: Plaintext API key to encrypt and store
            validate: If True, validate key against provider API before saving

        Returns:
            Created UserAPIKey model instance

        Raises:
            ValueError: If provider not supported, key already exists, or validation fails
        """
        # Validate provider
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Provider '{provider}' not supported. "
                f"Supported providers: {', '.join(self.SUPPORTED_PROVIDERS)}"
            )

        # Validate key if requested
        if validate:
            is_valid, message = self.validate_key(provider, plaintext_key)
            if not is_valid:
                raise ValueError(f"API key validation failed: {message}")

        # Check for duplicates
        existing = self.db.query(UserAPIKey).filter_by(
            workspace_id=workspace_id,
            provider=provider
        ).first()

        if existing:
            raise ValueError(
                f"API key for provider '{provider}' already exists for this workspace. "
                "Use update_key() to modify it."
            )

        # Encrypt key and compute hash
        encrypted_key = self.encrypt_key(plaintext_key)
        key_hash = UserAPIKey.compute_key_hash(plaintext_key)

        # Create database record
        user_api_key = UserAPIKey(
            workspace_id=workspace_id,
            provider=provider,
            encrypted_key=encrypted_key,
            key_hash=key_hash,
            is_active=True,
            last_validated_at=datetime.now(timezone.utc) if validate else None
        )

        try:
            self.db.add(user_api_key)
            self.db.commit()
            self.db.refresh(user_api_key)
        except IntegrityError as e:
            self.db.rollback()
            raise ValueError(
                f"Failed to add API key (possible duplicate): {str(e)}"
            )

        return user_api_key

    def get_key(self, workspace_id: str, provider: str) -> Optional[str]:
        """
        Get decrypted API key for a workspace and provider.

        Args:
            workspace_id: Workspace UUID
            provider: Provider name

        Returns:
            Decrypted plaintext API key, or None if not found or inactive
        """
        user_api_key = self.db.query(UserAPIKey).filter_by(
            workspace_id=workspace_id,
            provider=provider,
            is_active=True
        ).first()

        if not user_api_key:
            return None

        return self.decrypt_key(user_api_key.encrypted_key)

    def get_key_record(self, workspace_id: str, provider: str) -> Optional[UserAPIKey]:
        """
        Get UserAPIKey record (without decrypting).

        Args:
            workspace_id: Workspace UUID
            provider: Provider name

        Returns:
            UserAPIKey instance or None if not found
        """
        return self.db.query(UserAPIKey).filter_by(
            workspace_id=workspace_id,
            provider=provider
        ).first()

    def list_keys(self, workspace_id: str) -> list[UserAPIKey]:
        """
        List all API keys for a workspace.

        Args:
            workspace_id: Workspace UUID

        Returns:
            List of UserAPIKey instances (encrypted, not decrypted)
        """
        return self.db.query(UserAPIKey).filter_by(
            workspace_id=workspace_id
        ).all()

    def update_key(
        self,
        workspace_id: str,
        provider: str,
        new_plaintext_key: str,
        validate: bool = False
    ) -> UserAPIKey:
        """
        Update an existing API key.

        Args:
            workspace_id: Workspace UUID
            provider: Provider name
            new_plaintext_key: New plaintext API key
            validate: If True, validate key against provider API before saving

        Returns:
            Updated UserAPIKey instance

        Raises:
            ValueError: If key not found or validation fails
        """
        user_api_key = self.get_key_record(workspace_id, provider)
        if not user_api_key:
            raise ValueError(
                f"API key for provider '{provider}' not found for workspace '{workspace_id}'"
            )

        # Validate key if requested
        if validate:
            is_valid, message = self.validate_key(provider, new_plaintext_key)
            if not is_valid:
                raise ValueError(f"API key validation failed: {message}")

        # Encrypt new key and compute hash
        encrypted_key = self.encrypt_key(new_plaintext_key)
        key_hash = UserAPIKey.compute_key_hash(new_plaintext_key)

        # Update record
        user_api_key.encrypted_key = encrypted_key
        user_api_key.key_hash = key_hash
        user_api_key.last_validated_at = datetime.now(timezone.utc) if validate else None

        self.db.commit()
        self.db.refresh(user_api_key)

        return user_api_key

    def delete_key(self, workspace_id: str, provider: str) -> bool:
        """
        Delete an API key.

        Args:
            workspace_id: Workspace UUID
            provider: Provider name

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If deletion fails
        """
        user_api_key = self.get_key_record(workspace_id, provider)
        if not user_api_key:
            return False

        try:
            self.db.delete(user_api_key)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            raise ValueError(f"Failed to delete API key: {str(e)}")

    def delete_key_by_id(self, key_id: str) -> bool:
        """
        Delete an API key by ID.

        Args:
            key_id: UserAPIKey UUID (as string)

        Returns:
            True if deleted, False if not found
        """
        from uuid import UUID

        # Convert string to UUID object
        try:
            uuid_obj = UUID(key_id)
        except (ValueError, AttributeError):
            return False

        user_api_key = self.db.query(UserAPIKey).filter_by(id=uuid_obj).first()
        if not user_api_key:
            return False

        try:
            self.db.delete(user_api_key)
            self.db.commit()
            return True
        except Exception as e:
            self.db.rollback()
            raise ValueError(f"Failed to delete API key: {str(e)}")

    def validate_key(self, provider: str, api_key: str) -> tuple[bool, str]:
        """
        Validate an API key by testing it against the actual service API.

        Makes a lightweight test API call to verify the key works.

        Args:
            provider: Provider to validate (anthropic, openai, cohere, huggingface, google)
            api_key: Plaintext API key to test

        Returns:
            Tuple of (is_valid: bool, message: str)

        Raises:
            ValueError: If provider not supported
        """
        if provider not in self.SUPPORTED_PROVIDERS:
            raise ValueError(
                f"Provider '{provider}' validation not supported. "
                f"Supported providers: {', '.join(self.SUPPORTED_PROVIDERS)}"
            )

        # Validate based on provider
        if provider == "anthropic":
            return self._verify_anthropic(api_key)
        elif provider == "openai":
            return self._verify_openai(api_key)
        elif provider == "cohere":
            return self._verify_cohere(api_key)
        elif provider == "huggingface":
            return self._verify_huggingface(api_key)
        elif provider == "google":
            return self._verify_google(api_key)
        else:
            return False, f"Validation not implemented for provider '{provider}'"

    def _verify_anthropic(self, api_key: str) -> tuple[bool, str]:
        """Verify Anthropic API key."""
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)
            # Test API call - list models
            client.models.list()

            return True, "Anthropic API key is valid and authenticated successfully"
        except anthropic.AuthenticationError:
            return False, "Invalid Anthropic API key"
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
        except openai.AuthenticationError:
            return False, "Invalid OpenAI API key"
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
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "invalid" in error_msg:
                return False, "Invalid Cohere API key"
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
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "invalid" in error_msg:
                return False, "Invalid HuggingFace API key"
            return False, f"HuggingFace API key verification failed: {str(e)}"

    def _verify_google(self, api_key: str) -> tuple[bool, str]:
        """Verify Google API key."""
        try:
            import google.generativeai as genai

            genai.configure(api_key=api_key)
            # Test API call - list models
            list(genai.list_models())

            return True, "Google API key is valid and authenticated successfully"
        except Exception as e:
            error_msg = str(e).lower()
            if "unauthorized" in error_msg or "invalid" in error_msg or "api_key" in error_msg:
                return False, "Invalid Google API key"
            return False, f"Google API key verification failed: {str(e)}"
