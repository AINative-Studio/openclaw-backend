# Dagger Builder Service

## Overview

The Dagger Builder Service provides comprehensive containerization capabilities for the OpenClaw multi-agent system. It enables container lifecycle management, test execution in isolated environments, build artifact management, and multi-language support.

## Migration from Core Repository

This service was migrated from `/Users/aideveloper/core/src/backend/app/agents/swarm/dagger_integration.py` (741 lines) to the OpenClaw backend repository following TDD principles.

**Migration Date:** March 8, 2026
**Issue:** #111
**Source Lines:** 741
**Target File:** `backend/services/dagger_builder_service.py`
**Test Coverage:** 84% (70 tests)

## Features

### 1. Container Lifecycle Management
- **Build Images:** Async container image building with BuildKit optimization
- **Run Containers:** Execute containers with resource limits and volume mounts
- **Stop/Remove:** Graceful container shutdown and cleanup
- **Health Monitoring:** Container health checks and status tracking

### 2. Test Execution
- **Isolated Testing:** Run tests in clean, disposable containers
- **Multi-Language:** Python (pytest), Node.js (npm test), Go (go test)
- **Coverage Reporting:** Parse and track test coverage metrics
- **Test Parallelization:** Run multiple test suites concurrently

### 3. Build Artifact Management
- **Artifact Extraction:** Copy build outputs from containers to host
- **Archiving:** Create tar.gz archives of build artifacts
- **Size Tracking:** Monitor artifact sizes and storage usage

### 4. Multi-Language Support
- **Python:** Multi-stage builds with pip dependency caching
- **Node.js:** npm/pnpm support with production optimizations
- **Go:** CGO-enabled builds with Alpine-based production images
- **Dockerfile Generation:** Language-specific templates with best practices

### 5. Resource Limits
- **CPU Limits:** Configurable CPU allocation per container
- **Memory Limits:** Memory caps to prevent OOM conditions
- **Timeouts:** Per-operation timeout enforcement
- **Cleanup:** Automatic resource cleanup after timeout/failure

### 6. Parallel Builds
- **Concurrent Execution:** Build multiple images simultaneously
- **Semaphore Control:** Limit parallel build count
- **Timeout Handling:** Individual build timeouts with partial results
- **Error Isolation:** One build failure doesn't stop others

### 7. Cache Optimization
- **BuildKit Cache:** Local and registry-based caching
- **Cache Hit Tracking:** Monitor cache effectiveness
- **Old Entry Cleanup:** Remove stale cache entries (>24 hours)
- **Efficiency Metrics:** Calculate cache hit ratio

## Architecture

### Class Structure

```
DaggerBuilderService
├── Configuration
│   ├── DaggerConfig (engine, cache strategy, timeouts)
│   ├── ResourceLimits (CPU, memory, timeout)
│   └── LanguageConfig (language, version, dependencies)
├── Build Management
│   ├── build_image() - Main build orchestration
│   ├── _generate_build_command() - Engine-specific commands
│   ├── _execute_build() - Build execution with monitoring
│   └── _get_image_info() - Image metadata retrieval
├── Container Execution
│   ├── run_container() - Execute with resource limits
│   ├── stop_container() - Graceful shutdown
│   ├── remove_container() - Container cleanup
│   └── cleanup_containers() - Batch cleanup
├── Test Execution
│   ├── run_tests() - Test orchestration
│   ├── _generate_test_dockerfile() - Language-specific test setup
│   └── _parse_test_output() - Extract test metrics
├── Artifact Management
│   ├── copy_artifact() - Single artifact extraction
│   ├── extract_artifacts() - Batch extraction
│   └── archive_artifacts() - Create tar.gz archives
├── Multi-Language
│   ├── generate_dockerfile() - Language-aware generation
│   ├── _generate_python_dockerfile()
│   ├── _generate_nodejs_dockerfile()
│   └── _generate_go_dockerfile()
├── Parallel Builds
│   ├── build_agent_image() - Single agent build
│   ├── parallel_build_agents() - Concurrent builds
│   └── generate_agent_dockerfile() - Agent-specific templates
├── Cache & Cleanup
│   ├── optimize_cache() - Cache maintenance
│   ├── cleanup_workspace() - Build directory cleanup
│   ├── cleanup_dangling_images() - Prune unused images
│   └── full_cleanup() - Complete cleanup
└── Metrics
    └── get_build_metrics() - Comprehensive statistics
```

