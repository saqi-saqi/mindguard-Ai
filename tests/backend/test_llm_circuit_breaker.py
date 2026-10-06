"""
test_llm_circuit_breaker.py
===========================
Task 4 Tests: Gemini connectivity circuit breaker.

Verifies that:
1. A ConnectionError on the first Gemini model activates the module-level
   circuit breaker and causes the model loop to break immediately — without
   trying all remaining candidate models.
2. While the circuit breaker is active, generate_llm_response skips Gemini
   entirely and falls through to Ollama / offline KB.
3. Once the circuit breaker expires, Gemini calls are retried normally.
4. Quota errors (429/resource_exhausted) continue to use the existing
   per-model circuit breaker and do NOT activate the module-level breaker.
5. A healthy Gemini call succeeds normally (no regression).

These tests use unittest.mock.patch to avoid any real network calls.
"""

from __future__ import annotations

import sys
import time
import types as stdlib_types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

import services.llm_service as llm_service
from services.llm_service import (
    _call_gemini,
    generate_llm_response,
    GEMINI_CANDIDATE_MODELS,
    _GeminiConnectivityError,
)


def _reset_breakers():
    """Reset all circuit breakers to a clean state before each test."""
    llm_service._MODEL_QUOTA_EXCEEDED_UNTIL.clear()
    llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL = 0.0


