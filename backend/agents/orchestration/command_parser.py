"""
Command Parser for Claude Orchestration Layer

Parses WhatsApp commands and converts them into structured ParsedCommand objects.

Supports both structured and natural language commands:
- Structured: "work on issue #1234" (regex, fast)
- Natural: "Can you fix bug 456 in core repo?" (LLM, smart)

Refs #1076, #1096
"""

import re
import os
import json
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)

from contextlib import contextmanager

try:
    from backend.services.datadog_service import get_datadog_service
except ImportError:
    get_datadog_service = None  # type: ignore[assignment]


@contextmanager
def _noop_ctx():
    yield


class CommandType(Enum):
    """Types of commands supported by the orchestrator"""
    WORK_ON_ISSUE = "work_on_issue"
    STATUS_CHECK = "status_check"
    STOP_WORK = "stop_work"
    LIST_AGENTS = "list_agents"


class CommandParseError(Exception):
    """Raised when command parsing fails"""
    pass


@dataclass
class ParsedCommand:
    """Parsed command with extracted parameters"""
    command_type: CommandType
    raw_command: str
    issue_number: Optional[int] = None
    repository: Optional[str] = None  # GitHub repository (owner/repo format)
    task_description: Optional[str] = None  # Additional context from natural language
    is_natural_language: bool = False  # True if parsed via LLM, False if regex

    def __repr__(self) -> str:
        parts = [self.command_type.value]
        if self.issue_number:
            parts.append(f"issue={self.issue_number}")
        if self.repository:
            parts.append(f"repo={self.repository}")
        if self.is_natural_language:
            parts.append("NL")
        return f"<ParsedCommand {' '.join(parts)}>"


