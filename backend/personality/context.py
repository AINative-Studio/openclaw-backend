"""
Personality Context Injection

Builds personality context for LLM prompts by combining personality files
into a coherent system message that shapes agent behavior.
"""

from typing import Optional, List
from .loader import PersonalitySet, PersonalityFile


class PersonalityContext:
    """
    Builds context strings from personality files for injection into LLM prompts
    """

    @staticmethod
    def build_system_context(personality_set: PersonalitySet) -> str:
        """
        Build complete system context from personality files

        Args:
            personality_set: Complete set of personality files

        Returns:
            Formatted context string for LLM system message
        """
        sections = []

        # Start with identity
        if personality_set.identity:
            sections.append(PersonalityContext._format_section(
                "Identity",
                personality_set.identity.content
            ))

        # Add soul (core personality)
        if personality_set.soul:
            sections.append(PersonalityContext._format_section(
                "Core Personality & Ethics",
                personality_set.soul.content
            ))

        # Add user interaction patterns
        if personality_set.user:
            sections.append(PersonalityContext._format_section(
                "User Interaction Guidelines",
                personality_set.user.content
            ))

        # Add tool usage patterns
        if personality_set.tools:
            sections.append(PersonalityContext._format_section(
                "Tool Usage Guidelines",
                personality_set.tools.content
            ))

        # Add collaboration patterns
        if personality_set.agents:
            sections.append(PersonalityContext._format_section(
                "Multi-Agent Collaboration",
                personality_set.agents.content
            ))

        # Add curated memory
        if personality_set.memory:
            sections.append(PersonalityContext._format_section(
                "Long-Term Memory",
                personality_set.memory.content
            ))

        if not sections:
            return "# Agent Personality\nNo personality files configured."

        return "\n\n".join(sections)

    @staticmethod
    def build_task_context(
        personality_set: PersonalitySet,
        task_description: str
    ) -> str:
        """
        Build task-specific context including relevant personality aspects

        Args:
            personality_set: Complete personality set
            task_description: Description of current task

        Returns:
            Formatted context for task execution
        """
        sections = []

        # Always include identity
        if personality_set.identity:
            sections.append(PersonalityContext._format_section(
                "Your Identity",
                personality_set.identity.content,
                compact=True
            ))

        # Include soul for ethical guidance
        if personality_set.soul:
            sections.append(PersonalityContext._format_section(
                "Your Core Ethics",
                personality_set.soul.content,
                compact=True
            ))

        # Include tool guidelines if task involves tool usage
        if "tool" in task_description.lower() or "execute" in task_description.lower():
            if personality_set.tools:
                sections.append(PersonalityContext._format_section(
                    "Tool Usage Guidelines",
                    personality_set.tools.content,
                    compact=True
                ))

        # Include collaboration guidelines if multi-agent task
        if "agent" in task_description.lower() or "collaborate" in task_description.lower():
            if personality_set.agents:
                sections.append(PersonalityContext._format_section(
                    "Collaboration Guidelines",
                    personality_set.agents.content,
                    compact=True
                ))

        # Add task description
        sections.append(f"## Current Task\n{task_description}")

        return "\n\n".join(sections)

    @staticmethod
    def build_minimal_context(personality_set: PersonalitySet) -> str:
        """
        Build minimal context with just identity and soul

        Args:
            personality_set: Complete personality set

        Returns:
            Minimal context string
        """
        sections = []

        if personality_set.identity:
            # Extract just the name and role
            identity_lines = personality_set.identity.content.split('\n')
            name_line = next((line for line in identity_lines if '**Name**:' in line), None)
            role_section = []
            in_role = False
            for line in identity_lines:
                if '## Role' in line:
                    in_role = True
                    continue
                if in_role and line.strip().startswith('##'):
                    break
                if in_role and line.strip():
                    role_section.append(line)

            if name_line or role_section:
                sections.append("# Your Identity\n" + (name_line or "") + "\n" + "\n".join(role_section))

        if personality_set.soul:
            # Extract just the core ethics
            soul_lines = personality_set.soul.content.split('\n')
            ethics_section = []
            in_ethics = False
            for line in soul_lines:
                if '## Core Ethics' in line:
                    in_ethics = True
                    ethics_section.append(line)
                    continue
                if in_ethics and line.strip().startswith('##'):
                    break
                if in_ethics:
                    ethics_section.append(line)

            if ethics_section:
                sections.append("\n".join(ethics_section))

        return "\n\n".join(sections) if sections else "# Agent\nAutonomous AI agent."

    @staticmethod
    def extract_key_learnings(personality_set: PersonalitySet) -> List[str]:
        """
        Extract key learnings from memory file

        Args:
            personality_set: Complete personality set

        Returns:
            List of learning strings
        """
        if not personality_set.memory:
            return []

        learnings = []
        content = personality_set.memory.content
        lines = content.split('\n')

        in_learnings = False
        for line in lines:
            if '## Key Learnings' in line:
                in_learnings = True
                continue
            if in_learnings and line.strip().startswith('##'):
                break
            if in_learnings and line.strip() and line.strip().startswith('-'):
                learnings.append(line.strip()[1:].strip())

        return learnings

    @staticmethod
    def _format_section(title: str, content: str, compact: bool = False) -> str:
        """
        Format a personality section

        Args:
            title: Section title
            content: Markdown content
            compact: If True, reduce to essential info only

        Returns:
            Formatted section
        """
        if compact:
            # Extract only the most important parts
            lines = content.split('\n')
            essential_lines = []
            skip_next = False

            for i, line in enumerate(lines):
                # Skip metadata lines
                if line.startswith('*Last updated:') or line.startswith('---'):
                    continue

                # Include headings and important bullet points
                if line.strip().startswith('#') or line.strip().startswith('-') or line.strip().startswith('###'):
                    # But skip sub-sections in compact mode
                    if compact and line.strip().startswith('###'):
                        if 'What Works' in line or 'What to Avoid' in line or 'Successful' in line:
                            essential_lines.append(line)
                    else:
                        essential_lines.append(line)
                elif line.strip() and not line.strip().startswith('*'):
                    # Include regular text paragraphs
                    essential_lines.append(line)

            content = '\n'.join(essential_lines[:50])  # Limit to 50 lines in compact mode

        return f"# {title}\n{content}"
