"""Fixtures for the MindGuard deep suite (see mg_support.py for env + DB patching)."""
from __future__ import annotations

import functools
import inspect
import re
import socket
import sys
import uuid

import pytest

import mg_support  # noqa: F401  (must be imported first: sets env + patches pymongo)
from mg_support import STRONG_PW, new_client
from mg_adapter import auth_headers, get_app, login, modules_named, register

# ---------------------------------------------------------------- network guard
_LOOPBACK = {"127.0.0.1", "localhost", "::1", "0.0.0.0", ""}


class NetLog:
    def __init__(self):
        self.external: list[str] = []


def _is_loopback(host) -> bool:
    if isinstance(host, bytes):
        host = host.decode(errors="ignore")
    return (not isinstance(host, str)) or host in _LOOPBACK or host.startswith("127.")


@pytest.fixture(autouse=True)
def net_log(monkeypatch):
    log = NetLog()
    real_connect = socket.socket.connect
    real_gai = socket.getaddrinfo

    def guarded_connect(self, address, *a, **k):
        host = address[0] if isinstance(address, tuple) else address
        if not _is_loopback(host):
            log.external.append(str(host))
            raise ConnectionRefusedError(f"[deep-suite] outbound connection blocked: {host}")
        return real_connect(self, address, *a, **k)

    def guarded_gai(host, *a, **k):
        if not _is_loopback(host):
            log.external.append(str(host))
            raise socket.gaierror(f"[deep-suite] DNS blocked: {host}")
        return real_gai(host, *a, **k)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket, "getaddrinfo", guarded_gai)
    return log


# ---------------------------------------------------------------- app / clients
@pytest.fixture(scope="session")
def flask_app():
    app = get_app()
    # Make unhandled exceptions come back as 500 responses we can assert on,
    # instead of blowing up inside the test client.
    app.config["PROPAGATE_EXCEPTIONS"] = False
    app.testing = False
    return app


@pytest.fixture
def client(flask_app):
    c = flask_app.test_client()
    c.environ_base["REMOTE_ADDR"] = mg_support._next_ip()
    return c


@pytest.fixture(scope="session")
def session_user(flask_app):
    """One registered+logged-in user shared across the session."""
    c = new_client(flask_app)
    name = "deepuser_" + uuid.uuid4().hex[:8]
    resp, payload, token = register(c, flask_app, name, STRONG_PW)
    info = {"username": name, "password": STRONG_PW, "payload": payload,
            "token": token, "register_status": getattr(resp, "status_code", None)}
    if not token and payload:
        c2 = new_client(flask_app)
        _, token = login(c2, flask_app, payload)
        info["token"] = token
    return info


@pytest.fixture
def headers(session_user):
    return auth_headers(session_user["token"])


# ---------------------------------------------------------------- downstream instrumentation
_LLM_RE = r"generat|respond|reply|chat|complete|gemini|llm|ask|get_response|answer"
_HF_RE = r"classif|predict|analy|detect|sentiment|intent|emotion|infer|score|pipeline"


def instrument(monkeypatch, module_suffix: str, name_regex: str, calls: list, fail: bool = False) -> list[str]:
    """Wrap matching public functions/methods of every copy of `module_suffix`.
    Every call is recorded in `calls`; with fail=True the call raises RuntimeError.
    Returns the names that were instrumented."""
    mods = modules_named(module_suffix)
    wrapped_names: list[str] = []

    def make(name, orig):
        @functools.wraps(orig)
        def wrapper(*a, **k):
            calls.append(name)
            if fail:
                raise RuntimeError(f"[deep-suite] injected failure in {name}")
            return orig(*a, **k)
        return wrapper

    for mod in mods:
        for n, f in list(vars(mod).items()):
            if n.startswith("_"):
                continue
            if inspect.isfunction(f) and f.__module__ == mod.__name__ and re.search(name_regex, n, re.I):
                w = make(n, f)
                wrapped_names.append(n)
                for m in list(sys.modules.values()):
                    try:
                        items = list(vars(m).items())
                    except TypeError:
                        continue
                    for attr, val in items:
                        if val is f:
                            monkeypatch.setattr(m, attr, w)
            elif inspect.isclass(f) and f.__module__ == mod.__name__:
                for mn, mf in list(vars(f).items()):
                    if mn.startswith("_") or not inspect.isfunction(mf):
                        continue
                    if re.search(name_regex, mn, re.I):
                        monkeypatch.setattr(f, mn, make(f"{n}.{mn}", mf))
                        wrapped_names.append(f"{n}.{mn}")
    return wrapped_names


class Downstream:
    def __init__(self, monkeypatch):
        self._mp = monkeypatch
        self.llm_calls: list[str] = []
        self.hf_calls: list[str] = []
        self.llm_names: list[str] = []
        self.hf_names: list[str] = []

    def watch_llm(self, fail=False):
        self.llm_names = instrument(self._mp, "llm_service", _LLM_RE, self.llm_calls, fail)
        return self

    def watch_hf(self, fail=False):
        self.hf_names = instrument(self._mp, "huggingface_service", _HF_RE, self.hf_calls, fail)
        return self


@pytest.fixture
def downstream(monkeypatch, flask_app):
    return Downstream(monkeypatch)
