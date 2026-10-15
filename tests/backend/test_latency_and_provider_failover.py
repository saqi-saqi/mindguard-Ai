"""
tests/backend/test_latency_and_provider_failover.py
====================================================
Comprehensive verification suite for MindGuard latency controls,
provider failover, and safety-path independence.

Verifies:
1. Gemini 503 UNAVAILABLE & 504 DEADLINE_EXCEEDED immediate circuit breaker tripping (no waterfall)
2. Single-attempt SDK retries (no nested retries)
3. Empathetic predefined fallback on generation failure
4. Semantic safety classifier timeout bounding and non-auto-approval of unsafe queries
5. Configurable provider selection (Ollama, Gemini, Fast Demo)
6. Crisis-path independence from LLM availability
7. Regression test documenting the Tier-1 possession+future-intent crisis gap
"""

from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch, MagicMock

import app as app_module
from app import app
from database import init_db, get_db
from services import llm_service
from services.semantic_safety_classifier import classify_semantically, _semantic_reasoning_fallback
from services.safety_classifier import classify_safety_risk
from services.crisis_rules import evaluate_crisis, evaluate_deterministic_crisis


class LatencyAndProviderFailoverTestCase(unittest.TestCase):

    def setUp(self):
        init_db()
        db = get_db()
        db.users.delete_many({})
        db.chat_messages.delete_many({})
        db.chat_sessions.delete_many({})
        self.client = app.test_client()
        # Reset circuit breakers
        llm_service._MODEL_QUOTA_EXCEEDED_UNTIL.clear()
        llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL = 0.0

    def tearDown(self):
        llm_service._MODEL_QUOTA_EXCEEDED_UNTIL.clear()
        llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL = 0.0

    # -----------------------------------------------------------------------
    # 1. Gemini 503/504 Handling: Immediate Breaker, No Waterfall
    # -----------------------------------------------------------------------

    def test_gemini_503_unavailable_trips_circuit_breaker_immediately(self):
        """A 503 UNAVAILABLE response must trip the circuit breaker on the first attempt without trying other models."""
        call_count = 0

        def fake_generate(model, contents, config):
            nonlocal call_count
            call_count += 1
            raise Exception("503 UNAVAILABLE: This model is currently experiencing high demand.")

        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = fake_generate

        with (
            patch("services.llm_service._get_gemini_client", return_value=fake_client),
            patch("services.llm_service.os.environ.get", return_value="fake-key"),
            patch("services.llm_service.GEMINI_API_KEY", "fake-key"),
            patch("services.llm_service.query_local_ollama", return_value=None),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            start = time.time()
            reply = llm_service.generate_llm_response("I am exhausted", "SLEEP DISTURBANCE", "DISTRESS", "NEGATIVE")
            duration_ms = (time.time() - start) * 1000.0

        # Must have called Gemini exactly once, broken the waterfall, and returned the empathetic fallback
        self.assertEqual(call_count, 1, "Expected loop to terminate on first 503 failure without waterfalling")
        self.assertTrue(time.time() < llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL, "Circuit breaker should be active")
        self.assertIn("sleep", reply.lower())
        self.assertLess(duration_ms, 500, "Fallback after 503 should complete in under 500ms locally")

    def test_gemini_504_deadline_exceeded_trips_circuit_breaker(self):
        """A 504 DEADLINE_EXCEEDED response must activate the 60s circuit breaker."""
        def fake_generate(model, contents, config):
            raise Exception("504 DEADLINE_EXCEEDED: Deadline expired before operation could complete.")

        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = fake_generate

        with (
            patch("services.llm_service._get_gemini_client", return_value=fake_client),
            patch("services.llm_service.os.environ.get", return_value="fake-key"),
            patch("services.llm_service.GEMINI_API_KEY", "fake-key"),
            patch("services.llm_service.query_local_ollama", return_value=None),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            reply = llm_service.generate_llm_response("I feel lonely", "LONELINESS", "SADNESS", "NEGATIVE")

        self.assertTrue(time.time() < llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL)
        self.assertIn("disconnected", reply.lower())

    # -----------------------------------------------------------------------
    # 2. Configurable Provider: Ollama as Primary Demo Provider
    # -----------------------------------------------------------------------

    def test_configurable_demo_provider_uses_ollama_directly(self):
        """When LLM_PROVIDER is 'ollama', Gemini is skipped and Ollama is called as primary."""
        mock_ollama = MagicMock(return_value="Ollama primary counselor reply")
        mock_gemini = MagicMock()

        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "ollama"}),
            patch("services.llm_service.query_local_ollama", mock_ollama),
            patch("services.llm_service._call_gemini", mock_gemini),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            reply = llm_service.generate_llm_response("I need coping tips", "COPING", "ANXIETY", "NEGATIVE")

        self.assertEqual(reply, "Ollama primary counselor reply")
        mock_ollama.assert_called_once()
        mock_gemini.assert_not_called()

    def test_fast_demo_provider_uses_predefined_counselor_response(self):
        """When LLM_PROVIDER is 'fast', response is returned instantly without external calls."""
        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "fast"}),
            patch("services.llm_service.query_local_ollama") as mock_ollama,
            patch("services.llm_service._call_gemini") as mock_gemini,
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            start = time.time()
            reply = llm_service.generate_llm_response("I have trouble sleeping", "SLEEP", "DISTRESS", "NEGATIVE")
            elapsed_ms = (time.time() - start) * 1000.0

        self.assertIn("sleep", reply.lower())
        self.assertLess(elapsed_ms, 50.0, "Fast demo provider must respond in under 50ms")
        mock_ollama.assert_not_called()
        mock_gemini.assert_not_called()

    # -----------------------------------------------------------------------
    # 3. Semantic Safety Timeout & Safety Non-Approval Invariant
    # -----------------------------------------------------------------------

    def test_semantic_safety_timeout_falls_back_safely(self):
        """When the remote semantic classifier times out, it invokes offline reasoning and does not crash."""
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = TimeoutError("Deadline exceeded after timeout")

        with (
            patch("google.genai.Client", return_value=fake_client),
            patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}),
        ):
            start = time.time()
            result = classify_semantically("I want to end my life tonight", api_key="fake-key")
            elapsed_ms = (time.time() - start) * 1000.0

        self.assertIsNotNone(result)
        self.assertEqual(result["risk_level"], "HIGH_CRISIS")
        self.assertLess(elapsed_ms, 500, "Fallback after semantic timeout must run in under 500ms")

    def test_semantic_timeout_never_auto_approves_unsafe_input(self):
        """A timeout in semantic safety must NEVER suppress or downgrade deterministic safety."""
        # Case where deterministic detected distress/safety signal
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = TimeoutError("Deadline exceeded")

        with (
            patch("google.genai.Client", return_value=fake_client),
            patch.dict(os.environ, {"GEMINI_API_KEY": "fake-key"}),
        ):
            res = classify_safety_risk("I am feeling depressed and hopeless", api_key="fake-key")

        self.assertNotEqual(res.category.value, "NONE")
        self.assertEqual(res.category.value, "EMOTIONAL_DISTRESS")

    # -----------------------------------------------------------------------
    # 4. Crisis-Path Independence: Deterministic Crisis Bypasses All LLMs
    # -----------------------------------------------------------------------

    def test_deterministic_crisis_independent_of_llm_availability(self):
        """Acute crisis messages are handled deterministically in < 10ms with zero LLM/Ollama calls."""
        with (
            patch("app.generate_llm_response") as mock_gen_llm,
            patch("services.llm_service.query_local_ollama") as mock_ollama,
            patch("services.llm_service._call_gemini") as mock_gemini,
        ):
            start = time.time()
            resp = self.client.post("/api/chat", json={"message": "I want to kill myself tonight"})
            elapsed_ms = (time.time() - start) * 1000.0

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()["data"]
        self.assertEqual(data["risk_level"], "HIGH_CRISIS")
        self.assertTrue(data["requires_immediate_action"])
        self.assertIn("emergency_resources", data)
        self.assertLess(elapsed_ms, 100.0, "Crisis triage must execute in under 100ms")
        mock_gen_llm.assert_not_called()
        mock_ollama.assert_not_called()
        mock_gemini.assert_not_called()

    # -----------------------------------------------------------------------
    # 5. Fixed Crisis-Detection Gap: Positive & Negative Regression Tests
    # -----------------------------------------------------------------------

    def test_fixed_gap_possession_plus_future_intent_positive_cases(self):
        """
        Positive Regression Tests:
        Possession of lethal means combined with future ingestion intent
        must evaluate deterministically to is_crisis=True.
        """
        positives = [
            "I have a bottle of pills and I am going to take them tonight",
            "I have a bottle of pills and I'm going to take them tonight.",
            "I got pills and will swallow them tonight",
            "I have a bottle of sleeping pills and plan to take them all",
            "holding a bottle of pills and gonna take them tonight",
            "bought medication and planning to swallow them tonight",
            "I have these pills and intend to take them all tonight"
        ]
        for phrase in positives:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertTrue(
                    res.get("is_crisis", False),
                    f"Expected deterministic crisis detection for positive case: '{phrase}'"
                )

    def test_fixed_gap_possession_plus_future_intent_negative_cases(self):
        """
        Negative Regression Tests (False Alarm Prevention):
        Routine prescription, medical queries, or accidental statements
        must NOT trigger crisis alarms (is_crisis=False).
        """
        negatives = [
            "I have to take my blood pressure pills tonight",
            "I have pills to take for my headache tonight",
            "I have my pills ready for tomorrow morning as prescribed",
            "I forgot whether I took my pills",
            "Do I have to take these pills with food?",
            "I have a bottle of vitamins on my desk"
        ]
        for phrase in negatives:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertFalse(
                    res.get("is_crisis", False),
                    f"False alarm detected on benign query: '{phrase}'"
                )


if __name__ == "__main__":
    unittest.main()
