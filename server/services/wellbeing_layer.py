"""
wellbeing_layer.py
==================
Multi-label wellbeing-signal and safety-signal detection layer for MindGuard.

Detects independent co-existing dimensions:
- Wellbeing traits (non-clinical signals):
  - stress
  - anxiety_signals
  - depression_signals
- Safety-risk classifications (always take precedence):
  - suicide_ideation
  - suicide_intent
  - suicide_plan_or_means
  - harm_to_others

Safety Principles:
1. Non-diagnostic: Uses descriptive labels like "anxiety signals" and "depression-related signals",
   never clinical diagnoses ("the user has anxiety/depression").
2. Precedence: Suicide and harm-to-others are safety-risk classifications, NOT ordinary wellbeing
   traits. They take absolute precedence over stress, anxiety, and depression signals.
3. Canonical Routing: Preserves existing unified pipeline api_risk_label / risk_level verbatim:
   COMBINED_HIGH_CRISIS, THREAT_AGAINST_USER, HARM_TO_OTHERS_RISK, REPORTED_THREAT_TO_OTHERS,
   HIGH_CRISIS, THIRD_PARTY_REPORT, ELEVATED_DISTRESS, none.
4. Non-escalation: Stress, anxiety, or depression signals alone never cause a crisis lock.
5. Ordinary grief or sadness alone does not automatically flag depression_signals without
   independent depression-related evidence.
6. Third-party reports never label the reporting user as personally stressed, anxious,
   depressed, or suicidal.
7. Zero-duplicate scanning: Reuses existing normalized text, PreprocessResult, actor/target
   results, sentence findings, temporal/discourse results, and ML outputs.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("MindGuard-WellbeingLayer")

try:
    from config import ENABLE_WELLBEING_MULTILABEL_MODEL
except ImportError:
    ENABLE_WELLBEING_MULTILABEL_MODEL = False

from .generalizer import PreprocessResult
from .threat_actor_detector import ThreatActorTargetResult


# ---------------------------------------------------------------------------
# Pre-compiled Regex Patterns for Wellbeing Extraction
# ---------------------------------------------------------------------------

def _c(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


# 1. Stress Patterns (overload, pressure, burnout, deadlines, exhaustion, conflict, financial/work/academic strain)
_STRESS_PATTERNS = [
    _c(r"\b(?:overwhelmed|too\s+much\s+pressure|under\s+(?:a\s+lot\s+of\s+|so\s+much\s+|intense\s+|immense\s+)?pressure|feeling\s+pressured|can'?t\s+handle\s+(?:all\s+this|the\s+pressure|everything)|drowning\s+in\s+(?:work|responsibilities|chores))\b"),
    _c(r"\b(?:burnout|burned\s+out|burnt\s+out|chronically\s+exhausted|mental(?:ly)?\s+exhaust(?:ed|ion)|exhaustion|running\s+on\s+empty|running\s+on\s+fumes|drained\s+and\s+exhausted|so\s+stressed|stressing\s+out)\b"),
    _c(r"\b(?:deadline(?:s)?\s+(?:piling|looming|are\s+killing|tomorrow)|work(?:place)?\s+stress|stressed\s+(?:at|with|by|about|from)\s+(?:work|job|boss|school|college|uni|university|exams?)|exam\s+stress|finals\s+stress|academic\s+(?:pressure|strain|stress)|job\s+stress)\b"),
    _c(r"\b(?:financial\s+(?:stress|strain|crisis|burden|pressure)|money\s+stress|can'?t\s+pay\s+(?:my\s+)?bills|fighting\s+with\s+(?:my\s+)?(?:family|parents|spouse|partner|boss)|constant\s+(?:conflict|arguments)|relationship\s+strain)\b"),
    # Roman Urdu & Urdu markers
    _c(r"\b(?:bohot\s+tension\s+hai|kaam\s+ka\s+(?:bohot\s+)?load|parhai\s+ka\s+stress|sakht\s+pressure|paison\s+ki\s+tension|dimagh\s+fat\s+raha\s+hai|bohot\s+stress\s+hai|zehni\s+dabao|tension\s+mein\s+hoo?n|thak\s+chuka\s+hoo?n\s+kaam\s+se)\b"),
]

# 2. Anxiety Signals Patterns (excessive worry, panic, fear, restlessness, tension, racing thoughts, concentration/sleep difficulty)
_ANXIETY_PATTERNS = [
    _c(r"\b(?:can'?t\s+stop\s+worrying|constant\s+worry(?:ing)?|worrying\s+constantly|so\s+worried|terrified\s+that|paralyzed\s+by\s+fear|fearful|intense\s+fear|feeling\s+of\s+dread|sense\s+of\s+impending\s+doom)\b"),
    _c(r"\b(?:panic\s+attack(?:s)?|having\s+a\s+panic\s+attack|sudden\s+panic|panicking|hyperventilating|heart\s+racing\s+(?:from|with)\s+(?:anxiety|fear|panic)|chest\s+tightness\s+from\s+anxiety)\b"),
    _c(r"\b(?:feeling\s+restless|restlessness|on\s+edge|keyed\s+up|shaking\s+from\s+(?:nerves|anxiety)|nervous\s+wreck|feeling\s+jittery|can'?t\s+sit\s+still|severe\s+anxiety|anxious\s+feelings?|feeling\s+anxious|so\s+anxious)\b"),
    _c(r"\b(?:racing\s+thoughts|mind\s+is\s+racing|mind\s+won'?t\s+(?:slow\s+down|stop|shut\s+off)|brain\s+won'?t\s+shut\s+off|can'?t\s+concentrate\s+because\s+of\s+(?:anxiety|worry))\b"),
    _c(r"\b(?:can'?t\s+sleep\s+because\s+(?:of\s+worry|my\s+mind\s+is\s+racing|i'?m\s+anxious)|lying\s+awake\s+(?:worrying|anxious)|insomnia\s+from\s+anxiety)\b"),
    # Roman Urdu & Urdu markers
    _c(r"\b(?:ghabrahat|dil\s+ghabra\s+raha\s+hai|bechaini|dar\s+lag\s+raha\s+hai|sans\s+phool\s+rahi\s+hai|khauf\s+aa\s+raha\s+hai|dil\s+tez\s+dharak\s+raha\s+hai|soch\s+band\s+nahi\s+ho\s+rahi|anxiety\s+ho\s+rahi\s+hai)\b"),
]

# 3. Depression-Related Signals Patterns (persistent sadness/emptiness, loss of interest, hopelessness, low energy, worthlessness, withdrawal)
_DEPRESSION_PATTERNS = [
    _c(r"\b(?:feel(?:ing)?\s+(?:completely\s+|totally\s+|so\s+|deeply\s+)?(?:empty|hopeless|worthless|numb|depressed)|deep\s+emptiness|persistent\s+sadness|crying\s+every\s+day\s+for\s+weeks|numb\s+inside|feeling\s+numb|emotional\s+numbness|constant\s+darkness|depression-related\s+feelings?|feeling\s+depressed)\b"),
    _c(r"\b(?:lost\s+interest\s+in\s+everything|nothing\s+brings\s+me\s+joy|don'?t\s+enjoy\s+anything\s+anymore|no\s+pleasure\s+in\s+anything|lost\s+passion\s+for\s+everything|don'?t\s+care\s+about\s+anything\s+i\s+used\s+to\s+love)\b"),
    _c(r"\b(?:hopeless|hopelessness|feeling\s+(?:completely\s+|totally\s+)?hopeless|no\s+hope\s+left|nothing\s+will\s+ever\s+get\s+better|no\s+future\s+for\s+me|what'?s\s+the\s+point\s+of\s+(?:anything|trying|life)|everything\s+is\s+pointless)\b"),
    _c(r"\b(?:worthless|feel\s+worthless|feeling\s+worthless|i'?m\s+worthless|feel\s+like\s+a\s+burden|i'?m\s+just\s+a\s+burden|feeling\s+like\s+a\s+failure|i'?m\s+a\s+complete\s+failure|no\s+energy\s+to\s+(?:get\s+out\s+of\s+bed|do\s+anything))\b"),
    _c(r"\b(?:haven'?t\s+showered\s+in\s+days|can'?t\s+(?:even\s+)?get\s+out\s+of\s+bed|isolating\s+myself\s+from\s+everyone|withdrawing\s+from\s+(?:all\s+)?my\s+friends|stopped\s+talking\s+to\s+everyone|can'?t\s+function\s+anymore)\b"),
    # Roman Urdu & Urdu markers
    _c(r"\b(?:koi\s+umeed\s+nahi|zindagi\s+be-?maqsad\s+lagti\s+hai|khali\s*pan|kisi\s+cheez\s+mein\s+dil\s+nahi\s+lagta|main\s+bilkul\s+bekaar\s+hoo?n|bistar\s+se\s+uthne\s+ki\s+himmat\s+nahi|kuch\s+acha\s+nahi\s+lagta|dil\s+udas\s+rehta\s+hai|depressed\s+hoo?n)\b"),
]

# 4. Ordinary Grief or Sadness Patterns (Non-depression by default unless independent depression markers exist)
_GRIEF_SADNESS_PATTERNS = [
    _c(r"\b(?:sad|sadness|grief|grieving|mourning|feeling\s+down\s+today|unhappy\s+today|crying\s+today)\b"),
    _c(r"\b(?:lost\s+my\s+(?:grandmother|grandfather|grandma|grandpa|mother|father|mom|dad|dog|cat|pet)|passed\s+away|miss\s+my\s+\w+)\b"),
]

# 5. Local Negation Window Helper Pattern
_LOCAL_NEGATION_RE = _c(
    r"\b(?:not|no|never|don'?t|doesn'?t|didn'?t|won'?t|haven'?t|hasn'?t|without|nahi|nahin|nai|nhe)\b"
)

# 6. Third-party sentence subject pattern
_THIRD_PARTY_SUBJECT_RE = _c(
    r"\b(?:my\s+(?:friend|roommate|brother|sister|cousin|mother|father|mom|dad|partner|spouse|coworker|colleague)|someone\s+else|he|she|they)\b"
)

_FIRST_PERSON_SELF_RE = _c(r"\b(?:i|i'?m|i\s+am|i\s+feel|i\s+have|i\s+can'?t|i\s+was|i\s+am\s+feeling|mein|mujhe)\b")


def _is_negated_in_window(text: str, match_start: int) -> bool:
    """
    Checks if a local negation token precedes the match within ~40 characters
    in the same clause without an intervening contrastive conjunction.
    """
    prefix_start = max(0, match_start - 45)
    prefix = text[prefix_start:match_start]
    # Check for intervening contrast ("not happy, but stressed" -> stress is NOT negated)
    contrast_parts = re.split(r"\b(?:but|however|lekin|magar|yet)\b", prefix, flags=re.IGNORECASE)
    immediate_prefix = contrast_parts[-1]
    return bool(_LOCAL_NEGATION_RE.search(immediate_prefix))


def _sentence_has_first_person_affirmative(sentence: str) -> bool:
    """Returns True if the sentence contains direct first-person self-attribution."""
    s = re.sub(
        r"\b(?:my|mera|meri)\s+(?:friend|roommate|brother|sister|cousin|mother|father|mom|dad|partner|spouse|coworker|colleague|son|daughter|relative|dost|bhai|behn|walid|walida)\b",
        "",
        sentence,
        flags=re.IGNORECASE,
    )
    return bool(_FIRST_PERSON_SELF_RE.search(s))


def _sentence_is_purely_third_party(sentence: str) -> bool:
    """Returns True if the sentence discusses someone else without first-person self-attribution."""
    return bool(_THIRD_PARTY_SUBJECT_RE.search(sentence)) and not _sentence_has_first_person_affirmative(sentence)


# ---------------------------------------------------------------------------
# Core Wellbeing & Safety Extraction
# ---------------------------------------------------------------------------

def extract_deterministic_wellbeing_signals(
    raw_text: str,
    norm_text: str,
    preprocess_result: Optional[PreprocessResult] = None,
    actor_target: Optional[ThreatActorTargetResult] = None,
    has_casual_dampener: bool = False,
    has_inanimate_subject: bool = False,
    has_others_negation: bool = False,
    is_fictional: bool = False,
    det_res: Optional[Dict[str, Any]] = None,
    api_risk_label: str = "none",
    harm_to_others_matches: Optional[List[str]] = None,
    self_harm_matches: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Extracts structured multi-label wellbeing signals and safety risk signals
    reusing solely existing computed artifacts without duplicate scans.
    """
    det_res = det_res or {}
    sentence_findings = det_res.get("sentence_findings", [])
    bypass_reason = det_res.get("bypass_reason")
    bypass_triggered = det_res.get("bypass_triggered", False)
    matched_categories = det_res.get("matched_categories", [])

    # Global bypass flags
    is_third_party_global = (
        (preprocess_result and preprocess_result.is_third_party)
        or (actor_target and actor_target.category in ("THIRD_PARTY_REPORT", "REPORTED_THREAT_TO_OTHERS"))
        or api_risk_label in ("THIRD_PARTY_REPORT", "REPORTED_THREAT_TO_OTHERS")
    )
    is_fictional_global = (
        is_fictional
        or (preprocess_result and preprocess_result.is_fictional)
        or (actor_target and actor_target.is_fictional)
        or (bypass_reason in ("media_or_third_person_reference", "fictional_narrative"))
    )
    is_academic_global = (
        (preprocess_result and preprocess_result.is_academic)
        or (bypass_reason == "academic_or_research_context")
    )
    is_past_recovery_global = (
        (preprocess_result and preprocess_result.has_past_recovery and not preprocess_result.has_present_ideation)
        or (bypass_reason in ("past_historical_reflection", "past_historical_reflection_with_confirmed_resolution", "urdu_past_recovery"))
    )
    is_idiom_or_humour_global = (
        has_casual_dampener
        or (bypass_reason in ("idiomatic_or_hyperbolic_expression", "slang_hyperbole_dampener", "urdu_hyperbole", "urdu_sarcasm_frame"))
    )

    stress_evidence: List[str] = []
    anxiety_evidence: List[str] = []
    depression_evidence: List[str] = []
    grief_sadness_evidence: List[str] = []

    # Process sentences or full text
    sentences_to_evaluate = [f["sentence"] for f in sentence_findings if f.get("sentence")] if sentence_findings else [norm_text]

    for sent in sentences_to_evaluate:
        sent_lower = sent.lower()

        # Check sentence-level suppressions
        if is_fictional_global or is_academic_global:
            continue
        if is_past_recovery_global and not (preprocess_result and preprocess_result.has_present_ideation):
            continue
        if is_third_party_global and _sentence_is_purely_third_party(sent):
            continue

        # Stress scan
        for pat in _STRESS_PATTERNS:
            for m in pat.finditer(sent_lower):
                if not _is_negated_in_window(sent_lower, m.start()):
                    if not is_idiom_or_humour_global or not any(kw in m.group(0) for kw in ["killing", "dying", "mar"]):
                        stress_evidence.append(m.group(0))

        # Anxiety scan
        for pat in _ANXIETY_PATTERNS:
            for m in pat.finditer(sent_lower):
                if not _is_negated_in_window(sent_lower, m.start()):
                    anxiety_evidence.append(m.group(0))

        # Depression-related scan
        for pat in _DEPRESSION_PATTERNS:
            for m in pat.finditer(sent_lower):
                if not _is_negated_in_window(sent_lower, m.start()):
                    depression_evidence.append(m.group(0))

        # Ordinary grief / sadness scan
        for pat in _GRIEF_SADNESS_PATTERNS:
            for m in pat.finditer(sent_lower):
                if not _is_negated_in_window(sent_lower, m.start()):
                    grief_sadness_evidence.append(m.group(0))

    # Deduplicate evidence
    stress_evidence = sorted(list(set(stress_evidence)))
    anxiety_evidence = sorted(list(set(anxiety_evidence)))
    depression_evidence = sorted(list(set(depression_evidence)))
    grief_sadness_evidence = sorted(list(set(grief_sadness_evidence)))

    # If the entire message is a third-party report with NO first-person affirmative disclosure:
    if is_third_party_global and not any(_sentence_has_first_person_affirmative(s) for s in sentences_to_evaluate):
        stress_evidence = []
        anxiety_evidence = []
        depression_evidence = []

    # Flagging rules
    flag_stress = bool(stress_evidence)
    flag_anxiety = bool(anxiety_evidence)

    # Critical requirement: grief or sadness alone NEVER flags depression_signals
    # Depression signals flag ONLY if independent depression-related evidence exists!
    flag_depression = bool(depression_evidence)

    # Evidence-weighted calibrated confidence
    conf_stress = (0.88 if len(stress_evidence) >= 2 else 0.75) if flag_stress else 0.0
    conf_anxiety = (0.88 if len(anxiety_evidence) >= 2 else 0.75) if flag_anxiety else 0.0
    conf_depression = (0.88 if len(depression_evidence) >= 2 else 0.75) if flag_depression else 0.0

    # ---------------------------------------------------------------------------
    # Safety Signals Resolution (Precedence over wellbeing traits)
    # ---------------------------------------------------------------------------
    suicide_ideation = False
    suicide_intent = False
    suicide_plan_or_means = False
    harm_to_others = False

    # Harm to others
    if api_risk_label in ("HARM_TO_OTHERS_RISK", "COMBINED_HIGH_CRISIS"):
        harm_to_others = True
    elif actor_target and actor_target.category == "HARM_TO_OTHERS_RISK":
        harm_to_others = True
    elif bool(harm_to_others_matches) and not (has_inanimate_subject or has_others_negation or is_fictional_global):
        harm_to_others = True

    # Suicide / Self-harm safety signals
    if api_risk_label in ("HIGH_CRISIS", "COMBINED_HIGH_CRISIS") and not is_third_party_global:
        # Means and preparation
        has_prep = (
            "lethal_means_and_preparation" in matched_categories
            or "roman_urdu_means_attempt" in matched_categories
            or bool(preprocess_result and preprocess_result.has_preparatory_behavior)
            or bool(re.search(r"\b(?:pills|gun|knife|blade|rope|hanging|poison|overdose|sleeping\s+pills|razor|slit|jump(?:ing)?)\b", norm_text))
        )
        if has_prep:
            suicide_plan_or_means = True

        # Explicit intent
        has_intent = (
            "explicit_suicidal_intent" in matched_categories
            or "roman_urdu_imminent_intent" in matched_categories
            or "active_escalation_in_progress" in matched_categories
            or (actor_target and actor_target.category == "SELF_HARM_RISK")
        )
        if has_intent:
            suicide_intent = True

        # Ideation / self-harm
        has_ideation = (
            suicide_intent
            or suicide_plan_or_means
            or bool(self_harm_matches)
            or any(c in matched_categories for c in [
                "burden_and_goodbye",
                "subtle_slang_and_informal",
                "self_harm_and_cutting",
                "indirect_implicit_distress",
                "roman_urdu_burden_goodbye",
                "roman_urdu_self_harm",
                "roman_urdu_ideation_present",
            ])
        )
        if has_ideation:
            suicide_ideation = True

    wellbeing_signals = {
        "stress": {
            "flagged": flag_stress,
            "confidence": conf_stress,
            "deterministic_evidence": stress_evidence,
            "existing_ml_evidence": [],
        },
        "anxiety_signals": {
            "flagged": flag_anxiety,
            "confidence": conf_anxiety,
            "deterministic_evidence": anxiety_evidence,
            "existing_ml_evidence": [],
        },
        "depression_signals": {
            "flagged": flag_depression,
            "confidence": conf_depression,
            "deterministic_evidence": depression_evidence,
            "existing_ml_evidence": [],
        },
    }

    safety_signals = {
        "suicide_ideation": suicide_ideation,
        "suicide_intent": suicide_intent,
        "suicide_plan_or_means": suicide_plan_or_means,
        "harm_to_others": harm_to_others,
    }

    audit_metadata = {
        "grief_or_sadness_detected": bool(grief_sadness_evidence),
        "grief_or_sadness_evidence": grief_sadness_evidence,
        "is_third_party_suppressed": is_third_party_global,
        "is_fictional_suppressed": is_fictional_global,
        "is_academic_suppressed": is_academic_global,
        "is_past_recovery_suppressed": is_past_recovery_global,
        "evidence_disagreements": [],
    }

    return {
        "api_risk_label": api_risk_label,
        "wellbeing_signals": wellbeing_signals,
        "safety_signals": safety_signals,
        "source": "deterministic",
        "metadata": audit_metadata,
    }


