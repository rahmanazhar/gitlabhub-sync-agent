#!/usr/bin/env bash
#
# Install (or remove) a macOS launchd job that runs githublab-sync on a timer.
#
# Usage:
#   scripts/install-launchd.sh [--interval SECONDS] [--config PATH]
#                              [--project-dir PATH] [--run-at-load] [--uninstall]
#
# Defaults: every 6 hours, config <repo>/githublab-sync.yaml. Logs to
# ~/Library/Logs/githublab-sync.log. Uses your existing SSH key + gh login;
# no secrets are uploaded anywhere.
#
set -euo pipefail

LABEL="com.githublab-sync"
INTERVAL=21600          # 6 hours
RUN_AT_LOAD="false"
DO_UNINSTALL="false"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG=""

while [ $# -gt 0 ]; do
  case "$1" in
    --interval) INTERVAL="$2"; shift 2 ;;
    --config) CONFIG="$2"; shift 2 ;;
    --project-dir) PROJECT_DIR="$2"; shift 2 ;;
    --run-at-load) RUN_AT_LOAD="true"; shift ;;
    --uninstall) DO_UNINSTALL="true"; shift ;;
    -h|--help) grep '^#' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

[ -n "$CONFIG" ] || CONFIG="$PROJECT_DIR/githublab-sync.yaml"

UID_NUM="$(id -u)"
DOMAIN="gui/$UID_NUM"
PLIST_DIR="$HOME/Library/LaunchAgents"
PLIST="$PLIST_DIR/$LABEL.plist"
LOG="$HOME/Library/Logs/githublab-sync.log"
WRAPPER="$SCRIPT_DIR/run-sync.sh"
TEMPLATE="$PROJECT_DIR/packaging/launchd/com.githublab-sync.plist"

unload_existing() {
  launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null \
    || launchctl unload "$PLIST" 2>/dev/null \
    || true
}

if [ "$DO_UNINSTALL" = "true" ]; then
  unload_existing
  rm -f "$PLIST"
  echo "Removed launchd job '$LABEL'."
  exit 0
fi

[ -f "$TEMPLATE" ] || { echo "Template not found: $TEMPLATE" >&2; exit 1; }
mkdir -p "$PLIST_DIR" "$(dirname "$LOG")"
chmod +x "$WRAPPER"

sed \
  -e "s#@LABEL@#${LABEL}#g" \
  -e "s#@WRAPPER@#${WRAPPER}#g" \
  -e "s#@PROJECT_DIR@#${PROJECT_DIR}#g" \
  -e "s#@CONFIG@#${CONFIG}#g" \
  -e "s#@LOG@#${LOG}#g" \
  -e "s#@INTERVAL@#${INTERVAL}#g" \
  -e "s#@RUN_AT_LOAD@#${RUN_AT_LOAD}#g" \
  "$TEMPLATE" > "$PLIST"

unload_existing
launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST"
launchctl enable "$DOMAIN/$LABEL" 2>/dev/null || true

echo "Installed launchd job '$LABEL'."
echo "  schedule : every ${INTERVAL}s"
echo "  config   : ${CONFIG}"
echo "  log      : ${LOG}"
echo "  plist    : ${PLIST}"
echo
echo "Run once now : launchctl kickstart -k ${DOMAIN}/${LABEL}"
echo "Check status : launchctl print ${DOMAIN}/${LABEL} | grep -E 'state|last exit'"
echo "Uninstall    : $0 --uninstall"
