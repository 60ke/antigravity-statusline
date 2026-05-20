#!/usr/bin/env python3
"""Antigravity IDE — Status Line Script
Row 1: model · state · context left · path · quota · session tokens
Row 2: 💡 Tip  (rotates at most once every 3 seconds, persisted across restarts)
"""
import sys
import json
import time
import os
import random
import select
import re
import subprocess
import http.client
import ssl
from datetime import datetime, timezone

# ── ANSI Colors ────────────────────────────────────────────────────────────────
RESET        = "\033[0m"
BOLD         = "\033[1m"
GRAY         = "\033[90m"
WHITE        = "\033[37m"
GREEN        = "\033[32m"
YELLOW       = "\033[33m"
ORANGE       = "\033[38;5;208m"
LIGHT_ORANGE = "\033[38;5;214m"
RED          = "\033[31m"
MAGENTA      = "\033[35m"
CYAN         = "\033[36m"
BLUE         = "\033[34m"
PURPLE       = "\033[38;5;141m"

# ── Tips ───────────────────────────────────────────────────────────────────────
TIPS = [
    "Use /goal for complex, multi-step tasks that need deep focus.",
    "Press Ctrl+O to expand tool output details inline.",
    "Try /grill-me to refine your implementation plan interactively.",
    "Use /agents to see all active sub-agents and their status.",
    "Mention @conversation to reference past work in any session.",
    "Run agy --sandbox for restricted, sandboxed command execution.",
    "Use /schedule to automate recurring tasks or set reminders.",
    "Press Ctrl+R to search through your full command history.",
    "Use /changelog to see what's new in the latest release.",
    "Drag a file into the chat to attach it as context.",
    "Use /goal overnight for thorough, unattended long-running tasks.",
    "Prefix a message with ! to run it as a shell command directly.",
]

TIP_CACHE_FILE = "/tmp/agy_status_tip.json"
TIP_MIN_SECONDS = 3.0   # minimum seconds before rotating to the next tip
QUOTA_CACHE_FILE = os.environ.get(
    "AGY_QUOTA_CACHE",
    os.path.expanduser("~/.antigravity/quota-cache.json"),
)
STATUS_STATE_FILE = os.environ.get(
    "AGY_STATUS_STATE",
    os.path.expanduser("~/.antigravity/status-state.json"),
)
QUOTA_MAX_AGE_SECONDS = float(os.environ.get("AGY_QUOTA_MAX_AGE_SECONDS", "900"))
QUOTA_REFRESH_INTERVAL_SECONDS = float(os.environ.get("AGY_QUOTA_REFRESH_INTERVAL_SECONDS", "30"))
USER_STATUS_PATH = "/exa.language_server_pb.LanguageServerService/GetUserStatus"

# ── Helpers ────────────────────────────────────────────────────────────────────
def format_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.0f}k"
    return str(n)


def context_color(pct: float) -> str:
    if pct >= 50:
        return GREEN
    elif pct >= 20:
        return ORANGE
    else:
        return RED


def normalize_model_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def quota_color(pct: float) -> str:
    if pct >= 50:
        return PURPLE
    if pct >= 20:
        return LIGHT_ORANGE
    return RED


def format_reset_time(reset_time: str) -> str:
    try:
        reset = datetime.fromisoformat(reset_time.replace("Z", "+00:00"))
        diff = int((reset - datetime.now(timezone.utc)).total_seconds())
    except Exception:
        return ""

    if diff <= 0:
        return "now"
    minutes = (diff + 59) // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, mins = divmod(minutes, 60)
    if hours >= 24:
        days, rem_hours = divmod(hours, 24)
        return f"{days}d {rem_hours}h" if rem_hours else f"{days}d"
    return f"{hours}h {mins}m" if mins else f"{hours}h"


def extract_arg(command_line: str, name: str) -> str:
    match = re.search(rf"{re.escape(name)}(?:=|\s+)([^\s\"']+|\"[^\"]+\"|'[^']+')", command_line)
    if not match:
        return ""
    return match.group(1).strip("\"'")


