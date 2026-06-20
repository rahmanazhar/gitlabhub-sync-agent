"""Unit tests for provider clients and PR/MR orchestration (no network)."""

from __future__ import annotations

import json as jsonlib

from githublab_sync.config import ProviderConfig, RepoMapping, SyncOptions
from githublab_sync.providers.base import PullRequest, RepoProvider
from githublab_sync.providers.github import GitHubProvider
from githublab_sync.pull_requests import sync_pull_requests


class FakeResponse:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.text = jsonlib.dumps(payload)

    def json(self):
        return self._payload


class FakeSession:
    """Minimal stand-in for requests.Session driven by a handler callable."""

    def __init__(self, handler):
        self.headers: dict[str, str] = {}
        self._handler = handler
        self.calls: list[tuple[str, str, dict]] = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return self._handler(method, url, kwargs)


def _gh_config():
    return ProviderConfig(
        kind="github",
        token="tok",
        owner="acme",
        host="github.com",
        api_url="https://api.github.com",
    )


def test_repo_exists_true_and_false():
    def handler(method, url, kwargs):
        if url.endswith("/repos/acme/present"):
            return FakeResponse(200, {"default_branch": "main"})
        return FakeResponse(404, {"message": "Not Found"})

    provider = GitHubProvider(_gh_config(), session=FakeSession(handler))
    assert provider.repo_exists("present") is True
    assert provider.repo_exists("absent") is False


def test_list_open_pull_requests_parses_payload():
    def handler(method, url, kwargs):
        if kwargs.get("params", {}).get("page", 1) == 1:
            return FakeResponse(
                200,
                [
                    {
                        "number": 7,
                        "title": "Add feature",
                        "body": "details",
                        "head": {"ref": "feature"},
                        "base": {"ref": "main"},
                        "state": "open",
                        "html_url": "https://github.com/acme/r/pull/7",
                    }
                ],
            )
        return FakeResponse(200, [])

    provider = GitHubProvider(_gh_config(), session=FakeSession(handler))
    prs = provider.list_open_pull_requests("r")
    assert len(prs) == 1
    assert prs[0].source_branch == "feature"
    assert prs[0].target_branch == "main"
    assert prs[0].number == 7


def test_authenticated_clone_url_embeds_token():
    provider = GitHubProvider(_gh_config(), session=FakeSession(lambda *a: None))
    url = provider.authenticated_clone_url("repo")
    assert url == "https://x-access-token:tok@github.com/acme/repo.git"


# --- PR/MR orchestration ---------------------------------------------------

class FakeProvider(RepoProvider):
    def __init__(self, kind, prs):
        self.kind = kind
        self.config = ProviderConfig(kind, "t", "owner", "host", "api")
        self._prs = prs
        self.created: list[PullRequest] = []

    def repo_exists(self, name):  # pragma: no cover - unused here
        return True

    def create_repo(self, name, *, description="", visibility="private"):  # pragma: no cover
        pass

    def default_branch(self, name):  # pragma: no cover
        return "main"

    def authenticated_clone_url(self, name):  # pragma: no cover
        return f"https://{self.kind}/{name}.git"

    def list_open_pull_requests(self, name):
        return list(self._prs)

    def create_pull_request(self, name, pr):
        self.created.append(pr)
        return pr

    def whoami(self):  # pragma: no cover
        return "me"


def _pr(provider, title, source, target="main", body=""):
    return PullRequest(
        title=title,
        body=body,
        source_branch=source,
        target_branch=target,
        state="open",
        provider=provider,
    )


def test_sync_pull_requests_mirrors_missing_both_ways():
    github = FakeProvider("github", [_pr("github", "GH only", "feat-a")])
    gitlab = FakeProvider("gitlab", [_pr("gitlab", "GL only", "feat-b")])
    mapping = RepoMapping("r", "r", "r")
    options = SyncOptions(direction="bidirectional")

    actions = sync_pull_requests(mapping, github, gitlab, options)

    assert len(gitlab.created) == 1 and gitlab.created[0].source_branch == "feat-a"
    assert len(github.created) == 1 and github.created[0].source_branch == "feat-b"
    assert all(a.created for a in actions)


def test_sync_pull_requests_skips_existing_pairs():
    shared = _pr("github", "Shared", "feat-x")
    github = FakeProvider("github", [shared])
    gitlab = FakeProvider("gitlab", [_pr("gitlab", "Shared", "feat-x")])
    mapping = RepoMapping("r", "r", "r")

    sync_pull_requests(mapping, github, gitlab, SyncOptions())

    assert github.created == []
    assert gitlab.created == []


def test_sync_pull_requests_strips_ai_attribution_from_body():
    body = "Real description\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
    github = FakeProvider("github", [_pr("github", "Feature", "feat", body=body)])
    gitlab = FakeProvider("gitlab", [])
    mapping = RepoMapping("r", "r", "r")

    sync_pull_requests(mapping, github, gitlab, SyncOptions(strip_ai_attribution=True))

    assert len(gitlab.created) == 1
    assert "Claude" not in gitlab.created[0].body
    assert "Real description" in gitlab.created[0].body


def test_one_way_direction_only_mirrors_forward():
    github = FakeProvider("github", [_pr("github", "GH only", "feat-a")])
    gitlab = FakeProvider("gitlab", [_pr("gitlab", "GL only", "feat-b")])
    mapping = RepoMapping("r", "r", "r")

    sync_pull_requests(mapping, github, gitlab, SyncOptions(direction="github-to-gitlab"))

    assert len(gitlab.created) == 1  # gh -> gl
    assert github.created == []  # nothing flows back
