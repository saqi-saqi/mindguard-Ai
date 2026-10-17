"""
Discovery + normalisation layer for the MindGuard deep test-suite.

I could only read the README of the repo, not the source files, so instead of
hard-coding guessed names this module DISCOVERS them at runtime (routes from
Flask's url_map, rule functions from crisis_rules.py, etc.).

If discovery picks the wrong thing, set the matching key in OVERRIDES below.
That is the ONLY place you should ever need to edit.
"""
from __future__ import annotations

import dataclasses
import importlib
import inspect
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

def _find_project_root() -> Path:
    """Find the checkout rather than assuming this bundle lives at its root."""
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "server" / "app.py").is_file():
            return candidate
    return Path(__file__).resolve().parents[2]


ROOT = _find_project_root()
for _p in (ROOT, ROOT / "server"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# --------------------------------------------------------------------------- #
# EDIT HERE ONLY IF AUTO-DISCOVERY GETS SOMETHING WRONG
# --------------------------------------------------------------------------- #
OVERRIDES: dict[str, Optional[str]] = {
    "rules_func": None,       # e.g. "detect_crisis"  (function inside crisis_rules.py)
    "chat_route": None,       # e.g. "/api/chat"
    "register_route": None,   # e.g. "/api/auth/register"
    "login_route": None,      # e.g. "/api/auth/login"
    "history_route": None,    # e.g. "/api/history"   (GET, per-user chat history)
    "message_key": None,      # e.g. "message"        (JSON key holding user text)
}

# Allowed CORS origin from the README. Change if your config differs.
ALLOWED_ORIGIN = "http://localhost:5173"

# --------------------------------------------------------------------------- #
# Module discovery
# --------------------------------------------------------------------------- #

def import_first(names: Iterable[str]):
    errs = []
    for n in names:
        try:
            return importlib.import_module(n)
        except Exception as e:  # noqa: BLE001
            errs.append(f"{n}: {e!r}")
    raise ImportError("Could not import any of: " + " | ".join(errs))


def get_app():
    mod = import_first(["server.app", "app"])
    if hasattr(mod, "app"):
        return mod.app
    if hasattr(mod, "create_app"):
        return mod.create_app()
    raise LookupError("server/app.py exposes neither `app` nor `create_app()`")


def modules_named(suffix: str) -> list:
    """All already-imported module copies whose name is `suffix` or ends with .suffix.
    (The repo may be imported as `services.x` or `server.services.x`; we handle both.)"""
    found = []
    for name, m in list(sys.modules.items()):
        if m is not None and (name == suffix or name.endswith("." + suffix)):
            found.append(m)
    return found


def service_module(suffix: str):
    """Return the module actually used by the running app (imports the app first)."""
    get_app()
    mods = modules_named(suffix)
    if mods:
        return mods[0]
    return import_first([f"server.services.{suffix}", f"services.{suffix}"])


def rules_module():
    return service_module("crisis_rules")


# --------------------------------------------------------------------------- #
# Tier-1 rule function discovery
# --------------------------------------------------------------------------- #
_RULE_NAMES = [
    "detect_crisis", "check_crisis", "analyze_crisis", "assess_crisis", "evaluate_crisis",
    "crisis_check", "crisis_detect", "detect", "check", "analyze", "analyse", "assess",
    "evaluate", "classify", "scan", "run_rules", "check_text", "assess_risk", "detect_risk",
]


def _required_params(fn) -> int:
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):
        return 1
    return sum(
        1 for p in sig.parameters.values()
        if p.default is p.empty and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
        and p.name not in ("self", "cls")
    )


def rules_callable():
    mod = rules_module()
    if OVERRIDES["rules_func"]:
        return getattr(mod, OVERRIDES["rules_func"])
    for n in _RULE_NAMES:
        f = getattr(mod, n, None)
        if callable(f) and not inspect.isclass(f) and _required_params(f) == 1:
            return f
    # any public single-arg function whose name smells right
    for n, f in inspect.getmembers(mod, inspect.isfunction):
        if f.__module__ == mod.__name__ and not n.startswith("_") \
                and re.search(r"crisis|risk|detect|assess", n, re.I) and _required_params(f) == 1:
            return f
    # class based engine
    for cn, cls in inspect.getmembers(mod, inspect.isclass):
        if cls.__module__ != mod.__name__:
            continue
        try:
            inst = cls()
        except Exception:  # noqa: BLE001
            continue
        for n in _RULE_NAMES:
            f = getattr(inst, n, None)
            if callable(f):
                return f
    raise LookupError(
        "Could not auto-discover the Tier-1 rule function in crisis_rules.py. "
        "Set OVERRIDES['rules_func'] in tests/deep/mg_adapter.py"
    )


