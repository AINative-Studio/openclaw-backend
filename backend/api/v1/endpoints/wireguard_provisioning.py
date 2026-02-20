"""
WireGuard Peer Provisioning API Endpoint

FastAPI endpoint for WireGuard peer provisioning.
Implements E1-S3: WireGuard Peer Provisioning Service

Provides:
- POST /api/v1/wireguard/provision - Provision new peer
- GET /api/v1/wireguard/peers - List provisioned peers
- DELETE /api/v1/wireguard/peers/{node_id} - Deprovision peer
- GET /api/v1/wireguard/pool/stats - Get IP pool statistics

Security:
- Input validation via Pydantic models
- Error handling with appropriate HTTP status codes
- Rate limiting (to be implemented)
"""

import logging
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse

from backend.models.wireguard.provisioning import (
    ProvisioningRequest,
    ProvisioningResponse,
    PeerConfiguration
)
from backend.services.wireguard_provisioning_service import (
    WireGuardProvisioningService,
    DuplicatePeerError,
    IPPoolExhaustedError,
    InvalidCredentialsError,
    ProvisioningError
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wireguard", tags=["WireGuard", "Networking"])


# ============================================================================
# Dependency Injection
# ============================================================================

# Singleton instance of provisioning service
_provisioning_service: Optional[WireGuardProvisioningService] = None


def get_provisioning_service() -> WireGuardProvisioningService:
    """
    Get or create provisioning service instance

    Returns:
        WireGuardProvisioningService instance
    """
    global _provisioning_service

    if _provisioning_service is None:
        # Initialize service with default configuration
        # In production, these values would come from environment variables
        _provisioning_service = WireGuardProvisioningService(
            ip_pool_network="10.0.0.0/24",
            hub_public_key="hub_wireguard_public_key_placeholder==",
            hub_endpoint="hub.example.com:51820",
            hub_ip="10.0.0.1",
            config_path="/etc/wireguard/wg0.conf",
            enable_dbos=False  # Will enable when E4-S1 is ready
        )

    return _provisioning_service


# ============================================================================
# API Endpoints
# ============================================================================

@router.post(
    "/provision",
    response_model=ProvisioningResponse,
    status_code=status.HTTP_200_OK,
    summary="Provision new WireGuard peer",
    description="""
    Provision a new WireGuard peer in the swarm.

    This endpoint handles the complete provisioning workflow:
    1. Validates node credentials
    2. Allocates unique IP address from pool
    3. Updates hub WireGuard configuration
    4. Stores provisioning record in DBOS (if available)
    5. Returns complete peer configuration

    **Requirements:**
    - Unique node_id
    - Valid WireGuard public key (base64 encoded)
    - Node capabilities (GPU, CPU, models)
    - Software version (semantic versioning)

    **Returns:**
    - Assigned IP address
    - Hub connection details
    - Complete WireGuard configuration

    **Errors:**
    - 400: Invalid request (validation errors)
    - 409: Peer already provisioned
    - 503: IP pool exhausted
    - 500: Internal server error
    """,
    responses={
        200: {
            "description": "Peer provisioned successfully",
            "content": {
                "application/json": {
                    "example": {
                        "status": "success",
                        "config": {
                            "node_id": "test-node-001",
                            "assigned_ip": "10.0.0.2",
                            "subnet_mask": "255.255.255.0",
                            "hub_public_key": "hub_key==",
                            "hub_endpoint": "hub.example.com:51820",
                            "allowed_ips": "10.0.0.0/24",
                            "persistent_keepalive": 25,
                            "dns_servers": ["10.0.0.1"],
                            "provisioned_at": "2026-02-19T12:00:00"
                        },
                        "message": "Peer provisioned successfully"
                    }
                }
            }
        },
        409: {
            "description": "Peer already provisioned",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Peer test-node-001 is already provisioned",
                        "existing_config": {
                            "node_id": "test-node-001",
                            "assigned_ip": "10.0.0.2"
                        }
                    }
                }
            }
        },
        503: {
            "description": "IP pool exhausted",
            "content": {
                "application/json": {
                    "example": {
                        "detail": "IP pool exhausted: 253 addresses allocated from range 10.0.0.0/24"
                    }
                }
            }
        }
    }
)
async def provision_peer(
    request: ProvisioningRequest,
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> ProvisioningResponse:
    """
    Provision a new WireGuard peer

    Args:
        request: Provisioning request with node credentials
        service: Provisioning service instance (injected)

    Returns:
        ProvisioningResponse with peer configuration

    Raises:
        HTTPException: On provisioning errors
    """
    try:
        logger.info(
            f"Provisioning request received: node_id={request.node_id}, "
            f"version={request.version}"
        )

        # Provision peer through service layer
        config_dict = service.provision_peer(
            node_id=request.node_id,
            public_key=request.public_key,
            wireguard_public_key=request.wireguard_public_key,
            capabilities=request.capabilities.model_dump(),
            version=request.version,
            metadata=request.metadata
        )

        # Convert to Pydantic model
        peer_config = PeerConfiguration(**config_dict)

        # Build response
        response = ProvisioningResponse(
            status="success",
            config=peer_config,
            message=f"Peer {request.node_id} provisioned successfully"
        )

        logger.info(
            f"Provisioned peer {request.node_id} with IP {peer_config.assigned_ip}"
        )

        return response

    except DuplicatePeerError as e:
        logger.warning(f"Duplicate peer provisioning attempt: {e}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": str(e),
                "existing_config": e.existing_config
            }
        )

    except IPPoolExhaustedError as e:
        logger.error(f"IP pool exhausted: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e)
        )

    except InvalidCredentialsError as e:
        logger.warning(f"Invalid credentials: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except ProvisioningError as e:
        logger.error(f"Provisioning error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Provisioning failed: {str(e)}"
        )

    except Exception as e:
        logger.error(f"Unexpected error during provisioning: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error during provisioning"
        )


@router.get(
    "/peers",
    response_model=Dict[str, Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="List provisioned peers",
    description="""
    Get list of all provisioned WireGuard peers.

    Returns mapping of node_id to peer configuration.
    """
)
async def list_peers(
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> Dict[str, Dict[str, Any]]:
    """
    List all provisioned peers

    Args:
        service: Provisioning service instance (injected)

    Returns:
        Dictionary mapping node_id to configuration
    """
    try:
        peers = service.list_provisioned_peers()
        logger.info(f"Listed {len(peers)} provisioned peers")
        return peers

    except Exception as e:
        logger.error(f"Error listing peers: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list peers"
        )


@router.delete(
    "/peers/{node_id}",
    status_code=status.HTTP_200_OK,
    summary="Deprovision peer",
    description="""
    Deprovision a WireGuard peer (revoke access).

    This will:
    - Remove peer from hub configuration
    - Deallocate IP address
    - Remove provisioning record
    """
)
async def deprovision_peer(
    node_id: str,
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> Dict[str, str]:
    """
    Deprovision a peer

    Args:
        node_id: Node identifier to deprovision
        service: Provisioning service instance (injected)

    Returns:
        Success message

    Raises:
        HTTPException: On deprovisioning errors
    """
    try:
        service.deprovision_peer(node_id=node_id)
        logger.info(f"Deprovisioned peer {node_id}")

        return {
            "status": "success",
            "message": f"Peer {node_id} deprovisioned successfully"
        }

    except ValueError as e:
        logger.warning(f"Peer not found: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )

    except Exception as e:
        logger.error(f"Error deprovisioning peer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deprovision peer"
        )


@router.get(
    "/pool/stats",
    response_model=Dict[str, int],
    status_code=status.HTTP_200_OK,
    summary="Get IP pool statistics",
    description="""
    Get IP address pool statistics.

    Returns:
    - Total addresses in pool
    - Reserved addresses
    - Allocated addresses
    - Available addresses
    - Utilization percentage
    """
)
async def get_pool_stats(
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> Dict[str, int]:
    """
    Get IP pool statistics

    Args:
        service: Provisioning service instance (injected)

    Returns:
        Pool statistics dictionary
    """
    try:
        stats = service.get_pool_stats()
        logger.debug(f"Pool stats: {stats}")
        return stats

    except Exception as e:
        logger.error(f"Error getting pool stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get pool statistics"
        )


@router.get(
    "/peers/{node_id}",
    response_model=PeerConfiguration,
    status_code=status.HTTP_200_OK,
    summary="Get peer configuration",
    description="""
    Get configuration for a specific provisioned peer.
    """
)
async def get_peer_config(
    node_id: str,
    service: WireGuardProvisioningService = Depends(get_provisioning_service)
) -> PeerConfiguration:
    """
    Get peer configuration

    Args:
        node_id: Node identifier
        service: Provisioning service instance (injected)

    Returns:
        Peer configuration

    Raises:
        HTTPException: If peer not found
    """
    try:
        config = service.get_peer_config(node_id=node_id)

        if config is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Peer {node_id} not found"
            )

        return PeerConfiguration(**config)

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Error getting peer config: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get peer configuration"
        )
