"""Provider clients for GitHub and GitLab."""

from __future__ import annotations

from githublab_sync.config import ProviderConfig
from githublab_sync.providers.base import ProviderError, PullRequest, RepoProvider
from githublab_sync.providers.github import GitHubProvider
from githublab_sync.providers.gitlab import GitLabProvider

__all__ = [
    "GitHubProvider",
    "GitLabProvider",
    "ProviderError",
    "PullRequest",
    "RepoProvider",
    "build_provider",
]


def build_provider(config: ProviderConfig) -> RepoProvider:
    """Instantiate the correct provider client for ``config``."""
    if config.kind == "github":
        return GitHubProvider(config)
    if config.kind == "gitlab":
        return GitLabProvider(config)
    raise ProviderError(f"Unknown provider kind: {config.kind}")
