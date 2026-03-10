"""
GitHub API Client

Async wrapper for GitHub REST API operations.
Supports issue querying, label management, and comment creation.

Refs #141
"""

import logging
from typing import List, Dict, Any, Optional
import httpx
from datetime import datetime, timezone

# Configure logging
logger = logging.getLogger(__name__)


class GitHubAPIError(Exception):
    """Base exception for GitHub API errors"""
    pass


class GitHubAuthenticationError(GitHubAPIError):
    """Raised when authentication fails"""
    pass


class GitHubRateLimitError(GitHubAPIError):
    """Raised when rate limit is exceeded"""
    pass


class GitHubClient:
    """
    GitHub API Client

    Provides async methods for interacting with GitHub REST API.
    Handles authentication, rate limiting, and error handling.
    """

    def __init__(
        self,
        token: str,
        repository: str,
        base_url: str = "https://api.github.com",
        timeout_seconds: int = 30,
    ):
        """
        Initialize GitHub client

        Args:
            token: GitHub personal access token or app token
            repository: Repository in format "owner/repo"
            base_url: GitHub API base URL (default: public GitHub)
            timeout_seconds: Request timeout (default: 30)
        """
        self.token = token
        self.repository = repository
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds

        # Parse repository
        parts = repository.split("/")
        if len(parts) != 2:
            raise ValueError(f"Invalid repository format: {repository}. Expected 'owner/repo'")

        self.owner = parts[0]
        self.repo = parts[1]

        # Configure HTTP client
        self.client = httpx.AsyncClient(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=timeout_seconds,
        )

        logger.info(
            f"GitHubClient initialized for repository {repository}",
            extra={"repository": repository}
        )

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()

    async def __aenter__(self):
        """Async context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.close()

    async def get_issues(
        self,
        state: str = "open",
        labels: Optional[str] = None,
        assignee: Optional[str] = None,
        per_page: int = 100,
        page: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Get issues from repository

        Args:
            state: Issue state ("open", "closed", "all")
            labels: Comma-separated label names to filter by
            assignee: Filter by assignee username
            per_page: Results per page (max 100)
            page: Page number

        Returns:
            List of issue dictionaries

        Raises:
            GitHubAPIError: If API request fails
        """
        endpoint = f"/repos/{self.owner}/{self.repo}/issues"

        params = {
            "state": state,
            "per_page": min(per_page, 100),
            "page": page,
        }

        if labels:
            params["labels"] = labels

        if assignee:
            params["assignee"] = assignee

        try:
            response = await self.client.get(endpoint, params=params)
            self._check_response(response)

            issues = response.json()

            logger.info(
                f"Fetched {len(issues)} issues from {self.repository}",
                extra={
                    "repository": self.repository,
                    "issue_count": len(issues),
                    "state": state,
                    "labels": labels,
                }
            )

            return issues

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to fetch issues: {e}",
                extra={"error": str(e), "repository": self.repository}
            )
            raise GitHubAPIError(f"Failed to fetch issues: {e}")

    async def get_issue(self, issue_number: int) -> Dict[str, Any]:
        """
        Get single issue by number

        Args:
            issue_number: Issue number

        Returns:
            Issue dictionary

        Raises:
            GitHubAPIError: If API request fails
        """
        endpoint = f"/repos/{self.owner}/{self.repo}/issues/{issue_number}"

        try:
            response = await self.client.get(endpoint)
            self._check_response(response)

            issue = response.json()

            logger.debug(
                f"Fetched issue #{issue_number}",
                extra={"issue_number": issue_number}
            )

            return issue

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to fetch issue #{issue_number}: {e}",
                extra={"error": str(e), "issue_number": issue_number}
            )
            raise GitHubAPIError(f"Failed to fetch issue: {e}")

    async def add_label(
        self,
        issue_number: int,
        label: str,
    ) -> Dict[str, Any]:
        """
        Add label to issue

        Args:
            issue_number: Issue number
            label: Label name to add

        Returns:
            Updated issue labels

        Raises:
            GitHubAPIError: If API request fails
        """
        endpoint = f"/repos/{self.owner}/{self.repo}/issues/{issue_number}/labels"

        payload = {"labels": [label]}

        try:
            response = await self.client.post(endpoint, json=payload)
            self._check_response(response)

            result = response.json()

            logger.info(
                f"Added label '{label}' to issue #{issue_number}",
                extra={
                    "issue_number": issue_number,
                    "label": label,
                }
            )

            return result

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to add label to issue #{issue_number}: {e}",
                extra={
                    "error": str(e),
                    "issue_number": issue_number,
                    "label": label,
                }
            )
            raise GitHubAPIError(f"Failed to add label: {e}")

    async def remove_label(
        self,
        issue_number: int,
        label: str,
    ) -> None:
        """
        Remove label from issue

        Args:
            issue_number: Issue number
            label: Label name to remove

        Raises:
            GitHubAPIError: If API request fails
        """
        endpoint = f"/repos/{self.owner}/{self.repo}/issues/{issue_number}/labels/{label}"

        try:
            response = await self.client.delete(endpoint)
            self._check_response(response)

            logger.info(
                f"Removed label '{label}' from issue #{issue_number}",
                extra={
                    "issue_number": issue_number,
                    "label": label,
                }
            )

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to remove label from issue #{issue_number}: {e}",
                extra={
                    "error": str(e),
                    "issue_number": issue_number,
                    "label": label,
                }
            )
            raise GitHubAPIError(f"Failed to remove label: {e}")

    async def add_comment(
        self,
        issue_number: int,
        comment: str,
    ) -> Dict[str, Any]:
        """
        Add comment to issue

        Args:
            issue_number: Issue number
            comment: Comment text (markdown supported)

        Returns:
            Created comment dictionary

        Raises:
            GitHubAPIError: If API request fails
        """
        endpoint = f"/repos/{self.owner}/{self.repo}/issues/{issue_number}/comments"

        payload = {"body": comment}

        try:
            response = await self.client.post(endpoint, json=payload)
            self._check_response(response)

            result = response.json()

            logger.info(
                f"Added comment to issue #{issue_number}",
                extra={
                    "issue_number": issue_number,
                    "comment_id": result.get("id"),
                }
            )

            return result

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to add comment to issue #{issue_number}: {e}",
                extra={
                    "error": str(e),
                    "issue_number": issue_number,
                }
            )
            raise GitHubAPIError(f"Failed to add comment: {e}")

    async def update_issue(
        self,
        issue_number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Update issue

        Args:
            issue_number: Issue number
            title: New title (optional)
            body: New body (optional)
            state: New state ("open" or "closed", optional)
            labels: New labels list (optional)
            assignees: New assignees list (optional)

        Returns:
            Updated issue dictionary

        Raises:
            GitHubAPIError: If API request fails
        """
        endpoint = f"/repos/{self.owner}/{self.repo}/issues/{issue_number}"

        payload = {}

        if title is not None:
            payload["title"] = title

        if body is not None:
            payload["body"] = body

        if state is not None:
            payload["state"] = state

        if labels is not None:
            payload["labels"] = labels

        if assignees is not None:
            payload["assignees"] = assignees

        try:
            response = await self.client.patch(endpoint, json=payload)
            self._check_response(response)

            result = response.json()

            logger.info(
                f"Updated issue #{issue_number}",
                extra={
                    "issue_number": issue_number,
                    "updated_fields": list(payload.keys()),
                }
            )

            return result

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to update issue #{issue_number}: {e}",
                extra={
                    "error": str(e),
                    "issue_number": issue_number,
                }
            )
            raise GitHubAPIError(f"Failed to update issue: {e}")

    async def get_rate_limit(self) -> Dict[str, Any]:
        """
        Get current rate limit status

        Returns:
            Rate limit information

        Raises:
            GitHubAPIError: If API request fails
        """
        endpoint = "/rate_limit"

        try:
            response = await self.client.get(endpoint)
            self._check_response(response)

            return response.json()

        except httpx.HTTPError as e:
            logger.error(
                f"Failed to fetch rate limit: {e}",
                extra={"error": str(e)}
            )
            raise GitHubAPIError(f"Failed to fetch rate limit: {e}")

    def _check_response(self, response: httpx.Response) -> None:
        """
        Check response status and raise appropriate exceptions

        Args:
            response: HTTP response

        Raises:
            GitHubAuthenticationError: If authentication fails (401)
            GitHubRateLimitError: If rate limit exceeded (403)
            GitHubAPIError: For other error status codes
        """
        if response.is_success:
            return

        if response.status_code == 401:
            raise GitHubAuthenticationError("GitHub authentication failed - check token")

        if response.status_code == 403:
            # Check if rate limit error
            if "rate limit" in response.text.lower():
                raise GitHubRateLimitError("GitHub rate limit exceeded")
            raise GitHubAPIError(f"GitHub API forbidden: {response.text}")

        if response.status_code == 404:
            raise GitHubAPIError(f"Resource not found: {response.url}")

        # Generic error
        raise GitHubAPIError(
            f"GitHub API error {response.status_code}: {response.text}"
        )


async def create_github_client(
    token: Optional[str] = None,
    repository: Optional[str] = None,
) -> GitHubClient:
    """
    Factory function to create GitHub client from environment

    Args:
        token: GitHub token (falls back to GITHUB_TOKEN env var)
        repository: Repository (falls back to GITHUB_REPOSITORY env var)

    Returns:
        Configured GitHubClient instance

    Raises:
        ValueError: If required configuration missing
    """
    import os

    token = token or os.getenv("GITHUB_TOKEN")
    repository = repository or os.getenv("GITHUB_REPOSITORY")

    if not token:
        raise ValueError("GitHub token required (GITHUB_TOKEN environment variable)")

    if not repository:
        raise ValueError("GitHub repository required (GITHUB_REPOSITORY environment variable)")

    return GitHubClient(token=token, repository=repository)
