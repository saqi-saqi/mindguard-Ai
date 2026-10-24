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
    THREAT_AGAINST_USER = "THREAT_AGAINST_USER"
    HARM_TO_OTHERS_RISK = "HARM_TO_OTHERS_RISK"
    SELF_HARM_RISK = "SELF_HARM_RISK"
    REPORTED_THREAT_TO_OTHERS = "REPORTED_THREAT_TO_OTHERS"
    THIRD_PARTY_REPORT = "THIRD_PARTY_REPORT"
    EMOTIONAL_DISTRESS = "EMOTIONAL_DISTRESS"
    NONE = "NONE"


try:
    from services.threat_actor_detector import (
        analyze_threat_actor_target,
        ThreatActorTargetResult,
        REPORTED_THREAT_TO_OTHERS_SAFETY_MESSAGE,
        THREAT_AGAINST_USER_SAFETY_MESSAGE,
        build_reported_threat_safety_message,
        build_threat_against_user_safety_message,
    )
except ImportError:
    from .threat_actor_detector import (
        analyze_threat_actor_target,
        ThreatActorTargetResult,
        REPORTED_THREAT_TO_OTHERS_SAFETY_MESSAGE,
        THREAT_AGAINST_USER_SAFETY_MESSAGE,
        build_reported_threat_safety_message,
        build_threat_against_user_safety_message,
    )


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
    t = re.sub(r"[\u2018\u2019\u201A\u201B\u2032]", "'", text)
    t = re.sub(r"[\u201C\u201D\u201E\u201F]", '"', t)
    t = t.lower()
    t = re.sub(r"\bsu[1!i]c[1!i]d", "suicid", t)
    t = re.sub(r"\bk[!1i]ll\b", "kill", t)
    t = re.sub(r"\bd[1!i]e\b", "die", t)
    t = " ".join(t.split())
    return t


# 1. Hyperbolic / Casual Dampeners (indicates NOT a credible threat)
_CASUAL_JOKE_DAMPENERS = [
    _c(r"\b(?:lol|lmao|rofl|lmfao|haha+|hehe+|jk|j/k|just\s+kidding|only\s+kidding|sarcasm)\b"),
]

_INANIMATE_OR_METAPHOR_SUBJECTS = [
    _c(r"\b(?:this|the|my|that)\s+(?:traffic|exam|exams|test|tests|homework|commute|job|work|boss|meeting|weather|shoes|feet|computer|printer|code|headache)\s+(?:is|are|is\s+going\s+to|will)\s+(?:literally\s+)?(?:killing\s+me|kill\s+me)\b"),
    _c(r"\b(?:traffic|homework|work|exam|finals|shoes|feet)\s+(?:is|are|is\s+going\s+to|will)\s+(?:literally\s+)?(?:killing\s+me|kill\s+me)\b"),
    _c(r"\b(?:dying|died)\s+of\s+(?:laughter|boredom|embarrassment|curiosity)\b"),
    _c(r"\bi\s+(?:could|can)\s+kill\s+for\s+(?:a\s+)?(?:coffee|drink|beer|pizza|nap|break|vacation|cigarette|burger|food)\b"),
    _c(r"\bkill\s+two\s+birds\s+with\s+one\s+stone\b"),
    _c(r"\bdressed\s+to\s+kill\b"),
    _c(r"\b(?:need\s+to|have\s+to|want\s+to|trying\s+to|just)?\s*kill(?:ing)?\s+time\b"),
    _c(r"\b(?:kill|terminate|stop)\s+(?:the\s+)?(?:python|process|server|daemon|container|job|task|pid|session|service|thread|app|application|script|query|connection)\b"),
    _c(r"\bkill\s+-[0-9]+\b"),
    _c(r"\b(?:in\s+chess|chess|kill\s+the\s+king's\s+defense|kill\s+the\s+defense)\b"),
    _c(r"\bkill\s+the\s+(?:old\s+)?(?:browser\s+)?session\b"),
    _c(r"\b(?:killer\s+song|killer\s+performance)\b"),
    _c(r"\bcooking\s+could\s+kill\b"),
    _c(r"\b(?:my\s+)?(?:mom|dad|parents|mother|father|teacher|boss|wife|husband)\s+will\s+(?:literally\s+)?kill\s+me\s+if\b"),
    _c(r"\b(?:the\s+song\s+says|lyrics\s+(?:say|are)|texted\s*['\"].*?['\"]\s+and\s+then\s+laughed)\b"),
    _c(r"\b(?:psychology\s+assignment|assignment\s+is\s+about|homework\s+is\s+about|research\s+is\s+about)\b"),
]

