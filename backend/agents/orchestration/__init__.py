"""
Claude Orchestration Layer for NousCoder Agents

This module provides the orchestration layer that ties together OpenClaw integration,
NousCoder agent spawning, and WhatsApp notifications into a 24/7 autonomous
development system.

Architecture:
- WhatsApp Message (@mention) -> OpenClaw Gateway -> Claude Orchestration Layer
- Claude Orchestrator -> NousCoder Agent Spawner -> GitHub Issue Work + PR Creation
- Status Updates -> WhatsApp via OpenClaw

Refs #1076
"""

from .command_parser import CommandParser, ParsedCommand, CommandType, CommandParseError
from .notification_service import NotificationService, NotificationType, NotificationError
from .claude_orchestrator import ClaudeOrchestrator, OrchestrationError, WorkflowState

__all__ = [
    # Command Parser
    "CommandParser",
    "ParsedCommand",
    "CommandType",
    "CommandParseError",
    # Notification Service
    "NotificationService",
    "NotificationType",
    "NotificationError",
    # Orchestrator
    "ClaudeOrchestrator",
    "OrchestrationError",
    "WorkflowState",
]
