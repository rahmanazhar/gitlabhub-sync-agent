# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `clone_protocol: ssh` (and `ssh_user`) per provider: fetch/push over SSH with
  no API token. Repo creation and PR/MR sync are skipped gracefully when a
  provider has no token. `doctor` reports SSH-only providers without failing.
- Pure-SSH bidirectional mirroring: a provider with no API token is assumed to
  exist (it cannot be created without one), so branch/tag sync works token-free.
- macOS launchd scheduler: `scripts/run-sync.sh` wrapper, a plist template under
  `packaging/launchd/`, and `scripts/install-launchd.sh` to install/remove a
  timed local sync that uses your existing SSH key and `gh` login.

### Fixed

- Redact embedded credentials (`user:token@host`) from git error messages and
  logs, honouring the documented "tokens are never logged" guarantee.
- Surface per-repository error details in `sync` output (previously only the
  error count was printed).
- `--dry-run` no longer reports a spurious error when a mirror would be created:
  it skips fetching a repository that does not exist yet.

## [0.1.0] - 2026-06-20

### Added

- Bidirectional branch and tag sync between GitHub and GitLab via a per-repo
  bare cache repository, with fast-forward-only updates and conflict reporting.
- Automatic mirror creation on a provider when a repository is missing
  (`create_missing`).
- One-way sync modes: `github-to-gitlab` and `gitlab-to-github`.
- Pull request ⇄ merge request mirroring for open requests, matched by
  `(source_branch, target_branch)`.
- AI-attribution scrubbing for mirrored PR/MR text (`strip_ai_attribution`) and
  an opt-in `scrub_commit_messages` history-rewrite helper.
- CLI with `init`, `doctor`, and `sync` (`--dry-run`, `--repo`, `--direction`).
- GitHub and GitLab REST clients with pagination and rich error reporting.
- Claude Code subagent (`.claude/agents/repo-sync.md`) that drives the CLI and
  commits without AI attribution.
- Packaging (`pyproject.toml`), installer (`install.sh`), `Makefile`, example
  config and `.env`, and full test suite (config, text utils, git ops with real
  local repos, mocked providers).
- CI workflow (lint, type-check, tests on Python 3.9–3.12) and a scheduled
  unattended-sync workflow.

[Unreleased]: https://github.com/rahmanazhar/gitlabhub-sync-agent/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/rahmanazhar/gitlabhub-sync-agent/releases/tag/v0.1.0
