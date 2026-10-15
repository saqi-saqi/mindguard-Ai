"""
threat_actor_detector.py
========================
Actor, Target, and Reporter identification engine for violence and threat statements.

Preserves the critical distinction between:
- Who is making the threat (Actor / Subject)
- Who is at risk (Target / Object)
- Who is reporting it (Speaker / User)

Classification categories:
- REPORTED_THREAT_TO_OTHERS: Third-party threat against another person (e.g. "Atif wants to kill Taimoor")
- THREAT_AGAINST_USER: User reporting a threat against themselves (e.g. "Atif wants to kill me")
- HARM_TO_OTHERS_RISK: Direct potential threat made by the user (e.g. "I want to kill Taimoor")
- SELF_HARM_RISK: User threatening self-harm/suicide (e.g. "I want to kill myself")
- THIRD_PARTY_REPORT: Third-party suicide or self-harm concern (e.g. "my friend wants to commit suicide")
- NONE: Negated, fictional, hyperbolic, or non-threat statements
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Dict, Any


@dataclass
class ThreatActorTargetResult:
    is_threat: bool
    category: str  # "REPORTED_THREAT_TO_OTHERS" | "THREAT_AGAINST_USER" | "HARM_TO_OTHERS_RISK" | "SELF_HARM_RISK" | "THIRD_PARTY_REPORT" | "NONE"
    actor: Optional[str] = None
    target: Optional[str] = None
    is_negated: bool = False
    is_fictional: bool = False
    raw_match: Optional[str] = None
    confidence: float = 0.95


# ---------------------------------------------------------------------------
# Pre-compiled Canonical Regex Patterns
# ---------------------------------------------------------------------------

# 1. Fictional / Creative Writing Context
_FICTIONAL_PATTERNS = [
    re.compile(
        r"\b(?:in\s+my\s+novel|in\s+the\s+novel|in\s+my\s+(?:short\s+)?story|in\s+the\s+story|in\s+my\s+book|"
        r"in\s+the\s+book|in\s+the\s+movie|in\s+the\s+film|in\s+the\s+play|in\s+the\s+script|"
        r"in\s+the\s+screenplay|in\s+the\s+game|in\s+the\s+horror\s+game|in\s+the\s+rpg)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:writing|drafting|reading)\s+(?:a\s+)?(?:novel|book|story|script|screenplay|fanfic|fanfiction)\b", re.IGNORECASE),
    re.compile(r"\b(?:my\s+character|the\s+protagonist|the\s+antagonist|the\s+villain|npc)\b", re.IGNORECASE),
]

# 2. Negated Threat Patterns (Do not escalate solely on negated statements)
_NEGATED_THREAT_PATTERNS = [
    re.compile(
        r"\b(?:does\s+not|doesn'?t|did\s+not|didn'?t|will\s+not|won'?t|would\s+never|do\s+not|don'?t|"
        r"has\s+no\s+intention\s+(?:of|to)|have\s+no\s+intention\s+(?:of|to)|never\s+wanted\s+to|never\s+intended\s+to|"
        r"is\s+not\s+(?:going|trying|planning)\s+to|isn'?t\s+(?:going|trying|planning)\s+to)\s+"
        r"(?:want\s+to\s+)?(?:kill|murder|harm|hurt|shoot|stab|attack|injure|slaughter)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:i\s+would|i'd)\s+never\s+(?:kill|hurt|harm|shoot|stab|murder|injure)\b", re.IGNORECASE),
    re.compile(r"\b(?:nahi|nahin)\s+(?:marna|qatal|jaan\s+se\s+marna)\s+chaht[ai]\b", re.IGNORECASE),
    re.compile(r"\bmarne\s+ka\s+koi\s+irada\s+nah?i\b", re.IGNORECASE),
]

# 3. Inanimate / Metaphorical / Casual Dampeners
_INANIMATE_OR_METAPHOR_PATTERNS = [
    re.compile(
        r"\b(?:this|the|my|that)\s+(?:traffic|exam|exams|test|tests|homework|commute|job|work|boss|meeting|weather|shoes|feet|computer|printer|code|headache)\s+(?:is|are|is\s+going\s+to|will)\s+(?:literally\s+)?(?:killing\s+me|kill\s+me)\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?:traffic|homework|work|exam|finals|shoes|feet)\s+(?:is|are)\s+(?:literally\s+)?killing\s+me\b", re.IGNORECASE),
    re.compile(r"\b(?:dying|died)\s+of\s+(?:laughter|boredom|embarrassment|curiosity)\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:could|can)\s+kill\s+for\s+(?:a\s+)?(?:coffee|drink|beer|pizza|nap|break|vacation|cigarette)\b", re.IGNORECASE),
    re.compile(r"\bkill\s+two\s+birds\s+with\s+one\s+stone\b", re.IGNORECASE),
    re.compile(r"\bdressed\s+to\s+kill\b", re.IGNORECASE),
    re.compile(r"\btime\s+to\s+kill\b", re.IGNORECASE),
    re.compile(r"\b(?:i\s+could\s+kill\s+\w+\s+(?:lol|lmao|haha|jk|j/k))\b", re.IGNORECASE),
]

_CASUAL_JOKE_PATTERNS = [
    re.compile(r"\b(?:lol|lmao|rofl|lmfao|haha+|hehe+|jk|j/k|just\s+kidding)\b", re.IGNORECASE),
]

# 4. Third-Party Suicide or Self-Harm Disclosures (distinct from violence against others)
_THIRD_PARTY_SUICIDE_PATTERNS = [
    re.compile(
        r"\b(?P<actor>my\s+\w+|someone(?:\s+i\s+know|\s+in\s+my\s+\w+)?|a\s+friend|he|she|they|[a-z]+)\s+"
        r"(?:told\s+me\s+(?:that\s+)?(?:he|she|they)?\s*|posted\s+(?:that\s+)?(?:he|she|they)?\s*|says?\s+(?:that\s+)?(?:he|she|they)?\s*)?"
        r"(?:wants?\s+to\s+die|wants?\s+to\s+commit\s+suicide|is\s+suicidal|is\s+going\s+to\s+(?:die|commit\s+suicide|kill\s+(?:himself|herself|themselves))|"
        r"wants?\s+to\s+kill\s+(?:himself|herself|themselves)|talks?\s+about\s+(?:committing\s+suicide|ending\s+(?:his|her|their)\s+life|dying))\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b(?P<actor>someone|she|he|they|[a-z]+)\s+posted\s+that\s+(?:she|he|they)\s+wants?\s+to\s+(?:die|commit\s+suicide)\b", re.IGNORECASE),
]

# 5. First-Person Suicide Statements
_FIRST_PERSON_SUICIDE_PATTERNS = [
    re.compile(r"\b(?:i\s+want\s+to|i\s+wanna|i\s+will|i'm\s+going\s+to|i\s+am\s+going\s+to)\s+(?:die|commit\s+suicide|kill\s+myself|end\s+my\s+life)\b", re.IGNORECASE),
    re.compile(r"\bi\s+(?:want\s+to\s+die|wish\s+i\s+(?:was|were)\s+dead|am\s+suicidal)\b", re.IGNORECASE),
]

# 6. Third-party indirect disclosures ("my friend keeps talking about killing his ex")
_THIRD_PARTY_INDIRECT_PATTERNS = [
    re.compile(
        r"\b(?P<actor>my\s+\w+|someone\s+i\s+know|a\s+person\s+i\s+know|he|she|they|[a-z]+)\s+"
        r"(?:keeps?\s+talking\s+about|talks?\s+about|mentioned|posted\s+(?:about|that|online)|bragged\s+about|said\s+(?:he|she|they)?\s*(?:is|was)?)\s+"
        r"(?:killing|shooting|stabbing|murdering|harming|attacking)\s+"
        r"(?P<target>his\s+\w+|her\s+\w+|their\s+\w+|my\s+\w+|someone|anyone|[a-z]+(?:\s+[a-z]+)?)\b",
        re.IGNORECASE,
    ),
]

# 7. Canonical Subject-Verb-Object Threat Regex
_THREAT_SVO_PATTERN = re.compile(
    r"\b(?:(?P<reporter_prefix>[a-z]+\s+(?:told\s+me|said(?:\s+to\s+me)?)\s+(?:that\s+)?))?"
    r"(?P<actor>i\s+am|i'?m|i\s+will|i'?ll|i\s+plan\s+to|i'?m\s+planning\s+to|i|we|he|she|they|my\s+\w+|his\s+\w+|her\s+\w+|someone|somebody|a\s+guy|a\s+person|[a-z]+)\s+"
    r"(?P<intent>wants?\s+to|wanna|planning\s+to|plans?\s+to|is\s+planning\s+to|am\s+planning\s+to|going\s+to|gonna|is\s+going\s+to|am\s+going\s+to|will|intends?\s+to|is\s+trying\s+to|trying\s+to|threatened?\s+to|is\s+threatening\s+to|threatens?\s+to)\s+"
    r"(?P<verb>kill|murder|slaughter|shoot|stab|choke|strangle|poison|attack|harm|hurt|beat|injure)\s+"
    r"(?P<target>me|myself|himself|herself|themselves|him|her|them|my\s+\w+|his\s+\w+|her\s+\w+|someone|anyone|[a-z]+(?:\s+[a-z]+)?)\b",
    re.IGNORECASE,
)

_DIRECT_THREAT_PATTERN = re.compile(
    r"\b(?P<actor>he|she|they|my\s+\w+|someone|somebody|[a-z]+)\s+"
    r"(?:sent\s+a\s+death\s+threat\s+to|threatened)\s+"
    r"(?!to\b)(?P<target>me|him|her|them|my\s+\w+|someone|anyone|[a-z]+(?:\s+[a-z]+)?)\b",
    re.IGNORECASE,
)

# 8. Roman Urdu Threat Patterns
_URDU_THREAT_PATTERNS = [
    # First-person user threat against target: Main Taimoor ko maar dunga
    re.compile(r"\b(?P<actor>main|mai|hum)\s+(?P<target>[a-z]+|usko|usey|usay|unko)\s+(?:ko\s+)?(?:jaan\s+se\s+)?(?:maar|mar|qatal)\s*(?:dunga|doonga|doon\s*ga|dun\s*ga|marunga|dalun\s*ga)\b", re.IGNORECASE),
    # Actor mujhe marna chahta hai -> threat against user
    re.compile(r"\b(?P<actor>[a-z]+|woh?|us\s+ne)\s+(?:mujhe|humain|humein)\s+(?:jaan\s+se\s+)?(?:maar|mar|qatal)\s*(?:na\s+chahta|dega|dalega|kar\s+dega)\b", re.IGNORECASE),
    # Actor target ko marna chahta hai -> reported threat to others
    re.compile(r"\b(?P<actor>[a-z]+|woh?)\s+(?P<target>[a-z]+|usko|usey|usay|unko)\s+(?:ko\s+)?(?:jaan\s+se\s+)?(?:maar|mar|qatal)\s*(?:na\s+chahta|dega|dalega|kar\s+dega)\b", re.IGNORECASE),
]

_FIRST_PERSON_ACTORS = {"i", "i am", "i'm", "i will", "i'll", "i plan to", "i'm planning to", "we", "main", "mai", "hum"}
_USER_TARGETS = {"me", "myself", "us", "mujhe", "humein", "humain"}
_SELF_TARGETS = {"himself", "herself", "themselves", "khud ko", "apni jaan"}


def analyze_threat_actor_target(text: str) -> ThreatActorTargetResult:
    """
    Analyzes who is making the threat (actor), who is at risk (target),
    and whether the threat is negated or framed fictionally.
    """
    if not text or not text.strip():
        return ThreatActorTargetResult(is_threat=False, category="NONE")

    t = text.strip()

    # 1. Check Fictional Context
    is_fict = any(p.search(t) for p in _FICTIONAL_PATTERNS)
    if is_fict:
        return ThreatActorTargetResult(is_threat=False, category="NONE", is_fictional=True)

    # 2. Check Negation
    is_neg = any(p.search(t) for p in _NEGATED_THREAT_PATTERNS)
    if is_neg:
        return ThreatActorTargetResult(is_threat=False, category="NONE", is_negated=True)

    # 3. Check Inanimate / Metaphorical Wording
    if any(p.search(t) for p in _INANIMATE_OR_METAPHOR_PATTERNS):
        return ThreatActorTargetResult(is_threat=False, category="NONE")

    # 4. Check Casual Joke Dampeners with Kill Idiom
    if any(p.search(t) for p in _CASUAL_JOKE_PATTERNS) and re.search(r"\b(?:could\s+kill|kill\s+\w+)\b", t, re.IGNORECASE):
        return ThreatActorTargetResult(is_threat=False, category="NONE")

    # 5. Check First-Person Suicide Statements
    for fps_pat in _FIRST_PERSON_SUICIDE_PATTERNS:
        fps_m = fps_pat.search(t)
        if fps_m:
            return ThreatActorTargetResult(
                is_threat=True,
                category="SELF_HARM_RISK",
                actor="user",
                target="myself",
                raw_match=fps_m.group(0),
            )

    # 6. Check Third-Party Suicide Statements
    for tps_pat in _THIRD_PARTY_SUICIDE_PATTERNS:
        tps_m = tps_pat.search(t)
        if tps_m:
            d = tps_m.groupdict()
            actor = (d.get("actor") or "friend").strip()
            return ThreatActorTargetResult(
                is_threat=True,
                category="THIRD_PARTY_REPORT",
                actor=actor,
                target="self",
                raw_match=tps_m.group(0),
            )

    # 7. Check Roman Urdu Threat Patterns
    for upat in _URDU_THREAT_PATTERNS:
        um = upat.search(t)
        if um:
            d = um.groupdict()
            actor = d.get("actor", "").strip()
            target = d.get("target", "").strip()
            if actor.lower() in _FIRST_PERSON_ACTORS:
                return ThreatActorTargetResult(
                    is_threat=True,
                    category="HARM_TO_OTHERS_RISK",
                    actor="user",
                    target=target,
                    raw_match=um.group(0),
                )
            elif target in _USER_TARGETS or "mujhe" in t.lower():
                return ThreatActorTargetResult(
                    is_threat=True,
                    category="THREAT_AGAINST_USER",
                    actor=actor,
                    target="me",
                    raw_match=um.group(0),
                )
            else:
                return ThreatActorTargetResult(
                    is_threat=True,
                    category="REPORTED_THREAT_TO_OTHERS",
                    actor=actor,
                    target=target,
                    raw_match=um.group(0),
                )

    # 8. Check Third-Party Indirect Disclosures
    for tppat in _THIRD_PARTY_INDIRECT_PATTERNS:
        tpm = tppat.search(t)
        if tpm:
            d = tpm.groupdict()
            actor = d.get("actor", "").strip()
            target = d.get("target", "").strip()
            return ThreatActorTargetResult(
                is_threat=True,
                category="REPORTED_THREAT_TO_OTHERS",
                actor=actor,
                target=target,
                raw_match=tpm.group(0),
            )

    # 9. Check SVO Threat Pattern
    m = _THREAT_SVO_PATTERN.search(t)
    if m:
        d = m.groupdict()
        raw_actor = (d.get("actor") or "").strip().lower()
        target = (d.get("target") or "").strip().lower()
        reporter = (d.get("reporter_prefix") or "").strip()

        if not raw_actor and reporter:
            raw_actor = reporter.split()[0].lower()

        is_fp_actor = raw_actor in _FIRST_PERSON_ACTORS

        if is_fp_actor:
            if target in _USER_TARGETS:
                return ThreatActorTargetResult(
                    is_threat=True,
                    category="SELF_HARM_RISK",
                    actor=raw_actor,
                    target=target,
                    raw_match=m.group(0),
                )
            else:
                return ThreatActorTargetResult(
                    is_threat=True,
                    category="HARM_TO_OTHERS_RISK",
                    actor="user",
                    target=target,
                    raw_match=m.group(0),
                )
        else:
            actor = raw_actor or "someone"
            if target in _USER_TARGETS:
                return ThreatActorTargetResult(
                    is_threat=True,
                    category="THREAT_AGAINST_USER",
                    actor=actor,
                    target="me",
                    raw_match=m.group(0),
                )
            elif target in _SELF_TARGETS:
                return ThreatActorTargetResult(
                    is_threat=True,
                    category="THIRD_PARTY_REPORT",
                    actor=actor,
                    target=target,
                    raw_match=m.group(0),
                )
            else:
                return ThreatActorTargetResult(
                    is_threat=True,
                    category="REPORTED_THREAT_TO_OTHERS",
                    actor=actor,
                    target=target,
                    raw_match=m.group(0),
                )

    # 10. Check Direct Threat Pattern ("sent a death threat to", "threatened")
    dtm = _DIRECT_THREAT_PATTERN.search(t)
    if dtm:
        d = dtm.groupdict()
        actor = (d.get("actor") or "someone").strip()
        target = (d.get("target") or "target").strip().lower()
        if target in _USER_TARGETS:
            return ThreatActorTargetResult(
                is_threat=True,
                category="THREAT_AGAINST_USER",
                actor=actor,
                target="me",
                raw_match=dtm.group(0),
            )
        else:
            return ThreatActorTargetResult(
                is_threat=True,
                category="REPORTED_THREAT_TO_OTHERS",
                actor=actor,
                target=target,
                raw_match=dtm.group(0),
            )

    return ThreatActorTargetResult(is_threat=False, category="NONE")


# ---------------------------------------------------------------------------
# Emergency Message Builders (Pakistan-verified, Khyber Pakhtunkhwa Police 15 & Rescue 1122)
# ---------------------------------------------------------------------------

def build_reported_threat_safety_message(actor: Optional[str] = None, target: Optional[str] = None) -> str:
    """
    Constructs safety guidance for reported third-party threats.
    Focused on immediate safety assessment, police emergency (15), Rescue 1122, and non-confrontation.
    """
    target_str = target.title() if target else "the other person"
    actor_str = actor.title() if actor else "the person"

    return (
        f"This sounds like a possible threat to another person, and safety is important.\n\n"
        f"Is {target_str} in immediate danger right now?\n"
        f"If you believe {actor_str} may act on this threat, move to a safe place and contact the police emergency helpline at 15. "
        f"Do not confront {actor_str} yourself. If someone is injured or needs urgent medical assistance, call Rescue 1122.\n\n"
        f"If this is something you heard from someone else, share the information with a trusted responsible person or the police "
        f"so the situation can be assessed safely.\n\n"
        f"Emergency Contacts (Pakistan):\n"
        f"• Police Emergency: 15 (primary for immediate threat of violence & protection)\n"
        f"• Rescue Emergency: 1122 (emergency medical assistance & rescue)\n"
        f"• Edhi Ambulance: 115\n\n"
        f"This app cannot contact emergency services automatically — please call 15 or 1122 directly if anyone is in danger."
    )


def build_threat_against_user_safety_message(actor: Optional[str] = None) -> str:
    """
    Constructs safety guidance when the user reports an immediate threat against themselves.
    """
    actor_str = actor.title() if actor else "the person"

    return (
        f"Your safety is the immediate priority. If someone is threatening your life, please take steps to protect yourself right now:\n\n"
        f"1. Move to a safe, secure, or public place immediately and lock doors if possible.\n"
        f"2. Contact the Police Emergency helpline at 15 right now to report the threat and request urgent protection.\n"
        f"3. Do not confront {actor_str} yourself.\n"
        f"4. If you are injured or in need of emergency medical assistance, call Rescue 1122.\n"
        f"5. Reach out to a trusted family member or friend who can stay with you in a safe place.\n\n"
        f"Emergency Services (Pakistan):\n"
        f"• Police Emergency: 15 (threat of violence / immediate protection)\n"
        f"• Rescue Emergency: 1122 (medical assistance & trauma)\n"
        f"• Edhi Ambulance: 115\n\n"
        f"This app cannot contact emergency services automatically — please call 15 or 1122 directly."
    )


REPORTED_THREAT_TO_OTHERS_SAFETY_MESSAGE = build_reported_threat_safety_message()
THREAT_AGAINST_USER_SAFETY_MESSAGE = build_threat_against_user_safety_message()
