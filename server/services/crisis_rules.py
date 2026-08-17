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
from typing import Dict, List, Optional, Tuple

__all__ = [
    "CRISIS_PATTERNS",
    "CRISIS_PATTERN_CATEGORIES",
    "is_contextual_or_negated",
    "evaluate_crisis",
    "evaluate_deterministic_crisis",
]


from .intent_rules import CRISIS_EXPLICIT_PATTERNS, match_crisis_regex

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
    t = text.replace("\u2019", "'").replace("\u2018", "'")
    t = t.replace("\u201c", '"').replace("\u201d", '"')
    t = t.lower()
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
    r"\bbought\s+the\s+rope\b",
    r"\bpicked\s+the\s+bridge\b",
    r"\bhave\s+set\s+a\s+date\s+and\s+i'?m\s+sticking\s+to\s+it\b",
    r"\bhave\s+thought\s+this\s+through\s+completely,?\s+it'?s\s+decided\b",
    r"\bhave\s+decided\s+when\s+it'?s\s+going\s+to\s+happen\b",
    r"\bpicked\s+the\s+day\s+it'?s\s+going\s+to\s+happen\b",
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
    r"\b(?:not|never|no|wasn'?t|isn'?t|don'?t|won'?t|ain'?t|didn'?t|couldn'?t|wouldn'?t|shouldn'?t)\b(?:\s+(?!but\b|however\b|though\b|except\b|yet\b|stop\b|know\b)\w+){0,6}\s+\b(?:self[\s-]?harm(?:ing)?|hurt(?:ing)?\s+myself|harm(?:ing)?\s+myself|kill(?:ing)?\s+myself|end(?:ing)?\s+(?:my\s+life|it\s+all|it|things)|suicid\w*|take\s+my\s+(?:own\s+)?life|do\s+anything\s+to\s+myself)\b",
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
]

_CONTINUATION_OVERRIDE_MARKERS = [
    r"\bstill\s+(?:feel|feeling|have|having|want)\b",
    r"\beven\s+now\b",
    r"\bto\s+this\s+day\b",
    r"\band\s+(?:i\s+)?still\b",
    r"\bback\s+there\s+again\b",
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
    r"\bhave\s+the\s+pills\s+in\s+front\s+of\s+me\b",
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
]
_FIRST_PERSON_PRESENT_CRISIS_OVERRIDE: List[re.Pattern] = (
    CRISIS_EXPLICIT_PATTERNS +
    [_c(p) for p in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE_RAW] +
    [_c(p) for p in _INDIRECT_IMPLICIT_DISTRESS] +
    [_c(p) for p in _BURDEN_AND_GOODBYE] +
    [_c(p) for p in _LETHAL_MEANS_AND_PREPARATION] +
    [_c(p) for p in _SUBTLE_SLANG_AND_INFORMAL] +
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
    contrast_parts = re.split(r"\b(?:but|however|though|yet)\b", t, maxsplit=1)
    allow_idiom_bypass = True
    if len(contrast_parts) == 2:
        pre_negated = any(pat.search(contrast_parts[0]) for pat in NEGATION_PATTERNS)
        post_negated = any(pat.search(contrast_parts[1]) for pat in NEGATION_PATTERNS)

        pre_has_crisis = (not pre_negated) and any(pat.search(contrast_parts[0]) for pat in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE)
        post_has_crisis = (not post_negated) and any(pat.search(contrast_parts[1]) for pat in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE)
        if post_has_crisis:
            return None
        if pre_has_crisis:
            allow_idiom_bypass = False

    # (2) Specific compound distress pattern that is active distress:
    if re.search(r"\bi\s+feel\s+like\s+everything\s+is\s+falling\s+apart\s+and\s+i\s+can'?t\s+stop\s+it\b", t):
        return None
    if re.search(r"\b(?:don'?t|do\s+not|can'?t|cannot)\s+(?:know\s+how\s+to\s+)?stop\s+(?:hurting|harming|cutting)\s+myself\b", t):
        return None

    # (3) Idiom / hyperbole -- checked when not overridden by a crisis clause
    if allow_idiom_bypass:
        for pat in IDIOMATIC_METAPHOR_AND_HYPERBOLE_PATTERNS:
            if pat.search(t):
                return "idiomatic_or_hyperbolic_expression"

    # (4) Direct grammatical negation of a crisis phrase / survival request.
    for pat in NEGATION_PATTERNS:
        if pat.search(t):
            return "grammatical_negation"

    # (5) Past historical reflection with resolution
    if any(pat.search(t) for pat in PAST_HISTORICAL_REFLECTION_PATTERNS):
        if not any(pat.search(t) for pat in CONTINUATION_OVERRIDE_MARKERS):
            if any(pat.search(t) for pat in RESOLUTION_MARKERS):
                return "past_historical_reflection_with_confirmed_resolution"
            return "past_historical_reflection"

    # (6) Support-seeking and emotionally venting language without present self-harm/crisis intent
    for pat in SUPPORT_REQUEST_AND_VENTING_PATTERNS:
        if pat.search(t):
            if not any(override.search(t) for override in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE):
                return "support_request_or_emotional_venting"

    # (7) Academic context
    if any(pat.search(t) for pat in ACADEMIC_CONTEXT_PATTERNS):
        if not any(pat.search(t) for pat in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE):
            return "academic_or_research_context"

    # (8) Media / third-person context
    if any(pat.search(t) for pat in MEDIA_CONTEXT_PATTERNS):
        if not any(pat.search(t) for pat in _FIRST_PERSON_PRESENT_CRISIS_OVERRIDE):
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


def evaluate_crisis(text: str) -> Dict:
    if not text or not text.strip():
        return _empty_result()

    sentences = _split_sentences(text)

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
    }


from .crisis_resources import CRISIS_RESOURCES, SAFETY_DISCLAIMER

SAFETY_RESPONSE_TEMPLATE = """
I hear how deeply overwhelmed and in pain you are feeling right now, and I want you to know that your feelings are valid and you are not alone.

MindGuard is an automated AI tool and is NOT an emergency service or clinical medical provider. If you are in immediate physical danger, please contact local emergency services immediately or reach out to a trusted family member or friend who can stay with you.

Please connect with one of these free, confidential, 24/7 crisis support services right now:

📞 **Umang Pakistan Helpline (24/7)**: 0311-7786264
📞 **Rozan Emotional Support Line**: 0800-22444
📞 **Suicide & Crisis Lifeline (US & Canada)**: Call or Text 988
💬 **Crisis Text Line**: Text HOME to 741741
🌐 **Global Helpline Finder**: https://findahelpline.com
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
