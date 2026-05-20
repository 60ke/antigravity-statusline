#!/usr/bin/env python3
"""Cache Antigravity `/usage` model quota output for the status line.

Usage:
  pbpaste | python3 agy-quota-cache.py
  python3 agy-quota-cache.py usage-output.txt
"""
import json
import os
import re
import sys
import time

CACHE_FILE = os.environ.get(
    "AGY_QUOTA_CACHE",
    os.path.expanduser("~/.antigravity/quota-cache.json"),
)


def normalize_model_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def parse_usage(text: str) -> dict:
    models = {}
    current = None

    for raw_line in text.splitlines():
        line = re.sub(r"\x1b\[[0-9;?]*[A-Za-z]", "", raw_line).strip()
        if not line:
            continue

        header = re.match(r"^([A-Za-z][A-Za-z0-9 ._-]+(?:\([^)]*\))?)\s*$", line)
        if header and "quota" not in line.lower() and "available" not in line.lower():
            current = " ".join(header.group(1).split())
            continue

        pct = re.search(r"(\d{1,3})\s*%", line)
        if current and pct:
            remaining = max(0, min(100, int(pct.group(1))))
            models[normalize_model_name(current)] = {
                "name": current,
                "remaining_percentage": remaining,
                "source": "/usage",
            }
            continue

        if current and "quota available" in line.lower():
            models.setdefault(
                normalize_model_name(current),
                {
                    "name": current,
                    "remaining_percentage": 100,
                    "source": "/usage",
                },
            )

    return models


def main() -> int:
    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    models = parse_usage(text)
    if not models:
        print("No /usage model quota rows found.", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(CACHE_FILE), exist_ok=True)
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {"timestamp": time.time(), "models": models},
            f,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        f.write("\n")

    print(f"Cached {len(models)} model quota entries to {CACHE_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