### Data Models

#### Configuration Models
- `DaggerConfig`: Service configuration (engine, cache, timeouts)
- `ResourceLimits`: Container resource constraints
- `LanguageConfig`: Language-specific settings

#### Context Models
- `DaggerBuildContext`: Build context with Dockerfile and settings
- `DaggerBuildResult`: Build outcome with metrics
- `ContainerRunResult`: Container execution result
- `TestExecutionResult`: Test run metrics and coverage
- `BuildArtifact`: Artifact metadata

### Supported Engines

1. **BuildKit** (Recommended)
   - Advanced caching with layer deduplication
   - Registry and local cache backends
   - Parallel build steps
   - Secrets management

2. **Docker**
   - Standard Docker build
   - Basic layer caching
   - Wide compatibility

3. **Podman**
   - Rootless containers
   - Docker-compatible API
   - Enhanced security

## Usage Examples

### Basic Image Build

```python
from backend.services.dagger_builder_service import (
    DaggerBuilderService,
    DaggerConfig,
    DaggerEngine,
    BuildCacheStrategy,
    DaggerBuildContext,
)

# Initialize service
config = DaggerConfig(
    engine=DaggerEngine.BUILDKIT,
    cache_strategy=BuildCacheStrategy.LOCAL,
    build_timeout=1800,
)
service = DaggerBuilderService(config)

# Create build context
context = DaggerBuildContext(
    id="my_build_001",
    name="my-app",
    source_path="/path/to/source",
    dockerfile_content="FROM python:3.11-slim\nCOPY . /app",
    build_args={"PYTHON_VERSION": "3.11"},
    environment_vars={"PYTHONUNBUFFERED": "1"},
    secrets={},
)

# Build image
result = await service.build_image(context)

if result.success:
    print(f"✓ Built {result.image_id} in {result.build_time:.2f}s")
    print(f"  Cache hits: {result.cache_hits}")
    print(f"  Cache misses: {result.cache_misses}")
else:
    print(f"✗ Build failed: {result.error_message}")
```

### Run Tests in Container

```python
# Configure test execution
test_config = {
    "language": "python",
    "test_command": "pytest tests/ -v --cov=app",
    "requirements": "pytest pytest-cov",
    "coverage_threshold": 80.0,
}

# Run tests
result = await service.run_tests(
    source_path="/path/to/source",
    test_config=test_config,
)

if result.success:
    print(f"✓ Tests passed: {result.tests_passed}")
    print(f"  Coverage: {result.coverage_percent}%")
else:
    print(f"✗ Tests failed: {result.tests_failed}")
```

### Parallel Agent Builds

```python
# Define agent configurations
agent_configs = {
    "frontend": {
        "language": "nodejs",
        "port": 3000,
        "source_path": "/app/frontend",
    },
    "backend": {
        "language": "python",
        "port": 8000,
        "source_path": "/app/backend",
    },
    "worker": {
        "language": "python",
        "port": 8001,
        "source_path": "/app/worker",
    },
}

# Build all agents in parallel
results = await service.parallel_build_agents(agent_configs)

for agent, result in results.items():
    status = "✓" if result.success else "✗"
    print(f"{status} {agent}: {result.build_time:.2f}s")
```

### Container Execution with Resource Limits

```python
from backend.services.dagger_builder_service import ResourceLimits

# Define resource limits
limits = ResourceLimits(
    cpu_limit="2.0",          # 2 CPUs
    memory_limit="2g",        # 2GB RAM
    timeout_seconds=300,      # 5 minutes
)

# Run container
result = await service.run_container(
    image_name="my-app:latest",
    command=["python", "script.py"],
    environment_vars={"ENV": "production"},
    resource_limits=limits,
    volumes={
        "/host/data": "/container/data",
    },
)

print(f"Exit code: {result.exit_code}")
print(f"Duration: {result.duration:.2f}s")
```

### Build Artifact Extraction

```python
# Extract build artifacts
artifacts = await service.extract_artifacts(
    build_id="build_123",
    artifact_paths=[
        "/app/dist/bundle.js",
        "/app/dist/bundle.css",
        "/app/dist/index.html",
    ],
    dest_dir="/output/artifacts",
)

# Archive artifacts
archive_path = await service.archive_artifacts(
    artifact_dir="/output/artifacts",
    archive_name="build-artifacts.tar.gz",
)
```

