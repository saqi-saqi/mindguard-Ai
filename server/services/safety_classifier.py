"""
safety_classifier.py
====================
Isolated multi-signal safety classification module.

Runs BEFORE messages reach Gemini, Ollama, RAG, or any conversational reply logic.
Detects:
- COMBINED_HIGH_CRISIS (homicide/threat + self-harm in same or adjacent turns)
- HARM_TO_OTHERS_RISK (credible threats, weapons, targets)
- SELF_HARM_RISK (suicide intent, lethal means, self-harm)
- THIRD_PARTY_REPORT (reporting risk concerning another person)
- EMOTIONAL_DISTRESS (distress, casual hyperbole, idioms)
- NONE (benign chat)

Precedence Policy:
COMBINED_HIGH_CRISIS > HARM_TO_OTHERS_RISK > SELF_HARM_RISK > THIRD_PARTY_REPORT > EMOTIONAL_DISTRESS > NONE
"""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple, Dict, Any

logger = logging.getLogger("MindGuard-SafetyClassifier")


class SafetyRiskCategory(str, Enum):
    COMBINED_HIGH_CRISIS = "COMBINED_HIGH_CRISIS"
    HARM_TO_OTHERS_RISK = "HARM_TO_OTHERS_RISK"
    SELF_HARM_RISK = "SELF_HARM_RISK"
    THIRD_PARTY_REPORT = "THIRD_PARTY_REPORT"
    EMOTIONAL_DISTRESS = "EMOTIONAL_DISTRESS"
    NONE = "NONE"


@dataclass
class SafetyClassificationResult:
    category: SafetyRiskCategory
    confidence: float
    matched_signals: List[str] = field(default_factory=list)
    is_crisis: bool = False
    requires_immediate_action: bool = False
    safety_message: str = ""
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Pre-compiled Canonical Regex Patterns
# ---------------------------------------------------------------------------

def _c(pat: str) -> re.Pattern:
    return re.compile(pat, re.IGNORECASE)


def _normalize(text: str) -> str:
    if not text:
        return ""
    t = text.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.lower()
    t = " ".join(t.split())
    return t


# 1. Hyperbolic / Casual Dampeners (indicates NOT a credible threat)
_CASUAL_JOKE_DAMPENERS = [
    _c(r"\b(?:lol|lmao|rofl|lmfao|haha+|hehe+|jk|j/k|just\s+kidding|only\s+kidding|sarcasm)\b"),
]

_INANIMATE_OR_METAPHOR_SUBJECTS = [
    _c(r"\b(?:this|the|my|that)\s+(?:traffic|exam|exams|test|tests|homework|commute|job|work|boss|meeting|weather|shoes|feet|computer|printer|code|headache)\s+(?:is|are|is\s+going\s+to|will)\s+(?:literally\s+)?killing\s+me\b"),
    _c(r"\b(?:traffic|homework|work|exam|finals|shoes|feet)\s+(?:is|are)\s+killing\s+me\b"),
    _c(r"\b(?:dying|died)\s+of\s+(?:laughter|boredom|embarrassment|curiosity)\b"),
    _c(r"\bi\s+could\s+kill\s+for\s+(?:a\s+)?(?:coffee|drink|beer|pizza|nap|break|vacation|cigarette)\b"),
    _c(r"\bkill\s+two\s+birds\s+with\s+one\s+stone\b"),
    _c(r"\bdressed\s+to\s+kill\b"),
    _c(r"\btime\s+to\s+kill\b"),
]

_HARM_OTHERS_NEGATIONS = [
    _c(r"\b(?:i\s+would|i'd)\s+never\s+(?:kill|hurt|harm|shoot|stab)\s+(?:anyone|anybody|someone|him|her|them)\b"),
    _c(r"\bi\s+(?:do\s+not|don'?t)\s+want\s+to\s+(?:kill|hurt|harm)\s+(?:anyone|anybody|him|her|them)\b"),
    _c(r"\bno\s+intention\s+of\s+(?:hurting|killing|harming)\s+(?:anyone|him|her|them)\b"),
]

