"""
Agent Personality Endpoints

REST API for managing agent personality files.
Provides CRUD operations on the 8 personality markdown files.
"""

from fastapi import APIRouter, HTTPException, Path, Body

from backend.security.auth_dependencies import get_current_active_user
from backend.models.user import User
from pydantic import BaseModel, Field
from typing import Optional, Dict, List
from backend.personality import PersonalityManager, PersonalityContext
from backend.personality.loader import PersonalitySet, PersonalityFile

router = APIRouter(prefix="/agents", tags=["Agent Personality"])

# Initialize personality manager
personality_manager = PersonalityManager()


# Pydantic schemas for API
class PersonalityFileResponse(BaseModel):
    """Response schema for a single personality file"""
    name: str
    file_type: str
    content: str
    last_modified: Optional[float] = None


class PersonalitySetResponse(BaseModel):
    """Response schema for complete personality set"""
    agent_id: str
    files: Dict[str, Optional[PersonalityFileResponse]]
    missing_files: List[str]


class PersonalityFileUpdate(BaseModel):
    """Request schema for updating a personality file"""
    content: str = Field(..., min_length=1, description="Markdown content")


class PersonalityInitRequest(BaseModel):
    """Request schema for initializing agent personality"""
    agent_name: str = Field(..., description="Human-readable agent name")
    model: str = Field(default="claude-3-5-sonnet-20241022", description="Claude model name")
    persona: Optional[str] = Field(None, description="Optional persona description")


class PersonalityContextResponse(BaseModel):
    """Response schema for personality context"""
    context_type: str
    context: str


def _personality_file_to_response(pf: PersonalityFile) -> PersonalityFileResponse:
    """Convert PersonalityFile to response schema"""
    return PersonalityFileResponse(
        name=pf.name,
        file_type=pf.file_type,
        content=pf.content,
        last_modified=pf.last_modified
    )


def _personality_set_to_response(ps: PersonalitySet) -> PersonalitySetResponse:
    """Convert PersonalitySet to response schema"""
    files_dict = {}
    for file_type, pf in ps.get_all_files().items():
        files_dict[file_type] = _personality_file_to_response(pf) if pf else None

    return PersonalitySetResponse(
        agent_id=ps.agent_id,
        files=files_dict,
        missing_files=ps.get_missing_files()
    )


@router.get("/{agent_id}/personality", response_model=PersonalitySetResponse)
async def get_agent_personality(
    agent_id: str = Path(..., description="Agent UUID")
):
    """
    Get complete personality set for an agent

    Returns all 8 personality files if they exist.
    """
    try:
        personality_set = personality_manager.get_personality(agent_id)
        return _personality_set_to_response(personality_set)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load personality: {str(e)}")


@router.get("/{agent_id}/personality/{file_type}", response_model=PersonalityFileResponse)
async def get_personality_file(
    agent_id: str = Path(..., description="Agent UUID"),
    file_type: str = Path(..., description="File type (soul, agents, tools, identity, user, bootstrap, heartbeat, memory)")
):
    """
    Get a single personality file

    Valid file types:
    - soul: Core ethics and personality
    - agents: Multi-agent collaboration
    - tools: Tool usage patterns
    - identity: Agent identity
    - user: User interaction patterns
    - bootstrap: Initial setup
    - heartbeat: Health monitoring
    - memory: Curated long-term memory
    """
    valid_types = ['soul', 'agents', 'tools', 'identity', 'user', 'bootstrap', 'heartbeat', 'memory']
    if file_type.lower() not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Must be one of: {', '.join(valid_types)}")

    try:
        personality_file = personality_manager.get_personality_file(agent_id, file_type.lower())
        if not personality_file:
            raise HTTPException(status_code=404, detail=f"Personality file '{file_type}' not found for agent {agent_id}")
        return _personality_file_to_response(personality_file)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to load personality file: {str(e)}")


