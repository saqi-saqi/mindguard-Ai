"""
tests/deep/test_08_pipeline_never_below_tier1.py
================================================
Tier-1 Deterministic Authority Invariant Test Suite.

Enforces the absolute architectural invariant:
  For EVERY crisis-labelled case across all benchmark and fixture files:
  IF Tier 1 (deterministic rules) flags an acute crisis (is_crisis=True),
  THEN the API (/api/chat) MUST flag the crisis as well (can never downgrade below Tier 1).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple
import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
SERVER = ROOT / "server"
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

os.environ["USE_MONGOMOCK"] = "true"
os.environ["FLASK_ENV"] = "testing"

from services.crisis_rules import evaluate_crisis
from tests.deep.mg_adapter import get_app, response_signal

BENCHMARK_FILES = [
    ROOT / "tests" / "data" / "roman_urdu_crisis_benchmark_200.json",
    ROOT / "tests" / "data" / "english_crisis_benchmark_300.json",
    ROOT / "tests" / "fixtures" / "crisis_regression_cases.json",
    ROOT / "tests" / "fixtures" / "crisis_regression_cases_v2.json",
    ROOT / "tests" / "data" / "crisis_nlp_benchmark_dataset.json",
    ROOT / "tests" / "data" / "holdout" / "roman_urdu_test_frozen.json",
]


def _collect_crisis_cases() -> List[Tuple[str, int, str]]:
    """
    Harvests all crisis-labelled test utterances across all benchmark and fixture datasets.
    Returns list of (file_name, index, text).
    """
    cases = []
    for fp in BENCHMARK_FILES:
        if not fp.is_file():
            continue
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            items = data if isinstance(data, list) else data.get("cases", data.values() if isinstance(data, dict) else [])
            for idx, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                text = item.get("text") or item.get("utterance") or item.get("message")
                if not text or not str(text).strip():
                    continue

                is_crisis_label = item.get("expected_crisis")
                if is_crisis_label is None:
                    is_crisis_label = item.get("label") in (1, "1", "crisis", "suicide", "high", "HIGH_CRISIS")
                    if not is_crisis_label:
                        cat = str(item.get("category", "")).lower()
                        if any(k in cat for k in ("crisis", "suicide", "harm")):
                            is_crisis_label = True

                if is_crisis_label:
                    cases.append((fp.name, idx, str(text).strip()))
        except Exception as e:
            print(f"Warning: could not harvest from {fp}: {e}")
    return cases


ALL_CRISIS_CASES = _collect_crisis_cases()
_IP_COUNTER = 0


@pytest.fixture(scope="module")
def api_client():
    os.environ["USE_MONGOMOCK"] = "true"
    os.environ["FLASK_ENV"] = "testing"
    app = get_app()
    old_limit = app.config.get("RATE_LIMIT_PER_MINUTE")
    old_proxies = app.config.get("TRUSTED_PROXIES")
    app.config["RATE_LIMIT_PER_MINUTE"] = 100000
    app.config["TRUSTED_PROXIES"] = ["127.0.0.1", "::1"]
    yield app.test_client()
    if old_limit is not None:
        app.config["RATE_LIMIT_PER_MINUTE"] = old_limit
    else:
        app.config.pop("RATE_LIMIT_PER_MINUTE", None)
    if old_proxies is not None:
        app.config["TRUSTED_PROXIES"] = old_proxies
    else:
        app.config.pop("TRUSTED_PROXIES", None)


def _call_api_with_distinct_ip(client, text: str):
    global _IP_COUNTER
    _IP_COUNTER += 1
    ip = f"10.77.{(_IP_COUNTER // 250)}.{(_IP_COUNTER % 250) + 1}"
    return client.post("/api/chat", json={"message": text}, headers={"X-Forwarded-For": ip})


@pytest.mark.parametrize("file_name, idx, text", ALL_CRISIS_CASES, ids=[f"{c[0]}_{c[1]}" for c in ALL_CRISIS_CASES])
def test_pipeline_never_below_tier1(api_client, file_name: str, idx: int, text: str):
    """
    Core Invariant: If Tier 1 flags a crisis on a crisis-labelled utterance,
    the API endpoint must NEVER suppress or downgrade it.
    """
    t1_result = evaluate_crisis(text)
    t1_is_crisis = bool(t1_result.get("is_crisis"))

    # If Tier 1 did not flag this crisis utterance, the test passes this specific invariant
    # (Tier 2/3 may flag it, but Tier 1 authority is not violated).
    if not t1_is_crisis:
        pytest.skip(f"Tier 1 did not flag utterance '{text[:30]}...' (handled by downstream tiers)")

    # When Tier 1 flags crisis, API MUST flag crisis too!
    resp = _call_api_with_distinct_ip(api_client, text)
    assert resp.status_code == 200, f"API returned non-200 status {resp.status_code} for text: {text}"

    data = resp.get_json(silent=True) or {}
    api_flagged, how = response_signal(resp)

    # Secondary check: verify risk_level or requires_immediate_action
    inner_data = data.get("data", {})
    risk_level = data.get("risk_level") or inner_data.get("risk_level") or inner_data.get("classification")
    requires_action = data.get("requires_immediate_action") or inner_data.get("requires_immediate_action")

    is_emergency_response = (
        api_flagged
        or risk_level in ("HIGH_CRISIS", "COMBINED_HIGH_CRISIS", "HARM_TO_OTHERS_RISK", "THREAT_AGAINST_USER", "SELF_HARM_RISK")
        or requires_action is True
    )

    assert is_emergency_response, (
        f"TIER-1 AUTHORITY VIOLATION in {file_name}[{idx}]:\n"
        f"Input: {text!r}\n"
        f"Tier 1 Flagged: {t1_result}\n"
        f"API Response: {data}\n"
        f"Signal Evaluation: {how}"
    )


def test_tier1_authority_summary(api_client):
    """Verifies that across all harvested crisis cases flagged by Tier 1, zero are missed by the API."""
    flagged_t1 = 0
    flagged_api = 0

    for file_name, idx, text in ALL_CRISIS_CASES:
        t1 = evaluate_crisis(text)
        if t1.get("is_crisis"):
            flagged_t1 += 1
            resp = _call_api_with_distinct_ip(api_client, text)
            flagged, _ = response_signal(resp)
            if flagged:
                flagged_api += 1

    assert flagged_t1 > 0, "Expected at least some crisis cases to be flagged by Tier 1"
    assert flagged_api == flagged_t1, (
        f"Tier 1 flagged {flagged_t1} cases, but API only flagged {flagged_api} "
        f"({flagged_t1 - flagged_api} unexplained drops)."
    )