_TRIVIAL_BENIGN_PATTERNS = [
    _c(r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|howdy|sup|greetings|yo)\b[!?.]*$"),
    _c(r"^(?:ok|okay|thanks|thank\s+you|cool|got\s+it|sure|yes|no|yep|nope|bye|goodbye)\b[!?.]*$"),
    _c(r"^(?:hello|hi|hey)\s+(?:again|there|bot|mindguard)\b[!?.]*$"),
]

# 2. Harm-To-Others / Homicide Patterns (Direct Threats & Specific Methods)
_HARM_TO_OTHERS_PATTERNS = [
    # Direct intent to kill/murder/harm/attack/assault/injure someone (generic or specific)
    _c(r"\b(?:i'?m\s+gonna|i\s+am\s+going\s+to|i\s+will|i'll|i\s+plan\s+to|i'?m\s+planning\s+to|i\s+want\s+to|wanna|intend\s+to|planning\s+to|plan\s+to|gonna|urge\s+to|feel\s+like|need\s+to)\s+(?:gonna\s+)?(?:harm|hurt|beat|attack|assault|injure|kill|murder|slaughter|shoot|stab|slit|choke|strangle|poison|assassinate|execute)\s+(?:my\s+|the\s+|this\s+|that\s+)?(?:neighbour|neighbor|friend|boss|coworker|ex|wife|husband|mother|father|brother|sister|roommate|teacher|landlord|doctor|cousin|uncle|aunt|partner|girlfriend|boyfriend|son|daughter|kid|child|people|someone|anyone|anybody|somebody|everyone|everybody|them|him|her|bitch|bastard)\b"),
    _c(r"\b(?:gonna|going\s+to|will|i'll)\s+(?:kill|murder|shoot|stab|slaughter|poison|attack|harm|hurt|beat|assault|injure)\s+(?:him|her|them|my\s+\w+|someone|anyone|anybody|somebody|people|everybody)\b"),
    _c(r"\b(?:i'?m\s+going\s+to|i'?m\s+gonna|i\s+will|i'll)\s+(?:poison|attack|assault|beat)\s+(?:him|her|them|someone|anyone|people|everyone|[a-z]+)\b"),
    _c(r"\b(?:want\s+to|wanna|plan\s+to|planning\s+to|urge\s+to)\s+(?:harm|hurt|beat|attack|assault|injure)\s+(?:someone|anyone|anybody|somebody|people)\b"),
    _c(r"\b(?:have|got|holding|grabbed|brought|bring)\s+(?:a|the|my)?\s*(?:knife|gun|pistol|rifle|blade|weapon|axe|machete)\s+.*?\b(?:attack|harm|hurt|kill|shoot|stab|injure|use\s+it)\b"),
    _c(r"\bholding\s+(?:a|the|my)?\s*(?:gun|knife|blade|weapon)\b.*?\b(?:thinking\s+about\s+using|want\s+to\s+use|gonna\s+use)\b"),
    # Slit throat / run over / strangle
    _c(r"\b(?:will|going\s+to|gonna|i'll)\s+slit\s+(?:his|her|their|the|my\s+\w+)?\s*throats?\b"),
    _c(r"\b(?:slit\s+(?:his|her|their|the)?\s*throat)\b"),
    _c(r"\b(?:run|running)\s+(?:him|her|them|[a-z]+)\s+over(?:\s+with\s+(?:my|a|the)\s+(?:car|truck|vehicle))?\b"),
    # Threat with specific weapon or method
    _c(r"\b(?:i'?m\s+going\s+to|i'?m\s+gonna|i\s+will|i'll|going\s+to|gonna)\s+(?:stab|shoot|strangle|slit|poison|run\s+over|beat)\s+(?:him|her|them|my\s+\w+|the\s+\w+|someone)\s+(?:with|using)\s+(?:the\s+|a\s+)?(?:kitchen\s+knife|knife|gun|pistol|rifle|blade|hammer|axe|machete|rope|poison|car|truck|vehicle)\b"),
    _c(r"\b(?:stab|shoot|strangle|poison|slit\s+the\s+throat\s+of)\s+(?:him|her|them)\s+(?:with\s+a\s+|with\s+the\s+)?(?:kitchen\s+knife|knife|gun|pistol|blade|weapon)\b"),
    _c(r"\b(?:brought|bring|take|got)\s+(?:a|my)\s+(?:gun|knife|weapon|blade)\s+to\s+(?:kill|shoot|stab|attack)\s+(?:him|her|them|my\s+\w+|someone|everyone|coworker|boss)\b"),
    # Hit-list and stalking/hunting threats
    _c(r"\b(?:on\s+my|my)\s+(?:killing|kill|hit)\s+list\b"),
    _c(r"\bput\s+a\s+bullet\s+(?:in|through)\s+(?:his|her|their|him|them)\b"),
    _c(r"\bhunt(?:ing)?\s+(?:him|her|them)\s+down\s+(?:and|to)\s+(?:kill|end|destroy)\b"),
    _c(r"\bbeat\s+(?:him|her|them)\s+to\s+death\b"),
    # Roman Urdu threats to others
    _c(r"\b(?:mai|main|hum)\s+(?:usko|usey|usay|unko|isay|isko)\s+(?:jaan\s+se\s+)?(?:maar|mar)\s*(?:dun\s*ga|doon\s*ga|dalun\s*ga|daal\s*donga|marunga)\b"),
    _c(r"\b(?:usko|usey|usay|unko)\s+(?:jaan\s+se\s+)?(?:maar|mar)\s+d[ou]+n\s*ga\b"),
    _c(r"\b(?:mai|main)\s+(?:usko|usey|usay|unko)\s+qatal\s+kar\s*(?:dun|doon)\s*ga\b"),
    _c(r"\b(?:goli|chhuri|churi)\s+maar\s+d[ou]+n\s*ga\b"),
    _c(r"\b(?:us\s*ko|usay)\s+zinda\s+nah?i\s+ch[oó]r[uú]n\s*ga\b"),
]

