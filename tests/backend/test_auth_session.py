"""
test_auth_session.py
====================
Regression tests for the session-authentication rework (remediation plan 1.1/1.2):

- "Keep me signed in" issues an httpOnly rotating refresh cookie
- Rotation invalidates the old token and keeps the family consistent
- Reuse of a rotated token is treated as theft: family revoked + token_version bump
- Logout revokes everything server-side (access tokens die via version bump)
- JWTs carry a `ver` claim bound to the user's token_version
- Anonymous guests get a continuity cookie that resumes active-risk sessions
"""

import os
import unittest

os.environ.setdefault("USE_MONGOMOCK", "true")
os.environ.setdefault("FLASK_ENV", "testing")

from database import (  # noqa: E402
    bump_token_version,
    create_user,
    get_db,
    get_user_by_email,
    get_user_token_version,
    issue_refresh_token,
    rotate_refresh_token,
)
from auth import generate_token  # noqa: E402
from app import app, reset_rate_limits  # noqa: E402


def _extract_cookie(res, name):
    """Pulls the raw cookie value out of a Set-Cookie header."""
    for header in res.headers.getlist("Set-Cookie"):
        if header.startswith(name + "="):
            return header.split(name + "=", 1)[1].split(";", 1)[0]
    return None


class AuthSessionTestCase(unittest.TestCase):

    def setUp(self):
        reset_rate_limits()
        init = get_db()
        for name in ("users", "refresh_tokens", "audit_logs", "chat_sessions"):
            init[name].delete_many({})
        self.client = app.test_client()
        self.email = "session-test@example.com"
        self.password = "ValidPass!123"

    def _register(self, remember=True):
        res = self.client.post("/api/auth/register", json={
            "name": "Session Test",
            "email": self.email,
            "password": self.password,
            "consent_given": True,
            "remember_me": remember,
        })
        self.assertEqual(res.status_code, 201)
        return res

    def _login(self, remember=True):
        res = self.client.post("/api/auth/login", json={
            "email": self.email,
            "password": self.password,
            "remember_me": remember,
        })
        self.assertEqual(res.status_code, 200)
        return res

    # ---------------------------------------------------------------- cookies

    def test_login_without_remember_sets_no_refresh_cookie(self):
        self._register(remember=False)
        res = self._login(remember=False)
        self.assertIsNone(_extract_cookie(res, "mg_refresh"))

    def test_login_with_remember_sets_httponly_refresh_cookie(self):
        self._register(remember=False)
        res = self._login(remember=True)
        cookie = _extract_cookie(res, "mg_refresh")
        self.assertIsNotNone(cookie)
        self.assertTrue(cookie.startswith("rt-"))
        set_cookie_header = next(
            h for h in res.headers.getlist("Set-Cookie") if h.startswith("mg_refresh=")
        )
        self.assertIn("HttpOnly", set_cookie_header)
        self.assertIn("Path=/api/auth", set_cookie_header)

    # --------------------------------------------------------------- rotation

    def test_refresh_rotates_and_keeps_family(self):
        self._register(remember=True)
        first = self.client.post("/api/auth/refresh")
        self.assertEqual(first.status_code, 200)
        first_data = first.get_json()["data"]
        self.assertIn("token", first_data)
        self.assertEqual(first_data["user"]["email"], self.email)

        db = get_db()
        user = get_user_by_email(self.email)
        docs = list(db.refresh_tokens.find({"user_id": user["id"]}))
        self.assertEqual(len(docs), 2, "rotation should leave old + new token rows")
        self.assertEqual(len({d["family_id"] for d in docs}), 1, "same family")
        self.assertEqual(
            sum(1 for d in docs if d.get("revoked")), 1, "exactly the old one revoked"
        )

    def test_refresh_without_cookie_rejected_401(self):
        fresh = app.test_client()
        res = fresh.post("/api/auth/refresh")
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.get_json()["error"]["code"], "NO_REFRESH_TOKEN")

    def test_reuse_of_rotated_token_is_treated_as_theft(self):
        self._register(remember=True)

        # Capture the current cookie value directly.
        refresh_res = self.client.post("/api/auth/refresh")
        self.assertEqual(refresh_res.status_code, 200)
        current = None
        for h in refresh_res.headers.getlist("Set-Cookie"):
            if h.startswith("mg_refresh="):
                current = h.split("mg_refresh=", 1)[1].split(";", 1)[0]
        self.assertIsNotNone(current)

        user = get_user_by_email(self.email)
        self.assertEqual(get_user_token_version(user["id"]), 0)

        # First rotation succeeds (this token is now spent).
        rotated = rotate_refresh_token(current)
        self.assertIsNotNone(rotated)

        # Replaying the same, now-rotated token is treated as theft.
        result = rotate_refresh_token(current)
        self.assertIsNone(result, "rotated tokens must not validate")

        # Theft response: whole family revoked, token_version bumped.
        family = get_db().refresh_tokens.find_one({"user_id": user["id"]})["family_id"]
        docs = list(get_db().refresh_tokens.find({"family_id": family}))
        self.assertTrue(docs and all(d.get("revoked") for d in docs))
        self.assertEqual(get_user_token_version(user["id"]), 1)

        # An access token minted before the bump no longer authenticates.
        stale_token = generate_token(user["id"], user["email"], token_version=0)
        me = self.client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {stale_token}"}
        )
        self.assertEqual(me.status_code, 401)
        self.assertEqual(me.get_json()["error"]["code"], "TOKEN_REVOKED")

    # ----------------------------------------------------------------- logout

    def test_logout_revokes_everything_server_side(self):
        self._register(remember=True)
        login_res = self._login(remember=True)
        access_token = login_res.get_json()["data"]["token"]

        logout_res = self.client.post(
            "/api/auth/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        self.assertEqual(logout_res.status_code, 200)
        set_cookies = " | ".join(logout_res.headers.getlist("Set-Cookie"))
        self.assertIn("mg_refresh=;", set_cookies)

        user = get_user_by_email(self.email)
        self.assertGreaterEqual(get_user_token_version(user["id"]), 1)

        me = self.client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
        )
        self.assertEqual(me.status_code, 401)
        self.assertEqual(me.get_json()["error"]["code"], "TOKEN_REVOKED")

        # Refreshing is dead: the jar's cookie was cleared on logout, and every
        # server-side row for the user is revoked.
        refresh = self.client.post("/api/auth/refresh")
        self.assertEqual(refresh.status_code, 401)

        user = get_user_by_email(self.email)
        docs = list(get_db().refresh_tokens.find({"user_id": user["id"]}))
        self.assertTrue(docs and all(d.get("revoked") for d in docs))
        self.assertGreaterEqual(get_user_token_version(user["id"]), 1)

    def test_version_bound_token_rejected_after_bump(self):
        created = create_user(
            name="Version Test",
            email="version-test@example.com",
            password_hash="x",
            consent_given=True,
        )
        uid = created["id"]
        stale = generate_token(uid, created["email"])
        self.assertEqual(bump_token_version(uid), 1)

        me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {stale}"})
        self.assertEqual(me.status_code, 401)

        fresh = generate_token(uid, created["email"], token_version=1)
        me2 = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {fresh}"})
        self.assertEqual(me2.status_code, 200)

    # ------------------------------------------------------- guest continuity

    def test_guest_cookie_continuity_and_isolation(self):
        guest_a = app.test_client()
        r1 = guest_a.post("/api/chat", json={"message": "I want to kill myself"})
        self.assertEqual(r1.status_code, 200)
        self.assertEqual(r1.get_json()["data"]["risk_level"], "HIGH_CRISIS")
        session_id = r1.get_json()["data"]["session_id"]
        self.assertIsNotNone(session_id)
        self.assertIsNotNone(_extract_cookie(r1, "mg_guest"))

        doc = get_db().chat_sessions.find_one({"id": session_id})
        self.assertIsNotNone(doc.get("guest_ref"), "guest session stamped with its ref")

        # Same guest, lost session id (simulated reload): continuity resumes the
        # still-active crisis session and returns the guarded follow-up.
        r2 = guest_a.post("/api/chat", json={"message": "tell me a joke instead"})
        self.assertEqual(r2.status_code, 200)
        data2 = r2.get_json()["data"]
        self.assertEqual(data2["session_id"], session_id)
        self.assertEqual(data2["risk_level"], "ELEVATED_DISTRESS")

        # A different anonymous visitor never resumes someone else's session.
        guest_b = app.test_client()
        r3 = guest_b.post("/api/chat", json={"message": "hello there, bad day at work"})
        self.assertEqual(r3.status_code, 200)
        other_session = r3.get_json()["data"].get("session_id")
        self.assertIsNotNone(other_session)
        self.assertNotEqual(other_session, session_id)


if __name__ == "__main__":
    unittest.main()
