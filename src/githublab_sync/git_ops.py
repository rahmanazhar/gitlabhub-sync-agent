"""Low-level git mirror operations built on the ``git`` CLI.

The sync engine keeps one bare cache repository per logical repo. Both
providers are fetched into namespaced ref hierarchies so their branches and
tags never collide:

    refs/remotes/github/heads/<branch>   refs/remotes/github/tags/<tag>
    refs/remotes/gitlab/heads/<branch>   refs/remotes/gitlab/tags/<tag>

From there the bidirectional algorithm pushes whichever side is strictly ahead
to the other, and refuses to touch branches that have genuinely diverged.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_SAFE_KEY = re.compile(r"[^A-Za-z0-9._-]+")


class GitError(Exception):
    """Raised when a git invocation fails."""


def run_git(
    args: list[str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run ``git <args>`` returning the completed process."""
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed ({proc.returncode}): {proc.stderr.strip()}"
        )
    return proc


@dataclass
class BranchAction:
    branch: str
    direction: str  # "github->gitlab" | "gitlab->github"
    kind: str  # "create" | "update"


@dataclass
class TagAction:
    tag: str
    direction: str


@dataclass
class Conflict:
    ref: str
    kind: str  # "branch" | "tag"
    detail: str


@dataclass
class GitSyncReport:
    branch_actions: list[BranchAction] = field(default_factory=list)
    tag_actions: list[TagAction] = field(default_factory=list)
    conflicts: list[Conflict] = field(default_factory=list)


def _safe_key(text: str) -> str:
    return _SAFE_KEY.sub("-", text).strip("-") or "repo"


