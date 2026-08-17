"""
test_crisis_fixes_regression.py
================================
Regression test suite specifically verifying the safety audit fixes:
1. Benign medication statements do not trigger crisis.
2. Lethal means / acquisition statements DO trigger crisis.
3. Multi-turn recovery conversations do not get trapped in crisis.
4. Compound venting + active self-harm / crisis statements trigger crisis.
5. Negations and survival requests bypass safely.
6. Chat history ordering returns true most recent user turns.
"""

import unittest
import os
import json
import time

from services.crisis_rules import evaluate_crisis, evaluate_deterministic_crisis, is_contextual_or_negated
from services.huggingface_service import analyze_user_message
from database import init_db, get_db, save_chat_message, get_chat_history
from app import app, reset_rate_limits

class CrisisFixesRegressionTestCase(unittest.TestCase):

    def setUp(self):
        os.environ["USE_MONGOMOCK"] = "true"
        os.environ["FLASK_ENV"] = "testing"
        init_db()
        db = get_db()
        db.users.delete_many({})
        db.chat_messages.delete_many({})
        db.audit_logs.delete_many({})
        reset_rate_limits()
        self.app = app.test_client()
        self.app.testing = True

    def test_benign_medication_does_not_trigger_crisis(self):
        benign_phrases = [
            "I took my daily vitamin pills this morning.",
            "I forgot to take my pills today.",
            "My doctor changed my pills dosage.",
            "I need to take my blood pressure medication with water.",
            "Should I take my pills before or after breakfast?",
        ]
        for phrase in benign_phrases:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertFalse(
                    res["is_crisis"],
                    f"Benign medication statement flagged as crisis: {phrase} => {res}"
                )

    def test_lethal_means_and_acquisition_triggers_crisis(self):
        crisis_phrases = [
            "I bought a bottle of lethal pills to end everything.",
            "I stockpiled pills for tonight.",
            "I swallowed the pills and I am not stopping.",
            "I bought the rope and decided when it will happen.",
        ]
        for phrase in crisis_phrases:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertTrue(
                    res["is_crisis"],
                    f"Lethal means not detected: {phrase} => {res}"
                )

    def test_compound_emotional_distress_with_escalation_triggers_crisis(self):
        compound_phrases = [
            "I feel so empty, I already made the first cut",
            "I'm feeling so sad and lost, holding the blade right now",
            "This day was terrible, swallowed the pills already",
        ]
        for phrase in compound_phrases:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertTrue(
                    res["is_crisis"],
                    f"Compound crisis bypassed incorrectly: {phrase} => {res}"
                )

    def test_negations_and_help_seeking_bypass_safely(self):
        safe_phrases = [
            "I am definitely not suicidal.",
            "I don't want to die, I want help.",
            "Help me not hurt myself.",
            "How to stop hurting myself?",
            "Advice on how to stop cutting myself.",
            "I used to self-harm years ago, but I have been in recovery for a long time.",
        ]
        for phrase in safe_phrases:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertFalse(
                    res["is_crisis"],
                    f"Safe help-seeking / negation flagged as crisis: {phrase} => {res}"
                )

    def test_multi_turn_history_does_not_trap_user_after_stabilization(self):
        # Turn 1 was crisis, Turn 2 is stabilized
        stabilized_res = analyze_user_message(
            "Thank you so much, I am feeling a lot calmer and safe now.",
            context_turns=["I want to kill myself tonight"]
        )
        self.assertNotEqual(
            stabilized_res["intent"],
            "SUICIDE CRISIS OR SELF HARM RISK",
            "Stabilized message trapped in crisis intent due to history concatenation"
        )

    def test_chat_history_order_returns_most_recent_chronological(self):
        user_id = "test-user-history"
        for i in range(10):
            save_chat_message(user_id=user_id, sender="user", text=f"Message {i}")
            time.sleep(0.01)

        history = get_chat_history(user_id=user_id, limit=3)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["text"], "Message 7")
        self.assertEqual(history[1]["text"], "Message 8")
        self.assertEqual(history[2]["text"], "Message 9")


if __name__ == "__main__":
    unittest.main()
