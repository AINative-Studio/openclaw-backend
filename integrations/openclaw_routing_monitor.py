#!/usr/bin/env python3
"""
OpenClaw Routing Monitor - Verify WhatsApp to Claude message routing

This script monitors and verifies that OpenClaw Gateway is properly routing
WhatsApp messages to the Claude agent for processing.

Refs #1074
"""
import subprocess
import json
import sys
from typing import Dict, List, Optional
from datetime import datetime


class OpenClawRoutingMonitor:
    """Monitor OpenClaw Gateway routing configuration and status"""

    def __init__(self):
        self.gateway_url = "ws://127.0.0.1:18789"
        self.whatsapp_group = "120363401780756402@g.us"

    def run_openclaw_command(self, command: List[str]) -> Dict:
        """
        Execute openclaw CLI command and parse output

        Args:
            command: List of command arguments

        Returns:
            Dict with command result
        """
        try:
            result = subprocess.run(
                ["openclaw"] + command,
                capture_output=True,
                text=True,
                timeout=10
            )
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "error": "Command timed out",
                "stdout": "",
                "stderr": "Timeout after 10 seconds"
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "stdout": "",
                "stderr": str(e)
            }

    def check_gateway_status(self) -> Dict:
        """
        Check if OpenClaw Gateway is running

        Returns:
            Dict with gateway status information
        """
        result = self.run_openclaw_command(["gateway", "status"])

        if not result["success"]:
            return {
                "running": False,
                "error": result.get("stderr", "Gateway not running")
            }

        stdout = result["stdout"]
        return {
            "running": "running" in stdout.lower(),
            "listening": "Listening:" in stdout,
            "port": "18789" if "18789" in stdout else None,
            "raw_output": stdout
        }

    def check_whatsapp_channel(self) -> Dict:
        """
        Check WhatsApp channel status

        Returns:
            Dict with WhatsApp channel information
        """
        result = self.run_openclaw_command(["channels", "status"])

        if not result["success"]:
            return {
                "connected": False,
                "error": result.get("stderr", "Could not check channel status")
            }

        stdout = result["stdout"]
        # Check for "connected" but not "disconnected"
        is_connected = ("connected" in stdout.lower() and
                       "disconnected" not in stdout.lower() and
                       "whatsapp" in stdout.lower())
        return {
            "connected": is_connected,
            "running": "running" in stdout.lower(),
            "enabled": "enabled" in stdout.lower(),
            "raw_output": stdout
        }

    def check_agent_sessions(self) -> Dict:
        """
        Check active agent sessions

        Returns:
            Dict with session information
        """
        result = self.run_openclaw_command(["status"])

        if not result["success"]:
            return {
                "active": False,
                "error": result.get("stderr", "Could not check sessions")
            }

        stdout = result["stdout"]
        return {
            "active": "sessions" in stdout.lower(),
            "has_whatsapp_session": "whatsapp" in stdout.lower(),
            "model": "claude-opus-4-5" if "claude-opus-4-5" in stdout else None,
            "raw_output": stdout
        }

    def verify_routing_configuration(self) -> Dict:
        """
        Verify that routing configuration is correct

        Returns:
            Dict with routing verification results
        """
        try:
            with open("/Users/aideveloper/.openclaw/openclaw.json", "r") as f:
                config = json.load(f)

            whatsapp_config = config.get("channels", {}).get("whatsapp", {})
            groups_config = whatsapp_config.get("groups", {})
            group_config = groups_config.get(self.whatsapp_group, {})

            return {
                "configured": True,
                "group_registered": self.whatsapp_group in groups_config,
                "require_mention": group_config.get("requireMention", True),
                "dm_policy": whatsapp_config.get("dmPolicy"),
                "allowed_numbers": whatsapp_config.get("allowFrom", []),
                "group_policy": whatsapp_config.get("groupPolicy"),
                "config": group_config
            }
        except FileNotFoundError:
            return {
                "configured": False,
                "error": "OpenClaw configuration file not found"
            }
        except json.JSONDecodeError:
            return {
                "configured": False,
                "error": "Invalid JSON in configuration file"
            }
        except Exception as e:
            return {
                "configured": False,
                "error": str(e)
            }

    def run_full_check(self) -> Dict:
        """
        Run comprehensive routing verification

        Returns:
            Dict with all check results
        """
        print("OpenClaw Routing Monitor")
        print("=" * 60)
        print(f"Timestamp: {datetime.now().isoformat()}")
        print(f"Gateway URL: {self.gateway_url}")
        print(f"WhatsApp Group: {self.whatsapp_group}")
        print()

        results = {
            "timestamp": datetime.now().isoformat(),
            "gateway": self.check_gateway_status(),
            "whatsapp": self.check_whatsapp_channel(),
            "sessions": self.check_agent_sessions(),
            "routing": self.verify_routing_configuration()
        }

        # Print results
        print("Gateway Status:")
        print(f"  Running: {results['gateway'].get('running', False)}")
        print(f"  Listening: {results['gateway'].get('listening', False)}")
        print()

        print("WhatsApp Channel:")
        print(f"  Connected: {results['whatsapp'].get('connected', False)}")
        print(f"  Running: {results['whatsapp'].get('running', False)}")
        print(f"  Enabled: {results['whatsapp'].get('enabled', False)}")
        print()

        print("Agent Sessions:")
        print(f"  Active: {results['sessions'].get('active', False)}")
        print(f"  WhatsApp Session: {results['sessions'].get('has_whatsapp_session', False)}")
        print(f"  Model: {results['sessions'].get('model', 'Unknown')}")
        print()

        print("Routing Configuration:")
        print(f"  Configured: {results['routing'].get('configured', False)}")
        print(f"  Group Registered: {results['routing'].get('group_registered', False)}")
        print(f"  Require Mention: {results['routing'].get('require_mention', True)}")
        print(f"  DM Policy: {results['routing'].get('dm_policy', 'Unknown')}")
        print(f"  Group Policy: {results['routing'].get('group_policy', 'Unknown')}")
        print()

        # Overall status
        all_checks_passed = (
            results['gateway'].get('running', False) and
            results['whatsapp'].get('connected', False) and
            results['sessions'].get('active', False) and
            results['routing'].get('configured', False) and
            results['routing'].get('group_registered', False)
        )

        print("=" * 60)
        if all_checks_passed:
            print("STATUS: All routing checks PASSED")
            print()
            print("OpenClaw is properly configured to route WhatsApp messages")
            print("to Claude agent. Messages with @mentions will be processed.")
            results['overall_status'] = 'PASS'
            return_code = 0
        else:
            print("STATUS: Some routing checks FAILED")
            print()
            print("Issues detected:")
            if not results['gateway'].get('running'):
                print("  - Gateway is not running")
            if not results['whatsapp'].get('connected'):
                print("  - WhatsApp channel is not connected")
            if not results['sessions'].get('active'):
                print("  - No active agent sessions")
            if not results['routing'].get('configured'):
                print("  - Routing configuration missing or invalid")
            if not results['routing'].get('group_registered'):
                print("  - WhatsApp group not registered in configuration")
            results['overall_status'] = 'FAIL'
            return_code = 1

        print("=" * 60)
        return results

    def send_test_message(self, message: str) -> Dict:
        """
        Send test message to WhatsApp group via OpenClaw

        Args:
            message: Message text to send

        Returns:
            Dict with send result
        """
        result = self.run_openclaw_command([
            "message", "send",
            "--channel", "whatsapp",
            "--target", self.whatsapp_group,
            "--message", message
        ])

        return {
            "sent": result["success"],
            "output": result.get("stdout", ""),
            "error": result.get("stderr", "") if not result["success"] else None
        }


def main():
    """Main entry point"""
    monitor = OpenClawRoutingMonitor()

    if len(sys.argv) > 1 and sys.argv[1] == "--json":
        # JSON output mode
        results = monitor.run_full_check()
        print(json.dumps(results, indent=2))
        sys.exit(0 if results.get('overall_status') == 'PASS' else 1)
    else:
        # Human-readable output
        results = monitor.run_full_check()
        sys.exit(0 if results.get('overall_status') == 'PASS' else 1)


if __name__ == "__main__":
    main()
