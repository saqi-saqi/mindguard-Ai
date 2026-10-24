"""
unified_safety_pipeline.py
==========================
Consolidated single-pass Tier 1 Pre-LLM Deterministic Safety & Crisis Pipeline.

Replaces redundant dual-invocation (classify_safety_risk + evaluate_crisis_pipeline)
with a single authoritative execution that guarantees:
1. Upstream normalization evaluated ONCE
2. Actor/Target analysis evaluated ONCE
3. Sentence segmentation and category regexes evaluated ONCE
4. Unified hierarchical precedence arbitration
5. Complete parity with all safety invariants (homicide routing, combined crisis,
   session context tracking, emotional distress, emergency Pakistan hotlines,
   and generative LLM bypass).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("MindGuard-UnifiedSafetyPipeline")

from .text_normalizer import canonicalize_message
from .threat_actor_detector import (
    analyze_threat_actor_target,
    ThreatActorTargetResult,
    build_reported_threat_safety_message,
    build_threat_against_user_safety_message,
)
from .generalizer import preprocess_text, PreprocessResult
from .crisis_rules import (
    evaluate_crisis,
    SAFETY_RESPONSE_TEMPLATE,
    THIRD_PARTY_GUIDANCE_TEMPLATE,
    CRISIS_RESOURCES,
    SAFETY_DISCLAIMER,
    _has_unnegated_acute_crisis,
)
from .safety_classifier import (
    SafetyRiskCategory,
    HARM_TO_OTHERS_SAFETY_MESSAGE,
    COMBINED_CRISIS_SAFETY_MESSAGE,
    SELF_HARM_SAFETY_MESSAGE,
    THIRD_PARTY_SAFETY_MESSAGE,
    _CASUAL_JOKE_DAMPENERS,
    _INANIMATE_OR_METAPHOR_SUBJECTS,
    _HARM_OTHERS_NEGATIONS,
    _HARM_TO_OTHERS_PATTERNS,
    _SELF_HARM_PATTERNS,
    _THIRD_PARTY_PATTERNS,
    _DISTRESS_SIGNALS,
    _TRIVIAL_BENIGN_PATTERNS,
    _risk_level_to_priority,
    _category_from_risk_level,
)


@dataclass
class UnifiedSafetyResult:
    """
    Unified result object that provides both attribute access (for SafetyClassificationResult compatibility)
    and dict-like .get() / [] access (for evaluate_crisis_pipeline compatibility).
    """
    category: SafetyRiskCategory
    confidence: float
    matched_signals: List[str] = field(default_factory=list)
    is_crisis: bool = False
    requires_immediate_action: bool = False
    safety_message: str = ""
    reasoning: str = ""
    risk_level: str = "none"
    high_risk: bool = False
    imminent_risk: bool = False
    protective_factor: bool = False
    is_third_party: bool = False
    bypass_triggered: bool = False
    bypass_reason: Optional[str] = None
    source: str = "unified_tier1_pipeline"
    preprocess_result: Optional[PreprocessResult] = None
    rule_triggered: Optional[str] = None
    matched_categories: List[str] = field(default_factory=list)
    matched_phrases: List[str] = field(default_factory=list)
    disclaimer: str = SAFETY_DISCLAIMER
    resources: List[Dict] = field(default_factory=lambda: list(CRISIS_RESOURCES))

    def __getitem__(self, key: str) -> Any:
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(key)

    def get(self, key: str, default: Any = None) -> Any:
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)


def evaluate_unified_tier1_safety(
    raw_text: str,
    session_id: Optional[str] = None,
    context_turns: Optional[List[str]] = None,
    user_api_key: Optional[str] = None,
) -> UnifiedSafetyResult:
    """
    Single authoritative entry point for Tier 1 Deterministic Safety & Crisis Triage.
    Evaluates text normalization, threat actor/target detection, crisis regexes,
    and semantic safety in a single, non-redundant pass.
    """
    if not raw_text or not raw_text.strip():
        return UnifiedSafetyResult(
            category=SafetyRiskCategory.NONE,
            confidence=1.0,
            is_crisis=False,
            requires_immediate_action=False,
            risk_level="none",
            reasoning="Empty input",
            source="empty_input",
        )

    # 1. Single Upstream Normalization
    norm = canonicalize_message(raw_text)
    pp = preprocess_text(raw_text)

    # 2. Single Threat Actor & Target Analysis
    actor_target = analyze_threat_actor_target(raw_text)

    # 3. Idiom & Casual Joke Dampeners
    has_casual_dampener = any(pat.search(norm) for pat in _CASUAL_JOKE_DAMPENERS)
    has_inanimate_subject = any(pat.search(norm) for pat in _INANIMATE_OR_METAPHOR_SUBJECTS)
    has_others_negation = (
        (any(pat.search(norm) for pat in _HARM_OTHERS_NEGATIONS) and not (actor_target.is_threat and not actor_target.is_negated))
        or actor_target.is_negated
    )
    is_fictional = actor_target.is_fictional or pp.is_fictional

    # 4. Harm-to-Others Matching
    harm_to_others_matches = []
    if not has_inanimate_subject and not has_others_negation and not is_fictional:
        if actor_target.is_threat and actor_target.category == "HARM_TO_OTHERS_RISK":
            harm_to_others_matches.append(actor_target.raw_match or "direct_threat_to_others")
        if not (actor_target.is_threat and actor_target.category in ("REPORTED_THREAT_TO_OTHERS", "THREAT_AGAINST_USER")):
            for pat in _HARM_TO_OTHERS_PATTERNS:
                m = pat.search(norm)
                if m:
                    harm_to_others_matches.append(m.group(0))

    if has_casual_dampener and harm_to_others_matches:
        is_explicit_live_threat = (
            (actor_target.is_threat and actor_target.category == "HARM_TO_OTHERS_RISK")
            or bool(re.search(r"\b(?:tonight|today|tomorrow|now|after\s+work|right\s+now)\b", norm))
            or bool(re.search(r"\b(?:gun|knife|pistol|rifle|blade|weapon|shoot|stab|slit)\b", norm))
            or bool(re.search(r"\b(?:i\s+will|i'll|i\s+am\s+going\s+to|i'?m\s+gonna|brought|bring|plan\s+to)\s+(?:kill|murder|shoot|stab)\b", norm))
        )
        if not is_explicit_live_threat:
            harm_to_others_matches = []

    # 5. Deterministic Crisis Engine (Evaluated ONCE)
    det_res = evaluate_crisis(pp.text, preprocess_result=pp)
    
    # Check self-harm matches
    self_harm_matches = []
    is_negated_or_bypassed = det_res.get("bypass_triggered", False) and not _has_unnegated_acute_crisis(raw_text)

    if not is_negated_or_bypassed and not is_fictional:
        if actor_target.is_threat and actor_target.category == "SELF_HARM_RISK":
            self_harm_matches.append(actor_target.raw_match or "direct_self_harm")
        if not (actor_target.is_threat and actor_target.category in ("REPORTED_THREAT_TO_OTHERS", "THIRD_PARTY_REPORT")):
            for pat in _SELF_HARM_PATTERNS:
                m = pat.search(norm)
                if m:
                    self_harm_matches.append(m.group(0))

        if det_res.get("is_crisis"):
            matched_cats = det_res.get("matched_categories", [])
            tier1_self_cats = [c for c in matched_cats if c != "direct_threat_to_others"]
            tier1_others_cats = [c for c in matched_cats if c == "direct_threat_to_others"]
            if tier1_others_cats and not harm_to_others_matches:
                if not (actor_target.is_threat and actor_target.category in ("REPORTED_THREAT_TO_OTHERS", "THREAT_AGAINST_USER", "THIRD_PARTY_REPORT")):
                    harm_to_others_matches.append("tier1_direct_threat_to_others")
            if tier1_self_cats and not self_harm_matches:
                if not (actor_target.is_threat and actor_target.category in ("REPORTED_THREAT_TO_OTHERS", "THIRD_PARTY_REPORT")):
                    self_harm_matches.append("tier1_deterministic_crisis")

    # 6. Combined Crisis Matching (Same Turn + Cross Turn)
    has_combined_same_turn = bool(harm_to_others_matches and self_harm_matches)
    if not has_combined_same_turn and harm_to_others_matches:
        if re.search(
            r"\b(?:and|then|after\s+that|phir)\s+(?:also\s+)?(?:then\s+)?(?:myself|me|end\s+it\s+all|end\s+my\s+(?:own\s+)?life|kill\s+myself|take\s+my\s+own\s+life|turn\s+the\s+(?:gun|weapon)\s+on\s+myself|khud\s+ko\s+bhi\s+khatam|i'?m\s+gone|i\s+am\s+gone|done\s+living|commit\s+suicide|die)\b",
            norm
        ):
            has_combined_same_turn = True
            self_harm_matches.append("combined_self_target")
    if not has_combined_same_turn and self_harm_matches:
        if re.search(r"\b(?:and|then|after\s+that)\s+(?:also\s+)?(?:then\s+)?(?:kill|murder|hurt|harm|attack|stab|shoot)\s+(?:someone|them|him|her|[a-z]+)\b", norm):
            has_combined_same_turn = True
            harm_to_others_matches.append("combined_other_target")
    if re.search(r"\bnext\s+on\s+my\s+killing\s+list\s+is\s+me\b", norm) or (
        re.search(r"\bkilling\s+list\b", norm) and re.search(r"\bis\s+me\b|\band\s+(?:then\s+)?(?:me|myself)\b", norm)
    ):
        has_combined_same_turn = True

    has_combined_adjacent = False
    if session_id:
        try:
            from .session_context import get_session_context
            session_ctx = get_session_context(session_id)
            if harm_to_others_matches and session_ctx.had_self_harm_recently(120.0):
                has_combined_adjacent = True
            elif self_harm_matches and session_ctx.had_harm_to_others_recently(120.0):
                has_combined_adjacent = True
        except Exception:
            pass

    if context_turns and len(context_turns) > 0:
        last_turn_norm = canonicalize_message(context_turns[-1])
        last_had_others_threat = any(p.search(last_turn_norm) for p in _HARM_TO_OTHERS_PATTERNS) and not any(
            p.search(last_turn_norm) for p in _CASUAL_JOKE_DAMPENERS
        )
        last_had_self_harm = any(p.search(last_turn_norm) for p in _SELF_HARM_PATTERNS)
        if (last_had_others_threat and self_harm_matches) or (last_had_self_harm and harm_to_others_matches):
            has_combined_adjacent = True

    # 7. Third-Party & Threat Against User Matching
    third_party_matches = []
    threat_against_user_matches = []
    reported_threat_to_others_matches = []

    if not is_fictional and not has_others_negation:
        if actor_target.is_threat:
            if actor_target.category == "THREAT_AGAINST_USER":
                threat_against_user_matches.append(actor_target.raw_match or "threat_against_user")
            elif actor_target.category == "REPORTED_THREAT_TO_OTHERS":
                reported_threat_to_others_matches.append(actor_target.raw_match or "reported_threat_to_others")
            elif actor_target.category == "THIRD_PARTY_REPORT":
                third_party_matches.append(actor_target.raw_match or "third_party_report")

    if not harm_to_others_matches and not self_harm_matches and not threat_against_user_matches and not reported_threat_to_others_matches and not has_others_negation and not is_fictional:
        if pp.is_third_party:
            third_party_matches.append("third_party_subject")
        for pat in _THIRD_PARTY_PATTERNS:
            m = pat.search(norm)
            if m:
                if not re.search(r"\bi\s+(?:told|said\s+to|threatened)\s+my\b", norm):
                    third_party_matches.append(m.group(0))

    # 8. Deterministic Precedence Resolution
    if has_combined_same_turn or has_combined_adjacent:
        det_risk_level = "COMBINED_HIGH_CRISIS"
    elif threat_against_user_matches:
        det_risk_level = "THREAT_AGAINST_USER"
    elif harm_to_others_matches:
        det_risk_level = "HARM_TO_OTHERS_RISK"
    elif self_harm_matches:
        det_risk_level = "SELF_HARM_RISK"
    elif reported_threat_to_others_matches:
        det_risk_level = "REPORTED_THREAT_TO_OTHERS"
    elif third_party_matches:
        det_risk_level = "THIRD_PARTY_REPORT"
    elif any(pat.search(norm) for pat in _DISTRESS_SIGNALS):
        det_risk_level = "EMOTIONAL_DISTRESS"
    else:
        det_risk_level = "NONE"

    # 9. Semantic Safety Classifier (Tier 3)
    sem_risk_level = "NONE"
    sem_confidence = 0.0
    sem_rationale = ""
    is_trivial_benign = any(pat.match(norm) for pat in _TRIVIAL_BENIGN_PATTERNS)

    _skip_semantic = (
        is_trivial_benign
        or det_risk_level in ("COMBINED_HIGH_CRISIS", "THREAT_AGAINST_USER", "HARM_TO_OTHERS_RISK", "REPORTED_THREAT_TO_OTHERS")
        or (det_risk_level == "NONE" and (has_inanimate_subject or is_fictional or has_others_negation or det_res.get("bypass_triggered")))
    )

    if not _skip_semantic:
        try:
            ctx_descriptor = None
            if session_id:
                from .session_context import get_session_context
                s_ctx = get_session_context(session_id)
                recent = s_ctx.recent_events(120.0)
                if recent:
                    prior_risks = [e.risk_level for e in recent if e.risk_level not in ("NONE", "EMOTIONAL_DISTRESS")]
                    if prior_risks:
                        ctx_descriptor = f"Cross-turn context: prior turn safety signals detected: {', '.join(prior_risks[:3])}."

            from .semantic_safety_classifier import classify_semantically
            sem_result = classify_semantically(text=raw_text, cross_turn_context=ctx_descriptor, api_key=user_api_key)
            if sem_result:
                sem_risk_level = sem_result.get("risk_level", "NONE")
                sem_confidence = float(sem_result.get("confidence", 0.0))
                sem_rationale = sem_result.get("rationale", "")
        except Exception as sem_err:
            logger.warning("Semantic safety classifier error in unified pipeline: %s", sem_err)

    # 10. Authority Arbitration
    det_priority = _risk_level_to_priority(det_risk_level)
    sem_priority = _risk_level_to_priority(sem_risk_level)

    if det_priority >= sem_priority:
        final_risk_level = det_risk_level
        winning_source = "deterministic"
    else:
        if sem_confidence >= 0.70:
            final_risk_level = sem_risk_level
            winning_source = "semantic"
        else:
            final_risk_level = det_risk_level
            winning_source = "deterministic_low_sem_conf"

    # 11. Record to Session Context
    if session_id:
        try:
            from .session_context import record_safety_event
            record_safety_event(
                session_id=session_id,
                risk_level=final_risk_level,
                category=final_risk_level,
                confidence=max(0.95 if det_priority > 0 else 0.0, sem_confidence),
                has_harm_to_others=bool(harm_to_others_matches) or final_risk_level in ("HARM_TO_OTHERS_RISK", "COMBINED_HIGH_CRISIS"),
                has_self_harm=bool(self_harm_matches) or final_risk_level in ("SELF_HARM_RISK", "HIGH_CRISIS", "COMBINED_HIGH_CRISIS"),
                has_weapon_mention=bool(re.search(r"\b(?:gun|knife|blade|pistol|rifle|weapon|razor)\b", norm)),
                source=winning_source,
            )
        except Exception:
            pass

    # 12. Build Consolidated Result
    final_category = _category_from_risk_level(final_risk_level)
    is_crisis = final_category in (
        SafetyRiskCategory.COMBINED_HIGH_CRISIS,
        SafetyRiskCategory.THREAT_AGAINST_USER,
        SafetyRiskCategory.HARM_TO_OTHERS_RISK,
        SafetyRiskCategory.SELF_HARM_RISK,
    )
    is_third_party = final_category in (
        SafetyRiskCategory.REPORTED_THREAT_TO_OTHERS,
        SafetyRiskCategory.THIRD_PARTY_REPORT,
    )
    requires_action = is_crisis

    matched_signals = (
        (harm_to_others_matches or [])
        + (self_harm_matches or [])
        + (third_party_matches or [])
        + (threat_against_user_matches or [])
        + (reported_threat_to_others_matches or [])
    )
    if actor_target.is_threat and actor_target.raw_match:
        matched_signals.append(f"actor_target:{actor_target.category}")
    if winning_source == "semantic" and sem_rationale:
        matched_signals.append(f"semantic:{sem_rationale[:80]}")

    if final_risk_level == "COMBINED_HIGH_CRISIS":
        if has_combined_adjacent:
            matched_signals.append("cross_turn_adjacent_threat")
        safety_msg = COMBINED_CRISIS_SAFETY_MESSAGE
        reasoning = "Harm-to-others combined with self-harm intent detected"
        confidence = 0.99
        api_risk_label = "COMBINED_HIGH_CRISIS"
    elif final_risk_level == "THREAT_AGAINST_USER":
        safety_msg = build_threat_against_user_safety_message(actor=actor_target.actor)
        reasoning = "User reporting a direct threat against themselves"
        confidence = 0.98
        api_risk_label = "THREAT_AGAINST_USER"
    elif final_risk_level == "HARM_TO_OTHERS_RISK":
        safety_msg = HARM_TO_OTHERS_SAFETY_MESSAGE.replace("• Umang Pakistan Mental Health Helpline: 0311-7786264 (24/7 free support)\n", "")
        reasoning = "Direct credible threat to another person detected"
        confidence = 0.98
        api_risk_label = "HARM_TO_OTHERS_RISK"
    elif final_risk_level == "REPORTED_THREAT_TO_OTHERS":
        safety_msg = build_reported_threat_safety_message(actor=actor_target.actor, target=actor_target.target)
        reasoning = "Reported third-party threat to another person"
        confidence = 0.96
        api_risk_label = "REPORTED_THREAT_TO_OTHERS"
    elif final_risk_level in ("SELF_HARM_RISK", "HIGH_CRISIS"):
        safety_msg = SELF_HARM_SAFETY_MESSAGE
        reasoning = "Self-harm or suicidal intent detected"
        confidence = 0.98
        api_risk_label = "HIGH_CRISIS"
    elif final_risk_level == "THIRD_PARTY_REPORT":
        safety_msg = THIRD_PARTY_SAFETY_MESSAGE
        reasoning = "Third-party risk disclosure reported"
        confidence = 0.95
        api_risk_label = "THIRD_PARTY_REPORT"
    elif final_risk_level == "EMOTIONAL_DISTRESS":
        safety_msg = ""
        reasoning = "Emotional distress without crisis intent"
        confidence = 0.85
        api_risk_label = "ELEVATED_DISTRESS"
    else:
        safety_msg = ""
        reasoning = "No acute safety risk detected"
        confidence = 0.95
        api_risk_label = "none"

    return UnifiedSafetyResult(
        category=final_category,
        confidence=confidence,
        matched_signals=matched_signals,
        is_crisis=is_crisis,
        requires_immediate_action=requires_action,
        safety_message=safety_msg,
        reasoning=reasoning,
        risk_level=api_risk_label,
        high_risk=(api_risk_label in ("HIGH_CRISIS", "COMBINED_HIGH_CRISIS", "HARM_TO_OTHERS_RISK", "THREAT_AGAINST_USER")),
        imminent_risk=(api_risk_label in ("HIGH_CRISIS", "COMBINED_HIGH_CRISIS", "THREAT_AGAINST_USER")),
        is_third_party=is_third_party,
        bypass_triggered=det_res.get("bypass_triggered", False),
        bypass_reason=det_res.get("bypass_reason"),
        source=winning_source,
        preprocess_result=pp,
        rule_triggered=matched_signals[0] if matched_signals else None,
        matched_categories=det_res.get("matched_categories", []),
        matched_phrases=det_res.get("matched_phrases", []),
    )
