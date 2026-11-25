#!/usr/bin/env python3
"""Antigravity IDE — Status Line Script
Responsive status line with dynamic multi-line wrapping:
model · state · context left · path · branch · quota · session tokens
"""
import sys
import json
import time
import os
import select
import re
import subprocess
import http.client
import ssl
import shutil
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

# ── Responsive & Width Helpers ─────────────────────────────────────────────────
ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE_RE.sub("", text)


def visible_length(text: str) -> int:
    return len(strip_ansi(text))


def get_terminal_width(data: dict) -> int:
    w = data.get("terminal_width")
    if isinstance(w, (int, float)) and w > 0:
        return int(w)
    w = data.get("columns")
    if isinstance(w, (int, float)) and w > 0:
        return int(w)
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        pass
    try:
        return int(os.environ.get("COLUMNS", 80))
    except Exception:
        return 80


def shorten_path(path: str, max_chars: int = 28) -> str:
    if len(path) <= max_chars:
        return path
    parts = path.split(os.sep)
    if len(parts) <= 2:
        return path
    shortened = parts[0] + os.sep + "…" + os.sep + os.sep.join(parts[-2:])
    return shortened if len(shortened) < len(path) else path


QUOTA_CACHE_FILE = os.environ.get(
    "AGY_QUOTA_CACHE",
    os.path.expanduser("~/.antigravity/quota-cache.json"),
)
STATUS_STATE_FILE = os.environ.get(
    "AGY_STATUS_STATE",
    os.path.expanduser("~/.antigravity/status-state.json"),
)
STATUS_DEBUG_FILE = os.environ.get(
    "AGY_STATUS_DEBUG_FILE",
    os.path.expanduser("~/.antigravity/latest-payload.json"),
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


def format_seconds(diff: int) -> str:
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


def format_reset_time(reset_time: str) -> str:
    try:
        reset = datetime.fromisoformat(reset_time.replace("Z", "+00:00"))
        if reset.tzinfo is None:
            reset = reset.replace(tzinfo=timezone.utc)
        # Unix epoch sentinel (e.g. 1970-01-01T00:00:00Z) means no active reset window.
        if reset.timestamp() <= 0:
            return ""
        diff = int((reset - datetime.now(timezone.utc)).total_seconds())
        return format_seconds(diff)
    except Exception:
        return ""


_GIT_CACHE: dict[str, tuple[float, str]] = {}


def get_git_info(cwd_raw: str) -> str:
    if not cwd_raw:
        return ""
    cwd_dir = os.path.expanduser(cwd_raw)
    if not os.path.isdir(cwd_dir):
        return ""

    now = time.time()
    cached = _GIT_CACHE.get(cwd_dir)
    if cached and (now - cached[0]) < 1.5:
        return cached[1]

    try:
        res = subprocess.run(
            ["git", "-C", cwd_dir, "rev-parse", "--is-inside-work-tree", "--abbrev-ref", "HEAD"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=0.4,
        )
        if res.returncode != 0:
            _GIT_CACHE[cwd_dir] = (now, "")
            return ""

        lines = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        if not lines or lines[0] != "true":
            _GIT_CACHE[cwd_dir] = (now, "")
            return ""

        branch = lines[1] if len(lines) > 1 else ""
        if not branch or branch == "HEAD":
            rev = subprocess.run(
                ["git", "-C", cwd_dir, "rev-parse", "--short", "HEAD"],
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                timeout=0.3,
            )
            short_hash = rev.stdout.strip()
            branch = f":{short_hash}" if rev.returncode == 0 and short_hash else "detached"

        # Check for uncommitted or untracked changes
        status_res = subprocess.run(
            ["git", "-C", cwd_dir, "status", "--porcelain"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=0.4,
        )
        is_dirty = bool(status_res.returncode == 0 and status_res.stdout.strip())

        dirty_indicator = f"{YELLOW}*{RESET}" if is_dirty else ""
        display = f"{MAGENTA} {branch}{RESET}{dirty_indicator}"

        _GIT_CACHE[cwd_dir] = (now, display)
        return display
    except Exception:
        _GIT_CACHE[cwd_dir] = (now, "")
        return ""


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


def write_json_atomic(path: str, payload: dict) -> None:
    tmp_path = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        try:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
        except Exception:
            pass


def write_quota_cache(cache: dict) -> None:
    write_json_atomic(QUOTA_CACHE_FILE, cache)


def quota_scope(data: dict) -> dict:
    return {
        "email": data.get("email") or "",
        "plan_tier": data.get("plan_tier") or "",
    }


def write_status_state(data: dict) -> None:
    state = quota_scope(data)
    state["session_id"] = data.get("conversation_id") or data.get("session_id") or ""
    model_info = data.get("model")
    if isinstance(model_info, dict):
        state["model"] = model_info.get("display_name") or model_info.get("displayName") or model_info.get("id") or ""
    elif model_info is not None:
        state["model"] = str(model_info)
    else:
        state["model"] = ""
    state["timestamp"] = time.time()
    write_json_atomic(STATUS_STATE_FILE, state)


def write_debug_payload(data: dict) -> None:
    write_json_atomic(STATUS_DEBUG_FILE, data)


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


THIRD_PARTY_MODEL_RE = re.compile(
    r"(?:claude|sonnet|haiku|opus|anthropic|gpt|openai|codex|deepseek|llama|mistral|qwen|grok|kimi|glm|"
    r"(?<![a-z0-9])3p(?![a-z0-9])|(?<![a-z0-9])o[134](?:-[a-z0-9]+)?(?![a-z0-9]))",
    re.IGNORECASE,
)

GENERIC_MODEL_TOKENS = {
    "gemini", "claude", "gpt", "oss", "pro", "flash", "ultra", "nano", "mini",
    "low", "medium", "high", "xhigh", "max", "thinking", "preview", "exp",
    "experimental", "latest", "default", "orchestrator", "model", "3p",
    "5h", "weekly", "wtu", "agy",
}

WINDOW_5H_TOKENS = {"5h", "5hour", "fivehour"}
WINDOW_WEEKLY_TOKENS = {"weekly", "7d", "7day", "sevenday"}
WINDOW_KEY_WORDS = WINDOW_5H_TOKENS | WINDOW_WEEKLY_TOKENS | {"5", "7", "five", "seven", "hour", "day"}


def split_tokens(text: str) -> list[str]:
    return [tok for tok in re.split(r"[^a-z0-9]+", (text or "").lower()) if tok]


def is_third_party_model(model_name: str, model_id: str = "") -> bool:
    combined = f"{model_name or ''} {model_id or ''}".strip()
    return bool(combined and THIRD_PARTY_MODEL_RE.search(combined))


def bucket_window_kind(key: str) -> str:
    key_lower = (key or "").lower()
    tokens = set(split_tokens(key_lower))
    compact = re.sub(r"[^a-z0-9]+", "", key_lower)
    if tokens & WINDOW_5H_TOKENS or "fivehour" in compact or "5hour" in compact:
        return "5h"
    if tokens & WINDOW_WEEKLY_TOKENS or "sevenday" in compact or "7day" in compact:
        return "weekly"
    return ""


def parse_quota_entry(q) -> dict | None:
    if not isinstance(q, dict) or q.get("disabled"):
        return None

    raw_fraction = q.get("remaining_fraction")
    raw_amount = q.get("remaining_amount")
    pct = None
    amount = None
    if raw_fraction is not None:
        try:
            pct = max(0.0, min(100.0, float(raw_fraction) * 100.0))
        except (TypeError, ValueError):
            return None
    elif raw_amount is not None:
        try:
            amount = max(0.0, float(raw_amount))
        except (TypeError, ValueError):
            return None
    else:
        return None

    reset_time = q.get("reset_time")
    reset_time_str = reset_time if isinstance(reset_time, str) else ""
    refreshes_in = format_reset_time(reset_time_str) if reset_time_str else ""
    if not refreshes_in and q.get("reset_in_seconds") is not None:
        try:
            secs = int(q["reset_in_seconds"])
            if secs > 0:
                refreshes_in = format_seconds(secs)
        except (TypeError, ValueError):
            pass

    entry = {
        "reset_time": reset_time_str,
        "refreshes_in": refreshes_in,
    }
    if pct is not None:
        entry["remaining_percentage"] = pct
    else:
        entry["remaining_amount"] = amount
    return entry


def select_payload_buckets(quotas: dict, model_name: str, model_id: str = "") -> tuple[dict | None, dict | None, bool]:
    """Select (5h_bucket, weekly_bucket, saw_disabled) for the active model without cross-family leakage."""
    is_3p = is_third_party_model(model_name, model_id)
    family = "3p" if is_3p else "gemini"
    other_family = "gemini" if is_3p else "3p"

    # Extract specific variant tokens (e.g. "argon", "neon", "opus") to match dedicated buckets first.
    variant_tokens = [
        tok for tok in dict.fromkeys(split_tokens(f"{model_name} {model_id}"))
        if len(tok) >= 3 and not tok.isdigit() and tok not in GENERIC_MODEL_TOKENS
    ]

    saw_disabled = False

    def pick_from_keys(keys: list[str]) -> tuple[dict | None, dict | None]:
        nonlocal saw_disabled
        found_5h = None
        found_weekly = None
        for k in keys:
            val = quotas.get(k)
            if not isinstance(val, dict):
                continue
            kind = bucket_window_kind(k)
            if not kind:
                continue
            if val.get("disabled"):
                saw_disabled = True
                continue
            if kind == "5h" and found_5h is None:
                found_5h = val
            elif kind == "weekly" and found_weekly is None:
                found_weekly = val
        return found_5h, found_weekly

    # 1. Dedicated model-specific buckets (e.g., gemini-argon-wtu-weekly, gemini-argon-5h).
    if variant_tokens:
        dedicated_keys = []
        for k in quotas:
            key_tokens = set(split_tokens(k))
            if other_family in key_tokens:
                continue
            if any(vt in key_tokens for vt in variant_tokens):
                dedicated_keys.append(k)
        if dedicated_keys:
            q_5h, q_weekly = pick_from_keys(dedicated_keys)
            if q_5h is not None or q_weekly is not None:
                return q_5h, q_weekly, saw_disabled

    # 2. Standard family buckets (gemini-5h / gemini-weekly or 3p-5h / 3p-weekly).
    exact_keys = [
        k for k in (
            f"{family}-5h",
            f"{family}-weekly",
            f"{family}_5h",
            f"{family}_weekly",
        )
        if k in quotas
    ]
    q_5h, q_weekly = pick_from_keys(exact_keys)
    if q_5h is not None or q_weekly is not None:
        return q_5h, q_weekly, saw_disabled

    # 3. Any non-variant-specific key belonging strictly to the same family (e.g., gemini-five-hour).
    family_keys = []
    for k in quotas:
        key_tokens = set(split_tokens(k))
        if family not in key_tokens or other_family in key_tokens:
            continue
        # Skip keys clearly scoped to a different model variant (e.g., gemini-argon-wtu-weekly for Neon).
        extra_tokens = key_tokens - {family, "wtu"} - WINDOW_KEY_WORDS
        if extra_tokens and not (extra_tokens & set(variant_tokens)):
            continue
        family_keys.append(k)
    q_5h, q_weekly = pick_from_keys(family_keys)
    return q_5h, q_weekly, saw_disabled


def load_quota_for_model(model_name: str, data: dict, model_id: str = "") -> dict:
    """Extract quota for active model: prefer data['quota'] if present, else fallback to cache."""
    # 1. Prefer direct quota dictionary from Antigravity CLI payload
    quotas = data.get("quota")
    if isinstance(quotas, dict) and quotas:
        q_5h, q_weekly, saw_disabled = select_payload_buckets(quotas, model_name, model_id)
        entry_5h = parse_quota_entry(q_5h)
        entry_weekly = parse_quota_entry(q_weekly)

        if entry_5h or entry_weekly:
            result = {
                "name": model_name,
                "source": "payload",
                "5h": entry_5h,
                "weekly": entry_weekly,
            }
            primary = entry_5h or entry_weekly
            if (
                entry_weekly
                and entry_5h
                and "remaining_percentage" in entry_weekly
                and entry_weekly["remaining_percentage"] < 10.0
            ):
                primary = entry_weekly
            if "remaining_percentage" in primary:
                result["remaining_percentage"] = primary["remaining_percentage"]
            elif "remaining_amount" in primary:
                result["remaining_amount"] = primary["remaining_amount"]
            result["reset_time"] = primary.get("reset_time", "")
            result["refreshes_in"] = primary.get("refreshes_in", "")
            return result

        if saw_disabled:
            return {"disabled": True, "source": "payload"}

    # 2. Fallback to cached / local language server RPC
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


# ── Rendering ──────────────────────────────────────────────────────────────────
SEP = f" {GRAY}│{RESET} "


def format_quota_window(label: str, entry: dict) -> str:
    if "remaining_percentage" in entry:
        pct = float(entry["remaining_percentage"])
        color = quota_color(pct)
        value_str = f"{pct:.0f}%"
    else:
        amt = float(entry.get("remaining_amount", 0.0))
        color = PURPLE if amt > 0 else RED
        value_str = f"{amt:g}"
    reset_str = f" {GRAY}({entry['refreshes_in']}){RESET}" if entry.get("refreshes_in") else ""
    return f"{color}{label}: {value_str}{RESET}{reset_str}"


def render(data: dict) -> str:
    # 1. Model
    model_info = data.get("model")
    model_id = ""
    if isinstance(model_info, dict):
        model_id = str(model_info.get("id") or "")
        raw_name = model_info.get("display_name") or model_info.get("displayName") or model_id or "AGY"
    elif model_info is not None:
        raw_name = str(model_info) or "AGY"
    else:
        raw_name = "AGY"
    model_display = f"{YELLOW}{BOLD}{raw_name}{RESET}"

    # 2. Agent state
    state = str(data.get("agent_state") or "idle")
    state_colors = {
        "working":        CYAN,
        "tool_use":       CYAN,
        "reviewing":      LIGHT_ORANGE,
        "idle":           GRAY,
        "waiting":        LIGHT_ORANGE,
        "authenticating": YELLOW,
        "initializing":   GRAY,
        "error":          RED,
    }
    sc = state_colors.get(state, WHITE)
    state_label = state.replace("_", " ").capitalize()
    state_display = f"{sc}{state_label}{RESET}"

    # 3. Context window
    cw = data.get("context_window")
    if not isinstance(cw, dict):
        cw = {}
    raw_rem_pct = cw.get("remaining_percentage")
    rem_pct = float(raw_rem_pct) if raw_rem_pct is not None else 100.0
    cc      = context_color(rem_pct)
    ctx_display = f"{cc}Context {rem_pct:.0f}% left{RESET}"

    # 4. Session token totals
    in_t    = int(cw.get("total_input_tokens") or 0)
    out_t   = int(cw.get("total_output_tokens") or 0)
    total_t = in_t + out_t
    tokens_display = (
        f"{GRAY}↑{format_tokens(in_t)} ↓{format_tokens(out_t)}"
        f"  {WHITE}{format_tokens(total_t)} tok{RESET}"
    )

    # 5. Quota for the active model (5h & weekly from CLI payload, fallback to cache)
    quota = load_quota_for_model(raw_name, data, model_id=model_id)
    if quota.get("disabled"):
        quota_display = f"{GRAY}⬡ Quota: disabled{RESET}"
    elif quota.get("stale"):
        reason = quota.get("reason", "stale")
        quota_display = f"{GRAY}⬡ Quota: sync /usage ({reason}){RESET}"
    elif quota.get("5h") or quota.get("weekly"):
        parts = []
        if quota.get("5h"):
            parts.append(format_quota_window("⬡ 5h", quota["5h"]))
        if quota.get("weekly"):
            label = "Wk" if parts else "⬡ Wk"
            parts.append(format_quota_window(label, quota["weekly"]))
        quota_display = f" {GRAY}·{RESET} ".join(parts)
    elif "remaining_percentage" in quota:
        quota_pct = float(quota["remaining_percentage"])
        qc = quota_color(quota_pct)
        reset_in = quota.get("refreshes_in") or ""
        reset_display = f"{GRAY} · reset {reset_in}{RESET}" if reset_in else ""
        quota_display = f"{qc}⬡ Quota: {quota_pct:.0f}%{RESET}{reset_display}"
    else:
        quota_display = f"{GRAY}⬡ Quota: sync /usage{RESET}"

    # 6. Working directory
    cwd_raw = data.get("cwd") or os.getcwd()
    cwd  = cwd_raw
    home = os.path.expanduser("~")
    if cwd.startswith(home):
        cwd = "~" + cwd[len(home):]

    term_width = get_terminal_width(data)
    if term_width < 80 and len(cwd) > 28:
        cwd = shorten_path(cwd, 24)

    path_display = f"{GREEN}{cwd}{RESET}"

    # 7. Git branch status
    git_display = get_git_info(cwd_raw)

    # 8. Sandbox badge
    sandbox = data.get("sandbox")
    sandbox_enabled = bool(sandbox.get("enabled", False)) if isinstance(sandbox, dict) else False
    sandbox_str = f" {ORANGE}[sandbox]{RESET}" if sandbox_enabled else ""

    # ── Assemble segments ──────────────────────────────────────────────────────
    segments = [
        model_display,
        state_display,
        ctx_display,
        f"{path_display}{sandbox_str}",
    ]
    if git_display:
        segments.append(git_display)
    segments.extend([
        quota_display,
        tokens_display,
    ])

    # ── Responsive Line Packing ────────────────────────────────────────────────
    sep_vis_len = visible_length(SEP)
    total_single_line_len = sum(visible_length(s) for s in segments) + sep_vis_len * (len(segments) - 1)

    if total_single_line_len <= term_width:
        return SEP.join(segments)

    rows: list[str] = []
    current_row: list[str] = []
    current_row_len = 0

    for seg in segments:
        seg_len = visible_length(seg)
        if not current_row:
            current_row.append(seg)
            current_row_len = seg_len
        else:
            if current_row_len + sep_vis_len + seg_len <= term_width:
                current_row.append(seg)
                current_row_len += sep_vis_len + seg_len
            else:
                rows.append(SEP.join(current_row))
                current_row = [seg]
                current_row_len = seg_len

    if current_row:
        rows.append(SEP.join(current_row))

    return "\n".join(rows)


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
                            if isinstance(data, dict):
                                write_debug_payload(data)
                                if "model" in data:
                                    write_status_state(data)
                                    last_data = data
                                    print(render(last_data), flush=True)
                                    last_redraw_time = time.time()
                        except json.JSONDecodeError:
                            break
            
            elif last_data:
                now = time.time()
                if now - last_redraw_time >= 10.0:
                    print(render(last_data), flush=True)
                    last_redraw_time = now

        except EOFError:
            break
        except Exception:
            time.sleep(0.05)


if __name__ == "__main__":
    main()
