"""
TIER 2 (ML) & PIPELINE INTEGRATION TESTS (Phase 3)

Validates:
  * huggingface_service.py: model loading, missing artifacts, corrupt artifacts,
    lazy loading, thread safety, output schema, threshold boundary, latency budget,
    empty / long / non-Latin input robustness.
  * Contradictory output proofs:
    - Tier 2 raises risk when Tier 1 did not fire
    - Tier 2 can NEVER lower or override a Tier 1 crisis flag
    - Tier 2 exception / failure fails SAFE
"""
from __future__ import annotations

import os
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure server package is importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT / "server") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "server"))

from services import huggingface_service


# --------------------------------------------------------------------------- #
# 1. Output Schema & Input Robustness
# --------------------------------------------------------------------------- #
def test_output_schema_keys_and_types():
    """Verify analyze_user_message returns the required schema with correct types."""
    res = huggingface_service.analyze_user_message("I am feeling a little down today")
    expected_keys = {
        "intent", "intent_confidence",
        "emotion", "emotion_confidence",
        "sentiment", "sentiment_confidence",
        "inference_latency_ms"
    }
    assert expected_keys.issubset(res.keys()), f"Missing keys in output: {expected_keys - set(res.keys())}"
    assert isinstance(res["intent"], str)
    assert isinstance(res["intent_confidence"], (int, float))
    assert 0.0 <= res["intent_confidence"] <= 1.0
    assert isinstance(res["emotion"], str)
    assert isinstance(res["emotion_confidence"], (int, float))
    assert isinstance(res["sentiment"], str)
    assert isinstance(res["sentiment_confidence"], (int, float))
    assert isinstance(res["inference_latency_ms"], (int, float))


def test_empty_input_handled_safely():
    """Empty string returns fallback schema without crashing."""
    res = huggingface_service.analyze_user_message("")
    assert res["intent"] in ["GENERAL SUPPORT TOPIC", "GREETING OR CASUAL CHAT"]
    assert res["emotion"] in ["NEUTRAL", "FEAR", "SADNESS", "JOY"]
    assert res["sentiment"] in ["NEUTRAL", "POSITIVE", "NEGATIVE"]
    assert res["inference_latency_ms"] >= 0.0


def test_very_long_input_truncated_safely():
    """Input exceeding 2000 chars is safely handled and truncated."""
    long_text = "I feel stressed. " * 300  # ~5100 chars
    res = huggingface_service.analyze_user_message(long_text)
    assert isinstance(res["intent"], str)
    assert res["inference_latency_ms"] < 10000


def test_non_latin_unsupported_input_handled_safely():
    """Non-Latin input (Urdu script, Arabic, Chinese) does not crash inference."""
    for sample in [
        "میں بہت اداس ہوں",
        "أشعر بالحزن الشديد اليوم",
        "我今天感到很沮丧",
        "🎉 😭 ❤️ 🔥 🚀",
    ]:
        res = huggingface_service.analyze_user_message(sample)
        assert isinstance(res["intent"], str)
        assert "inference_latency_ms" in res


# --------------------------------------------------------------------------- #
# 2. Threshold Boundary & Contradictory Output Proofs
# --------------------------------------------------------------------------- #
def test_tier2_raises_risk_when_tier1_did_not_fire():
    """
    Tier 2 can raise risk when Tier 1 regex did not match.
    Simulate ML model outputting crisis probability >= 0.50 on subtle text.
    """
    subtle_text = "there is no reason for tomorrow to arrive"
    # Ensure Tier 1 regex does not match this phrasing
    from services.intent_rules import match_crisis_regex
    assert not match_crisis_regex(subtle_text), "Tier 1 should not match this subtle utterance"

    # Mock ML models so effective_crisis_prob = 0.85
    import numpy as np
    mock_pipeline = MagicMock()
    mock_classifier = MagicMock()
    mock_classifier.classes_ = ["non_suicide", "suicide"]
    mock_pipeline.named_steps = {"classifier": mock_classifier}
    mock_pipeline.predict_proba.return_value = np.array([[0.15, 0.85]])

    with patch.object(huggingface_service, "_CRISIS_MODEL_ARTIFACT", {"pipeline": mock_pipeline, "threshold": 0.50}):
        with patch.object(huggingface_service, "_CRISIS_TRANSFORMER_PIPE", None):
            res = huggingface_service.analyze_user_message(subtle_text)
            assert res["intent"] == "SUICIDE CRISIS OR SELF HARM RISK", (
                f"Tier 2 failed to raise crisis risk: got {res['intent']}"
            )
            assert res["intent_confidence"] >= 0.50