# ---------------------------------------------------------------------------
# ML Evidence Integration & Disagreement Auditing
# ---------------------------------------------------------------------------

def enrich_wellbeing_with_ml(
    wellbeing_dict: Dict[str, Any],
    ml_results: Dict[str, Any],
    preprocess_result: Optional[PreprocessResult] = None,
    actor_target: Optional[ThreatActorTargetResult] = None,
    bypass_reason: Optional[str] = None,
    sentence_findings: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Enriches existing wellbeing_signals with evidence from huggingface_service.analyze_user_message().

    Enforces Resolution Rules:
    1. Existing deterministic safety outcomes always win for crisis routing.
    2. Contextual, negation, recovery, fictional, and third-party bypasses suppress matching
       ML-derived wellbeing flags unless an independent affirmative sentence exists.
    3. ANXIETY OR PANIC ATTACK may contribute evidence to anxiety_signals.
    4. GRIEF OR SADNESS must NOT automatically become depression_signals.
    5. Disagreements between deterministic and ML are preserved in protected audit metadata.
    6. Does not alter ML intent labels or crisis routing behavior.
    7. ML crisis_probability remains crisis-model evidence, not repurposed for stress/anxiety/depression.
    """
    if not ml_results or not isinstance(ml_results, dict):
        return wellbeing_dict

    ml_intent = ml_results.get("intent", "")
    ml_conf = float(ml_results.get("intent_confidence", 0.50))
    metadata = wellbeing_dict.setdefault("metadata", {})
    disagreements = metadata.setdefault("evidence_disagreements", [])

    is_third_party = (
        (preprocess_result and preprocess_result.is_third_party)
        or (actor_target and actor_target.category in ("THIRD_PARTY_REPORT", "REPORTED_THREAT_TO_OTHERS"))
        or wellbeing_dict.get("api_risk_label") in ("THIRD_PARTY_REPORT", "REPORTED_THREAT_TO_OTHERS")
    )
    is_fictional = (
        (preprocess_result and preprocess_result.is_fictional)
        or (actor_target and actor_target.is_fictional)
        or bypass_reason in ("media_or_third_person_reference", "fictional_narrative")
    )
    is_academic = (
        (preprocess_result and preprocess_result.is_academic)
        or bypass_reason == "academic_or_research_context"
    )
    is_negated = bypass_reason in ("grammatical_negation", "urdu_negation")

    is_suppressed = is_third_party or is_fictional or is_academic or is_negated

    wb = wellbeing_dict.get("wellbeing_signals", {})
    has_ml_addition = False

    # Rule 3: ANXIETY OR PANIC ATTACK contributes evidence to anxiety_signals
    if ml_intent == "ANXIETY OR PANIC ATTACK":
        evidence_entry = f"ml_intent:ANXIETY OR PANIC ATTACK (conf={ml_conf:.2f})"
        wb["anxiety_signals"]["existing_ml_evidence"].append(evidence_entry)

        if not is_suppressed:
            wb["anxiety_signals"]["flagged"] = True
            wb["anxiety_signals"]["confidence"] = max(wb["anxiety_signals"]["confidence"], ml_conf)
            has_ml_addition = True
        else:
            disagreements.append({
                "trait": "anxiety_signals",
                "ml_evidence": evidence_entry,
                "status": "suppressed_by_bypass",
                "reason": bypass_reason or "contextual_frame",
            })

    # Rule 4: GRIEF OR SADNESS must NOT automatically become depression_signals
    elif ml_intent == "GRIEF OR SADNESS":
        evidence_entry = f"ml_intent:GRIEF OR SADNESS (conf={ml_conf:.2f})"
        metadata["ml_grief_or_sadness_evidence"] = evidence_entry

        # Record in depression audit without automatically flagging depression
        wb["depression_signals"]["existing_ml_evidence"].append(evidence_entry)

        # Disagreement audit if deterministic depression was false
        if not wb["depression_signals"]["flagged"]:
            disagreements.append({
                "trait": "depression_signals",
                "ml_intent": ml_intent,
                "status": "not_escalated_without_independent_evidence",
                "rule": "Grief or sadness alone does not flag depression signals",
            })

    # Record any general ML vs deterministic disagreement
    for trait in ["stress", "anxiety_signals", "depression_signals"]:
        trait_info = wb.get(trait, {})
        has_det = bool(trait_info.get("deterministic_evidence"))
        has_ml = bool(trait_info.get("existing_ml_evidence"))
        if has_det != has_ml and (has_det or has_ml):
            disagreements.append({
                "trait": trait,
                "deterministic_flagged": has_det,
                "ml_flagged": has_ml,
            })

    # Update source label
    if has_ml_addition:
        has_det_any = any(bool(wb[t]["deterministic_evidence"]) for t in ["stress", "anxiety_signals", "depression_signals"])
        wellbeing_dict["source"] = "hybrid" if has_det_any else "existing_ml"

    return wellbeing_dict


# ---------------------------------------------------------------------------
# Future ML Model Adapter Interface (Disabled by Default)
# ---------------------------------------------------------------------------

class WellbeingMultiLabelModelAdapter:
    """
    Narrow adapter interface for a future multi-label classifier.
    Controlled by ENABLE_WELLBEING_MULTILABEL_MODEL (disabled by default).

    Invariants:
    1. Returns None when disabled or model fails, falling back safely to deterministic + ML signals.
    2. Even when enabled, can NEVER override explicit deterministic suicide or harm-to-others outcomes.
    3. Supplement ambiguous non-safety wellbeing signals only.
    """
    def __init__(self, enabled: bool = ENABLE_WELLBEING_MULTILABEL_MODEL):
        self.enabled = enabled

    def predict(self, text: str) -> Optional[Dict[str, float]]:
        if not self.enabled:
            return None

        # Safe forward-pass stub for future fine-tuned model
        try:
            logger.info("WellbeingMultiLabelModelAdapter forward pass invoked.")
            return None
        except Exception as ex:
            logger.warning("Future wellbeing multi-label adapter prediction failed: %s", ex)
            return None
