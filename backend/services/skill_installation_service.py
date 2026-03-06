"""
Skill Installation Service

Handles installation of CLI-based skills via go install and npm install.
"""
import asyncio
import logging
from typing import Dict, Optional, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class InstallMethod(str, Enum):
    """Installation method for a skill"""
    GO = "go"
    NPM = "npm"
    BREW = "brew"
    MANUAL = "manual"


@dataclass
class InstallResult:
    """Result of a skill installation attempt"""
    success: bool
    message: str
    logs: List[str]
    method: Optional[InstallMethod] = None
    package: Optional[str] = None


# Mapping of skill names to installation methods
# All auto-installable skills are NPM packages from the NEURO skills monorepo
# Source: https://github.com/INSTINCTx/neuro-skills
# Published to: https://www.npmjs.com/org/instinctx_dev
INSTALLABLE_SKILLS: Dict[str, Dict[str, str]] = {
    # NPM Auto-Install (3 skills) - VERIFIED WORKING
    "bear-notes": {
        "method": "npm",
        "package": "@instinctx_dev/neuro-skill-bear-notes",
        "binary": "grizzly",
        "description": "Bear Notes CLI tool"
    },
    "blogwatcher": {
        "method": "npm",
        "package": "@instinctx_dev/neuro-skill-blogwatcher",
        "binary": "blogwatcher",
        "description": "Blog monitoring tool"
    },
    "blucli": {
        "method": "npm",
        "package": "@instinctx_dev/neuro-skill-blucli",
        "binary": "blu",
        "description": "Bluetooth CLI tool"
    },

    # Homebrew Auto-Install (1 skill)
    "camsnap": {
        "method": "brew",
        "package": "steipete/tap/camsnap",
        "binary": "camsnap",
        "description": "RTSP/ONVIF camera snapshot tool"
    },

    # Manual - Homebrew Formula Removed (2 skills)
    "bird": {
        "method": "manual",
        "description": "Twitter/X CLI tool - Use NPM alternative: npm install -g @steipete/bird",
        "docs": "https://bird.fast",
        "requirements": ["NPM: npm install -g @steipete/bird"]
    },
    "openhue": {
        "method": "manual",
        "description": "Philips Hue CLI - Homebrew formula not available",
        "docs": "https://github.com/INSTINCTx/neuro-skills",
        "requirements": ["Homebrew formula removed from tap"]
    },

    # Manual - NPM Package Not Published (7 skills)
    "gifgrep": {
        "method": "manual",
        "description": "GIF search tool - NPM package not yet published",
        "docs": "https://github.com/INSTINCTx/neuro-skills",
        "requirements": ["NPM package @instinctx_dev/neuro-skill-gifgrep must be published"]
    },
    "imsg": {
        "method": "manual",
        "description": "iMessage CLI - NPM package not yet published",
        "docs": "https://github.com/INSTINCTx/neuro-skills",
        "requirements": ["NPM package @instinctx_dev/neuro-skill-imsg must be published"]
    },
    "peekaboo": {
        "method": "manual",
        "description": "Camera preview tool - NPM package not yet published",
        "docs": "https://github.com/INSTINCTx/neuro-skills",
        "requirements": ["NPM package @instinctx_dev/neuro-skill-peekaboo must be published"]
    },
    "songsee": {
        "method": "manual",
        "description": "Music recognition tool - NPM package not yet published",
        "docs": "https://github.com/INSTINCTx/neuro-skills",
        "requirements": ["NPM package @instinctx_dev/neuro-skill-songsee must be published"]
    },
    "eightctl": {
        "method": "manual",
        "description": "Home automation control - NPM package not yet published",
        "docs": "https://github.com/INSTINCTx/neuro-skills",
        "requirements": ["NPM package @instinctx_dev/neuro-skill-eightctl must be published"]
    },
    "sonoscli": {
        "method": "manual",
        "description": "Sonos speaker control - NPM package not yet published",
        "docs": "https://github.com/INSTINCTx/neuro-skills",
        "requirements": ["NPM package @instinctx_dev/neuro-skill-sonoscli must be published"]
    },
    "ordercli": {
        "method": "manual",
        "description": "Order management CLI - NPM package not yet published",
        "docs": "https://github.com/INSTINCTx/neuro-skills",
        "requirements": ["NPM package @instinctx_dev/neuro-skill-food-order must be published"]
    },

    # Manual/Complex (14 skills) - Return documentation only
    "goplaces": {
        "method": "manual",
        "description": "Requires Google Places API key AND go install",
        "docs": "https://console.cloud.google.com/apis/library/places-backend.googleapis.com",
        "requirements": ["Google Places API key", "Go binary installation"]
    },
    "local-places": {
        "method": "manual",
        "description": "Requires Google Places API key",
        "docs": "https://console.cloud.google.com/apis/library/places-backend.googleapis.com",
        "requirements": ["Google Places API key"]
    },
    "nano-banana-pro": {
        "method": "manual",
        "description": "Requires Gemini API key",
        "docs": "https://aistudio.google.com/app/apikey",
        "requirements": ["Gemini API key"]
    },
    "nano-pdf": {
        "method": "manual",
        "description": "PDF processing tool requiring manual setup",
        "docs": "https://github.com/openclaw/nano-pdf",
        "requirements": ["PDF processing libraries"]
    },
    "notion": {
        "method": "manual",
        "description": "Requires Notion API key",
        "docs": "https://www.notion.so/my-integrations",
        "requirements": ["Notion Integration Token"]
    },
    "obsidian": {
        "method": "manual",
        "description": "Requires Obsidian vault configuration",
        "docs": "https://obsidian.md",
        "requirements": ["Obsidian vault path"]
    },
    "oracle": {
        "method": "manual",
        "description": "Oracle Database CLI requiring Oracle Instant Client",
        "docs": "https://www.oracle.com/database/technologies/instant-client.html",
        "requirements": ["Oracle Instant Client", "Database credentials"]
    },
    "sag": {
        "method": "manual",
        "description": "Requires ElevenLabs API key",
        "docs": "https://elevenlabs.io/api",
        "requirements": ["ElevenLabs API key"]
    },
    "sherpa-onnx-tts": {
        "method": "manual",
        "description": "Text-to-speech requiring ONNX model files",
        "docs": "https://github.com/k2-fsa/sherpa-onnx",
        "requirements": ["ONNX model files", "ONNX runtime"]
    },
    "summarize": {
        "method": "manual",
        "description": "Summarization tool requiring manual setup",
        "docs": "https://github.com/ossianhempel/things3-cli",
        "requirements": ["Configuration file"]
    },
    "gog": {
        "method": "manual",
        "description": "GOG gaming integration requiring credentials",
        "docs": "https://www.gog.com/account/settings/security",
        "requirements": ["GOG account credentials"]
    },
    "model-usage": {
        "method": "manual",
        "description": "Model analytics requiring API access",
        "docs": "https://github.com/openclaw/model-usage",
        "requirements": ["Model provider API keys"]
    },
    "spotify": {
        "method": "manual",
        "description": "Spotify integration requiring OAuth",
        "docs": "https://developer.spotify.com/dashboard",
        "requirements": ["Spotify Client ID/Secret", "OAuth flow"]
    },
    "claude-desktop": {
        "method": "manual",
        "description": "Claude Desktop integration",
        "docs": "https://claude.ai/desktop",
        "requirements": ["Claude Desktop installation"]
    },
}