_HARM_OTHERS_NEGATIONS = [
    _c(r"\b(?:i\s+would|i'd)\s+never\s+(?:kill|hurt|harm|shoot|stab)\s+(?:anyone|anybody|someone|him|her|them)\b"),
    _c(r"\bi\s+(?:do\s+not|don'?t)\s+want\s+to\s+(?:kill|hurt|harm)\s+(?:anyone|anybody|him|her|them)\b"),
    _c(r"\bno\s+intention\s+of\s+(?:hurting|killing|harming)\s+(?:anyone|him|her|them)\b"),
    _c(r"\b(?:[a-z]+\s+)?(?:does\s+not|doesn'?t|did\s+not|didn'?t|will\s+not|won'?t|would\s+never)\s+(?:want\s+to\s+)?(?:kill|murder|harm|hurt|shoot|stab|attack)\b"),
    _c(r"\b(?:clean\s+from\s+self[\s-]?harm|used\s+to\s+(?:want\s+to\s+)?(?:die|kill\s+myself|cut)|doing\s+much\s+better\s+now|therapy\s+(?:really\s+)?helped)\b"),
    _c(r"\b(?:don'?t|do\s+not)\s+want\s+to\s+die,?\s*(?:i\s+)?just\s+want\s+to\s+sleep\b"),
]

_TRIVIAL_BENIGN_PATTERNS = [
    _c(r"^(?:hi|hello|hey|good\s+(?:morning|afternoon|evening)|howdy|sup|greetings|yo)\b[!?.]*$"),
    _c(r"^(?:ok|okay|thanks|thank\s+you|cool|got\s+it|sure|yes|no|yep|nope|bye|goodbye)\b[!?.]*$"),
    _c(r"^(?:hello|hi|hey)\s+(?:again|there|bot|mindguard)\b[!?.]*$"),
]

