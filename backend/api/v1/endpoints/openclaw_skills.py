"""
OpenClaw Skills API Endpoints

Expose OpenClaw skills to the frontend for display in the agent Skills tab.
Merges OpenClaw CLI skills with Claude Code project skills.
"""

from fastapi import APIRouter, HTTPException, status, Query
from typing import List, Dict, Any, Optional
from backend.services.openclaw_skills_service import OpenClawSkillsService
from backend.services.claude_skills_service import ClaudeSkillsService

router = APIRouter()


@router.get(
    "/skills",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get all skills (OpenClaw + Claude)",
    description="Returns all available skills: OpenClaw CLI tools + Claude Code project skills",
)
async def get_all_skills(
    skill_type: Optional[str] = Query(None, description="Filter by type: 'cli', 'project', or None for all")
) -> Dict[str, Any]:
    """
    Get all skills - merges OpenClaw CLI skills with Claude Code project skills

    Args:
        skill_type: Optional filter - 'cli' for OpenClaw tools, 'project' for Claude skills, None for all

    Returns:
        {
            "total": int,
            "ready": int,
            "cli_total": int,
            "cli_ready": int,
            "project_total": int,
            "project_ready": int,
            "skills": [
                {
                    "name": str,
                    "description": str,
                    "type": "cli" | "project",
                    "eligible": bool,
                    "package": str,
                    "source": str,
                    ...
                }
            ]
        }
    """
    # Get OpenClaw CLI skills
    openclaw_data = OpenClawSkillsService.get_all_skills()
    cli_skills = openclaw_data.get("skills", [])

    # Add type field to CLI skills
    for skill in cli_skills:
        skill["type"] = "cli"

    # Get Claude Code project skills
    claude_service = ClaudeSkillsService()
    claude_data = claude_service.get_all_skills()
    project_skills = claude_data.get("skills", [])

    # Merge skills
    all_skills = cli_skills + project_skills

    # Apply filter if requested
    if skill_type:
        all_skills = [s for s in all_skills if s.get("type") == skill_type]

    # Calculate totals
    total = len(all_skills)
    ready = sum(1 for s in all_skills if s.get("eligible", False))

    return {
        "total": total,
        "ready": ready,
        "cli_total": openclaw_data.get("total", 0),
        "cli_ready": openclaw_data.get("ready", 0),
        "project_total": claude_data.get("total", 0),
        "project_ready": claude_data.get("ready", 0),
        "skills": all_skills
    }


@router.get(
    "/skills/ready",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Get ready skills",
    description="Returns only skills that are ready (installed and available)",
)
async def get_ready_skills() -> List[Dict[str, Any]]:
    """
    Get skills that are ready to use

    Returns:
        List of skill dicts where eligible=true
    """
    return OpenClawSkillsService.get_ready_skills()


@router.get(
    "/skills/missing",
    response_model=List[Dict[str, Any]],
    status_code=status.HTTP_200_OK,
    summary="Get missing skills",
    description="Returns skills that are not installed or have missing dependencies",
)
async def get_missing_skills() -> List[Dict[str, Any]]:
    """
    Get skills that are missing dependencies

    Returns:
        List of skill dicts where eligible=false
    """
    return OpenClawSkillsService.get_missing_skills()


@router.get(
    "/skills/{skill_name}",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get specific skill by name",
    description="Returns details for a specific skill (searches both OpenClaw and Claude skills)",
)
async def get_skill_by_name(skill_name: str) -> Dict[str, Any]:
    """
    Get a specific skill by name

    Args:
        skill_name: Name of the skill (e.g., 'github', 'apple-notes', 'git-workflow')

    Returns:
        Skill dict with added 'type' field ('cli' or 'project')

    Raises:
        404 if skill not found
    """
    # Try OpenClaw CLI skills first
    skill = OpenClawSkillsService.get_skill_by_name(skill_name)

    if skill:
        skill["type"] = "cli"
        return skill

    # Try Claude Code project skills
    claude_service = ClaudeSkillsService()
    skill = claude_service.get_skill_by_name(skill_name)

    if skill:
        return skill  # Already has type="project"

    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Skill '{skill_name}' not found in OpenClaw or Claude skills"
    )