# 3. Self-Harm / Suicide Threat Patterns
_SELF_HARM_PATTERNS = [
    _c(r"\b(?:going\s+to|gonna|want\s+to|wanna|will|plan\s+to|planning\s+to)\s+(?:kill\s+myself|end\s+my\s+life|commit\s+suicide|die)\b"),
    _c(r"\b(?:i\s+)?(?:want\s+to|wanna)\s+die\b"),
    _c(r"\bi\s+(?:wish\s+i\s+(?:was|were)\s+dead|don'?t\s+want\s+to\s+live\s+anymore)\b"),
    _c(r"\btake\s+my\s+(?:own\s+)?life\b"),
    _c(r"\b(?:i\s+am|i'?m)\s+(?:going\s+to\s+)?(?:suicidal|kill\s+myself|overdose|hang\s+myself|jump\s+off\s+a\s+bridge)\b"),
    _c(r"\b(?:took|swallowed|downed|ingested)\s+(?:a\s+whole\s+bottle|all\s+my|too\s+many)\s+(?:pills|tablets|medication|painkillers)\b"),
    _c(r"\b(?:cut|cutting|harm|harming)\s+myself\b"),
    _c(r"\b(?:kms|kys|unalive\s+myself)\b"),
    _c(r"\bnext\s+on\s+my\s+killing\s+list\s+is\s+me\b"),
    _c(r"\bkill\s+myself\s+(?:too|after|next)\b"),
    # Roman Urdu self harm
    _c(r"\b(?:mujhe\s+mar\s+ja+na\s+hai|main\s+khudkushi\s+karna\s+chaht[ai]\s+hoon|apni\s+jaan\s+lena\s+chaht[ai]\s+hoon)\b"),
]

# 4. Third-Party Crisis / Threat Disclosure Patterns
_THIRD_PARTY_PATTERNS = [
    _c(r"\b(?:my\s+|a\s+)?(?:friend|roommate|brother|sister|cousin|ex|coworker|colleague|classmate|partner|neighbour|neighbor|someone|somebody|he|she|they)(?:\s+in\s+my\s+\w+)?\b.{0,60}?\b(?:talks?|talking|said|says?|told\s+me|threaten(?:ed|ing)?|planning|plans?|posted|going|wants?)\b.{0,60}?\b(?:kill(?:ing)?|murder(?:ing)?|shoot(?:ing)?|stab(?:bing)?|hurt(?:ing)?|harm(?:ing)?|die|suicid|end\s+(?:his|her|their)\s+life|commit\s+suicide)\b"),
    _c(r"\b(?:my\s+friend|my\s+brother|my\s+sister|my\s+roommate|someone\s+i\s+know|someone\s+in\s+my\s+\w+)\s+(?:wants\s+to\s+die|is\s+suicidal|wants\s+to\s+kill|is\s+threatening\s+to\s+kill|wants\s+to\s+commit\s+suicide)\b"),
    _c(r"\b(?:someone|she|he|they)\s+posted\s+that\s+(?:she|he|they)\s+(?:wants?\s+to|is\s+going\s+to)\s+(?:die|commit\s+suicide|kill)\b"),
]

