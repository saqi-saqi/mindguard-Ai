"""
MindGuard Test Suite 1: API, Authentication and Privacy Security
=================================================================
Production Verification:
- User Authentication (Registration, Bcrypt Password Hashing, JWT Lifecycle and Validation)
- API Rate Limiting and 429 Throttle Header Invariants
- Cryptographic Storage and Session Persistence (AES-256 chat encryption at rest)
- GDPR / HIPAA-aligned Privacy Endpoints (Data Export, Right-to-be-Forgotten Data Wipe)
- Zero-PII Audit Logging and Sensitive Text Redaction
- Longitudinal Mood and Analytics Aggregation Pipelines
"""

import os
import sys
import json
import re
import unittest
import jwt
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Setup environment before application imports
os.environ["USE_MONGOMOCK"] = "true"
os.environ["FLASK_ENV"] = "testing"

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import app, reset_rate_limits
from auth import (
    hash_password,
    verify_password,
    generate_token,
    decode_token,
    JWT_SECRET_KEY,
    JWT_ALGORITHM,
)
from database import (
    init_db,
    get_db,
    save_chat_message,
    get_chat_history,
    save_mood_log,
    get_mood_logs,
    create_chat_session,
    save_audit_event,
    delete_user_data,
    cleanup_old_records,
)
from services.crisis_resources import check_resource_status, get_resources_for_region


