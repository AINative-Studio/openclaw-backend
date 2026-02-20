# GitHub Integration Endpoint Documentation

## Overview

This document describes the GitHub integration endpoint for AgentSwarm projects, implemented for **Issue #235**.

## Endpoint

```
GET /api/v1/public/agent-swarms/projects/{project_id}/github
```

## Description

Fetches comprehensive GitHub integration data for an AgentSwarm project, including repository information, issue statistics, pull request metrics, commit history, and CI/CD build status.

## Authentication

**Required**: Valid user authentication token (JWT Bearer token)

## Path Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | UUID | Yes | Unique identifier of the AgentSwarm project |

## Request Example

```bash
curl -X GET "https://api.ainative.studio/api/v1/public/agent-swarms/projects/550e8400-e29b-41d4-a716-446655440000/github" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

## Response Schema

### Success Response (200 OK)

```json
{
  "repo_url": "https://github.com/user/project",
  "repo_name": "user/project",
  "issues_created": 45,
  "issues_closed": 12,
  "pull_requests_total": 15,
  "pull_requests_merged": 15,
  "pull_requests_open": 0,
  "last_commit_at": "2025-12-05T10:30:00Z",
  "branch": "main",
  "build_status": "success"
}
```

### Response Fields

| Field | Type | Description | Default |
|-------|------|-------------|---------|
| `repo_url` | string (nullable) | Full GitHub repository URL | `null` |
| `repo_name` | string (nullable) | Repository name in format "owner/repo" | `null` |
| `issues_created` | integer | Total number of issues created | `0` |
| `issues_closed` | integer | Number of closed issues | `0` |
| `pull_requests_total` | integer | Total pull requests | `0` |
| `pull_requests_merged` | integer | Number of merged pull requests | `0` |
| `pull_requests_open` | integer | Number of open pull requests | `0` |
| `last_commit_at` | string (nullable) | ISO 8601 timestamp of last commit | `null` |
| `branch` | string | Default branch name | `"main"` |
| `build_status` | string | Build status: `success`, `pending`, `running`, `failed`, `unknown` | `"unknown"` |

## Error Responses

### 404 Not Found

**Scenario**: Project doesn't exist or has no GitHub integration

```json
{
  "detail": "Project 550e8400-e29b-41d4-a716-446655440000 not found or has no GitHub integration"
}
```

### 401 Unauthorized

**Scenario**: Missing or invalid authentication token

```json
{
  "detail": "Could not validate credentials"
}
```

### 403 Forbidden

**Scenario**: User doesn't have access to the project

```json
{
  "detail": "Unauthorized access to project"
}
```

### 500 Internal Server Error

**Scenario**: Unexpected server error

```json
{
  "detail": "Failed to fetch GitHub integration status: Database connection failed"
}
```

## Implementation Details

### Data Sources

The endpoint retrieves data from two sources:

1. **Database** (always available):
   - Repository URL and name
   - Default branch
   - Imported issues count
   - Basic GitHub integration metadata

2. **GitHub API** (optional, requires GitHub token):
   - Live issue counts (created/closed)
   - Pull request statistics
   - Latest commit timestamp
   - CI/CD build status from GitHub Actions

### Performance

- **Target Response Time**: < 500ms
- **Timeout**: 10 seconds for GitHub API calls
- **Caching**: Not implemented (future enhancement)

### Authentication Flow

```
1. User sends request with JWT token
2. System validates JWT and extracts user_id
3. System checks if user has GitHub token configured
4. If GitHub token exists:
   - Fetch live data from GitHub API
   - Merge with database data
5. Else:
   - Return database data only
