"""
Personality Loader

Loads and parses markdown-based personality files for agents.
Each agent has 8 personality files that define their behavior:
- SOUL.md: Core ethics and personality
- AGENTS.md: Multi-agent collaboration rules
- TOOLS.md: Tool usage patterns and preferences
- IDENTITY.md: Agent identity and role
- USER.md: User interaction patterns
- BOOTSTRAP.md: Initial setup and configuration
- HEARTBEAT.md: Health monitoring and self-awareness
- MEMORY.md: Curated long-term memory

SECURITY: Uses path validation to prevent directory traversal attacks (Issue #129).
"""

import os
from pathlib import Path
from typing import Dict, Optional
from pydantic import BaseModel, Field

from backend.utils.file_security import (
    validate_file_path,
    sanitize_filename,
    PathTraversalError,
    InvalidFilenameError,
)


class PersonalityFile(BaseModel):
    """Represents a single personality markdown file"""
    name: str = Field(..., description="File name (e.g., 'SOUL.md')")
    content: str = Field(..., description="Markdown content")
    last_modified: Optional[float] = Field(None, description="Unix timestamp of last modification")

    @property
    def file_type(self) -> str:
        """Extract personality type from filename (e.g., 'SOUL' from 'SOUL.md')"""
        return self.name.replace('.md', '')


class PersonalitySet(BaseModel):
    """Complete set of 8 personality files for an agent"""
    agent_id: str = Field(..., description="Agent UUID")
    soul: Optional[PersonalityFile] = Field(None, description="Core ethics and personality")
    agents: Optional[PersonalityFile] = Field(None, description="Multi-agent collaboration")
    tools: Optional[PersonalityFile] = Field(None, description="Tool usage patterns")
    identity: Optional[PersonalityFile] = Field(None, description="Agent identity")
    user: Optional[PersonalityFile] = Field(None, description="User interaction patterns")
    bootstrap: Optional[PersonalityFile] = Field(None, description="Initial setup")
    heartbeat: Optional[PersonalityFile] = Field(None, description="Health monitoring")
    memory: Optional[PersonalityFile] = Field(None, description="Curated memory")

    def get_all_files(self) -> Dict[str, PersonalityFile]:
        """Get all personality files as dict"""
        return {
            'soul': self.soul,
            'agents': self.agents,
            'tools': self.tools,
            'identity': self.identity,
            'user': self.user,
            'bootstrap': self.bootstrap,
            'heartbeat': self.heartbeat,
            'memory': self.memory,
        }

    def get_missing_files(self) -> list[str]:
        """Get list of missing personality files"""
        return [name for name, file in self.get_all_files().items() if file is None]