class SkillInstallationService:
    """Service for installing CLI-based skills"""

    @staticmethod
    async def install_neuro_skill(skill_name: str, neuro_package: str, timeout: int = 300) -> InstallResult:
        """
        Install a NEURO skill with 2-step process:
        1. Install NPM package (skill metadata/config)
        2. Parse SKILL.md and install actual CLI binary

        Args:
            skill_name: Name of the skill (e.g., 'blucli')
            neuro_package: NPM package name (e.g., '@instinctx_dev/neuro-skill-blucli')
            timeout: Installation timeout in seconds (default: 300)

        Returns:
            InstallResult with success status and logs
        """
        import os
        import re

        logs: List[str] = []

        try:
            # Step 1: Install NEURO skill package (config files)
            logs.append(f"Step 1: Installing NEURO skill package '{neuro_package}'...")
            npm_result = await SkillInstallationService.install_npm_package(neuro_package, timeout=60)
            logs.extend(npm_result.logs)

            if not npm_result.success:
                return InstallResult(
                    success=False,
                    message=f"Failed to install NEURO skill package: {npm_result.message}",
                    logs=logs,
                    method=InstallMethod.NPM,
                    package=neuro_package
                )

            # Step 2: Find and parse SKILL.md
            logs.append(f"Step 2: Reading skill metadata from SKILL.md...")
            npm_global_prefix = os.path.expanduser("~/.npm-global")
            if not os.path.exists(npm_global_prefix):
                # Try Homebrew location
                npm_global_prefix = "/opt/homebrew/lib"

            skill_md_path = os.path.join(
                npm_global_prefix,
                "node_modules",
                neuro_package,
                "SKILL.md"
            )

            if not os.path.exists(skill_md_path):
                logs.append(f"Warning: SKILL.md not found at {skill_md_path}")
                logs.append("Skill config installed, but actual CLI binary may need manual installation")
                return InstallResult(
                    success=True,
                    message=f"NEURO skill config installed (manual CLI installation may be required)",
                    logs=logs,
                    method=InstallMethod.NPM,
                    package=neuro_package
                )

            # Parse SKILL.md to extract installation command
            with open(skill_md_path, 'r') as f:
                skill_md_content = f.read()

            # Extract install metadata from YAML frontmatter
            install_match = re.search(r'"install":\s*\[(.*?)\]', skill_md_content, re.DOTALL)
            if not install_match:
                logs.append("Warning: No installation metadata found in SKILL.md")
                logs.append("Skill config installed, but actual CLI binary may need manual installation")
                return InstallResult(
                    success=True,
                    message=f"NEURO skill config installed (no binary installation metadata found)",
                    logs=logs,
                    method=InstallMethod.NPM,
                    package=neuro_package
                )

            install_section = install_match.group(1)

            # Extract kind and module/command
            kind_match = re.search(r'"kind":\s*"([^"]+)"', install_section)
            module_match = re.search(r'"module":\s*"([^"]+)"', install_section)

            if not kind_match:
                logs.append("Warning: Installation method not specified in SKILL.md")
                return InstallResult(
                    success=True,
                    message=f"NEURO skill config installed (installation method not specified)",
                    logs=logs,
                    method=InstallMethod.NPM,
                    package=neuro_package
                )

            install_kind = kind_match.group(1)
            logs.append(f"Found installation method: {install_kind}")

            # Step 3: Install actual CLI binary based on kind
            if install_kind == "go" and module_match:
                go_module = module_match.group(1)
                logs.append(f"Step 3: Installing Go binary from '{go_module}'...")
                go_result = await SkillInstallationService.install_go_package(go_module, timeout=timeout)
                logs.extend(go_result.logs)

                if go_result.success:
                    return InstallResult(
                        success=True,
                        message=f"Successfully installed {skill_name} (config + binary)",
                        logs=logs,
                        method=InstallMethod.GO,
                        package=go_module
                    )
                else:
                    return InstallResult(
                        success=False,
                        message=f"Config installed, but binary installation failed: {go_result.message}",
                        logs=logs,
                        method=InstallMethod.GO,
                        package=go_module
                    )

            elif install_kind == "npm" and module_match:
                npm_module = module_match.group(1)
                logs.append(f"Step 3: Installing NPM binary from '{npm_module}'...")
                npm_bin_result = await SkillInstallationService.install_npm_package(npm_module, timeout=timeout)
                logs.extend(npm_bin_result.logs)

                if npm_bin_result.success:
                    return InstallResult(
                        success=True,
                        message=f"Successfully installed {skill_name} (config + binary)",
                        logs=logs,
                        method=InstallMethod.NPM,
                        package=npm_module
                    )
                else:
                    return InstallResult(
                        success=False,
                        message=f"Config installed, but binary installation failed: {npm_bin_result.message}",
                        logs=logs,
                        method=InstallMethod.NPM,
                        package=npm_module
                    )
            else:
                logs.append(f"Warning: Unsupported installation kind '{install_kind}' or missing module")
                return InstallResult(
                    success=True,
                    message=f"NEURO skill config installed (binary installation not supported)",
                    logs=logs,
                    method=InstallMethod.NPM,
                    package=neuro_package
                )

        except Exception as e:
            logs.append(f"Error: {str(e)}")
            logger.exception(f"Error installing NEURO skill {skill_name}")
            return InstallResult(
                success=False,
                message=f"Installation error: {str(e)}",
                logs=logs,
                method=InstallMethod.NPM,
                package=neuro_package
            )

    @staticmethod
    async def install_go_package(package_path: str, timeout: int = 300) -> InstallResult:
        """
        Install a Go package using 'go install'

        Args:
            package_path: Full package path (e.g., github.com/user/package)
            timeout: Installation timeout in seconds (default: 300)

        Returns:
            InstallResult with success status and logs
        """
        logs: List[str] = []

        try:
            # Check if go is installed
            check_cmd = ["go", "version"]
            check_process = await asyncio.create_subprocess_exec(
                *check_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                check_process.communicate(),
                timeout=10
            )

            if check_process.returncode != 0:
                return InstallResult(
                    success=False,
                    message="Go is not installed on this system",
                    logs=["Error: 'go' command not found"],
                    method=InstallMethod.GO,
                    package=package_path
                )

            go_version = stdout.decode().strip()
            logs.append(f"Using: {go_version}")

            # Install the package (add @latest if not already present)
            if "@" not in package_path:
                package_with_version = f"{package_path}@latest"
            else:
                package_with_version = package_path

            install_cmd = ["go", "install", package_with_version]
            logs.append(f"Running: {' '.join(install_cmd)}")

            process = await asyncio.create_subprocess_exec(
                *install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            # Capture output
            if stdout:
                for line in stdout.decode().splitlines():
                    logs.append(f"[stdout] {line}")

            if stderr:
                for line in stderr.decode().splitlines():
                    logs.append(f"[stderr] {line}")

            if process.returncode == 0:
                logs.append("Installation successful")
                return InstallResult(
                    success=True,
                    message=f"Successfully installed {package_path}",
                    logs=logs,
                    method=InstallMethod.GO,
                    package=package_path
                )
            else:
                return InstallResult(
                    success=False,
                    message=f"Installation failed with exit code {process.returncode}",
                    logs=logs,
                    method=InstallMethod.GO,
                    package=package_path
                )

        except asyncio.TimeoutError:
            logs.append(f"Installation timed out after {timeout} seconds")
            return InstallResult(
                success=False,
                message=f"Installation timed out after {timeout} seconds",
                logs=logs,
                method=InstallMethod.GO,
                package=package_path
            )
        except Exception as e:
            logs.append(f"Error: {str(e)}")
            logger.exception(f"Error installing Go package {package_path}")
            return InstallResult(
                success=False,
                message=f"Installation error: {str(e)}",
                logs=logs,
                method=InstallMethod.GO,
                package=package_path
            )

    @staticmethod
    async def install_npm_package(package_name: str, timeout: int = 300) -> InstallResult:
        """
        Install an NPM package globally using 'npm install -g'

        Args:
            package_name: NPM package name
            timeout: Installation timeout in seconds (default: 300)

        Returns:
            InstallResult with success status and logs
        """
        logs: List[str] = []

        try:
            # Check if npm is installed
            check_cmd = ["npm", "--version"]
            check_process = await asyncio.create_subprocess_exec(
                *check_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                check_process.communicate(),
                timeout=10
            )

            if check_process.returncode != 0:
                return InstallResult(
                    success=False,
                    message="NPM is not installed on this system",
                    logs=["Error: 'npm' command not found"],
                    method=InstallMethod.NPM,
                    package=package_name
                )

            npm_version = stdout.decode().strip()
            logs.append(f"Using npm version: {npm_version}")

            # Install the package globally
            install_cmd = ["npm", "install", "-g", package_name]
            logs.append(f"Running: {' '.join(install_cmd)}")

            process = await asyncio.create_subprocess_exec(
                *install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            # Capture output
            if stdout:
                for line in stdout.decode().splitlines():
                    logs.append(f"[stdout] {line}")

            if stderr:
                # NPM writes progress to stderr, not always errors
                for line in stderr.decode().splitlines():
                    logs.append(f"[stderr] {line}")

            if process.returncode == 0:
                logs.append("Installation successful")
                return InstallResult(
                    success=True,
                    message=f"Successfully installed {package_name}",
                    logs=logs,
                    method=InstallMethod.NPM,
                    package=package_name
                )
            else:
                return InstallResult(
                    success=False,
                    message=f"Installation failed with exit code {process.returncode}",
                    logs=logs,
                    method=InstallMethod.NPM,
                    package=package_name
                )

        except asyncio.TimeoutError:
            logs.append(f"Installation timed out after {timeout} seconds")
            return InstallResult(
                success=False,
                message=f"Installation timed out after {timeout} seconds",
                logs=logs,
                method=InstallMethod.NPM,
                package=package_name
            )
        except Exception as e:
            logs.append(f"Error: {str(e)}")
            logger.exception(f"Error installing NPM package {package_name}")
            return InstallResult(
                success=False,
                message=f"Installation error: {str(e)}",
                logs=logs,
                method=InstallMethod.NPM,
                package=package_name
            )

    @staticmethod
    async def install_brew_package(package_name: str, timeout: int = 300) -> InstallResult:
        """
        Install a package using Homebrew 'brew install'

        Args:
            package_name: Homebrew package name
            timeout: Installation timeout in seconds (default: 300)

        Returns:
            InstallResult with success status and logs
        """
        logs: List[str] = []

        try:
            # Check if brew is installed
            check_cmd = ["brew", "--version"]
            check_process = await asyncio.create_subprocess_exec(
                *check_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                check_process.communicate(),
                timeout=10
            )

            if check_process.returncode != 0:
                return InstallResult(
                    success=False,
                    message="Homebrew is not installed on this system",
                    logs=["Error: 'brew' command not found", "Install from: https://brew.sh"],
                    method=InstallMethod.BREW,
                    package=package_name
                )

            brew_version = stdout.decode().strip().split('\n')[0]
            logs.append(f"Using: {brew_version}")

            # Install the package
            install_cmd = ["brew", "install", package_name]
            logs.append(f"Running: {' '.join(install_cmd)}")

            process = await asyncio.create_subprocess_exec(
                *install_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )

            # Capture output
            if stdout:
                for line in stdout.decode().splitlines():
                    logs.append(f"[stdout] {line}")

            if stderr:
                for line in stderr.decode().splitlines():
                    logs.append(f"[stderr] {line}")

            if process.returncode == 0:
                logs.append("Installation successful")
                return InstallResult(
                    success=True,
                    message=f"Successfully installed {package_name}",
                    logs=logs,
                    method=InstallMethod.BREW,
                    package=package_name
                )
            else:
                return InstallResult(
                    success=False,
                    message=f"Installation failed with exit code {process.returncode}",
                    logs=logs,
                    method=InstallMethod.BREW,
                    package=package_name
                )

        except asyncio.TimeoutError:
            logs.append(f"Installation timed out after {timeout} seconds")
            return InstallResult(
                success=False,
                message=f"Installation timed out after {timeout} seconds",
                logs=logs,
                method=InstallMethod.BREW,
                package=package_name
            )
        except Exception as e:
            logs.append(f"Error: {str(e)}")
            logger.exception(f"Error installing Homebrew package {package_name}")
            return InstallResult(
                success=False,
                message=f"Installation error: {str(e)}",
                logs=logs,
                method=InstallMethod.BREW,
                package=package_name
            )

    @staticmethod
    def get_install_method(skill_name: str) -> Optional[Dict[str, str]]:
        """
        Get installation method for a skill

        Args:
            skill_name: Name of the skill

        Returns:
            Dict with method, package, description, and optional docs/requirements
            None if skill is not recognized
        """
        return INSTALLABLE_SKILLS.get(skill_name)

    @staticmethod
    def get_all_installable_skills() -> Dict[str, Dict[str, str]]:
        """
        Get all installable skills with their metadata

        Returns:
            Dictionary of all skill installation configurations
        """
        return INSTALLABLE_SKILLS.copy()

    @staticmethod
    def is_skill_installable(skill_name: str) -> bool:
        """
        Check if a skill is installable (go, npm, or brew)

        Args:
            skill_name: Name of the skill

        Returns:
            True if skill can be auto-installed, False otherwise
        """
        skill_info = INSTALLABLE_SKILLS.get(skill_name)
        if not skill_info:
            return False
        return skill_info["method"] in [InstallMethod.GO, InstallMethod.NPM, InstallMethod.BREW]
