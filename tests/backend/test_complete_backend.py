"""
test_complete_backend.py
========================
Comprehensive backend integration test suite validating MindGuard APIs, security middleware,
authentication, mood logging, privacy retention, rate limiting, safety pipelines, and production config.
Runs completely offline with mongomock and mocks for external LLMs.
"""

import unittest
import os
import json
import time
import jwt
from datetime import datetime, timedelta

from app import app, reset_rate_limits
from auth import JWT_SECRET_KEY, JWT_ALGORITHM, generate_token
from database import get_db, init_db, save_chat_message, save_mood_log, create_chat_session, save_audit_event

class CompleteBackendTestCase(unittest.TestCase):

    def setUp(self):
        os.environ["USE_MONGOMOCK"] = "true"
        os.environ["FLASK_ENV"] = "testing"
        init_db()
        db = get_db()
        db.users.delete_many({})
        db.chat_messages.delete_many({})
        db.mood_logs.delete_many({})
        db.chat_sessions.delete_many({})
        db.audit_logs.delete_many({})
        reset_rate_limits()
        self.app = app.test_client()
        self.app.testing = True

        # Register test user 1
        res1 = self.app.post("/api/auth/register", json={
            "name": "Alice Smith",
            "email": "alice@example.com",
            "password": "Password123",
            "consent_given": True
        })
        self.assertEqual(res1.status_code, 201)
        data1 = res1.get_json()
        self.user1_token = data1["token"]
        self.user1_id = data1["user"]["id"]

        # Register test user 2 (for user isolation tests)
        res2 = self.app.post("/api/auth/register", json={
            "name": "Bob Jones",
            "email": "bob@example.com",
            "password": "Password123",
            "consent_given": True
        })
        self.assertEqual(res2.status_code, 201)
        data2 = res2.get_json()
        self.user2_token = data2["token"]
        self.user2_id = data2["user"]["id"]

    def tearDown(self):
        reset_rate_limits()

    # --- 1. AUTHENTICATION & INPUT VALIDATION ---

    def test_register_duplicate_email(self):
        res = self.app.post("/api/auth/register", json={
            "name": "Alice Clone",
            "email": "alice@example.com",
            "password": "Password123"
        })
        self.assertEqual(res.status_code, 409)
        self.assertFalse(res.get_json()["success"])

    def test_register_invalid_fields(self):
        # Short password
        res = self.app.post("/api/auth/register", json={
            "name": "Test", "email": "valid@example.com", "password": "123"
        })
        self.assertEqual(res.status_code, 400)

        # Invalid email format
        res = self.app.post("/api/auth/register", json={
            "name": "Test", "email": "invalid-email-format", "password": "Password123"
        })
        self.assertEqual(res.status_code, 400)

        # Non-string input fields
        res = self.app.post("/api/auth/register", json={
            "name": 12345, "email": "valid@example.com", "password": "Password123"
        })
        self.assertEqual(res.status_code, 400)

    def test_login_success_and_invalid_credentials(self):
        # Success
        res = self.app.post("/api/auth/login", json={
            "email": "alice@example.com", "password": "Password123"
        })
        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.get_json()["data"])

        # Invalid password
        res = self.app.post("/api/auth/login", json={
            "email": "alice@example.com", "password": "WrongPassword"
        })
        self.assertEqual(res.status_code, 401)

    def test_token_expiry_and_client_side_logout_semantics(self):
        # Generate expired token
        exp_payload = {
            "sub": self.user1_id,
            "email": "alice@example.com",
            "exp": datetime.utcnow() - timedelta(hours=1)
        }
        expired_token = jwt.encode(exp_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        
        res = self.app.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("expired", res.get_json()["error"]["message"].lower())

        # Client-side logout test: token disposal is handled on client, backend remains stateless
        res = self.app.get("/api/auth/me", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res.status_code, 200)

    # --- 2. MOOD LOGS, CRUD, & USER ISOLATION ---

    def test_mood_log_crud_and_user_isolation(self):
        # User 1 creates mood log
        res1 = self.app.post("/api/moods", json={"score": 8, "tags": ["happy", "calm"], "notes": "Great day"},
                            headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res1.status_code, 201)
        log1_id = res1.get_json()["data"]["mood_log"]["id"]

        # User 2 fetches moods - should not see User 1's log
        res2 = self.app.get("/api/moods", headers={"Authorization": f"Bearer {self.user2_token}"})
        self.assertEqual(res2.status_code, 200)
        logs2 = res2.get_json()["data"]["mood_logs"]
        self.assertNotIn(log1_id, [l["id"] for l in logs2])

        # User 2 attempts to delete User 1's log - should be 404/permission denied
        res_del = self.app.delete(f"/api/moods/{log1_id}", headers={"Authorization": f"Bearer {self.user2_token}"})
        self.assertEqual(res_del.status_code, 404)

        # User 1 deletes own log
        res_del_own = self.app.delete(f"/api/moods/{log1_id}", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_del_own.status_code, 200)

    def test_mood_log_validation_and_retention_disabled(self):
        # Invalid score range
        res = self.app.post("/api/moods", json={"score": 15, "tags": ["invalid"]},
                            headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res.status_code, 400)

        # Disable retention for User 1
        self.app.put("/api/user/settings", json={"retention_enabled": False},
                     headers={"Authorization": f"Bearer {self.user1_token}"})

        # Attempt to save mood log when retention is disabled -> 409 Conflict
        res_ret = self.app.post("/api/moods", json={"score": 7, "tags": ["calm"]},
                                headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_ret.status_code, 409)
        self.assertIn("RETENTION_DISABLED", res_ret.get_json()["error"]["code"])

    def test_analytics_aggregation(self):
        # Add mood logs for user 2
        self.app.post("/api/moods", json={"score": 9, "tags": ["joy"]}, headers={"Authorization": f"Bearer {self.user2_token}"})
        self.app.post("/api/moods", json={"score": 7, "tags": ["peace"]}, headers={"Authorization": f"Bearer {self.user2_token}"})

        res = self.app.get("/api/analytics?period=monthly", headers={"Authorization": f"Bearer {self.user2_token}"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertIn("mood_logs", data)
        self.assertEqual(len(data["mood_logs"]), 2)

    # --- 3. PRIVACY DATA EXPORT & ACCOUNT DELETION ---

    def test_data_export_wipe_and_account_deletion(self):
        # Export personal data
        res_exp = self.app.get("/api/user/export", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_exp.status_code, 200)
        export_data = res_exp.get_json()["data"]
        self.assertIn("user_profile", export_data)
        self.assertIn("chat_messages", export_data)
        self.assertIn("mood_logs", export_data)

        # Wipe personal data (/api/user/data)
        res_wipe = self.app.delete("/api/user/data", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_wipe.status_code, 200)

        # Delete account (/api/auth/account)
        res_acc = self.app.delete("/api/auth/account", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_acc.status_code, 200)

        # Verify user no longer exists
        res_me = self.app.get("/api/auth/me", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_me.status_code, 401)

    def test_privacy_deletion_removes_user_linked_records_and_audit_logs(self):
        db = get_db()

        save_chat_message(self.user1_id, "user", "I feel overwhelmed and cannot sleep", risk_level="ELEVATED_DISTRESS")
        save_chat_message(self.user1_id, "assistant", "I am here with you", risk_level="LOW")
        save_mood_log(self.user1_id, 3, ["stress"], "A rough day")
        save_mood_log(self.user1_id, 5, ["calm"], "Better in the evening")
        session = create_chat_session(self.user1_id, title="Stress check-in")
        save_audit_event("crisis_detected", self.user1_id, {"source": "deterministic", "request_id": "req-1"})
        save_audit_event("safety_support_selected", self.user2_id, {"source": "other_user"})

        self.assertEqual(db.chat_messages.count_documents({"user_id": self.user1_id}), 2)
        self.assertEqual(db.mood_logs.count_documents({"user_id": self.user1_id}), 2)
        self.assertEqual(db.chat_sessions.count_documents({"user_id": self.user1_id}), 1)
        self.assertEqual(db.audit_logs.count_documents({"actor_id": self.user1_id}), 1)

        res = self.app.delete("/api/user/data", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res.status_code, 200)
        stats = res.get_json()["data"]["stats"]
        self.assertEqual(stats["deleted_messages"], 2)
        self.assertEqual(stats["deleted_mood_logs"], 2)
        self.assertEqual(stats["deleted_sessions"], 1)
        self.assertEqual(stats["deleted_audit_events"], 1)

        self.assertEqual(db.chat_messages.count_documents({"user_id": self.user1_id}), 0)
        self.assertEqual(db.mood_logs.count_documents({"user_id": self.user1_id}), 0)
        self.assertEqual(db.chat_sessions.count_documents({"user_id": self.user1_id}), 0)
        self.assertEqual(db.audit_logs.count_documents({"actor_id": self.user1_id}), 0)
        self.assertEqual(db.audit_logs.count_documents({"actor_id": self.user2_id}), 1)

        res_acc = self.app.delete("/api/auth/account", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_acc.status_code, 200)
        self.assertIsNone(db.users.find_one({"id": self.user1_id}))

    # --- 4. SECURITY MIDDLEWARE, CORS, 1MB PAYLOAD & RATE LIMITING ---

    def test_cors_headers(self):
        res = self.app.get("/api/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")

    def test_payload_too_large_413(self):
        # Generate payload larger than 1MB
        large_text = "A" * (1 * 1024 * 1024 + 500)
        res = self.app.post("/api/chat", json={"message": large_text})
        self.assertEqual(res.status_code, 413)

    def test_rate_limit_429(self):
        reset_rate_limits()
        for i in range(60):
            res = self.app.post("/api/chat", json={"message": "hello"})
            self.assertEqual(res.status_code, 200)

        # 61st request should be rate-limited -> 429
        res_blocked = self.app.post("/api/chat", json={"message": "hello again"})
        self.assertEqual(res_blocked.status_code, 429)
        self.assertIn("RATE_LIMIT_EXCEEDED", res_blocked.get_json()["error"]["code"])

        # Reset isolated state for suite sanity
        reset_rate_limits()

    # --- 5. CHAT & SAFETY PIPELINE ---

    def test_chat_invalid_json_and_length_validation(self):
        # Empty message
        res = self.app.post("/api/chat", json={"message": "   "})
        self.assertEqual(res.status_code, 400)

        # Message exceeding MAX_MESSAGE_LENGTH (2000 chars)
        long_msg = "x" * 2005
        res = self.app.post("/api/chat", json={"message": long_msg})
        self.assertEqual(res.status_code, 400)
        self.assertIn("MESSAGE_TOO_LONG", res.get_json()["error"]["code"])

    def test_tier1_crisis_bypass(self):
        # Send explicit Tier-1 crisis utterance
        res = self.app.post("/api/chat", json={"message": "I want to kill myself right now."})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["risk_level"], "HIGH_CRISIS")
        self.assertTrue(data["requires_immediate_action"])
        self.assertIn("emergency_resources", data)

    def test_negation_non_crisis_flow(self):
        # Negated statement should not trigger crisis bypass
        res = self.app.post("/api/chat", json={"message": "I am definitely NOT suicidal, just feeling a bit anxious about my exam."})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertEqual(data["risk_level"], "LOW")
        self.assertFalse(data["requires_immediate_action"])

    def test_safety_feedback_is_metadata_only_and_optional_auth(self):
        response = self.app.post(
            "/api/safety-feedback",
            json={"outcome": "safe_for_now", "source": "crisis_modal"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["data"]["recorded"])

        audit = get_db().audit_logs.find_one({"event_type": "safety_support_selected"})
        self.assertIsNotNone(audit)
        self.assertEqual(audit["metadata"], {"outcome": "safe_for_now", "source": "crisis_modal"})

        invalid = self.app.post(
            "/api/safety-feedback",
            json={"outcome": "safe_for_now", "source": "untrusted_source", "message": "do not store this"},
        )
        self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main()