### Multi-Language Dockerfile Generation

```python
from backend.services.dagger_builder_service import LanguageConfig

# Python application
python_config = LanguageConfig(
    language="python",
    version="3.11",
    dependencies={"fastapi": "0.104.1", "pydantic": "2.0.0"},
    multi_stage=True,
)
python_dockerfile = service.generate_dockerfile(python_config)

# Node.js application
nodejs_config = LanguageConfig(
    language="nodejs",
    version="18",
    dependencies={"express": "^4.18.0"},
    multi_stage=True,
)
nodejs_dockerfile = service.generate_dockerfile(nodejs_config)

# Go application
go_config = LanguageConfig(
    language="go",
    version="1.21",
    multi_stage=True,
)
go_dockerfile = service.generate_dockerfile(go_config)
```

## Cache Strategies

### Local Cache (Default)
- Stores cache in `/tmp/buildkit-cache`
- Fast access, no network overhead
- Lost on system reboot

```python
config = DaggerConfig(
    engine=DaggerEngine.BUILDKIT,
    cache_strategy=BuildCacheStrategy.LOCAL,
)
```

### Registry Cache
- Stores cache in container registry
- Shared across machines
- Requires registry authentication

```python
config = DaggerConfig(
    engine=DaggerEngine.BUILDKIT,
    cache_strategy=BuildCacheStrategy.REGISTRY,
    cache_registry="gcr.io/my-project/cache",
)
```

### Inline Cache
- Embeds cache in image layers
- Good for CI/CD pipelines
- Larger image sizes

```python
config = DaggerConfig(
    engine=DaggerEngine.BUILDKIT,
    cache_strategy=BuildCacheStrategy.INLINE,
)
```

### No Cache
- Always rebuild from scratch
- Useful for debugging
- Slowest option

```python
config = DaggerConfig(
    engine=DaggerEngine.BUILDKIT,
    cache_strategy=BuildCacheStrategy.DISABLED,
)
```

## Metrics and Monitoring

### Build Metrics

```python
metrics = service.get_build_metrics()

print(f"Total builds: {metrics['total_builds']}")
print(f"Successful: {metrics['successful_builds']}")
print(f"Success rate: {metrics['success_rate']:.1f}%")
print(f"Avg build time: {metrics['average_build_time']:.2f}s")
print(f"Cache strategy: {metrics['cache_strategy']}")
print(f"Engine: {metrics['engine']}")
print(f"Active builds: {metrics['active_builds']}")
```

### Cache Optimization

```python
# Optimize cache (removes old entries)
stats = await service.optimize_cache()

print(f"Cached builds: {stats['total_cached_builds']}")
print(f"Cache efficiency: {stats['cache_efficiency']:.1f}%")
print(f"Cleanup performed: {stats['cleanup_performed']}")
```

## Cleanup Operations

### Workspace Cleanup
```python
# Remove old build directories (>24 hours)
await service.cleanup_workspace(older_than_hours=24)
```

### Container Cleanup
```python
# Remove all containers with prefix
result = await service.cleanup_containers(prefix="test-")
print(f"Cleaned {result['cleaned']} containers")
```

### Image Cleanup
```python
# Prune dangling images
await service.cleanup_dangling_images()
```

### Full Cleanup
```python
# Clean everything
result = await service.full_cleanup()
print(f"Workspace: {result['workspace']}")
print(f"Containers: {result['containers']['cleaned']}")
print(f"Images: {result['images']}")
```

## Error Handling

The service uses comprehensive error handling with graceful degradation:

```python
try:
    result = await service.build_image(context)
    if not result.success:
        # Build failed, check error
        logger.error(f"Build failed: {result.error_message}")
        # Logs available in result.build_logs
        for log in result.build_logs:
            print(log)
except Exception as e:
    # Catastrophic failure
    logger.exception(f"Unexpected error: {e}")
```

## Best Practices

### 1. Use BuildKit Engine
BuildKit provides the best performance and caching:
```python
config = DaggerConfig(
    engine=DaggerEngine.BUILDKIT,
    cache_strategy=BuildCacheStrategy.LOCAL,
)
```

### 2. Enable Debug Mode During Development
```python
config = DaggerConfig(
    engine=DaggerEngine.BUILDKIT,
    cache_strategy=BuildCacheStrategy.LOCAL,
    enable_debug=True,  # Logs all build output
)
```

