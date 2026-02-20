"""
WireGuard Network Monitoring Service

Collects and analyzes WireGuard connection statistics including:
- Peer connection status and handshake timestamps
- Data transfer statistics (received/sent bytes)
- Connection health metrics and stale connection detection
- Network quality metrics aggregation

Refs #E1-S6
"""

import subprocess
import re
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from collections import deque

logger = logging.getLogger(__name__)


class WireGuardMonitoringService:
    """
    Service for monitoring WireGuard network connections

    Handles:
    - Stats collection from wg show command
    - Peer handshake tracking
    - Connection health detection
    - Network quality metrics
    - Historical metrics aggregation
    """

    def __init__(
        self,
        interface: str = 'wg0',
        stale_threshold_seconds: int = 300,  # 5 minutes default
        max_history_size: int = 100
    ):
        """
        Initialize WireGuard monitoring service

        Args:
            interface: WireGuard interface name to monitor
            stale_threshold_seconds: Seconds after which connection is considered stale
            max_history_size: Maximum number of historical metrics to retain
        """
        self.interface = interface
        self.stale_threshold_seconds = stale_threshold_seconds
        self.max_history_size = max_history_size
        self._metrics_history: deque = deque(maxlen=max_history_size)

    def collect_peer_stats(self) -> Dict[str, Any]:
        """
        Collect peer statistics from wg show command

        Returns:
            Dictionary containing peer count and detailed peer stats

        Raises:
            RuntimeError: If wg show command fails
        """
        try:
            # Execute wg show all command
            result = subprocess.run(
                ['wg', 'show', self.interface, 'all'],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Failed to execute wg show: {result.stderr}"
                )

            # Parse output
            peers = self._parse_wg_show_output(result.stdout)

            return {
                'peer_count': len(peers),
                'peers': peers,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }

        except subprocess.TimeoutExpired:
            raise RuntimeError("wg show command timed out")
        except FileNotFoundError:
            raise RuntimeError("wg command not found - ensure WireGuard is installed")
        except Exception as e:
            logger.error(f"Error collecting peer stats: {e}")
            raise

    def check_connection_health(self) -> Dict[str, Any]:
        """
        Check health of all peer connections

        Returns:
            Health status including healthy/stale peer counts
        """
        stats = self.collect_peer_stats()
        peers = stats['peers']

        if not peers:
            return {
                'status': 'unhealthy',
                'total_peers': 0,
                'healthy_peers': 0,
                'stale_peers': 0,
                'stale_peer_list': [],
                'timestamp': stats['timestamp']
            }

        healthy_count = 0
        stale_count = 0
        stale_peer_list = []

        for peer in peers:
            handshake_age = peer.get('latest_handshake_seconds', float('inf'))

            if handshake_age <= self.stale_threshold_seconds:
                healthy_count += 1
            else:
                stale_count += 1
                stale_peer_list.append(peer['public_key'])

        # Determine overall status
        if healthy_count == len(peers):
            status = 'healthy'
        elif healthy_count > 0:
            status = 'degraded'
        else:
            status = 'unhealthy'

        return {
            'status': status,
            'total_peers': len(peers),
            'healthy_peers': healthy_count,
            'stale_peers': stale_count,
            'stale_peer_list': stale_peer_list,
            'timestamp': stats['timestamp']
        }

    def calculate_network_quality(self) -> Dict[str, Any]:
        """
        Calculate network quality metrics from transfer statistics

        Returns:
            Quality metrics including total bytes transferred and active connections
        """
        stats = self.collect_peer_stats()
        peers = stats['peers']

        total_received = 0
        total_sent = 0
        active_connections = len(peers)

        for peer in peers:
            total_received += peer.get('received_bytes', 0)
            total_sent += peer.get('sent_bytes', 0)

        return {
            'total_received_bytes': total_received,
            'total_sent_bytes': total_sent,
            'active_connections': active_connections,
            'timestamp': stats['timestamp']
        }

    def collect_and_store_metrics(self) -> Dict[str, Any]:
        """
        Collect current metrics and store in history

        Returns:
            Current metrics snapshot
        """
        stats = self.collect_peer_stats()
        quality = self.calculate_network_quality()

        metric_snapshot = {
            'timestamp': stats['timestamp'],
            'peer_count': stats['peer_count'],
            'total_received_bytes': quality['total_received_bytes'],
            'total_sent_bytes': quality['total_sent_bytes'],
        }

        self._metrics_history.append(metric_snapshot)

        return metric_snapshot

    def get_metrics_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get historical metrics

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of historical metric snapshots
        """
        history = list(self._metrics_history)

        if limit:
            history = history[-limit:]

        return history

    def get_health_summary(self) -> Dict[str, Any]:
        """
        Get comprehensive health summary

        Returns:
            Complete health summary including interface info and metrics
        """
        health = self.check_connection_health()
        quality = self.calculate_network_quality()
        interface_info = self._get_interface_info()

        return {
            'status': health['status'],
            'interface': self.interface,
            'public_key': interface_info.get('public_key'),
            'listening_port': interface_info.get('listening_port'),
            'peer_count': health['total_peers'],
            'healthy_peers': health['healthy_peers'],
            'stale_peers': health['stale_peers'],
            'stale_peer_list': health['stale_peer_list'],
            'total_received_bytes': quality['total_received_bytes'],
            'total_sent_bytes': quality['total_sent_bytes'],
            'timestamp': health['timestamp']
        }

    def _parse_wg_show_output(self, output: str) -> List[Dict[str, Any]]:
        """
        Parse wg show all output into structured peer data

        Args:
            output: Raw wg show output

        Returns:
            List of peer dictionaries with parsed stats
        """
        peers = []
        current_peer = None

        for line in output.split('\n'):
            line = line.strip()

            if line.startswith('peer:'):
                # Save previous peer if exists
                if current_peer:
                    peers.append(current_peer)

                # Start new peer
                public_key = line.split(':', 1)[1].strip()
                current_peer = {
                    'public_key': public_key,
                    'endpoint': None,
                    'allowed_ips': [],
                    'latest_handshake_seconds': None,
                    'received_bytes': 0,
                    'sent_bytes': 0,
                    'persistent_keepalive': None
                }

            elif current_peer:
                if line.startswith('endpoint:'):
                    current_peer['endpoint'] = line.split(':', 1)[1].strip()

                elif line.startswith('allowed ips:'):
                    ips = line.split(':', 1)[1].strip()
                    current_peer['allowed_ips'] = [ip.strip() for ip in ips.split(',')]

                elif line.startswith('latest handshake:'):
                    timestamp_str = line.split(':', 1)[1].strip()
                    current_peer['latest_handshake_seconds'] = \
                        self._parse_handshake_timestamp(timestamp_str)

                elif line.startswith('transfer:'):
                    # Parse "X received, Y sent"
                    transfer_str = line.split(':', 1)[1].strip()
                    parts = transfer_str.split(',')

                    if len(parts) >= 2:
                        received_str = parts[0].strip().replace('received', '').strip()
                        sent_str = parts[1].strip().replace('sent', '').strip()

                        current_peer['received_bytes'] = \
                            self._parse_transfer_bytes(received_str)
                        current_peer['sent_bytes'] = \
                            self._parse_transfer_bytes(sent_str)

                elif line.startswith('persistent keepalive:'):
                    keepalive_str = line.split(':', 1)[1].strip()
                    current_peer['persistent_keepalive'] = keepalive_str

        # Don't forget the last peer
        if current_peer:
            peers.append(current_peer)

        return peers

    def _parse_handshake_timestamp(self, timestamp_str: str) -> int:
        """
        Parse handshake timestamp string to seconds

        Args:
            timestamp_str: String like "1 minute, 23 seconds ago"

        Returns:
            Total seconds since handshake
        """
        # Pattern: "X day(s), Y hour(s), Z minute(s), W second(s) ago"
        # Can also be shorter like "5 minutes ago" or "30 seconds ago"

        total_seconds = 0

        # Extract days
        day_match = re.search(r'(\d+)\s+day', timestamp_str)
        if day_match:
            total_seconds += int(day_match.group(1)) * 86400

        # Extract hours
        hour_match = re.search(r'(\d+)\s+hour', timestamp_str)
        if hour_match:
            total_seconds += int(hour_match.group(1)) * 3600

        # Extract minutes
        minute_match = re.search(r'(\d+)\s+minute', timestamp_str)
        if minute_match:
            total_seconds += int(minute_match.group(1)) * 60

        # Extract seconds
        second_match = re.search(r'(\d+)\s+second', timestamp_str)
        if second_match:
            total_seconds += int(second_match.group(1))

        return total_seconds

    def _parse_transfer_bytes(self, size_str: str) -> int:
        """
        Parse transfer size string to bytes

        Args:
            size_str: String like "50.25 MiB" or "1.50 GiB"

        Returns:
            Size in bytes
        """
        # Extract number and unit
        match = re.match(r'([\d.]+)\s*([KMGT]i?B)', size_str)

        if not match:
            return 0

        value = float(match.group(1))
        unit = match.group(2)

        # Convert to bytes
        multipliers = {
            'B': 1,
            'KiB': 1024,
            'MiB': 1024 ** 2,
            'GiB': 1024 ** 3,
            'TiB': 1024 ** 4,
            # Also support non-binary units
            'KB': 1000,
            'MB': 1000 ** 2,
            'GB': 1000 ** 3,
            'TB': 1000 ** 4,
        }

        multiplier = multipliers.get(unit, 1)
        return int(value * multiplier)

    def _get_interface_info(self) -> Dict[str, Any]:
        """
        Get WireGuard interface information

        Returns:
            Interface details (public key, listening port)
        """
        try:
            result = subprocess.run(
                ['wg', 'show', self.interface],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                return {}

            info = {}

            for line in result.stdout.split('\n'):
                line = line.strip()

                if line.startswith('public key:'):
                    info['public_key'] = line.split(':', 1)[1].strip()
                elif line.startswith('listening port:'):
                    port_str = line.split(':', 1)[1].strip()
                    info['listening_port'] = int(port_str) if port_str.isdigit() else None

            return info

        except Exception as e:
            logger.warning(f"Failed to get interface info: {e}")
            return {}