# 2. Harm-To-Others / Homicide Patterns (Direct Threats & Specific Methods)
_HARM_TO_OTHERS_PATTERNS = [
    # Direct intent to kill/murder/harm/attack/assault/injure someone (generic or specific)
    _c(r"\b(?:i'?m\s+gonna|i\s+am\s+going\s+to|i\s+will|i'll|i\s+plan\s+to|i'?m\s+planning\s+to|i\s+want\s+to|wanna|intend\s+to|planning\s+to|plan\s+to|gonna|urge\s+to|feel\s+like|need\s+to)\s+(?:gonna\s+)?(?:severely\s+|seriously\s+)?(?:harm|hurt|beat|attack|assault|injure|kill|murder|slaughter|shoot|stab|slit|choke|strangle|poison|assassinate|execute)\s+(?:my\s+|the\s+|this\s+|that\s+)?(?:neighbour|neighbor|friend|boss|coworker|ex|wife|husband|mother|father|brother|sister|roommate|teacher|landlord|doctor|cousin|uncle|aunt|partner|girlfriend|boyfriend|son|daughter|kid|child|people|person|someone|anyone|anybody|somebody|everyone|everybody|them|him|her|bitch|bastard|(?!myself\b|me\b)[a-z]+)\b"),
    _c(r"\b(?:gonna|going\s+to|will|i'll)\s+(?:kill|murder|shoot|stab|slaughter|poison|attack|harm|hurt|beat|assault|injure)\s+(?:him|her|them|my\s+\w+|someone|anyone|anybody|somebody|people|everybody|(?!myself\b|me\b)[a-z]+)\b"),
    _c(r"\b(?:i'?m\s+going\s+to|i'?m\s+gonna|i\s+will|i'll)\s+(?:poison|attack|assault|beat)\s+(?:him|her|them|someone|anyone|people|everyone|(?!myself\b|me\b)[a-z]+)\b"),
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
    _c(r"\b(?:have|got)\s+(?:a\s+)?knife\s+and\s+.*?\bwaiting\s+outside\b"),
    _c(r"\bmake\s+(?:my\s+\w+|[a-z]+)\s+pay\s+with\s+(?:his|her|their)\s+life\b"),
    _c(r"\bfantasiz(?:e|ing)\s+about\s+killing\b"),
    _c(r"\btake\s+(?:him|her|them|[a-z]+)\s+down\s+with\s+me\b"),
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
    _c(r"\b(?:i\s+(?:am|feel|am\s+feeling)|i'?m|feeling)\s+(?:going\s+to\s+|gonna\s+)?(?:actively\s+)?(?:suicidal|kill\s+myself|overdose|hang\s+myself|jump\s+off\s+a\s+bridge)\b"),
    _c(r"\boverdos(?:e|ing|ed)\s+on\s+(?:my\s+|the\s+|all\s+my\s+)?(?:pills|meds|medication|painkillers)\b"),
    _c(r"\b(?:going\s+to|gonna|will|plan\s+to)\s+overdose\b"),
    _c(r"\b(?:actively\s+suicidal|feeling\s+actively\s+suicidal)\b"),
    _c(r"\b(?:i'?ve\s+decided\s+to|decided\s+to|going\s+to)\s+end\s+it\s+all(?:\s+tonight)?\b"),
    _c(r"\bend\s+it\s+all\s+(?:tonight|today|now)\b"),
    _c(r"\b(?:have|got|made)\s+(?:a\s+)?(?:suicide\s+plan|plan\s+to\s+(?:die|kill\s+myself))\b"),
    _c(r"\bsuicide\s+plan\b"),
    _c(r"\b(?:took|swallowed|downed|ingested)\s+(?:a\s+whole\s+bottle|all\s+my|too\s+many)\s+(?:pills|tablets|medication|painkillers)\b"),
    _c(r"\b(?:have|got|holding|bought|saved|stashed)\s+(?:(?:a|the|my|these|this)\s+)?(?:(?:whole|full|entire)\s+)?(?:bottle\s+of\s+|stash\s+of\s+|handful\s+of\s+)?(?:sleeping\s+)?(?:pills|meds|medication|tablets|capsules|painkillers)\b.*?\b(?:going\s+to|gonna|will|plan\s+to|planning\s+to|about\s+to|intend\s+to|i'?m\s+taking|taking)\s+(?:take|taking|swallow|down|ingest|overdose\s+on|them|it|all)\b"),
    _c(r"\b(?:saved|saving)\s+up\s+all\s+my\s+pills\s+and\s+.*?\btaking\s+them\b"),
    _c(r"\bending\s+it\s+(?:today|tonight|now|all)\b"),
    _c(r"\bnobody\s+will\s+miss\s+me\b"),
    _c(r"\bdoing\s+it\s+(?:tonight|today)\b"),
    _c(r"\bdecided\s+to\s+die\b"),
    _c(r"\bdone\s+living\b"),
    _c(r"\b(?:wrote|written|writing)\s+(?:my\s+)?goodbye\s+letters?\b"),
    _c(r"\btonight\s+is\s+the\s+night\b"),
    _c(r"\b(?:don'?t|do\s+not)\s+want\s+to\s+be\s+alive\b"),
    _c(r"\bwhat'?s\s+(?:even\s+)?(?:the\s+)?point\s+of\s+(?:living|being\s+alive)\b"),
    _c(r"\blife\s+isn'?t\s+worth\s+it(?:\s+anymore)?\b"),
    _c(r"\b(?:keep\s+)?thinking\s+about\s+dying\b"),
    _c(r"\b(?:happy|glad|wish)\s+if\s+i\s+got\s+hit\s+by\s+(?:a\s+)?(?:bus|truck|car|train)\b"),
    _c(r"\bburn\s+(?:my\s+)?arms?\b"),
    _c(r"\bhit\s+myself\s+until\s+(?:i\s+)?bruise\b"),
    _c(r"\bhow\s+many\s+.*?\b(?:tablets?|pills?|mg|grams?)\s+.*?\b(?:lethal|fatal|overdose|kill|die)\b"),
    _c(r"\b(?:what|which)\s+(?:is\s+)?(?:the\s+)?(?:painless|quickest|easiest)\s+way\s+to\s+die\b"),
    _c(r"\bwhich\s+(?:medicine|drug|pill|poison)\s+can\s+kill\b"),
    _c(r"\bhow\s+tall\s+does\s+a\s+building\s+need\s+to\s+be\s+to\s+die\b"),
    _c(r"\b(?:cut|cutting|harm|harming)\s+myself\b"),
    _c(r"\b(?:kms|kys|unalive\s+myself)\b"),
    _c(r"\bnext\s+on\s+my\s+killing\s+list\s+is\s+me\b"),
    _c(r"\bkill\s+myself\s+(?:too|after|next)\b"),
    # Roman Urdu self harm
    _c(r"\b(?:mujhe\s+mar\s+ja+na\s+hai|main\s+khudkushi\s+karna\s+chaht[ai]\s+hoon|apni\s+jaan\s+lena\s+chaht[ai]\s+hoon)\b"),
    _c(r"\b(?:bhai\s+)?(?:i\s+swear\s+)?(?:mujhe\s+)?jee+na\s+(?:hi\s+)?nah?i\s+hai\b"),
    _c(r"\b(?:suicide|death|dying|killing\s+myself)\s+is\s+(?:my\s+|the\s+)?(?:only\s+)?(?:way\s+out|option|choice|answer|plan)\b"),
    _c(r"\b(?:ab\s+)?aur\s+nah?i\s+jee\s+sakt[ai]\b"),
    _c(r"\bkhud\s*kush[eií]+\s*(?:kar|karn[ei]|kr)\s*(?:lun\s*ga|lunga|chaht[ai]|raha|rahi|dunga|karunga)\b"),
    _c(r"\b(?:mein|main)\s+khud\s*kush[eií]+\b"),
    _c(r"\b(?:apni\s+)?zindagi\s+khatam\s+kar\b"),
    _c(r"\bsab\s+khatam\s+kar\s*(?:dunga|doon\s*ga|dun\s*ga)\b"),
    _c(r"\bmeri\s+maut\s+(?:hi\s+)?behtar\b"),
    _c(r"\bmere\s+bina\s+(?:sab\s+)?khush\b"),
    _c(r"\bmain\s+mar\s+jao+n\b"),
    _c(r"\b(?:main\s+)?(?:apni\s+)?jaan\s+(?:de|le)\s*(?:dunga|doonga|doon\s*ga|dun\s*ga|lun\s*ga|lunga|loon\s*ga|loonga)\b"),
    _c(r"\bkaash\s+(?:mein\s+)?subah\s+uthon\s+hi\s+na\b"),
    _c(r"\bkitni\s+goliyan?\s+(?:khane\s+se\s+)?.*?\bmar\s+jata\s+hai\b"),
    _c(r"\bsuicide\s+karna\s+hai\b"),
    _c(r"\bmai\s+khudkashi\s+kr\s+lunga\b"),
    # Passive death wishes and non-waking euphemisms
    _c(r"\b(?:fall|falling|go|going)\s+asleep\s+and\s+(?:never|not)\s+(?:have\s+to\s+)?(?:wake|get)\s+up\b"),
    _c(r"\b(?:fall\s+asleep\s+and\s+not\s+come\s+back|fall\s+asleep\s+and\s+never\s+wake)\b"),
    _c(r"\b(?:wish\s+(?:i\s+)?(?:could\s+just\s+|would\s+just\s+)?|hope\s+(?:i\s+)?)(?:never|not|don'?t|wouldn'?t)\s+wake\s+up(?:\s+tomorrow|\s+again|\s+anymore)?\b"),
    _c(r"\b(?:don'?t|do\s+not)\s+want\s+to\s+wake\s+up\s+anymore\b"),
    _c(r"\b(?:close|shut)\s+my\s+eyes\s+and\s+(?:never|not)\s+(?:open\s+them\s+(?:again|anymore)|wake\s+up)\b"),
    _c(r"\bdidn'?t\s+open\s+my\s+eyes\s+tomorrow\b"),
    _c(r"\b(?:logging\s+off|checking\s+out)\s+(?:forever|permanently|of\s+life)\b"),
    _c(r"\bpermanently\s+log\s+off\b"),
]

