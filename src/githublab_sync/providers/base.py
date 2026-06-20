"""Abstract provider interface shared by GitHub and GitLab clients."""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any

import requests

from githublab_sync.config import ProviderConfig


class ProviderError(Exception):
    """Raised when a provider API call fails."""


@dataclass
class PullRequest:
    """A provider-agnostic view of a pull request / merge request."""

    title: str
    body: str
    source_branch: str
    target_branch: str
    state: str
    provider: str
    number: int | None = None
    web_url: str = ""

    @property
    def key(self) -> tuple[str, str]:
        """Identity used to match a PR against an MR: (source, target)."""
        return (self.source_branch, self.target_branch)


class RepoProvider(abc.ABC):
    """Common surface for the operations the sync engine needs."""

    kind: str

    def __init__(self, config: ProviderConfig, session: requests.Session | None = None):
        self.config = config
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", "githublab-sync")

    # -- repository lifecycle -------------------------------------------------
    @abc.abstractmethod
    def repo_exists(self, name: str) -> bool:
        """Return True if ``owner/name`` exists on this provider."""

    @abc.abstractmethod
    def create_repo(self, name: str, *, description: str = "", visibility: str = "private") -> None:
        """Create an empty repository ``owner/name``."""

    @abc.abstractmethod
    def default_branch(self, name: str) -> str | None:
        """Return the repository's default branch, or None if unknown/empty."""

    @abc.abstractmethod
    def authenticated_clone_url(self, name: str) -> str:
        """Return an HTTPS clone URL with embedded credentials."""

    # -- pull / merge requests ------------------------------------------------
    @abc.abstractmethod
    def list_open_pull_requests(self, name: str) -> list[PullRequest]:
        """List open PRs/MRs for ``owner/name``."""

    @abc.abstractmethod
    def create_pull_request(self, name: str, pr: PullRequest) -> PullRequest:
        """Open a PR/MR mirroring ``pr`` on this provider."""

    # -- diagnostics ----------------------------------------------------------
    @abc.abstractmethod
    def whoami(self) -> str:
        """Return the authenticated account login (used by ``doctor``)."""

    # -- shared helpers -------------------------------------------------------
    def _request(
        self,
        method: str,
        url: str,
        *,
        ok: tuple[int, ...] = (200, 201),
        **kwargs: Any,
    ) -> requests.Response:
        try:
            response = self.session.request(method, url, timeout=30, **kwargs)
        except requests.RequestException as exc:  # pragma: no cover - network
            raise ProviderError(f"{self.kind}: request to {url} failed: {exc}") from exc
        if response.status_code not in ok:
            raise ProviderError(
                f"{self.kind}: {method} {url} returned {response.status_code}: "
                f"{response.text[:300]}"
            )
        return response
