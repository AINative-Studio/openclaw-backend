"""
OpenClaw Skills Service

Exposes OpenClaw skills (bundled agent capabilities) to the API.
Uses subprocess to call `openclaw skills list --json` for programmatic access.
"""

import json
import subprocess
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class OpenClawSkillsService:
    """Service for retrieving OpenClaw skills"""

    @staticmethod
    def get_all_skills() -> Dict[str, Any]:
        """
        Get all available OpenClaw skills by calling `openclaw skills list --json`

        Returns:
            Dict with 'total', 'ready', 'skills' list
        """
        try:
            result = subprocess.run(
                ["openclaw", "skills", "list", "--json"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode == 0:
                skills_data = json.loads(result.stdout)
                skills = skills_data.get("skills", [])

                # Count eligible (ready) skills
                ready_count = sum(1 for s in skills if s.get("eligible", False))

                return {
                    "total": len(skills),
                    "ready": ready_count,
                    "skills": skills
                }
            else:
                logger.error(f"openclaw skills list failed: {result.stderr}")
                return {
                    "total": 0,
                    "ready": 0,
                    "skills": []
                }

        except subprocess.TimeoutExpired:
            logger.error("openclaw skills list timed out")
            return {"total": 0, "ready": 0, "skills": []}
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse skills JSON: {e}")
            return {"total": 0, "ready": 0, "skills": []}
        except Exception as e:
            logger.error(f"Error getting skills: {e}")
            return {"total": 0, "ready": 0, "skills": []}

    @staticmethod
    def get_skill_by_name(skill_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific skill by name

        Args:
            skill_name: Skill name (e.g., 'github', 'apple-notes')

        Returns:
            Skill dict or None if not found
        """
        skills_data = OpenClawSkillsService.get_all_skills()

        for skill in skills_data.get("skills", []):
            if skill.get("name") == skill_name:
                return skill

        return None

    @staticmethod
    def get_ready_skills() -> List[Dict[str, Any]]:
        """
        Get only skills that are ready (installed and available)

        Returns:
            List of ready skill dicts
        """
        skills_data = OpenClawSkillsService.get_all_skills()
        return [
            skill for skill in skills_data.get("skills", [])
            if skill.get("eligible", False)
        ]

    @staticmethod
    def get_missing_skills() -> List[Dict[str, Any]]:
        """
        Get skills that are missing (not installed)

        Returns:
            List of missing skill dicts
        """
        skills_data = OpenClawSkillsService.get_all_skills()
        return [
            skill for skill in skills_data.get("skills", [])
            if not skill.get("eligible", False)
        ]
