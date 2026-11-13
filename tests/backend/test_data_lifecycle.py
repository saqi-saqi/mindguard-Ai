"""
test_data_lifecycle.py
======================
Regression tests for the session-ownership guard and the data-erasure /
retention work (remediation plan Phase 1.3 / 1.4).

Covers:
- set_session_risk_state / update_chat_session fail closed on foreign sessions
- the chat endpoint drops (does not act on) a session id owned by another account
- anonymous callers cannot clear an account-owned crisis session
- guest session upsert behaviour is preserved
- delete_user_data erases every user-linked collection and anonymizes safety logs
- safety/audit records carry bounded-retention timestamps and TTL indexes exist
"""

import os
import unittest
from datetime import datetime

os.environ.setdefault("USE_MONGOMOCK", "true")
os.environ.setdefault("FLASK_ENV", "testing")

from database import (  # noqa: E402
    assert_session_ownership,
    clear_session_crisis_state,
    create_chat_session,
    create_user,
    delete_user_data,
    get_db,
    get_session_risk_state,
    init_db,
    log_safety_event,
    save_audit_event,
    save_chat_message,
    save_mood_log,
    set_session_risk_state,
    update_chat_session,
    issue_refresh_token,
)
from auth import generate_token  # noqa: E402
from app import app  # noqa: E402


def _reset_collections():
    db = get_db()
    for name in (
        "users", "chat_messages", "mood_logs", "chat_sessions",
        "audit_logs", "safety_logs", "user_profiles",
    ):
        db[name].delete_many({})
    init_db()


class TestSessionOwnership(unittest.TestCase):
    """A client-supplied session_id is not a credential."""

    def setUp(self):
        _reset_collections()
        db = get_db()
        for uid in ("owner-a", "attacker-b"):
            db.users.insert_one({
                "id": uid, "email": f"{uid}@example.com", "role": "user", "name": uid,
            })
        self.session = create_chat_session("owner-a", "Owner Session")
        self.session_id = self.session["id"]

    def test_ownership_helper_accepts_owner_and_missing_docs(self):
        self.assertEqual(assert_session_ownership(self.session_id, "owner-a"), "owner-a")
        # Unknown session documents are allowed: the caller may be creating one.
        self.assertIsNone(assert_session_ownership("ses-does-not-exist", "owner-a"))

    def test_risk_state_write_rejects_foreign_session(self):
        set_session_risk_state(self.session_id, "owner-a", "crisis_active", "HIGH_CRISIS")
        with self.assertRaises(PermissionError):
            set_session_risk_state(self.session_id, "attacker-b", "elevated_monitoring")
        # Victim state and ownership are untouched.
        state = get_session_risk_state(self.session_id)
        self.assertEqual(state["risk_state"], "crisis_active")
        doc = get_db().chat_sessions.find_one({"id": self.session_id})
        self.assertEqual(doc.get("user_id"), "owner-a")

    def test_update_chat_session_rejects_foreign_session(self):
        with self.assertRaises(PermissionError):
            update_chat_session(self.session_id, "attacker-b", {"title": "hijacked"})
        doc = get_db().chat_sessions.find_one({"id": self.session_id})
        self.assertNotEqual(doc.get("title"), "hijacked")

    def test_anonymous_caller_cannot_clear_account_owned_session(self):
        set_session_risk_state(self.session_id, "owner-a", "crisis_active", "HIGH_CRISIS")
        with self.assertRaises(PermissionError):
            clear_session_crisis_state(self.session_id, None)

    def test_guest_session_upsert_still_works(self):
        # Guests have no account; their sessions are keyed by the opaque session id.
        set_session_risk_state("ses-guest-1", None, "crisis_active", "HIGH_CRISIS")
        state = get_session_risk_state("ses-guest-1")
        self.assertEqual(state["risk_state"], "crisis_active")
        doc = get_db().chat_sessions.find_one({"id": "ses-guest-1"})
        self.assertIsNone(doc.get("user_id"))
        # A second guest write on the same session is still permitted.
        set_session_risk_state("ses-guest-1", None, "elevated_monitoring")
        self.assertEqual(
            get_session_risk_state("ses-guest-1")["risk_state"], "elevated_monitoring"
        )

    def test_chat_endpoint_drops_foreign_session_id(self):
        """The chat route must never steer another account's session state."""
        set_session_risk_state(self.session_id, "owner-a", "normal")

        attacker_token = generate_token("attacker-b", "attacker-b@example.com")
        client = app.test_client()
        resp = client.post(
            "/api/chat",
            json={"message": "I want to kill myself", "session_id": self.session_id},
            headers={"Authorization": f"Bearer {attacker_token}"},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data["data"]["risk_level"], "HIGH_CRISIS")
        self.assertTrue(data["requires_immediate_action"])

        # The victim's session was not touched by the attacker's crisis message.
        state = get_session_risk_state(self.session_id)
        self.assertEqual(state["risk_state"], "normal")
        self.assertEqual(state.get("crisis_count", 0), 0)

        # The request was audited as an ownership rejection.
        db = get_db()
        rejected = db.audit_logs.find_one({"event_type": "session_ownership_rejected"})
        self.assertIsNotNone(rejected)


