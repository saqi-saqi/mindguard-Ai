"""
MindGuard - Intent & Safety Rules (Single Source of Truth)
---------------------------------------------------------
Canonical regex patterns for first-person crisis signals, physical/emotional distress
detection, and fast-path non-crisis intent classification with strict word boundaries.
"""

import re
from typing import Optional, List, Tuple


def _c(pattern: str) -> re.Pattern:
    """Compile case-insensitive regex pattern."""
    return re.compile(pattern, re.IGNORECASE)


def _normalize(text: str) -> str:
    """Basic text normalization for regex matching."""
    if not text:
        return ""
    t = text.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.lower()
    t = re.sub(r"\bk[!1]ll\b", "kill", t)
    t = re.sub(r"\bsu[1!l]cid", "suicid", t)
    t = re.sub(r"\bself\s+h[@a]rm\b", "self harm", t)
    t = " ".join(t.split())
    return t


# ---------------------------------------------------------------------------
# 1. CANONICAL FIRST-PERSON CRISIS PATTERNS (English only, strictly anchored)
# ---------------------------------------------------------------------------
CRISIS_EXPLICIT_PATTERNS_RAW: List[str] = [
    r"\b(?:going\s+to|gonna|about\s+to|want\s+to|wanna|will|plan\s+to|planning\s+to|need\s+to|decided\s+to|intend\s+to)\s+(?:commit\s+)?suicide\b",
    r"\b(?:i'?m|i\s+am|i\s+will|i\s+might)\s+(?:going\s+to\s+|gonna\s+)?suicide\b",
    r"\bcommit(?:ting)?\s+suicide\b",
    r"\b(?:going|gonna|about)\s+to\s+kill\s+myself\b",
    r"\bkill(?:ing)?\s+myself\b",
    r"\b(?:i\s+)?(?:have\s+had\s+enough\s+and\s+)?(?:just\s+|really\s+)?(?:want\s+to|wanna)\s+die(?:\s+(?:right\s+now|today|tonight))?\b",
    r"\b(?:today|right\s+now|tonight)\s+i\s+(?:have\s+had\s+enough\s+and\s+)?want\s+to\s+die\b",
    r"\b(?:want\s+to|wanna|need\s+to)\s+be\s+dead\b",
    r"\bi\s+wish\s+i\s+(?:was|were)\s+dead\b",
    r"\brather\s+be\s+dead\b|\bbetter\s+off\s+dead\b",
    r"\bi\s+(?:do\s+not|don'?t)\s+(?:want\s+to|wanna)\s+live(?:\s+anymore)?\b",
    r"\b(?:no|zero)\s+(?:reason|point)\s+(?:in|to)\s*(?:living|live|be\s+alive)\b",
    r"\bi\s+(?:cannot|can't)\s+go\s+on(?:\s+(?:like\s+this|anymore))\b",
    r"\bi\s+(?:do\s+not|don'?t)\s+want\s+to\s+be\s+here\b",
    r"\bwant\s+to\s+disappear\b",
    r"\bwant\s+to\s+end\s+it\s+all\b",
    r"\bwant(?:s|ed|ing)?\s+to\s+end\s+(?:my\s+life|my\s+existence|everything)\b|\bending\s+my\s+life\b",
    r"\b(?:i\s+)?(?:want|wanna)\s+to\s+stop\s+existing(?:\s+(?:today|tonight|right\s+now|this\s+time))?\b",
    r"\b(?:i\s+)?want\s+(?:this\s+)?pain\s+to\s+stop\s+by\s+dying\b",
    r"\b(?:wanna|want\s+to|need\s+to|going\s+to|gonna|decided\s+to|intend\s+to|ready\s+to)\s+end\s+(?:my\s+life|my\s+existence)\b",
    r"\btake\s+my\s+(?:own\s+)?life\b",
    r"\bi(?:'m| am| feel| feeling)?\s+suicidal\b",
    r"\bfeel(?:ing)?\s+suicidal\b",
    r"\bi(?:'m| am)?\s+(?:going\s+to|gonna|want\s+to|wanna)?\s+(?:self[- ]?harm|hurt\s+myself|harm\s+myself)\b",
    r"\bharm(?:ing)?\s+myself\b|\bhurt(?:ing)?\s+myself\b",
    r"\bcutting\s+myself\b|\bcut\s+myself\b",
    r"\bcut(?:ting)?\s+my\s+wrists?\b",
    r"\bi\s+(?:am\s+)?(?:going\s+to|gonna)\s+overdose\b|\boverdos(?:e|ing)\s+on\s+pills\b",
    r"\bplan(?:ning|ned)?\s+to\s+(?:die|kill\s+myself|end\s+my\s+life)\b",
    r"\bhang(?:ing)?\s+myself\b",
    r"\bdon'?t\s+want\s+to\s+exist\b",
    r"\bgive\s+up\s+on\s+life\b",
    r"\bend\s+my\s+pain\b",
    r"\bjump\s+(?:off|from)\s+(?:a|the)\s+(?:bridge|building|roof)\b",
    r"\bshoot\s+myself\b",
    r"\bstab\s+myself\b",
    r"\bpoison\s+myself\b",
    r"\bnot\s+safe\s+with\s+myself\b",
    r"\b(?:i\s+am|i'?m)\s+not\s+going\s+to\s+be\s+alive\s+(?:much\s+longer|for\s+long)(?:\s+on\s+purpose)?\b",
    r"\bswallowed\s+a\s+(?:bottle|bunch|handful)\s+of\s+(?:tablets|pills)\b",
    r"\btook\s+too\s+many\s+pills\b",
    r"\bwant\s+to\s+cut\s+again\b",
    r"\b(?:i\s+am|i'?m|am)\s+(?:ready|decided)\s+to\s+die\b",
    r"\bdone\s+with\s+life\s+and\s+want\s+to\s+die\b",
    r"\bwant\s+it\s+all\s+to\s+be\s+over\b",
    r"\b(?:can'?t|cannot)\s+keep\s+living\b",
    r"\bmujhe\s+mar\s+ja+na\s+hai\b",
    r"\bmain\s+(?:khudkushi|khud\s*kushi)\s+karna\s+chaht[ai]\s+(?:hoon|hun)\b",
    r"\bmain\s+apni\s+jaan\s+lena\s+chaht[ai]\s+(?:hoon|hun)\b",
    r"\bmain\s+zindagi\s+khatam\s+karna\s+chaht[ai]\s+(?:hoon|hun)\b",
]