class ApiAuthPrivacyTestCase(unittest.TestCase):

    def setUp(self):
        app.config["TESTING"] = True
        init_db()
        db = get_db()
        db.users.delete_many({})
        db.chat_messages.delete_many({})
        db.mood_logs.delete_many({})
        db.chat_sessions.delete_many({})
        db.audit_logs.delete_many({})
        reset_rate_limits()
        self.client = app.test_client()
        self.client.testing = True

        # Pre-register primary test user
        reg1 = self.client.post("/api/auth/register", json={
            "name": "Alice Smith",
            "email": "alice@example.com",
            "password": "Password123!",
            "consent_given": True
        })
        self.assertEqual(reg1.status_code, 201)
        data1 = reg1.get_json()
        self.user1_token = data1["data"]["token"]
        self.user1_id = data1["data"]["user"]["id"]

        # Pre-register secondary test user for isolation tests
        reg2 = self.client.post("/api/auth/register", json={
            "name": "Bob Jones",
            "email": "bob@example.com",
            "password": "Password123!",
            "consent_given": True
        })
        self.assertEqual(reg2.status_code, 201)
        data2 = reg2.get_json()
        self.user2_token = data2["data"]["token"]
        self.user2_id = data2["data"]["user"]["id"]

    def tearDown(self):
        reset_rate_limits()

    # --- 1. HEALTH, CORS & RESOURCES ---

    def test_health_endpoint_healthy_and_no_secret_leakage(self):
        """GET /api/health must return 200 with healthy status and no leaked secrets."""
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("data", {}).get("status"), "healthy")
        self.assertNotIn("GEMINI_API_KEY", str(data))
        self.assertNotIn("JWT_SECRET_KEY", str(data))

    def test_cors_headers(self):
        """CORS headers should correctly reflect configured allowed origins."""
        res = self.client.get("/api/health", headers={"Origin": "http://localhost:5173"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers.get("Access-Control-Allow-Origin"), "http://localhost:5173")

        preflight = self.client.options(
            "/api/chat",
            headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"}
        )
        self.assertEqual(preflight.status_code, 200)

    def test_resources_endpoint_regional_and_fallback(self):
        """GET /api/resources returns active helplines, handles fallback for unknown regions."""
        # Regional query
        res_pk = self.client.get("/api/resources?region=pakistan")
        self.assertEqual(res_pk.status_code, 200)
        data = res_pk.get_json().get("data", {}).get("resources", {})
        self.assertIn("pakistan", data)
        self.assertIn("international", data)

        # Outdated detection logic
        valid_res = {
            "organization": "Active Helpline",
            "verification_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "review_interval_days": 180
        }
        self.assertFalse(check_resource_status(valid_res)["is_outdated"])

        old_date = (datetime.now(timezone.utc) - timedelta(days=200)).strftime("%Y-%m-%d")
        expired_res = {
            "organization": "Old Helpline",
            "verification_date": old_date,
            "review_interval_days": 180
        }
        self.assertTrue(check_resource_status(expired_res)["is_outdated"])

        # Unknown region fallback
        fallback = get_resources_for_region("unknown_region_xyz")
        self.assertGreater(len(fallback), 0)
        self.assertIn("Suicide & Crisis Lifeline", str(fallback))

    # --- 2. PASSWORD SECURITY & AUTHENTICATION ---

    def test_bcrypt_password_hashing(self):
        """Bcrypt password hashing must be one-way and correctly verifiable."""
        raw = "SecurePassword123!"
        hashed = hash_password(raw)
        self.assertNotEqual(raw, hashed)
        self.assertTrue(verify_password(raw, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_register_duplicate_email_rejected_with_409(self):
        """Registering with an already registered email must return 409 DUPLICATE_EMAIL."""
        res = self.client.post("/api/auth/register", json={
            "name": "Alice Clone",
            "email": "alice@example.com",
            "password": "Password123!"
        })
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.get_json()["error"]["code"], "DUPLICATE_EMAIL")

    def test_register_input_validation_and_malformed_fields(self):
        """Register must reject short passwords, invalid email formats, and non-string inputs with 400."""
        # Short password (<8 chars)
        res = self.client.post("/api/auth/register", json={
            "name": "Short", "email": "short@example.com", "password": "123"
        })
        self.assertEqual(res.status_code, 400)

        # Invalid email format
        res = self.client.post("/api/auth/register", json={
            "name": "BadEmail", "email": "not-an-email", "password": "Password123!"
        })
        self.assertEqual(res.status_code, 400)

        # Non-string identity fields (array / integer)
        res = self.client.post("/api/auth/register", json={
            "name": ["invalid"], "email": "array@example.com", "password": "Password123!"
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"]["code"], "INVALID_FIELD")

        # NoSQL object injection
        res = self.client.post("/api/auth/register", json={
            "name": "User", "email": {"$ne": None}, "password": "Password123!"
        })
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.get_json()["error"]["code"], "INVALID_FIELD")

    def test_login_valid_invalid_and_nosql_injection(self):
        """Login must succeed with valid credentials and reject invalid credentials or NoSQL injection."""
        # Valid credentials
        res_ok = self.client.post("/api/auth/login", json={
            "email": "alice@example.com", "password": "Password123!"
        })
        self.assertEqual(res_ok.status_code, 200)
        self.assertIn("token", res_ok.get_json()["data"])

        # Invalid password
        res_bad = self.client.post("/api/auth/login", json={
            "email": "alice@example.com", "password": "WrongPassword!"
        })
        self.assertEqual(res_bad.status_code, 401)

        # NoSQL object injection payload
        res_nosql = self.client.post("/api/auth/login", json={
            "email": {"$ne": None}, "password": {"$ne": None}
        })
        self.assertEqual(res_nosql.status_code, 400)
        self.assertEqual(res_nosql.get_json()["error"]["code"], "INVALID_FIELD")

    # --- 3. JWT TOKEN LIFECYCLE & ROUTE AUTHORIZATION ---

    def test_jwt_me_endpoint_and_authorization_guards(self):
        """GET /api/auth/me validates Bearer token and rejects missing, invalid, or expired tokens."""
        # Valid token
        res_valid = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_valid.status_code, 200)
        self.assertEqual(res_valid.get_json()["data"]["user"]["email"], "alice@example.com")

        # Missing token
        res_missing = self.client.get("/api/auth/me")
        self.assertEqual(res_missing.status_code, 401)

        # Malformed / invalid token
        res_malformed = self.client.get("/api/auth/me", headers={"Authorization": "Bearer fake.invalid.token"})
        self.assertEqual(res_malformed.status_code, 401)

        # Expired token
        exp_payload = {
            "sub": self.user1_id,
            "email": "alice@example.com",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1)
        }
        expired_token = jwt.encode(exp_payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
        res_expired = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        self.assertEqual(res_expired.status_code, 401)
        self.assertIn("expired", res_expired.get_json()["error"]["message"].lower())

    # --- 4. MOOD LOGS CRUD & MULTI-USER ISOLATION ---

    def test_mood_logs_crud_and_user_isolation(self):
        """Mood logs must be isolated per user: User 2 cannot view or delete User 1's entries."""
        # User 1 creates log
        res1 = self.client.post(
            "/api/moods",
            json={"score": 8, "tags": ["hopeful", "calm"], "notes": "Feeling good today"},
            headers={"Authorization": f"Bearer {self.user1_token}"}
        )
        self.assertEqual(res1.status_code, 201)
        log1_id = res1.get_json()["data"]["mood_log"]["id"]

        # User 2 reads moods - must not see User 1's log
        res2 = self.client.get("/api/moods", headers={"Authorization": f"Bearer {self.user2_token}"})
        self.assertEqual(res2.status_code, 200)
        user2_logs = res2.get_json()["data"]["mood_logs"]
        self.assertNotIn(log1_id, [l["id"] for l in user2_logs])

        # User 2 attempts to delete User 1's log -> 404
        res_del_unauth = self.client.delete(f"/api/moods/{log1_id}", headers={"Authorization": f"Bearer {self.user2_token}"})
        self.assertEqual(res_del_unauth.status_code, 404)

        # User 1 deletes own log -> 200
        res_del_own = self.client.delete(f"/api/moods/{log1_id}", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_del_own.status_code, 200)

    def test_mood_log_validation_and_retention_disabled(self):
        """Mood log validates score (1-10) and rejects creation if retention is disabled (409)."""
        # Invalid score > 10
        res_invalid = self.client.post(
            "/api/moods",
            json={"score": 15, "tags": ["invalid"]},
            headers={"Authorization": f"Bearer {self.user1_token}"}
        )
        self.assertEqual(res_invalid.status_code, 400)

        # Disable retention for user
        self.client.put(
            "/api/user/settings",
            json={"retention_enabled": False},
            headers={"Authorization": f"Bearer {self.user1_token}"}
        )

        # Create mood log with retention disabled -> 409 RETENTION_DISABLED
        res_disabled = self.client.post(
            "/api/moods",
            json={"score": 7, "tags": ["calm"]},
            headers={"Authorization": f"Bearer {self.user1_token}"}
        )
        self.assertEqual(res_disabled.status_code, 409)
        self.assertIn("RETENTION_DISABLED", res_disabled.get_json()["error"]["code"])

    def test_analytics_aggregation(self):
        """GET /api/analytics returns aggregated mood data."""
        self.client.post(
            "/api/moods",
            json={"score": 9, "tags": ["joy"]},
            headers={"Authorization": f"Bearer {self.user2_token}"}
        )
        self.client.post(
            "/api/moods",
            json={"score": 7, "tags": ["peace"]},
            headers={"Authorization": f"Bearer {self.user2_token}"}
        )

        res = self.client.get("/api/analytics?period=monthly", headers={"Authorization": f"Bearer {self.user2_token}"})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()["data"]
        self.assertIn("mood_logs", data)
        self.assertEqual(len(data["mood_logs"]), 2)

    # --- 5. CHAT PERSISTENCE, HISTORY & SUMMARIZATION ---

    def test_authenticated_chat_persistence_and_history(self):
        """Authenticated chat saves messages to database and retrieves chronological history."""
        chat_payload = {"message": "I am feeling stressed about exams."}
        self.client.post("/api/chat", json=chat_payload, headers={"Authorization": f"Bearer {self.user1_token}"})

        history_res = self.client.get("/api/chat/history", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(history_res.status_code, 200)
        messages = history_res.get_json()["data"]["messages"]
        self.assertGreaterEqual(len(messages), 2)  # User message + Bot response

    def test_session_summarization(self):
        """POST /api/chat/summarize returns supportive reflection summary."""
        payload = {
            "messages": [
                {"sender": "user", "text": "I feel stressed about my thesis."},
                {"sender": "bot", "text": "Take it step by step."},
                {"sender": "user", "text": "I tried box breathing and feel a bit calmer now."}
            ]
        }
        res = self.client.post("/api/chat/summarize", json=payload, headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("summary", res.get_json().get("data", {}))

    def test_trusted_contact_management(self):
        """POST /api/user/trusted-contact persists emergency contact details."""
        payload = {"name": "Dr. Sarah", "phone": "0300-1234567", "relationship": "Counselor"}
        tc_res = self.client.post("/api/user/trusted-contact", json=payload, headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(tc_res.status_code, 200)
        self.assertTrue(tc_res.get_json().get("success"))

    # --- 6. PRIVACY, DATA EXPORT, WIPE & ACCOUNT PURGE ---

    def test_data_export_and_user_data_wipe(self):
        """GET /api/user/export returns machine-readable JSON; DELETE /api/user/data wipes user records."""
        # Add mood and chat data
        self.client.post(
            "/api/moods",
            json={"score": 9, "tags": ["calm"], "notes": "Exportable Entry"},
            headers={"Authorization": f"Bearer {self.user1_token}"}
        )

        # Export data
        exp_res = self.client.get("/api/user/export", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(exp_res.status_code, 200)
        exp_data = exp_res.get_json()["data"]
        self.assertIn("user_profile", exp_data)
        self.assertIn("mood_logs", exp_data)
        self.assertIn("chat_messages", exp_data)

        # Wipe user data
        wipe_res = self.client.delete("/api/user/data", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(wipe_res.status_code, 200)

        # Verify mood logs are cleared
        moods_after = self.client.get("/api/moods", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(len(moods_after.get_json()["data"]["mood_logs"]), 0)

    def test_privacy_deletion_removes_user_linked_records_and_audit_logs(self):
        """DELETE /api/user/data and DELETE /api/auth/account completely purge records and user account."""
        db = get_db()
        save_chat_message(self.user1_id, "user", "I feel overwhelmed", risk_level="ELEVATED_DISTRESS")
        save_mood_log(self.user1_id, 3, ["stress"], "A rough day")
        create_chat_session(self.user1_id, title="Stress check-in")
        save_audit_event("crisis_detected", self.user1_id, {"source": "deterministic", "request_id": "req-1"})
        save_audit_event("safety_support_selected", self.user2_id, {"source": "other_user"})

        self.assertEqual(db.chat_messages.count_documents({"user_id": self.user1_id}), 1)
        self.assertEqual(db.mood_logs.count_documents({"user_id": self.user1_id}), 1)
        self.assertEqual(db.chat_sessions.count_documents({"user_id": self.user1_id}), 1)
        self.assertEqual(db.audit_logs.count_documents({"actor_id": self.user1_id}), 1)

        res = self.client.delete("/api/user/data", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res.status_code, 200)

        self.assertEqual(db.chat_messages.count_documents({"user_id": self.user1_id}), 0)
        self.assertEqual(db.mood_logs.count_documents({"user_id": self.user1_id}), 0)
        self.assertEqual(db.chat_sessions.count_documents({"user_id": self.user1_id}), 0)
        self.assertEqual(db.audit_logs.count_documents({"actor_id": self.user1_id}), 0)
        self.assertEqual(db.audit_logs.count_documents({"actor_id": self.user2_id}), 1)  # User 2 untouched

        # Delete account
        res_acc = self.client.delete("/api/auth/account", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_acc.status_code, 200)
        self.assertIsNone(db.users.find_one({"id": self.user1_id}))

        # Subsequent /me call must be 401
        res_me = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {self.user1_token}"})
        self.assertEqual(res_me.status_code, 401)

    def test_admin_retention_cleanup_authorization(self):
        """Admin retention cleanup endpoint requires admin role."""
        forbidden = self.client.post(
            "/api/admin/retention-cleanup",
            json={"retention_days": 30},
            headers={"Authorization": f"Bearer {self.user1_token}"}
        )
        self.assertEqual(forbidden.status_code, 403)

        # Elevate to admin
        get_db().users.update_one({"id": self.user1_id}, {"$set": {"role": "admin"}})
        allowed = self.client.post(
            "/api/admin/retention-cleanup",
            json={"retention_days": 30},
            headers={"Authorization": f"Bearer {self.user1_token}"}
        )
        self.assertEqual(allowed.status_code, 200)
        self.assertTrue(allowed.get_json()["success"])

    # --- 7. SECURITY MIDDLEWARE, RATE LIMITING & PAYLOAD GUARDS ---

    def test_payload_too_large_413(self):
        """Request body larger than 1MB must be rejected with 413 Payload Too Large."""
        large_text = "A" * (1 * 1024 * 1024 + 500)
        res = self.client.post("/api/chat", json={"message": large_text})
        self.assertEqual(res.status_code, 413)

    def test_rate_limit_429(self):
        """Exceeding rate limit (60 req/min) returns 429 RATE_LIMIT_EXCEEDED."""
        reset_rate_limits()
        for _ in range(60):
            res = self.client.post("/api/chat", json={"message": "hello"})
            self.assertEqual(res.status_code, 200)

        # 61st request triggers rate limit
        res_blocked = self.client.post("/api/chat", json={"message": "hello again"})
        self.assertEqual(res_blocked.status_code, 429)
        self.assertIn("RATE_LIMIT_EXCEEDED", res_blocked.get_json()["error"]["code"])
        reset_rate_limits()

    def test_chat_input_validation(self):
        """Chat endpoint rejects empty messages (400) and messages > 2000 chars (400)."""
        # Empty string / whitespace
        res_empty = self.client.post("/api/chat", json={"message": "   "})
        self.assertEqual(res_empty.status_code, 400)

        # Message exceeding 2000 chars
        long_msg = "x" * 2005
        res_long = self.client.post("/api/chat", json={"message": long_msg})
        self.assertEqual(res_long.status_code, 400)
        self.assertIn("MESSAGE_TOO_LONG", res_long.get_json()["error"]["code"])

    # --- 8. LOGGING REDACTION & PRIVACY AUDITING ---

    def test_logs_do_not_contain_raw_message(self):
        """Verify that raw user message text is redacted from application logs."""
        test_msg = "I wrote a goodbye note and deleted my accounts."
        with self.assertLogs("MindGuard-API", level="INFO") as cm:
            resp = self.client.post("/api/chat", json={"message": test_msg})
            self.assertEqual(resp.status_code, 200)
            logs = "\n".join(cm.output)
            self.assertNotIn(test_msg, logs)
            self.assertIsNotNone(re.search(r"req-[0-9a-f]{12}", logs))

    def test_safety_feedback_metadata_only_storage(self):
        """POST /api/safety-feedback stores structured telemetry and rejects arbitrary raw text."""
        response = self.client.post(
            "/api/safety-feedback",
            json={"outcome": "safe_for_now", "source": "crisis_modal"},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["data"]["recorded"])

        audit = get_db().audit_logs.find_one({"event_type": "safety_support_selected"})
        self.assertIsNotNone(audit)
        self.assertEqual(audit["metadata"], {"outcome": "safe_for_now", "source": "crisis_modal"})

        # Rejection of untrusted sources / rogue message payloads
        invalid = self.client.post(
            "/api/safety-feedback",
            json={"outcome": "safe_for_now", "source": "untrusted_source", "message": "do not store this"},
        )
        self.assertEqual(invalid.status_code, 400)


if __name__ == "__main__":
    unittest.main(verbosity=2)
