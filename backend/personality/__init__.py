"""
Personality System Module

Implements OpenClaw's personality architecture where agents have mutable,
evolving markdown-based personality files that shape their behavior and memory.

Key components:
- PersonalityLoader: Reads and parses .md personality files
- PersonalityManager: CRUD operations on personality files
- PersonalityContext: Injects personality into LLM prompts
"""

from .loader import PersonalityLoader
from .manager import PersonalityManager
from .context import PersonalityContext

__all__ = [
    "PersonalityLoader",
    "PersonalityManager",
    "PersonalityContext",
]
