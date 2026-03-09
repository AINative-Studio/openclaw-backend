"""
Claude Skills Service

Reads project-specific skills from .claude/skills/ directory
and .ainative/ directory, parses SKILL.md frontmatter.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class ClaudeSkillsService:
    """Service for retrieving Claude Code project skills"""

    def __init__(self, project_root: Optional[str] = None):
        """
        Initialize with project root directory

        Args:
            project_root: Path to project root (defaults to backend parent dir)
        """
        if project_root is None:
            # Default to parent of backend directory
            backend_dir = Path(__file__).parent.parent
            self.project_root = backend_dir.parent
        else:
            self.project_root = Path(project_root)

        self.claude_skills_dir = self.project_root / ".claude" / "skills"
        self.ainative_skills_dir = self.project_root / ".ainative"

    @staticmethod
    def parse_frontmatter(content: str) -> Dict[str, Any]:
        """
        Parse YAML frontmatter from markdown file

        Args:
            content: File content with frontmatter

        Returns:
            Dict with frontmatter fields
        """
        # Match YAML frontmatter between --- delimiters
        match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
        if not match:
            return {}

        frontmatter = {}
        yaml_content = match.group(1)

        # Simple YAML parser (handles name, description, location)
        current_key = None
        current_value = []

        for line in yaml_content.split('\n'):
            # Key: value format
            if ':' in line and not line.startswith(' '):
                if current_key:
                    frontmatter[current_key] = '\n'.join(current_value).strip()
                    current_value = []

                key, value = line.split(':', 1)
                current_key = key.strip()
                value = value.strip()

                # Handle multi-line values (|)
                if value == '|':
                    current_value = []
                elif value:
                    current_value = [value]
            else:
                # Continuation line
                current_value.append(line.strip())

        # Add last key
        if current_key:
            frontmatter[current_key] = '\n'.join(current_value).strip()

        return frontmatter

    def get_skill_files(self) -> List[Path]:
        """
        Find all skill files in .claude/skills/ and .ainative/

        Returns:
            List of Path objects to skill markdown files
        """
        skill_files = []

        # Check .claude/skills/ directory
        if self.claude_skills_dir.exists():
            # Find all SKILL.md files in subdirectories
            skill_files.extend(self.claude_skills_dir.glob("*/SKILL.md"))

            # Find standalone .md files (not in subdirectories)
            for item in self.claude_skills_dir.iterdir():
                if item.is_file() and item.suffix == '.md':
                    skill_files.append(item)

        # NOTE: .ainative/ directory contains general documentation, not skills
        # Commenting out to avoid parsing non-skill markdown files
        # if self.ainative_skills_dir.exists():
        #     skill_files.extend(self.ainative_skills_dir.glob("*.md"))

        return skill_files

    def get_all_skills(self) -> Dict[str, Any]:
        """
        Get all Claude Code project skills

        Returns:
            Dict with 'total', 'ready', 'skills' list
        """
        try:
            skill_files = self.get_skill_files()
            skills = []

            for skill_file in skill_files:
                try:
                    content = skill_file.read_text(encoding='utf-8')
                    frontmatter = self.parse_frontmatter(content)

                    if not frontmatter:
                        logger.warning(f"No frontmatter found in {skill_file}")
                        continue

                    # Derive skill name from frontmatter or filename
                    skill_name = frontmatter.get('name')
                    if not skill_name:
                        # Use filename without extension
                        if skill_file.name == 'SKILL.md':
                            skill_name = skill_file.parent.name
                        else:
                            skill_name = skill_file.stem

                    skill = {
                        "name": skill_name,
                        "description": frontmatter.get('description', ''),
                        "type": "project",  # Distinguish from CLI skills
                        "eligible": True,  # Project skills are always available
                        "package": "project",
                        "source": "claude-code",
                        "path": str(skill_file.relative_to(self.project_root)),
                        "location": frontmatter.get('location', 'project'),
                    }

                    skills.append(skill)

                except Exception as e:
                    logger.error(f"Error parsing skill file {skill_file}: {e}")
                    continue

            return {
                "total": len(skills),
                "ready": len(skills),  # All project skills are ready
                "skills": skills
            }

        except Exception as e:
            logger.error(f"Error getting Claude skills: {e}")
            return {"total": 0, "ready": 0, "skills": []}

    def get_skill_by_name(self, skill_name: str) -> Optional[Dict[str, Any]]:
        """
        Get a specific skill by name

        Args:
            skill_name: Skill name

        Returns:
            Skill dict or None if not found
        """
        skills_data = self.get_all_skills()

        for skill in skills_data.get("skills", []):
            if skill.get("name") == skill_name:
                return skill

        return None
