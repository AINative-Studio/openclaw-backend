"""
WireGuard Provisioning Models

Pydantic models for WireGuard peer provisioning requests and responses.
Implements E1-S3: WireGuard Peer Provisioning Service

Security considerations:
- All public keys validated for format
- IP addresses validated as private IPs
- Capabilities validated for reasonable values
"""

from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import List, Dict, Any, Optional
from datetime import datetime
import re


class NodeCapabilities(BaseModel):
    """Node hardware and software capabilities"""
    model_config = ConfigDict(extra='forbid')

    gpu_count: int = Field(
        0,
        ge=0,
        le=16,
        description="Number of GPUs available"
    )
    gpu_memory_mb: int = Field(
        0,
        ge=0,
        le=1048576,  # 1TB max
        description="Total GPU memory in MB"
    )
    cpu_cores: int = Field(
        1,
        ge=1,
        le=256,
        description="Number of CPU cores"
    )
    memory_mb: int = Field(
        1024,
        ge=512,
        le=2097152,  # 2TB max
        description="Total RAM in MB"
    )
    models: List[str] = Field(
        default_factory=list,
        description="List of supported AI models"
    )

    @field_validator('models')
    @classmethod
    def validate_models(cls, v):
        """Validate model names are non-empty strings"""
        if not isinstance(v, list):
            raise ValueError("models must be a list")
        for model in v:
            if not isinstance(model, str) or not model.strip():
                raise ValueError("model names must be non-empty strings")
        return v


class ProvisioningRequest(BaseModel):
    """Request to provision a new WireGuard peer"""
    model_config = ConfigDict(extra='forbid')

    node_id: str = Field(
        ...,
        min_length=1,
        max_length=128,
        description="Unique identifier for the node"
    )
    public_key: str = Field(
        ...,
        min_length=32,
        max_length=256,
        description="libp2p Ed25519 public key"
    )
    wireguard_public_key: str = Field(
        ...,
        min_length=32,
        max_length=256,
        description="WireGuard public key (base64 encoded)"
    )
    capabilities: NodeCapabilities = Field(
        ...,
        description="Node hardware and software capabilities"
    )
    version: str = Field(
        ...,
        pattern=r'^\d+\.\d+\.\d+$',
        description="Node software version (semantic versioning)"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional node metadata"
    )

    @field_validator('node_id')
    @classmethod
    def validate_node_id(cls, v):
        """Validate node_id format (alphanumeric, dashes, underscores)"""
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError(
                "node_id must contain only alphanumeric characters, dashes, and underscores"
            )
        return v

    @field_validator('wireguard_public_key')
    @classmethod
    def validate_wireguard_key(cls, v):
        """Validate WireGuard public key format (base64)"""
        # WireGuard keys are 44 characters base64 encoded
        if not re.match(r'^[A-Za-z0-9+/]{42,44}={0,2}$', v):
            raise ValueError(
                "wireguard_public_key must be a valid base64-encoded key"
            )
        return v


class PeerConfiguration(BaseModel):
    """Complete WireGuard peer configuration"""
    model_config = ConfigDict(extra='allow')

    node_id: str = Field(..., description="Node identifier")
    assigned_ip: str = Field(..., description="Assigned private IP address")
    subnet_mask: str = Field(
        "255.255.255.0",
        description="Subnet mask for the network"
    )
    hub_public_key: str = Field(..., description="Hub's WireGuard public key")
    hub_endpoint: str = Field(
        ...,
        description="Hub endpoint (hostname:port)"
    )
    allowed_ips: str = Field(
        "10.0.0.0/24",
        description="Allowed IP ranges"
    )
    persistent_keepalive: int = Field(
        25,
        ge=0,
        le=3600,
        description="Persistent keepalive interval in seconds"
    )
    dns_servers: List[str] = Field(
        default_factory=lambda: ["10.0.0.1"],
        description="DNS server addresses"
    )
    provisioned_at: str = Field(
        ...,
        description="ISO 8601 timestamp of provisioning"
    )

    @field_validator('assigned_ip')
    @classmethod
    def validate_ip_address(cls, v):
        """Validate IP address format"""
        import ipaddress
        try:
            ip = ipaddress.ip_address(v)
            if not ip.is_private:
                raise ValueError("assigned_ip must be a private IP address")
        except ValueError as e:
            raise ValueError(f"Invalid IP address: {e}")
        return v

    @field_validator('hub_endpoint')
    @classmethod
    def validate_endpoint(cls, v):
        """Validate endpoint format (hostname:port)"""
        if ':' not in v:
            raise ValueError("hub_endpoint must be in format 'hostname:port'")
        host, port = v.rsplit(':', 1)
        try:
            port_num = int(port)
            if not 1 <= port_num <= 65535:
                raise ValueError("port must be between 1 and 65535")
        except ValueError:
            raise ValueError("Invalid port number in hub_endpoint")
        return v


class ProvisioningResponse(BaseModel):
    """Response after successful provisioning"""
    model_config = ConfigDict(extra='allow')

    status: str = Field("success", description="Provisioning status")
    config: PeerConfiguration = Field(..., description="Peer configuration")
    message: str = Field(
        "Peer provisioned successfully",
        description="Human-readable message"
    )


class ProvisioningRecord(BaseModel):
    """Database record for provisioning (for DBOS integration)"""
    model_config = ConfigDict(extra='allow')

    id: Optional[int] = Field(None, description="Database ID")
    node_id: str = Field(..., description="Node identifier")
    assigned_ip: str = Field(..., description="Assigned IP address")
    wireguard_public_key: str = Field(..., description="WireGuard public key")
    provisioned_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Provisioning timestamp"
    )
    status: str = Field(
        "active",
        description="Peer status (active, revoked)"
    )
    capabilities: Dict[str, Any] = Field(
        default_factory=dict,
        description="Node capabilities"
    )
