"""
Agent Skill Configuration API Endpoints

Provides CRUD operations for agent skill configurations with encrypted credential storage.
Supports configuring API keys, OAuth tokens, and custom settings for agent skills.
"""

import logging
from uuid import UUID
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

try:
    from backend.db.base import get_db
    from backend.models.agent_skill_configuration import AgentSkillConfiguration
    from backend.models.agent_swarm_lifecycle import AgentSwarmInstance
    from backend.schemas.agent_skill_config import (
        SkillConfigurationRequest,
        SkillConfigurationResponse,
        AgentSkillsConfigResponse,
        SkillConfigurationSummary,
    )
    AGENT_SKILL_CONFIG_AVAILABLE = True
except (ImportError, ModuleNotFoundError) as e:
    logger.warning(f"Agent skill configuration service not available: {e}")
    AGENT_SKILL_CONFIG_AVAILABLE = False

router = APIRouter(prefix="/agents", tags=["Agent Skills"])


def _check_available() -> None:
    """Raise 503 if service dependencies are not available"""
    if not AGENT_SKILL_CONFIG_AVAILABLE:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent skill configuration service is not available",
        )


def _validate_agent_exists(db: Session, agent_id: UUID) -> AgentSwarmInstance:
    """
    Validate that agent exists in database

    Args:
        db: Database session
        agent_id: Agent UUID

    Returns:
        AgentSwarmInstance object

    Raises:
        HTTPException: 404 if agent not found
    """
    agent = db.query(AgentSwarmInstance).filter(AgentSwarmInstance.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_id}' not found",
        )
    return agent


def _config_to_response(config: AgentSkillConfiguration) -> SkillConfigurationResponse:
    """
    Convert ORM model to API response (redacts credentials)

    Args:
        config: AgentSkillConfiguration ORM object

    Returns:
        SkillConfigurationResponse with credentials redacted
    """
    return SkillConfigurationResponse(
        id=config.id,
        agent_id=config.agent_id,
        skill_name=config.skill_name,
        enabled=config.enabled,
        config=config.get_config(),
        has_credentials=bool(config.credentials),
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


def _config_to_summary(config: AgentSkillConfiguration) -> SkillConfigurationSummary:
    """
    Convert ORM model to summary (for list response)

    Args:
        config: AgentSkillConfiguration ORM object

    Returns:
        SkillConfigurationSummary
    """
    return SkillConfigurationSummary(
        skill_name=config.skill_name,
        enabled=config.enabled,
        has_credentials=bool(config.credentials),
        config=config.get_config(),
    )


@router.get(
    "/{agent_id}/skills",
    response_model=AgentSkillsConfigResponse,
    status_code=status.HTTP_200_OK,
    summary="List all skill configurations for an agent",
)
def list_agent_skills(
    agent_id: UUID,
    db: Session = Depends(get_db),
) -> AgentSkillsConfigResponse:
    """
    List all skill configurations for a specific agent.

    Returns credentials status (has_credentials) but not actual credential values.
    """
    _check_available()

    try:
        # Validate agent exists
        _validate_agent_exists(db, agent_id)

        # Query all skills for this agent
        configs = (
            db.query(AgentSkillConfiguration)
            .filter(AgentSkillConfiguration.agent_id == agent_id)
            .order_by(AgentSkillConfiguration.skill_name)
            .all()
        )

        # Calculate statistics
        total_skills = len(configs)
        enabled_skills = sum(1 for c in configs if c.enabled)
        configured_skills = sum(1 for c in configs if c.credentials)

        return AgentSkillsConfigResponse(
            agent_id=agent_id,
            total_skills=total_skills,
            enabled_skills=enabled_skills,
            configured_skills=configured_skills,
            skills=[_config_to_summary(c) for c in configs],
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing agent skills: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list agent skills: {str(e)}",
        )


@router.post(
    "/{agent_id}/skills/{skill_name}/configure",
    response_model=SkillConfigurationResponse,
    status_code=status.HTTP_200_OK,
    summary="Configure or update skill credentials and settings",
)
def configure_skill(
    agent_id: UUID,
    skill_name: str,
    request: SkillConfigurationRequest,
    db: Session = Depends(get_db),
) -> SkillConfigurationResponse:
    """
    Configure or update a skill for an agent.

    Creates new configuration if it doesn't exist, otherwise updates existing.
    Credentials are encrypted before storage using Fernet symmetric encryption.

    Returns the configuration with credentials redacted (has_credentials flag only).
    """
    _check_available()

    try:
        # Validate agent exists
        _validate_agent_exists(db, agent_id)

        # Check if configuration already exists
        existing_config = (
            db.query(AgentSkillConfiguration)
            .filter(
                AgentSkillConfiguration.agent_id == agent_id,
                AgentSkillConfiguration.skill_name == skill_name,
            )
            .first()
        )

        if existing_config:
            # Update existing configuration
            config = existing_config
        else:
            # Create new configuration
            config = AgentSkillConfiguration(
                agent_id=agent_id,
                skill_name=skill_name,
            )
            db.add(config)

        # Update credentials (encrypted)
        credentials_dict = request.get_credentials_dict()
        if credentials_dict:
            config.set_credentials(credentials_dict)

        # Update non-sensitive configuration
        if request.config is not None:
            config.set_config(request.config)

        # Update enabled flag
        config.enabled = request.enabled

        # Commit to database
        try:
            db.commit()
            db.refresh(config)
        except IntegrityError as e:
            db.rollback()
            # This shouldn't happen due to earlier check, but handle race condition
            logger.warning(f"Integrity error configuring skill: {e}")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Skill '{skill_name}' configuration already exists for agent",
            )

        return _config_to_response(config)

    except HTTPException:
        raise
    except ValueError as e:
        # Raised by set_credentials if encryption fails
        logger.error(f"Encryption error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error configuring skill: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to configure skill: {str(e)}",
        )