6. Return combined response
```

### Build Status Mapping

GitHub Actions workflow status → Build status:

| GitHub Status | Conclusion | Build Status |
|---------------|------------|--------------|
| `completed` | `success` | `success` |
| `completed` | `failure`, `timed_out`, `cancelled` | `failed` |
| `queued`, `in_progress` | - | `running` |
| Not available | - | `unknown` |

## Usage Examples

### JavaScript/TypeScript

```typescript
async function getProjectGitHubStatus(projectId: string): Promise<GitHubStatus> {
  const response = await fetch(
    `https://api.ainative.studio/api/v1/public/agent-swarms/projects/${projectId}/github`,
    {
      headers: {
        'Authorization': `Bearer ${getAuthToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    if (response.status === 404) {
      throw new Error('Project not found or has no GitHub integration');
    }
    throw new Error(`Failed to fetch GitHub status: ${response.statusText}`);
  }

  return await response.json();
}
```

### Python

```python
import requests
from typing import Optional, Dict, Any

def get_project_github_status(
    project_id: str,
    auth_token: str
) -> Optional[Dict[str, Any]]:
    """Fetch GitHub integration status for a project"""
    url = f"https://api.ainative.studio/api/v1/public/agent-swarms/projects/{project_id}/github"

    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }

    response = requests.get(url, headers=headers)

    if response.status_code == 404:
        return None  # No GitHub integration

    response.raise_for_status()
    return response.json()
```

### cURL

```bash
# Basic request
curl -X GET \
  "https://api.ainative.studio/api/v1/public/agent-swarms/projects/550e8400-e29b-41d4-a716-446655440000/github" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"

# With error handling
curl -X GET \
  "https://api.ainative.studio/api/v1/public/agent-swarms/projects/550e8400-e29b-41d4-a716-446655440000/github" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -w "\nHTTP Status: %{http_code}\n" \
  -s -o response.json

# Check if project has GitHub integration
http_code=$(curl -X GET \
  "https://api.ainative.studio/api/v1/public/agent-swarms/projects/550e8400-e29b-41d4-a716-446655440000/github" \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -w "%{http_code}" \
  -o /dev/null -s)

if [ "$http_code" -eq 200 ]; then
  echo "GitHub integration found"
elif [ "$http_code" -eq 404 ]; then
  echo "No GitHub integration"
else
  echo "Error: HTTP $http_code"
fi
```

## Testing

### Unit Tests

Run the comprehensive test suite:

```bash
cd /Users/aideveloper/core/src/backend
python3 test_github_endpoint_standalone.py
```

### Manual Testing

1. **Test with existing GitHub integration**:
   ```bash
   curl -X GET "http://localhost:8000/api/v1/public/agent-swarms/projects/{valid_project_id}/github" \
     -H "Authorization: Bearer {valid_token}"
   ```

2. **Test without GitHub integration**:
   ```bash
   curl -X GET "http://localhost:8000/api/v1/public/agent-swarms/projects/{project_without_github}/github" \
     -H "Authorization: Bearer {valid_token}"
   ```
   Expected: 404 error

3. **Test with invalid authentication**:
   ```bash
   curl -X GET "http://localhost:8000/api/v1/public/agent-swarms/projects/{project_id}/github" \
     -H "Authorization: Bearer invalid_token"
   ```
   Expected: 401 error

## Database Schema

### Related Tables

1. **agent_swarm_workflows**
   - Links projects to workflow orchestration
   - Contains workflow status and progress

2. **github_integrations**
   - Stores GitHub repository information
   - Contains encrypted PAT (Personal Access Token)
   - Tracks issue import status

3. **user_github_settings**
   - Stores user-specific GitHub tokens
   - Enables live API data fetching

### Entity Relationship

```
Project → AgentSwarmWorkflow → GitHubIntegration
User → UserGitHubSettings (for live API access)
```

## Security Considerations

1. **Token Encryption**: GitHub PATs are encrypted before storage
2. **Rate Limiting**: GitHub API calls respect rate limits (not implemented yet)
3. **Error Handling**: Sensitive information is not exposed in error messages
4. **Authentication**: All requests require valid JWT tokens
5. **Authorization**: Users can only access their own projects (to be implemented)

## Future Enhancements

1. **Caching**: Implement Redis caching for GitHub API responses (5-minute TTL)
2. **Rate Limiting**: Add per-user rate limiting for API calls
3. **Webhooks**: Real-time updates via GitHub webhooks
4. **Repository Health**: Add code quality metrics (test coverage, security alerts)
5. **Commit Analytics**: Detailed commit history and contributor statistics
6. **Project Authorization**: Verify user has access to requested project
7. **Pagination**: Support for projects with 100+ issues/PRs

## Troubleshooting

### Common Issues

**Issue**: Endpoint returns 404 for valid project
- **Cause**: Project has no GitHub integration configured
- **Solution**: Complete Step 6 (GitHub Setup) in AgentSwarm workflow

**Issue**: Build status always shows "unknown"
- **Cause**: No GitHub Actions workflows in repository
- **Solution**: Add GitHub Actions workflow file to repository

**Issue**: Live data not updating
- **Cause**: User has no GitHub token configured
- **Solution**: Configure GitHub token in user settings

**Issue**: Slow response times (> 500ms)
- **Cause**: GitHub API latency
- **Solution**: Implement caching (future enhancement)

## Support

For issues or questions:
- Create an issue in the GitHub repository
- Contact the backend team
- Review the AgentSwarm workflow documentation

## Changelog

### Version 1.0.0 (2025-12-05)
- Initial implementation
- Support for database-stored GitHub metadata
- Live GitHub API integration
- Comprehensive error handling
- Response schema validation
- Unit test coverage

---

**Endpoint Location**: `/Users/aideveloper/core/src/backend/app/api/api_v1/endpoints/agent_swarms.py`

**Service Location**: `/Users/aideveloper/core/src/backend/app/services/project_github_service.py`

**Tests Location**: `/Users/aideveloper/core/src/backend/test_github_endpoint_standalone.py`
