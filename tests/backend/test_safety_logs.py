"""
test_safety_logs.py
===================
Test suite for Admin Safety Logs feature:
1. Persistence of correctly-shaped safety_logs documents across Tier 1, 2, and 3.
2. Invariant verification: Real BSON Date timestamps (not ISO strings) and redacted excerpts.
3. Resilience invariant: Logging errors and circuit-breaker activations never block or alter crisis responses.
4. Admin authorization enforcement (401 without token, 403 for regular user, 200 for admin).
5. GET /api/admin/safety-logs pagination, multi-attribute filtering (tier, category, resolved, date range), and stats summary.
6. PATCH /api/admin/safety-logs/:id review resolution and clinical note persistence.
"""

from __future__ import annotations

import os
import sys
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch, MagicMock

os.environ["USE_MONGOMOCK"] = "true"
os.environ["FLASK_ENV"] = "testing"

ROOT_DIR = Path(__file__).resolve().parents[2]
SERVER_DIR = ROOT_DIR / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from app import app
from auth import generate_token, hash_password
from database import (
    init_db,
    get_db,
    log_safety_event,
    get_safety_logs,
    get_safety_log_by_id,
    update_safety_log,
    get_safety_logs_stats,
    reset_safety_log_circuit,
    redact_trigger_message,
)


@pytest.fixture
def client():
    app.config["TESTING"] = True
    reset_safety_log_circuit()
    init_db()
    db = get_db()
    db.users.delete_many({})
    db.safety_logs.delete_many({})
    with app.test_client() as c:
        yield c
    reset_safety_log_circuit()


@pytest.fixture
def user_and_admin_tokens():
    db = get_db()
    # Regular user
    user_id = "usr-testuser123"
    db.users.insert_one({
        "id": user_id,
        "name": "Regular User",
        "email": "user@example.com",
        "password_hash": hash_password("Password123!"),
        "role": "user",
        "created_at": datetime.utcnow().isoformat(),
        "settings": {"retention_enabled": True, "retention_days": 30}
    })
    user_token = generate_token(user_id, "user@example.com")

    # Admin user
    admin_id = "usr-testadmin999"
    db.users.insert_one({
        "id": admin_id,
        "name": "Clinical Admin",
        "email": "admin@example.com",
        "password_hash": hash_password("AdminPass123!"),
        "role": "admin",
        "created_at": datetime.utcnow().isoformat(),
        "settings": {"retention_enabled": True, "retention_days": 30}
    })
    admin_token = generate_token(admin_id, "admin@example.com")

    return {"user_id": user_id, "user_token": user_token, "admin_id": admin_id, "admin_token": admin_token}


# ---------------------------------------------------------------------------
# 1. DATA MODEL & TIER 1, 2, 3 SHAPE VERIFICATION
# ---------------------------------------------------------------------------

def test_tier1_writes_correctly_shaped_safety_log(client):
    """
    Tier 1 crisis utterance to /api/chat must write a document into safety_logs with:
    - Real BSON Date timestamp (datetime object in MongoDB, not ISO string)
    - tier == 1
    - Action taken and category
    - Redacted excerpt (never full raw message)
    - resolved == False
    """
    trigger_text = "I am going to kill myself tonight with pills"
    res = client.post("/api/chat", json={"message": trigger_text, "session_id": "ses-unit-t1"})
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert data["risk_level"] == "HIGH_CRISIS"
    assert data["requires_immediate_action"] is True

    db = get_db()
    logs = list(db.safety_logs.find({"session_id": "ses-unit-t1"}))
    assert len(logs) == 1
    doc = logs[0]

    # Verify BSON Date requirement: timestamp MUST be a datetime instance
    assert isinstance(doc["timestamp"], datetime), "Timestamp must be a real BSON Date (datetime object), not str"
    assert doc["tier"] == 1
    assert doc["category"] == "self-harm"
    assert "hotline_shown" in doc["action_taken"]
    assert doc["resolved"] is False
    assert doc["reviewed"] is False
    assert doc["admin_note"] == ""
    # Redacted excerpt verification: must NOT contain sensitive words or full raw text
    assert "[REDACTED]" in doc["message_excerpt"]
    assert "kill" not in doc["message_excerpt"].lower()
    assert "[hash:" in doc["message_excerpt"]
    assert doc["message_hash"] != ""


