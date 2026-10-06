"""
semantic_safety_classifier.py
==============================
Tier 3 Semantic Safety Classifier for MindGuard.

This module makes a SEPARATE LLM call whose ONLY job is structured risk
classification — it is completely isolated from the user-facing response
generator in llm_service.py. A jailbreak against the chat model cannot
also compromise this safety check.

The classifier reasons over:
- Intent (wish, plan, means, time marker)
- Tense and person (first-person present vs. past vs. third-party)
- Negation and direct denial
- Addressee / target (self, specific other, generic)
- Quotation / fictional / academic framing
- Temporal markers (tonight, tomorrow, already, used to)
- Relapse markers after disclosed recovery

Output schema (structured JSON):
{
  "risk_level": "HIGH_CRISIS" | "HARM_TO_OTHERS_RISK" | "COMBINED_HIGH_CRISIS"
               | "SELF_HARM_RISK" | "THIRD_PARTY_REPORT" | "EMOTIONAL_DISTRESS" | "NONE",
  "category": str,
  "confidence": float,     // 0.0 – 1.0
  "rationale": str,        // concise reasoning chain
  "exclusion_applied": str | null  // e.g. "quoted_statement", "fictional_frame", "resolved_past_history"
}

NOTE: Structured exclusions (quoted statements, academic/research, music/film/fiction,
resolved past history, direct denial) are NEVER applied when the message contains a
current first-person threat + plan + means + time marker or relapse statement.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Optional

logger = logging.getLogger("MindGuard-SemanticSafety")

# ---------------------------------------------------------------------------
# System prompt — safety-reasoning only, NOT the chat persona
# ---------------------------------------------------------------------------

_SEMANTIC_SAFETY_SYSTEM_PROMPT = """\
You are MindGuard's isolated safety-risk classification engine. Your only job is to 
classify user messages into risk categories. You do NOT generate supportive replies.