class TestDataErasure(unittest.TestCase):
    """Erasure leaves no record that points back to the person."""

    def setUp(self):
        _reset_collections()
        created = create_user(name="Erasure Test", email="erasure@example.com",
                              password_hash="x", consent_given=True)
        self.user_id = created["id"]
        issue_refresh_token(self.user_id)

        self.session = create_chat_session(self.user_id, "To be erased")
        save_chat_message(
            user_id=self.user_id, sender="user", text="hello",
            session_id=self.session["id"], expires_at=None,
        )
        save_mood_log(user_id=self.user_id, score=5, tags=[], notes="feeling ok")
        save_audit_event("login_success", self.user_id)
        self.safety = log_safety_event(
            tier=1, rule_or_model="unit-test", category="self-harm",
            action_taken="hotline_shown_LLM_bypassed",
            message="I want to end my life tonight",
            session_id=self.session["id"], user_id=self.user_id, confidence=0.99,
        )

    def _user_refs(self, user_id):
        db = get_db()
        return {
            "chat_messages": db.chat_messages.count_documents({"user_id": user_id}),
            "mood_logs": db.mood_logs.count_documents({"user_id": user_id}),
            "chat_sessions": db.chat_sessions.count_documents({"user_id": user_id}),
            "audit_logs": db.audit_logs.count_documents({"actor_id": user_id}),
            "safety_logs": db.safety_logs.count_documents({"user_id": user_id}),
            "refresh_tokens": db.refresh_tokens.count_documents({"user_id": user_id}),
        }

    def test_delete_user_data_wipes_and_anonymizes(self):
        result = delete_user_data(self.user_id)

        self.assertEqual(result["deleted_messages"], 1)
        self.assertEqual(result["deleted_mood_logs"], 1)
        self.assertEqual(result["deleted_sessions"], 1)
        self.assertGreaterEqual(result["deleted_audit_events"], 1)
        self.assertEqual(result["deleted_refresh_tokens"], 1)
        self.assertEqual(result["anonymized_safety_logs"], 1)

        refs = self._user_refs(self.user_id)
        for collection, count in refs.items():
            self.assertEqual(count, 0, f"{collection} still references the user")

        db = get_db()
        log = db.safety_logs.find_one({"id": self.safety["id"]})
        self.assertIsNotNone(log, "aggregate audit event must survive anonymization")
        self.assertIsNone(log.get("user_id"))
        self.assertIsNone(log.get("session_id"))
        self.assertNotIn("message_excerpt", log)
        self.assertTrue(log.get("is_guest"))
        self.assertTrue(log.get("redacted"))
        self.assertIsNotNone(log.get("anonymized_at"))

        # Idempotent: a second run finds nothing left to do.
        second = delete_user_data(self.user_id)
        self.assertEqual(second["anonymized_safety_logs"], 0)

    def test_delete_user_account_wipes_user_document(self):
        from database import delete_user_account
        result = delete_user_account(self.user_id)
        self.assertTrue(result["user_account_deleted"])
        self.assertIsNone(get_db().users.find_one({"id": self.user_id}))
        for collection, count in self._user_refs(self.user_id).items():
            self.assertEqual(count, 0, f"{collection} still references the user")

    def test_safety_and_audit_records_carry_expiry(self):
        db = get_db()
        log = db.safety_logs.find_one({"id": self.safety["id"]})
        self.assertIsInstance(log.get("expires_at"), datetime)
        self.assertGreater(log["expires_at"], datetime.utcnow())

        save_audit_event("unit_test_expiry", self.user_id)
        audit = db.audit_logs.find_one({"event_type": "unit_test_expiry"})
        self.assertIsInstance(audit.get("expires_at"), datetime)
        self.assertGreater(audit["expires_at"], datetime.utcnow())

    def test_ttl_indexes_exist(self):
        info = get_db().safety_logs.index_information()
        safety_ttl = info.get("idx_safety_expires_at")
        self.assertIsNotNone(safety_ttl, "safety_logs TTL index missing")
        self.assertEqual(safety_ttl.get("expireAfterSeconds"), 0)

        audit_ttl = get_db().audit_logs.index_information().get("idx_audit_expires_at")
        self.assertIsNotNone(audit_ttl, "audit_logs TTL index missing")
        self.assertEqual(audit_ttl.get("expireAfterSeconds"), 0)


if __name__ == "__main__":
    unittest.main()
