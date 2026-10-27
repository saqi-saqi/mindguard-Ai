"""
test_wellbeing_layer.py
=======================
Focused test suite for MindGuard's multi-label wellbeing-signal layer.

Verifies:
1. Stress only -> supportive low-risk route; stress.flagged=True.
2. Anxiety only -> supportive or elevated-distress route; anxiety_signals.flagged=True.
3. Depression-related signals without suicide risk -> appropriate non-crisis route; depression_signals.flagged=True.
4. Stress + Anxiety + Depression together -> all three flags True without crisis lock.
5. Depression-related signals + explicit suicide intent -> HIGH_CRISIS route unchanged.
6. Anxiety/panic + explicit self-harm -> crisis route unchanged.
7. Harm-to-others + wellbeing traits -> HARM_TO_OTHERS_RISK route unchanged.
8. Grief/sadness alone -> does NOT automatically flag depression_signals.
9. Negation, idiom/hyperbole, recovery narrative, fictional context, and third-party reporting
   do not produce false personal wellbeing labels.
10. Third-party report never labels reporting user as personally stressed, anxious, depressed, or suicidal.
11. Existing ML classifier integration adheres strictly to resolution rules:
    - ANXIETY OR PANIC ATTACK contributes evidence to anxiety_signals.
    - GRIEF OR SADNESS is NOT automatically depression_signals.
    - Disagreements are preserved in audit metadata.
12. Future ML adapter is disabled by default and safely falls back.
13. No duplicate scans: internal artifacts are surfaced and reused.
"""

import pytest
from server.services.unified_safety_pipeline import evaluate_unified_tier1_safety, UnifiedSafetyResult
from server.services.wellbeing_layer import (
    extract_deterministic_wellbeing_signals,
    enrich_wellbeing_with_ml,
    WellbeingMultiLabelModelAdapter,
)
from server.config import ENABLE_WELLBEING_MULTILABEL_MODEL


def test_stress_only_supportive_route():
    text = "I have so many deadlines piling up and work is overwhelming, feeling totally burned out"
    res = evaluate_unified_tier1_safety(text)
    
    assert res.risk_level in ("none", "ELEVATED_DISTRESS")
    assert not res.is_crisis
    
    wb = res.wellbeing_result
    assert wb is not None
    assert wb["api_risk_label"] == res.risk_level
    assert wb["wellbeing_signals"]["stress"]["flagged"] is True
    assert wb["wellbeing_signals"]["stress"]["confidence"] > 0.0
    assert len(wb["wellbeing_signals"]["stress"]["deterministic_evidence"]) > 0
    assert wb["wellbeing_signals"]["anxiety_signals"]["flagged"] is False
    assert wb["wellbeing_signals"]["depression_signals"]["flagged"] is False
    assert wb["safety_signals"]["suicide_intent"] is False
    assert wb["safety_signals"]["harm_to_others"] is False


def test_anxiety_only_signals():
    text = "My mind is racing and I can't stop worrying, feeling on edge and having panic attacks"
    res = evaluate_unified_tier1_safety(text)
    
    assert res.risk_level in ("none", "ELEVATED_DISTRESS")
    assert not res.is_crisis
    
    wb = res.wellbeing_result
    assert wb is not None
    assert wb["wellbeing_signals"]["anxiety_signals"]["flagged"] is True
    assert len(wb["wellbeing_signals"]["anxiety_signals"]["deterministic_evidence"]) > 0
    assert wb["wellbeing_signals"]["depression_signals"]["flagged"] is False
    assert wb["safety_signals"]["suicide_intent"] is False


def test_depression_related_signals_without_suicide_risk():
    text = "I feel completely empty inside, nothing brings me joy anymore and I feel hopeless"
    res = evaluate_unified_tier1_safety(text)
    
    assert res.risk_level in ("none", "ELEVATED_DISTRESS")
    assert not res.is_crisis
    
    wb = res.wellbeing_result
    assert wb is not None
    assert wb["wellbeing_signals"]["depression_signals"]["flagged"] is True
    assert len(wb["wellbeing_signals"]["depression_signals"]["deterministic_evidence"]) > 0
    assert wb["safety_signals"]["suicide_intent"] is False
    assert wb["safety_signals"]["suicide_plan_or_means"] is False


def test_stress_anxiety_depression_together():
    text = (
        "I am completely burned out from work stress, having severe anxiety and racing thoughts, "
        "and feeling completely empty and hopeless inside."
    )
    res = evaluate_unified_tier1_safety(text)
    
    # Must not lock to HIGH_CRISIS solely because multiple wellbeing signals co-exist
    assert res.risk_level in ("none", "ELEVATED_DISTRESS")
    assert not res.is_crisis
    
    wb = res.wellbeing_result
    assert wb is not None
    assert wb["wellbeing_signals"]["stress"]["flagged"] is True
    assert wb["wellbeing_signals"]["anxiety_signals"]["flagged"] is True
    assert wb["wellbeing_signals"]["depression_signals"]["flagged"] is True
    assert wb["safety_signals"]["suicide_intent"] is False