# --------------------------------------------------------------------------- #
# Verdict normalisation (handles bool / dict / dataclass / object / tuple)
# --------------------------------------------------------------------------- #
BOOL_KEYS = ("is_crisis", "crisis", "crisis_detected", "is_high_risk", "high_risk",
             "flagged", "triggered", "bypass_llm", "bypass", "emergency", "is_emergency")
LEVEL_KEYS = ("risk_level", "crisis_level", "level", "risk", "severity", "label",
              "category", "status", "risk_category", "crisis_type", "type")
_HIGH = re.compile(r"(high|crisis|critical|severe|emergency|imminent|immediate|harm_to_others|threat_against_user)", re.I)
_NOT_HIGH = re.compile(r"(no[_ -]?crisis|non[_ -]?crisis|not|low|none|safe|neutral|normal|medium|moderate)", re.I)


@dataclass
class Verdict:
    is_crisis: bool
    level: Optional[str] = None
    raw: Any = None


def _as_mapping(obj) -> Optional[dict]:
    if isinstance(obj, dict):
        return obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return dataclasses.asdict(obj)
    if hasattr(obj, "_asdict"):
        return obj._asdict()
    if hasattr(obj, "__dict__") and not inspect.isclass(obj):
        return {k: v for k, v in vars(obj).items() if not k.startswith("_")}
    return None


def _level_is_high(v) -> bool:
    s = getattr(v, "name", None) or getattr(v, "value", None) or v
    s = str(s)
    return bool(_HIGH.search(s)) and not _NOT_HIGH.search(s)


def walk(obj, depth=0):
    """Yield (key, value) for every key in nested dict/list structures."""
    if depth > 6:
        return
    m = _as_mapping(obj) if not isinstance(obj, (str, bytes, int, float, bool, type(None))) else None
    if m is not None:
        for k, v in m.items():
            yield k, v
            yield from walk(v, depth + 1)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from walk(v, depth + 1)


def structured_signal(obj) -> Optional[tuple[bool, Optional[str]]]:
    """Return (is_crisis, level) if `obj` carries any recognised keys, else None."""
    seen = False
    crisis = False
    level = None
    for k, v in walk(obj):
        lk = str(k).lower()
        if lk in BOOL_KEYS and isinstance(v, bool):
            seen = True
            crisis = crisis or v
        elif lk in LEVEL_KEYS and (isinstance(v, str) or hasattr(v, "name")):
            seen = True
            if _level_is_high(v):
                crisis = True
            level = level or str(getattr(v, "name", v))
    return (crisis, level) if seen else None


def verdict(raw) -> Verdict:
    if raw is None:
        return Verdict(False, None, raw)
    if isinstance(raw, bool):
        return Verdict(raw, None, raw)
    if isinstance(raw, (list, tuple)) and raw:
        if isinstance(raw[0], bool):
            return Verdict(raw[0], str(raw[1]) if len(raw) > 1 else None, raw)
        return verdict(raw[0])
    if isinstance(raw, str):
        return Verdict(_level_is_high(raw), raw, raw)
    sig = structured_signal(raw)
    if sig is not None:
        return Verdict(sig[0], sig[1], raw)
    return Verdict(bool(raw), None, raw)


def run_rules(text) -> Verdict:
    return verdict(rules_callable()(text))


# --------------------------------------------------------------------------- #
# HTTP-level helpers
# --------------------------------------------------------------------------- #

def routes(app) -> list[tuple[str, list[str]]]:
    out = []
    for r in app.url_map.iter_rules():
        if r.endpoint == "static":
            continue
        out.append((r.rule, sorted(r.methods - {"HEAD", "OPTIONS"})))
    return sorted(out)


