"""GitHub REST API v3 provider client."""

from __future__ import annotations

from urllib.parse import quote

import requests

from githublab_sync.config import ProviderConfig
from githublab_sync.providers.base import ProviderError, PullRequest, RepoProvider


class GitHubProvider(RepoProvider):
    kind = "github"

    def __init__(self, config: ProviderConfig, session: requests.Session | None = None):
        super().__init__(config, session)
        if config.token:
            self.session.headers.update(
                {
                    "Authorization": f"Bearer {config.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                }
            )
        self._login: str | None = None

    def _full(self, name: str) -> str:
        return f"{self.config.owner}/{name}"

    def _api(self, path: str) -> str:
        return f"{self.config.api_url}{path}"

    def whoami(self) -> str:
        if self._login is None:
            data = self._request("GET", self._api("/user")).json()
            self._login = str(data.get("login", ""))
        return self._login

    def repo_exists(self, name: str) -> bool:
        url = self._api(f"/repos/{self._full(name)}")
        response = self._request("GET", url, ok=(200, 404))
        return response.status_code == 200

    def create_repo(self, name: str, *, description: str = "", visibility: str = "private") -> None:
        private = visibility != "public"
        payload = {"name": name, "description": description, "private": private}
        # Decide between a user-owned and an org-owned repository.
        if self.config.owner.lower() == self.whoami().lower():
            url = self._api("/user/repos")
        else:
            url = self._api(f"/orgs/{quote(self.config.owner)}/repos")
        self._request("POST", url, ok=(201,), json=payload)

    def default_branch(self, name: str) -> str | None:
        url = self._api(f"/repos/{self._full(name)}")
        response = self._request("GET", url, ok=(200, 404))
        if response.status_code == 404:
            return None
        return response.json().get("default_branch")

    def authenticated_clone_url(self, name: str) -> str:
        token = self.config.token
        host = self.config.host
        if token:
            return f"https://x-access-token:{token}@{host}/{self._full(name)}.git"
        return f"https://{host}/{self._full(name)}.git"

    def list_open_pull_requests(self, name: str) -> list[PullRequest]:
        url = self._api(f"/repos/{self._full(name)}/pulls")
        results: list[PullRequest] = []
        page = 1
        while True:
            response = self._request(
                "GET", url, params={"state": "open", "per_page": 100, "page": page}
            )
            batch = response.json()
            if not batch:
                break
            for item in batch:
                results.append(
                    PullRequest(
                        title=item.get("title", ""),
                        body=item.get("body") or "",
                        source_branch=item.get("head", {}).get("ref", ""),
                        target_branch=item.get("base", {}).get("ref", ""),
                        state=item.get("state", "open"),
                        provider=self.kind,
                        number=item.get("number"),
                        web_url=item.get("html_url", ""),
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return results

    def create_pull_request(self, name: str, pr: PullRequest) -> PullRequest:
        url = self._api(f"/repos/{self._full(name)}/pulls")
        payload = {
            "title": pr.title,
            "body": pr.body,
            "head": pr.source_branch,
            "base": pr.target_branch,
        }
        try:
            data = self._request("POST", url, ok=(201,), json=payload).json()
        except ProviderError as exc:
            raise ProviderError(f"Could not open GitHub PR '{pr.title}': {exc}") from exc
        return PullRequest(
            title=data.get("title", pr.title),
            body=data.get("body") or pr.body,
            source_branch=pr.source_branch,
            target_branch=pr.target_branch,
            state=data.get("state", "open"),
            provider=self.kind,
            number=data.get("number"),
            web_url=data.get("html_url", ""),
        )