def test_tier2_ml_writes_correctly_shaped_safety_log(client):
    """
    Tier 2 ML classification flag writes a document with tier=2, ML model identifier, and confidence score.
    """
    # Mock ML results to trigger Tier 2 without depending on heavy torch weights
    with patch("app.analyze_user_message") as mock_ml:
        mock_ml.return_value = {
            "intent": "SUICIDE CRISIS OR SELF HARM RISK",
            "intent_confidence": 0.89,
            "emotion": "DISTRESS",
            "sentiment": "NEGATIVE"
        }
        res = client.post("/api/chat", json={"message": "i am in so much despair and darkness", "session_id": "ses-unit-t2"})
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["risk_level"] == "HIGH_CRISIS"

    db = get_db()
    logs = list(db.safety_logs.find({"session_id": "ses-unit-t2"}))
    assert len(logs) >= 1
    doc = logs[0]
    assert isinstance(doc["timestamp"], datetime)
    assert doc["tier"] == 2
    assert "crisis_detector" in doc["rule_or_model"] or "ml" in doc["rule_or_model"]
    assert doc["confidence"] == pytest.approx(0.89, rel=1e-2)
    assert doc["resolved"] is False


def test_tier3_llm_verifier_writes_correctly_shaped_safety_log(client):
    """
    Tier 3 LLM verification flag writes a document with tier=3, LLM guardrail identifier, and confidence score.
    """
    with patch("app.analyze_user_message") as mock_ml, \
         patch("app.evaluate_llm_safety_guardrail") as mock_llm:
        # Borderline ML confidence (0.65) triggers Tier 2.5/3 verifier
        mock_ml.return_value = {
            "intent": "SUICIDE CRISIS OR SELF HARM RISK",
            "intent_confidence": 0.65,
            "emotion": "DISTRESS",
            "sentiment": "NEGATIVE"
        }
        mock_llm.return_value = {
            "is_crisis": True,
            "category": "self-harm",
            "confidence": 0.94,
            "reasoning": "Explicit self-harm intent confirmed upon verification"
        }

        res = client.post("/api/chat", json={"message": "i have thought of leaving this world", "session_id": "ses-unit-t3"})
        assert res.status_code == 200
        data = res.get_json()["data"]
        assert data["risk_level"] == "HIGH_CRISIS"

    db = get_db()
    logs = list(db.safety_logs.find({"session_id": "ses-unit-t3"}))
    assert len(logs) >= 1
    doc = logs[0]
    assert isinstance(doc["timestamp"], datetime)
    assert doc["tier"] == 3
    assert doc["rule_or_model"] == "gemini_llm_guardrail"
    assert doc["category"] == "self-harm"
    assert doc["confidence"] == pytest.approx(0.94, rel=1e-2)


def test_guest_user_id_is_anonymously_hashed(client):
    """
    When a guest chats (no JWT user_id), safety_logs must store an anonymized/hashed reference,
    never None or exposing raw unhashed identity.
    """
    res = client.post("/api/chat", json={"message": "I want to kill myself right now", "session_id": "ses-guest-99"})
    assert res.status_code == 200

    db = get_db()
    doc = db.safety_logs.find_one({"session_id": "ses-guest-99"})
    assert doc is not None
    assert doc["is_guest"] is True
    assert doc["user_id"].startswith("guest-")
    assert len(doc["user_id"]) > 10


# ---------------------------------------------------------------------------
# 2. RESILIENCE: LOGGING FAILURE NEVER SUPPRESSES CRISIS RESPONSE
# ---------------------------------------------------------------------------

def test_logging_failure_does_not_block_or_alter_crisis_response(client):
    """
    Fail-closed architectural invariant:
    If writing to the safety_logs collection fails or raises a database error,
    the crisis response MUST NOT be suppressed, delayed, or altered in any way.
    """
    # Force the collection insert to throw an unhandled database exception
    with patch.object(get_db().safety_logs, "insert_one", side_effect=Exception("MongoDB disk full / network partition")):
        res = client.post("/api/chat", json={"message": "I will kill myself today", "session_id": "ses-fault-test"})
        # Safety triage must succeed completely with 200 and standard crisis response
        assert res.status_code == 200
        json_data = res.get_json()
        assert "1122" in json_data["data"]["reply"]
        assert "Emergency Services" in json_data["data"]["reply"]