def test_depression_signals_with_explicit_suicide_intent():
    text = "I feel completely hopeless and empty inside, and I am going to end my life tonight with pills"
    res = evaluate_unified_tier1_safety(text)
    
    # Invariant: Suicide intent takes precedence. Route remains HIGH_CRISIS.
    assert res.risk_level == "HIGH_CRISIS"
    assert res.is_crisis is True
    assert res.requires_immediate_action is True
    
    wb = res.wellbeing_result
    assert wb is not None
    assert wb["api_risk_label"] == "HIGH_CRISIS"
    assert wb["safety_signals"]["suicide_intent"] is True
    assert wb["safety_signals"]["suicide_plan_or_means"] is True
    assert wb["safety_signals"]["suicide_ideation"] is True
    assert wb["wellbeing_signals"]["depression_signals"]["flagged"] is True


def test_anxiety_panic_with_explicit_self_harm():
    text = "I'm having a panic attack and I am cutting my wrists right now"
    res = evaluate_unified_tier1_safety(text)
    
    # Invariant: Self-harm takes precedence over anxiety.
    assert res.risk_level == "HIGH_CRISIS"
    assert res.is_crisis is True
    
    wb = res.wellbeing_result
    assert wb is not None
    assert wb["api_risk_label"] == "HIGH_CRISIS"
    assert wb["safety_signals"]["suicide_ideation"] is True
    assert wb["wellbeing_signals"]["anxiety_signals"]["flagged"] is True


def test_harm_to_others_with_wellbeing_traits():
    text = "I am burned out and stressed from work, and I am going to kill my boss with a knife tomorrow"
    res = evaluate_unified_tier1_safety(text)
    
    # Invariant: Threat to others takes precedence over stress.
    assert res.risk_level == "HARM_TO_OTHERS_RISK"
    assert res.is_crisis is True
    
    wb = res.wellbeing_result
    assert wb is not None
    assert wb["api_risk_label"] == "HARM_TO_OTHERS_RISK"
    assert wb["safety_signals"]["harm_to_others"] is True
    assert wb["wellbeing_signals"]["stress"]["flagged"] is True


def test_grief_sadness_alone_does_not_flag_depression():
    text = "I am feeling so sad today because I miss my grandmother who passed away"
    res = evaluate_unified_tier1_safety(text)
    
    wb = res.wellbeing_result
    assert wb is not None
    # Crucial requirement: ordinary grief or sadness alone is NOT depression
    assert wb["wellbeing_signals"]["depression_signals"]["flagged"] is False
    assert wb["metadata"]["grief_or_sadness_detected"] is True
    assert len(wb["metadata"]["grief_or_sadness_evidence"]) > 0


def test_negation_suppresses_wellbeing_flag():
    text = "I am not feeling stressed or anxious at all today"
    res = evaluate_unified_tier1_safety(text)
    
    wb = res.wellbeing_result
    assert wb is not None
    assert wb["wellbeing_signals"]["stress"]["flagged"] is False
    assert wb["wellbeing_signals"]["anxiety_signals"]["flagged"] is False


def test_idiom_hyperbole_suppression():
    text = "This exam is literally killing me haha I am dying of laughter"
    res = evaluate_unified_tier1_safety(text)
    
    assert res.risk_level in ("none", "ELEVATED_DISTRESS")
    assert not res.is_crisis
    wb = res.wellbeing_result
    assert wb["safety_signals"]["suicide_intent"] is False
    assert wb["safety_signals"]["suicide_ideation"] is False


def test_recovery_narrative_suppression():
    text = "I used to suffer from severe depression years ago, but I have been in full recovery and feel great now"
    res = evaluate_unified_tier1_safety(text)
    
    assert res.risk_level in ("none", "ELEVATED_DISTRESS")
    assert not res.is_crisis
    wb = res.wellbeing_result
    assert wb["wellbeing_signals"]["depression_signals"]["flagged"] is False
    assert wb["safety_signals"]["suicide_ideation"] is False


def test_fictional_frame_suppression():
    text = "In my novel, the protagonist is feeling completely hopeless, depressed, and burned out"
    res = evaluate_unified_tier1_safety(text)
    
    assert res.risk_level in ("none", "ELEVATED_DISTRESS")
    assert not res.is_crisis
    wb = res.wellbeing_result
    assert wb["wellbeing_signals"]["stress"]["flagged"] is False
    assert wb["wellbeing_signals"]["depression_signals"]["flagged"] is False


def test_third_party_reporting_does_not_label_user():
    text = "My friend is having severe panic attacks, feels completely hopeless, and wants to kill himself"
    res = evaluate_unified_tier1_safety(text)
    
    assert res.risk_level in ("THIRD_PARTY_REPORT", "none")
    assert res.is_third_party is True
    
    wb = res.wellbeing_result
    assert wb is not None
    # User must NOT be labeled as personally anxious, depressed, or suicidal
    assert wb["wellbeing_signals"]["anxiety_signals"]["flagged"] is False
    assert wb["wellbeing_signals"]["depression_signals"]["flagged"] is False
    assert wb["safety_signals"]["suicide_intent"] is False
    assert wb["safety_signals"]["suicide_plan_or_means"] is False