@router.get(
    "/{agent_id}/skills/{skill_name}",
    response_model=SkillConfigurationResponse,
    status_code=status.HTTP_200_OK,
    summary="Get specific skill configuration",
)
def get_skill_configuration(
    agent_id: UUID,
    skill_name: str,
    db: Session = Depends(get_db),
) -> SkillConfigurationResponse:
    """
    Get configuration for a specific skill.

    Returns credentials status (has_credentials) but not actual credential values.
    """
    _check_available()

    try:
        # Validate agent exists
        _validate_agent_exists(db, agent_id)

        # Query skill configuration
        config = (
            db.query(AgentSkillConfiguration)
            .filter(
                AgentSkillConfiguration.agent_id == agent_id,
                AgentSkillConfiguration.skill_name == skill_name,
            )
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_name}' not configured for agent '{agent_id}'",
            )

        return _config_to_response(config)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting skill configuration: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get skill configuration: {str(e)}",
        )


@router.delete(
    "/{agent_id}/skills/{skill_name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete skill configuration",
)
def delete_skill_configuration(
    agent_id: UUID,
    skill_name: str,
    db: Session = Depends(get_db),
) -> None:
    """
    Delete a skill configuration for an agent.

    Removes both credentials and configuration settings.
    Returns 204 No Content on success.
    """
    _check_available()

    try:
        # Validate agent exists
        _validate_agent_exists(db, agent_id)

        # Query skill configuration
        config = (
            db.query(AgentSkillConfiguration)
            .filter(
                AgentSkillConfiguration.agent_id == agent_id,
                AgentSkillConfiguration.skill_name == skill_name,
            )
            .first()
        )

        if not config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skill '{skill_name}' not configured for agent '{agent_id}'",
            )

        # Delete configuration
        db.delete(config)
        db.commit()

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting skill configuration: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete skill configuration: {str(e)}",
        )