# 5. Emotional Distress Signals
_DISTRESS_SIGNALS = [
    _c(r"\b(?:depressed|overwhelmed|hopeless|anxious|panic|panicking|crying|heartbroken|angry|furious|desperate|scared|terrified|can't\s+cope|exhausted)\b"),
]


# ---------------------------------------------------------------------------
# Exact Safety Messages (Pakistan-focused, zero 988/111)
# ---------------------------------------------------------------------------

HARM_TO_OTHERS_SAFETY_MESSAGE = (
    "Immediate safety support needed — move away from the person and any weapon or harmful object, and contact emergency services now.\n\n"
    "Emergency Services (Pakistan):\n"
    "• Police Emergency: 15\n"
    "• Rescue Emergency: 1122\n"
    "• Edhi Ambulance: 115\n"
    "• Umang Pakistan Mental Health Helpline: 0311-7786264 (24/7 free support)\n"
    "Or go to the emergency department of your nearest hospital.\n\n"
    "This app cannot contact emergency services automatically — please call one of the numbers above or go to your nearest hospital emergency department."
)

COMBINED_CRISIS_SAFETY_MESSAGE = (
    "Immediate safety support needed — move away from the person and any weapon or harmful object, and contact emergency services now.\n\n"
    "Emergency Services (Pakistan):\n"
    "• Police Emergency: 15\n"
    "• Rescue Emergency: 1122\n"
    "• Edhi Ambulance: 115\n"
    "• Umang Pakistan Mental Health Helpline: 0311-7786264 (24/7 free support)\n"
    "Or go to the emergency department of your nearest hospital.\n\n"
    "This app cannot contact emergency services automatically — please call one of the numbers above or go to your nearest hospital emergency department."
)

SELF_HARM_SAFETY_MESSAGE = (
    "If you are feeling overwhelmed or in crisis, please know that you are not alone and support is available right now.\n\n"
    "Emergency Services (Pakistan):\n"
    "• Rescue Emergency: 1122\n"
    "• Edhi Ambulance: 115\n"
    "• Umang Pakistan Mental Health Helpline: 0311-7786264 (24/7 free support)\n"
    "• Police Emergency: 15\n"
    "Or go to the emergency department of your nearest hospital.\n\n"
    "This app cannot contact emergency services automatically — please call one of the numbers above or go to your nearest hospital emergency department."
)

THIRD_PARTY_SAFETY_MESSAGE = (
    "It sounds like you are carrying concern for someone who may be in danger. "
    "Please share these emergency services with them directly or contact someone who can intervene to help keep everyone safe:\n\n"
    "Emergency Services (Pakistan):\n"
    "• Police Emergency: 15 (if someone is in danger of being harmed)\n"
    "• Rescue Emergency: 1122\n"
    "• Edhi Ambulance: 115\n"
    "• Umang Pakistan Mental Health Helpline: 0311-7786264 (24/7 free & confidential)\n"
    "Or go to the emergency department of your nearest hospital.\n\n"
    "Please do not try to handle dangerous situations alone. Encourage them to connect with professionals or reach out to local emergency authorities directly."
)


# ---------------------------------------------------------------------------
# Core Classification Logic
# ---------------------------------------------------------------------------

def _risk_level_to_priority(risk_level: str) -> int:
    """Map risk level string to numeric priority for max() comparison."""
    return {
        "COMBINED_HIGH_CRISIS": 6,
        "HARM_TO_OTHERS_RISK": 5,
        "HIGH_CRISIS": 4,
        "SELF_HARM_RISK": 3,
        "THIRD_PARTY_REPORT": 2,
        "EMOTIONAL_DISTRESS": 1,
        "NONE": 0,
    }.get(risk_level, 0)