# 4. Third-Party Crisis / Threat Disclosure Patterns
_THIRD_PARTY_PATTERNS = [
    _c(r"\b(?:my\s+|a\s+)?(?:friend|roommate|brother|sister|cousin|ex|coworker|colleague|classmate|partner|neighbour|neighbor|someone|somebody|he|she|they)(?:\s+in\s+my\s+\w+)?\b.{0,60}?\b(?:talks?|talking|said|says?|told\s+me|threaten(?:ed|ing)?|planning|plans?|posted|going|wants?|left|wrote)\b.{0,60}?\b(?:kill(?:ing)?|murder(?:ing)?|shoot(?:ing)?|stab(?:bing)?|hurt(?:ing)?|harm(?:ing)?|die|suicid|end\s+(?:his|her|their)\s+life|commit\s+suicide|suicide\s+note)\b"),
    _c(r"\b(?:my\s+friend|my\s+brother|my\s+sister|my\s+roommate|someone\s+i\s+know|someone\s+in\s+my\s+\w+)\s+(?:wants\s+to\s+die|is\s+suicidal|wants\s+to\s+kill|is\s+threatening\s+to\s+kill|wants\s+to\s+commit\s+suicide)\b"),
    _c(r"\b(?:someone|she|he|they)\s+posted\s+that\s+(?:she|he|they)\s+(?:wants?\s+to|is\s+going\s+to)\s+(?:die|commit\s+suicide|kill)\b"),
    _c(r"\b(?:left\s+a\s+(?:suicide\s+)?note|roommate\s+left\s+a\s+note)\b"),
]