class PersonalityLoader:
    """
    Loads personality files from filesystem.

    Default structure:
    /personalities/
        {agent_id}/
            SOUL.md
            AGENTS.md
            TOOLS.md
            IDENTITY.md
            USER.md
            BOOTSTRAP.md
            HEARTBEAT.md
            MEMORY.md
    """

    PERSONALITY_FILES = [
        "SOUL.md",
        "AGENTS.md",
        "TOOLS.md",
        "IDENTITY.md",
        "USER.md",
        "BOOTSTRAP.md",
        "HEARTBEAT.md",
        "MEMORY.md",
    ]

    def __init__(self, base_path: str = "/tmp/openclaw_personalities"):
        """
        Initialize loader

        Args:
            base_path: Root directory for personality files
        """
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def get_agent_path(self, agent_id: str) -> Path:
        """
        Get personality directory for specific agent.

        Args:
            agent_id: Agent UUID (sanitized to prevent path traversal)

        Returns:
            Path to agent's personality directory

        Raises:
            InvalidFilenameError: If agent_id contains invalid characters
            PathTraversalError: If path traversal is detected
        """
        # SECURITY: Sanitize agent_id to prevent path traversal
        try:
            safe_agent_id = sanitize_filename(agent_id)
        except InvalidFilenameError as e:
            raise InvalidFilenameError(f"Invalid agent_id: {e}")

        agent_path = (self.base_path / safe_agent_id).resolve()

        # Ensure path is within base_path (defense in depth)
        try:
            agent_path.relative_to(self.base_path.resolve())
        except ValueError:
            raise PathTraversalError(
                f"Path traversal detected: agent_id '{agent_id}' resolves outside base directory"
            )

        return agent_path

    def load_personality_set(self, agent_id: str) -> PersonalitySet:
        """
        Load complete personality set for an agent

        Args:
            agent_id: Agent UUID

        Returns:
            PersonalitySet with all available files
        """
        agent_path = self.get_agent_path(agent_id)

        if not agent_path.exists():
            return PersonalitySet(agent_id=agent_id)

        personality_set = PersonalitySet(agent_id=agent_id)

        for filename in self.PERSONALITY_FILES:
            file_path = agent_path / filename
            if file_path.exists():
                content = file_path.read_text(encoding='utf-8')
                stat = file_path.stat()

                personality_file = PersonalityFile(
                    name=filename,
                    content=content,
                    last_modified=stat.st_mtime
                )

                # Map to appropriate field
                file_type = filename.replace('.md', '').lower()
                setattr(personality_set, file_type, personality_file)

        return personality_set

    def load_single_file(self, agent_id: str, filename: str) -> Optional[PersonalityFile]:
        """
        Load a single personality file

        Args:
            agent_id: Agent UUID
            filename: Name of file (e.g., 'SOUL.md')

        Returns:
            PersonalityFile or None if not found

        Raises:
            InvalidFilenameError: If filename is invalid
            PathTraversalError: If path traversal is detected
        """
        # SECURITY: Validate filename is in allowed list
        if filename not in self.PERSONALITY_FILES:
            raise InvalidFilenameError(
                f"Invalid personality file: {filename}. Must be one of {self.PERSONALITY_FILES}"
            )

        agent_path = self.get_agent_path(agent_id)

        # SECURITY: Use validate_file_path for additional protection
        try:
            file_path = validate_file_path(
                base_dir=agent_path,
                user_path=filename,
                allowed_extensions={'.md'},
                allow_create=False
            )
        except (PathTraversalError, InvalidFilenameError, FileNotFoundError):
            # File doesn't exist or path is invalid
            return None

        content = file_path.read_text(encoding='utf-8')
        stat = file_path.stat()

        return PersonalityFile(
            name=filename,
            content=content,
            last_modified=stat.st_mtime
        )

    def save_personality_file(
        self,
        agent_id: str,
        filename: str,
        content: str
    ) -> PersonalityFile:
        """
        Save or update a personality file

        Args:
            agent_id: Agent UUID
            filename: Name of file (e.g., 'SOUL.md')
            content: Markdown content

        Returns:
            Updated PersonalityFile

        Raises:
            InvalidFilenameError: If filename is invalid
            PathTraversalError: If path traversal is detected
        """
        # SECURITY: Validate filename is in allowed list
        if filename not in self.PERSONALITY_FILES:
            raise InvalidFilenameError(
                f"Invalid personality file: {filename}. Must be one of {self.PERSONALITY_FILES}"
            )

        agent_path = self.get_agent_path(agent_id)
        agent_path.mkdir(parents=True, exist_ok=True)

        # SECURITY: Use validate_file_path to ensure safe write
        file_path = validate_file_path(
            base_dir=agent_path,
            user_path=filename,
            allowed_extensions={'.md'},
            allow_create=True
        )

        file_path.write_text(content, encoding='utf-8')

        # Set restrictive permissions (owner read/write only)
        import os
        os.chmod(file_path, 0o600)

        stat = file_path.stat()

        return PersonalityFile(
            name=filename,
            content=content,
            last_modified=stat.st_mtime
        )

    def delete_personality_file(self, agent_id: str, filename: str) -> bool:
        """
        Delete a personality file

        Args:
            agent_id: Agent UUID
            filename: Name of file

        Returns:
            True if deleted, False if not found
        """
        agent_path = self.get_agent_path(agent_id)
        file_path = agent_path / filename

        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def delete_agent_personality(self, agent_id: str) -> int:
        """
        Delete all personality files for an agent

        Args:
            agent_id: Agent UUID

        Returns:
            Number of files deleted
        """
        agent_path = self.get_agent_path(agent_id)

        if not agent_path.exists():
            return 0

        count = 0
        for file_path in agent_path.iterdir():
            if file_path.is_file() and file_path.suffix == '.md':
                file_path.unlink()
                count += 1

        # Remove directory if empty
        if not any(agent_path.iterdir()):
            agent_path.rmdir()

        return count
