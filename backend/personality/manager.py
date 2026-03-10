"""
Personality Manager

High-level API for managing agent personalities.
Provides CRUD operations and business logic layer over PersonalityLoader.
"""

from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from .loader import PersonalityLoader, PersonalitySet, PersonalityFile


class PersonalityManager:
    """
    Manages agent personality files with high-level operations
    """

    def __init__(self, base_path: str = "/tmp/openclaw_personalities"):
        """
        Initialize manager

        Args:
            base_path: Root directory for personality files
        """
        self.loader = PersonalityLoader(base_path)

    def get_personality(self, agent_id: str) -> PersonalitySet:
        """
        Get complete personality set for agent

        Args:
            agent_id: Agent UUID

        Returns:
            PersonalitySet with all available files
        """
        return self.loader.load_personality_set(agent_id)

    def get_personality_file(self, agent_id: str, file_type: str) -> Optional[PersonalityFile]:
        """
        Get single personality file

        Args:
            agent_id: Agent UUID
            file_type: Type of file ('soul', 'agents', 'tools', etc.)

        Returns:
            PersonalityFile or None if not found
        """
        filename = f"{file_type.upper()}.md"
        return self.loader.load_single_file(agent_id, filename)

    def update_personality_file(
        self,
        agent_id: str,
        file_type: str,
        content: str
    ) -> PersonalityFile:
        """
        Update a personality file

        Args:
            agent_id: Agent UUID
            file_type: Type of file ('soul', 'agents', 'tools', etc.)
            content: New markdown content

        Returns:
            Updated PersonalityFile
        """
        filename = f"{file_type.upper()}.md"
        return self.loader.save_personality_file(agent_id, filename, content)

    def delete_personality_file(self, agent_id: str, file_type: str) -> bool:
        """
        Delete a personality file

        Args:
            agent_id: Agent UUID
            file_type: Type of file ('soul', 'agents', 'tools', etc.)

        Returns:
            True if deleted, False if not found
        """
        filename = f"{file_type.upper()}.md"
        return self.loader.delete_personality_file(agent_id, filename)

    def initialize_agent_personality(
        self,
        agent_id: str,
        agent_name: str,
        model: str = "claude-3-5-sonnet-20241022",
        persona: Optional[str] = None
    ) -> PersonalitySet:
        """
        Initialize personality files for a new agent with default templates

        Args:
            agent_id: Agent UUID
            agent_name: Human-readable agent name
            model: Claude model name
            persona: Optional persona description

        Returns:
            Initialized PersonalitySet
        """
        # Create default content for each file with current timestamp
        created_at = datetime.now().isoformat()
        templates = self._get_default_templates(
            agent_id=agent_id,
            agent_name=agent_name,
            model=model,
            persona=persona,
            created_at=created_at
        )

        # Save all templates
        for file_type, content in templates.items():
            filename = f"{file_type.upper()}.md"
            self.loader.save_personality_file(agent_id, filename, content)

        # Return complete set
        return self.loader.load_personality_set(agent_id)

    def _get_default_templates(
        self,
        agent_id: str,
        agent_name: str,
        model: str,
        persona: Optional[str],
        created_at: str
    ) -> Dict[str, str]:
        """
        Generate default personality templates by reading from template files
        and performing variable substitution

        Args:
            agent_id: Agent UUID
            agent_name: Agent name
            model: Model name
            persona: Optional persona description
            created_at: Creation timestamp in ISO format

        Returns:
            Dict of file_type -> content with variables substituted
        """
        # Get template directory path
        template_dir = Path(__file__).parent / "templates"

        # Define template mapping (file_type -> template_filename)
        template_files = {
            'soul': 'SOUL.md',
            'agents': 'AGENTS.md',
            'tools': 'TOOLS.md',
            'identity': 'IDENTITY.md',
            'user': 'USER.md',
            'bootstrap': 'BOOTSTRAP.md',
            'heartbeat': 'HEARTBEAT.md',
            'memory': 'MEMORY.md',
        }

        # Load and substitute variables in each template
        templates = {}
        for file_type, filename in template_files.items():
            template_path = template_dir / filename

            # Read template content
            if template_path.exists():
                content = template_path.read_text()

                # Perform variable substitution
                content = self._substitute_variables(
                    content=content,
                    agent_id=agent_id,
                    agent_name=agent_name,
                    model=model,
                    persona=persona,
                    created_at=created_at
                )

                templates[file_type] = content
            else:
                # Fallback to old inline template methods if file doesn't exist
                templates[file_type] = self._get_fallback_template(
                    file_type, agent_name, model, persona
                )

        return templates

    def _substitute_variables(
        self,
        content: str,
        agent_id: str,
        agent_name: str,
        model: str,
        persona: Optional[str],
        created_at: str
    ) -> str:
        """
        Substitute template variables with actual values

        Args:
            content: Template content with {{VARIABLE}} placeholders
            agent_id: Agent UUID
            agent_name: Agent name
            model: Model name
            persona: Optional persona description
            created_at: Creation timestamp

        Returns:
            Content with all variables substituted
        """
        # Replace variables
        content = content.replace("{{AGENT_NAME}}", agent_name)
        content = content.replace("{{AGENT_ID}}", agent_id)
        content = content.replace("{{MODEL}}", model)
        content = content.replace("{{CREATED_AT}}", created_at)

        # Handle persona specially - only substitute if provided
        if persona:
            content = content.replace("{{PERSONA}}", persona)
        else:
            # Remove persona placeholder if not provided
            content = content.replace("{{PERSONA}}", "")

        return content

    def _get_fallback_template(
        self,
        file_type: str,
        agent_name: str,
        model: str,
        persona: Optional[str]
    ) -> str:
        """
        Fallback template when template file doesn't exist

        This provides a minimal template if the template files are missing.
        In production, template files should always exist.

        Args:
            file_type: Type of template
            agent_name: Agent name
            model: Model name
            persona: Optional persona

        Returns:
            Minimal fallback template content
        """
        # Provide minimal fallback template
        persona_section = f"\n\n## Persona\n{persona}" if persona else ""

        return f"""# {agent_name} - {file_type.upper()}

## Notice
This is a fallback template. The template file `{file_type.upper()}.md` was not found.

## Agent Information
- **Agent Name**: {agent_name}
- **Model**: {model}
{persona_section}

## Purpose
*(This section should be populated from the proper template file)*

---
*Generated: Fallback template*
"""

    def delete_agent(self, agent_id: str) -> int:
        """
        Delete all personality files for an agent

        Args:
            agent_id: Agent UUID

        Returns:
            Number of files deleted
        """
        return self.loader.delete_agent_personality(agent_id)