# ---------------------------------------------------------------------------
# 3. ADMIN AUTHENTICATION ENFORCEMENT (401 / 403 / 200)
# ---------------------------------------------------------------------------

def test_admin_auth_enforced_on_get_safety_logs(client, user_and_admin_tokens):
    """
    GET /api/admin/safety-logs:
    - 401 when no token or invalid token
    - 403 when authenticated as a non-admin user
    - 200 when authenticated as an admin user
    """
    # 1. No token -> 401
    no_auth = client.get("/api/admin/safety-logs")
    assert no_auth.status_code == 401
    assert no_auth.get_json()["error"]["code"] == "UNAUTHORIZED"

    # 2. Non-admin user -> 403
    user_auth = client.get(
        "/api/admin/safety-logs",
        headers={"Authorization": f"Bearer {user_and_admin_tokens['user_token']}"}
    )
    assert user_auth.status_code == 403
    assert user_auth.get_json()["error"]["code"] == "FORBIDDEN"

    # 3. Admin user -> 200
    admin_auth = client.get(
        "/api/admin/safety-logs",
        headers={"Authorization": f"Bearer {user_and_admin_tokens['admin_token']}"}
    )
    assert admin_auth.status_code == 200
    assert admin_auth.get_json()["success"] is True


def test_admin_auth_enforced_on_patch_safety_logs(client, user_and_admin_tokens):
    """
    PATCH /api/admin/safety-logs/:id:
    - 401 when unauthenticated
    - 403 when non-admin user
    - 200 when admin
    """
    # Seed a log entry directly
    doc = log_safety_event(
        tier=1,
        rule_or_model="test_regex",
        category="self-harm",
        action_taken="hotline_shown",
        message="test suicide utterance",
        session_id="ses-patch-auth"
    )
    log_id = doc["id"]

    # 1. Unauthenticated -> 401
    no_auth = client.patch(f"/api/admin/safety-logs/{log_id}", json={"resolved": True})
    assert no_auth.status_code == 401

    # 2. Regular user -> 403
    user_auth = client.patch(
        f"/api/admin/safety-logs/{log_id}",
        json={"resolved": True},
        headers={"Authorization": f"Bearer {user_and_admin_tokens['user_token']}"}
    )
    assert user_auth.status_code == 403

    # 3. Admin user -> 200
    admin_auth = client.patch(
        f"/api/admin/safety-logs/{log_id}",
        json={"resolved": True, "admin_note": "Clinician reviewed, user safe."},
        headers={"Authorization": f"Bearer {user_and_admin_tokens['admin_token']}"}
    )
    assert admin_auth.status_code == 200
    assert admin_auth.get_json()["data"]["resolved"] is True
    assert admin_auth.get_json()["data"]["admin_note"] == "Clinician reviewed, user safe."


# ---------------------------------------------------------------------------
# 4. PAGINATION AND MULTI-ATTRIBUTE FILTERING
# ---------------------------------------------------------------------------

