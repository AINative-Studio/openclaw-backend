"""
OpenClaw Skills API Endpoints

Expose OpenClaw skills to the frontend for display in the agent Skills tab.
"""

from fastapi import APIRouter, HTTPException, status
from typing import List, Dict, Any
from backend.services.openclaw_skills_service import OpenClawSkillsService

router = APIRouter()


@router.get(
    "/skills",
    response_model=Dict[str, Any],
    status_code=status.HTTP_200_OK,
    summary="Get all OpenClaw skills",
    description="Returns all available OpenClaw skills with their status (ready/missing)",
)
async def get_all_skills() -> Dict[str, Any]:
    """
    Get all OpenClaw skills

    Returns:
        {
            "total": int,
            "ready": int,
            "skills": [
                {
                    "name": str,
                    "description": str,
                    "emoji": str,
                    "eligible": bool,
                    "disabled": bool,
                    "source": str,
                    "homepage": str,
                    "missing": {
                        "bins": List[str],
                        "anyBins": List[str],
                        "env": List[str],
                        "config": List[str],
                        "os": List[str]
                    }
                }
            ]
        }
    """
    return OpenClawSkillsService.get_all_skills()


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
    description="Returns details for a specific skill",
)
async def get_skill_by_name(skill_name: str) -> Dict[str, Any]:
    """
    Get a specific skill by name

    Args:
        skill_name: Name of the skill (e.g., 'github', 'apple-notes')

    Returns:
        Skill dict

    Raises:
        404 if skill not found
    """
    skill = OpenClawSkillsService.get_skill_by_name(skill_name)

    if not skill:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill '{skill_name}' not found"
        )

    return skill
