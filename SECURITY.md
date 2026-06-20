# Security Policy

## Supported versions

This project is pre-1.0; security fixes are applied to the latest released
version on the `main` branch.

## Reporting a vulnerability

**Please do not report security vulnerabilities through public GitHub issues.**

Instead, use [GitHub Security Advisories][advisories] ("Report a vulnerability")
on this repository, or email the maintainers at `security@example.com`. Include:

- A description of the issue and its impact
- Steps to reproduce or a proof of concept
- Affected version(s) and configuration

You can expect an initial acknowledgement within a few business days. We will
keep you informed as we work on a fix and will credit you in the release notes
unless you prefer to remain anonymous.

[advisories]: https://github.com/rahmanazhar/gitlabhub-sync-agent/security/advisories/new

## Handling of credentials

GitHubLab Sync is designed to keep secrets out of source control:

- Tokens are read from environment variables (`${VAR}` expansion in config);
  the real `githublab-sync.yaml` and `.env` are git-ignored by default.
- Tokens are only ever sent over HTTPS to the providers' official API/host.
- Authenticated clone URLs (which embed the token) are never logged or printed.

When self-hosting the scheduled workflow, store `GITLAB_TOKEN` (and any GitHub
token beyond the default `GITHUB_TOKEN`) as encrypted repository/organization
secrets, and grant the minimum scopes listed in the README.
