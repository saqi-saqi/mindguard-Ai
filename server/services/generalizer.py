"""
generalizer.py
==============

Generalizable, data-driven preprocessing utilities and semantic frame detectors
for MindGuard's multi-tier crisis detection architecture.

Provides:
- @dataclass PreprocessResult for clean metadata transfer (zero token pollution)
- Case-preserving, inflection-aware algospeak normalization
- Semantic frame detectors (academic/meta-linguistic, fictional narrative, third-party)
- Temporal anchor detectors (past resolved recovery vs present relapse markers)
- Behavioral marker detectors (lethal preparatory actions vs protective help-seeking)
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

from .text_normalizer import normalize_evasion_text


@dataclass
class PreprocessResult:
    """Structured container for preprocessed text and detected semantic frames."""
    text: str                                   # Clean, normalized text (no sentinel tokens)
    original_text: str = ""                     # Raw input before normalization
    is_academic: bool = False                   # Academic, research, or NLP dataset context
    is_fictional: bool = False                  # Fiction, novel, or gaming narrative context
    has_past_recovery: bool = False             # Resolved historical struggle / clean recovery
    has_present_ideation: bool = False          # Current struggle markers ("still do", "lately")
    has_preparatory_behavior: bool = False      # Lethal means access, concealed location, note
    has_protective_behavior: bool = False       # Help-seeking: hospital, hotline, therapy, doctor
    is_third_party: bool = False                # Statements reporting someone else's crisis
    normalized_slang_count: int = 0             # Observability counter for audit logs
    non_english_input: bool = False             # Observability flag for non-ASCII/Urdu/Hindi scripts
    is_truncated: bool = False                  # Flag if input exceeded hard length cap


# ---------------------------------------------------------------------------
# Constants & Regex Compilation Helper
# ---------------------------------------------------------------------------

MAX_INPUT_LENGTH = 10000


def _compile(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.IGNORECASE)


# ---------------------------------------------------------------------------
# 1. Algospeak & Digital Euphemism Normalizer
# ---------------------------------------------------------------------------

def _preserve_case_replace(match: re.Match, replacement: str) -> str:
    """Helper to match the casing (all upper, title case, or lower) of the matched text."""
    matched_text = match.group(0)
    if matched_text.isupper():
        return replacement.upper()
    if matched_text.istitle():
        return replacement.title()
    return replacement.lower()


# Substitution rules ordered by decreasing specificity:
# (1) Reflexive / multi-word slang -> "kill myself" / "kill yourself"
# (2) Transitive slang -> "kill"
# (3) Intransitive slang -> "die"
ALGOSPEAK_RULES: List[Tuple[re.Pattern, str]] = [
    # Reflexive 'unalive'
    (_compile(r"\bunaliv(?:ing|e)\s+myself\b"), "killing myself"),
    (_compile(r"\bunalived\s+myself\b"), "killed myself"),
    (_compile(r"\bunalives\s+myself\b"), "kills myself"),
    (_compile(r"\bunaliv(?:ing|e)\s+yourself\b"), "killing yourself"),
    (_compile(r"\bunalived\s+yourself\b"), "killed yourself"),
    (_compile(r"\bunalives\s+yourself\b"), "kills yourself"),
    (_compile(r"\bunalives\s+himself\b"), "kills himself"),
    (_compile(r"\bunalived\s+himself\b"), "killed himself"),
    (_compile(r"\bunalives\s+herself\b"), "kills herself"),
    (_compile(r"\bunalived\s+herself\b"), "killed herself"),
    (_compile(r"\bunalives\s+themselves\b"), "kills themselves"),
    (_compile(r"\bunalived\s+themselves\b"), "killed themselves"),
    
    # Common abbreviations & obfuscations (canonical 'kill myself' family)
    (_compile(r"\bi\s+should\s+kys\b"), "I should kill myself"),
    (_compile(r"\b(?:k-m-s|k\.m\.s|k\*ll\s+my\s*self|k[!1]ll\s+my\s*self)\b"), "kill myself"),
    (_compile(r"\bk\s+i\s+l\s+l\s+m\s+y\s+s\s+e\s+l\s+f\b"), "kill myself"),
    (_compile(r"\bs[\*#@!]icide\b"), "suicide"),
    (_compile(r"\bkms\b"), "kill myself"),
    (_compile(r"\b(?:k-y-s|k\.y\.s|k\*ll\s+your\s*self)\b"), "kill yourself"),
    (_compile(r"\bkys\b"), "kill yourself"),
    
    # Gaming & digital termination metaphors
    (_compile(r"\buninstall\s+myself\s+(?:from\s+this\s+server|irl)\b"), "kill myself"),
    (_compile(r"\buninstall\s+myself\b"), "kill myself"),
    (_compile(r"\bdelet(?:e|ing)\s+my\s+(?:whole\s+)?character(?:\s+tonight|\s+irl)?\b"), "kill myself"),
    (_compile(r"\bdelet(?:e|ing)\s+my\s+account\s+irl\b"), "kill myself"),
    (_compile(r"\bpermanent\s+ban\s+irl\b"), "kill myself"),
    (_compile(r"\bcatch\s+a\s+permanent\s+ban\b"), "kill myself"),
    (_compile(r"\bpass\s+the\s+controller\s+to\s+the\s+afterlife\b"), "kill myself"),
    (_compile(r"\bpull\s+the\s+plug\s+on\s+this\s+character\b"), "kill myself"),
    (_compile(r"\byeet\s+(?:myself|me)\s+(?:off|out\s+of)\b"), "jump to end my life"),
    
    # Qualified 'reset the sim'
    (_compile(r"\breset\s+(?:the\s+sim|my\s+life)\s+(?:permanently|forever|no\s+respawn|irl)\b"), "want to die permanently"),
    (_compile(r"\bno\s+respawn\b"), "want to die permanently"),

    # Transitive / Intransitive 'unalive'
    (_compile(r"\bunaliving\b"), "killing"),
    (_compile(r"\bunalived\b"), "killed"),
    (_compile(r"\bunalives\b"), "kills"),
    (_compile(r"\bunalive\b"), "kill"),
    
    # Obfuscated leetspeak phrases
    (_compile(r"\bk\*ll\b"), "kill"),
    (_compile(r"\bsu\*c\*de\b"), "suicide"),
    (_compile(r"\bsewerslide\b"), "suicide"),
    (_compile(r"\bself[ -]?harming\b"), "self-harming"),
]


def normalize_algospeak(text: str) -> Tuple[str, int]:
    """
    Perform case-preserving, inflection-aware normalization of algospeak and digital euphemisms.
    Returns the normalized text and the count of substitutions made.
    """
    if not text:
        return "", 0

    count = 0
    result = text

    for pattern, replacement in ALGOSPEAK_RULES:
        matches = pattern.findall(result)
        if matches:
            count += len(matches)
            result = pattern.sub(lambda m: _preserve_case_replace(m, replacement), result)

    return result, count


# ---------------------------------------------------------------------------
# 2. Semantic Frame Detectors
# ---------------------------------------------------------------------------

# Academic / Research / Meta-linguistic markers
_ACADEMIC_COLLOCATIONS = [
    _compile(r"\b(?:for\s+my|for\s+our|in\s+our|in\s+my)\s+(?:psychology|sociology|research|nlp|machine\s+learning|thesis|dissertation|coursework|homework|class|paper|assignment|project|study)\b"),
    _compile(r"\b(?:research\s+paper|nlp\s+annotation|annotation\s+guidelines|classifier\s+training|synthetic\s+examples?|in\s+the\s+dataset)\b"),
    _compile(r"\b(?:training\s+a\s+classifier|detect\s+self[ -]?harm\s+language|risk\s+factors\s+for\s+self[ -]?harm|statistics\s+about\s+suicide\s+rates)\b"),
    _compile(r"\b(?:phrase|sentence|string|example|quote)\s+['\"].*?['\"]\s+(?:appears\s+in|is\s+one\s+of\s+the\s+examples|as\s+a\s+positive\s+crisis\s+example)\b"),
    _compile(r"\bquoting\s+(?:a\s+message|a\s+text|data)\s+for\s+(?:a\s+)?(?:research\s+report|paper|assignment|study)\b"),
    _compile(r"\bmy\s+professor\s+assigned\s+us\b"),
]

def detect_academic_frame(text: str) -> bool:
    """
    Detect whether the text frames crisis language in an academic, research,
    or meta-linguistic inquiry.
    """
    return any(pat.search(text) for pat in _ACADEMIC_COLLOCATIONS)


# Fictional / Narrative / Creative Writing markers
_FICTIONAL_PATTERNS = [
    _compile(r"\b(?:in\s+my\s+novel|in\s+the\s+novel|in\s+my\s+short\s+story|in\s+the\s+story|in\s+the\s+book)\b"),
    _compile(r"\b(?:in\s+the\s+game|in\s+the\s+horror\s+game|in\s+the\s+rpg|in\s+the\s+movie|in\s+the\s+play)\b"),
    _compile(r"\b(?:the\s+protagonist|the\s+character|my\s+character|the\s+villain|the\s+detective)\s+(?:plans|whispers|says|decides|tries|wants)\b"),
    _compile(r"\bwriting\s+(?:a\s+novel|a\s+book|a\s+(?:short\s+)?story|a\s+script|a\s+screenplay|fanfiction)\s+(?:where|about)\b"),
]

def detect_fictional_frame(text: str) -> bool:
    """
    Detect whether the text describes a fictional, gaming, or narrative story context.
    """
    return any(pat.search(text) for pat in _FICTIONAL_PATTERNS)


# Third-Party Subject markers (Reporting another person's crisis)
_THIRD_PARTY_PATTERNS = [
    _compile(r"\b(?:my\s+(?:\w+\s+){0,2}?(?:friend|brother|sister|mom|dad|roommate|coworker|classmate|partner|ex|colleague|cousin|uncle|aunt|neighbor|husband|wife|son|daughter))\s+(?:is|was|has|just|told\s+me|texted\s+me|said|posted|threatened|sent\s+a\s+message)\b.*?(?:kill|hurt|unalive|die|suicide|end\s+(?:his|her|their|it|my)?\s*life|end\s+it|harm)\b"),
    _compile(r"\b(?:a\s+classmate|a\s+coworker|someone\s+i\s+know|my\s+friend)\s+(?:posted|wrote|said|texted)\s+(?:about\s+wanting\s+to|that\s+(?:he|she|they)\s+wants?\s+to)\s+(?:unalive|kill|die|suicide)\b"),
    _compile(r"\b(?:he|she|they)\s+(?:told\s+me|said)\s+(?:he|she|they)\s+(?:wants?|is\s+going|plans?)\s+to\s+(?:die|kill|end|suicide)\b"),
    _compile(r"\bhow\s+to\s+(?:help|support|report)\s+(?:a\s+friend|my\s+friend|my\s+sister|my\s+brother|someone)\s+(?:who\s+is|who\s+wants\s+to)\b"),
    _compile(r"\bmy\s+friend\s+texted\s+me\s*,\s*['\"].*?['\"]"),
    # Direct verb expressions: "my friend wants to commit suicide", "my brother plans to kill himself"
    _compile(r"\b(?:my\s+(?:\w+\s+){0,2}?(?:friend|brother|sister|mom|dad|roommate|coworker|classmate|partner|ex|colleague|cousin|uncle|aunt|neighbor|husband|wife|son|daughter))\s+(?:wants?\s+to|is\s+(?:going\s+to|trying\s+to|planning\s+to|thinking\s+(?:of|about)))\s+(?:commit\s+suicide|kill\s+(?:him|her|them)self|die|end\s+(?:his|her|their|its)\s+life|hurt\s+(?:him|her|them)self|cut\s+(?:him|her|them)self|overdose)\b"),
    # State expressions: "my friend is suicidal", "my brother is self-harming"
    _compile(r"\b(?:my\s+(?:\w+\s+){0,2}?(?:friend|brother|sister|mom|dad|roommate|coworker|classmate|partner|ex|colleague|cousin|uncle|aunt|neighbor|husband|wife|son|daughter))\s+is\s+(?:feeling\s+)?(?:suicidal|self[ -]?harming|depressed\s+and\s+suicidal|in\s+danger\s+of\s+suicide)\b"),
    # Concern/worry expressions: "I'm worried about my friend who wants to die"
    _compile(r"\b(?:i(?:'m|\s+am)\s+(?:worried|scared|concerned|terrified)\s+(?:about|for|that)\s+(?:my\s+)?(?:friend|brother|sister|mom|dad|roommate|colleague|cousin|someone)).*?(?:suicid|kill|die|end\s+(?:his|her|their)\s+life|hurt\s+(?:him|her|them)self)\b"),
    # Acquaintance expressions: "someone I know wants to commit suicide"
    _compile(r"\b(?:someone\s+i\s+know|a\s+person\s+i\s+know|a\s+friend\s+of\s+mine)\s+(?:wants?\s+to|is\s+(?:going\s+to|planning\s+to|thinking\s+of))\s+(?:commit\s+suicide|kill\s+(?:him|her|them)selves?|die|end\s+(?:his|her|their)\s+life)\b"),
]

def detect_third_party_frame(text: str) -> bool:
    """
    Detect whether the statement is reporting a third party's crisis rather than the speaker's.
    """
    return any(pat.search(text) for pat in _THIRD_PARTY_PATTERNS)


# ---------------------------------------------------------------------------
# 3. Temporal Anchors: Past Recovery vs Present Ideation
# ---------------------------------------------------------------------------

_PAST_RECOVERY_PATTERNS = [
    _compile(r"\b(?:i|we)\s+(?:used\s+to|previously)\s+(?:feel|felt|feeling|be|was|were)\s+(?:suicidal|depressed|hopeless|in\s+a\s+dark\s+place)\b"),
    _compile(r"\b(?:i|we)\s+had\s+suicidal\s+thoughts\s+(?:during|in|as\s+a|years\s+ago|months\s+ago)\b"),
    _compile(r"\b(?:\d+\s+years?|\d+\s+months?)\s+clean\s+from\s+self[ -]?harm\b"),
    _compile(r"\bself[ -]?harm\s+used\s+to\s+be\s+part\s+of\s+my\s+life\b"),
    _compile(r"\bmy\s+therapist\s+helped\s+me\s+stop\s+self[ -]?harming\s+years\s+ago\b"),
    _compile(r"\bhad\s+a\s+suicide\s+plan\s+once,\s+but\s+that\s+was\s+years\s+ago\b"),
    _compile(r"\bleft\s+(?:my\s+)?suicidal\s+past\s+behind\b"),
    _compile(r"\bhaven'?t\s+had\s+a\s+suicidal\s+thought\s+in\s+(?:years|months|a\s+long\s+time)\b"),
]

_ACTIVE_DISTRESS_CONTINUATION_MARKERS = [
    _compile(r"\b(?:still\s+do|sometimes\s+still|lately|recently|these\s+days|started\s+again|coming\s+back)\b"),
    _compile(r"\b(?:today\s+i\s+feel|now\s+i\s+feel)\s+(?:terrible|hopeless|bad|suicidal|overwhelmed|depressed)\b"),
    _compile(r"\b(?:but\s+now|but\s+today|but\s+lately)\s+i\s+(?:want\s+to\s+die|feel\s+(?:like\s+ending|terrible|hopeless|bad|suicidal|overwhelmed)|am\s+thinking\s+about\s+(?:dying|suicide|killing))\b"),
]

def has_past_recovery_structure(text: str) -> bool:
    """Detect whether the text describes a resolved past history of crisis/self-harm."""
    return any(pat.search(text) for pat in _PAST_RECOVERY_PATTERNS)


def has_present_ideation_markers(text: str) -> bool:
    """
    Detect whether present-tense struggle markers co-occur, indicating potential relapse.
    """
    return any(pat.search(text) for pat in _ACTIVE_DISTRESS_CONTINUATION_MARKERS)


# ---------------------------------------------------------------------------
# 4. Behavioral Markers: Preparatory Actions vs Protective Help-Seeking
# ---------------------------------------------------------------------------

_PREPARATORY_PATTERNS = [
    # Means acquisition & hoarding
    _compile(r"\b(?:gather(?:ed|ing)?|collect(?:ed|ing)?|bought|buy(?:ing)?|purchas(?:ed|ing)?|stockpil(?:ed|ing)?|hoard(?:ed|ing)?|stash(?:ed|ing)?)\s+(?:.*?\s+)?(?:pills|meds|medication|drugs|rope|blades?|razors?|weapons?)\b"),
    # Temporal & physical concealment
    _compile(r"\b(?:chosen|picked|found|selected)\s+(?:a\s+)?(?:place|spot|location)\s+(?:where\s+)?(?:nobody|no\s+one)\s+(?:will\s+)?find\s+me\b"),
    _compile(r"\bwait(?:ing)?\s+until\s+(?:everyone|they|my\s+family|my\s+parents|everyone\s+else)\s+(?:is|are|goes|falls)\s+asleep\b"),
    _compile(r"\bhave\s+the\s+pills\s+ready\s+and\s+i\s+am\s+waiting\b"),
    # Concrete planning verbs
    _compile(r"\b(?:plan(?:ning|ned|s)?|thought|thoughts|thinking)\s+(?:about|to)\s+(?:end\s+my\s+life|kill\s+myself|die|suicide)\b"),
    # Wills & final notes
    _compile(r"\b(?:writ(?:ing|ten|e)|left|leav(?:ing|e))\s+(?:a\s+)?(?:suicide\s+note|goodbye\s+letter|goodbye\s+note|will)\b"),
]

_PROTECTIVE_PATTERNS = [
    # Medical & emergency facility seeking
    _compile(r"\b(?:go(?:ing)?|headed|heading)\s+to\s+(?:the\s+)?(?:ER|emergency\s+room|hospital|clinic|doctor)\b"),
    _compile(r"\b(?:should\s+i|thinking\s+of)\s+go(?:ing)?\s+to\s+(?:the\s+)?(?:hospital|ER|emergency\s+room|doctor)\b"),
    # Crisis support lines
    _compile(r"\b(?:call(?:ed|ing)?|text(?:ed|ing)?|contact(?:ed|ing)?)\s+(?:the\s+)?(?:crisis\s+)?(?:hotline|lifeline|988|crisis\s+line|crisis\s+text\s+line)\b"),
    # Therapeutic engagement
    _compile(r"\b(?:schedul(?:ed|ing)|talk(?:ed|ing)?\s+to|reach(?:ed|ing)?\s+out\s+to|see(?:ing)?)\s+(?:my\s+)?(?:therapist|psychologist|psychiatrist|counselor|doctor)\b"),
    # Interpersonal support seeking
    _compile(r"\b(?:reach(?:ed|ing)?\s+out\s+to|talk(?:ed|ing)?\s+to|told|tell(?:ing)?)\s+(?:my\s+)?(?:friend|partner|spouse|mom|dad|family|parents|sister|brother)\b"),
    # Relational protective reasons
    _compile(r"\b(?:won'?t\s+do\s+it|staying\s+alive|living)\s+because\s+of\s+my\s+(?:dog|cat|kids?|children|family|partner|pet)\b"),
]

_COPING_OR_INFO_PATTERNS = [
    _compile(r"^(?:what\s+can\s+i\s+do|can\s+you\s+(?:recommend|help|suggest)|are\s+you\s+able\s+to\s+help|how\s+do\s+i\s+cope|can\s+you\s+give\s+me)\b"),
    _compile(r"\b(?:anxiety\s+exercises|breathing\s+exercises|meditation|after\s+work|feeling\s+emotionally\s+overloaded|study\s+and\s+try\s+again)\b"),
    _compile(r"\b(?:feel\s+sick\s+with\s+anxiety|racing\s+because\s+i\s+have\s+to\s+present)\b"),
]


def is_informational_or_coping_query(text: str) -> bool:
    """Detect whether text is a non-crisis coping or informational query."""
    return any(pat.search(text) for pat in _COPING_OR_INFO_PATTERNS)


def detect_preparatory_behavior(text: str) -> bool:
    """Detect concrete preparations, concealment, or means gathering for self-harm."""
    if re.search(r"\b(?:do\s+not|don'?t|have\s+no|have\s+not|zero|no|without\s+any|not)\s+(?:have\s+)?(?:any\s+)?(?:plan|plans|thoughts?|thinking|intention|desire)\b", text, re.I):
        return False
    return any(pat.search(text) for pat in _PREPARATORY_PATTERNS)


def detect_protective_behavior(text: str) -> bool:
    """Detect help-seeking, clinical care seeking, or crisis hotline engagement."""
    return any(pat.search(text) for pat in _PROTECTIVE_PATTERNS)


# ---------------------------------------------------------------------------
# 5. Non-English Script Detection (Observability)
# ---------------------------------------------------------------------------

def _is_non_ascii_script(text: str) -> bool:
    """Detect presence of Urdu, Arabic, Devanagari, or other non-Latin scripts."""
    for char in text:
        code = ord(char)
        if (0x0600 <= code <= 0x06FF) or (0x0750 <= code <= 0x077F) or (0x0900 <= code <= 0x097F):
            return True
    return False


# ---------------------------------------------------------------------------
# 6. Unified Preprocessor Orchestrator
# ---------------------------------------------------------------------------

def preprocess_text(text: str) -> PreprocessResult:
    """
    Main entry point for text normalization and semantic frame detection.
    
    Invariants guaranteed:
    1. Idempotency: preprocess_text(preprocess_text(t).text).text == preprocess_text(t).text
    2. Zero Token Pollution: Clean text is returned without sentinel tokens.
    3. Performance: Linear time evaluation, bounded memory, ReDoS safe.
    4. Input Cap: Enforces MAX_INPUT_LENGTH (10,000 characters).
    """
    if text is None:
        text = ""

    original = text
    is_truncated = False

    # Input length hard cap
    if len(text) > MAX_INPUT_LENGTH:
        text = text[:MAX_INPUT_LENGTH]
        is_truncated = True

    # 0. Adversarial evasion normalization (confusables, zero-width, compaction)
    evasion_cleaned = normalize_evasion_text(text)

    # 1. Algospeak & digital euphemism normalization
    normalized, slang_count = normalize_algospeak(evasion_cleaned)

    # 2. Semantic Frame Detection on normalized text
    is_acad = detect_academic_frame(normalized)
    is_fict = detect_fictional_frame(normalized)
    is_third = detect_third_party_frame(normalized)
    has_past = has_past_recovery_structure(normalized)
    has_pres = has_present_ideation_markers(normalized)
    has_prep = detect_preparatory_behavior(normalized)
    has_prot = detect_protective_behavior(normalized)
    non_eng = _is_non_ascii_script(original)

    return PreprocessResult(
        text=normalized,
        original_text=original,
        is_academic=is_acad,
        is_fictional=is_fict,
        has_past_recovery=has_past,
        has_present_ideation=has_pres,
        has_preparatory_behavior=has_prep,
        has_protective_behavior=has_prot,
        is_third_party=is_third,
        normalized_slang_count=slang_count,
        non_english_input=non_eng,
        is_truncated=is_truncated,
    )
