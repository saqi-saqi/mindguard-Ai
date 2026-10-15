"""
tests/backend/test_groq_provider.py
===================================
Tests for Groq API provider integration in MindGuard AI.
Verifies:
1. Groq primary generation path under normal operations
2. Deterministic crisis independence (crisis messages bypass Groq entirely)
3. Safe offline fallback on simulated HTTP 429, 500, timeouts, invalid JSON, and missing keys
4. Enforces Requirement 6: No slow Ollama fallback when Groq fails/expires
5. Semantic safety classifier does not invoke remote Gemini when LLM_PROVIDER=groq
6. Streaming token generation helper
"""

import os
import time
import unittest
from unittest.mock import patch, MagicMock
import requests

import app as app_module
from app import app
from database import init_db, get_db
from services import llm_service
from services.safety_classifier import classify_safety_risk
from services.semantic_safety_classifier import classify_semantically


class GroqProviderTestCase(unittest.TestCase):

    def setUp(self):
        init_db()
        db = get_db()
        db.users.delete_many({})
        db.chat_messages.delete_many({})
        db.chat_sessions.delete_many({})
        self.client = app.test_client()

    def test_groq_primary_provider_called_when_configured(self):
        """When LLM_PROVIDER is 'groq', query_groq is called and Gemini/Ollama are not."""
        mock_groq = MagicMock(return_value="Supportive Groq response.")
        mock_gemini = MagicMock()
        mock_ollama = MagicMock()

        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test_key"}),
            patch("services.llm_service.query_groq", mock_groq),
            patch("services.llm_service._call_gemini", mock_gemini),
            patch("services.llm_service.query_local_ollama", mock_ollama),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            reply = llm_service.generate_llm_response("I feel anxious", "ANXIETY", "ANXIETY", "NEGATIVE")

        self.assertEqual(reply, "Supportive Groq response.")
        mock_groq.assert_called_once()
        mock_gemini.assert_not_called()
        mock_ollama.assert_not_called()

    def test_groq_timeout_falls_back_to_safe_kb_without_slow_ollama(self):
        """When Groq times out, it must fall back to instant safe KB and NOT call slow Ollama."""
        mock_ollama = MagicMock(return_value="Slow Ollama reply")

        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test_key"}),
            patch.object(llm_service._GROQ_SESSION, "post", side_effect=requests.exceptions.Timeout("Read timeout")),
            patch("services.llm_service.query_local_ollama", mock_ollama),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            start = time.time()
            reply = llm_service.generate_llm_response("I have trouble sleeping", "SLEEP", "DISTRESS", "NEGATIVE")
            elapsed_ms = (time.time() - start) * 1000.0

        self.assertIn("sleep", reply.lower())
        self.assertLess(elapsed_ms, 50.0, "Fallback must return in under 50ms")
        # Critical Requirement 6: Ollama must NOT be invoked
        mock_ollama.assert_not_called()

    def test_groq_http_429_rate_limit_fallback(self):
        """When Groq returns HTTP 429, safe fallback is returned immediately."""
        fake_429 = MagicMock()
        fake_429.status_code = 429
        fake_429.text = '{"error": {"message": "Rate limit exceeded"}}'

        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test_key"}),
            patch.object(llm_service._GROQ_SESSION, "post", return_value=fake_429),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            reply = llm_service.generate_llm_response("I feel sad today", "SADNESS", "SADNESS", "NEGATIVE")

        self.assertTrue(len(reply) > 20)
        self.assertTrue(any(w in reply.lower() for w in ["valid", "listening", "alone", "care", "feel"]))

    def test_groq_http_500_server_error_fallback(self):
        """When Groq returns HTTP 500, safe fallback is returned immediately."""
        fake_500 = MagicMock()
        fake_500.status_code = 500
        fake_500.text = '{"error": {"message": "Internal Server Error"}}'

        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test_key"}),
            patch.object(llm_service._GROQ_SESSION, "post", return_value=fake_500),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            reply = llm_service.generate_llm_response("I feel angry and upset", "ANGER", "ANGER", "NEGATIVE")

        self.assertTrue(len(reply) > 20)
        self.assertTrue(any(w in reply.lower() for w in ["anger", "angry", "valid", "breathe", "listening"]))

    def test_groq_missing_api_key_returns_safe_fallback(self):
        """When GROQ_API_KEY is missing or empty, safe fallback is returned instantly."""
        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": ""}),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            start = time.time()
            reply = llm_service.generate_llm_response("I feel anxious", "ANXIETY", "ANXIETY", "NEGATIVE")
            elapsed_ms = (time.time() - start) * 1000.0

        self.assertTrue(len(reply) > 20)
        self.assertLess(elapsed_ms, 50.0)

    def test_groq_invalid_empty_json_response_fallback(self):
        """When Groq returns invalid JSON or empty choices, safe fallback is returned."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"choices": []}

        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test_key"}),
            patch.object(llm_service._GROQ_SESSION, "post", return_value=fake_resp),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            reply = llm_service.generate_llm_response("I feel lonely", "LONELINESS", "LONELINESS", "NEGATIVE")

        self.assertTrue(len(reply) > 20)
        self.assertTrue(any(w in reply.lower() for w in ["disconnected", "alone", "valid", "with you"]))

    def test_groq_crisis_bypasses_all_llms(self):
        """Crisis inputs must immediately bypass Groq and return deterministic emergency resources."""
        mock_groq = MagicMock()

        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "groq", "GROQ_API_KEY": "gsk_test_key"}),
            patch("services.llm_service.query_groq", mock_groq),
        ):
            resp = self.client.post("/api/chat", json={"message": "I want to kill myself tonight"})

        self.assertEqual(resp.status_code, 200)
        data = resp.get_json()
        self.assertEqual(data.get("risk_level"), "HIGH_CRISIS")
        self.assertTrue(data.get("requires_immediate_action"))
        # Crisis messages MUST NEVER invoke Groq
        mock_groq.assert_not_called()

    def test_semantic_classifier_does_not_call_gemini_when_groq_configured(self):
        """When LLM_PROVIDER=groq, semantic_safety_classifier uses offline fallback without remote Gemini."""
        with (
            patch.dict(os.environ, {"LLM_PROVIDER": "groq"}),
            patch("google.genai.Client") as mock_client,
        ):
            res = classify_semantically("I feel like giving up on school")

        self.assertIsNotNone(res)
        self.assertEqual(res["risk_level"], "NONE")
        # Google GenAI client must NOT be initialized for semantic safety
        mock_client.assert_not_called()

    def test_groq_streaming_generator_yields_tokens(self):
        """query_groq_stream yields delta tokens and timing."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.iter_lines.return_value = [
            b'data: {"choices": [{"delta": {"content": "Hello"}}]}',
            b'data: {"choices": [{"delta": {"content": " there"}}]}',
            b'data: [DONE]',
        ]

        with (
            patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test_key"}),
            patch.object(llm_service._GROQ_SESSION, "post", return_value=fake_resp),
        ):
            tokens = list(llm_service.query_groq_stream("hi", "GREETING", "NEUTRAL", "NEUTRAL"))

        self.assertEqual(len(tokens), 2)
        self.assertEqual(tokens[0][0], "Hello")
        self.assertEqual(tokens[1][0], " there")
