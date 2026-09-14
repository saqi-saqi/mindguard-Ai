"""
crisis_rules.py
================

Deterministic, regex-based rule engine for a mental-health conversational AI
("MindGuard") that flags user messages which may indicate suicide risk or
self-harm risk, while suppressing escalation for negated statements, past
history reflections, academic/media references, and idiomatic hyperbole.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

__all__ = [
    "CRISIS_PATTERNS",
    "CRISIS_PATTERN_CATEGORIES",
    "is_contextual_or_negated",
    "evaluate_crisis",
    "evaluate_deterministic_crisis",
    "evaluate_crisis_pipeline",
    "SAFETY_RESPONSE_TEMPLATE",
    "THIRD_PARTY_GUIDANCE_TEMPLATE",
]


from .intent_rules import CRISIS_EXPLICIT_PATTERNS, match_crisis_regex
from .generalizer import (
    preprocess_text,
    PreprocessResult,
    normalize_algospeak,
    detect_academic_frame,
    detect_fictional_frame,
    detect_third_party_frame,
    has_past_recovery_structure,
    has_present_ideation_markers,
    detect_preparatory_behavior,
    detect_protective_behavior,
    is_informational_or_coping_query,
)
from .temporal_engine import (
    has_past_anchor,
    has_confirmed_resolution,
    has_acute_relapse,
    extract_temporal_state,
)
from .discourse_evaluator import evaluate_discourse
from .semantic_concepts import (
    detect_fatal_sleep,
    detect_concealment,
    detect_irreversible_exit,
    extract_all_concepts,
)
from .text_normalizer import normalize_evasion_text
from .precedence_arbitrator import (
    arbitrate,
    ArbitrationInput,
    ArbitrationResult,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

from typing import Dict, List, Optional, Tuple, Union

def _c(pattern: Union[str, re.Pattern]) -> re.Pattern:
    """Compile a case-insensitive regex if string, or return pattern as-is if already compiled."""
    if isinstance(pattern, re.Pattern):
        return pattern
    return re.compile(pattern, re.IGNORECASE)


def _normalize(text: str) -> str:
    """Clean lowercasing: normalize curly quotes/apostrophes, typos, leetspeak, discourse markers, and whitespace."""
    if not text:
        return ""
    t = normalize_evasion_text(text)
    t = t.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.lower()
    t, _ = normalize_algospeak(t)
    t = re.sub(r"\bs[\*#@!]icide\b", "suicide", t)
    t = re.sub(r"\bk\s+i\s+l\s+l\s+m\s+y\s+s\s+e\s+l\s+f\b", "kill myself", t)
    t = re.sub(r"\bnot\s+gonna\s+lie\b", "truthfully", t)
    t = re.sub(r"\bngl\b", "truthfully", t)
    t = re.sub(r"\btbh\b", "truthfully", t)
    t = re.sub(r"\bto\s+be\s+honest\b", "truthfully", t)
    t = re.sub(r"\bno\s+cap\b", "truthfully", t)
    t = re.sub(r"\bk[!1]ll\b", "kill", t)
    t = re.sub(r"\bkll\b", "kill", t)
    t = re.sub(r"\bwnt\b", "want", t)
    t = re.sub(r"\bcom+it\b", "commit", t)
    t = re.sub(r"\bsu[1!l]cid", "suicid", t)
    t = re.sub(r"\bsu1c1d", "suicid", t)
    # Extended leetspeak: c0mm!t -> commit, d!e -> die, 0verd0se -> overdose
    t = re.sub(r"\bc0mm[!1i]t", "commit", t)
    t = re.sub(r"\bd[!1i]e\b(?!\s+(?:my\s+)?(?:hair|fabric|cloth|yarn|shirt|dress|eggs?))", "die", t)
    t = re.sub(r"\b0verd0se\b", "overdose", t)
    t = re.sub(r"\bov[3e]rdose\b", "overdose", t)
    t = re.sub(r"\bl[!1i]fe\b(?!\s+back)", "life", t)
    t = re.sub(r"\bh[8@]te\b", "hate", t)
    t = re.sub(r"\bcatch\s+the\s+bus\b", "commit suicide", t)
    t = re.sub(r"\bpull\s+the\s+plug\s+on\s+(?:this\s+)?life\b", "end my life", t)
    t = re.sub(r"\bself\s+h[@a]rm\b", "self harm", t)
    t = re.sub(r"\bk[.\s]*y[.\s]*s\b", "kys", t)
    t = re.sub(r"\bw@nna\b", "wanna", t)
    t = " ".join(t.split())
    return t


# Sentence splitter that avoids breaking on abbreviations (dr., mr., e.g., i.e., vs.), decimals, or ellipses (...)
_ABBREVIATION_PROTECT_RE = re.compile(
    r"\b(?:dr|mr|mrs|ms|prof|sr|jr|e\.g|i\.e|vs|st|approx)\.", re.IGNORECASE
)


def _split_sentences(text: str) -> List[str]:
    """
    Sentence splitter for per-sentence negation/context evaluation.
    Preserves sentences intact across common abbreviations, decimals, and ellipses.
    """
    if not text:
        return []
    # Protect periods in known abbreviations, ellipses, and decimals
    t = _ABBREVIATION_PROTECT_RE.sub(lambda m: m.group(0).replace(".", "___DOT___"), text)
    t = re.sub(r"\.\.\.", "___ELLIPSIS___", t)
    t = re.sub(r"(\d+)\.(\d+)", r"\1___DECIMAL___\2", t)

    parts = re.split(r"(?<=[.!?])\s+|[\n\r]+", t)
    sentences = []
    for p in parts:
        if p and p.strip():
            s = p.replace("___DOT___", ".").replace("___ELLIPSIS___", "...").replace("___DECIMAL___", ".")
            sentences.append(s.strip())
    return sentences or ([text.strip()] if text.strip() else [])


# ---------------------------------------------------------------------------
# SECTION 1 -- CRISIS SIGNAL PATTERNS
# ---------------------------------------------------------------------------

@dataclass
class PatternCategory:
    name: str
    severity: int  # 1 (elevated) .. 5 (imminent)
    patterns: List[re.Pattern]


# 1. EXPLICIT SUICIDAL INTENT (Imported from canonical intent_rules.py)
_EXPLICIT_SUICIDAL_INTENT = CRISIS_EXPLICIT_PATTERNS

# 2. INDIRECT / IMPLICIT DISTRESS -------------------------------------------
_INDIRECT_IMPLICIT_DISTRESS = [
    r"\b(?:i\s+)?feel\s+like\s+disappearing\s+(?:forever|for\s+good)?\b",
    r"\bdisappear\s+(?:forever|for\s+good)\b",
    r"\bi\s+(?:do\s+not|don'?t)\s+see\s+a\s+future\s+for\s+myself\b",
    r"\bdon'?t\s+see\s+(?:a|any)\s+future\s+for\s+myself\b",
    r"\bi'?ve\s+made\s+up\s+my\s+mind.*\bdon'?t\s+want\s+to\s+keep\s+living\b",
    r"\bthe\s+only\s+way\s+out\s+feels\s+like\s+ending\s+my\s+life\b",
    r"\bi'?m\s+done\s+fighting.*\bgive\s+up\s+on\s+everything\s+including\s+myself\b",
    r"\bi(?:\s+have|'ve)\s+been\s+planning\s+how\s+to\s+end\s+things\b",
    r"\bi\s+(?:do\s+not|don'?t)\s+think\s+i\s+can\s+survive\s+another\s+day\b",
    r"\b(?:can'?t|cannot|don'?t\s+think\s+i\s+can)\s+survive\s+(?:until\s+morning|another\s+day)\b",
    r"\b(?:i'?m\s+)?ready\s+to\s+give\s+up\s+on\s+life\b",
    r"\bgiving\s+up\s+on\s+everything\b",
    r"\bdon'?t\s+want\s+to\s+wake\s+up\b",
    r"\bwish(?:ing)?\s+(?:i\s+)?wouldn'?t\s+wake\s+up\b",
    r"\bwish(?:ing)?\s+i\s+(?:would|will)?\s*(?:just\s+)?not\s+wake\s+up\b",
    r"\bwant(?:ed)?\s+(?:the\s+)?pain\s+to\s+stop\s+permanently\b",
    r"\btired\s+of\s+existing\b",
    r"\bnot\s+existing\b",
    r"\bwant(?:ed)?\s+it\s+all\s+to\s+end\b",
    r"\b(?:no|zero)\s+(?:reason|point)\s+(?:in|to)\s*(?:staying|stay|keep\s+going|live|be)\s+alive\b",
    r"\bdon'?t\s+want\s+to\s+(?:be\s+here|exist)\s+anymore\b",
    r"\btired\s+of\s+(?:living|being\s+alive)\b",
    r"\bwhat'?s\s+the\s+point\s+of\s+(?:living|being\s+alive)\b",
    r"\bimagining\s+everyone\s+at\s+peace\s+without\s+me\b",
    r"\bforever\s+kind\s+of\s+rest\b",
    r"\bstop\s+feeling\s+anything\s+permanently\b",
    r"\bnever\s+wake\s+up\b",
    r"\b(?:i\s+)?can'?t\s+remember\s+the\s+last\s+time\s+i\s+felt\s+o?k\b",
    r"\b(?:i\s+)?(?:keep\s+)?(?:feel\s+like\s+)?can'?t\s+remember\s+the\s+last\s+time\s+i\s+felt\s+(?:okay|ok)\b",
    r"\b(?:see\s+no|don'?t\s+see\s+a|no)\s+way\s+out\b",
    r"\b(?:suicide|death|dying|killing\s+myself)\s+is\s+(?:my\s+|the\s+)?(?:only\s+)?(?:way\s+out|option|choice|answer)\b",
    r"\b(?:is\s+my|feels\s+like\s+my|the)\s+only\s+way\s+out\b",
    r"\b(?:i\s+)?don'?t\s+think\s+i\s+can\s+do\s+this\s+anymore\b",
    r"\bdisappear\s+from\s+existence\b",
    r"\bdon'?t\s+see\s+the\s+point\s+in\s+staying\s+alive\b",
    r"\bthinking\s+about\s+ending\s+everything\b",
    r"\b(?:can'?t|cannot)\s+keep\s+living\s+like\s+this\b",
    r"\bwant\s+(?:it|everything)\s+to\s+stop\b",
    r"\bwant\s+it\s+all\s+to\s+be\s+over\b",
    r"\bcan'?t\s+take\s+(?:it|this)\s+anymore\b",
    r"\bdon'?t\s+think\s+i\s+can\s+(?:keep\s+going|make\s+it\s+through\s+the\s+night)\b",
    r"\bgoing\s+through\s+the\s+motions\b",
    r"\bi'?m\s+just\s+going\s+thru\s+the\s+motions\b",
    r"\brunning\s+out\s+of\s+energy\s+to\s+keep\s+pretending\b",
    r"\bfeel\s+hopeless\s+about\s+(?:pretty\s+much\s+)?everything\b",
    r"\bstuck\s+and\s+there'?s\s+no\s+way\s+forward\b",
    r"\bfeel\s+trapped\s+and\s+see\s+no\s+way\s+out\b",
    r"\b(?:done|can'?t\s+keep|don'?t\s+think\s+i\s+can\s+keep)\s+fighting\s+this\s+pain\b",
    # Compound first-person hopelessness signals. These are deliberately
    # specific combinations rather than broad sadness/anxiety keywords.
    r"\b(?:i\s+)?(?:am\s+|i'?m\s+)?(?:so\s+)?tired\s+of\s+everything\b",
    r"\bexhausted\s+from\s+just\s+existing\b",
    r"\bfeel\s+numb\s+to\s+everything\b",
    r"\bfeel\s+like\s+i'?m\s+drowning\s+and\s+no\s*one\s+notices\b",
    r"\b(?:i\s+)?can'?t\s+keep\s+going\s+like\s+this\b",
    r"\b(?:i\s+)?can'?t\s+stop\s+crying\s+and\s+i\s+don'?t\s+know\s+why\b",
    r"\b(?:i\s+)?am\s+barely\s+holding\s+it\s+together\b",
    r"\bfeel\s+like\s+everything\s+is\s+falling\s+apart\s+and\s+i\s+can'?t\s+stop\s+it\b",
    r"\bnothing\s+will\s+ever\s+get\s+better\b",
    r"\b(?:truthfully\s+|honestly\s+)?(?:i\s+am|i'?m)\s+so\s+overwhelmed\s+i\s+don'?t\s+know\s+what\s+to\s+do\b",
    r"\b(?:i\s+)?don'?t\s+feel\s+like\s+myself\s+anymore\b",
    r"\b(?:i\s+)?(?:feel\s+like\s+)?i\s+have\s+nothing\s+left\s+to\s+give\b",
    r"\bnot\s+a\s+big\s+deal\s+but\s+(?:i\s+have|i\s+got|i'?ve\s+got)\s+a\s+(?:plan|lethal\s+plan)\b",
    r"\bdon'?t\s+worry,?\s*(?:about\s+me,?\s*)?(?:i\s+just\s+)?won'?t\s+be\s+here\s+(?:tomorrow|next\s+week|much\s+longer)\b",
    r"\bab\s+jee+ne\s+ki\s+him+at\s+nah?i\s*(?:rahi|hai)?\b",
    r"\bzindagi\s+se\s+tang\s+a+a?\s+gaya\s+(?:hoon|hun)\b",
    r"\b(?:maine?\s+)?marne\s+ka\s+waqt\s+a+a?gaya\s*(?:hai)?\b",
    r"\b(?:mujhe\s+)?zinda\s+nah?i\s+rehna(?:\s+chaht[ai]\s+(?:hoon|hun))?\b",
    # --- Expanded Roman Urdu / Hindi crisis phrases ---
    r"\bkhud\s*ko\s*khatam\s*kar",
    r"\baaj\s*raat.*khatam\s*kar",
    r"\bneend\s*ki\s*goli(?:yan|yaan)\b",
    r"\bmar\s*jana\s*chahta\b",
    r"\bchhat\s*se\s*kud\b",
    r"\bmarna\s*(?:hi|he)\s*behtar\b",
    r"\bblade\s*se\s*nas[il]\s*kaat\b",
    r"\bdarya\s*mein\s*dub\b",
    r"\bdawa\s*zyada\s*kha\b",
    r"\bzindagi\s*se\s*haar\b",
    r"\bapni\s*zindagi\s*lena\b",
    r"\bmaut\s*naseeb\s*ho\b",
    r"\bsab\s*kuch\s*khatam\s*karna\b",
    r"\bmar\s*jaon?ga\b",
    r"\bmake\s+everything\s+stop\b",
    r"\bpicturing\s+myself\s+dead\b",
    r"\bwant\s+that\s+to\s+happen\b",
    r"\bthe\s+blade\s+is\s+right\s+beside\s+me\b",
    r"\bactually\s+intend\s+to\s+do\s+it\b",
]

# 3. BURDEN & GOODBYE STATEMENTS ---------------------------------------------
_BURDEN_AND_GOODBYE = [
    r"\b(?:everyone|everybody|they|my\s+family|people)\s+(?:would\s+be|is|are)\s+(?:relieved|better\s+off|much\s+better\s+off)\s+(?:if\s+i\s+(?:was|were)\s+gone|without\s+me)\b",
    r"\b(?:relieved|relief)\s+if\s+i\s+(?:was|were)\s+gone\b",
    r"\b(?:writ(?:e|ten|ing)|wrote)\s+(?:a\s+)?(?:goodbye|farewell)\s+(?:letter|note|message)\b",
    r"\b(?:writ(?:e|ten|ing)|wrote)\s+letters?\s+for\s+(?:everyone|my\s+family|all)\b",
    r"\bgoodbye\s+(?:note|letter|world|everyone|all|friends)\b",
    r"\b(?:this\s+is\s+)?my\s+final\s+(?:message|goodbye|note|letter|words)\b",
    r"\bfinal\s+message\s+(?:to\s+my\s+family)?\b",
    r"\bthis\s+is\s+my\s+last\s+(?:message|goodbye|note|words)\b",
    r"\bsaying\s+my\s+last\s+goodbye\b",
    r"\b(?:i'?m|i\s+am)\s+(?:such\s+a|a)?\s*burden\s+(?:to|on)\s+(?:everyone|my\s+family|them)\b",
    r"\bfeel\s+like\s+a\s+burden\b",
    r"\bdon'?t\s+want\s+to\s+be\s+a\s+burden\s+anymore\b",
    r"\bwon'?t\s+have\s+to\s+deal\s+with\s+me\s+(?:anymore|much\s+longer)\b",
    r"\bwriting\s+(?:my\s+)?(?:will|suicide\s+note)\b",
    r"\bbetter\s+off\s+without\s+me\b",
    r"\bi\s+told\s+my\s+(?:[\w']+\s+)*\w+\s+today\s+how\s+much\s+they\s+meant\s+to\s+me,\s+felt\s+important\s+to\s+say\s+it\s+now\b",
    r"\bthank\s+you\s+for\s+everything,\s+i\s+just\s+wanted\s+to\s+say\s+goodbye\b",
    r"\bdeleted\s+all\s+my\s+social\s+media\s+and\s+said\s+my\s+goodbyes\b",
    r"\bnone\s+of\s+this\s+was\s+your\s+fault\b",
    r"\bdone\s+being\s+a\s+burden\b",
    r"\b(?:im|i'?m)\s+sorry\s+for\s+everything,?\s*(?:please\s+)?forgive\s+me\b",
    r"\b(?:im|i'?m)\s+leaving\s+for\s+good\b",
    r"\bcan'?t\s+keep\s+doing\s+this\s+to\s+you\s+all\b",
    r"\bcouldn'?t\s+be\s+stronger\s+for\s+(?:you|u)\b",
    r"\btake\s+care\s+of\s+my\s+things\s+after\s+i'?m\s+gone\b",
    r"\balready\s+said\s+my\s+goodbyes\b",
    r"\btired\s+of\s+being\s+a\s+weight\s+on\s+everyone\b",
    r"\bwanted\s+to\s+say\s+goodbye\s+before\s+it'?s\s+too\s+late\b",
    r"\bbetter\s+this\s+way\s+for\s+everyone\b",
    r"\bforgive\s+me\b",
    r"\bsorry\s+i\s+couldn'?t\s+stay\b",
    r"\bthis\s+is\s+goodbye\b",
    r"\btell\s+everyone\s+i\s+loved\s+them\b",
    r"\b(?:you'd|youd|you'll|you\s+would|everyone\s+would)\s+all?\s+be\s+happier\s+(?:if|once)\s+i\s+(?:wasn't|was\s+not|were\s+not|am)\s+(?:around|gone)\b",
    r"\bmake\s+sure\s+my\s+[\w\s]{1,20}\s+is\s+taken\s+care\s+of\s+after\s+i'?m\s+gone\b",
    r"\b(?:everyone|they)\s+will\s+finally\s+get\s+a\s+break\s+once\s+i'?m\s+gone\b",
    r"\bsorry\s+for\s+being\s+such\s+a\s+weight\s+on\s+everyone\b",
    r"\btake\s+care\s+of\s+my\s+(?:pets|dog|cat|things|stuff)\s+after\s+i'?m\s+gone\b",
    r"\byou'?d\s+all\s+be\s+happier\s+if\s+i\s+wasn'?t\s+around\b",
    r"\b(?:i'?m\s+)?(?:just\s+)?a\s+burden\s+to\s+everyone\s+i\s+love\b",
    r"\b(?:you|u)\s+deserve\s+better\s+than\s+dealing\s+with\s+me\b",
    r"\b(?:i'?m\s+)?sorry\s+i\s+couldn'?t\s+be\s+stronger\s+for\s+you\b",
    r"\bwanted\s+to\s+say\s+goodbye\s+(?:b4|before)\s+it'?s\s+too\s+late\b",
    r"\bwriting\s+goodbye\s+(?:messages?|letters?|notes?)\b",
    r"\bfinished\s+my\s+goodbye\s+letters?\b",
    r"\bsaying\s+goodbye\s+to\s+people\s+without\s+telling\s+them\b",
    r"\bwill\s+be\s+better\s+off\s+with\s+.*\s+because\s+i\s+will\s+not\s+be\s+around\b",
    r"\bknows?\s+where\s+my\s+important\s+documents\s+are\s+before\s+i\s+go\b",
    r"\bgave\s+away\s+my\s+favorite\s+things\b",
    r"\bdo\s+not\s+expect\s+to\s+need\s+them\s+again\b",
    r"\bwant\s+this\s+to\s+be\s+my\s+last\s+birthday\b",
]

# 4. LETHAL MEANS & PREPARATION ----------------------------------------------
_LETHAL_MEANS_AND_PREPARATION = [
    r"\b(?:buy|bought|buying|stockpil(?:e|ing|ed)|gather(?:ed|ing)?)\s+(?:[\w\s]{1,30}\s+)?(?:pills|medication|tablets)\b",
    r"\blook(?:ing)?\s+for\s+a\s+bridge\b",
    r"\bfound\s+a\s+rope\b",
    r"\bgiv(?:e|en|ing|e)\s+(?:away\s+)?my\s+(?:possessions|belongings|things|stuff|camera|bike|car|jewelry|guitar|books|record\s+collection)\b",
    r"\bwon'?t\s+be\s+needing\s+(?:it|them|anything|my\s+room)\b",
    r"\bthey\s+won'?t\s+need\s+to\s+ask\s+why\s+soon\b",
    r"\btold\s+(?:them|my\s+\w+)\s+(?:to\s+take\s+care\s+of\s+it|they\s+won'?t\s+need\s+to\s+ask)\b",
    r"\bsaying\s+goodbye\s+to\s+(?:friends|family)\s+forever\b",
    r"\bbought\s+a\s+gun\b",
    r"\bstockpil(?:e|ing|ed)\s+(?:pills|medication)\b",
    r"\b(?:wrote|hid)\s+a\s+(?:suicide\s+)?note\b",
    r"\bpick(?:ed|ing)\s+(?:out\s+)?a\s+(?:date|day|the\s+date|the\s+day)\s+to\s+(?:die|do\s+it|happen)\b",
    r"\bresearch(?:ing|ed)?\s+(?:how\s+to|lethal\s+doses)\b",
    r"\bsettled\s+all\s+my\s+debts\b",
    r"\bwrote\s+(?:a|my)\s+will\b",
    r"\bhave\s+everything\s+(?:i\s+need\s+)?(?:set\s+up|ready)\s+(?:already|to\s+go)?\b",
    r"\bnot\s+going\s+to\s+need\s+any\s+of\s+my\s+stuff\b",
    r"\bmade\s+peace\s+with\s+it,?\s*everything\s+is\s+already\s+arranged\b",
    r"\bcleaned\s+out\s+my\s+room\b",
    r"\bfigured\s+out\s+exactly\s+how\s+it'?s\s+going\s+to\s+happen\b",
    r"\btheres?\s+no\s+going\s+back\s+now\b",
    r"\bnot\s+telling\s+anyone\s+until\s+after\b",
    r"\balready\s+wrote\s+my\s+will\b",
    r"\bmade\s+all\s+the\s+arrangements\s+already\b",
    r"\btold\s+my\s+[\w\s]{1,20}\s+goodbye\s+without\s+saying\s+why\b",
    r"\bhave\s+a\s+plan\s+ready\b",
    r"\bgathered\s+all\s+my\s+medication\s+bottles\b",
    r"\bbought\s+(?:a|the)\s+rope\b",
    r"\bpicked\s+the\s+bridge\b",
    r"\bhave\s+set\s+a\s+date\s+and\s+i'?m\s+sticking\s+to\s+it\b",
    r"\bhave\s+thought\s+this\s+through\s+completely,?\s+it'?s\s+decided\b",
    r"\bhave\s+decided\s+when\s+it'?s\s+going\s+to\s+happen\b",
    r"\bpicked\s+the\s+day\s+it'?s\s+going\s+to\s+happen\b",
    r"\b(?:drank|drinking|swallowed|ingested)\s+(?:a\s+)?(?:bottle\s+of\s+|cup\s+of\s+)?(?:bleach|poison|chemicals|toxic)\b",
    r"\b(?:took|swallowed|downed|popped)\s+(?:\d+|all|the\s+entire\s+bottle\s+of|a\s+handful\s+of|my\s+whole\s+prescription\s+of)\s+(?:sleeping\s+)?(?:pills|tablets|capsules|meds|medication|painkillers)\b",
    r"\boverdos(?:ed|ing)\s+on\s+(?:my\s+)?(?:pills|meds|medication|drugs|painkillers)\b",
    r"\bhave\s+the\s+pills\s+(?:ready\s+)?(?:in\s+front\s+of\s+me|ready|here)\b",
    # --- Expanded means: medication hoarding, chemicals, vehicle, ingestion ---
    r"\bhoarding\s+(?:my\s+)?(?:pills|meds|medication|antidepressants?|painkillers?)\b",
    r"\bsaving\s+up\s+(?:my\s+)?(?:pills|meds|painkillers?|medication)\b",
    r"\bstash\s+of\s+.{0,30}?(?:pills|medication|tylenol|sleeping\s+pills)",
    r"\bmix(?:ing|ed)?\s+bleach\s+and\s+ammonia\b",
    r"\bdrank\s+(?:the\s+)?bleach\b",
    r"\bbleach\s+is\s+next\s+to\s+me\b",
    r"\bthinking\s+about\s+drinking\s+it\b",
    r"\bget\s+a\s+lot\s+of\s+sleeping\s+(?:tablets|pills)\b",
    r"\bmix(?:ed|ing)?\s+(?:the\s+)?(?:medicines?|meds|pills)\s+together\b",
    r"\bintend\s+to\s+take\s+them\s+all\b",
    r"\btake\s+them\s+all\s+at\s+once\b",
    r"\bdrank\s+something\s+poisonous\b",
    r"\bplanning\s+my\s+death\b",
    r"\bplanning\s+my\s+death\s+for\s+days\b",
    r"\bswallow(?:ed|ing)?\s+(?:a\s+)?(?:whole\s+)?bottle\s+of\s+(?:ibuprofen|pills|tylenol|advil|medication|aspirin)",
    r"\bcrash(?:ing)?\s+(?:my\s+)?car\s+(?:into|on\s+purpose)",
    r"\bstep(?:ping)?\s+in\s+front\s+of\s+(?:a\s+)?(?:car|truck|train|bus|vehicle|subway)",
    r"\bdrive\s+(?:my\s+car\s+)?into\s+(?:a\s+)?(?:wall|tree|median|oncoming)",
    r"\bwash(?:ing)?\s+down\s+.{0,20}?(?:pills|painkillers?|meds)\s+with\s+alcohol",
    r"\bcrushed?\s+up\s+(?:my\s+)?.{0,20}?(?:meds|pills|medication).*?overdose",
    r"\breplac(?:ed|ing)?\s+(?:my\s+)?.{0,20}?(?:vitamins?|meds)\s+with\s+poison",
    r"\brunning\s+(?:the\s+)?car\s+in\s+(?:the\s+)?garage\b",
    r"\bdrank\s+(?:the\s+)?(?:pesticide|rat\s+poison|antifreeze)\b",
    r"\bgoing\s+to\s+swallow\s+all\s+(?:these\s+)?(?:sleeping\s+)?pills\b",
]

# 5. SUBTLE SLANG & INFORMAL PHRASING ----------------------------------------
_SUBTLE_SLANG_AND_INFORMAL = [
    r"\bfinna\s+end\s+it\s+all\b",
    r"\b(?:boutta|bout\s+to)\s+jump\s+off\b",
    r"\bgonna\s+unalive\s+myself\b",
    r"\bunalive\s+myself\b",
    r"\bclock(?:ing)?\s+out\s+of\s+life\b",
    r"\bquit+ing\s+life\b",
    r"\bcheck(?:ing)?\s+out\s+(?:early|for\s+good)\b",
    r"\bkms\b",
    r"\bkys\b",
    r"\bk[.\s]*y[.\s]*s\b",
    r"\bk[.\s]*m[.\s]*s\b",
    r"\bkill\s+yourself\b",
    r"\bi\s+should\s+kill\s+myself\b",
    r"\bself[\s-]?delet(?:e|ing)\b",
    r"\bsewer\s*slide\b",
    r"\bi\s+should\s+kys\b",
    r"\b(?:tryna|trying\s+to|gonna|finna|bout\s+to)?\s*(?:log\s+off|peace\s+out|self\s*delete|tap\s+out|check\s+out|dip|off\s+myself|unalive\s+myself|unalive)\s*(?:for\s+good|permanently|forever|fr)?\b",
    r"\bend(?:ing)?\s+the\s+sim\b",
    r"\bnot\s+built\s+for\s+this\s+world\b",
    r"\bdone\s+with\s+this\s+level\s+called\s+life\b",
    r"\bnot\s+(?:tryna|trying\s+to)\s+see\s+tomorrow\b",
    r"\bpeace\s+out\s+permanently\b",
    r"\bkms\s+(?:is\s+looking\s+pretty\s+good|fr|no\s+cap)\b",
    r"\b(?:im|i'?m)\s+out\s+for\s+real\s+this\s+time\b",
    r"\b(?:im|i'?m)\s+out,?\s+for\s+real\s+this\s+time\b",
    r"\b(?:tryna|trying\s+to)\s+catch\s+the\s+bus\b",
    r"\btaking\s+the\s+early\s+exit\b",
    r"\bdone\s+playing\s+this\s+game\s+called\s+life\b",
    r"\b(?:im|i'?m)\s+so\s+done\s+with\s+life\b",
    r"\bthinking\s+about\s+unaliv(?:ing|e)\s+myself\b",
    # --- Gaming/digital suicide metaphors ---
    r"\breset\s+the\s+sim.*no\s+respawn",
    r"\breset\s+the\s+sim\b",
    r"\b(?:final|forever)\s+logout\b",
    r"\bpermanent\s+offline\s+button\b",
    r"\bdelete\s+the\s+character\b",
    r"\bone\s+bad\s+hour\s+away\s+from\b",
    r"\bdone\s+grinding\b",
    r"\bpermanent\s+ban\s+irl\b",
    r"\bcatch\s+a\s+permanent\s+ban\b",
    r"\bdelet(?:e|ing)\s+(?:my\s+)?account\s+irl\b",
    r"\bpass\s+the\s+controller\s+to\s+the\s+afterlife\b",
    r"\byeet\s+(?:myself|me)\s+(?:off|out\s+of)\b",
    r"\bpull\s+the\s+plug\s+on\s+this\s+character\b",
    r"\bcatch\s+me\s+unaliv(?:e|ing)\b",
]

# 6. SELF-HARM & CUTTING ------------------------------------------------------
_SELF_HARM_AND_CUTTING = [
    r"\bcut(?:ting)?\s+my\s+(?:wrists?|thighs?|arms?|legs?)\b",
    r"\bcutting\s+myself\b",
    r"\bharm(?:ing)?\s+myself\b",
    r"\bhurt(?:ing)?\s+myself\b",
    r"\bbleed(?:ing)?\s+out\b",
    r"\bburn(?:ing)?\s+my\s+skin\b",
    r"\bdeserve\s+to\s+feel\s+pain\b",
    r"\bself[\s-]?harm(?:ing)?\b",
    r"\bpunish(?:ing)?\s+myself\s+physically\b",
    r"\bscratch(?:ing)?\s+myself\s+until\s+i\s+bleed\b",
    r"\bcutting\s+again\b",
    r"\bself[\s-]?harmed\s+(?:for\s+the\s+first\s+time|again)\b",
    # --- NSSI expansion: non-cutting self-injury mechanisms ---
    r"\bhit(?:ting)?\s+(?:my\s+)?head\s+(?:against|on|into)\s+(?:the\s+)?wall",
    r"\bbang(?:ing)?\s+(?:my\s+)?head",
    r"\bpunch(?:ing)?\s+(?:my\s+)?(?:own\s+)?face\b",
    r"\bbit(?:e|ing|ten)?\s+(?:my\s+)?(?:own\s+)?(?:arm|hand|lip|finger)\s+(?:so\s+)?hard",
    r"\bpull(?:ing|ed)?\s+out\s+(?:a\s+)?(?:handful\s+of\s+)?(?:my\s+)?(?:own\s+)?hair\b",
    r"\btwist(?:ing)?\s+(?:my\s+)?(?:own\s+)?fingers?\s+back",
    r"\bpour(?:ing|ed)?\s+hot\s+(?:wax|water|oil)\s+on\s+(?:my\s+)?(?:own\s+)?skin",
    r"\bscrap(?:ing|ed)?\s+(?:my\s+)?skin\s+with",
    r"\bscratch(?:ing|ed)?\s+(?:my\s+)?skin\s+until",
    r"\bpress(?:ing)?\s+(?:my\s+)?(?:arm|hand|skin)\s+against\s+(?:the\s+)?(?:hot\s+)?stove",
    r"\bcarv(?:ing|ed)?\s+.{0,20}?(?:into|on)\s+(?:my\s+)?(?:thigh|arm|wrist|leg|skin)",
    r"\bswallow(?:ed|ing)?\s+glass\b",
    r"\bslic(?:e|ing)\s+(?:my\s+)?(?:wrist|arm|thigh)s?\b",
    r"\bhit(?:ting)?\s+myself\s+(?:in\s+the\s+head\s+)?repeatedly\b",
    r"\bhave\s+(?:a|the)\s+blade\s+in\s+my\s+hand\b",
    r"\bburn(?:ed|ing)?\s+(?:my\s+)?(?:arm|skin|legs?|hand|myself)\b",
    r"\bput\s+the\s+lighter\s+down\b",
    r"\bsqueez(?:ing|ed)\s+(?:my\s+)?(?:arm|hand|skin)\s+until\s+it\s+bruises\b",
    r"\bpunch(?:ed|ing)?\s+myself\b",
    r"\bhitting\s+(?:my\s+)?(?:legs?|head|body|face)\b",
    r"\busing\s+a\s+razor\s+on\s+my\s+skin\b",
    r"\b(?:making|make)\s+myself\s+bleed\b",
    r"\bbreaking\s+(?:my\s+)?skin\s+until\s+it\s+bleeds\b",
    r"\bfresh\s+cuts\s+on\s+my\b",
    r"\bmaking\s+the\s+injuries\s+worse\b",
]

# 7. ACTIVE ESCALATION IN PROGRESS -------------------------------------------
_ACTIVE_ESCALATION_IN_PROGRESS = [
    r"\bholding\s+the\s+blade\b",
    r"\bhave\s+the\s+rope\s+(?:ready|in\s+my\s+hands)\b",
    r"\bstanding\s+on\s+the\s+(?:edge|ledge|roof|bridge)\b",
    r"\bstaring\s+at\s+the\s+bridge\b",
    r"\bswallowed\s+the\s+pills\b",
    r"\balready\s+took\s+everything\b",
    r"\balready\s+made\s+the\s+first\s+cut\b",
    r"\balready\s+texted\s+my\s+goodbyes\b",
    r"\balready\s+wrote\s+(?:my\s+)?note\b",
    r"\bi'?m\s+not\s+stopping\b",
    r"\bready\s+to\s+end\s+it\s+now\b",
    r"\balready\s+have\s+a\s+plan\s+for\s+tonight\b",
    r"\bdon'?t\s+think\s+i'?m\s+going\s+to\s+make\s+it\s+through\s+the\s+night\b",
    r"\bdon'?t\s+think\s+i\s+can\s+stop\s+myself\s+this\s+time\b",
    r"\bdon'?t\s+want\s+to\s+put\s+it\s+down\b",
    r"\babout\s+to\s+do\s+something\s+i\s+can'?t\s+take\s+back\b",
    r"\bi\s+don'?t\s+know\s+why\s+i'?m\s+still\s+waiting\b",
    r"\bhave\s+the\s+pills\s+in\s+front\s+of\s+me\s+right\s+now\b",
]

CRISIS_PATTERN_CATEGORIES: List[PatternCategory] = [
    PatternCategory("explicit_suicidal_intent", 5, [_c(p) for p in _EXPLICIT_SUICIDAL_INTENT]),
    PatternCategory("indirect_implicit_distress", 3, [_c(p) for p in _INDIRECT_IMPLICIT_DISTRESS]),
    PatternCategory("burden_and_goodbye", 4, [_c(p) for p in _BURDEN_AND_GOODBYE]),
    PatternCategory("lethal_means_and_preparation", 5, [_c(p) for p in _LETHAL_MEANS_AND_PREPARATION]),
    PatternCategory("subtle_slang_and_informal", 4, [_c(p) for p in _SUBTLE_SLANG_AND_INFORMAL]),
    PatternCategory("self_harm_and_cutting", 4, [_c(p) for p in _SELF_HARM_AND_CUTTING]),
    PatternCategory("active_escalation_in_progress", 5, [_c(p) for p in _ACTIVE_ESCALATION_IN_PROGRESS]),
]

CRISIS_PATTERNS: List[re.Pattern] = [
    pat for cat in CRISIS_PATTERN_CATEGORIES for pat in cat.patterns
]


# ---------------------------------------------------------------------------
# SECTION 2 -- EXCLUSION / BYPASS PATTERNS
# ---------------------------------------------------------------------------

_NEGATION_PATTERNS = [
    # Living-arrangement statements are not statements of a wish to die.
    # Keep this narrowly tied to an explicit household relationship so that
    # "I don't want to live anymore" remains a crisis signal.
    r"\b(?:i\s+)?don'?t\s+want\s+to\s+live\s+(?:(?:more|anymore)\s+)?(?:with|at)\s+(?:my\s+)?(?:family|parents?|mother|father|mom|mum|dad|relatives?)\b",
    # Explicit coping / survival requests (e.g. "can u help me not die")
    r"\b(?:help|save|stop|prevent|keep|want|trying)\s+(?:me\s+)?(?:to\s+)?not\s+(?:die|harm\s+myself|hurt\s+myself|kill\s+myself|suicide)\b",
    r"\b(?:how\s+to|advice\s+on\s+how\s+to|help\s+me|help\s+to|want\s+to|trying\s+to|ways\s+to)\s+stop\s+(?:hurting|harming|cutting)\s+myself\b",
    r"\bhelp\s+me\s+(?:not\s+die|to\s+not\s+die|stay\s+alive|survive|live)\b",
    r"\bnot\s+die\b",
    r"\bso\s+i\s+don'?t\s+die\b",
    r"\bdon'?t\s+want\s+to\s+die\b",
    r"\bi(?:'m| am)\s+(?:definitely\s+)?not\s+suicidal\b",
    r"\bnot\s+(?:feeling\s+)?suicidal\b",
    r"\bnever\s+want(?:ed)?\s+to\s+die\b",
    r"\bno\s+longer\s+(?:having|feeling|experiencing)?\s*suicidal(?:\s+thoughts?)?\b",
    r"\bno\s+longer\s+suicidal\b",
    r"\bhaven'?t\s+(?:felt\s+suicidal|cut\s+myself)\b",
    r"\bhasn'?t\s+(?:harmed|hurt)\s+(?:myself|himself|herself|themselves)\b",
    r"\b(?:definitely\s+)?not\s+going\s+to\s+(?:kill|hurt|harm)\s+myself\b",
    r"\bdon'?t\s+want\s+to\s+(?:die|suicide|commit\s+suicide|kill\s+myself|end\s+my\s+life|hurt\s+myself|harm\s+myself|self[\s-]?harm|do\s+anything\s+drastic)\b",
    r"\b(?:don'?t|do\s+not)\s+(?:want|wish|plan)\s+to\s+(?:suicide|commit\s+suicide|die|kill\s+myself|end\s+my\s+life)\b",
    r"\bi\s+don'?t\s+want\s+to\s+suicide\b",
    r"\bnot\s+(?:wanting\s+to|going\s+to)\s+(?:suicide|commit\s+suicide)\b",
    r"\bdon'?t\s+have\s+any\s+thoughts\s+of\s+(?:harming|hurting)\b",
    r"\bno\s+suicidal\s+thoughts\b",
    r"\b(?:definitely\s+)?not\s+thinking\s+(?:about|of)\s+(?:suicide|self[\s-]?harm(?:ing)?|hurting\s+myself|harming\s+myself|killing\s+myself|ending\s+my\s+life|ending\s+things|taking\s+my\s+own\s+life|doing\s+anything\s+to\s+myself)\b",
    r"\bdefinitely\s+not\s+(?:suicidal|thinking\s+of\s+hurting\s+myself|hurting\s+myself)\b",
    r"\bnot\s+a\s+danger\s+to\s+myself\b",
    r"\bdenies?\s+suicidal\s+ideation\b",
    r"\bwithout\s+(?:any\s+)?suicidal\s+intent\b",
    r"\bnot\s+planning\s+(?:to\s+die|on\s+self[\s-]?harm(?:ing)?)\b",
    r"\bwasn'?t\s+planning\s+(?:on|to)\s+(?:self[\s-]?harm(?:ing)?|hurt(?:ing)?\s+myself|harm(?:ing)?\s+myself|end(?:ing)?\s+my\s+life|kill(?:ing)?\s+myself|dying)\b",
    r"\bnah\s+i'?m\s+not\s+(?:thinking\s+of|feeling)\s+(?:self[\s-]?harm(?:ing)?|suicidal|ending\s+things|hurting\s+myself|doing\s+anything|taking\s+my\s+own\s+life)\b",
    r"\bnot\s+that\s+i'?d\s+ever\s+(?:end\s+my\s+life|harm\s+myself|kill\s+myself|hurt\s+myself|be\s+suicidal|self[\s-]?harm(?:ing)?|do\s+anything\s+to\s+myself)\b",
    r"\bno\s+i\s+don'?t\s+want\s+to\s+(?:end\s+my\s+life|harm\s+myself|kill\s+myself|die|do\s+anything\s+to\s+myself|suicide)\b",
    r"\bnever\s+once\s+thought\s+about\s+(?:hurting\s+myself|self[\s-]?harm(?:ing)?|killing\s+myself|suicide|taking\s+my\s+own\s+life)\b",
    r"\bwasn'?t\s+going\s+to\s+(?:do\s+anything|hurt\s+myself|harm\s+myself)\b",
    r"\bno,\s+i\s+don'?t\s+want\s+to\s+hurt\s+myself\b",
    r"\bnot\s+(?:my\s+life|myself|suicidal|dying|suicide|self[\s-]?harm)\b",
    r"\bnot\s+ending\s+my\s+life\b",
    r"\bnot\s+killing\s+myself\b",
    r"\b(?:have\s+)?(?:zero|no)\s+(?:intention|desire|plan|plans|thoughts?)\s+of\s+(?:hurting|harming|killing|suicid\w*|ending\s+my\s+life|doing\s+anything\s+drastic)\b",
    r"\b(?:zero|no)\s+(?:intention|desire|plan|plans)\s+to\s+(?:hurt|harm|kill|end)\s+(?:myself|my\s+life)\b",
    r"\b(?:do\s+not|don'?t|have\s+no|have\s+not|zero|no|without\s+any)\s+(?:intention|desire|plan|plans|thoughts?)\s+(?:to|of)\s+(?:end\s+my\s+life|die|kill\s+myself|harm\s+myself|hurt\s+myself|commit\s+suicide)\b",
    r"\bdoes\s+not\s+mean\s+i\s+(?:want\s+to|am\s+going\s+to)\s+(?:die|kill\s+myself|end\s+my\s+life)\b",
    r"\bnot\s+because\s+i\s+(?:do\s+it|am|want\s+to|have)\b",
    r"\bnot\s+thinking\s+about\s+doing\s+it\b",
    r"\b(?:definitely\s+)?not\s+want\s+to\s+die\b",
    r"\bnot\s+thinking\s+about\s+suicide\b",
    r"\b(?:not|never|no|wasn'?t|isn'?t|don'?t|won'?t|ain'?t|didn'?t|couldn'?t|wouldn'?t|shouldn'?t)\b(?:\s+(?!but\b|however\b|though\b|except\b|yet\b|stop\b|know\b)\w+){0,6}\s+\b(?:self[\s-]?harm(?:ing)?|hurt(?:ing)?\s+myself|harm(?:ing)?\s+myself|kill(?:ing)?\s+myself|end(?:ing)?\s+(?:my\s+life|it\s+all|it|things)|suicid\w*|take\s+my\s+(?:own\s+)?life|do\s+anything\s+to\s+myself|die|want\s+to\s+die)\b",
]

_PAST_HISTORICAL_REFLECTION_PATTERNS = [
    r"\bused\s+to\s+feel\s+suicidal\b",
    r"\bused\s+to\s+be\s+suicidal\b",
    r"\bused\s+to\s+think\s+about\s+ending\s+things\b",
    r"\bused\s+to\s+(?:cut|harm|hurt|self[\s-]?harm)\s+(?:myself\s+)?every\s+week\b",
    r"\bused\s+to\s+self[\s-]?harm\b",
    r"\bused\s+to\s+(?:cut|harm|hurt|self[\s-]?harm)\s+myself\b",
    r"\bused\s+to\s+relapse\s+constantly\b",
    r"\bwas\s+suicidal\s+once\b",
    r"\bhad\s+thoughts\s+of\s+dying\s+back\s+in\b",
    r"\bwas\s+feeling\s+suicidal\s+(?:last\s+(?:month|year)|before|back\s+then|long\s+ago)\b",
    r"\bhad\s+suicidal\s+thoughts\s+(?:in\s+the\s+past|back\s+in|years?\s+ago|last\s+year)\b",
    r"\bstruggled\s+(?:a\s+lot\s+)?with\s+(?:suicidal\s+thoughts|self[\s-]?harm\s+urges|depression)\s+(?:in\s+the\s+past|years?\s+ago|in\s+high\s+school|in\s+college|in\s+middle\s+school|as\s+a\s+kid|as\s+a\s+young\s+adult)\b",
    r"\brecovery\s+from\s+my\s+PTSD\b",
    r"\bsurvived\s+(?:a\s+)?(?:really\s+)?(?:bad\s+)?bout\s+of\b",
    r"\bback\s+in\s+\d{4}\s+i\s+attempted\b",
    r"\bclean\s+for\s+\d+\s+(?:years?|months?)\b",
    r"\bbeen\s+stable\s+for\s+(?:almost\s+)?(?:\d+|a|one|two|three|four|five)\s+(?:years?|months?)\b",
    r"\bhaven'?t\s+had\s+those\s+thoughts\s+in\s+\d+\s+(?:years?|months?)\b",
    r"\b(?:\d+|a|one|two|three|four|five|six|seven|eight|nine|ten)\s+(?:years?|months?|decades?)\s+(?:ago|since)\b",
    r"\bit'?s\s+been\s+(?:a\s+)?(?:decade|year|years|months?)\s+since\b",
    r"\bwas\s+hospitalized\s+for\b.{0,40}\bback\s+in\s+(?:19|20)\d{2}\b",
    r"\bseveral\s+years\s+ago\s+i\s+was\s+in\s+a\s+really\s+dark\s+place\b",
    # --- Recovery milestone patterns ---
    r"\b\d+\s+years?\s+clean\s+from\s+self[\s-]?harm\b",
    r"\bself[\s-]?harm\s+free\s+for\s+(?:over\s+)?\d+\b",
    r"\bhaven'?t\s+had\s+a\s+suicidal\s+thought\s+in\s+(?:years|months|a\s+long\s+time)\b",
    r"\bleft\s+(?:my\s+)?suicidal\s+past\s+behind\b",
    r"\bdoing\s+(?:so\s+)?much\s+better\s+than\s+when\s+i\s+used\s+to\b",
    r"\b(?:remember|recall)\s+(?:feeling|being|having)\s+(?:suicidal|depression|self[\s-]?harm)\b",
    r"\b(?:not|never)\s+crossed\s+my\s+mind\s+in\s+(?:years|months|a\s+long\s+time)\b",
    r"\bused\s+to\s+say\s+['\"]?kms['\"]?\s+(?:online\s+)?as\s+a\s+joke\b",
]

_CONTINUATION_OVERRIDE_MARKERS = [
    r"\bstill\s+(?:feel|feeling|have|having|want)\b",
    r"\beven\s+now\b",
    r"\bto\s+this\s+day\b",
    r"\band\s+(?:i\s+)?still\b",
    r"\bback\s+there\s+again\b",
    # Relapse markers: past recovery followed by current relapse
    r"\brelaps(?:e|ed|ing)\b",
    r"\bholding\s+a\s+(?:razor|blade|knife)\s+right\s+now\b",
    r"\bbought\s+a\s+rope\s+today\b",
    r"\btonight\b",
    r"\blast\s+night\b",
    r"\bright\s+now\b",
]

_RESOLUTION_MARKERS = [
    r"\bbut\s+i'?m\s+doing\s+(?:great|better|fine|well|okay|good)\s+now\b",
    r"\bi'?m\s+in\s+a\s+(?:good|better|different)\s+place\s+now\b",
    r"\bthat'?s\s+(?:all\s+)?behind\s+me\s+now\b",
    r"\bi'?m\s+(?:doing\s+)?(?:much\s+)?better\s+now\b",
    r"\bi'?m\s+honestly\s+happy\s+now\b",
    r"\bi'?m\s+thriving\s+now\b",
    r"\bproud\s+of\s+how\s+far\s+i'?ve\s+come\b",
    r"\bbeen\s+stable\s+for\s+.*\s+now\b",
    r"\bancient\s+history\s+now\b",
    r"\bi'?m\s+doing\s+well\b",
    r"\bturned\s+things\s+around\s+for\s+me\b",
    r"\bhelped\s+me\s+pull\s+through\b",
]

_ACADEMIC_CONTEXT_PATTERNS = [
    r"\bwriting\s+a\s+(?:thesis|research\s+paper|psychology\s+paper|paper|essay)\s+(?:on|about)\s+(?:suicide|depression|self[\s-]?harm)\b",
    r"\bstudying\s+(?:for\s+a\s+)?(?:nursing|psychology|sociology|medical)?\s*(?:exam|test|class)\b",
    r"\bcrisis\s+intervention\b",
    r"\b(?:nursing|psychology)\s+exam\s+on\s+suicide\b",
    r"\breading\s+a\s+research\s+paper\s+on\s+self[\s-]?harm\b",
    r"\bfor\s+my\s+(?:essay|assignment|homework|dissertation|paper|thesis)\s+on\s+suicide\b",
    r"\b(?:psychology|sociology|nursing|medical)\s+(?:class|course|exam|assignment|lecture|training|session)\s+(?:about|on|covering|involving)\s+(?:suicide|self[\s-]?harm|depression|crisis)\b",
    r"\bsuicide\s+(?:statistics|prevention\s+training|risk\s+assessment\s+training|prevention)\b",
    r"\bcase\s+stud(?:y|ies)\s+(?:on|about|involving)\s+(?:suicide|self[\s-]?harm)\b",
    r"\breading\s+an?\s+(?:article|paper|essay|study|report)\s+about\b",
    r"\b(?:read|reading)\s+(?:a\s+)?news\s+(?:article|report|story)\b",
    r"\bdata\s+shows\b",
    r"\bsupport\s+group\s+discussed\b",
    r"\bwarning\s+signs\s+of\s+self[\s-]?harm\b",
    r"\bself[\s-]?harm\s+history\b",
    r"\b(?:nlp|dataset|corpus|annotation|guidelines|study|synthetic\s+examples?|quoting\s+a\s+message|research\s+report)\b",
    r"\b(?:the\s+words?|the\s+phrase|examples?\s+such\s+as)\s+['\"].*?['\"]\b",
    r"\bappears\s+in\s+the\s+dataset\b",
]

_MEDIA_CONTEXT_PATTERNS = [
    r"\bwatching\s+13\s+reasons\s+why\b",
    r"\breading\s+a\s+book\s+about\s+suicide\b",
    r"\b(?:movie|show|film|book|novel|tv\s+show|documentary|anime|manga)\s+(?:character|segment)?\s*(?:dies|died|kills\s+(?:himself|herself|themselves)|talks\s+about|battles|struggles|has|features|writes|discussed)\b",
    r"\b(?:character|protagonist)\s+in\s+that\s+(?:anime|show|movie|book|novel)\b",
    r"\b(?:book|novel|movie|show|film|anime|manga).{0,80}\bcharacter\b",
    r"\b(?:watched|watching)\s+(?:a\s+)?(?:documentary|movie|show|tv\s+show|film|anime)\b",
    r"\blistening\s+to\s+a\s+podcast\s+about\s+mental\s+health\b",
    r"\bmy\s+[\w'\s]{1,40}\s+(?:passed\s+away|died|attempted|committed|told\s+me|mentioned)\b",
    r"\bsaw\s+a\s+news\s+report\b",
    r"\bdocumentary\s+discussed\b",
    r"\b(?:in\s+the|in\s+a)\s+(?:horror\s+)?(?:game|video\s+game|rpg|story|novel|film|movie|show)\b",
    r"\bthe\s+character\s+(?:whispers|says|screams|thinks|cries|states)\b",
]

_IDIOMATIC_METAPHOR_AND_HYPERBOLE_PATTERNS = [
    r"\bdi(?:e|ed|es|ying)\s+of\s+embarrassment\b",
    r"\bcould\s+just\s+die\s+of\s+embarrassment\b",
    r"\b(?:want|wanted)\s+to\s+die\s+of\s+embarrassment\b",
    r"\bdi(?:e|ed|es|ying)\s+of\s+laughter\b",
    r"\bdi(?:e|ed|es|ying)\s+of\s+boredom\b",
    r"\bkill(?:ing)?\s+time\b",
    r"\b\w+\s+is\s+killing\s+me\b",
    r"\bmy\s+(?:feet|back|legs|head|arms)\s+(?:are|is)\s+killing\s+me\b",
    r"\bkill(?:ing)?\s+it\s+(?:at|in|on)\b",
    r"\bshoot(?:ing)?\s+myself\s+in\s+the\s+foot\b",
    r"\bover ?dos(?:e|ing)\s+on\s+(?:caffeine|coffee|netflix|homework|work|sugar|tv)\b",
    r"\bdying\s+to\s+(?:see|know|try|go)\b",
    r"\bdeath\s+of\s+me\b",
    r"\bkill\s+for\s+a\b",
    r"\bdead\s+on\s+my\s+feet\b",
    r"\bworld\s+(?:is\s+)?(?:gonna\s+|going\s+to\s+)?collapse\b",
    r"\bcollapse\s+on\s+my\s+head\b",
    r"\bweight\s+of\s+the\s+world\b",
    r"\bfalling\s+apart\b",
    r"\b(?:meeting|meetings|homework|test|tests|traffic|game|games|presentation|presentations|exam|exams|finals|math|chores|movie|show|bored)\b.*\b(?:want\s+to\s+die|wanna\s+die|kill\s+myself|makes\s+me\s+want\s+to\s+die|makes\s+me\s+wanna\s+die)\b",
    r"\bif\s+i\s+have\s+to\s+.*\b(?:kill\s+myself|want\s+to\s+die|wanna\s+die)\b",
    # --- Expanded death idioms ---
    r"\bdead\s+tired\b",
    r"\bdead\s+to\s+the\s+world\b",
    r"\bscared\s+to\s+death\b",
    r"\b(?:my\s+)?(?:boss|mom|dad|teacher|coach|professor|manager)\s+(?:is\s+going\s+to|will|gonna)\s+kill\s+me\b",
    r"\bworking\s+(?:myself\s+)?to\s+death\b",
    r"\bbored\s+to\s+death\b",
    r"\bi\s+want\s+to\s+die\s+old\s+and\s+(?:peaceful|happy|content)\b",
    r"\bwant\s+to\s+live\s+a\s+long\s+life\b",
    r"\bnot\s+going\s+to\s+die\s+today\b",
    r"\bi\s+am\s+not\s+going\s+to\s+die\b",
    r"\bso\s+hungry\s+i\s+could\s+die\b",
]

# Slang hyperbole dampeners: kms/kys/unalive used in trivial/humorous context
_SLANG_HYPERBOLE_DAMPENER_PATTERNS = [
    r"\b(?:kms|kys|kill\s+myself|kill\s+yourself)\b.*\b(?:brb|lol|lmao|rofl|haha|laughing|joke|joking|kidding|jk)\b",
    r"\b(?:brb|lol|lmao|rofl|haha|laughing|joke|joking|kidding|jk)\b.*\b(?:kms|kys|kill\s+myself|kill\s+yourself)\b",
    r"\b(?:unalive|kill\s+myself|kill)\s+(?:this\s+|my\s+)?(?:alarm\s+clock|pizza|burger|food|chicken|sandwich|steak|game|laptop|phone|computer|car|printer)\b",
    r"\bsaid\s+(?:kms|kys)\s+as\s+a\s+joke\b",
    r"\bfinna\s+tap\s+out\s+for\s+the\s+night\b",
    r"\b(?:kms|kys|kill\s+myself)\b.*\b(?:this\s+(?:game|test|exam|homework|class|traffic)|if\s+i\s+don'?t\s+get)\b",
    r"\b(?:this\s+(?:game|test|exam|homework|class|traffic)|if\s+i\s+don'?t\s+get)\b.*\b(?:kms|kys|kill\s+myself)\b",
    r"\b(?:is\s+)?just\s+a\s+(?:meme|joke)\b",
    r"\bi\s+am\s+actually\s+(?:fine|okay|ok|good)\b",
    r"\b(?:kys|kill\s+yourself)\s*,\s*(?:printer|computer|laptop|code|bug|wifi|phone|server|screen)\b",
    r"\breset\s+the\s+sim\s+after\s+this\s+boss\s+fight\b",
    r"\bmean\s+restart\s+the\s+game\b",
]

# Third-party subject indicators: statements about someone else's crisis
_THIRD_PARTY_SUBJECT_PATTERNS = [
    r"^\s*(?:my\s+)?(?:friend|brother|sister|mom|dad|mother|father|uncle|aunt|partner|colleague|teammate|roommate|classmate|neighbor|best\s+friend|bf|gf|girlfriend|boyfriend|husband|wife|son|daughter|cousin|nephew|niece)",
    r"^\s*someone\s+(?:on\s+this\s+|in\s+the\s+|at\s+|i\s+know\s+)?",
    r"\b(?:my\s+)?(?:friend|brother|sister|mom|dad|mother|father|partner|uncle|aunt|teammate|roommate|cousin|best\s+friend|colleague|classmate)\s+(?:is|was|has|just|told|texted|said|sent|has\s+been|might\s+be|wants?\s+to|plans?\s+to)\s+",
    r"\b(?:he|she|they)\s+(?:is|are|was|were|has|have)\s+(?:going\s+to|gonna|about\s+to|planning\s+to|trying\s+to)\s+(?:kill|hurt|harm|end|commit|jump|cut|overdose|suicide|die)\b",
    r"\b(?:he|she|they)\s+(?:wants?\s+to|plans?\s+to|is\s+thinking\s+(?:of|about))\s+(?:kill|hurt|harm|end|commit|jump|cut|overdose|suicide|die)\b",
    r"\b(?:my\s+)?(?:friend|brother|sister|mom|dad|roommate|cousin|partner)\s+is\s+(?:feeling\s+)?(?:suicidal|self[ -]?harming)\b",
    r"\b(?:worried|scared|concerned)\s+(?:about|for)\s+(?:my\s+)?(?:friend|brother|sister|roommate|someone)\b",
    r"\bhow\s+to\s+help\s+(?:a|my)\s+(?:friend|brother|sister|someone)\b",
]

# Accidental/benign context indicators
_ACCIDENTAL_CONTEXT_PATTERNS = [
    r"\bby\s+accident\b",
    r"\baccidentally\b",
    r"\bshould\s+i\s+go\s+to\s+the\s+(?:hospital|er|doctor|emergency)\b",
    r"\bstanding\s+on\s+the\s+edge\s+of\s+the\s+stage\b",
    r"\bforgot\s+if\s+i\s+took\s+my\b",
    r"\bready\s+to\s+perform\b",
    r"\b(?:rope\s+for|bought\s+(?:a\s+)?rope\s+for)\s+(?:the\s+)?(?:tire\s+swing|swing|tree|gym|climbing|boat|tent|camping|hammock)\b",
    r"\b(?:so\s+i\s+don'?t\s+run\s+out|in\s+case\s+of\s+(?:shortage|emergency)|in\s+case\s+they\s+run\s+out)\b",
    r"\b(?:suicidal|dying)\s+for\s+(?:pizza|burger|food|coffee|tacos|ice\s+cream|chocolate|sushi|boba)\b",
    r"\bafter\s+(?:the\s+)?funeral\b",
]

# Protective contrast patterns: crisis keyword + protective second clause
_PROTECTIVE_CONTRAST_PATTERNS = [
    r"(?:want\s+to\s+die|kill\s+myself|killing\s+myself|end\s+my\s+life).*\bbut\b.*(?:because\s+of\s+my|won'?t\s+because|decided\s+to\s+go\s+to\s+therapy|my\s+dog|my\s+kids|my\s+family|my\s+cat|called\s+the\s+hotline|chose\s+to|going\s+to\s+therapy)",
    r"(?:thought\s+about\s+killing\s+myself|thought\s+about\s+suicide|considered\s+suicide).*\bbut\b.*(?:decided\s+to|chose\s+to|went\s+to\s+therapy|called\s+the\s+hotline|talked\s+to|got\s+help)",
]

# Negation override: lethal actions that override a preceding negation disclaimer
_NEGATION_OVERRIDE_LETHAL_ACTIONS = [
    r"(?:took|swallowed|drank|have)\s+(?:the\s+|all\s+(?:the\s+)?)?(?:pills|bleach|poison|rope|knife|gun|blade)",
    r"(?:going\s+to|gonna|plan\s+to|about\s+to)\s+(?:jump|end\s+it|die|kill|crash|disappear\s+permanently|swallow|drink|do\s+it)",
    r"have\s+a\s+suicide\s+plan",
    r"want\s+to\s+(?:be\s+dead|sleep\s+forever|disappear\s+permanently|die\s+tonight|die)",
    r"planning\s+my\s+death",
    r"holding\s+(?:a\s+|the\s+)?(?:knife|blade|rope|gun|razor)",
    r"(?:the\s+)?(?:knife|blade|rope|gun|razor|pills?)\s+(?:is|are)\s+right\s+here",
    r"drive\s+into\s+(?:a\s+)?(?:wall|tree|median)",
    r"do\s+it\s+without\s+thinking",
    r"(?:except|for)\s+(?:the\s+)?(?:rope|knife|gun|blade|pills?)",
    r"burn(?:ed|ing)?\s+myself",
    r"put\s+the\s+lighter\s+down",
    r"not\s+put\s+(?:the\s+lighter|it)\s+down",
]

_SUPPORT_REQUEST_AND_VENTING_PATTERNS = [
    r"\b(?:i\s+)?(?:just\s+)?need\s+(?:help|support|advice|someone\s+to\s+talk\s+to)\s+(?:calming\s+down|staying\s+calm|sleeping|resting|breathing|grounding|focusing|getting\s+through\s+this)\b",
    r"\b(?:help|support|advice)\s+(?:me\s+)?(?:calm\s+down|stay\s+calm|sleep|rest|breathe|ground|focus|get\s+through\s+this)\b",
    r"\b(?:i'?m|i\s+am|i\s+feel)\s+(?:so\s+|really\s+)?(?:frustrated|angry|annoyed|overwhelmed|stressed|exhausted|hopeless|terrible|down|sad|miserable)\b",
    r"\bthis\s+day\s+was\s+terrible\b",
    r"\b(?:i'?m|i\s+am)\s+so\s+overwhelmed\s+i\s+don't\s+know\s+what\s+to\s+do\b",
    r"\b(?:i'?m|i\s+am)\s+(?:really\s+)?tired\s+and\s+need\s+help\s+sleeping\b",
    r"\b(?:help\s+me\s+)?sleep\b",
    r"\b(?:need\s+help|want\s+help)\s+(?:getting\s+through\s+this|calming\s+down|staying\s+calm|sleeping|resting|grounding)\b",
]

_NON_CRISIS_SITUATIONAL_EXPRESSIONS = [
    r"\blost\s+my\s+job\b",
    r"\b(?:i(?:'m| am)\s+|feel(?:ing)?\s+)?(?:completely\s+|really\s+|so\s+|very\s+|a\s+bit\s+|just\s+)?(?:broken|sad|lonely|down|upset|depressed|alone|overwhelmed|hopeless|numb|empty|anxious|stressed|exhausted|terrible|bad|miserable|frustrated|annoyed|angry|irritated|mad|furious|pissed|confused|stuck|lost|hurt|struggling)\b",
    r"\b(?:im|i'?m|i\s+am)\s+(?:really\s+)?(?:and\s+)?(?:frustrated|annoyed|angry|mad|stressed|overwhelmed|confused|upset|hurting)\b",
    r"\b(?:help|support|advice|listen\s+to|talk\s+to)\s+me\b",
    r"\b(?:i\s+need|need|want)\s+(?:help|support|advice|to\s+talk|someone\s+to\s+talk\s+to|guidance)\b",
    r"\bso\s+(?:frustrated|annoyed|mad|irritated|stressed|overwhelmed)\b",
    r"\bfed\s+up\s+(?:with|of)?\b",
    r"\b(?:breathing|grounding|calming|relaxation)\s+(?:exercise|technique|practice|session)\b",
    r"\b(?:guide|walk|help)\s+(?:me\s+)?(?:through|with)\s+(?:a\s+)?(?:breathing|grounding|calming|relaxation|mindfulness|meditation)\b",
    r"\bmeditat(?:e|ion|ing)\b",
    r"\b(?:having\s+)?trouble\s+(?:sleeping|to\s+sleep)\b",
    r"\b(?:can'?t|cannot)\s+sleep\b",
    r"\bfeel(?:ing)?\s+(?:so\s+|really\s+)?exhausted\b",
    r"\banxiety\s+has\s+been\s+through\s+the\s+roof\b",
    r"\bjob\s+search\b",
    r"\bcustody\s+hearing\b",
    r"\bmiscarriage\b",
    r"\bbroke\s+down\s+in\s+the\s+bathroom\b",
    r"\bfeel\s+like\s+such\s+a\s+failure\b",
    r"\bhard\s+(?:semester|couple\s+weeks|few\s+days|day|week|time)\b",
    r"\bpanic\s+attack\b",
    r"\bbreakup\b",
    r"\b(?:thesis|finals|exams?|presentation|homework)\b",
    r"\b(?:grandpa|grandma|family\s+drama|relationship)\b",
    r"\bkill\s+for\s+a\s+(?:vacation|burger|break|coffee|sleep|pizza)\b",
    r"\b(?:hike|gym)\b",
    r"\beverything\s+feels\s+so\s+heavy\b",
    r"\b(?:no\s+)?i?\s*don'?t\s+want\s+(?:to\s+)?(?:exercise|do\s+exercise|workout|walk|meditate|talk|do\s+this|do\s+that|try\s+this|try\s+that|anything)\b",
    r"\b(?:have\s+to\s+go|gotta\s+go|heading\s+out|talk\s+to\s+you\s+later|see\s+you\s+later|bye\s+bye|bye|cya)\b",
]
NON_CRISIS_SITUATIONAL_EXPRESSIONS = [_c(p) for p in _NON_CRISIS_SITUATIONAL_EXPRESSIONS]
SUPPORT_REQUEST_AND_VENTING_PATTERNS = [_c(p) for p in _SUPPORT_REQUEST_AND_VENTING_PATTERNS]

_FIRST_PERSON_PRESENT_CRISIS_OVERRIDE_RAW = [
    r"\b(?:i\s+)?feel\s+like\s+disappearing\s+forever\b",
    r"\bi\s+(?:do\s+not|don'?t)\s+see\s+a\s+future\s+for\s+myself\b",
    r"\bi'?ve\s+made\s+up\s+my\s+mind.*\bdon'?t\s+want\s+to\s+keep\s+living\b",
    r"\bthe\s+only\s+way\s+out\s+feels\s+like\s+ending\s+my\s+life\b",
    r"\bi'?m\s+done\s+fighting.*\bgive\s+up\s+on\s+everything\s+including\s+myself\b",
    r"\bi(?:\s+have|'ve)\s+been\s+planning\s+how\s+to\s+end\s+things\b",
    r"\bi\s+(?:do\s+not|don'?t)\s+think\s+i\s+can\s+survive\s+another\s+day\b",
    r"\b(?:i'?m\s+)?ready\s+to\s+give\s+up\s+on\s+life\b",
    r"\bholding\s+the\s+blade\b",
    r"\bhave\s+the\s+pills\s+(?:ready\s+)?(?:in\s+front\s+of\s+me|ready|here)\b",
    r"\bwant\s+(?:everything|it|it\s+all)\s+to\s+stop\b",
    r"\b(?:ending|end)\s+the\s+sim\b",
    r"\btap\s+out\s+(?:for\s+good|permanently)?\b",
    r"\bhave\s+everything\s+(?:i\s+need\s+)?ready\s+to\s+go\b",
    r"\b(?:hurting|harming)\s+myself\b",
    r"\bswallowed\s+the\s+pills\b",
    r"\balready\s+took\s+everything\b",
    r"\balready\s+have\s+the\s+rope\b",
    r"\b(?:have\s+)?(?:already\s+)?made\s+a\s+plan\b",
    r"\bhave\s+a\s+plan\b",
    r"\balready\s+texted\s+my\s+goodbyes\b",
    r"\balready\s+wrote\s+(?:my\s+)?note\b",
    r"\b(?:wrote|written|leaving|hid|hide)\s+a\s+(?:goodbye\s+|suicide\s+)?note\b",
    r"\bgoodbye\s+note\b",
    # Idiom escalation: phrases that confirm genuine intent after an idiomatic first clause
    r"\bmake\s+it\s+(?:permanent|reality|real)\b",
    r"\b(?:i'?ll|i\s+will|i'?m\s+going\s+to)\s+do\s+it\s+(?:first|myself|tonight|now)\b",
    r"\bmight\s+as\s+well\s+(?:finish|end)\s+it\b",
    r"\bplan\s+to\s+end\s+it\s+all\b",
    r"\bgoing\s+to\s+(?:actually\s+)?die\b",
    r"\bdie\s+anyway\b",
    r"\bfinish\s+(?:it|the\s+job|myself)\b",
    r"\bgoing\s+to\s+(?:kill\s+myself|end\s+my\s+life|end\s+it)\b",
    r"\bswallow\s+(?:the\s+)?bleach\b",
    r"\bholding\s+(?:a|the)\s+razor\b",
]
_FIRST_PERSON_PRESENT_CRISIS_OVERRIDE: List[re.Pattern] = (
    CRISIS_EXPLICIT_PATTERNS +
    [_c(p) for p in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE_RAW] +
    [_c(p) for p in _INDIRECT_IMPLICIT_DISTRESS] +
    [_c(p) for p in _BURDEN_AND_GOODBYE] +
    [_c(p) for p in _LETHAL_MEANS_AND_PREPARATION] +
    [_c(p) for p in _SUBTLE_SLANG_AND_INFORMAL] +
    [_c(p) for p in _SELF_HARM_AND_CUTTING] +
    [_c(p) for p in _ACTIVE_ESCALATION_IN_PROGRESS]
)

NEGATION_PATTERNS = [_c(p) for p in _NEGATION_PATTERNS]
PAST_HISTORICAL_REFLECTION_PATTERNS = [_c(p) for p in _PAST_HISTORICAL_REFLECTION_PATTERNS]
CONTINUATION_OVERRIDE_MARKERS = [_c(p) for p in _CONTINUATION_OVERRIDE_MARKERS]
RESOLUTION_MARKERS = [_c(p) for p in _RESOLUTION_MARKERS]
ACADEMIC_CONTEXT_PATTERNS = [_c(p) for p in _ACADEMIC_CONTEXT_PATTERNS]
MEDIA_CONTEXT_PATTERNS = [_c(p) for p in _MEDIA_CONTEXT_PATTERNS]
IDIOMATIC_METAPHOR_AND_HYPERBOLE_PATTERNS = [_c(p) for p in _IDIOMATIC_METAPHOR_AND_HYPERBOLE_PATTERNS]


# ---------------------------------------------------------------------------
# Context / negation evaluation
# ---------------------------------------------------------------------------

def _contextual_bypass_reason(text: str) -> Optional[str]:
    t = _normalize(text)
    if not t:
        return None

    # (1) Contrast clause handling:
    # A negated thought or idiom combined with a crisis clause is not a safe bypass.
    # Example: "I don't want to die, but I am going to kill myself tonight."
    # Example: "I want to die, but this exam is killing me."
    contrast_parts = [p.strip() for p in re.split(r"\b(?:but|however|though|yet)\b", t) if p.strip()][:4]
    so_parts = [p.strip() for p in re.split(r",?\s+(?:so|and)\s+", t) if p.strip()][:4]
    allow_idiom_bypass = True
    if len(contrast_parts) >= 2:
        for idx, part in enumerate(contrast_parts):
            part_negated = any(pat.search(part) for pat in NEGATION_PATTERNS)
            part_has_crisis = (not part_negated) and any(pat.search(part) for pat in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE)
            if part_has_crisis and idx > 0:
                return None  # Subsequent clause has un-negated crisis
            if part_has_crisis and idx == 0:
                allow_idiom_bypass = False

    # (2) Specific compound distress pattern that is active distress:
    if re.search(r"\bi\s+feel\s+like\s+everything\s+is\s+falling\s+apart\s+and\s+i\s+can'?t\s+stop\s+it\b", t):
        return None
    if re.search(r"\b(?:don'?t|do\s+not|can'?t|cannot)\s+(?:know\s+how\s+to\s+)?stop\s+(?:hurting|harming|cutting)\s+myself\b", t):
        return None

    # (2.5) Third-party subject check: "my friend is going to kill herself"
    _third_party_compiled = [_c(p) for p in _THIRD_PARTY_SUBJECT_PATTERNS]
    if any(pat.search(t) for pat in _third_party_compiled):
        # Third-party subjects: crisis is about someone else, not the speaker.
        # Check if any EXPLICIT first-person pronoun precedes a crisis verb.
        has_first_person_crisis = bool(re.search(
            r"\bi(?:'m|\s+am|\s+will|\s+have|\s+want|\s+plan|\s+feel|\s+need|'ve)\s+"
            r"(?:(?:going\s+)?to\s+|gonna\s+)?(?:kill|hurt|harm|end|cut|overdos|suicide|swallow|jump|hang|shoot|drown|crash|have\s+(?:the\s+)?(?:pills|rope|blade))",
            t, re.IGNORECASE
        ))
        has_explicit_override = any(pat.search(t) for pat in [_c(p) for p in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE_RAW])
        if not (has_first_person_crisis or has_explicit_override):
            return "third_party_subject_report"

    # (2.6) Accidental / benign context check
    _accidental_compiled = [_c(p) for p in _ACCIDENTAL_CONTEXT_PATTERNS]
    if any(pat.search(t) for pat in _accidental_compiled):
        return "accidental_or_benign_context"

    # (2.7) Slang hyperbole dampener: kms/kys/unalive in humorous/trivial context
    discourse = evaluate_discourse(text)
    if discourse.should_downgrade:
        return "slang_hyperbole_dampener"
    _slang_dampener_compiled = [_c(p) for p in _SLANG_HYPERBOLE_DAMPENER_PATTERNS]
    if any(pat.search(t) for pat in _slang_dampener_compiled):
        return "slang_hyperbole_dampener"

    # (2.8) Protective contrast: "want to die but won't because of my dog"
    _protective_compiled = [_c(p) for p in _PROTECTIVE_CONTRAST_PATTERNS]
    if any(pat.search(t) for pat in _protective_compiled):
        return "protective_contrast_clause"

    # (3) Idiom / hyperbole -- checked when not overridden by a crisis clause
    if allow_idiom_bypass:
        for pat in IDIOMATIC_METAPHOR_AND_HYPERBOLE_PATTERNS:
            if pat.search(t):
                # Check if idiom is followed by genuine crisis escalation via "so"/"and"
                if len(so_parts) == 2:
                    second_half = so_parts[1]
                    if any(p.search(second_half) for p in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE):
                        return None  # Idiom + genuine crisis escalation
                return "idiomatic_or_hyperbolic_expression"

    # (4) Direct grammatical negation of a crisis phrase / survival request.
    for pat in NEGATION_PATTERNS:
        if pat.search(t):
            # Negation-disclaimer paradox fix:
            # "I'm not suicidal, but I took the pills / want to die tonight"
            # (negation in 1st clause + un-negated lethal action in 2nd clause)
            negation_contrast = [p.strip() for p in re.split(r"\b(?:but|just|except|although|however|yet)\b", t) if p.strip()][:4]
            if len(negation_contrast) >= 2:
                for second_clause in negation_contrast[1:]:
                    second_is_negated = any(p.search(second_clause) for p in NEGATION_PATTERNS)
                    if not second_is_negated:
                        _lethal_compiled = [_c(p) for p in _NEGATION_OVERRIDE_LETHAL_ACTIONS]
                        if any(lp.search(second_clause) for lp in _lethal_compiled):
                            return None  # Override negation — lethal action in subsequent clause
            return "grammatical_negation"

    # (5) Past historical reflection with resolution
    past_sig = has_past_anchor(t)
    if past_sig.detected:
        relapse_sig = has_acute_relapse(t)
        if not relapse_sig.detected:
            res_sig = has_confirmed_resolution(t)
            if res_sig.detected:
                return "past_historical_reflection_with_confirmed_resolution"
            return "past_historical_reflection"

    # (6) Support-seeking and emotionally venting language without present self-harm/crisis intent
    for pat in SUPPORT_REQUEST_AND_VENTING_PATTERNS:
        if pat.search(t):
            if not any(override.search(t) for override in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE):
                return "support_request_or_emotional_venting"

    # (7) Academic context
    if detect_academic_frame(t) or any(pat.search(t) for pat in ACADEMIC_CONTEXT_PATTERNS):
        unquoted = re.sub(r"['\"].*?['\"]", "", t)
        has_real_override = any(pat.search(unquoted) for pat in [_c(p) for p in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE_RAW])
        if not has_real_override:
            return "academic_or_research_context"

    # (8) Media / third-person / fictional narrative context
    if detect_fictional_frame(t) or any(pat.search(t) for pat in MEDIA_CONTEXT_PATTERNS):
        unquoted = re.sub(r"['\"].*?['\"]", "", t)
        has_real_override = any(pat.search(unquoted) for pat in [_c(p) for p in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE_RAW])
        if not has_real_override:
            return "media_or_third_person_reference"

    # (9) Non-crisis situational expressions -- must not suppress active first-person crisis overrides
    for pat in NON_CRISIS_SITUATIONAL_EXPRESSIONS:
        if pat.search(t):
            if not any(override.search(t) for override in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE):
                return "non_crisis_situational_expression"

    return None


def is_contextual_or_negated(text: str) -> bool:
    """
    Public API helper. Returns True if the text contains a negation, past history,
    or academic/media reference that suppresses crisis classification.
    If ANY sentence contains un-bypassed first-person present crisis intent, returns False.
    """
    if not text or not text.strip():
        return False

    sentences = _split_sentences(text)
    discourse = evaluate_discourse(text, sentences)
    if discourse.should_downgrade:
        return True

    # Check if ANY sentence contains active un-bypassed first-person crisis intent
    has_unbypassed_crisis_sentence = False
    has_bypassed_sentence = False

    for sentence in sentences:
        norm_sent = _normalize(sentence)
        has_crisis_pattern = match_crisis_regex(norm_sent) or any(p.search(norm_sent) for p in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE)
        reason = _contextual_bypass_reason(sentence)
        
        if has_crisis_pattern and reason is None:
            has_unbypassed_crisis_sentence = True
        elif reason is not None:
            has_bypassed_sentence = True

    # If any sentence has active un-bypassed crisis intent, crisis stands (return False)
    if has_unbypassed_crisis_sentence:
        return False

    # Return True if a contextual/negated bypass reason was found
    return has_bypassed_sentence


def _find_category_matches(norm_text: str) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {}
    for cat in CRISIS_PATTERN_CATEGORIES:
        hits = [m.group(0) for pat in cat.patterns if (m := pat.search(norm_text))]
        if hits:
            found[cat.name] = hits
    return found


def _severity_to_label(severity: int) -> str:
    if severity >= 5:
        return "imminent"
    if severity >= 4:
        return "high"
    if severity >= 3:
        return "moderate"
    return "none"


def _empty_result(risk_level: str = "none") -> Dict:
    return {
        "is_crisis": False,
        "risk_level": risk_level,
        "matched_categories": [],
        "matched_phrases": [],
        "bypass_triggered": False,
        "bypass_reason": None,
        "sentence_findings": [],
        "confidence": 0.95,
        "recommended_action": "none",
    }


def evaluate_crisis(text: str, preprocess_result: Optional[PreprocessResult] = None) -> Dict:
    if not text or not text.strip():
        return _empty_result()

    pp = preprocess_result or preprocess_text(text)
    clean_text = pp.text

    sentences = _split_sentences(clean_text)

    sentence_findings: List[Dict] = []
    escalating_categories: set = set()
    escalating_phrases: set = set()
    all_matched_categories: set = set()
    all_matched_phrases: set = set()
    any_crisis_sentence_found = False
    last_bypass_reason: Optional[str] = None
    max_escalating_severity = 0

    for sentence in sentences:
        norm_sentence = _normalize(sentence)
        cat_matches = _find_category_matches(norm_sentence)

        if not cat_matches:
            sentence_findings.append({
                "sentence": sentence,
                "matched_categories": [],
                "bypassed": False,
                "bypass_reason": None,
            })
            continue

        any_crisis_sentence_found = True
        for cname, phrases in cat_matches.items():
            all_matched_categories.add(cname)
            all_matched_phrases.update(phrases)

        reason = _contextual_bypass_reason(sentence)
        is_bypassed = reason is not None
        if is_bypassed:
            last_bypass_reason = reason
        else:
            for cname, phrases in cat_matches.items():
                escalating_categories.add(cname)
                escalating_phrases.update(phrases)
                cat_obj = next(c for c in CRISIS_PATTERN_CATEGORIES if c.name == cname)
                max_escalating_severity = max(max_escalating_severity, cat_obj.severity)

        sentence_findings.append({
            "sentence": sentence,
            "matched_categories": list(cat_matches.keys()),
            "bypassed": is_bypassed,
            "bypass_reason": reason,
        })

    if not any_crisis_sentence_found:
        return _empty_result()

    if escalating_categories:
        risk_level = _severity_to_label(max_escalating_severity)
        action = (
            "escalate_to_crisis_protocol_immediately"
            if risk_level == "imminent"
            else "escalate_to_crisis_protocol"
            if risk_level == "high"
            else "flag_for_human_review"
        )
        return {
            "is_crisis": True,
            "risk_level": risk_level,
            "matched_categories": sorted(all_matched_categories, key=lambda c: (-next((cat.severity for cat in CRISIS_PATTERN_CATEGORIES if cat.name == c), 0), c)),
            "matched_phrases": sorted(all_matched_phrases),
            "bypass_triggered": False,
            "bypass_reason": None,
            "sentence_findings": sentence_findings,
            "confidence": 0.9,
            "recommended_action": action,
            "preprocess_result": pp,
        }

    return {
        "is_crisis": False,
        "risk_level": "none",
        "matched_categories": sorted(all_matched_categories, key=lambda c: (-next((cat.severity for cat in CRISIS_PATTERN_CATEGORIES if cat.name == c), 0), c)),
        "matched_phrases": sorted(all_matched_phrases),
        "bypass_triggered": True,
        "bypass_reason": last_bypass_reason,
        "sentence_findings": sentence_findings,
        "confidence": 0.85,
        "recommended_action": "log_only",
        "preprocess_result": pp,
    }


from .crisis_resources import CRISIS_RESOURCES, SAFETY_DISCLAIMER

SAFETY_RESPONSE_TEMPLATE = """
I hear how deeply overwhelmed and in pain you are feeling right now, and I want you to know that your feelings are valid and you are not alone.

