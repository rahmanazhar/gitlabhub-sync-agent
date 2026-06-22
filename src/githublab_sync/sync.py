"""Top-level orchestration: mirror creation, git sync, and PR/MR sync."""

from __future__ import annotations

from dataclasses import dataclass, field

from githublab_sync.config import Config, RepoMapping
from githublab_sync.git_ops import (
    GitError,
    GitSyncReport,
    MirrorCache,
    sync_branches_bidirectional,
    sync_one_way,
    sync_tags_bidirectional,
)
from githublab_sync.logging_utils import get_logger
from githublab_sync.providers.base import ProviderError, RepoProvider
from githublab_sync.pull_requests import PullRequestAction, sync_pull_requests

log = get_logger()


@dataclass
class RepoResult:
    name: str
    created_on: list[str] = field(default_factory=list)
    git_report: GitSyncReport = field(default_factory=GitSyncReport)
    pr_actions: list[PullRequestAction] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors and not self.git_report.conflicts


@dataclass
class SyncSummary:
    results: list[RepoResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.ok for r in self.results)

    @property
    def conflict_count(self) -> int:
        return sum(len(r.git_report.conflicts) for r in self.results)

    @property
    def error_count(self) -> int:
        return sum(len(r.errors) for r in self.results)


def _ensure_mirror(
    provider: RepoProvider,
    repo_name: str,
    other: RepoProvider,
    other_name: str,
    config: Config,
    result: RepoResult,
    dry_run: bool,
) -> tuple[bool, bool]:
    """Create ``repo_name`` on ``provider`` if missing.

    Returns ``(proceed, available)``: ``proceed`` is False on a fatal error;
    ``available`` is True when the repo can actually be fetched now (it already
    existed, or was really created). In dry-run a would-be-created repo is
    ``available=False`` so we don't try to fetch a repo that isn't there yet.
    """
    if not provider.config.has_token:
        # No REST access: we can neither verify nor create the repo via the API
        # (creation requires a token). Assume it exists and let the git fetch
        # surface a clear error if it does not. This is what makes pure-SSH
        # bidirectional mirroring work without an API token.
        return True, True
    try:
        if provider.repo_exists(repo_name):
            return True, True
    except ProviderError as exc:
        result.errors.append(f"{provider.kind}: existence check failed: {exc}")
        return False, False

    if not config.sync.create_missing:
        result.errors.append(
            f"{provider.kind}: '{provider.config.owner}/{repo_name}' missing and "
            "create_missing is disabled"
        )
        return False, False

    description = f"Mirror of {other.config.host}/{other.config.owner}/{other_name}"
    if dry_run:
        log.info("  [dry-run] would create mirror on %s: %s", provider.kind, repo_name)
        result.created_on.append(provider.kind)
        return True, False
    try:
        provider.create_repo(
            repo_name,
            description=description,
            visibility=config.sync.default_visibility,
        )
        result.created_on.append(provider.kind)
        log.info("  created mirror on %s: %s", provider.kind, repo_name)
        return True, True
    except ProviderError as exc:
        result.errors.append(f"{provider.kind}: could not create '{repo_name}': {exc}")
        return False, False


def sync_repo(
    config: Config,
    mapping: RepoMapping,
    github: RepoProvider,
    gitlab: RepoProvider,
    dry_run: bool = False,
) -> RepoResult:
    """Synchronise a single repository across both providers."""
    result = RepoResult(name=mapping.name)
    log.info("repo: %s", mapping.name)

    direction = config.sync.direction
    # In one-way modes the destination may legitimately not exist yet.
    need_github = direction in ("bidirectional", "gitlab-to-github")
    need_gitlab = direction in ("bidirectional", "github-to-gitlab")

    # Sides that aren't being ensured are the existing source — assume present.
    gh_available = True
    gl_available = True

    if need_gitlab:
        proceed, gl_available = _ensure_mirror(
            gitlab, mapping.gitlab_name, github, mapping.github_name, config, result, dry_run
        )
        if not proceed:
            return result
    if need_github:
        proceed, gh_available = _ensure_mirror(
            github, mapping.github_name, gitlab, mapping.gitlab_name, config, result, dry_run
        )
        if not proceed:
            return result

    gh_url = github.authenticated_clone_url(mapping.github_name)
    gl_url = gitlab.authenticated_clone_url(mapping.gitlab_name)

    cache = MirrorCache(config.sync.cache_dir, mapping.name)
    try:
        if gh_available:
            cache.fetch("github", gh_url)
        if gl_available:
            cache.fetch("gitlab", gl_url)
    except GitError as exc:
        result.errors.append(f"fetch failed: {exc}")
        return result

    try:
        if config.sync.sync_branches:
            if direction == "bidirectional":
                report = sync_branches_bidirectional(
                    cache, "github", gh_url, "gitlab", gl_url, dry_run
                )
                if config.sync.sync_tags:
                    sync_tags_bidirectional(
                        cache, "github", gh_url, "gitlab", gl_url, report, dry_run
                    )
            elif direction == "github-to-gitlab":
                report = sync_one_way(
                    cache, "github", "gitlab", gl_url, config.sync.sync_tags, dry_run
                )
            else:  # gitlab-to-github
                report = sync_one_way(
                    cache, "gitlab", "github", gh_url, config.sync.sync_tags, dry_run
                )
            result.git_report = report
            _log_git_report(report)
    except GitError as exc:
        result.errors.append(f"git sync failed: {exc}")
        return result

    if config.sync.sync_pull_requests:
        if not config.github.has_token or not config.gitlab.has_token:
            log.info(
                "  skipping PR/MR sync: requires an API token on both providers"
            )
        else:
            try:
                result.pr_actions = sync_pull_requests(
                    mapping, github, gitlab, config.sync, dry_run
                )
            except ProviderError as exc:
                result.errors.append(f"pull-request sync failed: {exc}")

    return result


def _log_git_report(report: GitSyncReport) -> None:
    for action in report.branch_actions:
        log.info("  branch %s %s (%s)", action.kind, action.branch, action.direction)
    for tag_action in report.tag_actions:
        log.info("  tag -> %s (%s)", tag_action.tag, tag_action.direction)
    for conflict in report.conflicts:
        log.warning("  CONFLICT %s %s: %s", conflict.kind, conflict.ref, conflict.detail)
    if not report.branch_actions and not report.tag_actions and not report.conflicts:
        log.info("  already in sync")


def sync_all(config: Config, dry_run: bool = False) -> SyncSummary:
    """Synchronise every configured repository."""
    from githublab_sync.providers import build_provider

    github = build_provider(config.github)
    gitlab = build_provider(config.gitlab)

    summary = SyncSummary()
    for mapping in config.repositories:
        summary.results.append(sync_repo(config, mapping, github, gitlab, dry_run))
    return summary
