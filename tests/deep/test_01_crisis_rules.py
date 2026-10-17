"""
TIER 1: deterministic rule engine (server/services/crisis_rules.py).

Safety-critical. Failures here marked "FINDING" are real false negatives /
false positives in your engine, not bugs in the test.
"""
from __future__ import annotations

import ast
import inspect
import json
import statistics
import time
from pathlib import Path

import pytest

from mg_adapter import ROOT, rules_callable, rules_module, run_rules, verdict
from mg_cases import (
    BENIGN_NOT_CRISIS, DISTRESS_NOT_CRISIS, EVASION_CASES, GARBAGE, LONG_FILLER,
    NEGATED_INTENT, POSITIVE, POSITIVE_FLAT, REDOS_INPUTS,
    ROMAN_URDU_SPELLING_VARIANTS, TRANSFORMS, HARM_TO_OTHERS,
)


# --------------------------------------------------------------------------- #
# 1. Core recall: every labelled crisis phrase MUST fire
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("category,phrase", POSITIVE_FLAT, ids=[f"{c}::{p[:40]}" for c, p in POSITIVE_FLAT])
def test_crisis_phrase_is_flagged(category, phrase):
    v = run_rules(phrase)
    assert v.is_crisis, f"FINDING (false negative) [{category}] not flagged: {phrase!r} -> {v.raw!r}"


@pytest.mark.parametrize("phrase", HARM_TO_OTHERS)
def test_harm_to_others_is_crisis_not_generic_distress(phrase):
    """Known bug area: homicide threats were only tagged as generic 'distressed'."""
    v = run_rules(phrase)
    assert v.is_crisis, f"FINDING: harm-to-others only tagged as non-crisis: {phrase!r} -> {v.raw!r}"


@pytest.mark.parametrize("phrase", POSITIVE["combined_harm_and_self_en"])
def test_combined_harm_and_self_harm_is_highest_risk(phrase):
    v = run_rules(phrase)
    assert v.is_crisis, f"FINDING: combined threat not flagged: {phrase!r} -> {v.raw!r}"
    if v.level:
        assert not any(w in v.level.lower() for w in ("low", "medium", "moderate", "none")), \
            f"combined threat got a weak level: {v.level}"


# --------------------------------------------------------------------------- #
# 2. Precision: benign look-alikes must NOT escalate
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("phrase", BENIGN_NOT_CRISIS)
def test_benign_phrase_is_not_flagged(phrase):
    v = run_rules(phrase)
    assert not v.is_crisis, f"FINDING (false positive): {phrase!r} -> {v.raw!r}"


@pytest.mark.parametrize("phrase", DISTRESS_NOT_CRISIS)
def test_ordinary_distress_is_not_high_crisis(phrase):
    v = run_rules(phrase)
    assert not v.is_crisis, f"FINDING (over-escalation): {phrase!r} -> {v.raw!r}"


@pytest.mark.parametrize("phrase", NEGATED_INTENT)
def test_explicit_negation_is_respected(phrase):
    """POLICY TEST: README promises 'contextual negations'. If you decide to be
    deliberately conservative and flag these anyway, change NEGATED_INTENT."""
    v = run_rules(phrase)
    assert not v.is_crisis, f"Negation not honoured: {phrase!r} -> {v.raw!r}"


# --------------------------------------------------------------------------- #
# 3. Evasion + formatting robustness
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("transform,seed", EVASION_CASES, ids=[f"{t}::{s[:25]}" for t, s in EVASION_CASES])
def test_formatting_variants_still_flagged(transform, seed):
    text = TRANSFORMS[transform](seed)
    v = run_rules(text)
    assert v.is_crisis, f"FINDING (evasion via '{transform}'): {text!r} -> {v.raw!r}"


@pytest.mark.parametrize("phrase", ROMAN_URDU_SPELLING_VARIANTS)
def test_roman_urdu_spelling_variants_flagged(phrase):
    v = run_rules(phrase)
    assert v.is_crisis, f"FINDING (Roman Urdu spelling variant missed): {phrase!r} -> {v.raw!r}"


@pytest.mark.parametrize("where", ["start", "middle", "end"])
@pytest.mark.parametrize("phrase", ["I want to kill myself", "main khudkushi karna chahta hun"])
def test_phrase_buried_in_long_text_is_flagged(phrase, where):
    text = {"start": phrase + ". " + LONG_FILLER,
            "middle": LONG_FILLER + phrase + ". " + LONG_FILLER,
            "end": LONG_FILLER + phrase}[where]
    v = run_rules(text)
    assert v.is_crisis, f"FINDING: crisis phrase lost in long text ({where})"


@pytest.mark.parametrize("phrase", [
    "I had a great day. Then at night I realised I want to kill myself",
    "Hi!\n\nThanks for talking.\n\nmujhe marna hai\n\nbye",
    "My exam went badly and honestly main khudkushi karna chahta hun now",
    "کل امتحان تھا اور I want to end my life",
])
def test_code_switched_and_multiline_messages(phrase):
    assert run_rules(phrase).is_crisis, f"FINDING: {phrase!r}"


# --------------------------------------------------------------------------- #
# 4. Engine contract: never crash, never hang, deterministic
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("text", GARBAGE, ids=[f"garbage{i}" for i in range(len(GARBAGE))])
def test_garbage_input_never_crashes_or_flags_noise(text):
    start = time.perf_counter()
    v = run_rules(text)
    assert time.perf_counter() - start < 2.0, "garbage input took >2s"
    # Pure noise must not be reported as a crisis (alert fatigue)
    if text.strip() in ("", "\x00", "\ufeff", "0" * 10, "!@#$%^&*()" * 100, "\n\t", "🙂" * 500, "a" * 100_000):
        assert not v.is_crisis, f"noise flagged as crisis: {text[:20]!r}"