def test_get_safety_logs_pagination_and_filtering(client, user_and_admin_tokens):
    """
    Verifies pagination (page, limit, total_pages) and filters:
    - tier (1, 2, 3)
    - category
    - resolved status (true/false)
    - date range ($gte, $lte)
    """
    auth_header = {"Authorization": f"Bearer {user_and_admin_tokens['admin_token']}"}
    db = get_db()
    now = datetime.now(timezone.utc)

    # Seed 10 documents with different tiers, categories, resolved statuses, and dates
    # 5 Tier 1 self-harm (unresolved)
    for i in range(5):
        log_safety_event(
            tier=1,
            rule_or_model="regex_suicide",
            category="self-harm",
            action_taken="hotline_shown",
            message=f"I want to die utterance {i}",
            session_id=f"ses-filter-{i}"
        )

    # 3 Tier 2 homicide/threat-to-others (resolved)
    for i in range(5, 8):
        created = log_safety_event(
            tier=2,
            rule_or_model="threat_detector",
            category="homicide/threat-to-others",
            action_taken="escalated",
            message=f"I will attack them {i}",
            session_id=f"ses-filter-{i}"
        )
        update_safety_log(created["id"], {"resolved": True, "admin_note": f"Reviewed {i}"})

    # 2 Tier 3 reported-threat-to-user (unresolved, older timestamp)
    for i in range(8, 10):
        doc = log_safety_event(
            tier=3,
            rule_or_model="gemini_llm_guardrail",
            category="reported-threat-to-user",
            action_taken="guidance_shown",
            message=f"My friend threatened me {i}",
            session_id=f"ses-filter-{i}"
        )
        # Shift timestamp back 10 days
        db.safety_logs.update_one({"id": doc["id"]}, {"$set": {"timestamp": now - timedelta(days=10)}})

    # 1. Total count check
    res_all = client.get("/api/admin/safety-logs", headers=auth_header)
    data_all = res_all.get_json()["data"]
    assert data_all["total"] == 10

    # 2. Filter by Tier 1
    res_t1 = client.get("/api/admin/safety-logs?tier=1", headers=auth_header)
    data_t1 = res_t1.get_json()["data"]
    assert data_t1["total"] == 5
    assert all(item["tier"] == 1 for item in data_t1["logs"])

    # 3. Filter by Category homicide/threat-to-others
    res_cat = client.get("/api/admin/safety-logs?category=homicide/threat-to-others", headers=auth_header)
    data_cat = res_cat.get_json()["data"]
    assert data_cat["total"] == 3
    assert all(item["category"] == "homicide/threat-to-others" for item in data_cat["logs"])

    # 4. Filter by resolved status
    res_unres = client.get("/api/admin/safety-logs?resolved=false", headers=auth_header)
    assert res_unres.get_json()["data"]["total"] == 7

    res_res = client.get("/api/admin/safety-logs?resolved=true", headers=auth_header)
    assert res_res.get_json()["data"]["total"] == 3

    # 5. Date range filtering (last 2 days only -> excludes the 10-day old tier 3 logs)
    two_days_ago = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    res_date = client.get(f"/api/admin/safety-logs?start_date={two_days_ago}&end_date={tomorrow}", headers=auth_header)
    data_date = res_date.get_json()["data"]
    assert data_date["total"] == 8

    # 6. Pagination check (page 1, limit 3)
    res_page1 = client.get("/api/admin/safety-logs?page=1&limit=3", headers=auth_header)
    p1 = res_page1.get_json()["data"]
    assert len(p1["logs"]) == 3
    assert p1["page"] == 1
    assert p1["limit"] == 3
    assert p1["total_pages"] == 4

    # Page 2
    res_page2 = client.get("/api/admin/safety-logs?page=2&limit=3", headers=auth_header)
    p2 = res_page2.get_json()["data"]
    assert len(p2["logs"]) == 3
    assert p2["page"] == 2
    # Ensure page 1 and page 2 items are different
    p1_ids = {item["id"] for item in p1["logs"]}
    p2_ids = {item["id"] for item in p2["logs"]}
    assert p1_ids.isdisjoint(p2_ids)

    # 7. Dashboard header summary stats
    stats = p1["stats"]
    assert stats["total_flags"] == 10
    assert stats["unresolved_count"] == 7
    assert stats["resolved_count"] == 3
    assert stats["last_7_days"]["tier_1"] == 5
    assert stats["last_7_days"]["tier_2"] == 3
    assert stats["last_30_days"]["total"] == 10


def test_patch_safety_log_not_found(client, user_and_admin_tokens):
    """PATCH with non-existent id returns 404."""
    auth_header = {"Authorization": f"Bearer {user_and_admin_tokens['admin_token']}"}
    res = client.patch("/api/admin/safety-logs/safe-nonexistent999", json={"resolved": True}, headers=auth_header)
    assert res.status_code == 404
    assert res.get_json()["error"]["code"] == "NOT_FOUND"


def test_redact_trigger_message_privacy():
    """Verify that redact_trigger_message masks lethal and self-harm keywords and truncates safely."""
    raw = "I want to commit suicide by overdose of poison pills and die tonight"
    redacted = redact_trigger_message(raw)
    assert "[REDACTED]" in redacted
    assert "suicide" not in redacted.lower()
    assert "overdose" not in redacted.lower()
    assert "die" not in redacted.lower()
    assert "[hash:" in redacted