def test_tier2_can_never_lower_or_override_tier1_flag():
    """
    Tier 1 has FINAL AUTHORITY.
    Even if Tier 2 ML models output 0.00 crisis probability, Tier 1 crisis MUST prevail.
    """
    explicit_crisis = "I want to kill myself right now"

    # Mock ML models to falsely claim 0.00 crisis probability
    import numpy as np
    mock_pipeline = MagicMock()
    mock_classifier = MagicMock()
    mock_classifier.classes_ = ["non_suicide", "suicide"]
    mock_pipeline.named_steps = {"classifier": mock_classifier}
    mock_pipeline.predict_proba.return_value = np.array([[1.0, 0.0]])

    # Mock transformer to claim 0.00 crisis
    mock_tf = MagicMock()
    mock_tf.return_value = [[{"label": "NON_SUICIDE", "score": 1.0}]]

    with patch.object(huggingface_service, "_CRISIS_MODEL_ARTIFACT", {"pipeline": mock_pipeline, "threshold": 0.50}):
        with patch.object(huggingface_service, "_CRISIS_TRANSFORMER_PIPE", mock_tf):
            res = huggingface_service.analyze_user_message(explicit_crisis)
            assert res["intent"] == "SUICIDE CRISIS OR SELF HARM RISK", (
                f"Tier 1 authority violated! ML lowered crisis flag to: {res['intent']}"
            )
            assert res["intent_confidence"] == 1.0


def test_tier2_inference_exception_fails_safe_and_preserves_tier1():
    """
    When ML inference throws an exception, the pipeline fails safe
    and preserves Tier 1 crisis flag.
    """
    crisis_text = "I am going to end my life"
    mock_pipeline = MagicMock()
    mock_pipeline.predict_proba.side_effect = RuntimeError("Inference Crash")
    mock_tf = MagicMock()
    mock_tf.side_effect = RuntimeError("Transformer inference crash")

    with patch.object(huggingface_service, "_CRISIS_MODEL_ARTIFACT", {"pipeline": mock_pipeline, "threshold": 0.50}):
        with patch.object(huggingface_service, "_CRISIS_TRANSFORMER_PIPE", mock_tf):
            res = huggingface_service.analyze_user_message(crisis_text)
            assert res["intent"] == "SUICIDE CRISIS OR SELF HARM RISK"


def test_tier2_load_exception_fails_safe():
    """
    When load_ml_pipelines crashes, safety floor should still evaluate.
    """
    crisis_text = "I am going to end my life"
    with patch.object(huggingface_service, "load_ml_pipelines", side_effect=RuntimeError("GPU OOM / Crash")):
        res = huggingface_service.analyze_user_message(crisis_text)
        assert res["intent"] == "SUICIDE CRISIS OR SELF HARM RISK"


# --------------------------------------------------------------------------- #
# 3. Robust Artifact Loading (Missing & Corrupt Files)
# --------------------------------------------------------------------------- #
def test_missing_artifacts_does_not_crash_pipeline():
    """Missing artifacts dir or files logs error without breaking analyze_user_message."""
    with patch("services.huggingface_service.Path.exists", return_value=False):
        res = huggingface_service.analyze_user_message("I am testing missing models")
        assert isinstance(res["intent"], str)


def test_corrupt_joblib_artifact_handled_gracefully():
    """A corrupt .joblib file (using temporary garbage bytes) is caught and handled."""
    with tempfile.NamedTemporaryFile(suffix=".joblib", delete=False) as tmp:
        tmp.write(b"NOT_A_VALID_JOBLIB_BINARY_DATA_CORRUPTED_BYTES")
        tmp_path = Path(tmp.name)

    try:
        import joblib
        with pytest.raises(Exception):
            # Proving that joblib.load would fail on this corrupt file
            joblib.load(tmp_path)

        # Now verify huggingface_service handles corrupt artifact safely
        with patch("services.huggingface_service.joblib.load", side_effect=Exception("Corrupt joblib stream")):
            # Reset cached global artifact
            orig_artifact = huggingface_service._CRISIS_MODEL_ARTIFACT
            try:
                huggingface_service._CRISIS_MODEL_ARTIFACT = None
                huggingface_service.load_ml_pipelines()
                res = huggingface_service.analyze_user_message("I feel anxious")
                assert isinstance(res["intent"], str)
            finally:
                huggingface_service._CRISIS_MODEL_ARTIFACT = orig_artifact
    finally:
        if tmp_path.exists():
            os.remove(tmp_path)


# --------------------------------------------------------------------------- #
# 4. Concurrency & Thread Safety
# --------------------------------------------------------------------------- #
def test_analyze_user_message_thread_safety():
    """Concurrent calls across 8 threads do not deadlock or cross-contaminate results."""
    test_inputs = [
        ("I feel okay today", False),
        ("I want to commit suicide", True),
        ("Just feeling a bit tired", False),
        ("main khudkushi karna chahta hun", True),
        ("Can we talk about school?", False),
        ("I will kill myself tonight", True),
        ("Tell me a poem", False),
        ("I want to die", True),
    ]

    results = [None] * len(test_inputs)
    errors = []

    def worker(idx, text, expect_crisis):
        try:
            r = huggingface_service.analyze_user_message(text)
            is_crisis = r["intent"] == "SUICIDE CRISIS OR SELF HARM RISK"
            results[idx] = (is_crisis, expect_crisis)
        except Exception as e:
            errors.append(f"Thread {idx} failed: {e}")

    threads = []
    for i, (txt, exp) in enumerate(test_inputs):
        t = threading.Thread(target=worker, args=(i, txt, exp))
        threads.append(t)
        t.start()

    for t in threads:
        t.join(timeout=10.0)

    assert errors == [], f"Thread execution errors: {errors}"
    for i, res in enumerate(results):
        assert res is not None, f"Thread {i} timed out"
        actual, expected = res
        assert actual == expected, f"Thread {i} got {actual}, expected {expected} for {test_inputs[i][0]}"
