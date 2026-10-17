"""Shared helpers + one-time environment setup (kept OUT of conftest.py so tests can import it
without clashing with the repo's own root conftest.py)."""
from __future__ import annotations

import itertools
import os
import socket

# ---------------------------------------------------------------- environment
FAKE_GEMINI_KEY = "test-gemini-key-NOT-REAL-9f8e7d6c"
FAKE_JWT_SECRET = "test-jwt-secret-for-deep-suite-0123456789abcdef"
_ENV = {
    "GEMINI_API_KEY": FAKE_GEMINI_KEY,
    "GOOGLE_API_KEY": FAKE_GEMINI_KEY,
    "JWT_SECRET_KEY": FAKE_JWT_SECRET,
    "JWT_SECRET": FAKE_JWT_SECRET,
    "SECRET_KEY": FAKE_JWT_SECRET,
    "MONGO_URI": "mongodb://localhost:27017/mindguard_test",
    "MONGODB_URI": "mongodb://localhost:27017/mindguard_test",
    "MONGO_DB_NAME": "mindguard_test",
    "MONGO_DB": "mindguard_test",
    "DATABASE_NAME": "mindguard_test",
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "TOKENIZERS_PARALLELISM": "false",
}
os.environ.update(_ENV)

# ---------------------------------------------------------------- mongomock
import mongomock  # noqa: E402
import pymongo  # noqa: E402


class TrackingClient(mongomock.MongoClient):
    instances: list = []

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        TrackingClient.instances.append(self)


pymongo.MongoClient = TrackingClient
mongomock.MongoClient = TrackingClient
try:
    import pymongo.mongo_client as _mc
    _mc.MongoClient = TrackingClient
except Exception:  # noqa: BLE001
    pass


def dump_all_documents() -> list[dict]:
    docs = []
    for c in TrackingClient.instances:
        for dbname in c.list_database_names():
            db = c[dbname]
            for coll in db.list_collection_names():
                for d in db[coll].find({}):
                    docs.append({"_db": dbname, "_collection": coll, **d})
    return docs



# ---------------------------------------------------------------- client helpers
_ip_counter = itertools.count(1)


def _next_ip() -> str:
    n = next(_ip_counter)
    return f"10.{(n >> 16) & 255}.{(n >> 8) & 255}.{n & 255}"


def new_client(app):
    c = app.test_client()
    c.environ_base["REMOTE_ADDR"] = _next_ip()
    return c


STRONG_PW = "Zq!9-Deep-Suite-Pw-7788"