class TestGeminiConnectivityCircuitBreaker(unittest.TestCase):

    def setUp(self):
        _reset_breakers()

    def tearDown(self):
        _reset_breakers()

    # -----------------------------------------------------------------------
    # 1. _call_gemini raises _GeminiConnectivityError on connection failures
    # -----------------------------------------------------------------------

    def test_connection_error_raises_sentinel_and_sets_breaker(self):
        """
        A ConnectionError inside _call_gemini must:
        - Raise _GeminiConnectivityError (so the model loop breaks immediately)
        - Set _GEMINI_CONNECTIVITY_BROKEN_UNTIL ~60 s in the future
        """
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = ConnectionError("connection refused")

        with self.assertRaises(_GeminiConnectivityError):
            _call_gemini(fake_client, "gemini-3.1-flash-lite", "sys", "user")

        self.assertGreater(
            llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL,
            time.time() + 50,
            "Connectivity circuit breaker should be active for ~60 s after ConnectionError"
        )

    def test_permission_denied_error_sets_breaker(self):
        """A 'permission_denied' API error is treated as a connectivity/config failure."""
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = Exception("PERMISSION_DENIED: API key invalid")

        with self.assertRaises(_GeminiConnectivityError):
            _call_gemini(fake_client, "gemini-3.1-flash-lite", "sys", "user")

        self.assertGreater(llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL, time.time() + 50)

    def test_quota_error_does_not_set_module_breaker(self):
        """
        A quota/429 error must NOT activate the module-level connectivity breaker —
        only the per-model quota breaker. This preserves the existing quota behaviour.
        """
        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = Exception("429 resource_exhausted quota exceeded")

        result = _call_gemini(fake_client, "gemini-3.1-flash-lite", "sys", "user")

        self.assertIsNone(result)
        # Per-model quota breaker should be set
        self.assertGreater(
            llm_service._MODEL_QUOTA_EXCEEDED_UNTIL.get("gemini-3.1-flash-lite", 0),
            time.time() + 50,
        )
        # Module-level connectivity breaker must NOT be set
        self.assertEqual(
            llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL, 0.0,
            "Quota errors must not activate the module-level connectivity breaker"
        )

    # -----------------------------------------------------------------------
    # 2. generate_llm_response breaks model loop on first connectivity error
    # -----------------------------------------------------------------------

    def test_model_loop_breaks_on_first_connectivity_error(self):
        """
        When the first candidate model raises a ConnectionError, the model loop
        must break immediately. No subsequent candidate models should be called.

        This prevents the ~1.5 s timeout from being applied N times serially.
        """
        call_count = 0

        def fake_generate(model, contents, config):
            nonlocal call_count
            call_count += 1
            raise ConnectionError("connection refused")

        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = fake_generate

        with (
            patch("services.llm_service._get_gemini_client", return_value=fake_client),
            patch("services.llm_service.os.environ.get", return_value="fake-key"),
            patch("services.llm_service.GEMINI_API_KEY", "fake-key"),
            patch("services.llm_service.query_local_ollama", return_value=None),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            _reset_breakers()
            generate_llm_response("I feel sad", "SADNESS", "SADNESS", "NEGATIVE")

        self.assertEqual(
            call_count, 1,
            f"Expected exactly 1 Gemini call (loop break on first connectivity error), "
            f"but got {call_count} calls across {len(GEMINI_CANDIDATE_MODELS)} candidate models"
        )

    def test_circuit_breaker_skips_all_models_on_subsequent_requests(self):
        """
        After a connectivity failure activates the breaker, the next request
        must skip Gemini entirely (0 calls) and go straight to offline fallback.
        """
        # Pre-activate the circuit breaker
        llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL = time.time() + 55.0

        fake_client = MagicMock()

        with (
            patch("services.llm_service._get_gemini_client", return_value=fake_client),
            patch("services.llm_service.os.environ.get", return_value="fake-key"),
            patch("services.llm_service.GEMINI_API_KEY", "fake-key"),
            patch("services.llm_service.query_local_ollama", return_value=None),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            generate_llm_response("I feel sad", "SADNESS", "SADNESS", "NEGATIVE")

        fake_client.models.generate_content.assert_not_called()

    # -----------------------------------------------------------------------
    # 3. Circuit breaker expiry restores normal Gemini calls
    # -----------------------------------------------------------------------

    def test_breaker_expiry_restores_gemini(self):
        """
        Once the connectivity circuit breaker expires, Gemini calls resume normally.
        """
        # Expired breaker (set in the past)
        llm_service._GEMINI_CONNECTIVITY_BROKEN_UNTIL = time.time() - 1.0

        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.text = "Hello, how can I help?"
        fake_client.models.generate_content.return_value = fake_response

        with (
            patch("services.llm_service._get_gemini_client", return_value=fake_client),
            patch("services.llm_service.os.environ.get", return_value="fake-key"),
            patch("services.llm_service.GEMINI_API_KEY", "fake-key"),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            result = generate_llm_response("I feel sad", "SADNESS", "SADNESS", "NEGATIVE")

        # Gemini should have been called (breaker expired)
        fake_client.models.generate_content.assert_called()
        self.assertIn("help", result.lower())

    # -----------------------------------------------------------------------
    # 4. Healthy Gemini path is unaffected (regression)
    # -----------------------------------------------------------------------

    def test_healthy_gemini_call_succeeds(self):
        """
        When Gemini responds normally and no breaker is active, generate_llm_response
        returns the Gemini reply without touching the offline fallback.
        """
        _reset_breakers()

        fake_client = MagicMock()
        fake_response = MagicMock()
        fake_response.text = "I hear you, and I want to help."
        fake_client.models.generate_content.return_value = fake_response

        with (
            patch("services.llm_service._get_gemini_client", return_value=fake_client),
            patch("services.llm_service.os.environ.get", return_value="real-key"),
            patch("services.llm_service.GEMINI_API_KEY", "real-key"),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
            patch("services.llm_service.query_local_ollama") as mock_ollama,
        ):
            result = generate_llm_response("I feel sad", "SADNESS", "SADNESS", "NEGATIVE")

        # Ollama should NOT have been called — Gemini succeeded
        mock_ollama.assert_not_called()
        self.assertIn("hear", result.lower())

    # -----------------------------------------------------------------------
    # 5. No regression: quota per-model breaker still works independently
    # -----------------------------------------------------------------------

    def test_per_model_quota_breaker_skips_only_exhausted_model(self):
        """
        A per-model quota breaker must only skip that specific model, not all models.
        The next candidate model in the list should still be tried.
        """
        _reset_breakers()
        first_model = GEMINI_CANDIDATE_MODELS[0]
        second_model = GEMINI_CANDIDATE_MODELS[1] if len(GEMINI_CANDIDATE_MODELS) > 1 else None

        if second_model is None:
            self.skipTest("Need at least 2 candidate models for this test")

        # Mark first model quota-exceeded
        llm_service._MODEL_QUOTA_EXCEEDED_UNTIL[first_model] = time.time() + 60.0

        call_order = []

        def fake_generate(model, contents, config):
            call_order.append(model)
            resp = MagicMock()
            resp.text = "Ollama not needed"
            return resp

        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = fake_generate

        with (
            patch("services.llm_service._get_gemini_client", return_value=fake_client),
            patch("services.llm_service.os.environ.get", return_value="fake-key"),
            patch("services.llm_service.GEMINI_API_KEY", "fake-key"),
            patch("services.llm_service._get_keyword_specific_response", return_value=None),
        ):
            generate_llm_response("I feel stressed", "STRESS", "SADNESS", "NEGATIVE")

        self.assertNotIn(first_model, call_order, "Quota-exhausted model should be skipped")
        self.assertIn(second_model, call_order, "Next model should be tried after quota skip")


if __name__ == "__main__":
    unittest.main()
