from __future__ import annotations

import pytest

from githublab_sync.config import ConfigError, load_config

VALID = """\
github:
  owner: my-user
  token: ${GH_TOKEN}
gitlab:
  owner: my-group
  token: ${GL_TOKEN}
sync:
  direction: bidirectional
repositories:
  - simple-repo
  - name: aliased
    github_name: gh-name
    gitlab_name: gl-name
"""


def _write(tmp_path, text):
    path = tmp_path / "cfg.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_loads_and_expands_env(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "gh-secret")
    monkeypatch.setenv("GL_TOKEN", "gl-secret")
    config = load_config(_write(tmp_path, VALID))

    assert config.github.token == "gh-secret"
    assert config.gitlab.token == "gl-secret"
    assert config.github.host == "github.com"
    assert config.gitlab.api_url == "https://gitlab.com/api/v4"
    assert config.sync.direction == "bidirectional"
    assert [r.name for r in config.repositories] == ["simple-repo", "aliased"]
    assert config.repositories[0].github_name == "simple-repo"
    assert config.repositories[1].github_name == "gh-name"
    assert config.repositories[1].gitlab_name == "gl-name"


def test_missing_env_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GL_TOKEN", "x")
    with pytest.raises(ConfigError, match="GH_TOKEN"):
        load_config(_write(tmp_path, VALID))


def test_invalid_direction(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("GL_TOKEN", "y")
    bad = VALID.replace("direction: bidirectional", "direction: sideways")
    with pytest.raises(ConfigError, match="direction"):
        load_config(_write(tmp_path, bad))


def test_missing_section(tmp_path):
    with pytest.raises(ConfigError, match="github"):
        load_config(_write(tmp_path, "gitlab:\n  owner: x\n  token: y\nrepositories: [a]\n"))


def test_requires_repositories(tmp_path, monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "x")
    monkeypatch.setenv("GL_TOKEN", "y")
    no_repos = VALID.split("repositories:")[0]
    with pytest.raises(ConfigError, match="repositories"):
        load_config(_write(tmp_path, no_repos))


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "nope.yaml")
