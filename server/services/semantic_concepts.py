"""
semantic_concepts.py
====================

Syntactically-bounded semantic concept grammars for MindGuard crisis detection.

Provides positive/negative pattern pair matching for complex figurative concepts:
1. Fatal sleep metaphors ("go to sleep and never wake up" vs "went to sleep and didn't wake up until noon")
2. Concealment ("don't want anyone to know what I'm planning to do" vs "planning a surprise party")
3. Irreversible exits ("no coming back from this" vs "no coming back from vacation")

By decoupling positive intent triggers from negative false-positive blockers,
we prevent cross-pattern interference and maintain clean syntactic boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, List, Tuple


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class ConceptMatch:
    """Result of a semantic concept evaluation."""
    detected: bool
    concept: str                          # "fatal_sleep" | "concealment" | "irreversible_exit"
    confidence: float = 0.0              # 0.0–1.0
    matched_span: Optional[str] = None    # the positive text fragment that matched
    blocked_by: Optional[str] = None      # pattern string that suppressed the match (if any)


# ---------------------------------------------------------------------------
# Compiled Pattern Sets
# ---------------------------------------------------------------------------

def _c(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


# 1. FATAL SLEEP METAPHOR
_FATAL_SLEEP_POSITIVE: List[re.Pattern] = [
    _c(r"\b(?:go|going|want\s+to\s+go)\s+to\s+sleep\s+and\s+(?:never|not)\s+(?:have\s+to\s+)?(?:wake|get)\s+up\b"),
    _c(r"\b(?:go\s+to\s+)?sleep\s+and\s+(?:not|never)\s+(?:have\s+to\s+)?wake\s+up(?:\s+to\s+this)?\b"),
    _c(r"\b(?:close|shut)\s+my\s+eyes\s+and\s+(?:never|not)\s+(?:wake|open\s+them)\s*(?:up|again)?\b"),
    _c(r"\bsleep\s+forever\b"),
    _c(r"\bwant\s+to\s+sleep\s+and\s+(?:never|not)\s+wake\s+up\b"),
    _c(r"\bforever\s+kind\s+of\s+(?:rest|sleep)\b"),
    _c(r"\bgo\s+to\s+sleep\s+and\s+not\s+wake\s+up\b"),
    _c(r"\bnever\s+want\s+to\s+wake\s+up\s+again\b"),
    _c(r"\bwish\s+(?:i\s+)?would\s+never\s+wake\s+up\b"),
    _c(r"\bwish\s+i\s+could\s+just\s+sleep\s+and\s+not\s+wake\s+up\b"),
    _c(r"\bput\s+me\s+to\s+sleep\s+permanently\b"),
]

_FATAL_SLEEP_NEGATIVE_BLOCKERS: List[re.Pattern] = [
    _c(r"\b(?:didn'?t|did\s+not|not)\s+wake\s+up\s+(?:until|till|'?til)\s+(?:noon|morning|\d+|late|lunch|afternoon|dawn)\b"),
    _c(r"\b(?:fell|went)\s+(?:back\s+)?to\s+sleep\s+and\s+(?:woke|got)\s+up\s+(?:late|at\s+\d+|in\s+the\s+afternoon|around\s+\d+)\b"),
    _c(r"\bslept?\s+(?:in|through\s+(?:the\s+)?(?:alarm|night|morning|noise))\b"),
    _c(r"\bwent\s+to\s+sleep\s+(?:tired|early|late|at\s+\d+)\b"),
    _c(r"\bclosed?\s+my\s+eyes\s+and\s+(?:fell\s+asleep|rested|took\s+a\s+nap)\b"),
    _c(r"\bso\s+tired\s+(?:i\s+)?(?:went\s+to\s+sleep|slept)\b"),
    _c(r"\bneed\s+a\s+good\s+night'?s?\s+sleep\b"),
]

# 2. CONCEALMENT
_CONCEALMENT_POSITIVE: List[re.Pattern] = [
    _c(r"\bdon'?t\s+want\s+anyone\s+to\s+know\s+what\s+i'?m\s+planning\b"),
    _c(r"\bhid(?:den)?\s+(?:the|my)\s+(?:suicide\s+|goodbye\s+)?note\s+where\s+(?:they|someone|nobody)\b"),
    _c(r"\bwait(?:ing)?\s+until\s+(?:everyone|family|my\s+parents?|they)\s+is\s+asleep\b"),
    _c(r"\bpicked\s+a\s+spot\s+where\s+nobody\s+will\s+find\s+me\b"),
    _c(r"\bnot\s+telling\s+anyone\s+until\s+after\s+(?:it'?s\s+done|i'?m\s+gone)\b"),
    _c(r"\bkeep(?:ing)?\s+(?:my|this)\s+(?:plan|suicide|goodbye)\s+(?:a\s+)?secret\b"),
    _c(r"\bthey\s+won'?t\s+find\s+me\s+until\s+it'?s\s+too\s+late\b"),
    _c(r"\bsaying\s+goodbye\s+without\s+(?:them\s+knowing|telling\s+them\s+why)\b"),
    _c(r"\bdo\s+it\s+where\s+no\s*one\s+(?:can\s+see|will\s+look)\b"),
]

_CONCEALMENT_NEGATIVE_BLOCKERS: List[re.Pattern] = [
    _c(r"\b(?:surprise\s+party|birthday\s+gift|present|proposal|anniversary|secret\s+santa)\b"),
    _c(r"\bplanning\s+(?:a\s+)?(?:party|trip|vacation|event|surprise|wedding|dinner)\b"),
    _c(r"\bhid(?:den)?\s+(?:the\s+)?(?:presents?|gifts?|keys?|candy|money)\b"),
    _c(r"\bdon'?t\s+want\s+anyone\s+to\s+know\s+about\s+the\s+(?:promotion|score|grade|test|result|interview)\b"),
]

# 3. IRREVERSIBLE EXIT
_IRREVERSIBLE_EXIT_POSITIVE: List[re.Pattern] = [
    _c(r"\bend\s+it\s+all\s+permanently\b"),
    _c(r"\b(?:there'?s?\s+)?no\s+coming\s+back\s+from\s+this\b"),
    _c(r"\bthis\s+is\s+my\s+final\s+exit\b"),
    _c(r"\btaking\s+the\s+permanent\s+way\s+out\b"),
    _c(r"\bpoint\s+of\s+no\s+return\s+for\s+me\b"),
    _c(r"\bpermanent\s+solution\s+to\s+(?:my\s+)?problems?\b"),
    _c(r"\bno\s+turning\s+back\s+now\b"),
    _c(r"\bleaving\s+this\s+world\s+for\s+good\b"),
    _c(r"\bexit(?:ing)?\s+life\s+permanently\b"),
]

_IRREVERSIBLE_EXIT_NEGATIVE_BLOCKERS: List[re.Pattern] = [
    _c(r"\b(?:vacation|holiday|trip|concert|movie|feeling|high)\b"),
    _c(r"\bend\s+(?:this\s+)?(?:project|chapter|semester|game|contract|subscription|meeting|call|class)\b"),
    _c(r"\bno\s+turning\s+back\s+on\s+this\s+(?:deal|investment|project|career|decision|offer)\b"),
]


# ---------------------------------------------------------------------------
# Evaluators
# ---------------------------------------------------------------------------

def detect_fatal_sleep(text: str) -> ConceptMatch:
    """
    Detects fatal sleep metaphors ('go to sleep and never wake up').
    Guarded against benign completions ('went to sleep and didn't wake up until noon').
    """
    for pos in _FATAL_SLEEP_POSITIVE:
        m = pos.search(text)
        if m:
            # Check negative blockers
            for neg in _FATAL_SLEEP_NEGATIVE_BLOCKERS:
                if neg.search(text):
                    return ConceptMatch(
                        detected=False,
                        concept="fatal_sleep",
                        confidence=0.0,
                        matched_span=m.group(0),
                        blocked_by=neg.pattern,
                    )
            return ConceptMatch(
                detected=True,
                concept="fatal_sleep",
                confidence=0.92,
                matched_span=m.group(0),
            )
    return ConceptMatch(detected=False, concept="fatal_sleep")


def detect_concealment(text: str) -> ConceptMatch:
    """
    Detects language about concealing suicidal plans.
    Guarded against benign concealment (surprise party, gifts).
    """
    for pos in _CONCEALMENT_POSITIVE:
        m = pos.search(text)
        if m:
            for neg in _CONCEALMENT_NEGATIVE_BLOCKERS:
                if neg.search(text):
                    return ConceptMatch(
                        detected=False,
                        concept="concealment",
                        confidence=0.0,
                        matched_span=m.group(0),
                        blocked_by=neg.pattern,
                    )
            return ConceptMatch(
                detected=True,
                concept="concealment",
                confidence=0.90,
                matched_span=m.group(0),
            )
    return ConceptMatch(detected=False, concept="concealment")


def detect_irreversible_exit(text: str) -> ConceptMatch:
    """
    Detects permanent/irreversible exit framing.
    Guarded against benign usage (vacation, end of semester/project).
    """
    for pos in _IRREVERSIBLE_EXIT_POSITIVE:
        m = pos.search(text)
        if m:
            for neg in _IRREVERSIBLE_EXIT_NEGATIVE_BLOCKERS:
                if neg.search(text):
                    return ConceptMatch(
                        detected=False,
                        concept="irreversible_exit",
                        confidence=0.0,
                        matched_span=m.group(0),
                        blocked_by=neg.pattern,
                    )
            return ConceptMatch(
                detected=True,
                concept="irreversible_exit",
                confidence=0.90,
                matched_span=m.group(0),
            )
    return ConceptMatch(detected=False, concept="irreversible_exit")


def extract_all_concepts(text: str) -> List[ConceptMatch]:
    """Extract and return results for all 3 semantic concept grammars."""
    return [
        detect_fatal_sleep(text),
        detect_concealment(text),
        detect_irreversible_exit(text),
    ]