@router.put("/{agent_id}/personality/{file_type}", response_model=PersonalityFileResponse)
async def update_personality_file(
    agent_id: str = Path(..., description="Agent UUID"),
    file_type: str = Path(..., description="File type"),
    update: PersonalityFileUpdate = Body(...)
):
    """
    Update a personality file

    Creates the file if it doesn't exist.
    This is how agents evolve their personality over time.
    """
    valid_types = ['soul', 'agents', 'tools', 'identity', 'user', 'bootstrap', 'heartbeat', 'memory']
    if file_type.lower() not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Must be one of: {', '.join(valid_types)}")

    try:
        personality_file = personality_manager.update_personality_file(
            agent_id,
            file_type.lower(),
            update.content
        )
        return _personality_file_to_response(personality_file)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update personality file: {str(e)}")


@router.delete("/{agent_id}/personality/{file_type}")
async def delete_personality_file(
    agent_id: str = Path(..., description="Agent UUID"),
    file_type: str = Path(..., description="File type")
):
    """
    Delete a personality file

    Note: This removes the file but doesn't affect the agent's core functionality.
    The agent will use default behavior for that personality aspect.
    """
    valid_types = ['soul', 'agents', 'tools', 'identity', 'user', 'bootstrap', 'heartbeat', 'memory']
    if file_type.lower() not in valid_types:
        raise HTTPException(status_code=400, detail=f"Invalid file type. Must be one of: {', '.join(valid_types)}")

    try:
        deleted = personality_manager.delete_personality_file(agent_id, file_type.lower())
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Personality file '{file_type}' not found")
        return {"status": "deleted", "file_type": file_type}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete personality file: {str(e)}")


@router.post("/{agent_id}/personality/initialize", response_model=PersonalitySetResponse)
async def initialize_agent_personality(
    agent_id: str = Path(..., description="Agent UUID"),
    init_request: PersonalityInitRequest = Body(...)
):
    """
    Initialize personality files for a new agent

    Creates all 8 personality files with default templates.
    Should be called when a new agent is created.
    """
    try:
        personality_set = personality_manager.initialize_agent_personality(
            agent_id,
            init_request.agent_name,
            init_request.model,
            init_request.persona
        )
        return _personality_set_to_response(personality_set)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize personality: {str(e)}")


@router.delete("/{agent_id}/personality")
async def delete_agent_personality(
    agent_id: str = Path(..., description="Agent UUID")
):
    """
    Delete all personality files for an agent

    Should be called when an agent is deleted.
    """
    try:
        count = personality_manager.delete_agent(agent_id)
        return {
            "status": "deleted",
            "agent_id": agent_id,
            "files_deleted": count
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to delete personality: {str(e)}")


@router.get("/{agent_id}/personality/context/system", response_model=PersonalityContextResponse)
async def get_system_context(
    agent_id: str = Path(..., description="Agent UUID")
):
    """
    Get complete system context for LLM prompts

    Returns formatted personality context suitable for system messages.
    Includes all personality files in structured format.
    """
    try:
        personality_set = personality_manager.get_personality(agent_id)
        context = PersonalityContext.build_system_context(personality_set)
        return PersonalityContextResponse(
            context_type="system",
            context=context
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build system context: {str(e)}")


@router.get("/{agent_id}/personality/context/minimal", response_model=PersonalityContextResponse)
async def get_minimal_context(
    agent_id: str = Path(..., description="Agent UUID")
):
    """
    Get minimal personality context

    Returns just identity and core ethics.
    Useful for token-constrained scenarios.
    """
    try:
        personality_set = personality_manager.get_personality(agent_id)
        context = PersonalityContext.build_minimal_context(personality_set)
        return PersonalityContextResponse(
            context_type="minimal",
            context=context
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build minimal context: {str(e)}")


@router.post("/{agent_id}/personality/context/task", response_model=PersonalityContextResponse)
async def get_task_context(
    agent_id: str = Path(..., description="Agent UUID"),
    task_description: str = Body(..., embed=True, description="Description of the task")
):
    """
    Get task-specific personality context

    Returns personality context tailored to a specific task.
    Includes only relevant personality aspects for the task.
    """
    try:
        personality_set = personality_manager.get_personality(agent_id)
        context = PersonalityContext.build_task_context(personality_set, task_description)
        return PersonalityContextResponse(
            context_type="task",
            context=context
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to build task context: {str(e)}")