# 5. Emotional Distress Signals
_DISTRESS_SIGNALS = [
    _c(r"\b(?:depressed|overwhelmed|hopeless|anxious|panic|panicking|crying|heartbroken|angry|furious|desperate|scared|terrified|can't\s+cope|exhausted|wanted\s+to\s+kill\s+myself\s+earlier|shaky)\b"),
    _c(r"\b(?:blackmail(?:ing)?|touches\s+me|being\s+followed|feel\s+unsafe|beats\s+me|sasural\s+wale\s+mujhe\s+maarte\s+hain|abused|harassed)\b"),
    _c(r"\b(?:haven't\s+eaten|throw\s+up\s+after\s+every\s+meal|drinking\s+every\s+night\s+to\s+forget|way\s+too\s+many\s+(?:sleeping\s+)?pills|overdosed)\b"),
    _c(r"\b(?:i\s+)?(?:just\s+)?want\s+(?:the\s+)?pain\s+to\s+stop\b"),
    # A bare first-person finality statement is ambiguous, not confirmed
    # crisis. Route it to the gentle elevated-distress check-in rather than
    # silently treating it as ordinary chat.
    _c(r"\bi(?:'m|\s+am)\s+done\s*[.!?]*$"),
    _c(r"\b(?:it'll\s+all\s+be\s+over\s+soon|remember\s+me\s+kindly|bas\s+ab\s+khatam)\b"),
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
        "COMBINED_HIGH_CRISIS": 7,
        "THREAT_AGAINST_USER": 6,
        "HARM_TO_OTHERS_RISK": 5,
        "HIGH_CRISIS": 4,
        "SELF_HARM_RISK": 4,
        "REPORTED_THREAT_TO_OTHERS": 3,
        "THIRD_PARTY_REPORT": 2,
        "EMOTIONAL_DISTRESS": 1,
        "NONE": 0,
    }.get(risk_level, 0)


