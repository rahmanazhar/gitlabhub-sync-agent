"""Configuration loading and validation."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_ENV_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

VALID_DIRECTIONS = ("bidirectional", "github-to-gitlab", "gitlab-to-github")
VALID_VISIBILITY = ("private", "public", "internal")
VALID_PROTOCOLS = ("https", "ssh")


class ConfigError(Exception):
    """Raised when the configuration file is missing or invalid."""


def _expand_env(value: Any) -> Any:
    """Recursively expand ``${VAR}`` references using the process environment."""
    if isinstance(value, str):

        def _replace(match: re.Match[str]) -> str:
            name = match.group(1)
            resolved = os.environ.get(name)
            if resolved is None:
                raise ConfigError(
                    f"Environment variable '{name}' referenced in config is not set"
                )
            return resolved

        return _ENV_PATTERN.sub(_replace, value)
    if isinstance(value, dict):
        return {key: _expand_env(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    return value


@dataclass
class ProviderConfig:
    """Connection settings for a single git host."""

    kind: str  # "github" or "gitlab"
    token: str
    owner: str  # user / org (GitHub) or group / namespace path (GitLab)
    host: str
    api_url: str
    clone_protocol: str = "https"  # "https" (token-embedded) or "ssh"
    ssh_user: str = "git"

    @property
    def has_token(self) -> bool:
        return bool(self.token)

    @property
    def uses_ssh(self) -> bool:
        return self.clone_protocol == "ssh"


@dataclass
class SyncOptions:
    """Behavioural toggles for a sync run."""

    direction: str = "bidirectional"
    create_missing: bool = True
    sync_branches: bool = True
    sync_tags: bool = True
    sync_pull_requests: bool = True
    strip_ai_attribution: bool = True
    default_visibility: str = "private"
    cache_dir: Path = field(
        default_factory=lambda: Path.home() / ".cache" / "githublab-sync"
    )


@dataclass
class RepoMapping:
    """A single repository to keep in sync across both providers."""

    name: str
    github_name: str
    gitlab_name: str


@dataclass
class Config:
    """Top-level configuration."""

    github: ProviderConfig
    gitlab: ProviderConfig
    sync: SyncOptions
    repositories: list[RepoMapping]


def _build_provider(kind: str, raw: dict[str, Any]) -> ProviderConfig:
    defaults = {
        "github": ("github.com", "https://api.github.com"),
        "gitlab": ("gitlab.com", "https://gitlab.com/api/v4"),
    }[kind]
    host = str(raw.get("host", defaults[0]))
    api_url = str(raw.get("api_url", defaults[1])).rstrip("/")
    owner = raw.get("owner")
    if not owner:
        raise ConfigError(f"'{kind}.owner' is required")
    clone_protocol = str(raw.get("clone_protocol", "https"))
    if clone_protocol not in VALID_PROTOCOLS:
        raise ConfigError(
            f"'{kind}.clone_protocol' must be one of {VALID_PROTOCOLS}, got '{clone_protocol}'"
        )
    return ProviderConfig(
        kind=kind,
        token=str(raw.get("token", "")),
        owner=str(owner),
        host=host,
        api_url=api_url,
        clone_protocol=clone_protocol,
        ssh_user=str(raw.get("ssh_user", "git")),
    )


def _build_repos(raw: Any) -> list[RepoMapping]:
    if not raw:
        raise ConfigError("'repositories' must contain at least one entry")
    if not isinstance(raw, list):
        raise ConfigError("'repositories' must be a list")
    repos: list[RepoMapping] = []
    for entry in raw:
        if isinstance(entry, str):
            repos.append(RepoMapping(name=entry, github_name=entry, gitlab_name=entry))
            continue
        if not isinstance(entry, dict) or "name" not in entry:
            raise ConfigError(
                "Each repository must be a string or a mapping with a 'name' key"
            )
        name = str(entry["name"])
        repos.append(
            RepoMapping(
                name=name,
                github_name=str(entry.get("github_name", name)),
                gitlab_name=str(entry.get("gitlab_name", name)),
            )
        )
    return repos


def _build_sync_options(raw: dict[str, Any]) -> SyncOptions:
    direction = str(raw.get("direction", "bidirectional"))
    if direction not in VALID_DIRECTIONS:
        raise ConfigError(
            f"'sync.direction' must be one of {VALID_DIRECTIONS}, got '{direction}'"
        )
    visibility = str(raw.get("default_visibility", "private"))
    if visibility not in VALID_VISIBILITY:
        raise ConfigError(
            f"'sync.default_visibility' must be one of {VALID_VISIBILITY}, got '{visibility}'"
        )
    options = SyncOptions(
        direction=direction,
        create_missing=bool(raw.get("create_missing", True)),
        sync_branches=bool(raw.get("sync_branches", True)),
        sync_tags=bool(raw.get("sync_tags", True)),
        sync_pull_requests=bool(raw.get("sync_pull_requests", True)),
        strip_ai_attribution=bool(raw.get("strip_ai_attribution", True)),
        default_visibility=visibility,
    )
    if raw.get("cache_dir"):
        options.cache_dir = Path(str(raw["cache_dir"])).expanduser()
    return options


def load_config(path: str | os.PathLike[str]) -> Config:
    """Load and validate the YAML configuration at ``path``."""
    config_path = Path(path).expanduser()
    if not config_path.is_file():
        raise ConfigError(f"Config file not found: {config_path}")
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:  # pragma: no cover - passthrough
        raise ConfigError(f"Could not parse YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("Top-level config must be a mapping")

    raw = _expand_env(raw)

    for required in ("github", "gitlab"):
        if required not in raw or not isinstance(raw[required], dict):
            raise ConfigError(f"Missing required '{required}' section")

    return Config(
        github=_build_provider("github", raw["github"]),
        gitlab=_build_provider("gitlab", raw["gitlab"]),
        sync=_build_sync_options(raw.get("sync", {}) or {}),
        repositories=_build_repos(raw.get("repositories")),
    )
