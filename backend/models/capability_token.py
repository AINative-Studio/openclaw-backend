"""
Capability Token Schema (E7-S1, E7-S5)

Defines capability tokens for secure node authorization in the P2P swarm.
Tokens control node permissions, execution limits, and data access scope.
Extended with rotation and renewal capabilities.

Refs: OpenCLAW P2P Swarm PRD Section on Security, Backlog E7-S1, #47
"""

from datetime import datetime, timedelta
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional
import secrets


class TokenLimits(BaseModel):
    """
    Resource limits for token holder

    Defines maximum resource allocation and concurrent task constraints
    """
    max_gpu_minutes: int = Field(
        ...,
        ge=0,
        description="Maximum GPU minutes allocated"
    )
    max_concurrent_tasks: int = Field(
        ...,
        ge=0,
        description="Maximum number of concurrent tasks"
    )


class CapabilityToken(BaseModel):
    """
    Capability token for node authorization

    Controls what models a node can execute, resource limits,
    and data access scope. Tokens are signed JWTs with expiration.
    Supports rotation and renewal for enhanced security.

    Attributes:
        jti: JWT ID (unique token identifier) for rotation tracking
        peer_id: libp2p peer ID (12D3KooW...)
        capabilities: List of allowed capabilities (e.g., "can_execute:llama-2-7b")
        limits: Resource allocation limits
        data_scope: List of allowed project IDs (empty means all projects)
        expires_at: Unix timestamp when token expires
        parent_jti: Optional parent token ID (for rotation tracking)
    """
    jti: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="JWT ID (unique token identifier)"
    )
    peer_id: str = Field(
        ...,
        min_length=1,
        description="libp2p peer ID"
    )
    capabilities: List[str] = Field(
        ...,
        min_length=1,
        description="List of allowed capabilities (e.g., can_execute:model-name)"
    )
    limits: TokenLimits = Field(
        ...,
        description="Resource allocation limits"
    )
    data_scope: List[str] = Field(
        default_factory=list,
        description="List of allowed project IDs (empty = all projects)"
    )
    expires_at: int = Field(
        ...,
        ge=0,
        description="Unix timestamp when token expires"
    )
    parent_jti: Optional[str] = Field(
        None,
        description="Parent token ID (for rotation)"
    )

    @field_validator('peer_id')
    @classmethod
    def validate_peer_id_not_empty(cls, v: str) -> str:
        """Ensure peer_id is not empty or whitespace"""
        if not v or not v.strip():
            raise ValueError("peer_id cannot be empty")
        return v

    @field_validator('capabilities')
    @classmethod
    def validate_capabilities_not_empty(cls, v: List[str]) -> List[str]:
        """Ensure capabilities list is not empty"""
        if not v or len(v) == 0:
            raise ValueError("capabilities cannot be empty")
        return v

    @field_validator('expires_at')
    @classmethod
    def validate_expires_at_future(cls, v: int) -> int:
        """Ensure expiration is in the future"""
        current_timestamp = int(datetime.utcnow().timestamp())
        if v < current_timestamp:
            raise ValueError(
                f"expires_at must be in the future (current: {current_timestamp}, provided: {v})"
            )
        return v

    def has_capability(self, capability: str) -> bool:
        """
        Check if token has a specific capability

        Args:
            capability: Capability string to check (e.g., "can_execute:llama-2-7b")

        Returns:
            True if token has the capability, False otherwise
        """
        return capability in self.capabilities

    def has_data_access(self, project_id: str) -> bool:
        """
        Check if token has access to a specific project

        Args:
            project_id: Project ID to check access for

        Returns:
            True if token has access, False otherwise
            Empty data_scope means access to all projects
        """
        # Empty data_scope means no restrictions
        if not self.data_scope or len(self.data_scope) == 0:
            return True

        return project_id in self.data_scope

    def is_expired(self) -> bool:
        """
        Check if token is expired

        Returns:
            True if token is expired, False otherwise
        """
        current_timestamp = int(datetime.utcnow().timestamp())
        return current_timestamp >= self.expires_at

    def expires_in_seconds(self) -> int:
        """
        Get remaining seconds until expiration

        Returns:
            Remaining seconds (0 if already expired)
        """
        current_timestamp = int(datetime.utcnow().timestamp())
        remaining = self.expires_at - current_timestamp
        return max(0, remaining)

    def should_renew(self, threshold_seconds: int = 3600) -> bool:
        """
        Check if token should be renewed

        Args:
            threshold_seconds: Renew if expiring within this threshold (default 1 hour)

        Returns:
            True if token should be renewed
        """
        return self.expires_in_seconds() < threshold_seconds and not self.is_expired()

    @classmethod
    def create(
        cls,
        peer_id: str,
        capabilities: List[str],
        limits: TokenLimits,
        data_scope: Optional[List[str]] = None,
        expires_in_seconds: int = 3600,
        parent_jti: Optional[str] = None
    ) -> "CapabilityToken":
        """
        Create a new capability token

        Args:
            peer_id: libp2p peer ID
            capabilities: List of allowed capabilities
            limits: Resource allocation limits
            data_scope: Optional list of allowed project IDs
            expires_in_seconds: Token lifetime (default 1 hour)
            parent_jti: Parent token ID if this is a renewal

        Returns:
            New capability token instance
        """
        expires_at = int((datetime.utcnow() + timedelta(seconds=expires_in_seconds)).timestamp())

        return cls(
            peer_id=peer_id,
            capabilities=capabilities,
            limits=limits,
            data_scope=data_scope or [],
            expires_at=expires_at,
            parent_jti=parent_jti
        )