def find_server_candidates() -> list[dict]:
    try:
        ps = subprocess.check_output(["ps", "auxww"], text=True, timeout=1.5)
    except Exception:
        return []

    candidates = []
    for line in ps.splitlines():
        lower = line.lower()
        is_cli = re.search(r"\bagy(\s|$)", line) is not None
        is_language_server = "language_server" in lower
        if not is_cli and not is_language_server:
            continue
        parts = line.split(None, 10)
        if len(parts) < 11:
            continue
        try:
            pid = int(parts[1])
        except ValueError:
            continue
        token = extract_arg(parts[10], "--csrf_token")
        score = 10
        if is_cli:
            score += 40
        if is_language_server:
            score += 20
        if token:
            score += 10
        if "/applications/antigravity.app" in lower:
            score -= 10
        candidates.append({
            "pid": pid,
            "csrf_token": token,
            "score": score,
            "kind": "cli" if is_cli else "language_server",
        })

    return sorted(candidates, key=lambda x: x["score"], reverse=True)


def get_listening_ports(pid: int) -> list[int]:
    try:
        out = subprocess.check_output(
            ["lsof", "-nP", "-a", "-p", str(pid), "-iTCP", "-sTCP:LISTEN"],
            text=True,
            timeout=1.5,
        )
    except Exception:
        return []

    ports = []
    for match in re.finditer(r":(\d+)\s+\(LISTEN\)", out):
        port = int(match.group(1))
        if port not in ports:
            ports.append(port)
    return sorted(ports)


def request_user_status(port: int, csrf_token: str, use_https: bool) -> dict:
    body = json.dumps({
        "metadata": {
            "ideName": "antigravity",
            "extensionName": "antigravity",
            "locale": "en",
        }
    })
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Connect-Protocol-Version": "1",
    }
    if csrf_token:
        headers["X-Codeium-Csrf-Token"] = csrf_token
    if use_https:
        conn = http.client.HTTPSConnection(
            "127.0.0.1",
            port,
            timeout=2,
            context=ssl._create_unverified_context(),
        )
    else:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    conn.request("POST", USER_STATUS_PATH, body, headers)
    res = conn.getresponse()
    raw = res.read().decode("utf-8", "replace")
    if res.status < 200 or res.status >= 300:
        raise RuntimeError(f"HTTP {res.status}")
    return json.loads(raw)


def parse_user_status_quota(response: dict) -> dict:
    user_status = response.get("userStatus", {})
    plan_status = user_status.get("planStatus", {})
    plan_info = plan_status.get("planInfo", {})
    cascade = user_status.get("cascadeModelConfigData", {})
    models = {}

    for model in cascade.get("clientModelConfigs", []) or []:
        quota_info = model.get("quotaInfo") or {}
        if "remainingFraction" not in quota_info:
            continue
        label = model.get("label") or model.get("modelOrAlias", {}).get("model") or "Unknown"
        remaining = max(0.0, min(100.0, float(quota_info.get("remainingFraction", 0)) * 100))
        entry = {
            "name": label,
            "remaining_percentage": remaining,
            "source": "local_language_server",
        }
        reset_time = quota_info.get("resetTime")
        if reset_time:
            entry["reset_time"] = reset_time
            entry["refreshes_in"] = format_reset_time(reset_time)
        models[normalize_model_name(label)] = entry

    return {
        "timestamp": time.time(),
        "source": "local_language_server",
        "scope": {
            "email": user_status.get("email") or "",
            "plan_tier": plan_info.get("planName") or "",
        },
        "models": models,
    }


def fetch_live_quota_cache(expected_email: str = "") -> dict:
    fallback = {}
    expected = (expected_email or "").lower()

    for process_info in find_server_candidates():
        ports = get_listening_ports(process_info["pid"])
        for port in ports:
            for use_https in (True, False):
                try:
                    response = request_user_status(
                        port,
                        process_info.get("csrf_token", ""),
                        use_https,
                    )
                    cache = parse_user_status_quota(response)
                    if not cache.get("models"):
                        continue
                    cache["source_process"] = process_info.get("kind", "")
                    cache["source_port"] = port
                    email = str(cache.get("scope", {}).get("email", "")).lower()
                    if expected and email == expected:
                        return cache
                    if not fallback:
                        fallback = cache
                except Exception:
                    continue
    return fallback


def read_json_file(path: str) -> dict:
    try:
        with open(path, "r") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_quota_cache(cache: dict) -> None:
    try:
        os.makedirs(os.path.dirname(QUOTA_CACHE_FILE), exist_ok=True)
        with open(QUOTA_CACHE_FILE, "w") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    except Exception:
        pass


