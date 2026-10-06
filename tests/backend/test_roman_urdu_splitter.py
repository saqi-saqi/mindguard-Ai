"""
Splitter tests — written BEFORE the splitter (plan requirement).

Semantics under test:
  - Commas NEVER split segments; negation/temporal markers carry across commas.
  - Contrastive conjunctions (lekin, magar, phir bhi, but, however) DO split.
  - Sentence-final punctuation splits.
  - Suppression (negation/recovery) applies to its own span only.
"""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("USE_MONGOMOCK", "true")
os.environ.setdefault("FLASK_ENV", "testing")

from server.services.crisis_rules import _split_contrastive_segments, evaluate_deterministic_crisis


class SplitterUnitTests(unittest.TestCase):
    def test_comma_never_splits(self):
        segs = _split_contrastive_segments("pehle theek tha, ab marna chahta hoon")
        self.assertEqual(len(segs), 1)

    def test_lekin_splits(self):
        segs = _split_contrastive_segments("behtar hoon lekin phir bhi marna chahta hoon")
        self.assertEqual(len(segs), 2)
        self.assertIn("marna chahta hoon", segs[1].lower())

    def test_phir_bhi_splits(self):
        segs = _split_contrastive_segments("theek hoon phir bhi khatam ho jana chahta hoon")
        self.assertEqual(len(segs), 2)

    def test_sentence_punctuation_splits(self):
        segs = _split_contrastive_segments("Aaj bohat dukh hua. Mujhe marna hai")
        self.assertEqual(len(segs), 2)

    def test_but_splits_english(self):
        segs = _split_contrastive_segments("I feel better, but tonight I plan to end my life")
        self.assertEqual(len(segs), 2)

    def test_no_contrastive_single(self):
        segs = _split_contrastive_segments("Mujhe marna hai")
        self.assertEqual(len(segs), 1)


class TrapSentenceSemantics(unittest.TestCase):
    """The exact sentences the plan requires to be right, as end-to-end rules verdicts."""

    def assertCrisis(self, text):
        res = evaluate_deterministic_crisis(text)
        self.assertTrue(res["is_crisis"], f"expected CRISIS for: {text} -> {res['risk_level']}")

    def assertNotCrisis(self, text):
        res = evaluate_deterministic_crisis(text)
        self.assertFalse(res["is_crisis"], f"expected NON-CRISIS for: {text} -> {res}")

    def test_past_denial_present_ideation_is_crisis(self):
        self.assertCrisis("pehle nahi sochta tha, ab sochta hoon")

    def test_past_ideation_present_denial_is_not_crisis(self):
        self.assertNotCrisis("pehle sochta tha, ab nahi")

    def test_recovery_then_lekin_risk_is_crisis(self):
        self.assertCrisis("behtar hoon lekin phir bhi marna chahta hoon")

    def test_hedged_negation_is_crisis_tier3(self):
        self.assertCrisis("Main marna nahi chahta, bas sab khatam ho jaye")

    def test_direct_denial_is_not_crisis(self):
        self.assertNotCrisis("Main marna nahi chahta")

    def test_hyperbole_not_crisis(self):
        self.assertNotCrisis("Kal exam hai, mar hi jaoon ga")
        self.assertNotCrisis("Bohat garmi hai, mar jaunga")
        self.assertNotCrisis("Garmi ne maar dala aaj")

    def test_bare_mar_jaunga_not_crisis(self):
        self.assertNotCrisis("Mar jaunga")

    def test_suppression_does_not_cross_lekin(self):
        # Recovery in span 1 must not suppress risk in span 2
        self.assertCrisis("Alhamdulillah ab theek hoon lekin aaj phir se marna chahta hoon")


if __name__ == "__main__":
    unittest.main()
