"""Sync open pull requests <-> merge requests between providers."""

from __future__ import annotations

from dataclasses import dataclass

from githublab_sync.config import RepoMapping, SyncOptions
from githublab_sync.logging_utils import get_logger
from githublab_sync.providers.base import ProviderError, PullRequest, RepoProvider
from githublab_sync.text_utils import strip_ai_attribution

log = get_logger()


@dataclass
class PullRequestAction:
    direction: str  # "github->gitlab" | "gitlab->github"
    title: str
    source_branch: str
    target_branch: str
    created: bool
    error: str = ""


def _clean(pr: PullRequest, strip: bool) -> PullRequest:
    if not strip:
        return pr
    return PullRequest(
        title=strip_ai_attribution(pr.title),
        body=strip_ai_attribution(pr.body),
        source_branch=pr.source_branch,
        target_branch=pr.target_branch,
        state=pr.state,
        provider=pr.provider,
        number=pr.number,
        web_url=pr.web_url,
    )


def _mirror_missing(
    src_items: list[PullRequest],
    dest_keys: set[tuple[str, str]],
    dest_provider: RepoProvider,
    dest_repo_name: str,
    direction: str,
    options: SyncOptions,
    dry_run: bool,
) -> list[PullRequestAction]:
    actions: list[PullRequestAction] = []
    for pr in src_items:
        if pr.key in dest_keys:
            continue
        cleaned = _clean(pr, options.strip_ai_attribution)
        action = PullRequestAction(
            direction=direction,
            title=cleaned.title,
            source_branch=cleaned.source_branch,
            target_branch=cleaned.target_branch,
            created=False,
        )
        if dry_run:
            log.info("    [dry-run] would open %s: %s", direction, cleaned.title)
        else:
            try:
                dest_provider.create_pull_request(dest_repo_name, cleaned)
                action.created = True
                log.info("    opened %s: %s", direction, cleaned.title)
            except ProviderError as exc:
                action.error = str(exc)
                log.warning("    skipped %s '%s': %s", direction, cleaned.title, exc)
        actions.append(action)
    return actions


def sync_pull_requests(
    mapping: RepoMapping,
    github: RepoProvider,
    gitlab: RepoProvider,
    options: SyncOptions,
    dry_run: bool = False,
) -> list[PullRequestAction]:
    """Open any PR/MR that exists on one side but not the other.

    Matching is by (source_branch, target_branch). Existing requests are left
    untouched — this never closes or edits anything.
    """
    gh_prs = github.list_open_pull_requests(mapping.github_name)
    gl_prs = gitlab.list_open_pull_requests(mapping.gitlab_name)
    gh_keys = {pr.key for pr in gh_prs}
    gl_keys = {pr.key for pr in gl_prs}

    actions: list[PullRequestAction] = []
    if options.direction in ("bidirectional", "github-to-gitlab"):
        actions += _mirror_missing(
            gh_prs, gl_keys, gitlab, mapping.gitlab_name,
            "github->gitlab", options, dry_run,
        )
    if options.direction in ("bidirectional", "gitlab-to-github"):
        actions += _mirror_missing(
            gl_prs, gh_keys, github, mapping.github_name,
            "gitlab->github", options, dry_run,
        )
    return actions