### 3. Set Appropriate Timeouts
```python
config = DaggerConfig(
    engine=DaggerEngine.BUILDKIT,
    cache_strategy=BuildCacheStrategy.LOCAL,
    build_timeout=3600,  # 1 hour for large builds
)
```

### 4. Use Multi-Stage Builds
Multi-stage builds reduce image size and improve security:
```python
config = LanguageConfig(
    language="python",
    version="3.11",
    multi_stage=True,  # Enable multi-stage
)
```

### 5. Clean Up Regularly
```python
# Schedule periodic cleanup
await service.optimize_cache()
await service.cleanup_workspace(older_than_hours=24)
await service.cleanup_dangling_images()
```

### 6. Monitor Build Metrics
```python
metrics = service.get_build_metrics()
if metrics['success_rate'] < 90:
    logger.warning("Build success rate below 90%!")
```

## Testing

The service has comprehensive test coverage (84%) with 70 tests covering:

- Configuration and initialization
- Build lifecycle (success and failure)
- Container execution with resource limits
- Test execution for Python, Node.js, and Go
- Artifact extraction and archiving
- Multi-language Dockerfile generation
- Parallel builds with timeout handling
- Cache optimization
- Resource limits enforcement
- Cleanup operations
- Error handling and edge cases

Run tests:
```bash
pytest tests/services/test_dagger_builder_service.py -v
```

Run with coverage:
```bash
pytest tests/services/test_dagger_builder_service.py --cov=backend.services.dagger_builder_service --cov-report=term
```

## Integration with OpenClaw

### Task Execution
```python
# Build task execution environment
task_context = DaggerBuildContext(
    id=f"task_{task_id}",
    name=f"task-{task_type}",
    source_path=task_source,
    dockerfile_content=task_dockerfile,
    build_args=task.build_args,
    environment_vars=task.env_vars,
    secrets=task.secrets,
)

result = await service.build_image(task_context)
```

### Agent Deployment
```python
# Deploy agent swarm
agents = ["architect", "frontend", "backend", "qa"]
agent_configs = {
    agent: {
        "language": "python",
        "port": 8000 + i,
        "source_path": f"/agents/{agent}",
    }
    for i, agent in enumerate(agents)
}

results = await service.parallel_build_agents(agent_configs)
```

## Performance Considerations

### Build Performance
- **BuildKit cache:** 5-10x faster on cache hits
- **Parallel builds:** Linear scaling up to CPU count
- **Multi-stage builds:** 30-50% smaller images

### Resource Usage
- **Memory:** ~100MB base + build memory
- **Disk:** Cache size depends on image count
- **CPU:** Scales with max_parallelism setting

## Troubleshooting

### Build Failures
```python
if not result.success:
    print("Build logs:")
    for log in result.build_logs:
        print(log)
```

### Cache Issues
```python
# Clear cache and rebuild
config.cache_strategy = BuildCacheStrategy.DISABLED
result = await service.build_image(context)
```

### Resource Exhaustion
```python
# Reduce parallelism
config.max_parallelism = 2

# Add resource limits
limits = ResourceLimits(
    cpu_limit="1.0",
    memory_limit="1g",
)
```

## Future Enhancements

1. **Container Registry Integration**
   - Push built images to registries
   - Pull from private registries with authentication

2. **Build Queue Management**
   - Priority-based build scheduling
   - Build result caching and reuse

3. **Security Scanning**
   - Vulnerability scanning with Trivy/Grype
   - SBOM generation

4. **Build Reproducibility**
   - Deterministic builds with locked dependencies
   - Build provenance tracking

5. **Advanced Caching**
   - Content-addressable storage
   - Remote build execution

## Related Documentation

- [OpenClaw Architecture](/docs/ARCHITECTURE.md)
- [Task Assignment](/docs/TASK_ASSIGNMENT.md)
- [Agent Lifecycle](/docs/AGENT_LIFECYCLE.md)
- [Testing Guide](/docs/TESTING.md)

## Support

For issues or questions:
- GitHub Issues: [OpenClaw Backend Issues](https://github.com/your-org/openclaw-backend/issues)
- Documentation: `/docs/DAGGER_BUILDER_SERVICE.md`
- Tests: `/tests/services/test_dagger_builder_service.py`