class MirrorCache:
    """A bare cache repository that fetches from and pushes to both providers."""

    def __init__(self, cache_dir: Path, repo_key: str):
        self.path = Path(cache_dir).expanduser() / f"{_safe_key(repo_key)}.git"

    def _git(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        """Run a git command against the bare cache repo.

        Uses an explicit ``--git-dir`` (rather than ``cwd``) so it works even
        when the user has ``safe.bareRepository = explicit`` configured.
        """
        return run_git(["--git-dir", str(self.path), *args], check=check)

    def ensure(self) -> None:
        if not (self.path / "HEAD").exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            run_git(["init", "--bare", str(self.path)])

    def fetch(self, remote_name: str, url: str) -> None:
        """Fetch all heads and tags from ``url`` into namespaced refs."""
        self.ensure()
        self._git(
            [
                "fetch",
                "--prune",
                url,
                f"+refs/heads/*:refs/remotes/{remote_name}/heads/*",
                f"+refs/tags/*:refs/remotes/{remote_name}/tags/*",
            ]
        )

    def _list_refs(self, prefix: str) -> dict[str, str]:
        proc = self._git(["for-each-ref", "--format=%(refname) %(objectname)", prefix])
        refs: dict[str, str] = {}
        for line in proc.stdout.splitlines():
            if not line.strip():
                continue
            refname, sha = line.rsplit(" ", 1)
            short = refname[len(prefix):]
            refs[short] = sha
        return refs

    def branches(self, remote_name: str) -> dict[str, str]:
        return self._list_refs(f"refs/remotes/{remote_name}/heads/")

    def tags(self, remote_name: str) -> dict[str, str]:
        return self._list_refs(f"refs/remotes/{remote_name}/tags/")

    def is_ancestor(self, maybe_ancestor: str, descendant: str) -> bool:
        proc = self._git(
            ["merge-base", "--is-ancestor", maybe_ancestor, descendant],
            check=False,
        )
        return proc.returncode == 0

    def push_branch(self, url: str, source_ref: str, branch: str, force: bool = False) -> None:
        refspec = f"{source_ref}:refs/heads/{branch}"
        if force:
            refspec = "+" + refspec
        self._git(["push", url, refspec])

    def push_tag(self, url: str, source_ref: str, tag: str) -> None:
        self._git(["push", url, f"{source_ref}:refs/tags/{tag}"])


def sync_branches_bidirectional(
    cache: MirrorCache,
    left: str,
    left_url: str,
    right: str,
    right_url: str,
    dry_run: bool = False,
) -> GitSyncReport:
    """Reconcile branches between two already-fetched remotes."""
    report = GitSyncReport()
    left_branches = cache.branches(left)
    right_branches = cache.branches(right)

    for branch in sorted(set(left_branches) | set(right_branches)):
        left_sha = left_branches.get(branch)
        right_sha = right_branches.get(branch)
        left_ref = f"refs/remotes/{left}/heads/{branch}"
        right_ref = f"refs/remotes/{right}/heads/{branch}"

        if left_sha and not right_sha:
            report.branch_actions.append(
                BranchAction(branch, f"{left}->{right}", "create")
            )
            if not dry_run:
                cache.push_branch(right_url, left_ref, branch)
        elif right_sha and not left_sha:
            report.branch_actions.append(
                BranchAction(branch, f"{right}->{left}", "create")
            )
            if not dry_run:
                cache.push_branch(left_url, right_ref, branch)
        elif left_sha == right_sha:
            continue
        elif cache.is_ancestor(right_ref, left_ref):
            # left is strictly ahead of right.
            report.branch_actions.append(
                BranchAction(branch, f"{left}->{right}", "update")
            )
            if not dry_run:
                cache.push_branch(right_url, left_ref, branch)
        elif cache.is_ancestor(left_ref, right_ref):
            report.branch_actions.append(
                BranchAction(branch, f"{right}->{left}", "update")
            )
            if not dry_run:
                cache.push_branch(left_url, right_ref, branch)
        else:
            report.conflicts.append(
                Conflict(
                    ref=branch,
                    kind="branch",
                    detail=f"diverged: {left}={str(left_sha)[:8]} {right}={str(right_sha)[:8]}",
                )
            )
    return report


def sync_tags_bidirectional(
    cache: MirrorCache,
    left: str,
    left_url: str,
    right: str,
    right_url: str,
    report: GitSyncReport,
    dry_run: bool = False,
) -> None:
    """Propagate tags missing on either side. Existing tags are never moved."""
    left_tags = cache.tags(left)
    right_tags = cache.tags(right)

    for tag in sorted(set(left_tags) | set(right_tags)):
        left_sha = left_tags.get(tag)
        right_sha = right_tags.get(tag)
        if left_sha and not right_sha:
            report.tag_actions.append(TagAction(tag, f"{left}->{right}"))
            if not dry_run:
                cache.push_tag(right_url, f"refs/remotes/{left}/tags/{tag}", tag)
        elif right_sha and not left_sha:
            report.tag_actions.append(TagAction(tag, f"{right}->{left}"))
            if not dry_run:
                cache.push_tag(left_url, f"refs/remotes/{right}/tags/{tag}", tag)
        elif left_sha != right_sha:
            report.conflicts.append(
                Conflict(ref=tag, kind="tag", detail="tag points at different commits")
            )


def sync_one_way(
    cache: MirrorCache,
    source: str,
    dest: str,
    dest_url: str,
    include_tags: bool,
    dry_run: bool = False,
) -> GitSyncReport:
    """Force ``dest`` to match ``source`` (source is the source of truth)."""
    report = GitSyncReport()
    source_branches = cache.branches(source)
    dest_branches = cache.branches(dest)
    for branch, sha in sorted(source_branches.items()):
        if dest_branches.get(branch) == sha:
            continue
        kind = "update" if branch in dest_branches else "create"
        report.branch_actions.append(BranchAction(branch, f"{source}->{dest}", kind))
        if not dry_run:
            cache.push_branch(
                dest_url, f"refs/remotes/{source}/heads/{branch}", branch, force=True
            )
    if include_tags:
        source_tags = cache.tags(source)
        dest_tags = cache.tags(dest)
        for tag, sha in sorted(source_tags.items()):
            if dest_tags.get(tag) == sha:
                continue
            report.tag_actions.append(TagAction(tag, f"{source}->{dest}"))
            if not dry_run:
                cache.push_tag(dest_url, f"refs/remotes/{source}/tags/{tag}", tag)
    return report


def scrub_commit_messages(repo_path: Path) -> None:
    """Rewrite every commit message in a bare repo to drop AI attribution.

    This rewrites history and changes commit hashes — opt-in only. It uses
    ``git filter-branch`` so it works without extra tooling.
    """

    git_dir = ["--git-dir", str(repo_path)]
    proc = run_git([*git_dir, "rev-list", "--all"])
    if not proc.stdout.strip():
        return
    msg_filter = (
        "python3 -c \"import sys;"
        "from githublab_sync.text_utils import strip_ai_attribution;"
        "sys.stdout.write(strip_ai_attribution(sys.stdin.read()))\""
    )
    run_git(
        [
            *git_dir,
            "filter-branch",
            "--force",
            "--msg-filter",
            msg_filter,
            "--",
            "--all",
        ]
    )
