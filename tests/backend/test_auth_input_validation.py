"""Regression tests for malformed JSON fields on public auth endpoints."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from server.app import app
except ImportError:
    from app import app


def test_login_rejects_nosql_object_fields_with_400():
    client = app.test_client()
    response = client.post(
        "/api/auth/login",
        json={"email": {"$ne": None}, "password": {"$ne": None}},
    )

    body = response.get_json()
    assert response.status_code == 400
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_FIELD"


def test_register_rejects_non_string_identity_fields_with_400():
    client = app.test_client()
    response = client.post(
        "/api/auth/register",
        json={"name": ["user"], "email": {"$ne": None}, "password": "safe-password"},
    )

    body = response.get_json()
    assert response.status_code == 400
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_FIELD"
