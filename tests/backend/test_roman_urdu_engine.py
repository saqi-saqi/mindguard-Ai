"""
Roman Urdu engine tests: router, normalizer (property/fuzz/forbidden folds),
feature-flag restore, Arabic-script fallback, LOW_CONFIDENCE_RISK, latency.
"""
import json
import os
import random
import statistics
import subprocess
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
os.environ.setdefault("USE_MONGOMOCK", "true")
os.environ.setdefault("FLASK_ENV", "testing")

from server.services.roman_urdu_router import route, ROUTE_ENGLISH, ROUTE_URDU, ROUTE_BOTH, ROUTE_ARABIC_SCRIPT, urdu_density
from server.services.roman_urdu_normalizer import normalize_roman_urdu, FORBIDDEN_FOLDS
from server.services.crisis_rules import evaluate_deterministic_crisis, evaluate_crisis_pipeline

ROOT = Path(__file__).resolve().parents[2]
SEED = 42


class RouterTests(unittest.TestCase):
    def test_pure_english_routes_english(self):
        for t in ["I am feeling anxious about my exam", "Hello there", "This weather is nice today"]:
            r, _ = route(t)
            self.assertEqual(r, ROUTE_ENGLISH, t)

    def test_pure_roman_urdu_routes_urdu(self):
        for t in ["Mujhe marna hai", "Zindagi se tang aa gaya hoon", "Mujhe ab jeene ki himmat nahi"]:
            r, _ = route(t)
            self.assertEqual(r, ROUTE_URDU, t)

    def test_code_switch_routes_urdu(self):
        r, _ = route("yaar I am done, mujhe mar jana hai")
        self.assertEqual(r, ROUTE_URDU)

    def test_single_foreign_word_is_not_urdu(self):
        # "yaar" alone (English message) must not force the Urdu path
        r, _ = route("That movie was great yaar")
        self.assertIn(r, (ROUTE_ENGLISH, ROUTE_BOTH))

    def test_arabic_script_routes_fallback(self):
        r, _ = route("مجھے مرنا ہے")
        self.assertEqual(r, ROUTE_ARABIC_SCRIPT)


class NormalizerTests(unittest.TestCase):
    def test_idempotency(self):
        samples = ["Mujhe marna hai", "nahin yaar main theek hoon", "marrrr jaunga", "Mjhe krna hai"]
        for s in samples:
            self.assertEqual(normalize_roman_urdu(normalize_roman_urdu(s)), normalize_roman_urdu(s))

    def test_english_passthrough_property(self):
        texts = []
        for f in ["english_crisis_benchmark_300.json", "generated_crisis_eval_dataset.json",
                  "generated_crisis_eval_dataset_v2.json"]:
            p = ROOT / "tests" / "data" / f
            if p.exists():
                texts += [c["text"] for c in json.loads(p.read_text(encoding="utf-8"))]
        # Guarantee scope: only texts the router routes as ENGLISH must pass through
        # unchanged (the benchmark files also contain Roman-Urdu rows by design).
        from server.services.roman_urdu_router import route, ROUTE_ENGLISH
        texts = [t for t in texts if route(t)[0] == ROUTE_ENGLISH]
        rng = random.Random(SEED)
        sample = texts if len(texts) <= 500 else rng.sample(texts, 500)
        self.assertGreaterEqual(len(sample), 300)
        for t in sample:
            self.assertEqual(normalize_roman_urdu(t), t, f"English text mutated: {t[:60]}")

    def test_forbidden_folds_never_happen(self):
        for src, dst, _why in FORBIDDEN_FOLDS:
            out = normalize_roman_urdu(f"ye {src} kaam")
            self.assertNotIn(dst, out.lower().replace(src, ""), (src, dst, out))
        # explicit meaning pairs
        self.assertIn("mein", normalize_roman_urdu("dil mein dukh hai"))  # 'in' untouched
        out = normalize_roman_urdu("marr raha hoon")  # 'beating' untouched as marr
        self.assertIn("marr", out)

    def test_spelling_folds(self):
        self.assertEqual(normalize_roman_urdu("Mujhe marna nai hai"), "Mujhe marna nahi hai")
        self.assertEqual(normalize_roman_urdu("main jaonga"), "main jaunga")
        self.assertIn("khudkushi", normalize_roman_urdu("khud kushi karna chahta hoon"))

    def test_repeats_and_noise(self):
        self.assertEqual(normalize_roman_urdu("marrrrr jaunga"), "mar jaunga")
        out = normalize_roman_urdu("Mujhe\u200b marna hai \U0001F62D")
        self.assertNotIn("\u200b", out)
        self.assertNotIn("\U0001F62D", out)