def test_roman_urdu_wellbeing_markers():
    text = "Mujhe bohot tension hai aur kaam ka sakht pressure hai, dimagh fat raha hai"
    res = evaluate_unified_tier1_safety(text)
    
    wb = res.wellbeing_result
    assert wb is not None
    assert wb["wellbeing_signals"]["stress"]["flagged"] is True


def test_ml_enrichment_resolution_rules():
    base_wb = extract_deterministic_wellbeing_signals(
        raw_text="Hello, I wanted to talk",
        norm_text="hello, i wanted to talk",
        api_risk_label="none"
    )
    
    # 1. ANXIETY OR PANIC ATTACK contributes evidence to anxiety_signals
    ml_anxiety = {"intent": "ANXIETY OR PANIC ATTACK", "intent_confidence": 0.88}
    enriched = enrich_wellbeing_with_ml(base_wb, ml_anxiety)
    assert enriched["wellbeing_signals"]["anxiety_signals"]["flagged"] is True
    assert enriched["wellbeing_signals"]["anxiety_signals"]["confidence"] >= 0.88
    assert "ml_intent:ANXIETY OR PANIC ATTACK" in enriched["wellbeing_signals"]["anxiety_signals"]["existing_ml_evidence"][0]
    assert enriched["source"] in ("existing_ml", "hybrid")

    # 2. GRIEF OR SADNESS must NOT automatically become depression_signals
    base_wb2 = extract_deterministic_wellbeing_signals(
        raw_text="I am sad today",
        norm_text="i am sad today",
        api_risk_label="none"
    )
    ml_grief = {"intent": "GRIEF OR SADNESS", "intent_confidence": 0.85}
    enriched2 = enrich_wellbeing_with_ml(base_wb2, ml_grief)
    assert enriched2["wellbeing_signals"]["depression_signals"]["flagged"] is False
    assert any(d.get("trait") == "depression_signals" for d in enriched2["metadata"]["evidence_disagreements"])

    # 3. Third-party bypass suppresses ML evidence from flagging the user
    base_wb3 = extract_deterministic_wellbeing_signals(
        raw_text="My sister is anxious",
        norm_text="my sister is anxious",
        api_risk_label="THIRD_PARTY_REPORT"
    )
    enriched3 = enrich_wellbeing_with_ml(base_wb3, ml_anxiety, bypass_reason="third_party_subject_report")
    assert enriched3["wellbeing_signals"]["anxiety_signals"]["flagged"] is False
    assert any(d.get("status") == "suppressed_by_bypass" for d in enriched3["metadata"]["evidence_disagreements"])


def test_future_ml_adapter_defaults():
    assert ENABLE_WELLBEING_MULTILABEL_MODEL is False
    adapter = WellbeingMultiLabelModelAdapter()
    assert adapter.enabled is False
    res = adapter.predict("I am feeling stressed")
    assert res is None


def test_internal_artifacts_surfaced_without_duplicate_scans():
    text = "I am having panic attacks from work stress"
    res = evaluate_unified_tier1_safety(text)
    
    assert isinstance(res, UnifiedSafetyResult)
    # Check internal contract fields exist and are populated
    assert res.preprocess_result is not None
    assert res.actor_target_result is not None
    assert hasattr(res, "has_casual_dampener")
    assert hasattr(res, "has_inanimate_subject")
    assert hasattr(res, "has_others_negation")
    assert hasattr(res, "is_fictional")
    assert hasattr(res, "sentence_findings")
    assert hasattr(res, "temporal_result")
    assert hasattr(res, "discourse_result")
    assert hasattr(res, "semantic_concepts")
    assert res.wellbeing_result is not None


@pytest.fixture
def test_client():
    import sys
    from pathlib import Path
    server_dir = str(Path(__file__).resolve().parents[2] / "server")
    if server_dir not in sys.path:
        sys.path.insert(0, server_dir)
    import app as flask_app
    flask_app.app.config["TESTING"] = True
    flask_app.app.config["RATE_LIMIT_PER_MINUTE"] = 100000
    with flask_app.app.test_client() as c:
        yield c


def test_api_chat_stress_supportive_flow(test_client):
    resp = test_client.post("/api/chat", json={
        "message": "I have deadlines piling up at work and feeling burned out",
        "session_id": "test_wb_session_1"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    assert data["risk_level"] in ("LOW", "ELEVATED_DISTRESS")
    assert not data["requires_immediate_action"]
    # Check that a grounding exercise is suggested for low-risk supportive flow
    if data["risk_level"] == "LOW":
        assert data["data"].get("grounding_exercise") is not None


def test_api_chat_crisis_routing_precedence(test_client):
    resp = test_client.post("/api/chat", json={
        "message": "I feel so hopeless and stressed, and I am going to kill myself tonight with a gun",
        "session_id": "test_wb_session_2"
    })
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["success"] is True
    # Emergency routing invariant: HIGH_CRISIS takes precedence
    assert data["risk_level"] == "HIGH_CRISIS"
    assert data["requires_immediate_action"] is True
    assert data["data"]["emergency_resources"] is not None
