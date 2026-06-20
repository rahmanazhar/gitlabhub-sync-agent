# Contributing to GitHubLab Sync

Thanks for your interest in improving GitHubLab Sync! This document explains how
to set up your environment and the expectations for contributions.

## Getting started

```bash
git clone https://github.com/rahmanazhar/gitlabhub-sync-agent
cd githublab-sync
make dev      # editable install with dev dependencies
make test     # confirm the suite passes before you start
```

You need Python 3.9+ and `git`. No GitHub/GitLab credentials are required to run
the test suite — the git tests use local bare repositories and the provider
tests mock all HTTP.

## Development workflow

1. Create a branch: `git checkout -b feature/short-description`.
2. Make your change with tests.
3. Run the full local check:
   ```bash
   make format     # ruff format + autofix
   make lint       # ruff check
   make typecheck  # mypy
   make test       # pytest
   ```
4. Commit with a clear, conventional message (see below).
5. Open a pull request describing the change and the motivation.

## Commit & PR conventions

- Use concise, imperative commit subjects: `Add tag conflict reporting`.
- Reference issues where relevant: `Fix #42: handle empty default branch`.
- **Do not add AI authorship trailers** (`Co-Authored-By: Claude`,
  `🤖 Generated with ...`, etc.) — this project intentionally keeps history free
  of AI attribution, and CI does not require it.
- Keep PRs focused; unrelated changes belong in separate PRs.

## Code style

- Formatting and linting are handled by [ruff](https://docs.astral.sh/ruff/);
  run `make format` before committing.
- Type hints are expected on public functions; `make typecheck` must pass.
- Match the surrounding style — small, readable functions and clear names.

## Tests

- Add tests for any new behaviour or bug fix.
- Git-level logic goes in `tests/test_git_ops.py` (uses real local repos).
- API/provider logic goes in `tests/test_providers.py` (mock the HTTP session;
  never hit the network in tests).
- Aim to keep or improve coverage (`make cov`).

## Reporting bugs & requesting features

Use the issue templates under `.github/ISSUE_TEMPLATE/`. For security issues,
follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Code of Conduct

By participating you agree to abide by our
[Code of Conduct](CODE_OF_CONDUCT.md).
