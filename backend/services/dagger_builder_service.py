"""
Dagger Builder Service for OpenClaw Backend

Provides containerization capabilities for the OpenClaw multi-agent system,
including:
- Container lifecycle management (build, run, stop, cleanup)
- Test execution in isolated containers
- Build artifact management
- Multi-language support (Python, Node.js, Go)
- Resource limits and cleanup
- Parallel builds with caching
- Build metrics and monitoring

Migrated from core repository with enhancements for OpenClaw architecture.
"""

import asyncio
import json
import logging
import os
import shutil
import tarfile
import tempfile
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

logger = logging.getLogger(__name__)


# Enums

class DaggerEngine(Enum):
    """Container engine types supported"""
    DOCKER = "docker"
    BUILDKIT = "buildkit"
    CONTAINERD = "containerd"
    PODMAN = "podman"


class BuildCacheStrategy(Enum):
    """Build cache strategies"""
    LOCAL = "local"
    REGISTRY = "registry"
    INLINE = "inline"
    DISABLED = "disabled"


# Configuration Models

@dataclass
class DaggerConfig:
    """Configuration for DaggerBuilderService"""
    engine: DaggerEngine
    cache_strategy: BuildCacheStrategy
    cache_registry: Optional[str] = None
    build_timeout: int = 1800  # 30 minutes
    max_parallelism: int = 4
    enable_debug: bool = False
    workspace_dir: str = "/tmp/dagger-workspace"


@dataclass
class ResourceLimits:
    """Resource limits for container execution"""
    cpu_limit: Optional[str] = None  # e.g., "2.0" for 2 CPUs
    memory_limit: Optional[str] = None  # e.g., "2g" for 2GB
    timeout_seconds: Optional[int] = None


@dataclass
class LanguageConfig:
    """Language-specific configuration"""
    language: str  # python, nodejs, go
    version: str
    dependencies: Optional[Dict[str, str]] = None
    multi_stage: bool = True


# Build Context Models

@dataclass
class DaggerBuildContext:
    """Build context for container image builds"""
    id: str
    name: str
    source_path: str
    dockerfile_content: str
    build_args: Dict[str, str]
    environment_vars: Dict[str, str]
    secrets: Dict[str, str]
    target_stage: Optional[str] = None
    platform: str = "linux/amd64"
    cache_from: List[str] = field(default_factory=list)
    cache_to: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


# Result Models

@dataclass
class DaggerBuildResult:
    """Result of a container image build"""
    id: str
    image_id: str
    image_size: int
    build_time: float
    cache_hits: int
    cache_misses: int
    success: bool
    error_message: Optional[str] = None
    build_logs: List[str] = field(default_factory=list)
    created_at: Optional[datetime] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


@dataclass
class ContainerRunResult:
    """Result of container execution"""
    success: bool
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    container_id: Optional[str] = None


@dataclass
class TestExecutionResult:
    """Result of test execution in container"""
    success: bool
    tests_passed: int
    tests_failed: int
    duration: float
    coverage_percent: Optional[float] = None
    test_output: Optional[str] = None


@dataclass
class BuildArtifact:
    """Build artifact metadata"""
    success: bool
    artifact_path: Optional[str]
    size_bytes: int = 0
    artifact_type: Optional[str] = None


# Main Service

