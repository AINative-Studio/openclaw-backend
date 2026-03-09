"""
OpenClaw Skills Service

Exposes OpenClaw skills (bundled agent capabilities) to the API.
Uses subprocess to call `openclaw skills list --json` for programmatic access.
"""

import json
import subprocess
from typing import List, Dict, Any, Optional
import logging
import time

logger = logging.getLogger(__name__)

# Cache for skills to avoid repeated expensive openclaw calls
_skills_cache: Optional[Dict[str, Any]] = None
_cache_timestamp: float = 0
CACHE_TTL_SECONDS = 60  # Cache for 1 minute


class OpenClawSkillsService:
    """Service for retrieving OpenClaw skills"""

    @staticmethod
    def get_all_skills() -> Dict[str, Any]:
        """
        Get all available OpenClaw skills by calling `openclaw skills list --json`
        Uses in-memory cache to avoid repeated expensive subprocess calls.

        Returns:
            Dict with 'total', 'ready', 'skills' list
        """
        global _skills_cache, _cache_timestamp

        # Return cached data if still valid
        current_time = time.time()
        if _skills_cache is not None and (current_time - _cache_timestamp) < CACHE_TTL_SECONDS:
            logger.debug(f"Returning cached skills (age: {current_time - _cache_timestamp:.1f}s)")
            return _skills_cache

        try:
            import os
            # Ensure GOPATH/bin is in PATH for Go-installed skill binaries
            env = os.environ.copy()
            gopath = os.path.expanduser("~/go/bin")
            homebrew_bin = "/opt/homebrew/bin"

            # Add Go and Homebrew paths if not already present
            if gopath not in env.get("PATH", ""):
                env["PATH"] = f"{env.get('PATH', '')}:{gopath}"
            if homebrew_bin not in env.get("PATH", ""):
                env["PATH"] = f"{env.get('PATH', '')}:{homebrew_bin}"

            # Use shell=True with full command to ensure PATH is available
            result = subprocess.run(
                "which openclaw > /dev/null && openclaw skills list --json",
                shell=True,
                capture_output=True,
                text=True,
                timeout=5,  # Reduced to 5s - fail fast if OpenClaw is unresponsive
                executable="/bin/zsh",  # Use zsh which loads user PATH
                env=env  # Pass modified environment with Go/Homebrew paths
            )

            if result.returncode == 0:
                # openclaw outputs Doctor UI followed by JSON
                # Find where JSON starts (first line beginning with '{')
                lines = result.stdout.split('\n')
                json_start_idx = None
                for i, line in enumerate(lines):
                    if line.strip().startswith('{'):
                        json_start_idx = i
                        break

                if json_start_idx is None:
                    logger.error("Could not find JSON in openclaw output")
                    return {"total": 0, "ready": 0, "skills": []}

                json_output = '\n'.join(lines[json_start_idx:])
                skills_data = json.loads(json_output)
                skills = skills_data.get("skills", [])

                # Count eligible (ready) skills
                ready_count = sum(1 for s in skills if s.get("eligible", False))

                result_data = {
                    "total": len(skills),
                    "ready": ready_count,
                    "skills": skills
                }

                # Cache successful result
                _skills_cache = result_data
                _cache_timestamp = current_time
                logger.info(f"Cached {len(skills)} skills from OpenClaw CLI")

                return result_data
            else:
                logger.error(f"openclaw skills list failed: {result.stderr}")
                # Return empty but don't cache failures
                return {
                    "total": 0,
                    "ready": 0,
                    "skills": []
                }

        except subprocess.TimeoutExpired:
            logger.error("openclaw skills list timed out after 5s")
            # Return empty but don't cache timeout
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
