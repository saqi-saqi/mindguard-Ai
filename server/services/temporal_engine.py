"""
temporal_engine.py
==================

Dedicated temporal state extraction module for MindGuard's crisis detection.

Extracts and composes three discrete boolean signals:
1. has_past_anchor(text, pp) — detects past-tense crisis framing
2. has_confirmed_resolution(text) — detects explicit recovery language
3. has_acute_relapse(text, pp) — detects present-tense crisis recurrence after a past anchor

These replace the inline temporal logic previously scattered across
_contextual_bypass_reason() and evaluate_crisis_pipeline() in crisis_rules.py.

The module consumes low-level signals from generalizer.py's PreprocessResult
(has_past_recovery, has_present_ideation) and layers refined pattern matching
on top.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, List

from .generalizer import PreprocessResult, has_past_recovery_structure, has_present_ideation_markers


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class TemporalSignal:
    """Result of a single temporal boolean extractor."""
    detected: bool
    confidence: float = 0.0          # 0.0–1.0
    matched_span: Optional[str] = None  # the text fragment that triggered it
    pattern_name: Optional[str] = None  # which pattern matched (for audit/debug)


@dataclass
class TemporalState:
    """Composed result of all 3 temporal extractors."""
    past_anchor: TemporalSignal
    confirmed_resolution: TemporalSignal
    acute_relapse: TemporalSignal
    relapse_window: str = "none"  # "none" | "same_day" | "recent" | "distant"


# ---------------------------------------------------------------------------
# Compiled Pattern Sets
# ---------------------------------------------------------------------------

def _c(pattern: str) -> re.Pattern:
    """Compile a case-insensitive regex."""
    return re.compile(pattern, re.IGNORECASE)


# --- Past Historical Reflection Patterns ---
# (Migrated from crisis_rules.py _PAST_HISTORICAL_REFLECTION_PATTERNS L530-562)
_PAST_ANCHOR_PATTERNS: List[re.Pattern] = [
    _c(r"\bused\s+to\s+feel\s+suicidal\b"),
    _c(r"\bused\s+to\s+be\s+suicidal\b"),
    _c(r"\bused\s+to\s+think\s+about\s+ending\s+things\b"),
    _c(r"\bused\s+to\s+(?:cut|harm|hurt|self[\s-]?harm)\s+(?:myself\s+)?every\s+week\b"),
    _c(r"\bused\s+to\s+self[\s-]?harm\b"),
    _c(r"\bused\s+to\s+(?:cut|harm|hurt|self[\s-]?harm)\s+myself\b"),
    _c(r"\bused\s+to\s+relapse\s+constantly\b"),
    _c(r"\bwas\s+suicidal\s+once\b"),
    _c(r"\bhad\s+thoughts\s+of\s+dying\s+back\s+in\b"),
    _c(r"\bwas\s+feeling\s+suicidal\s+(?:last\s+(?:month|year)|before|back\s+then|long\s+ago)\b"),
    _c(r"\bhad\s+suicidal\s+thoughts\s+(?:in\s+the\s+past|back\s+in|years?\s+ago|last\s+year)\b"),
    _c(r"\bstruggled\s+(?:a\s+lot\s+)?with\s+(?:suicidal\s+thoughts|self[\s-]?harm\s+urges|depression)\s+(?:in\s+the\s+past|years?\s+ago|in\s+high\s+school|in\s+college|in\s+middle\s+school|as\s+a\s+kid|as\s+a\s+young\s+adult)\b"),
    _c(r"\brecovery\s+from\s+my\s+PTSD\b"),
    _c(r"\bsurvived\s+(?:a\s+)?(?:really\s+)?(?:bad\s+)?bout\s+of\b"),
    _c(r"\bback\s+in\s+\d{4}\s+i\s+attempted\b"),
    _c(r"\bclean\s+for\s+\d+\s+(?:years?|months?)\b"),
    _c(r"\bbeen\s+stable\s+for\s+(?:almost\s+)?(?:\d+|a|one|two|three|four|five)\s+(?:years?|months?)\b"),
    _c(r"\bhaven'?t\s+had\s+those\s+thoughts\s+in\s+\d+\s+(?:years?|months?)\b"),
    _c(r"\b(?:\d+|a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:years?|months?|decades?)\s+(?:ago|since)\b"),
    _c(r"\bit'?s\s+been\s+(?:a\s+)?(?:decade|year|years|months?)\s+since\b"),
    _c(r"\bwas\s+hospitalized\s+for\b.{0,40}\bback\s+in\s+(?:19|20)\d{2}\b"),
    _c(r"\bseveral\s+years\s+ago\s+i\s+was\s+in\s+a\s+really\s+dark\s+place\b"),
    _c(r"\b(?:that\s+was\s+a\s+)?dark\s+(?:period|time|phase|chapter|place|days)\b"),
    # Recovery milestone patterns
    _c(r"\b\d+\s+years?\s+clean\s+from\s+self[\s-]?harm\b"),
    _c(r"\bself[\s-]?harm\s+free\s+for\s+(?:over\s+)?\d+\b"),
    _c(r"\bhaven'?t\s+had\s+a\s+suicidal\s+thought\s+in\s+(?:years|months|a\s+long\s+time)\b"),
    _c(r"\bleft\s+(?:my\s+)?suicidal\s+past\s+behind\b"),
    _c(r"\bdoing\s+(?:so\s+)?much\s+better\s+than\s+when\s+i\s+used\s+to\b"),
    _c(r"\b(?:remember|recall)\s+(?:feeling|being|having)\s+(?:suicidal|depression|self[\s-]?harm)\b"),
    _c(r"\b(?:not|never)\s+crossed\s+my\s+mind\s+in\s+(?:years|months|a\s+long\s+time)\b"),
    _c(r"\bused\s+to\s+say\s+['\"]?kms['\"]?\s+(?:online\s+)?as\s+a\s+joke\b"),
    # Additional temporal anchors
    _c(r"\b(?:i\s+)?(?:was|had\s+been)\s+(?:depressed|suicidal|struggling|in\s+a\s+dark\s+place)\b"),
    _c(r"\bi\s+tried\s+to\s+kill\s+myself\s+(?:last\s+(?:year|month|week|weekend)|\d+\s+(?:years?|months?|weeks?)\s+ago|back\s+in\s+\d{4}|when\s+i\s+was\s+\d+)\b"),
    _c(r"\bi\s+attempted\s+suicide\s+(?:last\s+(?:year|month|week|weekend)|\d+\s+(?:years?|months?|weeks?)\s+ago|in\s+\d{4})\b"),
    _c(r"\bwhen\s+i\s+was\s+(?:younger|a\s+(?:kid|teenager|teen|child|student))\b"),
    _c(r"\byears\s+ago\s+(?:i\s+)?(?:tried|attempted|wanted)\b"),
    _c(r"\bin\s+the\s+past\s+(?:i\s+)?(?:tried|attempted|wanted|had)\b"),
]

# Temporal window classification patterns
_SAME_DAY_ANCHORS: List[re.Pattern] = [
    _c(r"\b(?:earlier\s+today|this\s+morning|this\s+afternoon|a\s+few\s+hours\s+ago|just\s+now|moments?\s+ago)\b"),
]

_RECENT_ANCHORS: List[re.Pattern] = [
    _c(r"\b(?:last\s+(?:night|week|weekend|month)|a\s+(?:few|couple)\s+(?:days?|weeks?)\s+ago|recently|the\s+other\s+day)\b"),
]

# --- Resolution Markers ---
# (Migrated from crisis_rules.py _RESOLUTION_MARKERS L579-592)
_RESOLUTION_PATTERNS: List[re.Pattern] = [
    _c(r"\bbut\s+i'?m\s+doing\s+(?:great|better|fine|well|okay|good)\s+now\b"),
    _c(r"\bi'?m\s+in\s+a\s+(?:good|better|different)\s+place\s+now\b"),
    _c(r"\bthat'?s\s+(?:all\s+)?behind\s+me\s+now\b"),
    _c(r"\bi'?m\s+(?:doing\s+)?(?:much\s+)?better\s+now\b"),
    _c(r"\bi'?m\s+honestly\s+happy\s+now\b"),
    _c(r"\bi'?m\s+thriving\s+now\b"),
    _c(r"\bproud\s+of\s+how\s+far\s+i'?ve\s+come\b"),
    _c(r"\bbeen\s+stable\s+for\s+.*\s+now\b"),
    _c(r"\bancient\s+history\s+now\b"),
    _c(r"\bi'?m\s+doing\s+well\b"),
    _c(r"\bturned\s+things\s+around\s+for\s+me\b"),
    _c(r"\bhelped\s+me\s+pull\s+through\b"),
    # Additional resolution markers
    _c(r"\bi\s+(?:got|received|sought|found)\s+help\b"),
    _c(r"\bi'?ve\s+(?:since\s+|fully\s+)?(?:recovered|healed|moved\s+on)\b"),
    _c(r"\bthat\s+was\s+(?:a\s+long\s+)?(?:time\s+ago|in\s+the\s+past)\b"),
    _c(r"\bi'?m\s+(?:safe|okay|fine|good|stable|healthy)\s+now\b"),
    _c(r"\bfeeling\s+(?:much\s+)?(?:stronger|better|safer)\s+(?:now|these\s+days|today)\b"),
    _c(r"\bhave\s+a\s+(?:strong\s+)?support\s+system\b"),
    _c(r"\b(?:today\s+)?i\s+feel\s+safe\b"),
]

# --- Acute Relapse Patterns ---
# (Partially migrated from crisis_rules.py _CONTINUATION_OVERRIDE_MARKERS L564-577
#  + NEW relapse-specific patterns that detect present-tense crisis recurrence)
_RELAPSE_PATTERNS: List[re.Pattern] = [
    # Migrated from _CONTINUATION_OVERRIDE_MARKERS
    _c(r"\bstill\s+(?:feel|feeling|have|having|want)\b"),
    _c(r"\beven\s+now\b"),
    _c(r"\bto\s+this\s+day\b"),
    _c(r"\band\s+(?:i\s+)?still\b"),
    _c(r"\bback\s+there\s+again\b"),
    _c(r"\brelaps(?:e|ed|ing)\b"),
    _c(r"\bholding\s+a\s+(?:razor|blade|knife)\s+right\s+now\b"),
    _c(r"\bbought\s+a\s+rope\s+today\b"),
    _c(r"\btonight\b"),
    _c(r"\blast\s+night\b"),
    _c(r"\bright\s+now\b"),
    # NEW: Explicit relapse recurrence patterns
    _c(r"\b(?:and\s+)?(?:now|again|today|tonight)\s+(?:i|I)\s+(?:feel|am|'m)\s+(?:the\s+same|that\s+way|like\s+(?:that|before|dying|ending)|suicidal|like\s+dying)\b"),
    _c(r"\b(?:it'?s?\s+)?(?:happening|coming\s+back|returning|starting)\s+again\b"),
    _c(r"\b(?:i(?:'m|\s+am)\s+)?(?:back\s+(?:in|to)\s+(?:that(?:\s+same)?|the\s+same)\s+(?:place|spot|headspace|mindset))\b"),
    _c(r"\b(?:those|the)\s+(?:feelings?|thoughts?|urges?)\s+(?:are|have)\s+(?:come|came|returned|back)\b"),
    _c(r"\b(?:i\s+)?(?:feel|am)\s+(?:exactly\s+)?(?:the\s+same(?:\s+way)?|like\s+before|that\s+way)\s+(?:all\s+over\s+)?(?:again|now)\b"),
    _c(r"\bbut\s+(?:now|today|lately|recently|this\s+(?:week|month))\s+(?:i|I)\s+(?:want\s+to\s+die|feel\s+(?:like\s+ending|terrible|hopeless|suicidal|overwhelmed)|am\s+thinking\s+about\s+(?:dying|suicide|killing))\b"),
    _c(r"\b(?:started|starting|began|beginning)\s+(?:to\s+)?(?:feel|feeling|think|thinking|have|having)\s+(?:that\s+way|those\s+thoughts?|suicidal\s+(?:thoughts?|feelings?|urges?))\s+again\b"),
    _c(r"\b(?:the|my)\s+(?:thoughts?|feelings?|urges?|darkness|depression)\s+(?:(?:is|are|has|have)\s+)?(?:come|came|coming|crept|creeping|returned|back)\b"),
    _c(r"\b(?:i'?m|i\s+am)\s+(?:right\s+)?back\s+(?:where\s+i\s+(?:started|was|began)|to\s+square\s+one)\b"),
    _c(r"\bhistory\s+(?:is\s+)?repeating\b"),
    _c(r"\bfeel\s+(?:the\s+same(?:\s+way)?|like\s+before|that\s+way)\s+(?:all\s+over\s+)?again\b"),
    _c(r"\bnow\s+i\s+feel\s+the\s+same\s+way\b"),
    _c(r"\bnow\s+i\s+feel\s+the\s+same\s+way\s+again\b"),
]


# ---------------------------------------------------------------------------
# Extractor Functions
# ---------------------------------------------------------------------------

def has_past_anchor(text: str, pp: Optional[PreprocessResult] = None) -> TemporalSignal:
    """
    Detect whether the text contains past-tense crisis framing.

    Consumes pp.has_past_recovery as a base signal from generalizer.py,
    then applies the full set of _PAST_ANCHOR_PATTERNS for broader coverage.

    Returns a TemporalSignal with temporal window classification.
    """
    # Check generalizer's base signal first
    if pp and pp.has_past_recovery:
        return TemporalSignal(
            detected=True,
            confidence=0.90,
            matched_span=None,
            pattern_name="generalizer.has_past_recovery",
        )

    # Check our full pattern set
    for pat in _PAST_ANCHOR_PATTERNS:
        m = pat.search(text)
        if m:
            return TemporalSignal(
                detected=True,
                confidence=0.85,
                matched_span=m.group(0),
                pattern_name=pat.pattern,
            )

    # Also check the generalizer function directly on the text
    if has_past_recovery_structure(text):
        return TemporalSignal(
            detected=True,
            confidence=0.85,
            matched_span=None,
            pattern_name="generalizer.has_past_recovery_structure",
        )

    return TemporalSignal(detected=False)


def has_confirmed_resolution(text: str) -> TemporalSignal:
    """
    Detect whether the text contains explicit recovery/resolution language.

    Requires positive evidence of recovery (e.g., 'but I'm better now',
    'I got help', 'that's behind me'). Absence of distress is NOT resolution.
    """
    for pat in _RESOLUTION_PATTERNS:
        m = pat.search(text)
        if m:
            return TemporalSignal(
                detected=True,
                confidence=0.85,
                matched_span=m.group(0),
                pattern_name=pat.pattern,
            )

    return TemporalSignal(detected=False)


def has_acute_relapse(text: str, pp: Optional[PreprocessResult] = None) -> TemporalSignal:
    """
    Detect present-tense crisis recurrence after a past anchor.

    This is the CORE GAP the reviewer identified. It detects language like:
    - "and now I feel the same way again"
    - "it's happening again / coming back / returning"
    - "I'm back in that place / headspace / mindset"
    - "those feelings/thoughts/urges have come back"
    - "started again / relapsing / the thoughts returned"

    Consumes pp.has_present_ideation as a base signal, then applies
    relapse-specific patterns for broader coverage.
    """
    # Check generalizer's base signal first
    if pp and pp.has_present_ideation:
        return TemporalSignal(
            detected=True,
            confidence=0.90,
            matched_span=None,
            pattern_name="generalizer.has_present_ideation",
        )

    # Check our relapse-specific patterns
    for pat in _RELAPSE_PATTERNS:
        m = pat.search(text)
        if m:
            return TemporalSignal(
                detected=True,
                confidence=0.85,
                matched_span=m.group(0),
                pattern_name=pat.pattern,
            )

    # Also check generalizer function directly
    if has_present_ideation_markers(text):
        return TemporalSignal(
            detected=True,
            confidence=0.85,
            matched_span=None,
            pattern_name="generalizer.has_present_ideation_markers",
        )

    return TemporalSignal(detected=False)


def _classify_temporal_window(text: str) -> str:
    """
    Classify the temporal distance of the past anchor.

    Returns: "same_day" | "recent" | "distant" | "none"
    """
    for pat in _SAME_DAY_ANCHORS:
        if pat.search(text):
            return "same_day"
    for pat in _RECENT_ANCHORS:
        if pat.search(text):
            return "recent"
    # If we have a past anchor but none of the short-window patterns matched,
    # it's a distant reference (years ago, back in school, etc.)
    return "distant"


def extract_temporal_state(text: str, pp: Optional[PreprocessResult] = None) -> TemporalState:
    """
    Compose the 3 boolean extractors into a single TemporalState.

    This is the primary entry point for temporal analysis. Returns a structured
    TemporalState containing all 3 signals and a temporal window classification.

    Decision matrix for downstream arbitration:

    | past_anchor | resolution | relapse | Behavior                           |
    |------------|------------|---------|------------------------------------|
    | True       | True       | True    | Imminent crisis (relapse overrides) |
    | True       | True       | False   | Safe bypass (resolved)              |
    | True       | False      | True    | Imminent crisis (relapse)           |
    | True       | False      | False   | Ambiguous (flag for review)         |
    | False      | *          | *       | No temporal modulation              |
    """
    past = has_past_anchor(text, pp)
    resolution = has_confirmed_resolution(text)
    relapse = has_acute_relapse(text, pp)

    # Classify temporal window only if a past anchor was detected
    window = _classify_temporal_window(text) if past.detected else "none"

    return TemporalState(
        past_anchor=past,
        confirmed_resolution=resolution,
        acute_relapse=relapse,
        relapse_window=window,
    )
