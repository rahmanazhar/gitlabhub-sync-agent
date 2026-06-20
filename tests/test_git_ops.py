"""Integration tests for the git mirror logic using local bare repos."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from githublab_sync.git_ops import (
    MirrorCache,
    run_git,
    sync_branches_bidirectional,
    sync_tags_bidirectional,
)

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(args, cwd):
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
    )


def _init_bare(path: Path) -> str:
    run_git(["init", "--bare", "-b", "main", str(path)])
    return str(path)


def _commit_to(remote_url: str, workdir: Path, branch: str, content: str, tag: str | None = None):
    """Create a commit on ``branch`` in a fresh clone of ``remote_url`` and push it."""
    workdir.mkdir(parents=True, exist_ok=True)
    _git(["clone", remote_url, str(workdir)], cwd=workdir.parent)
    _git(["config", "user.email", "test@example.com"], cwd=workdir)
    _git(["config", "user.name", "Test"], cwd=workdir)
    _git(["checkout", "-B", branch], cwd=workdir)
    (workdir / "file.txt").write_text(content, encoding="utf-8")
    _git(["add", "."], cwd=workdir)
    _git(["commit", "-m", f"commit: {content}"], cwd=workdir)
    if tag:
        _git(["tag", tag], cwd=workdir)
    _git(["push", "origin", branch], cwd=workdir)
    if tag:
        _git(["push", "origin", tag], cwd=workdir)
    shutil.rmtree(workdir)


def _sha(repo: Path, ref: str) -> str:
    return run_git(["--git-dir", str(repo), "rev-parse", ref]).stdout.strip()


def test_creates_branch_on_empty_side(tmp_path):
    gh = _init_bare(tmp_path / "gh.git")
    gl = _init_bare(tmp_path / "gl.git")
    _commit_to(gh, tmp_path / "work", "main", "hello")

    cache = MirrorCache(tmp_path / "cache", "demo")
    cache.fetch("github", gh)
    cache.fetch("gitlab", gl)

    report = sync_branches_bidirectional(cache, "github", gh, "gitlab", gl)

    assert any(a.branch == "main" and a.direction == "github->gitlab" for a in report.branch_actions)
    assert _sha(Path(gl), "refs/heads/main") == _sha(Path(gh), "refs/heads/main")


def test_fast_forward_propagates(tmp_path):
    gh = _init_bare(tmp_path / "gh.git")
    gl = _init_bare(tmp_path / "gl.git")
    # First commit goes to both via an initial bidirectional sync.
    _commit_to(gh, tmp_path / "w1", "main", "one")
    cache = MirrorCache(tmp_path / "cache", "demo")
    cache.fetch("github", gh)
    cache.fetch("gitlab", gl)
    sync_branches_bidirectional(cache, "github", gh, "gitlab", gl)

    # Second commit lands only on gitlab; sync should carry it to github.
    _commit_to(gl, tmp_path / "w2", "main", "two")
    cache.fetch("github", gh)
    cache.fetch("gitlab", gl)
    report = sync_branches_bidirectional(cache, "github", gh, "gitlab", gl)

    assert any(a.direction == "gitlab->github" and a.kind == "update" for a in report.branch_actions)
    assert _sha(Path(gh), "refs/heads/main") == _sha(Path(gl), "refs/heads/main")


def test_divergence_is_reported_not_forced(tmp_path):
    gh = _init_bare(tmp_path / "gh.git")
    gl = _init_bare(tmp_path / "gl.git")
    _commit_to(gh, tmp_path / "w0", "main", "base")
    cache = MirrorCache(tmp_path / "cache", "demo")
    cache.fetch("github", gh)
    cache.fetch("gitlab", gl)
    sync_branches_bidirectional(cache, "github", gh, "gitlab", gl)

    # Each side now gets its own distinct commit on top of the shared base.
    _commit_to(gh, tmp_path / "wg", "main", "github-change")
    _commit_to(gl, tmp_path / "wl", "main", "gitlab-change")
    cache.fetch("github", gh)
    cache.fetch("gitlab", gl)
    report = sync_branches_bidirectional(cache, "github", gh, "gitlab", gl)

    assert report.conflicts, "diverged branches must be reported"
    assert report.conflicts[0].kind == "branch"
    # Neither side should have been overwritten.
    assert _sha(Path(gh), "refs/heads/main") != _sha(Path(gl), "refs/heads/main")


def test_tags_propagate(tmp_path):
    gh = _init_bare(tmp_path / "gh.git")
    gl = _init_bare(tmp_path / "gl.git")
    _commit_to(gh, tmp_path / "work", "main", "tagged", tag="v1.0.0")

    cache = MirrorCache(tmp_path / "cache", "demo")
    cache.fetch("github", gh)
    cache.fetch("gitlab", gl)
    report = sync_branches_bidirectional(cache, "github", gh, "gitlab", gl)
    sync_tags_bidirectional(cache, "github", gh, "gitlab", gl, report)

    assert any(t.tag == "v1.0.0" for t in report.tag_actions)
    assert _sha(Path(gl), "refs/tags/v1.0.0") == _sha(Path(gh), "refs/tags/v1.0.0")


def test_dry_run_makes_no_changes(tmp_path):
    gh = _init_bare(tmp_path / "gh.git")
    gl = _init_bare(tmp_path / "gl.git")
    _commit_to(gh, tmp_path / "work", "main", "hello")

    cache = MirrorCache(tmp_path / "cache", "demo")
    cache.fetch("github", gh)
    cache.fetch("gitlab", gl)
    report = sync_branches_bidirectional(cache, "github", gh, "gitlab", gl, dry_run=True)

    assert report.branch_actions  # it reports the intended action
    # ...but gitlab still has no main branch.
    result = run_git(["--git-dir", str(gl), "for-each-ref", "refs/heads/"])
    assert result.stdout.strip() == ""
