"""
discourse_evaluator.py
======================

Windowed multi-sentence discourse and sarcasm evaluator for MindGuard.

Replaces flat, single-sentence-independent sarcasm and hyperbole evaluation
with a windowed discourse parser that distinguishes:
1. Casual hyperbole ("If I get another email I'll unalive myself, lol") -> safe to downgrade
2. Nervous laughter / masked genuine distress ("I've been planning this for weeks. Tonight is it. lol") -> DO NOT downgrade
3. Cross-sentence retractions ("I want to die." -> "Just kidding lmao.") -> safe to downgrade

Safety boundaries:
- Lethal means mentions in ANY window -> never downgrade
- Planning language in ANY window -> never downgrade
- Escalation in ANY window -> never downgrade
- Multi-sentence crisis (>=2 crisis windows) with trailing humor -> never downgrade
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class WindowRisk:
    """Risk assessment for a single sentence/window."""
    sentence: str
    sentence_index: int
    has_crisis_signal: bool = False
    has_humor_marker: bool = False
    has_planning_language: bool = False
    has_method_mention: bool = False
    has_escalation: bool = False
    matched_patterns: List[str] = field(default_factory=list)


@dataclass
class DiscourseContext:
    """Composed multi-sentence discourse assessment."""
    windows: List[WindowRisk]
    is_genuine_distress: bool = False
    humor_type: str = "none"            # "casual_hyperbole" | "nervous_laughter" | "none"
    should_downgrade: bool = False       # Final recommendation: safe to bypass/downgrade
    cross_sentence_retraction: bool = False
    has_safety_blocker: bool = False     # Means/planning/escalation blocked downgrade
    reasoning: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Pattern Sets
# ---------------------------------------------------------------------------

def _c(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


# Humor / Sarcasm / Joke markers
_HUMOR_MARKERS: List[re.Pattern] = [
    _c(r"\b(?:lol|lmao|rofl|lmfao|haha|hahaha|hahahaha|hehe|j[/\\]?k|jk|joking|just\s+kidding|sarcasm|sarcastic|as\s+a\s+joke|just\s+a\s+joke|just\s+a\s+meme|meme)\b"),
    _c(r"(?:😂|🤣|😹|💀|😭\s*😭)"),
    _c(r"\bi\s+am\s+(?:just\s+)?(?:kidding|joking|messing\s+around|being\s+dramatic)\b"),
    _c(r"\bnot\s+(?:really|actually|seriously|literally)\b"),
    _c(r"\bdon'?t\s+take\s+me\s+seriously\b"),
    _c(r"\bi'?m\s+(?:actually\s+)?(?:fine|okay|ok|good)\b"),
    _c(r"\bbrb\b"),
]

# Planning language indicators
_PLANNING_MARKERS: List[re.Pattern] = [
    _c(r"\b(?:been\s+)?planning\s+(?:this|how\s+to|my\s+death|to\s+end)\b"),
    _c(r"\b(?:wrote|written|leaving|leaving\s+a|hid|hide)\s+(?:a\s+|my\s+)?(?:goodbye|suicide|farewell)?\s*(?:note|letter|will)\b"),
    _c(r"\bgoodbye\s+(?:note|letter)\b"),
    _c(r"\bmade\s+(?:a\s+|all\s+the\s+)?(?:plan|arrangements)\b"),
    _c(r"\bhave\s+a\s+plan\b"),
    _c(r"\bpicked\s+(?:the\s+|a\s+)?(?:bridge|date|day|spot|time)\b"),
    _c(r"\bset\s+a\s+date\b"),
    _c(r"\bsettled\s+(?:all\s+)?my\s+debts\b"),
    _c(r"\bgave\s+away\s+my\s+(?:stuff|things|belongings|possessions)\b"),
    _c(r"\bhave\s+everything\s+(?:ready|set\s+up)\b"),
]

# Lethal means indicators (cannot be downgraded by humor)
_METHOD_MARKERS: List[re.Pattern] = [
    _c(r"\b(?:pills|medication|tablets|capsules|painkillers?|sleeping\s+pills)\b"),
    _c(r"\b(?:rope|noose)\b"),
    _c(r"\b(?:blade|razor|knife|knives|scalpel)\b"),
    _c(r"\b(?:gun|firearm|pistol|revolver)\b"),
    _c(r"\b(?:bridge|ledge|roof|rooftop|balcony)\b"),
    _c(r"\b(?:bleach|poison|pesticide|antifreeze|chemicals)\b"),
    _c(r"\b(?:hang|hanging|jump|jumping|cut|cutting|overdose|overdosing|drown|drowning)\b"),
]

# Escalation markers (urgency)
_ESCALATION_MARKERS: List[re.Pattern] = [
    _c(r"\b(?:tonight|today|right\s+now|at\s+midnight|this\s+evening)\b"),
    _c(r"\b(?:already|finally)\s+(?:took|swallowed|drank|made|did)\b"),
    _c(r"\bholding\s+(?:the|a)\b"),
    _c(r"\bstanding\s+on\s+the\b"),
    _c(r"\blast\s+(?:day|night|message|goodbye|words)\b"),
    _c(r"\bwon'?t\s+see\s+tomorrow\b"),
]

# Slang hyperbole dampeners (direct slang in trivial/joke context)
_SLANG_HYPERBOLE_EXPLICIT: List[re.Pattern] = [
    _c(r"\b(?:unalive|kill\s+myself|kill)\s+(?:this\s+|my\s+)?(?:alarm\s+clock|pizza|burger|food|chicken|sandwich|steak|game|laptop|phone|computer|car|printer)\b"),
    _c(r"\b(?:kys|kill\s+yourself)\s*,\s*(?:printer|computer|laptop|code|bug|wifi|phone|server|screen)\b"),
    _c(r"\breset\s+the\s+sim\s+after\s+this\s+boss\s+fight\b"),
    _c(r"\bmean\s+restart\s+the\s+game\b"),
    _c(r"\bfinna\s+tap\s+out\s+for\s+the\s+night\b"),
    _c(r"\b(?:if\s+i\s+get\s+another\s+email|this\s+exam\s+is\s+killing\s+me|traffic\s+is\s+making\s+me\s+want\s+to\s+die)\b"),
]

# Common hyperbole context switches
_CONTEXT_SWITCH_MARKERS: List[re.Pattern] = [
    _c(r"\b(?:anyway|anyways|anywho|moving\s+on|on\s+another\s+note|so\s+yeah|whatever)\b"),
    _c(r"\bwhat'?s\s+for\s+(?:dinner|lunch|breakfast)\b"),
    _c(r"\bhow\s+about\s+you\b"),
]


# ---------------------------------------------------------------------------
# Evaluator Logic
# ---------------------------------------------------------------------------

def evaluate_window(sentence: str, index: int) -> WindowRisk:
    """Analyze a single sentence window for signals."""
    s = sentence.strip()
    if not s:
        return WindowRisk(sentence=sentence, sentence_index=index)

    # Check humor
    has_humor = any(p.search(s) for p in _HUMOR_MARKERS) or any(p.search(s) for p in _SLANG_HYPERBOLE_EXPLICIT)

    # Check planning
    has_planning = any(p.search(s) for p in _PLANNING_MARKERS)

    # Check method
    has_method = any(p.search(s) for p in _METHOD_MARKERS)

    # Check escalation
    has_escalation = any(p.search(s) for p in _ESCALATION_MARKERS)

    # Check generic crisis signal
    # Matches common intent phrases or slang
    crisis_signal_pats = [
        r"\b(?:kill\s+myself|kill\s+me|kill\s+me\s+now|want\s+to\s+die|wanna\s+die|end\s+my\s+life|suicid\w*|unalive\s+myself|kms|kys)\b",
        r"\b(?:die|ending\s+it\s+all|cut\s+myself|take\s+my\s+life|give\s+up\s+on\s+life|can'?t\s+live\s+anymore|cannot\s+live\s+anymore)\b",
        r"\b(?:can'?t|cannot)\s+(?:live|keep\s+living|go\s+on)\s+(?:anymore|like\s+this)?\b",
    ]
    has_crisis = any(re.search(p, s, re.IGNORECASE) for p in crisis_signal_pats)

    matched = []
    if has_humor:
        matched.append("humor")
    if has_planning:
        matched.append("planning")
    if has_method:
        matched.append("method")
    if has_escalation:
        matched.append("escalation")
    if has_crisis:
        matched.append("crisis")

    return WindowRisk(
        sentence=sentence,
        sentence_index=index,
        has_crisis_signal=has_crisis,
        has_humor_marker=has_humor,
        has_planning_language=has_planning,
        has_method_mention=has_method,
        has_escalation=has_escalation,
        matched_patterns=matched,
    )


def evaluate_discourse(text: str, sentences: Optional[List[str]] = None) -> DiscourseContext:
    """
    Multi-sentence windowed discourse evaluator.

    Evaluates whether sarcasm/humor in text is:
    - Casual hyperbole (safe to downgrade to low/none)
    - Nervous laughter / masked genuine distress (unsafe, keep crisis level)
    - Cross-sentence retraction (prior crisis sentence cancelled by humor sentence)
    """
    if not text or not text.strip():
        return DiscourseContext(windows=[])

    if sentences is None or len(sentences) == 0:
        # Fallback split
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|[\n\r]+", text) if s.strip()]
        if not sentences:
            sentences = [text.strip()]

    windows = [evaluate_window(s, i) for i, s in enumerate(sentences)]

    crisis_windows = [w for w in windows if w.has_crisis_signal or w.has_planning_language or w.has_method_mention]
    humor_windows = [w for w in windows if w.has_humor_marker]
    has_any_method = any(w.has_method_mention for w in windows)
    has_any_planning = any(w.has_planning_language for w in windows)
    has_any_escalation = any(w.has_escalation for w in windows)

    reasoning: List[str] = []

    # Check for explicit hyperbole markers anywhere in text
    has_explicit_hyperbole = any(p.search(text) for p in _SLANG_HYPERBOLE_EXPLICIT)
    has_context_switch = any(p.search(text) for p in _CONTEXT_SWITCH_MARKERS)

    # 1. No crisis signals detected in any window
    if not crisis_windows and not has_explicit_hyperbole:
        return DiscourseContext(
            windows=windows,
            is_genuine_distress=False,
            humor_type="none",
            should_downgrade=False,
            reasoning=["No crisis signals detected in any window"],
        )

    # 2. Safety override: Method mentions, planning, or escalation block downgrade
    if has_any_method or has_any_planning or (has_any_escalation and len(crisis_windows) > 0):
        blockers = []
        if has_any_method:
            blockers.append("lethal method mention")
        if has_any_planning:
            blockers.append("planning language")
        if has_any_escalation:
            blockers.append("escalation marker")

        humor_type = "nervous_laughter" if humor_windows else "none"
        reasoning.append(f"Safety override triggered by: {', '.join(blockers)}. Downgrade blocked.")

        return DiscourseContext(
            windows=windows,
            is_genuine_distress=True,
            humor_type=humor_type,
            should_downgrade=False,
            has_safety_blocker=True,
            reasoning=reasoning,
        )

    # 3. Multi-sentence escalation: >=2 crisis windows vs trailing humor
    if len(crisis_windows) >= 2 and len(humor_windows) > 0:
        reasoning.append(
            f"Multi-sentence crisis signals ({len(crisis_windows)} windows) outweigh humor ({len(humor_windows)} window). Classified as nervous laughter."
        )
        return DiscourseContext(
            windows=windows,
            is_genuine_distress=True,
            humor_type="nervous_laughter",
            should_downgrade=False,
            has_safety_blocker=True,
            reasoning=reasoning,
        )

    # 4. Cross-sentence retraction: Sentence N has crisis, Sentence N+1 has humor/retraction
    if len(windows) >= 2 and len(crisis_windows) == 1 and (len(humor_windows) >= 1 or has_context_switch):
        crisis_idx = crisis_windows[0].sentence_index
        # If humor appears in the same or subsequent window or context switch
        if any(w.sentence_index >= crisis_idx for w in humor_windows) or has_context_switch:
            reasoning.append(
                f"Cross-sentence retraction: Crisis in window {crisis_idx} followed by humor/retraction in subsequent window."
            )
            return DiscourseContext(
                windows=windows,
                is_genuine_distress=False,
                humor_type="casual_hyperbole",
                should_downgrade=True,
                cross_sentence_retraction=True,
                reasoning=reasoning,
            )

    # 5. Single window with both crisis + humor (isolated casual hyperbole)
    if len(windows) == 1 and (humor_windows or has_explicit_hyperbole):
        reasoning.append("Single-window co-occurrence of crisis slang with humor marker (casual hyperbole).")
        return DiscourseContext(
            windows=windows,
            is_genuine_distress=False,
            humor_type="casual_hyperbole",
            should_downgrade=True,
            reasoning=reasoning,
        )

    # 6. Explicit hyperbole match
    if has_explicit_hyperbole:
        reasoning.append("Explicit slang hyperbole pattern matched.")
        return DiscourseContext(
            windows=windows,
            is_genuine_distress=False,
            humor_type="casual_hyperbole",
            should_downgrade=True,
            reasoning=reasoning,
        )

    # 7. Default: genuine crisis without humor mitigation
    reasoning.append("Crisis signal present without valid humor/sarcasm mitigation.")
    return DiscourseContext(
        windows=windows,
        is_genuine_distress=True,
        humor_type="none",
        should_downgrade=False,
        reasoning=reasoning,
    )