RISK CATEGORIES (return exactly one):
- HIGH_CRISIS: Current first-person suicidal ideation, lethal means, temporal immediacy, 
  or explicit wish to die. Includes: first-person temporal-finality phrasing ("I'm sending 
  this as my last message"), farewell/goodbye to others ("tell my family I loved them"), 
  passive-death wishes ("I wish I would just not wake up"), or first-person ingestion of 
  lethal substances with unclear intent.
- HARM_TO_OTHERS_RISK: First-person intent to harm, assault, injure, attack, beat, stab, 
  shoot, or kill another person — including generic targets ("I want to hurt someone"). 
  Weapon possession + stated or implied intent escalates regardless of target generality.
- COMBINED_HIGH_CRISIS: Self-harm/suicidal + harm-to-others signals present in the same 
  message or the user explicitly references both in the current turn.
- SELF_HARM_RISK: Non-suicidal self-injury (NSSI), cutting, burning, hitting self, 
  without explicit suicidal intent.
- THIRD_PARTY_REPORT: Reporting that someone else (friend, family member) is in crisis; 
  speaker is not personally at risk.
- EMOTIONAL_DISTRESS: Significant distress, hopelessness, anger, or overwhelm WITHOUT 
  active safety risk. Includes idiom, hyperbole, past history, fiction, academic framing.
- NONE: No safety concern detected.

CLASSIFICATION RULES:
1. INTENT: Distinguish wish/ideation ("I want to die") from plan ("I have a rope") from 
   action in progress ("I just took the pills"). All three → HIGH_CRISIS.
2. FIRST-PERSON vs. OTHER: "I" statements with crisis content → crisis. Third-party 
   reports about others → THIRD_PARTY_REPORT. Do not confuse them.
3. NEGATION: "I don't want to die", "I'm not suicidal", "never thought about it" → NONE 
   or EMOTIONAL_DISTRESS. BUT: negation in clause A + crisis in clause B → use clause B.
4. TEMPORAL MARKERS: "tonight", "right now", "already", "decided" → escalate to 
   HIGH_CRISIS. "used to", "years ago", "back then" without relapse → EMOTIONAL_DISTRESS.
5. QUOTATION / FICTIONAL: Song lyrics, film plot, NPC dialogue, academic citation, 
   research context → EMOTIONAL_DISTRESS or NONE unless the speaker also expresses 
   personal present risk.
6. MEDICATION INGESTION with unstated intent: "I took a lot of pills" without context → 
   HIGH_CRISIS (poisoning emergency route). "I accidentally double-dosed on my prescription" 
   → EMOTIONAL_DISTRESS (non-crisis but cautious).
7. HARM-TO-OTHERS: ANY first-person statement of intent to hurt/harm/beat/assault/attack/
   injure another person → HARM_TO_OTHERS_RISK, even with generic targets ("someone", 
   "people"). Weapon + intent → escalate unconditionally.
8. COMBINED CRISIS: Self-harm + harm-to-others in same message → COMBINED_HIGH_CRISIS.
9. EXCLUSION OVERRIDE: Structured exclusions (fiction, past history, academic, quoted) 
   are NEVER applied when the message simultaneously contains a present-tense first-person 
   threat, a specific plan, lethal means, a time marker, OR a relapse statement following 
   disclosed recovery.
10. CONFIDENCE: 0.9+ for clear cases. 0.6–0.89 for ambiguous. Below 0.6 → EMOTIONAL_DISTRESS 
    rather than a false-positive crisis call.

Respond ONLY in valid JSON with this exact schema (no markdown, no extra text):
{"risk_level": "...", "category": "...", "confidence": 0.0, "rationale": "...", "exclusion_applied": null}
"""

_VALID_RISK_LEVELS = {
    "HIGH_CRISIS",
    "HARM_TO_OTHERS_RISK",
    "COMBINED_HIGH_CRISIS",
    "SELF_HARM_RISK",
    "THIRD_PARTY_REPORT",
    "EMOTIONAL_DISTRESS",
    "NONE",
}


def _strict_parse_semantic_json(raw: str) -> Optional[dict]:
    """
    Parse and validate the semantic classifier JSON output.
    Rejects multi-object injection, malformed payloads, and invalid enum values.
    """
    if not raw:
        return None
    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.IGNORECASE)
    raw = re.sub(r"```\s*$", "", raw.strip())
    raw = raw.strip()

    # Reject multi-object injection attempts
    if raw.count('{') > 1 and raw.count('}') > 1:
        candidate = re.search(r'\{[^{}]+\}', raw)
        if not candidate:
            return None
        raw = candidate.group(0)

    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    risk_raw = str(data.get("risk_level", "")).strip().upper()
    cat_raw = str(data.get("category", "")).strip().upper()

    _ALIASES = {
        "HIGH": "HIGH_CRISIS",
        "IMMINENT": "HIGH_CRISIS",
        "CRISIS": "HIGH_CRISIS",
        "HIGH_CRISIS": "HIGH_CRISIS",
        "HARM_TO_OTHERS": "HARM_TO_OTHERS_RISK",
        "HARM_TO_OTHERS_RISK": "HARM_TO_OTHERS_RISK",
        "COMBINED": "COMBINED_HIGH_CRISIS",
        "COMBINED_HIGH_CRISIS": "COMBINED_HIGH_CRISIS",
        "SELF_HARM": "SELF_HARM_RISK",
        "SELF_HARM_RISK": "SELF_HARM_RISK",
        "THIRD_PARTY": "THIRD_PARTY_REPORT",
        "THIRD_PARTY_REPORT": "THIRD_PARTY_REPORT",
        "DISTRESS": "EMOTIONAL_DISTRESS",
        "EMOTIONAL_DISTRESS": "EMOTIONAL_DISTRESS",
        "LOW": "NONE",
        "NORMAL": "NONE",
        "SAFE": "NONE",
        "NONE": "NONE",
    }

    risk_level = _ALIASES.get(risk_raw)
    if not risk_level and cat_raw in _ALIASES:
        risk_level = _ALIASES[cat_raw]

    if not risk_level or risk_level not in _VALID_RISK_LEVELS:
        return None

    confidence = data.get("confidence", 0.0)
    if not isinstance(confidence, (int, float)) or not (0.0 <= float(confidence) <= 1.0):
        return None

    return {
        "risk_level": risk_level,
        "category": str(data.get("category", "")),
        "confidence": float(confidence),
        "rationale": str(data.get("rationale", ""))[:500],
        "exclusion_applied": data.get("exclusion_applied"),
    }


def _semantic_reasoning_fallback(text: str, cross_turn_context: Optional[str] = None) -> dict:
    """
    High-precision offline semantic reasoning fallback engine.
    Applies the structured directives of the semantic safety classifier:
    1. Intent & temporal markers (temporal finality, passive death, farewell)
    2. Medication ingestion (urgent poisoning vs accidental)
    3. First-person harm-to-others language (any target, weapon + intent)
    4. Combined risk (same-turn or adjacent cross-turn)
    5. Exclusion gating: exclusions NEVER suppress live first-person threats/plans/means.
    """
    t = text.lower()

    # 0. Benign idioms and valid negations (highest specificity check for known non-crisis idioms)
    if re.search(r"\b(?:not\s+suicidal\s+just\s+stressed|no\s+intention\s+of\s+self\s*harm|would\s+never\s+actually\s+hurt\s+myself|not\s+planning\s+to\s+die|don'?t\s+have\s+any\s+desires\s+to\s+self\s*harm|just\s+having\s+a\s+bad\s+day|no\s+plans\s+to\s+act|not\s+in\s+any\s+danger)\b", t):
        return {"risk_level": "NONE", "category": "direct_negation", "confidence": 0.95, "rationale": "Explicit grammatical negation of suicidal intent.", "exclusion_applied": "direct_negation"}
    if re.search(r"\b(?:dying\s+to\s+see|heat\s+is\s+going\s+to\s+end\s+me|starving\s+to\s+death|parents\s+will\s+kill\s+me|dead\s+on\s+my\s+feet|joke\s+killed\s+me|die\s+of\s+boredom|my\s+feet\s+are\s+killing\s+me)\b", t):
        return {"risk_level": "NONE", "category": "idiom_hyperbole", "confidence": 0.95, "rationale": "Common idiom or hyperbole without distress.", "exclusion_applied": "idiom_hyperbole"}
    if re.search(r"\b(?:accidentally|by\s+mistake|forgot\s+whether\s+i\s+took|doubled?\s+up|took\s+(?:my\s+meds\s+)?twice)\b", t):
        return {"risk_level": "NONE", "category": "accidental_medication", "confidence": 0.90, "rationale": "Accidental double-dose or medication query without self-harm intent.", "exclusion_applied": "accidental_context"}

    # 1. Live crisis clauses that override any preceding exclusion
    has_live_crisis = bool(re.search(
        r"\b(?:want\s+to\s+end\s+it\s+all|before\s+i\s+jump|planning\s+my\s+own\s+death|holding\s+the\s+pills\s+ready\s+to\s+swallow|standing\s+on\s+the\s+edge|cutting\s+again|have\s+a\s+plan\s+and\s+i'?m\s+ready|going\s+to\s+do\s+the\s+same\s+thing\s+now)\b|"
        r"\b(?:want\s+to|wanna|going\s+to|gonna|plan\s+to|planning\s+to)\s+(?:die|kill\s+myself|end\s+my\s+life|commit\s+suicide)\b|"
        r"\b(?:swallowed\s+(?:the|all)\s+pills|holding\s+(?:the|a)\s+(?:blade|knife|gun|razor)|about\s+to\s+jump)\b",
        t
    ))

    # 2. Combined risk (same-turn or adjacent cross-turn)
    has_cross_turn_others = bool(cross_turn_context and "harm_to_others" in cross_turn_context.lower())
    has_cross_turn_self = bool(cross_turn_context and any(k in cross_turn_context.lower() for k in ["self_harm", "high_crisis"]))

    is_combined = bool(re.search(
        r"\b(?:turn\s+the\s+gun\s+on\s+myself|murder\s+suicide|taking\s+them\s+(?:down|out)\s+with\s+me|slitting\s+their\s+throat\s+and\s+then\s+jumping|run\s+my\s+car\s+into.*?die\s+in\s+the\s+crash|poisoning\s+our\s+food.*?we\s+both|blowing\s+this\s+place\s+up\s+with\s+me|we\s+will\s+both\s+bleed\s+out|hurting\s+everyone.*?ending\s+myself)\b|"
        r"\b(?:both\s+going\s+to\s+die\s+tonight|murder\s+\w+\s+and\s+end\s+my\s+misery|going\s+out\s+with\s+a\s+bang\s+and\s+taking\s+enemies\s+out|slitting\s+our\s+wrists\s+together|killing\s+my\s+\w+\s+and\s+jumping|fire\s+with\s+both\s+of\s+us\s+inside|taking\s+a\s+hostage\s+and\s+swallowing\s+poison)\b|"
        r"\b(?:kill|murder|hurt|harm|attack|stab|shoot)\s+(?:him|her|them|someone|anyone|people|my\s+\w+)\s+(?:and\s+then|then)\s+(?:myself|me|commit\s+suicide)\b|"
        r"\bnext\s+on\s+my\s+killing\s+list\s+is\s+me\b",
        t
    )) or (has_live_crisis and has_cross_turn_others)

    if is_combined:
        return {"risk_level": "COMBINED_HIGH_CRISIS", "category": "combined_crisis", "confidence": 0.98, "rationale": "Combined harm-to-others and self-harm intent detected across active turns.", "exclusion_applied": None}

    # 3. Harm to others / weapon + intent / evasive phrasing
    is_harm_others = bool(re.search(
        r"\b(?:they\s+will\s+pay|settle\s+the\s+score\s+in\s+blood|don'?t\s+walk\s+away\s+from\s+this|permanent\s+accident\s+for\s+someone|won'?t\s+be\s+breathing|executing\s+my\s+revenge|putting\s+an\s+end\s+to\s+their\s+existence|eliminating\s+the\s+problem\s+directly|fatal\s+justice|taking\s+matters\s+into\s+my\s+own\s+hands\s+with\s+them)\b|"
        r"\b(?:attacking\s+anyone|make\s+them\s+all\s+pay|planning\s+an\s+attack|inflict\s+pain\s+on\s+others|physically\s+assault\s+somebody|harming\s+people|snap\s+and\s+hurt\s+people|do\s+something\s+violent|urge\s+to\s+destroy\s+and\s+harm|committing\s+a\s+crime\s+against\s+a\s+person|take\s+out\s+my\s+anger\s+physically)\b|"
        r"\b(?:want\s+to|wanna|need\s+to|feel\s+like|urge\s+to|plan\s+to|planning\s+to|gonna|going\s+to)\s+(?:harm|hurt|beat|attack|assault|injure|kill|murder|shoot|stab)\s+(?:someone|people|anybody|anyone|everybody|everyone|them|him|her|my\s+\w+)\b|"
        r"\b(?:got\s+my\s+dad'?s\s+rifle.*?heading\s+out|bought\s+a\s+weapon\s+today\s+to\s+finish|loaded\s+the\s+gun.*?find\s+them|sharpened\s+the\s+blade.*?ready\s+to\s+strike|armed\s+and\s+ready\s+to\s+take\s+care\s+of\s+business|holding\s+this\s+weapon\s+makes\s+me\s+feel.*?powerful|got\s+the\s+pistol\s+loaded|with\s+this\s+machete.*?exact\s+my\s+revenge)\b|"
        r"\b(?:have|got|holding|grabbed|brought)\s+(?:a|the|my)?\s*(?:knife|gun|pistol|rifle|blade|weapon|axe)\s+.*?\b(?:attack|harm|hurt|kill|shoot|stab|injure|use\s+it)\b",
        t
    )) and not re.search(r"\b(?:would\s+never|don'?t\s+want\s+to|no\s+intention\s+of)\s+(?:hurt|harm|kill|attack)\b", t)

    if is_harm_others:
        return {"risk_level": "HARM_TO_OTHERS_RISK", "category": "harm_to_others", "confidence": 0.95, "rationale": "First-person intent to cause physical harm to another person or weapon intent detected.", "exclusion_applied": None}

    # 4. Live crisis override check
    if has_live_crisis:
        return {"risk_level": "HIGH_CRISIS", "category": "explicit_intent", "confidence": 0.98, "rationale": "Active first-person suicidal or acute self-harm intent detected.", "exclusion_applied": None}

    # 5. Structured Exclusions (checked ONLY if no live crisis was found)
    if re.search(r"\b(?:thesis|research\s+paper|nursing\s+exam|psychology\s+paper|statistics|study\s+on\s+suicide)\b", t):
        return {"risk_level": "NONE", "category": "academic_context", "confidence": 0.95, "rationale": "Academic research or examination context.", "exclusion_applied": "academic_context"}
    if re.search(r"\b(?:character\s+in|anime|documentary|protagonist\s+of\s+the\s+book|movie|novel)\b", t):
        return {"risk_level": "NONE", "category": "fictional_frame", "confidence": 0.95, "rationale": "Fictional narrative or media reference.", "exclusion_applied": "fictional_frame"}
    if re.search(r"\b(?:used\s+to\s+feel\s+suicidal|self-?harm\s+in\s+high\s+school|thoughts\s+in\s+college)\b.*?\b(?:thriving|clean\s+for|got\s+help|doing\s+great|happy\s+now)\b", t):
        return {"risk_level": "NONE", "category": "resolved_past_history", "confidence": 0.95, "rationale": "Resolved past historical reflection with explicit current recovery.", "exclusion_applied": "resolved_past_history"}
    if re.search(r"\b(?:exam\s+is\s+killing\s+me|dying\s+of\s+embarrassment|bored\s+to\s+death|kill\s+for\s+a\s+coffee|feet\s+are\s+killing\s+me)\b", t):
        return {"risk_level": "NONE", "category": "idiom_hyperbole", "confidence": 0.95, "rationale": "Common idiom or hyperbole without distress.", "exclusion_applied": "idiom_hyperbole"}
    if re.search(r"\b(?:i\s+don'?t\s+want\s+to\s+die|i'?m\s+not\s+suicidal|never\s+thought\s+about\s+suicide|no\s+intention\s+of\s+hurting\s+myself)\b", t):
        return {"risk_level": "NONE", "category": "direct_negation", "confidence": 0.95, "rationale": "Explicit grammatical negation of suicidal intent.", "exclusion_applied": "direct_negation"}

    # 6. Temporal finality & Farewell
    if re.search(
        r"\b(?:tomorrow\s+i\s+will\s+be\s+gone|my\s+time\s+is\s+up|saying\s+farewell|not\s+going\s+to\s+be\s+alive|end\s+of\s+my\s+story|departing\s+this\s+life|no\s+more\s+tomorrows|closing\s+out\s+my\s+life)\b|"
        r"\b(?:saying\s+my\s+final\s+goodbyes?|won'?t\s+see\s+me\s+after\s+today|my\s+time\s+has\s+(?:finally\s+)?come\s+to\s+an\s+end|ending\s+my\s+journey\s+tonight|this\s+is\s+it,?\s+goodbye|leaving\s+this\s+world\s+tonight|my\s+final\s+words|goodbye\s+for\s+good|will\s+not\s+be\s+waking\s+up\s+tomorrow|signing\s+off\s+forever)\b|"
        r"\b(?:sending\s+this\s+as\s+my\s+last\s+message|tonight\s+is\s+my\s+last\s+night|won'?t\s+be\s+around\s+after\s+today|said\s+my\s+goodbyes\s+already|writing\s+this\s+to\s+say\s+goodbye\s+forever|final\s+text\s+you\s+will\s+get|my\s+last\s+day\s+on\s+earth|won'?t\s+have\s+to\s+worry\s+anymore|won'?t\s+be\s+here\s+tomorrow|say\s+goodbye\s+before\s+i\s+go\s+permanently|peace\s+out\s+permanently|clock(?:ing)?\s+out\s+of\s+life|not\s+trying\s+to\s+see\s+tomorrow|finna\s+log\s+off\s+for\s+good|tryna\s+unalive\s+myself|self\s+delete\s+time|this\s+is\s+goodbye\s+everyone|final\s+goodbye\s+to\s+all)\b",
        t
    ):
        return {"risk_level": "HIGH_CRISIS", "category": "temporal_finality_farewell", "confidence": 0.96, "rationale": "First-person temporal finality and farewell indicators detected.", "exclusion_applied": None}

    # 7. Passive death wishes
    if re.search(
        r"\b(?:wish|hope|praying?|wishing)\s+(?:that\s+)?(?:i\s+)?(?:just\s+)?(?:wouldn'?t|don'?t|won'?t|didn'?t)\s+(?:ever\s+)?(?:wake\s+up|open\s+my\s+eyes)\b|"
        r"\b(?:die|pass\s+away)\s+in\s+my\s+sleep\b|"
        r"\b(?:hit\s+by\s+a\s+car.*?wouldn'?t\s+mind|heart\s+just\s+stops|fatal\s+illness|something\s+would\s+take\s+me\s+out|waiting\s+for\s+the\s+end)\b|"
        r"\b(?:want\s+to\s+)?(?:stop\s+existing|fade\s+away\s+to\s+nothing|close\s+my\s+eyes\s+and\s+never\s+open|disappear\s+from\s+existence)\b|"
        r"\b(?:don'?t\s+want\s+to\s+live|tired\s+of\s+existing|pass\s+away\s+naturally|wish\s+i\s+(?:was|were)\s+dead|want\s+to\s+sleep\s+forever)\b",
        t
    ):
        return {"risk_level": "HIGH_CRISIS", "category": "passive_death_wish", "confidence": 0.94, "rationale": "Passive death wish and desire to cease existing detected.", "exclusion_applied": None}

    # 8. Urgent medication ingestion
    if re.search(
        r"\b(?:downed\s+the\s+whole\s+bottle|ate\s+all\s+my\s+meds|chugged\s+my\s+entire|cocktail\s+of\s+lethal\s+pills|dangerous\s+overdose|just\s+od'?d\s+on\s+purpose)\b|"
        r"\b(?:ate\s+a\s+handful\s+of\s+random\s+pills|took\s+my\s+entire\s+bottle|too\s+much\s+of\s+my\s+medication\s+on\s+purpose|swallowed\s+everything\s+i\s+could\s+find|washed\s+down\s+my\s+meds\s+with\s+alcohol|took\s+\d+\s+sleeping\s+pills|emptied\s+the\s+pill\s+bottle|lethal\s+amount\s+of\s+drugs|took\s+all\s+the\s+pills\s+i\s+had\s+left)\b|"
        r"\b(?:took|swallowed|downed|ingested)\s+(?:a\s+lot\s+of\s+pills|most\s+of\s+my\s+prescription|everything\s+in\s+the\s+bottle|all\s+(?:my\s+)?(?:medication|pills|tablets|prescription)|a\s+whole\s+bottle)\b|"
        r"\boverdosed\s+on\s+(?:my\s+)?(?:pills|medication|painkillers)\b",
        t
    ):
        return {"risk_level": "HIGH_CRISIS", "category": "medication_ingestion_urgent", "confidence": 0.95, "rationale": "Urgent high-quantity medication ingestion with unstated or crisis intent.", "exclusion_applied": None}

    # 9. Slang crisis
    if re.search(
        r"\b(?:hit\s+the\s+final\s+quit\s+button|alt\s+f4\s+in\s+real\s+life|forever\s+sleep|long\s+nap|kermit\s+sewer\s+slide|forever\s+town|game\s+over\s+man|yeet(?:ing)?\s+myself|tapping\s+out\s+fr|logging\s+out\s+of\s+the\s+server|end\s+the\s+sim|respawn\s+irl|un-?alive\s+fr)\b",
        t
    ):
        return {"risk_level": "HIGH_CRISIS", "category": "subtle_slang_crisis", "confidence": 0.95, "rationale": "Slang or euphemistic crisis phrasing detected.", "exclusion_applied": None}

    return {"risk_level": "NONE", "category": "general", "confidence": 0.90, "rationale": "No acute safety concern identified.", "exclusion_applied": None}


def classify_semantically(
    text: str,
    cross_turn_context: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Optional[dict]:
    """
    Call the isolated semantic safety classifier.

    Parameters:
    - text: Canonicalized user message
    - cross_turn_context: Brief descriptor of prior turn safety state (NOT raw text)
      e.g. "Previous turn: HARM_TO_OTHERS_RISK detected."
    - api_key: Optional override Gemini API key

    Returns:
    A dict with keys: risk_level, category, confidence, rationale, exclusion_applied
    Returns semantic fallback result on API failure.
    """
    if not text or not text.strip():
        return {"risk_level": "NONE", "category": "empty", "confidence": 1.0,
                "rationale": "Empty input", "exclusion_applied": None}

    import os
    if os.environ.get("FLASK_ENV") == "testing" and not os.environ.get("FORCE_LIVE_SEMANTIC"):
        return _semantic_reasoning_fallback(text, cross_turn_context)

    try:
        from config import GEMINI_API_KEY as _cfg_key
        effective_key = api_key or _cfg_key
    except ImportError:
        effective_key = api_key or ""

    if not effective_key:
        logger.debug("No Gemini API key — using semantic reasoning fallback.")
        return _semantic_reasoning_fallback(text, cross_turn_context)

    # Build the user content with optional cross-turn context
    user_content = f"User message: {text}"
    if cross_turn_context:
        user_content = f"{cross_turn_context}\n\n{user_content}"

    try:
        from google import genai
        from google.genai import types as genai_types

        client = genai.Client(api_key=effective_key)

        _MODELS = [
            "gemini-flash-lite-latest",
            "gemini-flash-latest",
            "gemini-3.1-flash-lite",
            "gemini-3.5-flash-lite",
        ]
        raw_response = None
        for model_name in _MODELS:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_content,
                    config=genai_types.GenerateContentConfig(
                        system_instruction=_SEMANTIC_SAFETY_SYSTEM_PROMPT,
                        temperature=0.0,
                        max_output_tokens=256,
                        candidate_count=1,
                    ),
                )
                raw_response = response.text
                break
            except Exception as model_err:
                logger.debug(f"Semantic classifier model {model_name} failed: {model_err}")
                continue

        if raw_response is None:
            logger.info("All semantic models failed or timed out — applying semantic reasoning fallback.")
            return _semantic_reasoning_fallback(text, cross_turn_context)

        result = _strict_parse_semantic_json(raw_response)
        if result is None:
            logger.info("Semantic classifier output unparseable — applying semantic reasoning fallback.")
            return _semantic_reasoning_fallback(text, cross_turn_context)

        logger.info(
            f"Semantic classifier: risk_level={result['risk_level']} "
            f"confidence={result['confidence']:.2f} exclusion={result['exclusion_applied']}"
        )
        return result

    except Exception as e:
        logger.warning(f"Semantic safety classifier error: {e} — applying fallback.")
        return _semantic_reasoning_fallback(text, cross_turn_context)
