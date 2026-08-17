"""
test_suite.py
=============
Automated Unit and Integration Test Suite for MindGuard REST API
Includes complete coverage for User Authentication, Bcrypt Password Hashing,
JWT Validation, Route Authorization, User Data Isolation, Mood Logs CRUD, Chat Persistence,
Data Deletion, Retention Cleanup, Crisis Resources Verification, and Health Checks.
"""

import unittest
from unittest.mock import patch, MagicMock
import json
import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Configure the in-memory test database before importing the application config.
os.environ['USE_MONGOMOCK'] = 'true'

# Add server directory to Python path
SERVER_DIR = Path(__file__).resolve().parent
sys.path.append(str(SERVER_DIR))

from app import app
from database import (
    init_db,
    get_user_by_email,
    get_user_by_id,
    get_db,
    save_mood_log,
    get_mood_logs,
    save_chat_message,
    get_chat_history,
    delete_user_data,
    cleanup_old_records
)
from auth import hash_password, verify_password, generate_token, decode_token
from services.crisis_resources import check_resource_status, get_resources_for_region, CRISIS_RESOURCES


class TestMindGuardAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config['TESTING'] = True
        init_db()


    def setUp(self):
        self.client = app.test_client()

    # --- Section 1: Health & System Endpoints ---

    def test_01_health_endpoint(self):
        """Test GET /api/health returns 200 and healthy status without sensitive data."""
        response = self.client.get('/api/health')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('data', {}).get('status'), 'healthy')
        self.assertNotIn('GEMINI_API_KEY', str(data))

    def test_02_resources_endpoint(self):
        """Test GET /api/resources returns active crisis helplines and disclaimers."""
        response = self.client.get('/api/resources?region=pakistan')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get('success'))
        resources = data.get('data', {}).get('resources', {})
        self.assertIn('pakistan', resources)
        self.assertIn('international', resources)

    # --- Section 2: Authentication & Password Security ---

    def test_03_password_hashing(self):
        """Test bcrypt password hashing and verification logic."""
        raw_password = "SecurePassword123!"
        hashed = hash_password(raw_password)
        self.assertNotEqual(raw_password, hashed)
        self.assertTrue(verify_password(raw_password, hashed))
        self.assertFalse(verify_password("WrongPassword", hashed))

    def test_04_user_registration(self):
        """Test POST /api/auth/register creates a user and returns a valid JWT token."""
        unique_email = f"testuser_{int(datetime.utcnow().timestamp())}@example.com"
        payload = {
            "name": "Test User",
            "email": unique_email,
            "password": "Password123!"
        }
        response = self.client.post('/api/auth/register', json=payload)
        self.assertEqual(response.status_code, 201)
        data = response.get_json()
        self.assertTrue(data.get('success'))
        self.assertIn('token', data.get('data', {}))

    def test_05_duplicate_registration_rejection(self):
        """Test POST /api/auth/register rejects duplicate email address with 409 Conflict."""
        email = "dupuser@example.com"
        payload = {"name": "Dup User", "email": email, "password": "Password123!"}
        # First registration
        self.client.post('/api/auth/register', json=payload)
        # Duplicate registration attempt
        response = self.client.post('/api/auth/register', json=payload)
        self.assertEqual(response.status_code, 409)
        data = response.get_json()
        self.assertFalse(data.get('success'))
        self.assertEqual(data.get('error', {}).get('code'), 'DUPLICATE_EMAIL')

    def test_06_login_success_and_failure(self):
        """Test POST /api/auth/login with valid and invalid credentials."""
        email = f"loginuser_{int(datetime.utcnow().timestamp())}@example.com"
        password = "ValidPassword123!"
        self.client.post('/api/auth/register', json={"name": "Login User", "email": email, "password": password})

        # Valid Login
        res_valid = self.client.post('/api/auth/login', json={"email": email, "password": password})
        self.assertEqual(res_valid.status_code, 200)
        self.assertIn('token', res_valid.get_json().get('data', {}))

        # Invalid Login
        res_invalid = self.client.post('/api/auth/login', json={"email": email, "password": "WrongPassword"})
        self.assertEqual(res_invalid.status_code, 401)
        self.assertFalse(res_invalid.get_json().get('success'))

    def test_07_jwt_token_validation_and_me_endpoint(self):
        """Test GET /api/auth/me returns authenticated user details for valid token."""
        email = f"jwtuser_{int(datetime.utcnow().timestamp())}@example.com"
        reg_res = self.client.post('/api/auth/register', json={"name": "JWT User", "email": email, "password": "Password123!"})
        token = reg_res.get_json()['data']['token']

        # Request with Bearer Token
        response = self.client.get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data.get('data', {}).get('user', {}).get('email'), email)

    def test_08_protected_route_unauthorized_access(self):
        """Test protected endpoints return 401 Unauthorized when Bearer token is missing or invalid."""
        # Missing Header
        res_no_token = self.client.get('/api/auth/me')
        self.assertEqual(res_no_token.status_code, 401)

        # Invalid Token
        res_invalid_token = self.client.get('/api/auth/me', headers={"Authorization": "Bearer invalid.fake.token"})
        self.assertEqual(res_invalid_token.status_code, 401)

    # --- Section 3: Data Persistence & Isolation ---

    def test_09_mood_logs_crud_and_user_isolation(self):
        """Test persistent mood log creation, retrieval, and user data isolation."""
        # User A
        reg_a = self.client.post('/api/auth/register', json={"name": "User A", "email": f"usera_{int(datetime.utcnow().timestamp())}@example.com", "password": "Password123!"})
        token_a = reg_a.get_json()['data']['token']

        # User B
        reg_b = self.client.post('/api/auth/register', json={"name": "User B", "email": f"userb_{int(datetime.utcnow().timestamp())}@example.com", "password": "Password123!"})
        token_b = reg_b.get_json()['data']['token']

        # Create Mood Log for User A
        post_res = self.client.post('/api/moods', json={"score": 8, "tags": ["hopeful"], "notes": "Feeling hopeful today"}, headers={"Authorization": f"Bearer {token_a}"})
        self.assertEqual(post_res.status_code, 201)

        # Retrieve Mood Logs User A
        get_a = self.client.get('/api/moods', headers={"Authorization": f"Bearer {token_a}"})
        self.assertEqual(len(get_a.get_json()['data']['mood_logs']), 1)

        # Verify User B cannot see User A's logs
        get_b = self.client.get('/api/moods', headers={"Authorization": f"Bearer {token_b}"})
        self.assertEqual(len(get_b.get_json()['data']['mood_logs']), 0)

    def test_10_chat_message_persistence_and_history(self):
        """Test authenticated POST /api/chat saves conversation to persistent storage."""
        email = f"chatuser_{int(datetime.utcnow().timestamp())}@example.com"
        reg_res = self.client.post('/api/auth/register', json={"name": "Chat User", "email": email, "password": "Password123!"})
        token = reg_res.get_json()['data']['token']

        # Send Chat Message with Token
        chat_payload = {"message": "I am feeling stressed about work."}
        self.client.post('/api/chat', json=chat_payload, headers={"Authorization": f"Bearer {token}"})

        # Retrieve Chat History
        history_res = self.client.get('/api/chat/history', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(history_res.status_code, 200)
        messages = history_res.get_json()['data']['messages']
        self.assertGreaterEqual(len(messages), 2)  # User message + Bot response

    def test_11_personal_data_deletion(self):
        """Test DELETE /api/user/data wipes personal chat and mood records."""
        email = f"wipeuser_{int(datetime.utcnow().timestamp())}@example.com"
        reg_res = self.client.post('/api/auth/register', json={"name": "Wipe User", "email": email, "password": "Password123!"})
        token = reg_res.get_json()['data']['token']

        # Add Mood and Chat Data
        self.client.post('/api/moods', json={"score": 5, "tags": [], "notes": "Test Entry"}, headers={"Authorization": f"Bearer {token}"})
        self.client.post('/api/chat', json={"message": "Test Message"}, headers={"Authorization": f"Bearer {token}"})

        # Wipe Data
        wipe_res = self.client.delete('/api/user/data', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(wipe_res.status_code, 200)

        # Confirm Empty
        moods_res = self.client.get('/api/moods', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(len(moods_res.get_json()['data']['mood_logs']), 0)

    def test_12_data_retention_cleanup(self):
        """Test administrative data-retention cleanup workflow."""
        email = f"adminuser_{int(datetime.utcnow().timestamp())}@example.com"
        reg_res = self.client.post('/api/auth/register', json={"name": "Admin User", "email": email, "password": "Password123!"})
        token = reg_res.get_json()['data']['token']

        forbidden = self.client.post('/api/admin/retention-cleanup', json={"retention_days": 30}, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(forbidden.status_code, 403)
        get_db().users.update_one({"email": email}, {"$set": {"role": "admin"}})
        cleanup_res = self.client.post('/api/admin/retention-cleanup', json={"retention_days": 30}, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(cleanup_res.status_code, 200)
        self.assertTrue(cleanup_res.get_json().get('success'))

    def test_19_user_data_export(self):
        """Test GET /api/user/export returns machine-readable JSON export (UC9)."""
        email = f"exportuser_{int(datetime.utcnow().timestamp())}@example.com"
        reg_res = self.client.post('/api/auth/register', json={"name": "Export User", "email": email, "password": "Password123!"})
        token = reg_res.get_json()['data']['token']

        # Add Mood and Chat Data
        self.client.post('/api/moods', json={"score": 9, "tags": ["calm"], "notes": "Exportable Entry"}, headers={"Authorization": f"Bearer {token}"})

        # Fetch Export
        export_res = self.client.get('/api/user/export', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(export_res.status_code, 200)
        data = export_res.get_json().get('data', {})
        self.assertIn('user_profile', data)
        self.assertIn('mood_logs', data)
        self.assertIn('chat_messages', data)

    # --- Section 4: Crisis Resource Verification & Fallbacks ---

    def test_13_crisis_resource_verification_and_outdated_detection(self):
        """Test crisis resource verification logic and outdated status detection."""
        # Active verified resource
        valid_res = {
            "organization": "Test Helpline",
            "verification_date": datetime.utcnow().strftime("%Y-%m-%d"),
            "review_interval_days": 180
        }
        status_valid = check_resource_status(valid_res)
        self.assertFalse(status_valid["is_outdated"])
        self.assertEqual(status_valid["review_status"], "VERIFIED")

        # Expired resource
        old_date = (datetime.utcnow() - timedelta(days=200)).strftime("%Y-%m-%d")
        expired_res = {
            "organization": "Old Helpline",
            "verification_date": old_date,
            "review_interval_days": 180
        }
        status_expired = check_resource_status(expired_res)
        self.assertTrue(status_expired["is_outdated"])
        self.assertEqual(status_expired["review_status"], "EXPIRED")

    def test_14_crisis_resource_unknown_region_fallback(self):
        """Test regional lookup falls back to international for unknown regions."""
        resources = get_resources_for_region("unknown_mars_region")
        self.assertGreater(len(resources), 0)
        self.assertIn("Suicide & Crisis Lifeline", str(resources))

    # --- Section 5: Safety Pipeline & Gemini Bypass ---

    def test_15_chat_high_risk_crisis_detection(self):
        """Test POST /api/chat detects high risk and returns safety response with emergency helplines."""
        payload = {"message": "I feel hopeless and I want to end my life tonight."}
        response = self.client.post('/api/chat', json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertTrue(data.get('success'))
        self.assertEqual(data.get('risk_level'), 'HIGH_CRISIS')

    @patch('app.generate_llm_response')
    def test_16_mocked_gemini_bypass_tier1(self, mock_llm):
        """Confirm Gemini function is called 0 times on Tier 1 high-risk crisis."""
        payload = {"message": "I want to end my life."}
        response = self.client.post('/api/chat', json=payload)
        self.assertEqual(response.status_code, 200)
        mock_llm.assert_not_called()

    @patch('app.generate_llm_response')
    @patch('app.analyze_user_message')
    def test_17_mocked_gemini_bypass_tier2(self, mock_ml, mock_llm):
        """Confirm Gemini function is called 0 times on Tier 2 ML high-risk crisis."""
        mock_ml.return_value = {
            "intent": "SUICIDE CRISIS OR SELF HARM RISK",
            "intent_confidence": 0.95,
            "emotion": "DISTRESS",
            "sentiment": "NEGATIVE",
            "inference_latency_ms": 10.0
        }
        payload = {"message": "Distressing statement triggering ML zero-shot."}
        response = self.client.post('/api/chat', json=payload)
        self.assertEqual(response.status_code, 200)
        mock_llm.assert_not_called()

    def test_18_cors_headers(self):
        """Test CORS headers allow configured origin."""
        response = self.client.options('/api/chat', headers={'Origin': 'http://localhost:5173', 'Access-Control-Request-Method': 'POST'})
        self.assertEqual(response.status_code, 200)

    def test_20_full_account_deletion(self):
        """Test DELETE /api/auth/account permanently purges user profile and data (SRS 2.1.7)."""
        email = f"delaccount_{int(datetime.utcnow().timestamp())}@example.com"
        reg_res = self.client.post('/api/auth/register', json={"name": "Delete User", "email": email, "password": "Password123!"})
        token = reg_res.get_json()['data']['token']

        # Delete Account
        del_res = self.client.delete('/api/auth/account', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.get_json().get('success'))

        # Verify Unauthorized
        me_res = self.client.get('/api/auth/me', headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(me_res.status_code, 401)

    def test_21_trusted_contact_management(self):
        """Test POST /api/user/trusted-contact persists emergency contact (SRS 2.1.4)."""
        email = f"trusteduser_{int(datetime.utcnow().timestamp())}@example.com"
        reg_res = self.client.post('/api/auth/register', json={"name": "Trusted User", "email": email, "password": "Password123!"})
        token = reg_res.get_json()['data']['token']

        payload = {"name": "Dr. Sarah", "phone": "0300-1234567", "relationship": "Counselor"}
        tc_res = self.client.post('/api/user/trusted-contact', json=payload, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(tc_res.status_code, 200)
        self.assertTrue(tc_res.get_json().get('success'))

    def test_22_session_summarization(self):
        """Test POST /api/chat/summarize returns supportive reflection summary (SRS 2.1.2)."""
        email = f"summaryuser_{int(datetime.utcnow().timestamp())}@example.com"
        reg_res = self.client.post('/api/auth/register', json={"name": "Summary User", "email": email, "password": "Password123!"})
        token = reg_res.get_json()['data']['token']

        payload = {
            "messages": [
                {"sender": "user", "text": "I feel stressed about my thesis."},
                {"sender": "bot", "text": "Take it step by step."},
                {"sender": "user", "text": "I tried box breathing and feel a bit calmer now."}
            ]
        }
        sum_res = self.client.post('/api/chat/summarize', json=payload, headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(sum_res.status_code, 200)
        self.assertIn("summary", sum_res.get_json().get('data', {}))


if __name__ == '__main__':
    unittest.main(verbosity=2)