def quota_scope(data: dict) -> dict:
    return {
        "email": data.get("email") or "",
        "plan_tier": data.get("plan_tier") or "",
    }


def write_status_state(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATUS_STATE_FILE), exist_ok=True)
        state = quota_scope(data)
        state["session_id"] = data.get("conversation_id") or data.get("session_id") or ""
        model_info = data.get("model", {})
        if isinstance(model_info, dict):
            state["model"] = model_info.get("display_name") or model_info.get("id") or ""
        else:
            state["model"] = str(model_info or "")
        state["timestamp"] = time.time()
        with open(STATUS_STATE_FILE, "w") as f:
            json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
    except Exception:
        pass


def scope_mismatch(cache: dict, data: dict) -> str:
    expected = quota_scope(data)
    actual = cache.get("scope", {})
    if not isinstance(actual, dict):
        return "scope"

    for key, label in (
        ("email", "account"),
        ("plan_tier", "plan"),
    ):
        # CLI status JSON says "Google AI Pro"; local API says "Pro".
        if key == "plan_tier" and expected.get(key) and actual.get(key):
            if expected[key].lower().endswith(str(actual[key]).lower()):
                continue
        if expected.get(key) and actual.get(key) and actual.get(key) != expected.get(key):
            return label
    return ""


def should_refresh_quota(data: dict, cache: dict) -> bool:
    if not cache:
        return True
    now = time.time()
    ts = float(cache.get("timestamp", 0) or 0)
    if not ts or now - ts >= QUOTA_REFRESH_INTERVAL_SECONDS:
        return True
    state = read_json_file(STATUS_STATE_FILE)
    current_session = data.get("conversation_id") or data.get("session_id") or ""
    if current_session and state.get("session_id") and state.get("session_id") != current_session:
        return True
    if scope_mismatch(cache, data):
        return True
    return False


def refresh_quota_if_needed(data: dict) -> dict:
    cache = read_json_file(QUOTA_CACHE_FILE)
    if should_refresh_quota(data, cache):
        live_cache = fetch_live_quota_cache(data.get("email") or "")
        if live_cache:
            cache = live_cache
            write_quota_cache(cache)
    return cache


def load_quota_for_model(model_name: str, data: dict) -> dict:
    """Read the latest /usage cache and return the entry for the active model."""
    cache = refresh_quota_if_needed(data)
    if not cache:
        return {}

    mismatch = scope_mismatch(cache, data)
    if mismatch:
        return {"stale": True, "reason": mismatch}

    ts = float(cache.get("timestamp", 0) or 0)
    if ts and time.time() - ts > QUOTA_MAX_AGE_SECONDS:
        return {"stale": True, "reason": "age"}

    models = cache.get("models", {})
    if not isinstance(models, dict):
        return {}

    wanted = normalize_model_name(model_name)
    if wanted in models:
        return models[wanted]

    for key, value in models.items():
        key_norm = normalize_model_name(key)
        if key_norm and (key_norm in wanted or wanted in key_norm):
            return value
    return {}


def get_tip(force_rotate=False) -> str:
    """Return the current tip. Rotate if force_rotate is True or if time is up."""
    now = time.time()
    tip = ""
    ts = 0.0

    try:
        with open(TIP_CACHE_FILE, "r") as f:
            cache = json.load(f)
        tip = cache.get("tip", "")
        ts  = float(cache.get("timestamp", 0))
    except Exception:
        pass

    if tip and not force_rotate and (now - ts) < TIP_MIN_SECONDS:
        return tip

    # Pick a new tip that's different from the current one if possible
    choices = [t for t in TIPS if t != tip] or TIPS
    new_tip = random.choice(choices)
    
    try:
        with open(TIP_CACHE_FILE, "w") as f:
            json.dump({"tip": new_tip, "timestamp": now}, f)
    except Exception:
        pass
        
    return new_tip


# ── Rendering ──────────────────────────────────────────────────────────────────
SEP = f" {GRAY}│{RESET} "