def _category_from_risk_level(risk_level: str) -> SafetyRiskCategory:
    """Map risk level string to SafetyRiskCategory enum."""
    return {
        "COMBINED_HIGH_CRISIS": SafetyRiskCategory.COMBINED_HIGH_CRISIS,
        "THREAT_AGAINST_USER": SafetyRiskCategory.THREAT_AGAINST_USER,
        "HARM_TO_OTHERS_RISK": SafetyRiskCategory.HARM_TO_OTHERS_RISK,
        "HIGH_CRISIS": SafetyRiskCategory.SELF_HARM_RISK,  # HIGH_CRISIS maps to SELF_HARM_RISK for API compat
        "SELF_HARM_RISK": SafetyRiskCategory.SELF_HARM_RISK,
        "REPORTED_THREAT_TO_OTHERS": SafetyRiskCategory.REPORTED_THREAT_TO_OTHERS,
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
    try:
        from config import USE_UNIFIED_CRISIS_PIPELINE
    except ImportError:
        import os
        USE_UNIFIED_CRISIS_PIPELINE = os.environ.get("USE_UNIFIED_CRISIS_PIPELINE", "true").lower() in ("true", "1", "yes")

    if USE_UNIFIED_CRISIS_PIPELINE:
        try:
            from services.unified_safety_pipeline import evaluate_unified_tier1_safety
        except ImportError:
            from .unified_safety_pipeline import evaluate_unified_tier1_safety
        unified_res = evaluate_unified_tier1_safety(
            text,
            session_id=session_id,
            context_turns=context_turns,
            user_api_key=api_key,
        )
        return SafetyClassificationResult(
            category=unified_res.category,
            confidence=unified_res.confidence,
            matched_signals=unified_res.matched_signals,
            is_crisis=unified_res.is_crisis,
            requires_immediate_action=unified_res.requires_immediate_action,
            safety_message=unified_res.safety_message,
            reasoning=unified_res.reasoning,
        )

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

    # Actor, Target, and Reporter analysis
    actor_target_res = analyze_threat_actor_target(text)

    # Step A: Check for Hyperbole / Idiom / Casual Joke Dampeners & Framing
    has_casual_dampener = any(pat.search(norm) for pat in _CASUAL_JOKE_DAMPENERS)
    has_inanimate_subject = any(pat.search(norm) for pat in _INANIMATE_OR_METAPHOR_SUBJECTS)
    has_others_negation = (
        (any(pat.search(norm) for pat in _HARM_OTHERS_NEGATIONS) and not (actor_target_res.is_threat and not actor_target_res.is_negated))
        or actor_target_res.is_negated
    )
    is_fictional = actor_target_res.is_fictional

    # Step B: Deterministic Harm-to-Others matching
    harm_to_others_matches = []
    if not has_inanimate_subject and not has_others_negation and not is_fictional:
        if actor_target_res.is_threat and actor_target_res.category == "HARM_TO_OTHERS_RISK":
            harm_to_others_matches.append(actor_target_res.raw_match or "direct_threat_to_others")
        # Only check generic _HARM_TO_OTHERS_PATTERNS if actor_target did not identify a third-party threat or threat against user
        if not (actor_target_res.is_threat and actor_target_res.category in ("REPORTED_THREAT_TO_OTHERS", "THREAT_AGAINST_USER")):
            for pat in _HARM_TO_OTHERS_PATTERNS:
                m = pat.search(norm)
                if m:
                    harm_to_others_matches.append(m.group(0))

    if has_casual_dampener and harm_to_others_matches:
        is_explicit_live_threat = (
            (actor_target_res.is_threat and actor_target_res.category == "HARM_TO_OTHERS_RISK")
            or bool(re.search(r"\b(?:tonight|today|tomorrow|now|after\s+work|right\s+now)\b", norm))
            or bool(re.search(r"\b(?:gun|knife|pistol|rifle|blade|weapon|shoot|stab|slit)\b", norm))
            or bool(re.search(r"\b(?:i\s+will|i'll|i\s+am\s+going\s+to|i'?m\s+gonna|brought|bring|plan\s+to)\s+(?:kill|murder|shoot|stab)\b", norm))
        )
        if not is_explicit_live_threat:
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

    if not is_negated and not is_fictional:
        if actor_target_res.is_threat and actor_target_res.category == "SELF_HARM_RISK":
            self_harm_matches.append(actor_target_res.raw_match or "direct_self_harm")
        if not (actor_target_res.is_threat and actor_target_res.category in ("REPORTED_THREAT_TO_OTHERS", "THIRD_PARTY_REPORT")):
            for pat in _SELF_HARM_PATTERNS:
                m = pat.search(norm)
                if m:
                    self_harm_matches.append(m.group(0))

        # Also check Tier-1 deterministic crisis engine
        try:
            from services.crisis_rules import evaluate_crisis
            det_res = evaluate_crisis(text)
            if det_res.get("is_crisis"):
                matched_cats = det_res.get("matched_categories", [])
                tier1_self_harm_cats = [c for c in matched_cats if c != "direct_threat_to_others"]
                tier1_others_cats = [c for c in matched_cats if c == "direct_threat_to_others"]
                if tier1_others_cats and not harm_to_others_matches:
                    if not (actor_target_res.is_threat and actor_target_res.category in ("REPORTED_THREAT_TO_OTHERS", "THREAT_AGAINST_USER", "THIRD_PARTY_REPORT")):
                        harm_to_others_matches.append("tier1_direct_threat_to_others")
                if tier1_self_harm_cats and not self_harm_matches:
                    if not (actor_target_res.is_threat and actor_target_res.category in ("REPORTED_THREAT_TO_OTHERS", "THIRD_PARTY_REPORT")):
                        self_harm_matches.append("tier1_deterministic_crisis")
        except Exception as e:
            logger.debug("Error checking crisis_rules: %s", e)

    # Step D: Combined signal (same turn)
    has_combined_same_turn = bool(harm_to_others_matches and self_harm_matches)
    if not has_combined_same_turn and harm_to_others_matches:
        if re.search(
            r"\b(?:and|then|after\s+that|phir)\s+(?:also\s+)?(?:then\s+)?(?:myself|me|end\s+it\s+all|end\s+my\s+(?:own\s+)?life|kill\s+myself|take\s+my\s+own\s+life|turn\s+the\s+(?:gun|weapon)\s+on\s+myself|khud\s+ko\s+bhi\s+khatam|i'?m\s+gone|i\s+am\s+gone|done\s+living|commit\s+suicide|die)\b",
            norm
        ):
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

    # Step E: Third-party & actor-target threat matching
    third_party_matches = []
    threat_against_user_matches = []
    reported_threat_to_others_matches = []

    if not is_fictional and not has_others_negation:
        if actor_target_res.is_threat:
            if actor_target_res.category == "THREAT_AGAINST_USER":
                threat_against_user_matches.append(actor_target_res.raw_match or "threat_against_user")
            elif actor_target_res.category == "REPORTED_THREAT_TO_OTHERS":
                reported_threat_to_others_matches.append(actor_target_res.raw_match or "reported_threat_to_others")
            elif actor_target_res.category == "THIRD_PARTY_REPORT":
                third_party_matches.append(actor_target_res.raw_match or "third_party_report")

    if not harm_to_others_matches and not self_harm_matches and not threat_against_user_matches and not reported_threat_to_others_matches and not has_others_negation and not is_fictional:
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
    elif threat_against_user_matches:
        det_risk_level = "THREAT_AGAINST_USER"
    elif harm_to_others_matches:
        det_risk_level = "HARM_TO_OTHERS_RISK"
    elif self_harm_matches:
        det_risk_level = "SELF_HARM_RISK"
    elif reported_threat_to_others_matches:
        det_risk_level = "REPORTED_THREAT_TO_OTHERS"
    elif third_party_matches:
        det_risk_level = "THIRD_PARTY_REPORT"
    elif any(pat.search(norm) for pat in _DISTRESS_SIGNALS):
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
        or det_risk_level in ("COMBINED_HIGH_CRISIS", "THREAT_AGAINST_USER", "HARM_TO_OTHERS_RISK", "REPORTED_THREAT_TO_OTHERS")
        or (det_risk_level == "NONE" and (has_inanimate_subject or is_fictional or has_others_negation))
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
        SafetyRiskCategory.THREAT_AGAINST_USER,
        SafetyRiskCategory.HARM_TO_OTHERS_RISK,
        SafetyRiskCategory.SELF_HARM_RISK,
    )
    requires_action = is_crisis

    # Determine matched signals and safety message
    matched_signals: list = (
        (harm_to_others_matches or [])
        + (self_harm_matches or [])
        + (third_party_matches or [])
        + (threat_against_user_matches or [])
        + (reported_threat_to_others_matches or [])
    )
    if actor_target_res.is_threat and actor_target_res.raw_match:
        matched_signals.append(f"actor_target:{actor_target_res.category}")
    if winning_source == "semantic" and sem_rationale:
        matched_signals.append(f"semantic:{sem_rationale[:80]}")

    if final_risk_level == "COMBINED_HIGH_CRISIS":
        if has_combined_adjacent:
            matched_signals.append("cross_turn_adjacent_threat")
        safety_msg = COMBINED_CRISIS_SAFETY_MESSAGE
        reasoning = "Harm-to-others combined with self-harm intent detected"
        confidence = 0.99
    elif final_risk_level == "THREAT_AGAINST_USER":
        safety_msg = build_threat_against_user_safety_message(actor=actor_target_res.actor if actor_target_res else None)
        reasoning = "User reporting a direct threat against themselves"
        confidence = 0.98
    elif final_risk_level == "HARM_TO_OTHERS_RISK":
        safety_msg = HARM_TO_OTHERS_SAFETY_MESSAGE.replace("• Umang Pakistan Mental Health Helpline: 0311-7786264 (24/7 free support)\n", "")
        reasoning = "Direct credible threat to another person detected"
        confidence = 0.98
    elif final_risk_level == "REPORTED_THREAT_TO_OTHERS":
        safety_msg = build_reported_threat_safety_message(
            actor=actor_target_res.actor if actor_target_res else None,
            target=actor_target_res.target if actor_target_res else None,
        )
        reasoning = "Reported third-party threat to another person"
        confidence = 0.96
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