class CommandParser:
    """
    Hybrid command parser supporting both regex patterns and natural language

    Examples:
        # Structured commands (fast regex path)
        parser = CommandParser()
        cmd = parser.parse("work on issue #123")
        # → WORK_ON_ISSUE, issue=123, is_natural_language=False

        # Natural language (LLM path)
        parser = CommandParser(use_llm=True, default_repository="AINative-Studio/core")
        cmd = await parser.parse_async("Can you fix bug 456 in core repo?")
        # → WORK_ON_ISSUE, issue=456, repo="AINative-Studio/core", is_natural_language=True
    """

    # Repository aliases for natural language
    REPO_ALIASES = {
        "core": "AINative-Studio/core",
        "website": "AINative-Studio/website",
        "backend": "AINative-Studio/core",
        "frontend": "AINative-Studio/website",
    }

    # Command patterns with regex
    PATTERNS = {
        # Work on issue: "work on issue #1234", "work on issue 1234"
        CommandType.WORK_ON_ISSUE: [
            r"work\s+on\s+issue\s+#?(\d+)",
            r"work\s+on\s+issue\s*#?(\S*)",  # Catch incomplete/invalid patterns
        ],
        # Status check: "status of issue #1234", "check status of issue #1234"
        CommandType.STATUS_CHECK: [
            r"(?:check\s+)?status\s+(?:of\s+)?issue\s+#?(\d+)",
            r"(?:check\s+)?status\s+(?:of\s+)?issue\s*#?(\S*)",  # Catch incomplete/invalid
        ],
        # Stop work: "stop work on issue #1234", "stop issue #1234", "cancel work on issue #1234"
        CommandType.STOP_WORK: [
            r"(?:stop|cancel)\s+(?:work\s+(?:on\s+)?)?issue\s+#?(\d+)",
            r"(?:stop|cancel)\s+(?:work\s+(?:on\s+)?)?issue\s*#?(\S*)",  # Catch incomplete/invalid
        ],
        # List agents: "list active agents", "list agents", "show agents"
        CommandType.LIST_AGENTS: [
            r"(?:list|show)\s+(?:active\s+)?agents",
        ],
    }

    def __init__(
        self,
        default_repository: Optional[str] = None,
        use_llm: bool = True,
        llm_model: str = "claude-3-5-haiku-20241022"
    ):
        """
        Initialize command parser

        Args:
            default_repository: Default repository when not specified in command
            use_llm: Enable LLM parsing for natural language (default: True)
            llm_model: Claude model for natural language parsing (Haiku is fast/cheap)
        """
        self.default_repository = default_repository or os.getenv(
            "GITHUB_DEFAULT_REPO",
            "AINative-Studio/core"
        )
        self.use_llm = use_llm
        self.llm_model = llm_model
        self.client = None

        # Initialize Anthropic client if LLM parsing enabled
        if use_llm:
            try:
                from anthropic import Anthropic
                api_key = os.getenv("ANTHROPIC_API_KEY")
                if api_key:
                    self.client = Anthropic(api_key=api_key)
                    logger.info(f"CommandParser initialized with LLM support (model: {llm_model})")
                else:
                    logger.warning("ANTHROPIC_API_KEY not found - LLM parsing disabled")
                    self.use_llm = False
            except ImportError:
                logger.warning("anthropic package not installed - LLM parsing disabled")
                self.use_llm = False

    def parse(self, command: str) -> ParsedCommand:
        """
        Parse a command string into a structured ParsedCommand

        Args:
            command: Raw command string from WhatsApp

        Returns:
            ParsedCommand with type and extracted parameters

        Raises:
            CommandParseError: If command cannot be parsed
        """
        # Validate input
        if not command or not command.strip():
            raise CommandParseError("Command cannot be empty")

        # Normalize command (strip, lowercase for matching)
        normalized = command.strip().lower()
        raw_command = command.strip()

        # Try to match against known patterns
        for command_type, patterns in self.PATTERNS.items():
            for pattern in patterns:
                match = re.match(pattern, normalized)
                if match:
                    return self._build_command(
                        command_type=command_type,
                        raw_command=raw_command,
                        match=match
                    )

        # No pattern matched
        raise CommandParseError(
            f"Unknown command: '{raw_command}'. "
            f"Supported commands: work on issue #N, status of issue #N, "
            f"stop work on issue #N, list agents"
        )

    def _build_command(
        self,
        command_type: CommandType,
        raw_command: str,
        match: re.Match
    ) -> ParsedCommand:
        """
        Build ParsedCommand from regex match

        Args:
            command_type: Type of command matched
            raw_command: Original command string
            match: Regex match object

        Returns:
            ParsedCommand instance

        Raises:
            CommandParseError: If issue number is invalid
        """
        # Extract issue number if present in match groups
        issue_number = None
        if match.groups():
            issue_str = match.group(1)
            try:
                issue_number = int(issue_str)
                # Validate issue number is positive
                if issue_number <= 0:
                    raise ValueError("Issue number must be positive")
            except ValueError:
                raise CommandParseError(
                    f"Invalid issue number: '{issue_str}'. "
                    f"Issue numbers must be positive integers"
                )

        # Validate that issue-based commands have issue numbers
        requires_issue = command_type in [
            CommandType.WORK_ON_ISSUE,
            CommandType.STATUS_CHECK,
            CommandType.STOP_WORK,
        ]

        if requires_issue and issue_number is None:
            raise CommandParseError(
                f"Command '{raw_command}' requires an issue number"
            )

        return ParsedCommand(
            command_type=command_type,
            raw_command=raw_command,
            issue_number=issue_number,
            repository=self.default_repository,  # Use default repository
            is_natural_language=False  # Regex parsed
        )

    async def parse_async(self, command: str) -> ParsedCommand:
        """
        Parse command with LLM fallback (async version)

        Tries regex first (fast path), then falls back to LLM for natural language.

        Args:
            command: Raw command string

        Returns:
            ParsedCommand with extracted parameters

        Raises:
            CommandParseError: If command cannot be parsed
        """
        # Try regex first (fast, free)
        try:
            return self.parse(command)
        except CommandParseError:
            pass

        # Fall back to LLM (smart, costs ~$0.0001)
        if self.use_llm and self.client:
            try:
                return await self._parse_llm(command)
            except Exception as e:
                logger.error(f"LLM parsing failed: {e}")
                raise CommandParseError(f"Could not parse command: {command}")

        # No LLM available
        raise CommandParseError(
            f"Command not recognized and LLM parsing unavailable: {command}"
        )

    async def _parse_llm(self, command: str) -> ParsedCommand:
        """
        Use Claude Haiku to extract structured information from natural language

        Args:
            command: Natural language command

        Returns:
            ParsedCommand with extracted information

        Raises:
            CommandParseError: If LLM cannot extract valid command
        """
        system_prompt = f"""You are a command parser for a GitHub automation system that controls coding agents.

Extract structured information from user messages and return JSON.

COMMAND TYPES:
- work_on_issue: User wants agent to work on a GitHub issue
- status_check: User wants status of issue work
- stop_work: User wants to stop work on an issue
- list_agents: User wants to see active agents
- not_a_command: Message is casual conversation, not a command

REPOSITORIES:
- "core" or "backend" → AINative-Studio/core
- "website" or "frontend" → AINative-Studio/website
- Default if not mentioned: {self.default_repository}

RETURN JSON FORMAT:
{{
  "command_type": "work_on_issue" | "status_check" | "stop_work" | "list_agents" | "not_a_command",
  "issue_number": 123 | null,
  "repository": "AINative-Studio/core" | "AINative-Studio/website" | null,
  "task_description": "brief context" | null,
  "confidence": 0.0-1.0
}}

EXAMPLES:
"Can you work on issue 123 in core?" → {{"command_type": "work_on_issue", "issue_number": 123, "repository": "AINative-Studio/core", "confidence": 0.95}}
"Fix bug 456" → {{"command_type": "work_on_issue", "issue_number": 456, "repository": null, "confidence": 0.9}}
"What's the status of issue 789?" → {{"command_type": "status_check", "issue_number": 789, "repository": null, "confidence": 0.95}}
"How are you?" → {{"command_type": "not_a_command", "confidence": 0.99}}

Return ONLY valid JSON, no other text."""

        dd = get_datadog_service() if get_datadog_service else None
        try:
            with (dd.workflow_span("command_parse_llm") if dd else _noop_ctx()):
                response = self.client.messages.create(
                    model=self.llm_model,
                    max_tokens=200,
                    system=system_prompt,
                    messages=[{"role": "user", "content": command}]
                )

            # Parse JSON response
            result = json.loads(response.content[0].text)
            logger.info(f"LLM parsed command: {result}")

            if dd:
                dd.annotate_span(
                    input_data=command,
                    output_data=json.dumps(result),
                )

            # Handle non-commands
            if result.get("command_type") == "not_a_command":
                raise CommandParseError(
                    f"Message is not a command (appears to be casual conversation): {command}"
                )

            # Validate command type
            try:
                command_type = CommandType(result["command_type"])
            except (KeyError, ValueError):
                raise CommandParseError(
                    f"LLM returned invalid command type: {result.get('command_type')}"
                )

            # Extract issue number
            issue_number = result.get("issue_number")
            if issue_number is not None:
                try:
                    issue_number = int(issue_number)
                    if issue_number <= 0:
                        raise ValueError("Issue number must be positive")
                except (ValueError, TypeError):
                    raise CommandParseError(f"Invalid issue number: {issue_number}")

            # Resolve repository (use alias or default)
            repository = result.get("repository")
            if not repository or repository.lower() == "null":
                repository = self.default_repository
            elif repository.lower() in self.REPO_ALIASES:
                repository = self.REPO_ALIASES[repository.lower()]

            # Get task description
            task_description = result.get("task_description")

            return ParsedCommand(
                command_type=command_type,
                raw_command=command,
                issue_number=issue_number,
                repository=repository,
                task_description=task_description,
                is_natural_language=True
            )

        except json.JSONDecodeError as e:
            logger.error(f"LLM returned invalid JSON: {response.content[0].text}")
            raise CommandParseError(f"LLM parsing failed: invalid JSON response")
        except Exception as e:
            logger.error(f"LLM parsing error: {e}")
            raise
