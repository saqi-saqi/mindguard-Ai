"""
MindGuard - LLM Execution Flow Verification Test
------------------------------------------------
Verifies that generate_llm_response tries Gemini API first (~300ms),
then falls back to local Ollama CPU model second, and finally emotion KB fallback third.
"""

import sys
import os

server_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

import unittest
from unittest.mock import patch, MagicMock
from services import llm_service


class TestLLMFlow(unittest.TestCase):

    def test_gemini_first_then_ollama_fallback(self):
        """
        Verify execution order:
        1. Try Gemini API first.
        2. If Gemini hits 429 or fails, fallback to query_local_ollama second.
        3. If Ollama also fails, fallback to _get_emotion_fallback third.
        """
        call_order = []

        def mock_query_local_ollama(user_text, intent, emotion, sentiment):
            call_order.append("ollama")
            return "Ollama dynamic reply"

        def mock_get_emotion_fallback(text, emotion, sentiment):
            call_order.append("fallback")
            return "Fallback reply"

        with patch.object(llm_service, "query_local_ollama", side_effect=mock_query_local_ollama), \
             patch.object(llm_service, "_get_emotion_fallback", side_effect=mock_get_emotion_fallback):
            llm_service._MODEL_QUOTA_EXCEEDED_UNTIL.clear()

            with patch.object(llm_service, "_get_gemini_client", return_value=MagicMock()), \
                 patch.object(llm_service, "_call_gemini", return_value="Gemini response"):
                reply = llm_service.generate_llm_response("I feel anxious", "ANXIETY OR PANIC ATTACK", "ANXIETY", "NEGATIVE", api_key="test_key")

                self.assertEqual(reply, "Gemini response")
                self.assertNotIn("ollama", call_order, "Ollama should NOT be called when Gemini succeeds!")

        call_order.clear()
        with patch.object(llm_service, "query_local_ollama", side_effect=mock_query_local_ollama), \
             patch.object(llm_service, "_get_emotion_fallback", side_effect=mock_get_emotion_fallback):
            llm_service._MODEL_QUOTA_EXCEEDED_UNTIL = {m: 9999999999.0 for m in llm_service.GEMINI_CANDIDATE_MODELS}

            reply = llm_service.generate_llm_response("I feel anxious", "ANXIETY OR PANIC ATTACK", "ANXIETY", "NEGATIVE", api_key="test_key")

            self.assertEqual(reply, "Ollama dynamic reply")
            self.assertEqual(call_order, ["ollama"], "Expected Ollama to be called as fallback when Gemini is rate-limited!")

    def test_timeout_and_circuit_breaker_fail_gracefully_to_offline_reply(self):
        """Gemini timeouts or quota exhaustion must degrade cleanly to Ollama, then to offline safe fallback."""
        llm_service._MODEL_QUOTA_EXCEEDED_UNTIL.clear()

        with patch.object(llm_service, "_get_gemini_client", return_value=MagicMock()), \
             patch.object(llm_service, "_call_gemini", side_effect=TimeoutError("deadline exceeded")), \
             patch.object(llm_service, "query_local_ollama", return_value="Ollama recovery reply") as mock_ollama, \
             patch.object(llm_service, "_get_emotion_fallback", return_value="Offline safety reply") as mock_fallback:
            reply = llm_service.generate_llm_response("I feel overwhelmed", "STRESS OR ANXIETY", "ANXIETY", "NEGATIVE", api_key="test_key")

            self.assertEqual(reply, "Ollama recovery reply")
            mock_ollama.assert_called_once()
            mock_fallback.assert_not_called()

        llm_service._MODEL_QUOTA_EXCEEDED_UNTIL = {m: 9999999999.0 for m in llm_service.GEMINI_CANDIDATE_MODELS}
        with patch.object(llm_service, "_get_gemini_client", return_value=MagicMock()), \
             patch.object(llm_service, "query_local_ollama", return_value=None), \
             patch.object(llm_service, "_get_emotion_fallback", return_value="Offline safety reply") as mock_fallback:
            reply = llm_service.generate_llm_response("I feel overwhelmed", "STRESS OR ANXIETY", "ANXIETY", "NEGATIVE", api_key="test_key")

            self.assertEqual(reply, "Offline safety reply")
            mock_fallback.assert_called_once()


if __name__ == "__main__":
    unittest.main(verbosity=2)
