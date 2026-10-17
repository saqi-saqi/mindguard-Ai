"""
BACKEND API + AUTH + DATABASE + SECURITY + PRIVACY CLAIMS.

Covers: validation, auth (bcrypt/JWT), IDOR/isolation, NoSQL injection,
rate-limit (60/min), CORS, log redaction, error leakage, concurrency,
secret scanning, and repo/Docker hygiene.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import threading
import uuid
from pathlib import Path

import pytest

from mg_adapter import (
    ALLOWED_ORIGIN, ROOT, auth_headers, chat, chat_route, find_token, history_route,
    login, login_route, register, register_route, reply_text, routes,
)
from mg_support import (
    FAKE_GEMINI_KEY, FAKE_JWT_SECRET, STRONG_PW, dump_all_documents, new_client,
)


def _b64(d: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()


def _need(route, what):
    if not route:
        pytest.skip(f"{what} route not discovered; set OVERRIDES in mg_adapter.py")
    return route


# =========================================================================== #
# 1. ROUTE INVENTORY (so you can see exactly what the suite discovered)
# =========================================================================== #
def test_route_inventory(flask_app, capsys):
    inv = routes(flask_app)
    with capsys.disabled():
        print("\n  Discovered routes:")
        for rule, methods in inv:
            print(f"    {','.join(methods):<14} {rule}")
        print(f"  chat={chat_route(flask_app)}  register={register_route(flask_app)}  "
              f"login={login_route(flask_app)}  history={history_route(flask_app)}")
    assert inv, "no routes found"
    assert chat_route(flask_app), "chat route not discovered"


# =========================================================================== #
# 2. INPUT VALIDATION: bad input must give 4xx, never 500
# =========================================================================== #
BAD_BODIES = [
    None, [], "just a string", 12345, {}, {"message": None}, {"message": 123},
    {"message": ""}, {"message": "   "}, {"message": ["a", "b"]},
    {"message": {"$ne": 1}}, {"message": True}, {"unrelated": "x"},
    {"message": "x" * 200_000},
]


@pytest.mark.parametrize("body", BAD_BODIES, ids=[f"body{i}" for i in range(len(BAD_BODIES))])
def test_chat_endpoint_never_500s_on_bad_bodies(client, flask_app, headers, body):
    route = _need(chat_route(flask_app), "chat")
    r = client.post(route, json=body, headers=headers)
    assert r.status_code < 500, f"FINDING: {r.status_code} on body {str(body)[:60]!r}: {r.get_data(as_text=True)[:200]}"


def test_malformed_json_gives_4xx_without_traceback(client, flask_app, headers):
    route = _need(chat_route(flask_app), "chat")
    r = client.post(route, data='{"message": "oops', content_type="application/json", headers=headers)
    assert 400 <= r.status_code < 500, f"got {r.status_code}"
    assert "Traceback" not in r.get_data(as_text=True)


def test_wrong_content_type_is_handled(client, flask_app, headers):
    route = _need(chat_route(flask_app), "chat")
    r = client.post(route, data="message=hello", content_type="application/x-www-form-urlencoded", headers=headers)
    assert r.status_code < 500


def test_wrong_http_method_is_405_not_500(client, flask_app):
    route = _need(chat_route(flask_app), "chat")
    for method in ("get", "put", "delete", "patch"):
        r = getattr(client, method)(route)
        assert r.status_code in (401, 403, 404, 405), f"{method.upper()} {route} -> {r.status_code}"


def test_oversized_payload_is_rejected_or_handled(client, flask_app, headers):
    route = _need(chat_route(flask_app), "chat")
    r = client.post(route, json={"message": "A" * 5_000_000}, headers=headers)
    assert r.status_code < 500, f"FINDING: {r.status_code} on a 5MB message (DoS risk)"


@pytest.mark.parametrize("text", [
    "میں آج بہت تھکا ہوا ہوں", "mujhe neend nahi aati", "🙂😢💔", "Ünïcödé tëxt ñ", "line1\nline2\r\nline3",
])
def test_unicode_and_multilingual_messages_roundtrip(client, flask_app, headers, text):
    r = chat(client, flask_app, text, headers)
    assert r.status_code < 500
    assert r.status_code == 200 or r.status_code in (401, 403)


def test_chat_route_does_not_leak_stack_traces(client, flask_app, headers):
    route = _need(chat_route(flask_app), "chat")
    for body in BAD_BODIES:
        r = client.post(route, json=body, headers=headers)
        t = r.get_data(as_text=True)
        assert "Traceback (most recent call last)" not in t
        assert not re.search(r'File "[^"]+\.py", line \d+', t), "file path leaked in error body"


# =========================================================================== #
# 3. AUTHENTICATION
# =========================================================================== #
def test_register_and_login_roundtrip(flask_app):
    _need(register_route(flask_app), "register")
    c = new_client(flask_app)
    name = "rt_" + uuid.uuid4().hex[:8]
    resp, payload, token = register(c, flask_app, name, STRONG_PW)
    assert resp is not None and resp.status_code in (200, 201), \
        f"registration failed: {getattr(resp, 'status_code', None)} {resp.get_data(as_text=True)[:200] if resp else ''}"
    r, tok = login(new_client(flask_app), flask_app, payload)
    assert r is not None and r.status_code == 200 and tok, "login did not return a JWT"
    assert tok.count(".") == 2


def test_duplicate_registration_is_rejected(flask_app):
    _need(register_route(flask_app), "register")
    name = "dup_" + uuid.uuid4().hex[:8]
    _, payload, _ = register(new_client(flask_app), flask_app, name, STRONG_PW)
    r = new_client(flask_app).post(register_route(flask_app), json=payload)
    assert r.status_code in (400, 409, 422), f"FINDING: duplicate registration returned {r.status_code}"


def test_wrong_password_is_rejected_without_token(flask_app, session_user):
    _need(login_route(flask_app), "login")
    bad = dict(session_user["payload"], password="Definitely-Wrong-Pw-1!")
    r, tok = login(new_client(flask_app), flask_app, bad)
    assert r.status_code in (400, 401, 403)
    assert not tok


def test_login_does_not_reveal_whether_user_exists(flask_app, session_user):
    """User enumeration check: unknown-user and wrong-password must look the same."""
    route = _need(login_route(flask_app), "login")
    known = {k: v for k, v in session_user["payload"].items() if k in ("username", "email")}
    r1 = new_client(flask_app).post(route, json={**known, "password": "wrong-Pw-123!"})
    ghost = {k: ("ghost" + uuid.uuid4().hex[:6] + ("@example.com" if k == "email" else "")) for k in known}
    r2 = new_client(flask_app).post(route, json={**ghost, "password": "wrong-Pw-123!"})
    assert r1.status_code == r2.status_code, f"enumeration leak: {r1.status_code} vs {r2.status_code}"


NOSQL_PAYLOADS = [
    {"username": {"$ne": ""}, "password": {"$ne": ""}},
    {"email": {"$gt": ""}, "password": {"$gt": ""}},
    {"username": {"$regex": ".*"}, "password": {"$regex": ".*"}},
    {"username": {"$where": "1==1"}, "password": "x"},
    {"email": {"$ne": None}, "password": {"$ne": None}},
]


@pytest.mark.parametrize("body", NOSQL_PAYLOADS, ids=[f"nosql{i}" for i in range(len(NOSQL_PAYLOADS))])
def test_nosql_injection_cannot_bypass_login(flask_app, session_user, body):
    route = _need(login_route(flask_app), "login")
    r = new_client(flask_app).post(route, json=body)
    assert r.status_code < 500, f"FINDING: injection payload crashed login ({r.status_code})"
    assert not find_token(r.get_json(silent=True)), f"FINDING (critical): NoSQL injection logged in with {body}"


@pytest.mark.parametrize("body", NOSQL_PAYLOADS, ids=[f"nosql_reg{i}" for i in range(len(NOSQL_PAYLOADS))])
def test_nosql_operators_rejected_in_registration(flask_app, body):
    route = _need(register_route(flask_app), "register")
    r = new_client(flask_app).post(route, json=body)
    assert r.status_code < 500 and r.status_code not in (200, 201), \
        f"FINDING: operator payload accepted by register: {r.status_code}"


def test_password_is_never_stored_in_plaintext(flask_app):
    _need(register_route(flask_app), "register")
    pw = "Plain-Check-" + uuid.uuid4().hex + "!A1"
    name = "pw_" + uuid.uuid4().hex[:8]
    resp, payload, _ = register(new_client(flask_app), flask_app, name, pw)
    assert resp is not None and resp.status_code in (200, 201)
    docs = dump_all_documents()
    blob = json.dumps(docs, default=str)
    assert pw not in blob, "FINDING (critical): plaintext password stored in the database"
    assert re.search(r"\$2[aby]\$\d{2}\$", blob), "no bcrypt hash found in DB (README claims bcrypt)"


def test_registration_and_login_responses_do_not_leak_hash(flask_app):
    _need(register_route(flask_app), "register")
    name = "lk_" + uuid.uuid4().hex[:8]
    resp, payload, _ = register(new_client(flask_app), flask_app, name, STRONG_PW)
    r, _ = login(new_client(flask_app), flask_app, payload)
    for x in (resp, r):
        t = x.get_data(as_text=True)
        assert not re.search(r"\$2[aby]\$", t), "password hash leaked in API response"
        assert "password" not in {k.lower() for k in (x.get_json(silent=True) or {}).keys()}


@pytest.mark.parametrize("pw", ["", "123", "password", "a", "        "])
def test_weak_passwords_are_rejected(flask_app, pw):
    """POLICY: remove this test if you intentionally allow weak passwords."""
    route = _need(register_route(flask_app), "register")
    name = "weak_" + uuid.uuid4().hex[:8]
    ok = False
    for p in ({"username": name, "email": f"{name}@example.com", "password": pw},
              {"email": f"{name}@example.com", "password": pw}):
        r = new_client(flask_app).post(route, json=p)
        ok = ok or r.status_code in (200, 201)
    assert not ok, f"FINDING: weak password {pw!r} accepted"


# =========================================================================== #
# 4. JWT HANDLING
# =========================================================================== #
def _protected(flask_app, headers_):
    """Find a route that rejects anonymous requests and accepts our valid token."""
    c = new_client(flask_app)
    route = chat_route(flask_app)
    anon = chat(c, flask_app, "hello", {})
    authed = chat(new_client(flask_app), flask_app, "hello", headers_)
    if anon.status_code in (401, 403) and authed.status_code == 200:
        return True
    return False


def test_chat_requires_authentication_or_is_intentionally_public(flask_app, headers):
    anon = chat(new_client(flask_app), flask_app, "hello", {})
    if anon.status_code == 200:
        pytest.skip("chat endpoint is public (anonymous allowed): auth tests below are skipped")
    assert anon.status_code in (401, 403, 422)


def test_tampered_jwt_is_rejected(flask_app, session_user):
    tok = session_user["token"]
    if not tok:
        pytest.skip("no token obtained")
    if not _protected(flask_app, auth_headers(tok)):
        pytest.skip("chat is not an auth-protected route")
    head, body, sig = tok.split(".")
    flipped = sig[:-2] + ("AA" if not sig.endswith("AA") else "BB")
    r = chat(new_client(flask_app), flask_app, "hi", auth_headers(f"{head}.{body}.{flipped}"))
    assert r.status_code in (401, 403, 422), f"FINDING (critical): tampered JWT accepted ({r.status_code})"


def test_alg_none_jwt_is_rejected(flask_app, session_user):
    tok = session_user["token"]
    if not tok or not _protected(flask_app, auth_headers(tok)):
        pytest.skip("needs an auth-protected chat route + token")
    claims = json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "=="))
    forged = f"{_b64({'alg': 'none', 'typ': 'JWT'})}.{_b64(claims)}."
    r = chat(new_client(flask_app), flask_app, "hi", auth_headers(forged))
    assert r.status_code in (401, 403, 422), f"FINDING (critical): alg=none JWT accepted ({r.status_code})"


def test_expired_jwt_is_rejected(flask_app, session_user):
    jwt = pytest.importorskip("jwt")
    tok = session_user["token"]
    if not tok or not _protected(flask_app, auth_headers(tok)):
        pytest.skip("needs an auth-protected chat route + token")
    secret = None
    cands = {FAKE_JWT_SECRET, *[v for k, v in flask_app.config.items()
                                if isinstance(v, str) and re.search(r"SECRET|JWT", k, re.I)]}
    for cand in cands:
        for alg in ("HS256", "HS384", "HS512"):
            try:
                jwt.decode(tok, cand, algorithms=[alg], options={"verify_exp": False})
                secret, used_alg = cand, alg
                break
            except Exception:  # noqa: BLE001
                continue
        if secret:
            break
    if not secret:
        pytest.skip("could not determine the JWT secret/algorithm used by the app")
    claims = jwt.decode(tok, secret, algorithms=[used_alg], options={"verify_exp": False})
    claims["exp"] = 1_000_000_000  # year 2001
    expired = jwt.encode(claims, secret, algorithm=used_alg)
    r = chat(new_client(flask_app), flask_app, "hi", auth_headers(expired))
    assert r.status_code in (401, 403, 422), f"FINDING (critical): expired JWT accepted ({r.status_code})"


@pytest.mark.parametrize("hdr", [
    {"Authorization": "Bearer"}, {"Authorization": "Bearer "}, {"Authorization": "Bearer null"},
    {"Authorization": "Bearer undefined"}, {"Authorization": "Bearer a.b.c"},
    {"Authorization": "Basic Zm9vOmJhcg=="}, {"Authorization": "x" * 10_000},
    {"Authorization": "Bearer " + "A" * 10_000}, {"Authorization": "bearer\x00token"},
])
def test_garbage_authorization_headers_never_500(client, flask_app, hdr):
    try:
        r = chat(client, flask_app, "hello", hdr)
    except Exception as e:  # noqa: BLE001
        pytest.fail(f"request with bad header crashed the test client: {e!r}")
    assert r.status_code < 500, f"FINDING: {r.status_code} for header {str(hdr)[:60]}"
    assert not (r.status_code == 200 and reply_text(r) == "" and hdr), "garbage token produced empty 200"


# =========================================================================== #
# 5. ROUTE-LEVEL AUTH AUDIT
# =========================================================================== #
_PUBLIC = re.compile(r"login|signin|register|signup|health|ping|status|^/$|resource|helpline|docs|"
                     r"openapi|swagger|favicon|metrics|crisis-?resources|version", re.I)


def test_every_non_public_route_rejects_anonymous_requests(flask_app, session_user):
    if not _protected(flask_app, auth_headers(session_user["token"])):
        pytest.skip("chat is not auth-protected; skipping auth audit (set up per your design)")
    open_routes = []
    for rule, methods in routes(flask_app):
        if _PUBLIC.search(rule):
            continue
        path = re.sub(r"<[^>]+>", "1", rule)
        for m in methods:
            r = getattr(new_client(flask_app), m.lower())(path, json={} if m != "GET" else None)
            if r.status_code < 400 or r.status_code >= 500:
                open_routes.append(f"{m} {rule} -> {r.status_code}")
    assert not open_routes, "FINDING: routes reachable WITHOUT a token:\n  " + "\n  ".join(open_routes)


# =========================================================================== #
# 6. DATA ISOLATION (IDOR) + PERSISTENCE
# =========================================================================== #
def test_users_cannot_read_each_others_chat_history(flask_app):
    hist = _need(history_route(flask_app), "history (GET)")
    _need(register_route(flask_app), "register")
    pwd = STRONG_PW
    a_name, b_name = "ia_" + uuid.uuid4().hex[:6], "ib_" + uuid.uuid4().hex[:6]
    _, pa, ta = register(new_client(flask_app), flask_app, a_name, pwd)
    _, pb, tb = register(new_client(flask_app), flask_app, b_name, pwd)
    ta = ta or login(new_client(flask_app), flask_app, pa)[1]
    tb = tb or login(new_client(flask_app), flask_app, pb)[1]
    if not (ta and tb):
        pytest.skip("could not authenticate two users")
    marker = "PRIVATE-MARKER-" + uuid.uuid4().hex
    chat(new_client(flask_app), flask_app, f"my secret note {marker}", auth_headers(ta))
    r = new_client(flask_app).get(hist, headers=auth_headers(tb))
    assert marker not in r.get_data(as_text=True), "FINDING (critical): user B can read user A's messages"


def test_history_requires_authentication(flask_app):
    hist = _need(history_route(flask_app), "history (GET)")
    r = new_client(flask_app).get(hist)
    assert r.status_code in (401, 403, 422), f"FINDING: history reachable anonymously ({r.status_code})"


# =========================================================================== #
# 7. RATE LIMITING (README: 60 requests/minute per IP)
# =========================================================================== #
def test_rate_limit_kicks_in_around_60_per_minute(flask_app):
    route = login_route(flask_app) or chat_route(flask_app)
    _need(route, "login/chat")
    c = new_client(flask_app)  # dedicated fresh IP
    codes = [c.post(route, json={"username": "x", "email": "x@example.com", "password": "x"}).status_code
             for _ in range(75)]
    first_429 = codes.index(429) + 1 if 429 in codes else None
    assert first_429 is not None, "FINDING: no 429 after 75 requests; rate limiting not enforced"
    assert 50 <= first_429 <= 66, f"limit triggered after {first_429} requests (README says 60/min)"


def test_rate_limit_is_per_ip_not_global(flask_app):
    route = login_route(flask_app) or chat_route(flask_app)
    _need(route, "login/chat")
    hog = new_client(flask_app)
    for _ in range(70):
        hog.post(route, json={"username": "x", "password": "x"})
    other = new_client(flask_app)
    r = other.post(route, json={"username": "x", "password": "x"})
    assert r.status_code != 429, "FINDING: one IP exhausting its quota blocks everyone (global limiter)"


def test_rate_limit_cannot_be_bypassed_with_spoofed_forwarded_for(flask_app):
    route = login_route(flask_app) or chat_route(flask_app)
    _need(route, "login/chat")
    c = new_client(flask_app)
    saw_429 = False
    for i in range(80):
        r = c.post(route, json={"username": "x", "password": "x"}, headers={"X-Forwarded-For": f"9.9.{i}.{i}"})
        saw_429 = saw_429 or r.status_code == 429
    assert saw_429, "FINDING: X-Forwarded-For spoofing bypasses the rate limiter"


# =========================================================================== #
# 8. CORS
# =========================================================================== #
def test_cors_allows_configured_frontend_origin(client, flask_app):
    route = _need(chat_route(flask_app), "chat")
    r = client.options(route, headers={"Origin": ALLOWED_ORIGIN, "Access-Control-Request-Method": "POST",
                                       "Access-Control-Request-Headers": "content-type,authorization"})
    allow = r.headers.get("Access-Control-Allow-Origin")
    assert allow in (ALLOWED_ORIGIN, "*"), f"frontend origin not allowed (got {allow!r})"


@pytest.mark.parametrize("origin", ["http://evil.example", "https://attacker.com", "null", "http://localhost:5173.evil.com"])
def test_cors_blocks_foreign_origins(client, flask_app, origin):
    route = _need(chat_route(flask_app), "chat")
    r = client.options(route, headers={"Origin": origin, "Access-Control-Request-Method": "POST"})
    allow = r.headers.get("Access-Control-Allow-Origin")
    assert allow not in (origin, "*"), f"FINDING: CORS allows {origin!r} (header={allow!r})"


def test_cors_does_not_allow_credentials_with_wildcard(client, flask_app):
    route = _need(chat_route(flask_app), "chat")
    r = client.options(route, headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert not (r.headers.get("Access-Control-Allow-Origin") == "*" and
                r.headers.get("Access-Control-Allow-Credentials") == "true")


# =========================================================================== #
# 9. LOG REDACTION (README: logger redacts user text, API keys, prompts)
# =========================================================================== #
def test_logs_never_contain_user_text_or_secrets(flask_app, headers, caplog, capfd):
    marker = "ZXQ-USER-TEXT-" + uuid.uuid4().hex
    caplog.set_level(logging.DEBUG)
    c = new_client(flask_app)
    chat(c, flask_app, f"I feel anxious {marker}", headers)
    chat(c, flask_app, f"I want to end my life {marker}", headers)
    out, err = capfd.readouterr()
    haystack = caplog.text + out + err
    assert marker not in haystack, "FINDING: raw user text found in logs/stdout/stderr"
    assert FAKE_GEMINI_KEY not in haystack, "FINDING: API key found in logs"
    assert FAKE_JWT_SECRET not in haystack, "FINDING: JWT secret found in logs"


def test_passwords_never_appear_in_logs(flask_app, caplog, capfd):
    _need(register_route(flask_app), "register")
    caplog.set_level(logging.DEBUG)
    pw = "LogCheck-" + uuid.uuid4().hex + "!9"
    register(new_client(flask_app), flask_app, "lg_" + uuid.uuid4().hex[:6], pw)
    out, err = capfd.readouterr()
    assert pw not in caplog.text + out + err, "FINDING: plaintext password logged"


# =========================================================================== #
# 10. DATABASE
# =========================================================================== #
def test_chat_messages_are_persisted_when_history_exists(flask_app, headers):
    hist = history_route(flask_app)
    if not hist:
        pytest.skip("no history route discovered")
    marker = "PERSIST-" + uuid.uuid4().hex
    chat(new_client(flask_app), flask_app, f"remember {marker}", headers)
    r = new_client(flask_app).get(hist, headers=headers)
    assert r.status_code == 200
    assert marker in r.get_data(as_text=True), "message not persisted / not returned by history"


def test_stored_documents_contain_no_api_keys_or_jwts(flask_app, headers):
    chat(new_client(flask_app), flask_app, "hello there", headers)
    blob = json.dumps(dump_all_documents(), default=str)
    assert FAKE_GEMINI_KEY not in blob
    assert not re.search(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.", blob), "a JWT is stored in the database"


def test_database_indexes_exist_for_users(flask_app):
    """README mentions compound indexes: at least a users collection should have a unique index."""
    from mg_support import TrackingClient
    found = []
    for cl in TrackingClient.instances:
        for dbn in cl.list_database_names():
            for coll in cl[dbn].list_collection_names():
                for name, info in cl[dbn][coll].index_information().items():
                    if name != "_id_":
                        found.append((coll, name, info.get("unique", False)))
    assert found, "FINDING: no secondary indexes at all (README promises compound indexes)"


# =========================================================================== #
# 11. CONCURRENCY
# =========================================================================== #
def test_concurrent_chat_requests_are_safe(flask_app, headers):
    results, errors = [], []

    def worker(i):
        try:
            c = new_client(flask_app)
            text = "I want to end my life" if i % 3 == 0 else f"hello {i}, I feel a bit stressed"
            r = chat(c, flask_app, text, headers)
            results.append((i, r.status_code))
        except Exception as e:  # noqa: BLE001
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(24)]
    [t.start() for t in threads]
    [t.join(timeout=60) for t in threads]
    assert not errors, errors
    assert len(results) == 24
    assert all(code < 500 for _, code in results), f"500s under concurrency: {[r for r in results if r[1] >= 500]}"


def test_concurrent_duplicate_registration_creates_one_user(flask_app):
    route = _need(register_route(flask_app), "register")
    name = "race_" + uuid.uuid4().hex[:8]
    _, payload, _ = register(new_client(flask_app), flask_app, "tmp_" + uuid.uuid4().hex[:6], STRONG_PW)
    body = {k: (name if k == "username" else f"{name}@example.com" if k == "email" else v) for k, v in payload.items()}
    codes = []

    def go():
        codes.append(new_client(flask_app).post(route, json=body).status_code)

    ts = [threading.Thread(target=go) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert sum(c in (200, 201) for c in codes) <= 1, f"FINDING (race): duplicate users created: {codes}"


# =========================================================================== #
# 12. REPO + CONFIG HYGIENE (secret scanning, docker, env)
# =========================================================================== #
_SKIP_DIRS = {".git", "node_modules", "venv", ".venv", ".venv_clean", "__pycache__", "dist", "build", "artifacts", ".pytest_cache"}
_SECRET_PATTERNS = {
    "Google API key": re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
    "Private key block": re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9]{32,}\b"),
    "Mongo URI with password": re.compile(r"mongodb(\+srv)?://[^/\s:@]+:[^@\s]{3,}@"),
    "Hard-coded JWT": re.compile(r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"),
}


def _repo_text_files():
    for p in ROOT.rglob("*"):
        if p.is_file() and not (set(p.relative_to(ROOT).parts) & _SKIP_DIRS) \
                and p.suffix.lower() in {".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yml", ".yaml", ".md",
                                         ".env", ".ini", ".cfg", ".toml", ".txt", ".html", ".sh"} \
                and p.stat().st_size < 2_000_000 and "tests/deep" not in p.as_posix():
            yield p


def test_no_secrets_committed_in_source():
    hits = []
    for p in _repo_text_files():
        if p.name == ".env.example":
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for label, rx in _SECRET_PATTERNS.items():
            if rx.search(txt):
                hits.append(f"{label} in {p.relative_to(ROOT)}")
    assert not hits, "FINDING: possible secrets committed:\n  " + "\n  ".join(hits)


def test_dotenv_is_gitignored_and_template_exists():
    gi = (ROOT / ".gitignore")
    assert gi.exists(), ".gitignore missing"
    lines = [l.strip() for l in gi.read_text(errors="ignore").splitlines()]
    assert any(l in (".env", "*.env", ".env*", "**/.env") for l in lines), ".env is not git-ignored"
    assert (ROOT / ".env").exists() is False or ".env" in "".join(lines)
    if not (ROOT / ".env.example").exists():
        pytest.fail("README tells users to `cp .env.example .env` but .env.example is missing from the repo")


def test_env_example_lists_required_variables():
    ex = ROOT / ".env.example"
    if not ex.exists():
        pytest.skip(".env.example missing (reported by the test above)")
    txt = ex.read_text(errors="ignore")
    for must in ("GEMINI", "MONGO", "JWT|SECRET"):
        assert re.search(must, txt, re.I), f".env.example does not mention {must}"
    for line in txt.splitlines():
        if "=" in line and not line.strip().startswith("#"):
            v = line.split("=", 1)[1].strip().strip('"\'')
            assert not re.search(r"AIza|sk-[A-Za-z0-9]{20}", v), "real-looking key in .env.example"


def test_dockerfiles_do_not_run_as_root_or_bake_secrets():
    problems = []
    for df in list(ROOT.rglob("Dockerfile")) + [ROOT / "docker-compose.yml"]:
        if not df.exists() or set(df.relative_to(ROOT).parts) & _SKIP_DIRS:
            continue
        txt = df.read_text(errors="ignore")
        if df.name == "Dockerfile":
            if "nginx" not in txt.lower() and not re.search(r"^\s*USER\s+(?!root)", txt, re.M):
                problems.append(f"{df.relative_to(ROOT)}: no non-root USER (container runs as root)")
            if re.search(r"^\s*(ENV|ARG)\s+\w*(KEY|SECRET|PASSWORD|TOKEN)\w*\s*=\s*\S+", txt, re.M | re.I):
                problems.append(f"{df.relative_to(ROOT)}: secret baked into image via ENV/ARG")
        else:
            if re.search(r"(KEY|SECRET|PASSWORD|TOKEN)\w*\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{12,}", txt) and "${" not in txt:
                problems.append("docker-compose.yml: hard-coded secret value")
    assert not problems, "FINDING:\n  " + "\n  ".join(problems)


def test_config_fails_loudly_or_defaults_safely_without_secrets(monkeypatch):
    """Config must not silently run with a guessable JWT secret."""
    import mg_adapter
    cfg = None
    for name in ("server.config", "config"):
        try:
            cfg = __import__(name, fromlist=["*"])
            break
        except Exception:  # noqa: BLE001
            continue
    if cfg is None:
        pytest.skip("config module not importable")
    src = Path(cfg.__file__).read_text(errors="ignore")
    bad = re.findall(r"(?i)(?:jwt|secret)[_a-z]*\s*=\s*os\.(?:environ\.get|getenv)\([^,)]+,\s*['\"]([^'\"]{1,40})['\"]\)", src)
    weak = [b for b in bad if b.lower() in ("secret", "changeme", "dev", "development", "your-secret-key",
                                            "supersecret", "default", "test", "mindguard", "jwt-secret")]
    assert not weak, f"FINDING: config falls back to a guessable secret: {weak}"
