#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${AGY_STATUSLINE_DIR:-$HOME/.antigravity}"
SETTINGS_FILE="${AGY_SETTINGS_FILE:-$HOME/.gemini/antigravity-cli/settings.json}"
BACKUP_DIR="$INSTALL_DIR/backups"

mkdir -p "$INSTALL_DIR" "$BACKUP_DIR"

timestamp="$(date +%Y%m%d_%H%M%S)"

if [[ -f "$SETTINGS_FILE" ]]; then
  cp "$SETTINGS_FILE" "$BACKUP_DIR/settings.json.$timestamp.bak"
fi

if [[ -f "$INSTALL_DIR/status.py" ]]; then
  cp "$INSTALL_DIR/status.py" "$BACKUP_DIR/status.py.$timestamp.bak"
fi

if [[ -f "$INSTALL_DIR/agy-quota-cache.py" ]]; then
  cp "$INSTALL_DIR/agy-quota-cache.py" "$BACKUP_DIR/agy-quota-cache.py.$timestamp.bak"
fi

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cp "$script_dir/status.py" "$INSTALL_DIR/status.py"
cp "$script_dir/agy-quota-cache.py" "$INSTALL_DIR/agy-quota-cache.py"
chmod +x "$INSTALL_DIR/status.py" "$INSTALL_DIR/agy-quota-cache.py"

mkdir -p "$(dirname "$SETTINGS_FILE")"

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

settings["statusLine"] = {
    "type": "command",
    "command": f"python3 {status_path}",
}

tmp_path = settings_path + ".tmp"
with open(tmp_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, ensure_ascii=False, indent=2)
    f.write("\n")
os.replace(tmp_path, settings_path)
PY

cat <<EOF
Antigravity status line installed.

Installed files:
  $INSTALL_DIR/status.py
  $INSTALL_DIR/agy-quota-cache.py

Updated settings:
  $SETTINGS_FILE

Backups:
  $BACKUP_DIR

Restart Antigravity CLI or start a new agy session to see it.
EOF
