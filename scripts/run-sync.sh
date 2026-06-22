#!/usr/bin/env bash
#
# Wrapper that runs a githublab-sync mirror non-interactively (for launchd/cron).
# It resolves credentials and the CLI without relying on an interactive shell.
#
# Environment:
#   GITHUBLAB_SYNC_DIR     project directory (default: repo root above this script)
#   GITHUBLAB_SYNC_CONFIG  config path (default: $GITHUBLAB_SYNC_DIR/githublab-sync.yaml)
#   GITHUB_TOKEN           used if set; otherwise pulled from `gh auth token`
#
set -euo pipefail

# launchd/cron start with a minimal PATH; add the usual tool locations.
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:${PATH:-}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="${GITHUBLAB_SYNC_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
CONFIG="${GITHUBLAB_SYNC_CONFIG:-$PROJECT_DIR/githublab-sync.yaml}"

cd "$PROJECT_DIR"

# Load a local .env (e.g. GITLAB_TOKEN) if present.
if [ -f "$PROJECT_DIR/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$PROJECT_DIR/.env"
  set +a
fi

# Provide GITHUB_TOKEN from the gh CLI when not already supplied.
if [ -z "${GITHUB_TOKEN:-}" ] && command -v gh >/dev/null 2>&1; then
  GITHUB_TOKEN="$(gh auth token 2>/dev/null || true)"
  export GITHUB_TOKEN
fi

# Resolve the CLI: installed binary, project venv, then module fallback.
if command -v githublab-sync >/dev/null 2>&1; then
  CLI=(githublab-sync)
elif [ -x "$PROJECT_DIR/.venv/bin/githublab-sync" ]; then
  CLI=("$PROJECT_DIR/.venv/bin/githublab-sync")
else
  CLI=(python3 -m githublab_sync)
fi

stamp() { date '+%Y-%m-%dT%H:%M:%S%z'; }

echo "[$(stamp)] githublab-sync starting (config: $CONFIG)"
if "${CLI[@]}" sync --config "$CONFIG"; then
  status=0
else
  status=$?
fi
echo "[$(stamp)] githublab-sync finished (exit $status)"
exit "$status"