class DaggerBuilderService:
    """
    Service for managing containerized builds and test execution
    using Dagger-inspired techniques.
    """

    def __init__(self, config: Optional[DaggerConfig] = None):
        """
        Initialize DaggerBuilderService

        Args:
            config: Dagger configuration, uses defaults if None
        """
        self.config = config or DaggerConfig(
            engine=DaggerEngine.BUILDKIT,
            cache_strategy=BuildCacheStrategy.LOCAL
        )

        # Initialize workspace
        self.workspace_dir = Path(self.config.workspace_dir)
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Build tracking
        self.build_cache: Dict[str, Dict[str, Any]] = {}
        self.active_builds: Dict[str, asyncio.Task] = {}

        # Dockerfile templates for different languages
        self.dockerfile_templates = self._initialize_templates()

        logger.info(f"DaggerBuilderService initialized with engine: {self.config.engine.value}")

    def _initialize_templates(self) -> Dict[str, str]:
        """Initialize Dockerfile templates for different agent types"""
        return {
            "python_agent": """
# Multi-stage Python build optimized for Dagger
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \\
    PYTHONUNBUFFERED=1 \\
    PIP_NO_CACHE_DIR=1 \\
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

FROM base AS dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \\
    gcc g++ git curl && rm -rf /var/lib/apt/lists/*

FROM dependencies AS python-deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

FROM python-deps AS app
COPY . .

RUN useradd --create-home --shell /bin/bash agent && \\
    chown -R agent:agent /app
USER agent

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

EXPOSE ${PORT:-8000}

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "${PORT:-8000}"]
""",
            "node_agent": """
# Multi-stage Node.js build optimized for Dagger
FROM node:18-alpine AS base

ENV NODE_ENV=production \\
    NPM_CONFIG_CACHE=/tmp/.npm

WORKDIR /app

FROM base AS dependencies
COPY package*.json ./
RUN npm ci --only=production --no-audit --no-fund

FROM dependencies AS build
COPY . .
RUN npm run build

FROM node:18-alpine AS production

RUN addgroup -g 1001 -S nodejs && adduser -S agent -u 1001

WORKDIR /app

COPY --from=build --chown=agent:nodejs /app/dist ./dist
COPY --from=dependencies --chown=agent:nodejs /app/node_modules ./node_modules
COPY --chown=agent:nodejs package*.json ./

USER agent

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD wget --no-verbose --tries=1 --spider http://localhost:${PORT:-3000}/health || exit 1

EXPOSE ${PORT:-3000}

CMD ["node", "dist/index.js"]
""",
            "go_agent": """
# Multi-stage Go build optimized for Dagger
FROM golang:1.21-alpine AS builder

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -a -installsuffix cgo -o main .

FROM alpine:latest AS production

RUN apk --no-cache add ca-certificates
RUN adduser -D -u 1001 agent

WORKDIR /app

COPY --from=builder --chown=agent:agent /app/main .

USER agent

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \\
    CMD wget --no-verbose --tries=1 --spider http://localhost:${PORT:-8080}/health || exit 1

EXPOSE ${PORT:-8080}

CMD ["./main"]
""",
            "multi_agent_orchestrator": """
# Multi-agent orchestrator build
FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \\
    curl git gcc g++ postgresql-client && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

RUN useradd --create-home --shell /bin/bash orchestrator && \\
    chown -R orchestrator:orchestrator /app

USER orchestrator

HEALTHCHECK --interval=30s --timeout=15s --start-period=10s --retries=3 \\
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
"""
        }

    # Build Methods

    async def build_image(self, context: DaggerBuildContext) -> DaggerBuildResult:
        """
        Build a container image from build context

        Args:
            context: Build context with Dockerfile and settings

        Returns:
            DaggerBuildResult with build outcome and metrics
        """
        build_start = datetime.utcnow()

        try:
            logger.info(f"Starting build for: {context.name}")

            # Create build workspace
            build_workspace = self.workspace_dir / context.id
            build_workspace.mkdir(parents=True, exist_ok=True)

            # Write Dockerfile
            dockerfile_path = build_workspace / "Dockerfile"
            dockerfile_path.write_text(context.dockerfile_content)

            # Copy source files if they exist
            if os.path.exists(context.source_path):
                await self._copy_source_files(context.source_path, build_workspace)

            # Generate build command
            build_cmd = await self._generate_build_command(context, build_workspace)

            # Execute build
            result = await self._execute_build(build_cmd, context)

            # Calculate build time
            build_time = (datetime.utcnow() - build_start).total_seconds()

            # Create result
            build_result = DaggerBuildResult(
                id=context.id,
                image_id=result.get('image_id', ''),
                image_size=result.get('image_size', 0),
                build_time=build_time,
                cache_hits=result.get('cache_hits', 0),
                cache_misses=result.get('cache_misses', 0),
                success=result.get('success', False),
                error_message=result.get('error_message'),
                build_logs=result.get('logs', [])
            )

            # Update cache on success
            if build_result.success:
                self.build_cache[context.id] = {
                    'image_id': build_result.image_id,
                    'build_time': build_result.build_time,
                    'created_at': build_result.created_at,
                    'success': True,
                }
                logger.info(f"Build completed successfully: {context.name} in {build_time:.2f}s")
            else:
                logger.error(f"Build failed: {context.name} - {build_result.error_message}")

            return build_result

        except Exception as e:
            build_time = (datetime.utcnow() - build_start).total_seconds()
            logger.error(f"Build error for {context.name}: {e}")

            return DaggerBuildResult(
                id=context.id,
                image_id="",
                image_size=0,
                build_time=build_time,
                cache_hits=0,
                cache_misses=0,
                success=False,
                error_message=str(e),
                build_logs=[str(e)]
            )

    async def _generate_build_command(
        self,
        context: DaggerBuildContext,
        workspace: Path
    ) -> List[str]:
        """Generate build command based on engine and settings"""
        if self.config.engine == DaggerEngine.BUILDKIT:
            cmd = [
                "docker", "buildx", "build",
                "--progress=plain",
                "--platform", context.platform,
                "-f", str(workspace / "Dockerfile"),
                "-t", f"{context.name}:latest"
            ]

            # Add build arguments
            for key, value in context.build_args.items():
                cmd.extend(["--build-arg", f"{key}={value}"])

            # Add caching configuration
            if self.config.cache_strategy == BuildCacheStrategy.REGISTRY and self.config.cache_registry:
                cache_from = f"type=registry,ref={self.config.cache_registry}/{context.name}:cache"
                cache_to = f"type=registry,ref={self.config.cache_registry}/{context.name}:cache,mode=max"
                cmd.extend(["--cache-from", cache_from, "--cache-to", cache_to])
            elif self.config.cache_strategy == BuildCacheStrategy.LOCAL:
                cmd.extend(["--cache-from", "type=local,src=/tmp/buildkit-cache"])
                cmd.extend(["--cache-to", "type=local,dest=/tmp/buildkit-cache,mode=max"])

            # Add target stage if specified
            if context.target_stage:
                cmd.extend(["--target", context.target_stage])

            cmd.append(str(workspace))

        elif self.config.engine == DaggerEngine.DOCKER:
            cmd = [
                "docker", "build",
                "-f", str(workspace / "Dockerfile"),
                "-t", f"{context.name}:latest"
            ]

            for key, value in context.build_args.items():
                cmd.extend(["--build-arg", f"{key}={value}"])

            cmd.append(str(workspace))

        elif self.config.engine == DaggerEngine.PODMAN:
            cmd = [
                "podman", "build",
                "-f", str(workspace / "Dockerfile"),
                "-t", f"{context.name}:latest"
            ]

            for key, value in context.build_args.items():
                cmd.extend(["--build-arg", f"{key}={value}"])

            cmd.append(str(workspace))

        else:
            raise ValueError(f"Unsupported engine: {self.config.engine}")

        return cmd

    async def _execute_build(
        self,
        cmd: List[str],
        context: DaggerBuildContext
    ) -> Dict[str, Any]:
        """Execute build command and capture output"""
        try:
            # Prepare environment
            env = os.environ.copy()
            env.update(context.environment_vars)

            if self.config.engine == DaggerEngine.BUILDKIT:
                env["DOCKER_BUILDKIT"] = "1"
                env["BUILDKIT_PROGRESS"] = "plain"
                env["BUILDKIT_INLINE_CACHE"] = "1"

            logger.info(f"Executing: {' '.join(cmd)}")

            # Execute build
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env
            )

            # Capture logs and track cache usage
            logs = []
            cache_hits = 0
            cache_misses = 0

            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                log_line = line.decode('utf-8').strip()
                logs.append(log_line)

                # Track cache usage
                if "CACHED" in log_line or "Using cache" in log_line:
                    cache_hits += 1
                elif "RUN" in log_line or "COPY" in log_line or "Running in" in log_line:
                    cache_misses += 1

                if self.config.enable_debug:
                    logger.debug(f"Build: {log_line}")

            await process.wait()

            # Check success
            if process.returncode == 0:
                image_info = await self._get_image_info(context.name)

                return {
                    'success': True,
                    'image_id': image_info.get('image_id', ''),
                    'image_size': image_info.get('size', 0),
                    'cache_hits': cache_hits,
                    'cache_misses': cache_misses,
                    'logs': logs
                }
            else:
                return {
                    'success': False,
                    'error_message': f"Build failed with exit code {process.returncode}",
                    'cache_hits': cache_hits,
                    'cache_misses': cache_misses,
                    'logs': logs
                }

        except Exception as e:
            logger.error(f"Build execution error: {e}")
            return {
                'success': False,
                'error_message': str(e),
                'cache_hits': 0,
                'cache_misses': 0,
                'logs': [str(e)]
            }

    async def _get_image_info(self, image_name: str) -> Dict[str, Any]:
        """Get information about a built image"""
        try:
            cmd = ["docker", "inspect", f"{image_name}:latest"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                image_data = json.loads(stdout.decode('utf-8'))[0]
                return {
                    'image_id': image_data['Id'],
                    'size': image_data['Size'],
                    'created': image_data['Created']
                }
            else:
                logger.warning(f"Failed to inspect image {image_name}: {stderr.decode('utf-8')}")
                return {}

        except Exception as e:
            logger.error(f"Error getting image info: {e}")
            return {}

    async def _copy_source_files(self, source_path: str, dest_path: Path):
        """Copy source files to build workspace"""
        try:
            if os.path.isdir(source_path):
                # Use shutil for directory copy (more reliable than subprocess)
                for item in os.listdir(source_path):
                    s = os.path.join(source_path, item)
                    d = os.path.join(dest_path, item)
                    if os.path.isdir(s):
                        shutil.copytree(s, d, dirs_exist_ok=True)
                    else:
                        shutil.copy2(s, d)
            else:
                shutil.copy2(source_path, dest_path)

        except Exception as e:
            logger.error(f"Error copying source files: {e}")
            raise

    # Container Execution Methods

    async def run_container(
        self,
        image_name: str,
        command: List[str],
        environment_vars: Optional[Dict[str, str]] = None,
        resource_limits: Optional[ResourceLimits] = None,
        volumes: Optional[Dict[str, str]] = None,
    ) -> ContainerRunResult:
        """
        Run a container with specified command and configuration

        Args:
            image_name: Container image to run
            command: Command to execute
            environment_vars: Environment variables
            resource_limits: Resource limits (CPU, memory, timeout)
            volumes: Volume mounts

        Returns:
            ContainerRunResult with execution outcome
        """
        start_time = datetime.utcnow()

        try:
            cmd = ["docker", "run", "--rm"]

            # Add resource limits
            if resource_limits:
                if resource_limits.cpu_limit:
                    cmd.extend(["--cpus", resource_limits.cpu_limit])
                if resource_limits.memory_limit:
                    cmd.extend(["--memory", resource_limits.memory_limit])

            # Add environment variables
            if environment_vars:
                for key, value in environment_vars.items():
                    cmd.extend(["-e", f"{key}={value}"])

            # Add volume mounts
            if volumes:
                for host_path, container_path in volumes.items():
                    cmd.extend(["-v", f"{host_path}:{container_path}"])

            # Add image and command
            cmd.append(image_name)
            cmd.extend(command)

            logger.info(f"Running container: {' '.join(cmd)}")

            # Execute with timeout if specified
            timeout = resource_limits.timeout_seconds if resource_limits else None

            try:
                process = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )

                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=timeout
                )

                duration = (datetime.utcnow() - start_time).total_seconds()

                return ContainerRunResult(
                    success=process.returncode == 0,
                    exit_code=process.returncode,
                    stdout=stdout.decode('utf-8'),
                    stderr=stderr.decode('utf-8'),
                    duration=duration,
                )

            except asyncio.TimeoutError:
                duration = (datetime.utcnow() - start_time).total_seconds()
                return ContainerRunResult(
                    success=False,
                    exit_code=-1,
                    stdout="",
                    stderr=f"Container execution timeout after {timeout}s",
                    duration=duration,
                )

        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            logger.error(f"Container execution error: {e}")
            return ContainerRunResult(
                success=False,
                exit_code=-1,
                stdout="",
                stderr=str(e),
                duration=duration,
            )

    async def stop_container(self, container_id: str) -> bool:
        """Stop a running container"""
        try:
            cmd = ["docker", "stop", container_id]
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.wait()
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Error stopping container {container_id}: {e}")
            return False

    async def remove_container(self, container_id: str) -> bool:
        """Remove a container"""
        try:
            cmd = ["docker", "rm", "-f", container_id]
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.wait()
            return process.returncode == 0
        except Exception as e:
            logger.error(f"Error removing container {container_id}: {e}")
            return False

    async def cleanup_containers(self, prefix: Optional[str] = None) -> Dict[str, int]:
        """
        Cleanup containers with optional prefix filter

        Args:
            prefix: Only cleanup containers with this name prefix

        Returns:
            Dict with cleanup stats
        """
        try:
            # List containers
            cmd = ["docker", "ps", "-a", "--format", "{{.ID}}:{{.Names}}"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                logger.error(f"Failed to list containers: {stderr.decode('utf-8')}")
                return {"cleaned": 0}

            containers = []
            for line in stdout.decode('utf-8').strip().split('\n'):
                if not line:
                    continue
                container_id, name = line.split(':', 1)
                if prefix is None or name.startswith(prefix):
                    containers.append(container_id)

            # Remove containers
            cleaned = 0
            for container_id in containers:
                if await self.remove_container(container_id):
                    cleaned += 1

            return {"cleaned": cleaned}

        except Exception as e:
            logger.error(f"Error cleaning up containers: {e}")
            return {"cleaned": 0}

    # Test Execution Methods

    async def run_tests(
        self,
        source_path: str,
        test_config: Dict[str, Any],
    ) -> TestExecutionResult:
        """
        Run tests in isolated container

        Args:
            source_path: Path to source code
            test_config: Test configuration with language, command, etc.

        Returns:
            TestExecutionResult with test outcomes
        """
        start_time = datetime.utcnow()

        try:
            language = test_config.get("language", "python")
            test_command = test_config.get("test_command", "pytest")

            # Build test image
            dockerfile = self._generate_test_dockerfile(language, test_config)

            context = DaggerBuildContext(
                id=f"test_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}",
                name=f"test-{language}",
                source_path=source_path,
                dockerfile_content=dockerfile,
                build_args={},
                environment_vars={},
                secrets={},
            )

            build_result = await self.build_image(context)

            if not build_result.success:
                return TestExecutionResult(
                    success=False,
                    tests_passed=0,
                    tests_failed=0,
                    duration=0,
                    test_output=build_result.error_message,
                )

            # Run tests
            run_result = await self.run_container(
                image_name=f"{context.name}:latest",
                command=test_command.split(),
            )

            # Parse test results
            tests_passed, tests_failed, coverage = self._parse_test_output(
                run_result.stdout,
                language
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            return TestExecutionResult(
                success=run_result.success,
                tests_passed=tests_passed,
                tests_failed=tests_failed,
                duration=duration,
                coverage_percent=coverage,
                test_output=run_result.stdout,
            )

        except Exception as e:
            logger.error(f"Test execution error: {e}")
            duration = (datetime.utcnow() - start_time).total_seconds()
            return TestExecutionResult(
                success=False,
                tests_passed=0,
                tests_failed=0,
                duration=duration,
                test_output=str(e),
            )

    def _generate_test_dockerfile(self, language: str, config: Dict[str, Any]) -> str:
        """Generate Dockerfile for test execution"""
        if language == "python":
            requirements = config.get("requirements", "pytest")
            # Handle space-separated and dict-based requirements
            if isinstance(requirements, dict):
                req_str = " ".join([f"{k}=={v}" for k, v in requirements.items()])
            else:
                req_str = requirements
            return f"""
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir {req_str}
CMD ["pytest", "tests/", "-v"]
"""
        elif language == "nodejs":
            return """
FROM node:18-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npm", "test"]
"""
        elif language == "go":
            return """
FROM golang:1.21-alpine
WORKDIR /app
COPY . .
RUN go mod download
CMD ["go", "test", "./..."]
"""
        else:
            raise ValueError(f"Unsupported language: {language}")

    def _parse_test_output(
        self,
        output: str,
        language: str
    ) -> tuple[int, int, Optional[float]]:
        """Parse test output to extract metrics"""
        tests_passed = 0
        tests_failed = 0
        coverage = None

        if language == "python":
            # Parse pytest output
            if "passed" in output:
                parts = output.split()
                for i, part in enumerate(parts):
                    if part == "passed":
                        try:
                            tests_passed = int(parts[i - 1])
                        except (IndexError, ValueError):
                            pass

            if "Coverage:" in output:
                try:
                    coverage_str = output.split("Coverage:")[1].split("%")[0].strip()
                    coverage = float(coverage_str)
                except (IndexError, ValueError):
                    pass

        elif language == "nodejs":
            # Parse Jest/npm test output
            if "Tests:" in output:
                parts = output.split("Tests:")[1].split(",")
                for part in parts:
                    if "passed" in part:
                        try:
                            tests_passed = int(part.split()[0])
                        except ValueError:
                            pass

        return tests_passed, tests_failed, coverage

    # Artifact Management Methods

    async def copy_artifact(
        self,
        container_id: str,
        artifact_path: str,
        dest_path: str,
    ) -> BuildArtifact:
        """Copy artifact from container to host"""
        try:
            cmd = ["docker", "cp", f"{container_id}:{artifact_path}", dest_path]
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.wait()

            if process.returncode == 0:
                size = os.path.getsize(dest_path) if os.path.exists(dest_path) else 0
                return BuildArtifact(
                    success=True,
                    artifact_path=dest_path,
                    size_bytes=size,
                )
            else:
                return BuildArtifact(
                    success=False,
                    artifact_path=None,
                )

        except Exception as e:
            logger.error(f"Error copying artifact: {e}")
            return BuildArtifact(
                success=False,
                artifact_path=None,
            )

    async def extract_artifacts(
        self,
        build_id: str,
        artifact_paths: List[str],
        dest_dir: str,
    ) -> List[BuildArtifact]:
        """Extract multiple artifacts from build"""
        artifacts = []

        for artifact_path in artifact_paths:
            artifact = await self.copy_artifact(
                container_id=build_id,
                artifact_path=artifact_path,
                dest_path=os.path.join(dest_dir, os.path.basename(artifact_path)),
            )
            artifacts.append(artifact)

        return artifacts

    async def archive_artifacts(
        self,
        artifact_dir: str,
        archive_name: str,
    ) -> Optional[str]:
        """Create tar.gz archive of artifacts"""
        try:
            archive_path = os.path.join(
                os.path.dirname(artifact_dir),
                archive_name
            )

            with tarfile.open(archive_path, "w:gz") as tar:
                tar.add(artifact_dir, arcname=os.path.basename(artifact_dir))

            return archive_path

        except Exception as e:
            logger.error(f"Error archiving artifacts: {e}")
            return None

    # Multi-Language Support Methods

    def generate_dockerfile(self, config: LanguageConfig) -> str:
        """Generate Dockerfile for language configuration"""
        language = config.language.lower()

        if language == "python":
            return self._generate_python_dockerfile(config)
        elif language == "nodejs":
            return self._generate_nodejs_dockerfile(config)
        elif language == "go":
            return self._generate_go_dockerfile(config)
        else:
            raise ValueError(f"Unsupported language: {language}")

    def _generate_python_dockerfile(self, config: LanguageConfig) -> str:
        """Generate Python Dockerfile"""
        base_image = f"python:{config.version}-slim"

        if config.multi_stage:
            dockerfile = self.dockerfile_templates["python_agent"].replace(
                "python:3.11-slim",
                base_image
            )

            # Add specific dependencies if provided
            if config.dependencies:
                deps_str = " ".join([f"{k}=={v}" for k, v in config.dependencies.items()])
                dockerfile = dockerfile.replace(
                    "RUN pip install --no-cache-dir -r requirements.txt",
                    f"RUN pip install --no-cache-dir -r requirements.txt {deps_str}"
                )

            return dockerfile
        else:
            deps_line = ""
            if config.dependencies:
                deps_str = " ".join([f"{k}=={v}" for k, v in config.dependencies.items()])
                deps_line = f"\nRUN pip install --no-cache-dir {deps_str}"

            return f"""
FROM {base_image}
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt{deps_line}
COPY . .
CMD ["python", "main.py"]
"""

    def _generate_nodejs_dockerfile(self, config: LanguageConfig) -> str:
        """Generate Node.js Dockerfile"""
        base_image = f"node:{config.version}-alpine"

        if config.multi_stage:
            return self.dockerfile_templates["node_agent"].replace(
                "node:18-alpine",
                base_image
            )
        else:
            return f"""
FROM {base_image}
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["node", "index.js"]
"""

    def _generate_go_dockerfile(self, config: LanguageConfig) -> str:
        """Generate Go Dockerfile"""
        base_image = f"golang:{config.version}-alpine"

        if config.multi_stage:
            return self.dockerfile_templates["go_agent"].replace(
                "golang:1.21-alpine",
                base_image
            )
        else:
            return f"""
FROM {base_image}
WORKDIR /app
COPY . .
RUN go build -o main .
CMD ["./main"]
"""

    # Parallel Build Methods

    async def build_agent_image(
        self,
        agent_type: str,
        agent_config: Dict[str, Any]
    ) -> DaggerBuildResult:
        """Build container image for a specific agent"""
        context_id = f"agent_{agent_type}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"

        # Generate Dockerfile
        dockerfile_content = self.generate_agent_dockerfile(agent_type, agent_config)

        # Create build context
        context = DaggerBuildContext(
            id=context_id,
            name=f"openclaw-{agent_type}-agent",
            source_path=agent_config.get('source_path', '/app'),
            dockerfile_content=dockerfile_content,
            build_args={
                'AGENT_TYPE': agent_type,
                'PORT': str(agent_config.get('port', 8000)),
                'ENVIRONMENT': agent_config.get('environment', 'production')
            },
            environment_vars={
                'BUILDKIT_INLINE_CACHE': '1',
                'DOCKER_BUILDKIT': '1'
            },
            secrets=agent_config.get('secrets', {}),
            platform=agent_config.get('platform', 'linux/amd64')
        )

        return await self.build_image(context)

    def generate_agent_dockerfile(
        self,
        agent_type: str,
        config: Dict[str, Any]
    ) -> str:
        """Generate Dockerfile for specific agent type"""
        if agent_type == "orchestrator":
            return self.dockerfile_templates["multi_agent_orchestrator"]

        language = config.get("language", "python")

        if language == "python":
            return self.dockerfile_templates["python_agent"]
        elif language == "nodejs":
            return self.dockerfile_templates["node_agent"]
        elif language == "go":
            return self.dockerfile_templates["go_agent"]
        else:
            return self.dockerfile_templates["python_agent"]

    async def parallel_build_agents(
        self,
        agent_configs: Dict[str, Dict[str, Any]]
    ) -> Dict[str, DaggerBuildResult]:
        """Build multiple agent images in parallel"""
        logger.info(f"Starting parallel build for {len(agent_configs)} agents")

        # Create build tasks
        build_tasks = {}
        for agent_type, config in agent_configs.items():
            task = asyncio.create_task(
                self.build_agent_image(agent_type, config),
                name=f"build_{agent_type}"
            )
            build_tasks[agent_type] = task

        # Execute builds with timeout
        results = {}
        try:
            completed_tasks = await asyncio.wait_for(
                asyncio.gather(*build_tasks.values(), return_exceptions=True),
                timeout=self.config.build_timeout
            )

            for agent_type, result in zip(agent_configs.keys(), completed_tasks):
                if isinstance(result, Exception):
                    logger.error(f"Build failed for {agent_type}: {result}")
                    results[agent_type] = DaggerBuildResult(
                        id=f"failed_{agent_type}",
                        image_id="",
                        image_size=0,
                        build_time=0,
                        cache_hits=0,
                        cache_misses=0,
                        success=False,
                        error_message=str(result)
                    )
                else:
                    results[agent_type] = result

        except asyncio.TimeoutError:
            logger.error("Parallel build timed out")

            # Cancel remaining tasks
            for task in build_tasks.values():
                if not task.done():
                    task.cancel()

            # Return partial results
            for agent_type in agent_configs.keys():
                if agent_type not in results:
                    results[agent_type] = DaggerBuildResult(
                        id=f"timeout_{agent_type}",
                        image_id="",
                        image_size=0,
                        build_time=0,
                        cache_hits=0,
                        cache_misses=0,
                        success=False,
                        error_message="Build timed out"
                    )

        successful = sum(1 for r in results.values() if r.success)
        logger.info(f"Parallel build completed: {successful}/{len(agent_configs)} successful")

        return results

    # Cache Optimization Methods

    async def optimize_cache(self) -> Dict[str, Any]:
        """Optimize build cache"""
        try:
            cache_stats = {
                'total_cached_builds': len(self.build_cache),
                'cache_hits': 0,
                'cache_efficiency': 0.0,
                'cleanup_performed': False
            }

            # Calculate efficiency
            if self.build_cache:
                total_builds = len(self.build_cache)
                cache_stats['cache_efficiency'] = min(100.0, (total_builds / 10) * 100)

            # Clean up old entries (>24 hours)
            cutoff_time = datetime.utcnow() - timedelta(hours=24)
            old_entries = [
                key for key, value in self.build_cache.items()
                if value.get('created_at', datetime.utcnow()) < cutoff_time
            ]

            for key in old_entries:
                del self.build_cache[key]
                cache_stats['cleanup_performed'] = True

            logger.info(f"Cache optimization completed: {cache_stats}")
            return cache_stats

        except Exception as e:
            logger.error(f"Cache optimization error: {e}")
            return {'error': str(e)}

    # Cleanup Methods

    async def cleanup_workspace(self, older_than_hours: int = 24):
        """Clean up old build workspaces"""
        try:
            cutoff_time = datetime.utcnow() - timedelta(hours=older_than_hours)

            for build_dir in self.workspace_dir.iterdir():
                if build_dir.is_dir():
                    mtime = datetime.fromtimestamp(build_dir.stat().st_mtime)
                    if mtime < cutoff_time:
                        shutil.rmtree(build_dir)
                        logger.info(f"Cleaned up workspace: {build_dir}")

        except Exception as e:
            logger.error(f"Workspace cleanup error: {e}")

    async def cleanup_dangling_images(self) -> int:
        """Clean up dangling Docker images"""
        try:
            cmd = ["docker", "image", "prune", "-f"]
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.wait()
            return 0  # Docker doesn't provide count
        except Exception as e:
            logger.error(f"Image cleanup error: {e}")
            return 0

    async def full_cleanup(self) -> Dict[str, Any]:
        """Perform full cleanup of all resources"""
        result = {}

        result['workspace'] = await self.cleanup_workspace(older_than_hours=24)
        result['containers'] = await self.cleanup_containers()
        result['images'] = await self.cleanup_dangling_images()

        return result

    # Metrics Methods

    def get_build_metrics(self) -> Dict[str, Any]:
        """Get comprehensive build metrics"""
        total_builds = len(self.build_cache)
        successful_builds = sum(
            1 for cache in self.build_cache.values()
            if cache.get('success', False)
        )

        if total_builds > 0:
            success_rate = (successful_builds / total_builds) * 100
            avg_build_time = sum(
                cache.get('build_time', 0)
                for cache in self.build_cache.values()
            ) / total_builds
        else:
            success_rate = 0.0
            avg_build_time = 0.0

        return {
            'total_builds': total_builds,
            'successful_builds': successful_builds,
            'success_rate': success_rate,
            'average_build_time': avg_build_time,
            'cache_strategy': self.config.cache_strategy.value,
            'engine': self.config.engine.value,
            'active_builds': len(self.active_builds)
        }


# Factory function for service creation

def get_dagger_builder_service(config: Optional[DaggerConfig] = None) -> DaggerBuilderService:
    """
    Get or create DaggerBuilderService instance

    Args:
        config: Optional configuration, uses defaults if None

    Returns:
        DaggerBuilderService instance
    """
    try:
        service = DaggerBuilderService(config)
        logger.info("DaggerBuilderService initialized successfully")
        return service
    except Exception as e:
        logger.error(f"Failed to initialize DaggerBuilderService: {e}")
        raise
