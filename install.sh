#!/usr/bin/env bash
#
# Installer for githublab-sync.
#
# Usage:
#   ./install.sh           # install into the current environment with pip
#   ./install.sh --pipx    # install as an isolated CLI with pipx (recommended)
#   ./install.sh --dev     # editable install incl. dev dependencies
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="pip"

for arg in "$@"; do
  case "$arg" in
    --pipx) MODE="pipx" ;;
    --dev)  MODE="dev" ;;
    -h|--help)
      grep '^#' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 2 ;;
  esac
done

require() {
  command -v "$1" >/dev/null 2>&1 || { echo "error: '$1' is required but not installed." >&2; exit 1; }
}

require git

case "$MODE" in
  pipx)
    require pipx
    echo ">> Installing githublab-sync with pipx..."
    pipx install "$SCRIPT_DIR"
    ;;
  dev)
    require python3
    echo ">> Installing githublab-sync (editable, with dev deps)..."
    python3 -m pip install -e "$SCRIPT_DIR[dev]"
    ;;
  pip)
    require python3
    echo ">> Installing githublab-sync with pip..."
    python3 -m pip install "$SCRIPT_DIR"
    ;;
esac

echo
echo ">> Installed. Next steps:"
echo "   1. export GITHUB_TOKEN=... GITLAB_TOKEN=..."
echo "   2. githublab-sync init           # writes githublab-sync.yaml"
echo "   3. \$EDITOR githublab-sync.yaml   # set owners and repositories"
echo "   4. githublab-sync doctor         # verify connectivity"
echo "   5. githublab-sync sync --dry-run # preview, then drop --dry-run"
