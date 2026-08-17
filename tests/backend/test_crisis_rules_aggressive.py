"""High-coverage, dependency-free release gate for crisis_rules.py.

Run from the server directory:
    python test_crisis_rules_aggressive.py

It tests direct intent, indirect intent, self-harm, means, slang, Roman Urdu,
negation, recovery, academic/media references, metaphors, mixed statements,
and formatting/obfuscation variants. A JSON report is saved under artifacts/.
"""
from __future__ import annotations

import json
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

from services.crisis_rules import evaluate_crisis


Case = Tuple[str, str, bool]


CRISIS_CASES: List[Case] = [
    ("explicit_intent", "I want to die", True),
    ("explicit_intent", "I wish I were dead", True),
    ("explicit_intent", "I don't want to live anymore", True),
    ("explicit_intent", "I can't go on like this", True),
    ("explicit_intent", "I am going to kill myself tonight", True),
    ("explicit_intent", "I am feeling suicidal", True),
    ("explicit_intent", "I am planning to end my life", True),
    ("explicit_intent", "I will take my own life", True),
    ("explicit_intent", "I am ready to die", True),
    ("implicit_distress", "I feel like disappearing forever", True),
    ("implicit_distress", "I do not see a future for myself", True),
    ("implicit_distress", "The only way out feels like ending my life", True),
    ("implicit_distress", "I have been planning how to end things", True),
    ("implicit_distress", "I do not think I can survive another day", True),
    ("means_or_attempt", "I am going to overdose tonight", True),
    ("means_or_attempt", "I took too many pills", True),
    ("means_or_attempt", "I swallowed a bottle of tablets", True),
    ("means_or_attempt", "I am going to jump off a bridge", True),
    ("means_or_attempt", "I have the rope ready", True),
    ("means_or_attempt", "I have the pills in front of me right now", True),
    ("means_or_attempt", "I wrote a goodbye note", True),
    ("self_harm", "I am not safe with myself", True),
    ("self_harm", "I want to cut again", True),
    ("self_harm", "I am cutting myself", True),
    ("self_harm", "I am holding the blade", True),
    ("self_harm", "I might hurt myself tonight", True),
    ("slang", "kms", True),
    ("slang", "I should kys", True),
    ("slang", "I am gonna unalive myself", True),
    ("slang", "I am finna end it all", True),
    ("roman_urdu", "Mujhe mar jana hai", True),
    ("roman_urdu", "Main khudkushi karna chahta hoon", True),
    ("roman_urdu", "Main apni jaan lena chahti hoon", True),
    ("roman_urdu", "Main zindagi khatam karna chahta hoon", True),
    ("contradiction", "I do not want to die, but I am going to kill myself tonight", True),
    ("contradiction", "I am not suicidal anymore; however, tonight I plan to end my life", True),
]

SAFE_CASES: List[Case] = [
    ("negation", "I do not want to die; I want help staying safe", False),
    ("negation", "I am not suicidal, just exhausted", False),
    ("negation", "I have no thoughts of harming myself", False),
    ("distress_support_request", "I am so frustrated and angry today; I just need help calming down", False),
    ("distress_support_request", "This day was terrible and I need help sleeping tonight", False),
    ("distress_support_request", "I do not want to die; I need help staying calm and resting", False),
    ("distress_support_request", "I am writing an essay on suicide for class and I am not in crisis", False),
    ("recovery", "I used to self-harm, but I have been stable for years", False),
    ("recovery", "I had suicidal thoughts years ago but I am doing well now", False),
    ("academic", "I am writing a research paper about suicide prevention", False),
    ("academic", "I read a news article about a celebrity's suicidal thoughts", False),
    ("academic", "My psychology class discussed suicide statistics", False),
    ("media", "The book I am reading has a character who battles suicidal ideation", False),
    ("media", "I watched a documentary about self-harm awareness", False),
    ("third_party", "My friend wants to die and I need advice on helping them", False),
    ("metaphor", "I want to die of embarrassment after that presentation", False),
    ("metaphor", "I am dying of laughter", False),
    ("metaphor", "My feet are killing me after the hike", False),
    ("metaphor", "I am dead tired after finals", False),
    ("normal_distress", "I feel hopeless about my exam but I will keep trying", False),
    ("normal_distress", "I lost my job and feel overwhelmed", False),
    ("normal_distress", "I cannot sleep because I am stressed", False),
]

# These cases specifically validate targeted normalization of common obfuscation.
OBFUSCATED_CASES: List[Case] = [
    ("obfuscation", "I will k!ll myself", True),
    ("obfuscation", "I feel su1cidal", True),
    ("obfuscation", "I might self h@rm", True),
    ("obfuscation", "k.y.s", True),
    ("obfuscation", "I w@nna die", True),
    ("obfuscation", "I dont wanna live anymore", True),
]


def variants(text: str) -> Iterable[str]:
    """Formatting changes that must not affect the decision."""
    yield text
    yield text.upper()
    yield "  " + text.replace(" ", "   ") + "  "
    yield text.replace("'", "\u2019") + "!!!"


def all_cases() -> Iterable[Case]:
    for category, text, expected in CRISIS_CASES + SAFE_CASES:
        for index, variant in enumerate(variants(text), start=1):
            yield category, f"variant_{index}: {variant}", expected
    yield from OBFUSCATED_CASES


class AggressiveCrisisRulesTests(unittest.TestCase):
    def test_release_gate(self) -> None:
        results: List[Dict] = []
        category_stats: Dict[str, Counter] = defaultdict(Counter)

        for category, labelled_text, expected in all_cases():
            text = labelled_text.split(": ", 1)[-1] if labelled_text.startswith("variant_") else labelled_text
            actual = evaluate_crisis(text)["is_crisis"]
            passed = actual == expected
            category_stats[category]["total"] += 1
            category_stats[category]["passed"] += int(passed)
            results.append({"category": category, "text": text, "expected_crisis": expected, "actual_crisis": actual, "passed": passed})

        total = len(results)
        passed = sum(item["passed"] for item in results)
        report = {
            "suite": "MindGuard aggressive deterministic crisis-rule release gate",
            "total_cases": total,
            "passed": passed,
            "failed": total - passed,
            "accuracy": round(passed / total, 4),
            "category_breakdown": {name: dict(stats) for name, stats in sorted(category_stats.items())},
            "failures": [item for item in results if not item["passed"]],
        }
        try:
            report_path = Path(__file__).resolve().parent.parent / "artifacts" / "crisis_rule_aggressive_report.json"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except Exception:
            # Fall back gracefully so filesystem permission restrictions do not block test execution
            pass

        self.assertGreaterEqual(total, 200, "The release gate should cover at least 200 cases.")
        self.assertEqual([], report["failures"], f"Crisis-rule failures recorded in {results}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