CRISIS_EXPLICIT_PATTERNS: List[re.Pattern] = [_c(p) for p in CRISIS_EXPLICIT_PATTERNS_RAW]


def match_crisis_regex(text: str) -> bool:
    """Returns True if input matches any first-person explicit crisis pattern."""
    t = _normalize(text)
    if not t:
        return False
    return any(pat.search(t) for pat in CRISIS_EXPLICIT_PATTERNS)


# ---------------------------------------------------------------------------
# 2. PHYSICAL & EMOTIONAL DISTRESS SIGNAL GATE (Strict \b Boundaries)
# ---------------------------------------------------------------------------
DISTRESS_SIGNAL_PATTERNS_RAW: List[str] = [
    r"\bnot\s+feeling\b",
    r"\bhurt\b",
    r"\bpain\b",
    r"\bsick\b",
    r"\bill\b",
    r"\binjur(?:y|ed|ing)?\b",
    r"\bfell\b",
    r"\bfall\b",
    r"\bbleed(?:ing)?\b",
    r"\bhelp\s+me\b",
    r"\bemergency\b",
    r"\baccident\b",
    r"\bhospital\b",
    r"\bdying\b",
    r"\bdied\b",
    r"\bdead\b",
    r"\bkilling\s+me\b",
    r"\bscared\b",
    r"\bafraid\b",
    r"\bterrified\b",
    r"\bfrightened\b",
    r"\bpanicking\b",
    r"\boverwhelmed\b",
    r"\bhopeless\b",
    r"\bdesperate\b",
    r"\bcan't\s+cope\b",
    r"\bcant\s+cope\b",
]

DISTRESS_SIGNAL_PATTERNS: List[re.Pattern] = [_c(p) for p in DISTRESS_SIGNAL_PATTERNS_RAW]


def has_distress_signal(text: str) -> bool:
    """
    Returns True if message contains physical/emotional distress or emergency signals.
    Forces dynamic LLM handling instead of template fast-paths.
    """
    t = _normalize(text)
    if not t:
        return False
    return any(pat.search(t) for pat in DISTRESS_SIGNAL_PATTERNS)


# ---------------------------------------------------------------------------
# 3. UNIFIED FAST-PATH NON-CRISIS INTENT CLASSIFIER (Strict \b Boundaries)
# ---------------------------------------------------------------------------
FAST_PATH_INTENTS: List[Tuple[str, re.Pattern]] = [
    ("ANXIETY OR PANIC ATTACK", _c(r"\b(anxiet(?:y|ies)|anxious|panic|stress|stressed|exam|exams|test|tests|worried|worry)\b")),
    ("SLEEP OR FATIGUE ISSUE", _c(r"\b(sleep|sleeping|exhausted|tired|insomnia|can't\s+sleep|cant\s+sleep)\b")),
    ("MEDITATION OR COPING REQUEST", _c(r"\b(relaxation|meditation|exercise|calm|relax|breathing|breathe|coping)\b")),
    ("PHYSICAL OR DAILY NEED LIKE EATING OR RESTING", _c(r"\b(eat|food|hungry|lunch|dinner|snack)\b")),
    ("GRIEF OR SADNESS", _c(r"\b(sad|sadness|lonely|loneliness|grief|grieving|crying|down)\b")),
    ("BOT INFORMATION REQUEST", _c(r"\b(who\s+are\s+you|what\s+are\s+you|mindguard)\b")),
]

GREETING_PATTERN: re.Pattern = _c(r"\b(hi|hello|hey|wsp|what's\s+up|whats\s+up|good\s+morning|good\s+evening|sup)\b")


def match_fast_path_intent(text: str) -> Optional[str]:
    """
    Returns high-confidence non-crisis intent label for unambiguous inputs.
    Returns None for ambiguous or distress-carrying messages.
    """
    t = _normalize(text)
    if not t:
        return None

    # Distress messages bypass fast-path to allow contextual dynamic handling
    if has_distress_signal(t):
        return None

    for intent_name, pat in FAST_PATH_INTENTS:
        if pat.search(t):
            return intent_name

    # Greetings only match for short non-distress messages (<= 6 words)
    words = t.split()
    if len(words) <= 6 and GREETING_PATTERN.search(t):
        return "GREETING OR CASUAL CHAT"

    return None