def test_none_input_fails_safely():
    try:
        v = verdict(rules_callable()(None))
    except (TypeError, ValueError, AttributeError):
        return  # acceptable: explicit rejection
    assert not v.is_crisis  # acceptable: treated as empty


@pytest.mark.parametrize("n", range(len(REDOS_INPUTS)))
def test_no_catastrophic_regex_backtracking(n):
    text = REDOS_INPUTS[n]
    start = time.perf_counter()
    run_rules(text)
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"FINDING (ReDoS risk): input #{n} took {elapsed:.2f}s"


def test_deterministic_same_input_same_verdict():
    for phrase in ("I want to kill myself", "this exam is killing me", "main udaas hun"):
        results = {run_rules(phrase).is_crisis for _ in range(25)}
        assert len(results) == 1, f"non-deterministic verdict for {phrase!r}"


def test_rules_do_not_mutate_or_depend_on_global_state():
    a = run_rules("I want to kill myself").is_crisis
    for junk in ("hello", "I feel sad", "kill the process"):
        run_rules(junk)
    assert run_rules("I want to kill myself").is_crisis == a


def test_latency_budget_for_crisis_detection():
    """Crisis detection must feel instant."""
    run_rules("warm up")
    samples = []
    for _ in range(50):
        t = time.perf_counter()
        run_rules("I have a plan to kill myself tonight and I wrote a note")
        samples.append(time.perf_counter() - t)
    assert statistics.median(samples) < 0.05, f"median {statistics.median(samples)*1000:.1f}ms is too slow"


# --------------------------------------------------------------------------- #
# 5. Architecture guarantees from the README
# --------------------------------------------------------------------------- #
def test_tier1_has_no_ml_or_network_dependencies():
    """Tier 1 must keep working when ML libs / the network / Gemini are down."""
    src = Path(inspect.getsourcefile(rules_module())).read_text(encoding="utf-8")
    tree = ast.parse(src)
    banned = {"torch", "transformers", "sklearn", "joblib", "google", "requests", "httpx",
              "urllib3", "aiohttp", "openai", "pymongo", "flask"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    bad = imported & banned
    assert not bad, f"crisis_rules.py imports {bad}: Tier 1 must be self-sufficient"


# --------------------------------------------------------------------------- #
# 6. Existing regression fixture (tests/fixtures/crisis_regression_cases.json)
# --------------------------------------------------------------------------- #
def _load_regression():
    p = ROOT / "tests" / "fixtures" / "crisis_regression_cases.json"
    if not p.exists():
        return []
    data = json.loads(p.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        for k in ("cases", "tests", "data", "items"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
    out = []
    for i, c in enumerate(data if isinstance(data, list) else []):
        if not isinstance(c, dict):
            continue
        text = next((c[k] for k in ("text", "input", "message", "prompt", "query") if isinstance(c.get(k), str)), None)
        if text is None:
            continue
        exp = None
        for k in ("expected_crisis", "is_crisis", "crisis", "expect_crisis"):
            if isinstance(c.get(k), bool):
                exp = c[k]
        if exp is None:
            lab = next((c[k] for k in ("expected", "label", "expected_level", "risk_level") if k in c), None)
            if isinstance(lab, str):
                exp = verdict(lab).is_crisis
        out.append(pytest.param(text, exp, id=f"fixture{i}"))
    return out


_REG = _load_regression()


@pytest.mark.skipif(not _REG, reason="no parsable tests/fixtures/crisis_regression_cases.json")
@pytest.mark.parametrize("text,expected", _REG)
def test_existing_regression_fixtures(text, expected):
    v = run_rules(text)
    if expected is not None:
        assert v.is_crisis == expected, f"regression: {text!r} expected crisis={expected} got {v.raw!r}"


# --------------------------------------------------------------------------- #
# 7. Metrics gate (prints a per-category recall table)
# --------------------------------------------------------------------------- #
def test_recall_and_false_positive_gate(capsys):
    rows, tp_total, n_total = [], 0, 0
    for cat, phrases in POSITIVE.items():
        hits = sum(run_rules(p).is_crisis for p in phrases)
        rows.append((cat, hits, len(phrases)))
        tp_total += hits
        n_total += len(phrases)
    fp = sum(run_rules(p).is_crisis for p in BENIGN_NOT_CRISIS + DISTRESS_NOT_CRISIS)
    neg_total = len(BENIGN_NOT_CRISIS) + len(DISTRESS_NOT_CRISIS)

    with capsys.disabled():
        print("\n  Tier-1 recall by category")
        for cat, h, n in rows:
            print(f"    {cat:<30} {h}/{n}  ({100*h/n:.0f}%)")
        print(f"    OVERALL recall {tp_total}/{n_total}   false positives {fp}/{neg_total}")

    assert tp_total / n_total >= 0.95, f"overall recall {tp_total/n_total:.2%} < 95%"
    for cat, h, n in rows:
        assert h / n >= 0.85, f"recall for {cat} is {h}/{n} (<85%)"
    assert fp / neg_total <= 0.10, f"false-positive rate {fp/neg_total:.2%} > 10%"