def render(data: dict) -> str:
    # 1. Model
    model_info = data.get("model", {})
    if isinstance(model_info, dict):
        raw_name = model_info.get("display_name") or model_info.get("id") or "AGY"
    else:
        raw_name = str(model_info) or "AGY"
    model_display = f"{YELLOW}{BOLD}{raw_name}{RESET}"

    # 2. Agent state
    state = data.get("agent_state", "idle")
    state_colors = {
        "working": CYAN,
        "idle":    GRAY,
        "waiting": LIGHT_ORANGE,
        "error":   RED,
    }
    sc = state_colors.get(state, WHITE)
    state_display = f"{sc}{state.capitalize()}{RESET}"

    # 3. Context window
    cw      = data.get("context_window", {})
    rem_pct = float(cw.get("remaining_percentage", 100.0))
    cc      = context_color(rem_pct)
    ctx_display = f"{cc}Context {rem_pct:.0f}% left{RESET}"

    # 4. Session token totals
    in_t    = int(cw.get("total_input_tokens",  0))
    out_t   = int(cw.get("total_output_tokens", 0))
    total_t = in_t + out_t
    tokens_display = (
        f"{GRAY}↑{format_tokens(in_t)} ↓{format_tokens(out_t)}"
        f"  {WHITE}{format_tokens(total_t)} tok{RESET}"
    )

    # 5. Quota from the cached /usage output for the active model
    quota = load_quota_for_model(raw_name, data)
    if quota.get("stale"):
        reason = quota.get("reason", "stale")
        quota_display = f"{GRAY}⬡ Quota: sync /usage ({reason}){RESET}"
    elif "remaining_percentage" in quota:
        quota_pct = float(quota["remaining_percentage"])
        qc = quota_color(quota_pct)
        reset_in = quota.get("refreshes_in") or ""
        reset_display = f"{GRAY} · reset {reset_in}{RESET}" if reset_in else ""
        quota_display = f"{qc}⬡ Quota: {quota_pct:.0f}%{RESET}{reset_display}"
    else:
        quota_display = f"{GRAY}⬡ Quota: sync /usage{RESET}"

    # 6. Working directory
    cwd  = data.get("cwd", "")
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]
    path_display = f"{GREEN}{cwd}{RESET}"

    # 7. Sandbox badge
    sandbox_enabled = data.get("sandbox", {}).get("enabled", False)
    sandbox_str = f" {ORANGE}[sandbox]{RESET}" if sandbox_enabled else ""

    # 8. Tip (stable for ≥ 3 s)
    tip         = get_tip()
    tip_display = f"{BLUE}💡 {tip}{RESET}"

    # ── Assemble rows ──────────────────────────────────────────────────────────
    row1 = (
        f"{model_display}{SEP}"
        f"{state_display}{SEP}"
        f"{ctx_display}{SEP}"
        f"{path_display}{sandbox_str}{SEP}"
        f"{quota_display}{SEP}"
        f"{tokens_display}"
    )
    row2 = f"  {tip_display}"

    return f"{row1}\n{row2}"


# ── Main loop ──────────────────────────────────────────────────────────────────
def main():
    decoder = json.JSONDecoder()
    buffer  = ""
    last_data = None
    last_redraw_time = 0.0

    while True:
        try:
            # Use select to wait for input with a timeout of 1 second
            r, _, _ = select.select([sys.stdin], [], [], 1.0)
            
            if r:
                chunk = sys.stdin.read(1)
                if not chunk:
                    break
                buffer += chunk

                if chunk == "}":
                    while buffer:
                        stripped = buffer.lstrip()
                        if not stripped:
                            buffer = ""
                            break
                        try:
                            data, idx = decoder.raw_decode(stripped)
                            buffer = stripped[idx:]
                            if isinstance(data, dict) and "model" in data:
                                write_status_state(data)
                                last_data = data
                                print(render(last_data), flush=True)
                                last_redraw_time = time.time()
                        except json.JSONDecodeError:
                            break
            
            # If no input arrived recently, but we have last_data, check if we should rotate tip
            elif last_data:
                now = time.time()
                # Check if 3 seconds have passed since we last got a new tip
                # get_tip() handles the 3-second cache logic internally
                current_tip = get_tip()
                # To actually redraw on idle state, we force print if 3 seconds passed
                try:
                    with open(TIP_CACHE_FILE, "r") as f:
                        cache = json.load(f)
                        ts = float(cache.get("timestamp", 0))
                except Exception:
                    ts = now
                
                # If time since last tip generation is >= 3, get_tip() will generate a new one
                # If time is up, we should render and print.
                if now - ts >= TIP_MIN_SECONDS:
                    print(render(last_data), flush=True)

        except EOFError:
            break
        except Exception:
            time.sleep(0.05)


if __name__ == "__main__":
    main()