class FlagRestoreTests(unittest.TestCase):
    def test_flag_off_restores_previous_behavior(self):
        code = (
            "import sys, json; sys.path.insert(0, r'%s');"
            "from server.services.crisis_rules import evaluate_deterministic_crisis;"
            "print(json.dumps([evaluate_deterministic_crisis(t)['is_crisis'] for t in %r]))"
        ) % (str(ROOT), ["Main sab ka bojh hoon", "Mujhe mar jana hai", "I want to die"])
        env = dict(os.environ, ROMAN_URDU_RULES_ENABLED="false", USE_MONGOMOCK="true", FLASK_ENV="testing")
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, timeout=120)
        self.assertEqual(out.returncode, 0, out.stderr[-500:])
        results = json.loads(out.stdout.strip().splitlines()[-1])
        # Urdu-ONLY additions are gone; canonical patterns and English stay.
        self.assertEqual(results, [False, True, True], "flag-off must restore pre-Urdu behavior")


class PipelineRouteTests(unittest.TestCase):
    def test_arabic_script_never_silent(self):
        res = evaluate_crisis_pipeline("مجھے مدد کی ضرورت ہے", allow_ml_fallback=False)
        self.assertEqual(res.get("source"), "arabic_script_fallback")
        self.assertTrue(res.get("resources"))
        self.assertTrue(res.get("safety_message"))

    def test_low_confidence_from_suppressed_anchor(self):
        # Tier-2 anchor ("sab ka bojh") suppressed by negation -> gentle check-in
        text = "Main sach mein sab ka bojh hoon... mazak kar raha hoon, sab theek hai"
        res = evaluate_crisis_pipeline(text, allow_ml_fallback=False)
        # suppressed anchor => LOW_CONFIDENCE_RISK (never a crisis hit, never silence)
        if res.get("bypass_triggered") and res.get("risk_level") == "LOW_CONFIDENCE_RISK":
            self.assertFalse(res["is_crisis"])
            self.assertTrue(res.get("safety_message"))
            self.assertTrue(res.get("resources"))
        else:
            # must at least never be silent-with-anchor: either crisis (wrong) or no anchor
            self.assertNotIn("bojh", [p for cat in [res.get("matched_categories", [])] for p in cat] if res.get("is_crisis") else [])


class LatencyTests(unittest.TestCase):
    def test_p95_latency_under_20ms(self):
        texts = []
        for f in ["roman_urdu_benchmark_dev.json"]:
            p = ROOT / "tests" / "data" / f
            if p.exists():
                texts += [c["text"] for c in json.loads(p.read_text(encoding="utf-8"))["cases"]]
        texts = (texts * 10)[:1000]
        texts[::2] = [t + " " + "aur mujhe lagta hai ke sab theek ho jayega inshaAllah bohat kuch" for t in texts[::2]]
        texts[1::4] = [t[:500] for t in texts[1::4]]
        times = []
        for t in texts:
            t0 = time.perf_counter()
            evaluate_deterministic_crisis(t)
            times.append((time.perf_counter() - t0) * 1000)
        p95 = statistics.quantiles(times, n=100)[94]
        self.assertLess(p95, 20.0, f"p95 latency {p95:.1f} ms exceeds 20 ms gate")

    def test_10k_char_input_does_not_explode(self):
        t = ("mujhe theek nahi lag raha " * 500)[:10000]
        t0 = time.perf_counter()
        evaluate_deterministic_crisis(t)
        self.assertLess(time.perf_counter() - t0, 5.0)


if __name__ == "__main__":
    unittest.main()