def find_route(app, pattern: str, method: str = "POST") -> Optional[str]:
    for rule, methods in routes(app):
        if method in methods and "<" not in rule and re.search(pattern, rule, re.I):
            return rule
    return None


def chat_route(app):
    return OVERRIDES["chat_route"] or find_route(app, r"chat|message|analy[sz]e|predict|respond")


def register_route(app):
    return OVERRIDES["register_route"] or find_route(app, r"regist|sign-?up")


def login_route(app):
    return OVERRIDES["login_route"] or find_route(app, r"log-?in|sign-?in|auth(?!.*regist)")


def history_route(app):
    return OVERRIDES["history_route"] or find_route(app, r"histor|conversation|session|messages", "GET")


_TOKEN_KEYS = ("token", "access_token", "accesstoken", "jwt", "id_token")


def find_token(payload) -> Optional[str]:
    for k, v in walk(payload):
        if str(k).lower() in _TOKEN_KEYS and isinstance(v, str) and v.count(".") == 2:
            return v
    return None


def _user_payloads(username: str, email: str, pw: str) -> list[dict]:
    return [
        {"username": username, "email": email, "password": pw},
        {"email": email, "password": pw},
        {"username": username, "password": pw},
        {"name": username, "email": email, "password": pw},
        {"full_name": username, "username": username, "email": email, "password": pw},
        {"name": username, "username": username, "email": email, "password": pw},
    ]


def register(client, app, username: str, pw: str):
    """Register a user, trying common payload shapes. Returns (response, payload_used, token_or_None)."""
    route = register_route(app)
    if not route:
        return None, None, None
    email = f"{username}@example.com"
    last = None
    for p in _user_payloads(username, email, pw):
        r = client.post(route, json=p)
        last = (r, p)
        if r.status_code in (200, 201):
            return r, p, find_token(r.get_json(silent=True))
    return last[0], last[1], None


def login(client, app, payload: dict):
    route = login_route(app)
    if not route:
        return None, None
    creds = {k: v for k, v in payload.items() if k in ("username", "email", "password")}
    # try full set, then each identifier on its own
    attempts = [creds]
    for ident in ("email", "username"):
        if ident in creds:
            attempts.append({ident: creds[ident], "password": creds["password"]})
    r = None
    for a in attempts:
        r = client.post(route, json=a)
        if r.status_code == 200:
            tok = find_token(r.get_json(silent=True))
            if tok:
                return r, tok
    return r, None


def auth_headers(token: Optional[str]) -> dict:
    return {"Authorization": f"Bearer {token}"} if token else {}


_WORKING_KEY: dict[str, str] = {}
_MESSAGE_KEYS = ["message", "text", "content", "query", "input", "user_message", "prompt"]


def chat(client, app, text, headers=None, extra: Optional[dict] = None):
    """POST a chat message, discovering which JSON key the API wants."""
    route = chat_route(app)
    assert route, "No chat route discovered; set OVERRIDES['chat_route'] in tests/deep/mg_adapter.py"
    keys = [OVERRIDES["message_key"]] if OVERRIDES["message_key"] else (
        [_WORKING_KEY["k"]] if "k" in _WORKING_KEY else _MESSAGE_KEYS)
    resp = None
    for k in keys:
        body = {k: text, **(extra or {})}
        resp = client.post(route, json=body, headers=headers or {})
        if resp.status_code not in (400, 422):
            _WORKING_KEY["k"] = k
            return resp
    return resp


def response_signal(resp) -> tuple[bool, str]:
    """Did the API response flag a crisis? Returns (flagged, how_we_know)."""
    data = resp.get_json(silent=True)
    if data is not None:
        sig = structured_signal(data)
        if sig is not None:
            return sig[0], f"structured keys -> level={sig[1]}"
    text = resp.get_data(as_text=True)
    return ("1122" in text), "fallback: emergency number 1122 in body"


_REPLY_KEYS = ("reply", "response", "message", "answer", "text", "content", "bot_response", "output")


def reply_text(resp) -> str:
    data = resp.get_json(silent=True)
    if data is None:
        return resp.get_data(as_text=True)
    best = ""
    for k, v in walk(data):
        if str(k).lower() in _REPLY_KEYS and isinstance(v, str) and len(v) > len(best):
            best = v
    return best or resp.get_data(as_text=True)
