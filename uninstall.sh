#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${AGY_STATUSLINE_DIR:-$HOME/.antigravity}"
SETTINGS_FILE="${AGY_SETTINGS_FILE:-$HOME/.gemini/antigravity-cli/settings.json}"
BACKUP_DIR="$INSTALL_DIR/backups"

mkdir -p "$BACKUP_DIR"
timestamp="$(date +%Y%m%d_%H%M%S)"

if [[ -f "$SETTINGS_FILE" ]]; then
  cp "$SETTINGS_FILE" "$BACKUP_DIR/settings.json.before-uninstall.$timestamp.bak"

  python3 - "$SETTINGS_FILE" "$INSTALL_DIR/status.py" <<'PY'
import json
import os
import sys

settings_path, status_path = sys.argv[1], sys.argv[2]

try:
    with open(settings_path, "r", encoding="utf-8") as f:
        settings = json.load(f)
except FileNotFoundError:
    settings = {}
except json.JSONDecodeError as exc:
    raise SystemExit(f"Invalid JSON in {settings_path}: {exc}")

status_line = settings.get("statusLine")
if isinstance(status_line, dict):
    command = str(status_line.get("command", ""))
    if status_path in command or ".antigravity/status.py" in command:
        settings.pop("statusLine", None)

tmp_path = settings_path + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, ensure_ascii=False, indent=2)
    f.write("\n")
os.replace(tmp_path, settings_path)
PY
fi

rm -f "$INSTALL_DIR/status.py" "$INSTALL_DIR/agy-quota-cache.py"

cat <<EOF
Antigravity status line uninstalled.

Removed:
  $INSTALL_DIR/status.py
  $INSTALL_DIR/agy-quota-cache.py

Updated settings:
  $SETTINGS_FILE

Backups:
  $BACKUP_DIR

Restart Antigravity CLI or start a new agy session for the change to apply.
EOF
