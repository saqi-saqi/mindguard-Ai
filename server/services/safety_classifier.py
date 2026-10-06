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

# 2. Harm-To-Others / Homicide Patterns (Direct Threats & Specific Methods)
_HARM_TO_OTHERS_PATTERNS = [
    # Direct intent to kill/murder/harm someone
    _c(r"\b(?:i'?m\s+gonna|i\s+am\s+going\s+to|i\s+will|i'll|i\s+plan\s+to|i'?m\s+planning\s+to|i\s+want\s+to|wanna|intend\s+to)\s+(?:gonna\s+)?(?:kill|murder|slaughter|shoot|stab|slit|choke|strangle|poison|assassinate|execute)\s+(?:my\s+|the\s+|this\s+|that\s+)?(?:neighbour|neighbor|friend|boss|coworker|ex|wife|husband|mother|father|brother|sister|roommate|teacher|landlord|doctor|cousin|uncle|aunt|partner|girlfriend|boyfriend|son|daughter|kid|child|people|someone|everyone|everybody|them|him|her|bitch|bastard)\b"),
    _c(r"\b(?:gonna|going\s+to|will|i'll)\s+(?:kill|murder|shoot|stab|slaughter|poison)\s+(?:him|her|them|my\s+\w+|someone|everybody)\b"),
    _c(r"\b(?:i'?m\s+going\s+to|i'?m\s+gonna|i\s+will|i'll)\s+poison\s+(?:him|her|them|someone|everyone|[a-z]+)\b"),
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

def classify_safety_risk(
    text: str,
    context_turns: Optional[List[str]] = None,
    api_key: Optional[str] = None
) -> SafetyClassificationResult:
    """
    Classifies user message into one of 6 safety categories.
    Applies precedence:
    COMBINED_HIGH_CRISIS > HARM_TO_OTHERS_RISK > SELF_HARM_RISK > THIRD_PARTY_REPORT > EMOTIONAL_DISTRESS > NONE

    Parameters:
    - text: Current user message
    - context_turns: Optional list of recent user turns in chronological order
    - api_key: Optional Gemini API key for temperature-0 ambiguous fallback
    """
    norm = _normalize(text)
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

    # Step B: Match Harm to Others
    harm_to_others_matches = []
    if not has_inanimate_subject and not has_others_negation:
        for pat in _HARM_TO_OTHERS_PATTERNS:
            m = pat.search(norm)
            if m:
                harm_to_others_matches.append(m.group(0))

    # If casual joke dampeners like "lol" accompany the threat, do not treat as active crisis
    if has_casual_dampener and harm_to_others_matches:
        logger.info("Harm-to-others phrase matched but suppressed by casual/joke dampener: %s", harm_to_others_matches)
        harm_to_others_matches = []

    # Step C: Match Self Harm
    self_harm_matches = []
    for pat in _SELF_HARM_PATTERNS:
        m = pat.search(norm)
        if m:
            self_harm_matches.append(m.group(0))

    # Also check existing deterministic crisis engine for self-harm detection
    if not self_harm_matches:
        try:
            from services.crisis_rules import evaluate_crisis
            det_res = evaluate_crisis(text)
            if det_res.get("is_crisis"):
                self_harm_matches.append("tier1_deterministic_crisis")
        except Exception as e:
            logger.debug("Error checking crisis_rules: %s", e)

    # Step D: Check for Combined Signals (Same Turn or Cross-Turn Adjacent)
    has_combined_same_turn = bool(harm_to_others_matches and self_harm_matches)
    # Special phrasing: "after that next on my killing list is me"
    if re.search(r"\bnext\s+on\s+my\s+killing\s+list\s+is\s+me\b", norm) or (
        re.search(r"\bkilling\s+list\b", norm) and re.search(r"\bis\s+me\b|\band\s+(?:then\s+)?(?:me|myself)\b", norm)
    ):
        has_combined_same_turn = True

    has_combined_adjacent = False
    if context_turns and len(context_turns) > 0:
        last_turn_norm = _normalize(context_turns[-1])
        last_had_others_threat = any(p.search(last_turn_norm) for p in _HARM_TO_OTHERS_PATTERNS) and not any(
            p.search(last_turn_norm) for p in _CASUAL_JOKE_DAMPENERS
        )
        last_had_self_harm = any(p.search(last_turn_norm) for p in _SELF_HARM_PATTERNS)

        if (last_had_others_threat and self_harm_matches) or (last_had_self_harm and harm_to_others_matches):
            has_combined_adjacent = True

    # Step E: Match Third-Party Report
    third_party_matches = []
    if not harm_to_others_matches and not self_harm_matches:
        for pat in _THIRD_PARTY_PATTERNS:
            m = pat.search(norm)
            if m:
                # Ensure the speaker is not the subject
                if not re.search(r"\bi\s+(?:told|said\s+to|threatened)\s+my\b", norm):
                    third_party_matches.append(m.group(0))

    # Step F: Apply Precedence Hierarchy
    # 1. COMBINED_HIGH_CRISIS
    if has_combined_same_turn or has_combined_adjacent:
        signals = harm_to_others_matches + self_harm_matches
        if has_combined_adjacent:
            signals.append("cross_turn_adjacent_threat")
        return SafetyClassificationResult(
            category=SafetyRiskCategory.COMBINED_HIGH_CRISIS,
            confidence=0.99,
            matched_signals=signals,
            is_crisis=True,
            requires_immediate_action=True,
            safety_message=COMBINED_CRISIS_SAFETY_MESSAGE,
            reasoning="Harm-to-others combined with self-harm intent detected"
        )

    # 2. HARM_TO_OTHERS_RISK
    if harm_to_others_matches:
        return SafetyClassificationResult(
            category=SafetyRiskCategory.HARM_TO_OTHERS_RISK,
            confidence=0.98,
            matched_signals=harm_to_others_matches,
            is_crisis=True,
            requires_immediate_action=True,
            safety_message=HARM_TO_OTHERS_SAFETY_MESSAGE,
            reasoning="Direct credible threat to another person detected"
        )

    # 3. SELF_HARM_RISK
    if self_harm_matches:
        return SafetyClassificationResult(
            category=SafetyRiskCategory.SELF_HARM_RISK,
            confidence=0.98,
            matched_signals=self_harm_matches,
            is_crisis=True,
            requires_immediate_action=True,
            safety_message=SELF_HARM_SAFETY_MESSAGE,
            reasoning="Direct self-harm or suicidal intent detected"
        )

    # 4. THIRD_PARTY_REPORT
    if third_party_matches:
        return SafetyClassificationResult(
            category=SafetyRiskCategory.THIRD_PARTY_REPORT,
            confidence=0.95,
            matched_signals=third_party_matches,
            is_crisis=False,
            requires_immediate_action=False,
            safety_message=THIRD_PARTY_SAFETY_MESSAGE,
            reasoning="Third-party risk disclosure reported"
        )

    # 5. EMOTIONAL_DISTRESS
    is_distress = any(pat.search(norm) for pat in _DISTRESS_SIGNALS) or has_inanimate_subject or has_casual_dampener
    if is_distress:
        return SafetyClassificationResult(
            category=SafetyRiskCategory.EMOTIONAL_DISTRESS,
            confidence=0.85,
            matched_signals=["emotional_distress_signal"],
            is_crisis=False,
            requires_immediate_action=False,
            reasoning="Emotional distress or casual hyperbole without crisis intent"
        )

    # 6. NONE
    return SafetyClassificationResult(
        category=SafetyRiskCategory.NONE,
        confidence=0.95,
        is_crisis=False,
        requires_immediate_action=False,
        reasoning="No safety risk detected"
    )
