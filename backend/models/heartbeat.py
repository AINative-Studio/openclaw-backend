"""
Heartbeat Models

Minimal stub models for peer state and events used by NodeCrashDetectionService.
These models provide a Python interface to DBOS heartbeat data.

Note: Actual heartbeat data is managed by OpenClaw Gateway (DBOS) in TypeScript.
See: openclaw-gateway/src/workflows/agent-lifecycle-workflow.ts
DBOS tables: dbos_agents, dbos_heartbeat_executions
"""

from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass


@dataclass
class PeerState:
    """
    Represents the current state of a peer node.

    Attributes:
        peer_id: Unique peer identifier
        status: Current peer status ("online", "offline", etc.)
        last_heartbeat: Timestamp of last received heartbeat
        metadata: Additional peer metadata
    """
    peer_id: str
    status: str
    last_heartbeat: datetime
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class PeerEvent:
    """
    Represents a peer state change event.

    Used for crash detection, status changes, and other peer-related events.

    Attributes:
        event_type: Type of event (e.g., "node_crashed", "node_online")
        peer_id: Peer that generated the event
        timestamp: When the event occurred
        previous_status: Status before the event
        current_status: Status after the event
        metadata: Additional event metadata
    """
    event_type: str
    peer_id: str
    timestamp: datetime
    previous_status: str
    current_status: str
    metadata: Optional[Dict[str, Any]] = None
