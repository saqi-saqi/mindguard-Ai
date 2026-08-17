"""Dependency-free regression tests for the deterministic crisis rule engine.

Run with: python test_crisis_rules.py
"""
import unittest

from services.crisis_rules import evaluate_crisis


class CrisisRulesRegressionTests(unittest.TestCase):
    def assert_crisis(self, text: str) -> None:
        result = evaluate_crisis(text)
        self.assertTrue(result["is_crisis"], f"Expected crisis: {text!r}; got {result}")

    def assert_not_crisis(self, text: str) -> None:
        result = evaluate_crisis(text)
        self.assertFalse(result["is_crisis"], f"Expected non-crisis: {text!r}; got {result}")

    def test_common_high_risk_language_is_detected(self):
        for text in [
            "I want to die.",
            "I wish I were dead.",
            "I do not want to live anymore.",
            "I cannot go on like this.",
            "I am not safe with myself tonight.",
            "I am going to jump off a bridge.",
            "I am going to overdose tonight.",
            "I took too many pills.",
            "I swallowed a bottle of tablets.",
            "I want to cut again.",
        ]:
            with self.subTest(text=text):
                self.assert_crisis(text)

    def test_roman_urdu_crisis_language_is_detected(self):
        for text in [
            "Mujhe mar jana hai.",
            "Main khudkushi karna chahta hoon.",
            "Main apni jaan lena chahti hoon.",
            "Main zindagi khatam karna chahta hoon.",
        ]:
            with self.subTest(text=text):
                self.assert_crisis(text)

    def test_negation_cannot_hide_later_crisis_intent(self):
        self.assert_crisis("I don't want to die, but I am going to kill myself tonight.")
        self.assert_crisis("I am not suicidal anymore, but tonight I plan to end my life.")

    def test_safe_contexts_remain_non_crisis(self):
        for text in [
            "I do not want to die; I want help staying safe.",
            "I could die of embarrassment after that presentation.",
            "I am writing an essay about suicide prevention.",
            "My friend wants to die and I need advice on helping them.",
            "I used to self-harm, but I have been stable for years.",
            "I don't want to live more with my family.",
            "I don't want to live with my parents anymore; I need help finding another place.",
        ]:
            with self.subTest(text=text):
                self.assert_not_crisis(text)

    def test_living_arrangement_context_cannot_hide_later_crisis_intent(self):
        self.assert_crisis("I don't want to live with my family, but I want to die tonight.")


if __name__ == "__main__":
    unittest.main(verbosity=2)
