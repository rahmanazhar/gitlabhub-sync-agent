"""GitLab REST API v4 provider client."""

from __future__ import annotations

from urllib.parse import quote

import requests

from githublab_sync.config import ProviderConfig
from githublab_sync.providers.base import ProviderError, PullRequest, RepoProvider

_VISIBILITY_MAP = {"private": "private", "public": "public", "internal": "internal"}


class GitLabProvider(RepoProvider):
    kind = "gitlab"

    def __init__(self, config: ProviderConfig, session: requests.Session | None = None):
        super().__init__(config, session)
        if config.token:
            # PRIVATE-TOKEN works for both PATs and group/project access tokens.
            self.session.headers.update({"PRIVATE-TOKEN": config.token})
        self._login: str | None = None

    def _project_path(self, name: str) -> str:
        return f"{self.config.owner}/{name}"

    def _encoded(self, name: str) -> str:
        return quote(self._project_path(name), safe="")

    def _api(self, path: str) -> str:
        return f"{self.config.api_url}{path}"

    def whoami(self) -> str:
        if self._login is None:
            data = self._request("GET", self._api("/user")).json()
            self._login = str(data.get("username", ""))
        return self._login

    def _namespace_id(self) -> int:
        url = self._api("/namespaces")
        response = self._request("GET", url, params={"search": self.config.owner})
        for namespace in response.json():
            if namespace.get("full_path", "").lower() == self.config.owner.lower():
                return int(namespace["id"])
        raise ProviderError(
            f"GitLab namespace '{self.config.owner}' not found or not accessible by token"
        )

    def repo_exists(self, name: str) -> bool:
        url = self._api(f"/projects/{self._encoded(name)}")
        response = self._request("GET", url, ok=(200, 404))
        return response.status_code == 200

    def create_repo(self, name: str, *, description: str = "", visibility: str = "private") -> None:
        payload = {
            "name": name,
            "path": name,
            "namespace_id": self._namespace_id(),
            "description": description,
            "visibility": _VISIBILITY_MAP.get(visibility, "private"),
        }
        self._request("POST", self._api("/projects"), ok=(201,), json=payload)

    def default_branch(self, name: str) -> str | None:
        url = self._api(f"/projects/{self._encoded(name)}")
        response = self._request("GET", url, ok=(200, 404))
        if response.status_code == 404:
            return None
        return response.json().get("default_branch")

    def authenticated_clone_url(self, name: str) -> str:
        token = self.config.token
        host = self.config.host
        if token:
            return f"https://oauth2:{token}@{host}/{self._project_path(name)}.git"
        return f"https://{host}/{self._project_path(name)}.git"

    def list_open_pull_requests(self, name: str) -> list[PullRequest]:
        url = self._api(f"/projects/{self._encoded(name)}/merge_requests")
        results: list[PullRequest] = []
        page = 1
        while True:
            response = self._request(
                "GET", url, params={"state": "opened", "per_page": 100, "page": page}
            )
            batch = response.json()
            if not batch:
                break
            for item in batch:
                results.append(
                    PullRequest(
                        title=item.get("title", ""),
                        body=item.get("description") or "",
                        source_branch=item.get("source_branch", ""),
                        target_branch=item.get("target_branch", ""),
                        state="open",
                        provider=self.kind,
                        number=item.get("iid"),
                        web_url=item.get("web_url", ""),
                    )
                )
            if len(batch) < 100:
                break
            page += 1
        return results

    def create_pull_request(self, name: str, pr: PullRequest) -> PullRequest:
        url = self._api(f"/projects/{self._encoded(name)}/merge_requests")
        payload = {
            "title": pr.title,
            "description": pr.body,
            "source_branch": pr.source_branch,
            "target_branch": pr.target_branch,
        }
        try:
            data = self._request("POST", url, ok=(201,), json=payload).json()
        except ProviderError as exc:
            raise ProviderError(f"Could not open GitLab MR '{pr.title}': {exc}") from exc
        return PullRequest(
            title=data.get("title", pr.title),
            body=data.get("description") or pr.body,
            source_branch=pr.source_branch,
            target_branch=pr.target_branch,
            state="open",
            provider=self.kind,
            number=data.get("iid"),
            web_url=data.get("web_url", ""),
        )
