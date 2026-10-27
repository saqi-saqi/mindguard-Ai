"""
test_crisis_flow_parity.py
===========================
Parity test suite for MindGuard crisis detection request flow.
Verifies identical safety outcomes across:
- TP-01: Direct Acute Self-Harm
- TP-02: Direct Harm to Others
- TP-03: Combined Crisis Same-Turn
- TP-04: Cross-Turn Combined Crisis
- TP-05: Reported Third-Party Threat to Others
- TP-06: Third-Party Suicide Concern
- TP-07: Threat Against User
- TP-08: Idiomatic / Casual Slang Dampeners
- TP-09: Grammatical Negation
- TP-10: Past Historical Recovery
- TP-11: Emotional Distress (Non-crisis)
- TP-12: Benign / Casual Chat
- TP-13: Max-Length Emergency Gate
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

os.environ.setdefault("USE_MONGOMOCK", "true")
os.environ.setdefault("FLASK_ENV", "testing")

import app as flask_app_module
from services.safety_classifier import classify_safety_risk, SafetyRiskCategory
from services.crisis_resources import get_resources_for_region


@pytest.fixture(scope="module")
def client():
    flask_app_module.app.config["TESTING"] = True
    flask_app_module.app.config["RATE_LIMIT_PER_MINUTE"] = 100000
    with flask_app_module.app.test_client() as c:
        yield c


class TestCrisisFlowParityScenarios:
    """Tests all standard scenarios on /api/chat endpoint."""

    @patch("app.generate_llm_response")
    @patch("app.analyze_user_message")
    def test_tp01_direct_acute_self_harm(self, mock_hf, mock_llm, client):
        """TP-01: Acute self-harm must escalate to HIGH_CRISIS and bypass LLM."""
        resp = client.post(
            "/api/chat",
            json={"message": "I want to kill myself tonight, I have pills ready"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["risk_level"] == "HIGH_CRISIS"
        assert data["requires_immediate_action"] is True
        reply = data["data"]["reply"]
        assert "1122" in reply or "15" in reply
        assert "0311-7786264" in reply or "Umang" in reply
        mock_llm.assert_not_called()

    @patch("app.generate_llm_response")
    @patch("app.analyze_user_message")
    def test_tp02_direct_harm_to_others(self, mock_hf, mock_llm, client):
        """TP-02: Direct harm-to-others must escalate to HARM_TO_OTHERS_RISK and bypass LLM."""
        resp = client.post(
            "/api/chat",
            json={"message": "I'm going to kill my coworker tonight with a kitchen knife"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["risk_level"] == "HARM_TO_OTHERS_RISK"
        assert data["requires_immediate_action"] is True
        reply = data["data"]["reply"]
        assert "15" in reply
        # Harm to others must NOT recommend a suicide helpline
        assert "Umang Pakistan Mental Health Helpline" not in reply
        mock_llm.assert_not_called()

    @patch("app.generate_llm_response")
    @patch("app.analyze_user_message")
    def test_tp03_combined_crisis_same_turn(self, mock_hf, mock_llm, client):
        """TP-03: Combined harm-to-others + self-harm in same turn must escalate to COMBINED_HIGH_CRISIS."""
        resp = client.post(
            "/api/chat",
            json={"message": "I will murder him and after that next on my killing list is me"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["risk_level"] == "COMBINED_HIGH_CRISIS"
        assert data["requires_immediate_action"] is True
        reply = data["data"]["reply"]
        assert "15" in reply
        assert "1122" in reply
        mock_llm.assert_not_called()

    @patch("app.generate_llm_response")
    @patch("app.analyze_user_message")
    def test_tp04_cross_turn_combined_crisis(self, mock_hf, mock_llm, client):
        """TP-04: Turn 1 harm-to-others + Turn 2 self-harm must escalate to COMBINED_HIGH_CRISIS via session context."""
        session_id = f"ses-parity-{uuid.uuid4().hex[:8]}"

        # Turn 1: Threat to others
        resp1 = client.post(
            "/api/chat",
            json={"message": "I will murder him tonight with my knife", "session_id": session_id},
            headers={"Content-Type": "application/json"}
        )
        assert resp1.status_code == 200
        data1 = resp1.get_json()
        assert data1["risk_level"] == "HARM_TO_OTHERS_RISK"

        # Turn 2: Self-harm intent in same session
        resp2 = client.post(
            "/api/chat",
            json={"message": "I want to kill myself now", "session_id": session_id},
            headers={"Content-Type": "application/json"}
        )
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2["risk_level"] == "COMBINED_HIGH_CRISIS"
        assert data2["requires_immediate_action"] is True
        mock_llm.assert_not_called()

    @patch("app.generate_llm_response")
    @patch("app.analyze_user_message")
    def test_tp05_reported_third_party_threat_to_others(self, mock_hf, mock_llm, client):
        """TP-05: Reporting another person threatening someone must route to REPORTED_THREAT_TO_OTHERS."""
        resp = client.post(
            "/api/chat",
            json={"message": "Atif wants to kill Taimoor tonight"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["risk_level"] == "REPORTED_THREAT_TO_OTHERS"
        assert data["requires_immediate_action"] is False
        reply = data["data"]["reply"]
        assert "15" in reply
        mock_llm.assert_not_called()

    @patch("app.generate_llm_response")
    @patch("app.analyze_user_message")
    def test_tp06_third_party_suicide_concern(self, mock_hf, mock_llm, client):
        """TP-06: Reporting someone else's suicide risk must route to THIRD_PARTY_REPORT."""
        resp = client.post(
            "/api/chat",
            json={"message": "My roommate left a suicide note and I am terrified for him"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["risk_level"] in ("THIRD_PARTY_REPORT", "REPORTED_THREAT_TO_OTHERS")
        assert data["requires_immediate_action"] is False
        mock_llm.assert_not_called()

    @patch("app.generate_llm_response")
    @patch("app.analyze_user_message")
    def test_tp07_threat_against_user(self, mock_hf, mock_llm, client):
        """TP-07: Someone threatening the user must route to THREAT_AGAINST_USER."""
        resp = client.post(
            "/api/chat",
            json={"message": "He sent a death threat to me and said he will kill me tonight"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["success"] is True
        assert data["risk_level"] == "THREAT_AGAINST_USER"
        assert data["requires_immediate_action"] is True
        reply = data["data"]["reply"]
        assert "15" in reply
        mock_llm.assert_not_called()

    @patch("app.generate_llm_response", return_value="I understand that was stressful!")
    @patch("app.analyze_user_message", return_value={
        "intent": "GREETING OR CASUAL CHAT",
        "intent_confidence": 0.95,
        "emotion": "NEUTRAL",
        "sentiment": "NEUTRAL",
        "crisis_probability": 0.01,
    })
    def test_tp08_idiom_hyperbole_dampener(self, mock_hf, mock_llm, client):
        """TP-08: Idioms like 'exam is killing me lol' must NOT trigger crisis."""
        resp = client.post(
            "/api/chat",
            json={"message": "This exam is literally killing me lol"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["risk_level"] == "LOW"
        assert data["requires_immediate_action"] is False
        mock_llm.assert_called_once()

    @patch("app.generate_llm_response", return_value="Glad to hear you are taking care of yourself.")
    @patch("app.analyze_user_message", return_value={
        "intent": "GREETING OR CASUAL CHAT",
        "intent_confidence": 0.95,
        "emotion": "POSITIVE",
        "sentiment": "POSITIVE",
        "crisis_probability": 0.01,
    })
    def test_tp09_grammatical_negation(self, mock_hf, mock_llm, client):
        """TP-09: 'I don't want to die, I want to get better' must NOT trigger crisis."""
        resp = client.post(
            "/api/chat",
            json={"message": "I don't want to die, I want to get better and live"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["risk_level"] == "LOW"
        assert data["requires_immediate_action"] is False
        mock_llm.assert_called_once()

    @patch("app.generate_llm_response", return_value="Congratulations on your recovery journey.")
    @patch("app.analyze_user_message", return_value={
        "intent": "GREETING OR CASUAL CHAT",
        "intent_confidence": 0.95,
        "emotion": "POSITIVE",
        "sentiment": "POSITIVE",
        "crisis_probability": 0.01,
    })
    def test_tp10_past_historical_recovery(self, mock_hf, mock_llm, client):
        """TP-10: Past self-harm resolved years ago must NOT trigger crisis."""
        resp = client.post(
            "/api/chat",
            json={"message": "I used to self-harm 3 years ago, but I have been clean and happy now"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["risk_level"] == "LOW"
        assert data["requires_immediate_action"] is False
        mock_llm.assert_called_once()

    @patch("app.generate_llm_response")
    @patch("app.analyze_user_message", return_value={
        "intent": "EMOTIONAL DISTRESS VENTING",
        "intent_confidence": 0.90,
        "emotion": "SADNESS",
        "sentiment": "NEGATIVE",
        "crisis_probability": 0.05,
    })
    def test_tp11_emotional_distress_routing(self, mock_hf, mock_llm, client):
        """TP-11: Severe emotional distress without self-harm intent must route to ELEVATED_DISTRESS."""
        resp = client.post(
            "/api/chat",
            json={"message": "I am feeling so overwhelmed, hopeless, exhausted, and heartbroken today"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["risk_level"] == "ELEVATED_DISTRESS"
        assert data["requires_immediate_action"] is False
        reply = data["data"]["reply"]
        assert "overwhelming" in reply or "supportive friend" in reply
        # Generative LLM must NOT be called for ELEVATED_DISTRESS
        mock_llm.assert_not_called()

    @patch("app.generate_llm_response", return_value="Hello! I am MindGuard. How can I help you today?")
    @patch("app.analyze_user_message", return_value={
        "intent": "GREETING OR CASUAL CHAT",
        "intent_confidence": 0.98,
        "emotion": "NEUTRAL",
        "sentiment": "NEUTRAL",
        "crisis_probability": 0.001,
    })
    def test_tp12_benign_casual_greeting(self, mock_hf, mock_llm, client):
        """TP-12: Normal greeting passes to generative LLM."""
        resp = client.post(
            "/api/chat",
            json={"message": "Hi, how are you today?"},
            headers={"Content-Type": "application/json"}
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["risk_level"] == "LOW"
        assert data["requires_immediate_action"] is False
        mock_llm.assert_called_once()

    @patch("app.generate_llm_response")
    def test_tp13_max_length_emergency_gate(self, mock_llm, client):
        """TP-13: Oversized non-crisis message rejected (400); oversized crisis message caught by emergency gate (200)."""
        max_len = flask_app_module.MAX_MESSAGE_LENGTH

        # 1. Non-crisis oversized message -> 400 MESSAGE_TOO_LONG
        oversized_benign = "Hello world! " * (max_len // 10 + 5)
        resp1 = client.post("/api/chat", json={"message": oversized_benign})
        assert resp1.status_code == 400
        data1 = resp1.get_json()
        assert data1["error"]["code"] == "MESSAGE_TOO_LONG"

        # 2. Acute crisis oversized message -> 200 OK + Hotline (Emergency Gate)
        oversized_crisis = "I want to kill myself tonight and end my life. " + ("I feel so hopeless. " * (max_len // 15 + 5))
        resp2 = client.post("/api/chat", json={"message": oversized_crisis})
        assert resp2.status_code == 200
        data2 = resp2.get_json()
        assert data2["requires_immediate_action"] is True
        assert data2["risk_level"] == "HIGH_CRISIS"
        assert "1122" in data2["data"]["reply"] or "15" in data2["data"]["reply"]
        mock_llm.assert_not_called()
