"""Tests for orchestration helpers in sync.py."""

from __future__ import annotations

from githublab_sync.config import Config, ProviderConfig, SyncOptions
from githublab_sync.providers.base import PullRequest, RepoProvider
from githublab_sync.sync import RepoResult, _ensure_mirror


class _Provider(RepoProvider):
    def __init__(self, token: str):
        self.kind = "gitlab"
        self.config = ProviderConfig(
            kind="gitlab",
            token=token,
            owner="o",
            host="h",
            api_url="a",
            clone_protocol="ssh",
        )
        self.repo_exists_called = False

    def repo_exists(self, name):
        self.repo_exists_called = True
        return False  # would normally trigger a create attempt

    def create_repo(self, name, *, description="", visibility="private"):  # pragma: no cover
        raise AssertionError("create_repo must not be called without a token")

    def default_branch(self, name):  # pragma: no cover
        return "main"

    def authenticated_clone_url(self, name):  # pragma: no cover
        return f"git@h:o/{name}.git"

    def list_open_pull_requests(self, name):  # pragma: no cover
        return []

    def create_pull_request(self, name, pr: PullRequest):  # pragma: no cover
        return pr

    def whoami(self):  # pragma: no cover
        return "me"


def _config() -> Config:
    pc = ProviderConfig("github", "t", "o", "h", "a")
    return Config(github=pc, gitlab=pc, sync=SyncOptions(), repositories=[])


def test_tokenless_provider_skips_api_and_is_assumed_available():
    provider = _Provider(token="")
    result = RepoResult(name="r")
    proceed, available = _ensure_mirror(
        provider, "r", provider, "r", _config(), result, dry_run=False
    )
    assert (proceed, available) == (True, True)
    assert provider.repo_exists_called is False  # never touched the REST API
    assert result.errors == []


def test_tokened_provider_does_consult_api():
    provider = _Provider(token="secret")
    result = RepoResult(name="r")
    # create_missing defaults to True, so a missing repo would try create_repo,
    # which raises in this fake — proving the API path is taken when a token exists.
    config = _config()
    config.sync.create_missing = False  # avoid the create attempt; just check the call
    proceed, available = _ensure_mirror(
        provider, "r", provider, "r", config, result, dry_run=False
    )
    assert provider.repo_exists_called is True
    assert proceed is False  # missing + create disabled