def _category_from_risk_level(risk_level: str) -> SafetyRiskCategory:
    """Map risk level string to SafetyRiskCategory enum."""
    return {
        "COMBINED_HIGH_CRISIS": SafetyRiskCategory.COMBINED_HIGH_CRISIS,
        "HARM_TO_OTHERS_RISK": SafetyRiskCategory.HARM_TO_OTHERS_RISK,
        "HIGH_CRISIS": SafetyRiskCategory.SELF_HARM_RISK,  # HIGH_CRISIS maps to SELF_HARM_RISK for API compat
        "SELF_HARM_RISK": SafetyRiskCategory.SELF_HARM_RISK,
        "THIRD_PARTY_REPORT": SafetyRiskCategory.THIRD_PARTY_REPORT,
        "EMOTIONAL_DISTRESS": SafetyRiskCategory.EMOTIONAL_DISTRESS,
        "NONE": SafetyRiskCategory.NONE,
    }.get(risk_level, SafetyRiskCategory.NONE)


def classify_safety_risk(
    text: str,
    context_turns: Optional[List[str]] = None,
    api_key: Optional[str] = None,
    session_id: Optional[str] = None,
) -> SafetyClassificationResult:
    """
    Classifies user message into one of 6 safety categories.

    Authority model (INVERTED from legacy):
    - final_risk = max(Tier1_deterministic, Semantic_tier)
    - Tier 1 retains authority to ESCALATE (high-recall safety net)
    - Tier 1 no longer has sole authority to SUPPRESS a semantic escalation
    - Semantic tier handles structured exclusions natively
    - Cross-turn anonymous session context used for COMBINED_HIGH_CRISIS detection

    Precedence:
    COMBINED_HIGH_CRISIS > HARM_TO_OTHERS_RISK > HIGH_CRISIS > SELF_HARM_RISK
    > THIRD_PARTY_REPORT > EMOTIONAL_DISTRESS > NONE
    """
    # Step 0: Canonicalize ONCE upstream (single normalization point for all tiers)
    try:
        from services.text_normalizer import canonicalize_message
        norm = canonicalize_message(text)
    except ImportError:
        from .text_normalizer import canonicalize_message
        norm = canonicalize_message(text)

    if not norm:
        return SafetyClassificationResult(
            category=SafetyRiskCategory.NONE,
            confidence=1.0,
            is_crisis=False,
            requires_immediate_action=False,
            reasoning="Empty input"
        )

    # Step A: Check for Hyperbole / Idiom / Casual Joke Dampeners
    has_casual_dampener = any(pat.search(norm) for pat in _CASUAL_JOKE_DAMPENERS)
    has_inanimate_subject = any(pat.search(norm) for pat in _INANIMATE_OR_METAPHOR_SUBJECTS)
    has_others_negation = any(pat.search(norm) for pat in _HARM_OTHERS_NEGATIONS)

    # Step B: Deterministic Harm-to-Others matching
    harm_to_others_matches = []
    if not has_inanimate_subject and not has_others_negation:
        for pat in _HARM_TO_OTHERS_PATTERNS:
            m = pat.search(norm)
            if m:
                harm_to_others_matches.append(m.group(0))

    if has_casual_dampener and harm_to_others_matches:
        logger.info("Harm-to-others phrase matched but suppressed by casual/joke dampener: %s", harm_to_others_matches)
        harm_to_others_matches = []

    # Step C: Deterministic Self-Harm matching
    self_harm_matches = []
    # Check if text is purely negated/contextual (e.g. "I don't want to die, I want to get better")
    is_negated = False
    try:
        from services.crisis_rules import is_contextual_or_negated
        is_negated = is_contextual_or_negated(text)
    except Exception:
        pass

    if not is_negated:
        for pat in _SELF_HARM_PATTERNS:
            m = pat.search(norm)
            if m:
                self_harm_matches.append(m.group(0))

        # Also check Tier-1 deterministic crisis engine
        if not self_harm_matches:
            try:
                from services.crisis_rules import evaluate_crisis
                det_res = evaluate_crisis(text)
                if det_res.get("is_crisis"):
                    self_harm_matches.append("tier1_deterministic_crisis")
            except Exception as e:
                logger.debug("Error checking crisis_rules: %s", e)

    # Step D: Combined signal (same turn)
    has_combined_same_turn = bool(harm_to_others_matches and self_harm_matches)
    if not has_combined_same_turn and harm_to_others_matches:
        if re.search(r"\b(?:and|then|after\s+that)\s+(?:also\s+)?(?:then\s+)?(?:myself|me|end\s+it\s+all|kill\s+myself|take\s+my\s+own\s+life)\b", norm):
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

    # Step D2: Cross-turn combined via anonymous session context
    has_combined_adjacent = False
    if session_id:
        try:
            from services.session_context import get_session_context
            session_ctx = get_session_context(session_id)
            if harm_to_others_matches and session_ctx.had_self_harm_recently(120.0):
                has_combined_adjacent = True
            elif self_harm_matches and session_ctx.had_harm_to_others_recently(120.0):
                has_combined_adjacent = True
        except Exception as ctx_err:
            logger.debug("Session context check error: %s", ctx_err)

    # Legacy context_turns cross-turn check (authenticated users with history)
    if context_turns and len(context_turns) > 0:
        last_turn_norm = canonicalize_message(context_turns[-1])
        last_had_others_threat = any(p.search(last_turn_norm) for p in _HARM_TO_OTHERS_PATTERNS) and not any(
            p.search(last_turn_norm) for p in _CASUAL_JOKE_DAMPENERS
        )
        last_had_self_harm = any(p.search(last_turn_norm) for p in _SELF_HARM_PATTERNS)
        if (last_had_others_threat and self_harm_matches) or (last_had_self_harm and harm_to_others_matches):
            has_combined_adjacent = True

    # Step E: Third-party matching
    third_party_matches = []
    if not harm_to_others_matches and not self_harm_matches:
        for pat in _THIRD_PARTY_PATTERNS:
            m = pat.search(norm)
            if m:
                if not re.search(r"\bi\s+(?:told|said\s+to|threatened)\s+my\b", norm):
                    third_party_matches.append(m.group(0))

    # -----------------------------------------------------------------------
    # Build deterministic result string
    # -----------------------------------------------------------------------
    if has_combined_same_turn or has_combined_adjacent:
        det_risk_level = "COMBINED_HIGH_CRISIS"
    elif harm_to_others_matches:
        det_risk_level = "HARM_TO_OTHERS_RISK"
    elif self_harm_matches:
        det_risk_level = "SELF_HARM_RISK"
    elif third_party_matches:
        det_risk_level = "THIRD_PARTY_REPORT"
    elif any(pat.search(norm) for pat in _DISTRESS_SIGNALS) or has_inanimate_subject or has_casual_dampener:
        det_risk_level = "EMOTIONAL_DISTRESS"
    else:
        det_risk_level = "NONE"

    # -----------------------------------------------------------------------
    # Step F: Semantic Safety Classifier (Tier 3)
    # Only skip for clearly NONE cases where deterministic is confident
    # -----------------------------------------------------------------------
    sem_risk_level = "NONE"
    sem_confidence = 0.0
    sem_rationale = ""
    sem_exclusion = None

    is_trivial_benign = any(pat.match(norm) for pat in _TRIVIAL_BENIGN_PATTERNS)

    # Skip semantic call for trivially safe cases to save latency
    _skip_semantic = (
        is_trivial_benign
        or det_risk_level in ("COMBINED_HIGH_CRISIS", "HARM_TO_OTHERS_RISK")
        or (det_risk_level == "NONE" and has_inanimate_subject)
    )

    if not _skip_semantic:
        try:
            # Build cross-turn context descriptor (NOT raw text)
            ctx_descriptor = None
            if session_id:
                from services.session_context import get_session_context
                s_ctx = get_session_context(session_id)
                recent = s_ctx.recent_events(120.0)
                if recent:
                    prior_risks = [e.risk_level for e in recent if e.risk_level not in ("NONE", "EMOTIONAL_DISTRESS")]
                    if prior_risks:
                        ctx_descriptor = f"Cross-turn context: prior turn safety signals detected: {', '.join(prior_risks[:3])}."

            from services.semantic_safety_classifier import classify_semantically
            sem_result = classify_semantically(text=text, cross_turn_context=ctx_descriptor, api_key=api_key)
            if sem_result:
                sem_risk_level = sem_result.get("risk_level", "NONE")
                sem_confidence = float(sem_result.get("confidence", 0.0))
                sem_rationale = sem_result.get("rationale", "")
                sem_exclusion = sem_result.get("exclusion_applied")
        except Exception as sem_err:
            logger.warning("Semantic safety classifier error in classify_safety_risk: %s", sem_err)

    # -----------------------------------------------------------------------
    # Step G: Inverted authority — final = max(deterministic, semantic)
    # Tier 1 can escalate but no longer suppresses semantic escalation
    # -----------------------------------------------------------------------
    det_priority = _risk_level_to_priority(det_risk_level)
    sem_priority = _risk_level_to_priority(sem_risk_level)

    if det_priority >= sem_priority:
        final_risk_level = det_risk_level
        winning_source = "deterministic"
    else:
        # Semantic escalated higher than deterministic
        # Apply exclusions ONLY if confidence >= 0.7 AND no first-person override in deterministic
        if sem_confidence >= 0.70:
            final_risk_level = sem_risk_level
            winning_source = "semantic"
            logger.info(
                f"Semantic classifier escalated from {det_risk_level} to {sem_risk_level} "
                f"(conf={sem_confidence:.2f}): {sem_rationale[:100]}"
            )
        else:
            # Low-confidence semantic escalation — stay with deterministic
            final_risk_level = det_risk_level
            winning_source = "deterministic_low_sem_conf"

    # -----------------------------------------------------------------------
    # Step H: Record to anonymous session context (classification metadata only)
    # -----------------------------------------------------------------------
    if session_id:
        try:
            from services.session_context import record_safety_event
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
        except Exception as rec_err:
            logger.debug("Session context record error: %s", rec_err)

    # -----------------------------------------------------------------------
    # Step I: Build and return SafetyClassificationResult
    # -----------------------------------------------------------------------
    final_category = _category_from_risk_level(final_risk_level)
    is_crisis = final_category in (
        SafetyRiskCategory.COMBINED_HIGH_CRISIS,
        SafetyRiskCategory.HARM_TO_OTHERS_RISK,
        SafetyRiskCategory.SELF_HARM_RISK,
    )
    requires_action = is_crisis

    # Determine matched signals and safety message
    matched_signals: list = (
        (harm_to_others_matches or []) + (self_harm_matches or []) + (third_party_matches or [])
    )
    if winning_source == "semantic" and sem_rationale:
        matched_signals.append(f"semantic:{sem_rationale[:80]}")

    if final_risk_level == "COMBINED_HIGH_CRISIS":
        if has_combined_adjacent:
            matched_signals.append("cross_turn_adjacent_threat")
        safety_msg = COMBINED_CRISIS_SAFETY_MESSAGE
        reasoning = "Harm-to-others combined with self-harm intent detected"
        confidence = 0.99
    elif final_risk_level == "HARM_TO_OTHERS_RISK":
        safety_msg = HARM_TO_OTHERS_SAFETY_MESSAGE
        reasoning = "Direct credible threat to another person detected"
        confidence = 0.98
    elif final_risk_level in ("SELF_HARM_RISK", "HIGH_CRISIS"):
        safety_msg = SELF_HARM_SAFETY_MESSAGE
        reasoning = "Self-harm or suicidal intent detected"
        confidence = 0.98
    elif final_risk_level == "THIRD_PARTY_REPORT":
        safety_msg = THIRD_PARTY_SAFETY_MESSAGE
        reasoning = "Third-party risk disclosure reported"
        confidence = 0.95
    elif final_risk_level == "EMOTIONAL_DISTRESS":
        safety_msg = ""
        reasoning = "Emotional distress or casual hyperbole without crisis intent"
        confidence = 0.85
    else:
        safety_msg = ""
        reasoning = "No safety risk detected"
        confidence = 0.95

    return SafetyClassificationResult(
        category=final_category,
        confidence=confidence,
        matched_signals=matched_signals,
        is_crisis=is_crisis,
        requires_immediate_action=requires_action,
        safety_message=safety_msg,
        reasoning=reasoning,
    )