MindGuard is an automated AI tool and is NOT an emergency service or clinical medical provider. If you are in immediate physical danger, please contact local emergency services immediately or reach out to a trusted family member or friend who can stay with you.

Please connect with one of these free, confidential, 24/7 crisis support services right now:

🚑 **Rescue 1122 (medical emergency)**: 1122
👮 **Police emergency (immediate threat to another person)**: 15
📞 **Umang Pakistan Helpline (24/7)**: 0311-7786264
📞 **Rozan Emotional Support Line**: 0800-22444
"""

THIRD_PARTY_GUIDANCE_TEMPLATE = """
Thank you for reaching out and caring about someone in distress. Supporting a friend, family member, or colleague through a crisis is deeply important, and you do not have to carry this alone.

If you believe this person is in immediate physical danger, please contact local emergency services immediately or notify a trusted authority or family member who can stay with them.

Please connect with one of these free, confidential, 24/7 crisis support services right now:

🚑 **Rescue 1122 (medical emergency)**: 1122
👮 **Police emergency (immediate threat to another person)**: 15
📞 **Umang Pakistan Helpline (24/7)**: 0311-7786264
📞 **Rozan Emotional Support Line**: 0800-22444

💡 **Tips for Supporting Someone in Crisis**:
1. Listen without judgment and acknowledge their emotional pain.
2. Ask directly if they are having thoughts of suicide or self-harm.
3. Stay with them or help them connect directly to one of the crisis resources above.
4. Do not agree to keep suicidal plans a secret.
"""


def evaluate_deterministic_crisis(text: str) -> Dict:
    res = evaluate_crisis(text)
    return {
        "is_crisis": res["is_crisis"],
        "risk_level": res["risk_level"] if res["is_crisis"] else "none",
        "rule_triggered": res["matched_categories"][0] if res.get("matched_categories") else None,
        "safety_message": SAFETY_RESPONSE_TEMPLATE.strip(),
        "disclaimer": SAFETY_DISCLAIMER,
        "resources": CRISIS_RESOURCES
    }


def evaluate_crisis_pipeline(
    raw_text: str,
    context_turns: Optional[List[Dict[str, str]]] = None,
    allow_ml_fallback: bool = True
) -> Dict[str, Any]:
    """
    Primary single-entry orchestrator for multi-tier crisis detection in MindGuard.
    
    Execution Contract:
    1. Preprocessing: Executes clean normalization and semantic frame detection via generalizer.
    2. Third-Party Routing: If reporting another person's crisis, returns third-party guidance.
    3. Tier 1 (Deterministic Rules & Behavioral Preparatory):
       - Clinical Elevation: Prior recovery + present ideation elevates to 'imminent' (high_risk=True, imminent_risk=True).
       - Preparatory means + protective help-seeking sets 'elevated' (high_risk=False, protective_factor=True).
       - Preparatory means alone elevates to 'imminent' (high_risk=True, imminent_risk=True).
    4. Bypass Gating: If rules or semantic frame confirmed a bypass (academic, fictional, past recovery resolved, idiom, negation),
       suppresses ML fallback and returns non-crisis.
    5. Tier 2 (ML Intent Classifier): Fallback on clean text when rules are uncertain (no match and no bypass).
    6. Fail-Safe: On any unhandled exception, fails closed with high_risk and human review flag.
    """
    try:
        if not raw_text or not raw_text.strip():
            return {
                "is_crisis": False,
                "risk_level": "none",
                "high_risk": False,
                "imminent_risk": False,
                "protective_factor": False,
                "is_third_party": False,
                "source": "empty_input",
                "confidence": 1.0,
                "safety_message": "",
                "disclaimer": SAFETY_DISCLAIMER,
                "resources": CRISIS_RESOURCES,
            }

        # Step 1: Preprocess text cleanly
        pp = preprocess_text(raw_text)

        # Step 2: Third-party subject crisis routing (L1)
        if pp.is_third_party:
            unquoted = re.sub(r"['\"].*?['\"]", "", pp.text)
            has_first_person_crisis = bool(re.search(
                r"\bi(?:'m|\s+am|\s+will|\s+have|\s+want|\s+plan|\s+feel|\s+need|'ve)\s+"
                r"(?:(?:going\s+)?to\s+|gonna\s+)?(?:kill|hurt|harm|end|cut|overdos|suicide|swallow|jump|hang|shoot|drown|crash|have\s+(?:the\s+)?(?:pills|rope|blade))",
                unquoted, re.IGNORECASE
            ))
            has_explicit_override = any(pat.search(unquoted) for pat in [_c(p) for p in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE_RAW])
            if has_first_person_crisis or has_explicit_override:
                pp.is_third_party = False
            else:
                return {
                    "is_crisis": False,
                    "is_third_party": True,
                    "third_party_crisis_reported": True,
                    "risk_level": "none",
                    "high_risk": False,
                    "imminent_risk": False,
                    "protective_factor": False,
                    "source": "third_party_guidance",
                    "confidence": 0.95,
                    "safety_message": THIRD_PARTY_GUIDANCE_TEMPLATE.strip(),
                    "disclaimer": SAFETY_DISCLAIMER,
                    "resources": CRISIS_RESOURCES,
                    "preprocess_result": pp,
                }

        # Step 3: Extract modular extractor signals
        det_result = evaluate_crisis(pp.text, preprocess_result=pp)
        temporal = extract_temporal_state(pp.text, pp)
        discourse = evaluate_discourse(raw_text, _split_sentences(pp.text))
        concepts = extract_all_concepts(pp.text)
        unquoted = re.sub(r"['\"].*?['\"]", "", pp.text)
        has_first_person_override = any(pat.search(unquoted) for pat in [_c(p) for p in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE_RAW])

        # Step 4: Run Precedence Arbitration
        arb_input = ArbitrationInput(
            base_severity=next((cat.severity for cat in CRISIS_PATTERN_CATEGORIES if cat.name in det_result.get("matched_categories", [])), 0) if det_result.get("is_crisis") else 0,
            base_risk_level=det_result.get("risk_level", "none"),
            is_base_crisis=det_result.get("is_crisis", False),
            matched_categories=det_result.get("matched_categories", []),
            matched_phrases=det_result.get("matched_phrases", []),
            bypass_reason=det_result.get("bypass_reason"),
            temporal=temporal,
            discourse=discourse,
            semantic_concepts=concepts,
            is_academic=pp.is_academic,
            is_fictional=pp.is_fictional,
            is_third_party=pp.is_third_party,
            has_preparatory_behavior=pp.has_preparatory_behavior,
            has_protective_behavior=pp.has_protective_behavior,
            has_first_person_override=has_first_person_override,
        )
        arb_result = arbitrate(arb_input)

        # Step 4a: Deterministic / Concept / Relapse Crisis Match
        if arb_result.is_crisis:
            return {
                "is_crisis": True,
                "risk_level": arb_result.risk_level,
                "high_risk": arb_result.high_risk,
                "imminent_risk": arb_result.imminent_risk,
                "protective_factor": arb_result.protective_factor,
                "is_third_party": False,
                "rule_triggered": arb_result.rule_triggered or (det_result["matched_categories"][0] if det_result.get("matched_categories") else None),
                "matched_categories": det_result.get("matched_categories", []) or ([arb_result.rule_triggered] if arb_result.rule_triggered else []),
                "matched_phrases": det_result.get("matched_phrases", []),
                "source": arb_result.source,
                "confidence": arb_result.confidence,
                "safety_message": SAFETY_RESPONSE_TEMPLATE.strip(),
                "disclaimer": SAFETY_DISCLAIMER,
                "resources": CRISIS_RESOURCES,
                "preprocess_result": pp,
            }

        # Step 4b: Contextual Bypass Gating (suppress ML fallback)
        if arb_result.bypass_triggered:
            return {
                "is_crisis": False,
                "risk_level": "none",
                "high_risk": False,
                "imminent_risk": False,
                "protective_factor": arb_result.protective_factor,
                "is_third_party": False,
                "bypass_triggered": True,
                "bypass_reason": arb_result.bypass_reason or det_result.get("bypass_reason"),
                "source": arb_result.source,
                "confidence": arb_result.confidence,
                "safety_message": "",
                "disclaimer": SAFETY_DISCLAIMER,
                "resources": CRISIS_RESOURCES,
                "preprocess_result": pp,
            }

        # Step 5: Tier 2 - ML Fallback (Uncertain / No Rules Fired)
        if allow_ml_fallback:
            if is_informational_or_coping_query(pp.text):
                return {
                    "is_crisis": False,
                    "risk_level": "none",
                    "high_risk": False,
                    "imminent_risk": False,
                    "protective_factor": False,
                    "is_third_party": False,
                    "source": "coping_or_info_request",
                    "confidence": 0.95,
                    "safety_message": "",
                    "disclaimer": SAFETY_DISCLAIMER,
                    "resources": CRISIS_RESOURCES,
                    "preprocess_result": pp,
                }

            from .huggingface_service import analyze_user_message
            ml_res = analyze_user_message(pp.text, context_turns=context_turns)

            if ml_res.get("intent") == "SUICIDE CRISIS OR SELF HARM RISK" and ml_res.get("intent_confidence", 0) > 0.40:
                return {
                    "is_crisis": True,
                    "risk_level": "high",
                    "high_risk": True,
                    "imminent_risk": False,
                    "protective_factor": pp.has_protective_behavior,
                    "is_third_party": False,
                    "source": "ml_intent",
                    "intent": ml_res.get("intent"),
                    "intent_confidence": ml_res.get("intent_confidence"),
                    "confidence": ml_res.get("intent_confidence", 0.85),
                    "safety_message": SAFETY_RESPONSE_TEMPLATE.strip(),
                    "disclaimer": SAFETY_DISCLAIMER,
                    "resources": CRISIS_RESOURCES,
                    "preprocess_result": pp,
                }

            return {
                "is_crisis": False,
                "risk_level": "none",
                "high_risk": False,
                "imminent_risk": False,
                "protective_factor": pp.has_protective_behavior,
                "is_third_party": False,
                "source": "tier2_non_crisis",
                "intent": ml_res.get("intent"),
                "intent_confidence": ml_res.get("intent_confidence"),
                "emotion": ml_res.get("emotion"),
                "sentiment": ml_res.get("sentiment"),
                "confidence": 0.85,
                "safety_message": "",
                "disclaimer": SAFETY_DISCLAIMER,
                "resources": CRISIS_RESOURCES,
                "preprocess_result": pp,
            }

        # Non-crisis default without ML fallback
        return {
            "is_crisis": False,
            "risk_level": "none",
            "high_risk": False,
            "imminent_risk": False,
            "protective_factor": pp.has_protective_behavior,
            "is_third_party": False,
            "source": "tier1_uncertain_noml",
            "confidence": 0.80,
            "safety_message": "",
            "disclaimer": SAFETY_DISCLAIMER,
            "resources": CRISIS_RESOURCES,
            "preprocess_result": pp,
        }

    except Exception as exc:
        # Step 7: Fail-Closed Emergency Fallback (L3)
        import logging
        logging.getLogger("MindGuard-API").error(f"Crisis pipeline error: {exc}", exc_info=True)
        return {
            "is_crisis": True,
            "risk_level": "high",
            "high_risk": True,
            "imminent_risk": False,
            "protective_factor": False,
            "is_third_party": False,
            "source": "error_fallback",
            "needs_human_review": True,
            "error_detail": str(exc),
            "confidence": 0.50,
            "safety_message": SAFETY_RESPONSE_TEMPLATE.strip(),
            "disclaimer": SAFETY_DISCLAIMER,
            "resources": CRISIS_RESOURCES,
        }
