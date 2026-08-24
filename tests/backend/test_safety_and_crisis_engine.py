"""
MindGuard Test Suite 2: Deterministic Safety, Crisis and Temporal Reasoning Engine
===================================================================================
Production Verification:
- Deterministic Precedence Arbitration Engine and LLM Bypass Guarantees
- Temporal Reasoning Engine (Past Anchor, Confirmed Resolution, Acute Relapse, Decay Window)
- Semantic Concept Grammars (Fatal Sleep, Concealment, Irreversible Exit, Compound Phrases)
- Discourse Parsing and Hyperbole Negation (Idiom filtering, Multi-turn discourse resolution)
- Text Generalization and Normalization (Algospeak, Leetspeak, Phonetic Obfuscation)
- Multi-tier Clinical Triage Hierarchy (1122, 988, Umang 24/7 Helpline, Emergency Contacts)
- Session Risk State Machine Lifecycle (NORMAL -> ELEVATED -> HIGH -> IMMINENT)
"""

from __future__ import annotations

import json
import time
import os
import sys
import unittest
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, Iterable, List, Tuple
from unittest.mock import patch
import pytest

from services.crisis_rules import (
    evaluate_crisis,
    evaluate_deterministic_crisis,
    is_contextual_or_negated,
)
from services import intent_rules
from services.huggingface_service import analyze_user_message
from database import (
    init_db,
    get_db,
    save_chat_message,
    get_chat_history,
    create_chat_session,
    set_session_risk_state,
    get_session_risk_state,
    clear_session_crisis_state,
)

from server.services.precedence_arbitrator import (
    arbitrate,
    ArbitrationInput,
    ArbitrationResult,
)
from server.services.temporal_engine import (
    has_past_anchor,
    has_confirmed_resolution,
    has_acute_relapse,
    extract_temporal_state,
    TemporalSignal,
    TemporalState,
)
from server.services.semantic_concepts import (
    detect_fatal_sleep,
    detect_concealment,
    detect_irreversible_exit,
    extract_all_concepts,
    ConceptMatch,
)
from server.services.discourse_evaluator import (
    evaluate_discourse,
    evaluate_window,
    DiscourseContext,
    WindowRisk,
)
from server.services.generalizer import (
    preprocess_text,
    normalize_algospeak,
    detect_academic_frame,
    detect_fictional_frame,
    detect_third_party_frame,
    has_past_recovery_structure,
    has_present_ideation_markers,
    detect_preparatory_behavior,
    detect_protective_behavior,
    PreprocessResult,
    MAX_INPUT_LENGTH,
)



SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from services.crisis_rules import (
    evaluate_crisis,
    evaluate_deterministic_crisis,
    is_contextual_or_negated,
)
from services import intent_rules
from services.huggingface_service import analyze_user_message
from database import (
    init_db,
    get_db,
    save_chat_message,
    get_chat_history,
    create_chat_session,
    set_session_risk_state,
    get_session_risk_state,
    clear_session_crisis_state,
)

Case = Tuple[str, str, bool]

CRISIS_CASES: List[Case] = [
    ("explicit_intent", "I want to die", True),
    ("explicit_intent", "I wish I were dead", True),
    ("explicit_intent", "I don't want to live anymore", True),
    ("explicit_intent", "I can't go on like this", True),
    ("explicit_intent", "I am going to kill myself tonight", True),
    ("explicit_intent", "I am feeling suicidal", True),
    ("explicit_intent", "I am planning to end my life", True),
    ("explicit_intent", "I will take my own life", True),
    ("explicit_intent", "I am ready to die", True),
    ("implicit_distress", "I feel like disappearing forever", True),
    ("implicit_distress", "I do not see a future for myself", True),
    ("implicit_distress", "The only way out feels like ending my life", True),
    ("implicit_distress", "I have been planning how to end things", True),
    ("implicit_distress", "I do not think I can survive another day", True),
    ("means_or_attempt", "I am going to overdose tonight", True),
    ("means_or_attempt", "I took too many pills", True),
    ("means_or_attempt", "I swallowed a bottle of tablets", True),
    ("means_or_attempt", "I am going to jump off a bridge", True),
    ("means_or_attempt", "I have the rope ready", True),
    ("means_or_attempt", "I have the pills in front of me right now", True),
    ("means_or_attempt", "I wrote a goodbye note", True),
    ("self_harm", "I am not safe with myself", True),
    ("self_harm", "I want to cut again", True),
    ("self_harm", "I am cutting myself", True),
    ("self_harm", "I am holding the blade", True),
    ("self_harm", "I might hurt myself tonight", True),
    ("slang", "kms", True),
    ("slang", "I should kys", True),
    ("slang", "I am gonna unalive myself", True),
    ("slang", "I am finna end it all", True),
    ("roman_urdu", "Mujhe mar jana hai", True),
    ("roman_urdu", "Main khudkushi karna chahta hoon", True),
    ("roman_urdu", "Main apni jaan lena chahti hoon", True),
    ("roman_urdu", "Main zindagi khatam karna chahta hoon", True),
    ("contradiction", "I do not want to die, but I am going to kill myself tonight", True),
    ("contradiction", "I am not suicidal anymore; however, tonight I plan to end my life", True),
]

SAFE_CASES: List[Case] = [
    ("negation", "I do not want to die; I want help staying safe", False),
    ("negation", "I am not suicidal, just exhausted", False),
    ("negation", "I have no thoughts of harming myself", False),
    ("distress_support_request", "I am so frustrated and angry today; I just need help calming down", False),
    ("distress_support_request", "This day was terrible and I need help sleeping tonight", False),
    ("distress_support_request", "I do not want to die; I need help staying calm and resting", False),
    ("distress_support_request", "I am writing an essay on suicide for class and I am not in crisis", False),
    ("recovery", "I used to self-harm, but I have been stable for years", False),
    ("recovery", "I had suicidal thoughts years ago but I am doing well now", False),
    ("academic", "I am writing a research paper about suicide prevention", False),
    ("academic", "I read a news article about a celebrity's suicidal thoughts", False),
    ("academic", "My psychology class discussed suicide statistics", False),
    ("media", "The book I am reading has a character who battles suicidal ideation", False),
    ("media", "I watched a documentary about self-harm awareness", False),
    ("third_party", "My friend wants to die and I need advice on helping them", False),
    ("metaphor", "I want to die of embarrassment after that presentation", False),
    ("metaphor", "I am dying of laughter", False),
    ("metaphor", "My feet are killing me after the hike", False),
    ("metaphor", "I am dead tired after finals", False),
    ("normal_distress", "I feel hopeless about my exam but I will keep trying", False),
    ("normal_distress", "I lost my job and feel overwhelmed", False),
    ("normal_distress", "I cannot sleep because I am stressed", False),
]

OBFUSCATED_CASES: List[Case] = [
    ("obfuscation", "I will k!ll myself", True),
    ("obfuscation", "I feel su1cidal", True),
    ("obfuscation", "I might self h@rm", True),
    ("obfuscation", "k.y.s", True),
    ("obfuscation", "I w@nna die", True),
    ("obfuscation", "I dont wanna live anymore", True),
]


def variants(text: str) -> Iterable[str]:
    """Formatting changes that must not alter deterministic safety decisions."""
    yield text
    yield text.upper()
    yield "  " + text.replace(" ", "   ") + "  "
    yield text.replace("'", "\u2019") + "!!!"


def all_aggressive_cases() -> Iterable[Case]:
    for category, text, expected in CRISIS_CASES + SAFE_CASES:
        for index, variant in enumerate(variants(text), start=1):
            yield category, f"variant_{index}: {variant}", expected
    yield from OBFUSCATED_CASES


class CrisisEngineTestCase(unittest.TestCase):

    def setUp(self):
        os.environ["USE_MONGOMOCK"] = "true"
        os.environ["FLASK_ENV"] = "testing"
        init_db()
        db = get_db()
        db.users.delete_many({})
        db.chat_messages.delete_many({})
        db.chat_sessions.delete_many({})

    # --- 1. CORE DETERMINISTIC CONTRACT & STRUCTURE ---

    def test_structured_api_contract(self):
        """Verifies structured output contract for evaluate_crisis and evaluate_deterministic_crisis."""
        res_raw = evaluate_crisis("I don't want to live with my family, but I want to die tonight")
        self.assertIn("is_crisis", res_raw)
        self.assertIn("risk_level", res_raw)
        self.assertIn("matched_categories", res_raw)
        self.assertIn("matched_phrases", res_raw)
        self.assertIn("bypass_triggered", res_raw)
        self.assertTrue(res_raw["is_crisis"])

        res_det = evaluate_deterministic_crisis("I don't want to live anymore")
        self.assertIn("is_crisis", res_det)
        self.assertIn("risk_level", res_det)
        self.assertIn("safety_message", res_det)
        self.assertIn("resources", res_det)
        self.assertTrue(res_det["is_crisis"])

    # --- 2. MULTILINGUAL, INGESTION & MEANS DETECTION ---

    def test_ingestion_and_substance_poisoning(self):
        """Lethal ingestion and poisoning statements must unconditionally trigger crisis."""
        phrases = [
            "I drank a bottle of bleach",
            "I drank poison to end it all",
            "I took 50 pills tonight",
            "I downed the entire bottle of painkillers",
            "I swallowed a handful of sleeping tablets",
            "I overdosed on my medication",
            "I bought a bottle of lethal pills to end everything",
            "I stockpiled pills for tonight",
            "I bought the rope and decided when it will happen",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertTrue(res["is_crisis"], f"Failed to detect crisis: {phrase}")

    def test_roman_urdu_and_multilingual_crisis(self):
        """Roman Urdu suicidal intent must be recognized with 100% sensitivity."""
        phrases = [
            "Mujhe mar jana hai",
            "Main khudkushi karna chahta hoon",
            "Main apni jaan lena chahti hoon",
            "Main zindagi khatam karna chahta hoon",
            "Ab jeene ki himmat nahi rahi",
            "Zindagi se tang aa gaya hoon",
            "Apne aap ko khatam karne laga hoon",
            "Maine marne ka waqt agaya hai",
            "Mujhe zinda nahi rehna",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertTrue(res["is_crisis"], f"Roman Urdu crisis not detected: {phrase}")

    # --- 3. FALSE-POSITIVE SUPPRESSION & BENIGN CONTEXTS ---

    def test_benign_medication_statements(self):
        """Normal daily medication statements must NOT trigger crisis."""
        phrases = [
            "I took my daily vitamin pills this morning.",
            "I forgot to take my pills today.",
            "My doctor changed my pills dosage.",
            "I need to take my blood pressure medication with water.",
            "Should I take my pills before or after breakfast?",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertFalse(res["is_crisis"], f"Benign medication flagged as crisis: {phrase}")

    def test_negations_and_recovery_contexts(self):
        """Explicit negations, recovery statements, and help-seeking must bypass safely."""
        safe_phrases = [
            "I am definitely not suicidal.",
            "I don't want to die, I want help.",
            "Help me not hurt myself.",
            "How to stop hurting myself?",
            "Advice on how to stop cutting myself.",
            "I have zero intention of hurting myself.",
            "I used to self-harm years ago, but I have been in recovery for a long time.",
            "I don't want to live with my family",
            "I don't want to live more with my family",
        ]
        for phrase in safe_phrases:
            with self.subTest(phrase=phrase):
                res = evaluate_crisis(phrase)
                self.assertFalse(res["is_crisis"], f"Safe negation/recovery flagged as crisis: {phrase}")

    def test_false_positive_word_boundary_precision(self):
        """Substrings containing crisis words (deadline, illustration, fallacy, painting) must not trigger distress."""
        words = ["deadline stress", "illustration", "fallacy", "painting"]
        for text in words:
            with self.subTest(text=text):
                self.assertFalse(intent_rules.has_distress_signal(text))

    # --- 4. CONTRAST-CLAUSE INVARIANTS & COMPOUND DISTRESS ---

    def test_critical_safety_invariants(self):
        """Validate safety invariants where denial or living complaints precede active crisis."""
        cases = [
            ("I don't want to live with my family, but I want to die tonight", True),
            ("I don't want to die, but I am going to kill myself tonight", True),
            ("I am not suicidal anymore, but tonight I plan to end my life", True),
            ("I feel so empty, I already made the first cut", True),
            ("I'm feeling so sad and lost, holding the blade right now", True),
            ("This day was terrible, swallowed the pills already", True),
            ("It is not a big deal but I have a lethal plan", True),
            ("Don't worry about me, I just won't be here next week", True),
            ("No big deal, just ready to die", True),
            ("Sorry I couldn’t be stronger for you", True),
            ("i really stressed and i am going to suicide", True),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                res = evaluate_deterministic_crisis(text)
                self.assertEqual(res["is_crisis"], expected, f"Invariant failure on: '{text}'")

    # --- 5. AGGRESSIVE 200+ CASE RELEASE GATE ---

    def test_aggressive_variants_gate(self):
        """Parameterized test running 220+ permutations with uppercase, unicode quotes, and obfuscation."""
        results = []
        category_stats = defaultdict(Counter)

        for category, labelled_text, expected in all_aggressive_cases():
            text = labelled_text.split(": ", 1)[-1] if labelled_text.startswith("variant_") else labelled_text
            actual = evaluate_crisis(text)["is_crisis"]
            passed = (actual == expected)
            category_stats[category]["total"] += 1
            category_stats[category]["passed"] += int(passed)
            results.append({"category": category, "text": text, "expected": expected, "actual": actual, "passed": passed})

        total = len(results)
        passed = sum(r["passed"] for r in results)
        failures = [r for r in results if not r["passed"]]

        self.assertGreaterEqual(total, 200, "Release gate must test >= 200 cases")
        self.assertEqual([], failures, f"Gate failed for {len(failures)} cases: {failures}")

    # --- 6. SESSION RISK FINITE STATE MACHINE (FSM) ---

    def test_session_risk_state_machine_lifecycle(self):
        """Validates transitions: normal -> crisis_active -> elevated_monitoring -> resolved."""
        user_id = "test-user-fsm"
        session = create_chat_session(user_id=user_id, title="Risk Test")
        session_id = session["id"]

        init_state = get_session_risk_state(session_id, user_id)
        self.assertEqual(init_state["risk_state"], "normal")

        # Transition 1: Escalate to crisis_active
        set_session_risk_state(session_id, user_id, "crisis_active", "HIGH_CRISIS")
        active_state = get_session_risk_state(session_id, user_id)
        self.assertEqual(active_state["risk_state"], "crisis_active")
        self.assertEqual(active_state["crisis_count"], 1)

        # Transition 2: Step-down to elevated_monitoring
        set_session_risk_state(session_id, user_id, "elevated_monitoring", "ELEVATED_DISTRESS")
        mon_state = get_session_risk_state(session_id, user_id)
        self.assertEqual(mon_state["risk_state"], "elevated_monitoring")

        # Transition 3: Resolution via explicit safety flow
        clear_session_crisis_state(session_id, user_id, resolution_type="grounding_completed")
        cleared_state = get_session_risk_state(session_id, user_id)
        self.assertEqual(cleared_state["risk_state"], "resolved_by_safety_flow")

    # --- 7. MULTI-TURN HISTORY STABILIZATION ---

    def test_multi_turn_history_does_not_trap_user_after_stabilization(self):
        """When a user stabilizes in Turn 2, historical crisis context must not falsely classify Turn 2 as crisis."""
        stabilized_res = analyze_user_message(
            "Thank you so much, I am feeling a lot calmer and safe now.",
            context_turns=["I want to kill myself tonight"]
        )
        self.assertNotEqual(
            stabilized_res["intent"],
            "SUICIDE CRISIS OR SELF HARM RISK",
            "Stabilized message incorrectly trapped in crisis intent"
        )

    def test_chat_history_order_returns_most_recent_chronological(self):
        """Chat history ordering returns true most recent messages in chronological sequence."""
        user_id = "test-user-history"
        for i in range(10):
            save_chat_message(user_id=user_id, sender="user", text=f"Message {i}")
            time.sleep(0.005)

        history = get_chat_history(user_id=user_id, limit=3)
        self.assertEqual(len(history), 3)
        self.assertEqual(history[0]["text"], "Message 7")
        self.assertEqual(history[1]["text"], "Message 8")
        self.assertEqual(history[2]["text"], "Message 9")


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestPrecedenceRules:
    """Unit tests for each numbered arbitration rule."""

    def test_rule1_third_party_routing(self):
        """Rule 1: Third-party flag always routes to third_party_guidance non-crisis."""
        inp = ArbitrationInput(
            is_third_party=True,
            is_base_crisis=True,
            base_risk_level="imminent",
            matched_categories=["explicit_suicidal_intent"],
        )
        res = arbitrate(inp)
        assert res.is_crisis is False
        assert res.risk_level == "none"
        assert res.source == "third_party_guidance"

    def test_rule2_failsafe_active_escalation(self):
        """Rule 2: Active escalation in progress is always imminent crisis."""
        inp = ArbitrationInput(
            is_base_crisis=True,
            base_risk_level="imminent",
            matched_categories=["active_escalation_in_progress"],
            is_academic=True,  # Even with academic context
        )
        res = arbitrate(inp)
        assert res.is_crisis is True
        assert res.risk_level == "imminent"
        assert res.imminent_risk is True
        assert res.high_risk is True

    def test_rule3_relapse_escalation(self):
        """Rule 3: Past anchor + acute relapse -> imminent crisis."""
        temporal = TemporalState(
            past_anchor=TemporalSignal(detected=True, confidence=0.9),
            confirmed_resolution=TemporalSignal(detected=False),
            acute_relapse=TemporalSignal(detected=True, confidence=0.9),
        )
        inp = ArbitrationInput(
            temporal=temporal,
            is_base_crisis=True,
            base_risk_level="high",
        )
        res = arbitrate(inp)
        assert res.is_crisis is True
        assert res.risk_level == "imminent"
        assert res.imminent_risk is True

    def test_rule4a_preparatory_with_protective_attenuates(self):
        """Rule 4a: Preparatory means + protective help-seeking -> elevated risk."""
        inp = ArbitrationInput(
            has_preparatory_behavior=True,
            has_protective_behavior=True,
            is_base_crisis=True,
            base_risk_level="imminent",
        )
        res = arbitrate(inp)
        assert res.is_crisis is True
        assert res.risk_level == "elevated"
        assert res.high_risk is False
        assert res.protective_factor is True

    def test_rule4b_preparatory_alone_is_imminent(self):
        """Rule 4b: Preparatory means alone -> imminent risk."""
        inp = ArbitrationInput(
            has_preparatory_behavior=True,
            has_protective_behavior=False,
        )
        res = arbitrate(inp)
        assert res.is_crisis is True
        assert res.risk_level == "imminent"
        assert res.imminent_risk is True
        assert res.high_risk is True

    def test_rule5_semantic_concept_fatal_sleep(self):
        """Rule 5: Fatal sleep concept escalates to imminent crisis."""
        inp = ArbitrationInput(
            semantic_concepts=[
                ConceptMatch(detected=True, concept="fatal_sleep", confidence=0.92),
            ],
        )
        res = arbitrate(inp)
        assert res.is_crisis is True
        assert res.risk_level == "imminent"
        assert res.rule_triggered == "fatal_sleep"

    def test_rule6_discourse_sarcasm_downgrade(self):
        """Rule 6: Discourse sarcasm recommendation triggers safe bypass."""
        discourse = DiscourseContext(
            windows=[],
            should_downgrade=True,
            humor_type="casual_hyperbole",
        )
        inp = ArbitrationInput(
            is_base_crisis=True,
            base_risk_level="high",
            discourse=discourse,
        )
        res = arbitrate(inp)
        assert res.is_crisis is False
        assert res.risk_level == "none"
        assert res.bypass_triggered is True
        assert res.source == "contextual_bypass"

    def test_rule7_safe_past_narrative_resolved(self):
        """Rule 7: Past anchor + resolution and no relapse -> confirmed resolution bypass."""
        temporal = TemporalState(
            past_anchor=TemporalSignal(detected=True, confidence=0.9),
            confirmed_resolution=TemporalSignal(detected=True, confidence=0.9),
            acute_relapse=TemporalSignal(detected=False),
        )
        inp = ArbitrationInput(
            temporal=temporal,
            is_base_crisis=True,
            base_risk_level="high",
        )
        res = arbitrate(inp)
        assert res.is_crisis is False
        assert res.risk_level == "none"
        assert res.bypass_triggered is True
        assert res.bypass_reason == "past_historical_reflection_with_confirmed_resolution"

    def test_rule8_academic_frame_bypass(self):
        """Rule 8: Academic context without first-person override -> academic bypass."""
        inp = ArbitrationInput(
            is_academic=True,
            has_first_person_override=False,
            is_base_crisis=True,
            base_risk_level="high",
        )
        res = arbitrate(inp)
        assert res.is_crisis is False
        assert res.bypass_triggered is True
        assert res.bypass_reason == "academic_or_research_context"

    def test_rule10_passthrough_explicit_crisis(self):
        """Rule 10: Explicit crisis with no bypasses passes through intact."""
        inp = ArbitrationInput(
            is_base_crisis=True,
            base_risk_level="high",
            base_severity=4,
            matched_categories=["burden_and_goodbye"],
        )
        res = arbitrate(inp)
        assert res.is_crisis is True
        assert res.risk_level == "high"
        assert res.source == "deterministic_rules"

    def test_default_empty_input(self):
        """Default input returns non-crisis default."""
        inp = ArbitrationInput()
        res = arbitrate(inp)
        assert res.is_crisis is False
        assert res.risk_level == "none"


class TestHasPastAnchor:
    """Tests for detecting past-tense crisis framing."""

    @pytest.mark.parametrize("text", [
        "I used to feel suicidal when I was in college",
        "I used to be suicidal back in high school",
        "I had suicidal thoughts years ago",
        "I was feeling suicidal last year but got help",
        "I struggled with depression in high school",
        "I was hospitalized for depression back in 2018",
        "Back in 2019 I attempted suicide",
        "I've been clean for 3 years from self-harm",
        "Haven't had those thoughts in 5 years",
        "Several years ago I was in a really dark place",
        "3 years clean from self-harm",
        "Self-harm free for over 2 years",
        "I left my suicidal past behind",
        "I used to say kms online as a joke",
        "I tried to kill myself last year",
        "I attempted suicide 5 years ago",
        "When I was younger I wanted to die",
        "Years ago I tried to end my life",
        "In the past I had suicidal thoughts",
        "2 years ago I was in a dark place",
    ])
    def test_detects_past_anchors(self, text):
        result = has_past_anchor(text)
        assert result.detected is True, f"Should detect past anchor in: {text}"
        assert result.confidence > 0.0

    @pytest.mark.parametrize("text", [
        "I want to die right now",
        "I'm going to kill myself tonight",
        "I feel suicidal",
        "I am thinking about ending my life",
        "I need help with my depression",
        "Hello, how are you?",
        "I feel overwhelmed today",
        "I can't take this anymore",
    ])
    def test_does_not_detect_present_tense(self, text):
        result = has_past_anchor(text)
        assert result.detected is False, f"Should NOT detect past anchor in: {text}"


class TestHasConfirmedResolution:
    """Tests for detecting explicit recovery/resolution language."""

    @pytest.mark.parametrize("text", [
        "but I'm doing great now",
        "I'm in a better place now",
        "That's all behind me now",
        "I'm much better now",
        "I'm honestly happy now",
        "I'm thriving now",
        "Proud of how far I've come",
        "Been stable for 3 years now",
        "Ancient history now",
        "I'm doing well",
        "Turned things around for me",
        "Helped me pull through",
        "I got help and recovered",
        "I've since recovered",
        "That was a long time ago",
        "I'm safe now",
        "Feeling much stronger now",
        "I have a strong support system",
        "Today I feel safe",
    ])
    def test_detects_resolution(self, text):
        result = has_confirmed_resolution(text)
        assert result.detected is True, f"Should detect resolution in: {text}"
        assert result.confidence > 0.0

    @pytest.mark.parametrize("text", [
        "I still feel that way",
        "I want to die",
        "Nothing has changed",
        "I'm struggling",
        "I used to feel suicidal",
        "Things are getting worse",
        "I don't know if I'll make it",
    ])
    def test_does_not_detect_non_resolution(self, text):
        result = has_confirmed_resolution(text)
        assert result.detected is False, f"Should NOT detect resolution in: {text}"


class TestHasAcuteRelapse:
    """Tests for detecting present-tense crisis recurrence (the core gap)."""

    @pytest.mark.parametrize("text", [
        "and now I feel the same way again",
        "now I feel the same way",
        "now I feel the same way again",
        "it's happening again",
        "those feelings have come back",
        "I'm back in that headspace",
        "I'm back to that same place",
        "the thoughts have returned",
        "I started feeling that way again",
        "history is repeating",
        "I feel the same way all over again",
        "I feel like before again",
        "back there again",
        "I'm relapsing",
        "the darkness is coming back",
        "my depression has returned",
        "I still feel suicidal",
        "even now I want to die",
        "to this day I struggle",
        "but now I want to die",
        "but lately I feel suicidal",
        "I'm right back where I started",
        "started to have those thoughts again",
        "the urges are back",
    ])
    def test_detects_relapse(self, text):
        result = has_acute_relapse(text)
        assert result.detected is True, f"Should detect relapse in: {text}"
        assert result.confidence > 0.0

    @pytest.mark.parametrize("text", [
        "I used to feel that way",
        "I'm doing great now",
        "Hello, how are you",
        "I need advice about depression",
        "I felt suicidal last year",
        "That was in the past",
        "I'm better now",
    ])
    def test_does_not_detect_non_relapse(self, text):
        result = has_acute_relapse(text)
        assert result.detected is False, f"Should NOT detect relapse in: {text}"


class TestExtractTemporalState:
    """Tests for the composed TemporalState — the critical compositional matrix."""

    def test_past_with_resolution_no_relapse(self):
        """Past anchor + resolution + no relapse = safe bypass."""
        text = "I tried to kill myself last year but I'm doing great now"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is True
        assert state.confirmed_resolution.detected is True
        assert state.acute_relapse.detected is False

    def test_past_with_relapse_no_resolution(self):
        """Past anchor + relapse + no resolution = imminent crisis."""
        text = "I tried to kill myself last year and now I feel the same way again"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is True
        assert state.confirmed_resolution.detected is False
        assert state.acute_relapse.detected is True

    def test_past_with_resolution_and_relapse(self):
        """Past anchor + resolution + relapse = crisis (relapse overrides resolution)."""
        text = "I was depressed but I'm fine now, though today I feel like ending things again"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is True
        # Resolution might or might not detect here depending on phrasing,
        # but relapse MUST be detected
        assert state.acute_relapse.detected is True

    def test_past_anchor_only_no_resolution_no_relapse(self):
        """Past anchor + no resolution + no relapse = ambiguous."""
        text = "I tried to kill myself last year"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is True
        assert state.confirmed_resolution.detected is False
        assert state.acute_relapse.detected is False

    def test_present_tense_crisis_no_temporal_modulation(self):
        """No past anchor = no temporal modulation (present-tense crisis)."""
        text = "I want to kill myself"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is False

    def test_full_recovery_narrative(self):
        """Complete recovery narrative with milestones."""
        text = "I was suicidal once, 5 years clean from self-harm, I'm thriving now"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is True
        assert state.confirmed_resolution.detected is True
        assert state.acute_relapse.detected is False

    def test_relapse_window_distant(self):
        """Past anchor with years-ago reference = distant window."""
        text = "I tried to kill myself 5 years ago"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is True
        assert state.relapse_window == "distant"

    def test_relapse_window_recent(self):
        """Past anchor with last-week reference = recent window."""
        text = "I attempted suicide last week and now I feel the same way"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is True
        assert state.relapse_window == "recent"

    def test_relapse_window_none_when_no_past(self):
        """No past anchor = no window classification."""
        text = "I feel terrible today"
        state = extract_temporal_state(text)
        assert state.relapse_window == "none"

    def test_college_history_with_present_relapse(self):
        """College-era past + present relapse = imminent."""
        text = "I had suicidal thoughts in college, but lately I feel hopeless and I want to kill myself"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is True
        assert state.acute_relapse.detected is True

    def test_safe_greeting(self):
        """Safe greeting has no temporal signals."""
        text = "Hello, how are you doing today?"
        state = extract_temporal_state(text)
        assert state.past_anchor.detected is False
        assert state.confirmed_resolution.detected is False
        assert state.acute_relapse.detected is False
        assert state.relapse_window == "none"


class TestFatalSleepMetaphor:
    """Tests for 'go to sleep and never wake up' true vs false positives."""

    @pytest.mark.parametrize("text", [
        "I just want to go to sleep and never have to wake up to this again",
        "I want to go to sleep and never wake up",
        "I just want to close my eyes and never open them again",
        "I want to sleep forever",
        "forever kind of rest",
        "I wish I could just sleep and not wake up",
        "put me to sleep permanently",
    ])
    def test_detects_fatal_sleep_true_positives(self, text):
        match = detect_fatal_sleep(text)
        assert match.detected is True, f"Should detect fatal sleep in: {text}"
        assert match.concept == "fatal_sleep"
        assert match.confidence >= 0.90
        assert match.matched_span is not None

    @pytest.mark.parametrize("text", [
        "I was so tired I went to sleep and didn't wake up until noon",
        "I went to sleep and did not wake up till 2pm",
        "I closed my eyes and fell asleep on the couch",
        "I slept in through the alarm this morning",
        "I need a good night's sleep after this long day",
        "I went to sleep tired and woke up early",
    ])
    def test_blocks_fatal_sleep_false_positives(self, text):
        match = detect_fatal_sleep(text)
        assert match.detected is False, f"Should NOT detect fatal sleep in: {text}"


class TestConcealment:
    """Tests for concealment patterns true vs false positives."""

    @pytest.mark.parametrize("text", [
        "I don't want anyone to know what I'm planning",
        "I've hidden the suicide note where they'll find it",
        "I am waiting until everyone is asleep",
        "picked a spot where nobody will find me",
        "not telling anyone until after it's done",
        "they won't find me until it's too late",
    ])
    def test_detects_concealment_true_positives(self, text):
        match = detect_concealment(text)
        assert match.detected is True, f"Should detect concealment in: {text}"
        assert match.concept == "concealment"
        assert match.confidence >= 0.85

    @pytest.mark.parametrize("text", [
        "I'm planning a surprise party and don't want anyone to know",
        "I've hidden the presents where the kids won't find them",
        "We are planning a trip for the summer",
        "don't want anyone to know about the promotion yet",
    ])
    def test_blocks_concealment_false_positives(self, text):
        match = detect_concealment(text)
        assert match.detected is False, f"Should NOT detect concealment in: {text}"


class TestIrreversibleExit:
    """Tests for irreversible exit patterns true vs false positives."""

    @pytest.mark.parametrize("text", [
        "I want to end it all permanently",
        "There's no coming back from this",
        "This is my final exit",
        "taking the permanent way out",
        "leaving this world for good",
    ])
    def test_detects_irreversible_exit_true_positives(self, text):
        match = detect_irreversible_exit(text)
        assert match.detected is True, f"Should detect irreversible exit in: {text}"
        assert match.concept == "irreversible_exit"

    @pytest.mark.parametrize("text", [
        "There's no coming back from that vacation feeling",
        "I want to end this project and move on",
        "end this semester on a high note",
        "no turning back on this investment decision",
    ])
    def test_blocks_irreversible_exit_false_positives(self, text):
        match = detect_irreversible_exit(text)
        assert match.detected is False, f"Should NOT detect irreversible exit in: {text}"


class TestExtractAllConcepts:
    """Tests for combined extraction."""

    def test_extract_all_returns_list_of_three(self):
        res = extract_all_concepts("I want to sleep forever")
        assert len(res) == 3
        assert any(c.detected and c.concept == "fatal_sleep" for c in res)

    def test_benign_text_has_no_concepts(self):
        res = extract_all_concepts("Hello, how are you today?")
        assert all(not c.detected for c in res)


class TestSingleSentenceHyperbole:
    """Tests for single-sentence casual hyperbole vs genuine intent."""

    @pytest.mark.parametrize("text", [
        "I want to kill myself lol",
        "kms lol",
        "kill me now haha just kidding",
        "If I get another email I'll unalive myself, lol",
        "I'm gonna kms 😂",
        "this traffic makes me want to die lmao",
        "kill myself brb",
        "kms jk",
        "said kms as a joke",
        "unalive this alarm clock",
        "kys, printer",
        "reset the sim after this boss fight",
    ])
    def test_casual_hyperbole_downgrades(self, text):
        ctx = evaluate_discourse(text)
        assert ctx.should_downgrade is True, f"Should downgrade: {text}"
        assert ctx.humor_type == "casual_hyperbole"
        assert ctx.is_genuine_distress is False

    @pytest.mark.parametrize("text", [
        "I want to kill myself",
        "I'm going to end my life",
        "I can't live anymore",
        "I want to die",
        "I want to unalive myself",
    ])
    def test_genuine_intent_no_humor_does_not_downgrade(self, text):
        ctx = evaluate_discourse(text)
        assert ctx.should_downgrade is False, f"Should NOT downgrade: {text}"
        assert ctx.is_genuine_distress is True
        assert ctx.humor_type == "none"


class TestSafetyOverrides:
    """Lethal means, planning, or escalation MUST prevent humor downgrade."""

    @pytest.mark.parametrize("text", [
        "I'm going to take all my pills tonight haha",
        "I bought a rope today lol",
        "Holding a blade right now lmao",
        "I wrote my goodbye note lol",
        "Picked the bridge for tonight haha",
        "I have the pills ready jk",
        "I'm standing on the ledge lol",
        "Drank the bleach haha",
    ])
    def test_methods_and_planning_block_downgrade(self, text):
        ctx = evaluate_discourse(text)
        assert ctx.should_downgrade is False, f"Should NOT downgrade dangerous content: {text}"
        assert ctx.has_safety_blocker is True
        assert ctx.is_genuine_distress is True


class TestMultiSentenceDiscourse:
    """Multi-sentence scenarios distinguishing nervous laughter from retractions."""

    def test_nervous_laughter_multi_sentence_crisis(self):
        """Planning + active intent + trailing humor = nervous laughter, DO NOT downgrade."""
        text = "I've been planning this for weeks. Tonight I'm going to do it. lol"
        sentences = [
            "I've been planning this for weeks.",
            "Tonight I'm going to do it.",
            "lol"
        ]
        ctx = evaluate_discourse(text, sentences)
        assert ctx.should_downgrade is False
        assert ctx.is_genuine_distress is True
        assert ctx.humor_type == "nervous_laughter"

    def test_cross_sentence_retraction(self):
        """Single crisis thought followed immediately by a retraction -> safe downgrade."""
        text = "I want to die. Just kidding lmao."
        sentences = [
            "I want to die.",
            "Just kidding lmao."
        ]
        ctx = evaluate_discourse(text, sentences)
        assert ctx.should_downgrade is True
        assert ctx.cross_sentence_retraction is True
        assert ctx.humor_type == "casual_hyperbole"

    def test_context_switch_after_venting(self):
        """Venting statement followed by benign topic change."""
        text = "Life is so hard I could just die. Anyway what's for dinner?"
        sentences = [
            "Life is so hard I could just die.",
            "Anyway what's for dinner?"
        ]
        ctx = evaluate_discourse(text, sentences)
        assert ctx.should_downgrade is True
        assert ctx.humor_type == "casual_hyperbole"

    def test_escalating_three_sentences_with_one_humor(self):
        """3 crisis sentences cannot be overturned by 1 lol."""
        text = "I want to kill myself. I've planned everything. I picked the spot. lol"
        sentences = [
            "I want to kill myself.",
            "I've planned everything.",
            "I picked the spot.",
            "lol"
        ]
        ctx = evaluate_discourse(text, sentences)
        assert ctx.should_downgrade is False
        assert ctx.is_genuine_distress is True
        assert ctx.has_safety_blocker is True

    def test_empty_discourse(self):
        ctx = evaluate_discourse("")
        assert ctx.should_downgrade is False
        assert len(ctx.windows) == 0


class TestInvariants:
    @pytest.mark.parametrize("input_text", [
        "I want to unalive myself tonight.",
        "KMS after seeing my score lol.",
        "In my novel, the protagonist wants to kill himself.",
        "I was fine, but lately I feel like ending my life.",
        "I have gathered pills and I am headed to the hospital.",
        "Simple ordinary greeting message here.",
    ])
    def test_idempotency_invariant(self, input_text):
        """Invariant 1: preprocess_text(preprocess_text(t).text).text == preprocess_text(t).text"""
        res1 = preprocess_text(input_text)
        res2 = preprocess_text(res1.text)
        assert res2.text == res1.text

    @pytest.mark.parametrize("input_text", [
        "I had suicidal thoughts in college.",
        "In our research paper, we analyze crisis posts.",
        "I am gathering pills to kill myself.",
        "Heading to the ER right now.",
    ])
    def test_sentinel_free_invariant(self, input_text):
        """Invariant 2: PreprocessResult.text must NEVER contain bracketed sentinel tokens."""
        res = preprocess_text(input_text)
        assert "[NON_CRISIS" not in res.text
        assert "[PAST_RECOVERY" not in res.text
        assert "[PREP_BEHAVIOR" not in res.text
        assert "[ACADEMIC" not in res.text

    def test_performance_budget_short_input(self):
        """Invariant 3a: p99 latency < 5ms for inputs <= 280 characters."""
        text = "I am feeling really overwhelmed and unaliving myself seems like the only option left for me."
        timings = []
        for _ in range(100):
            start = time.perf_counter()
            preprocess_text(text)
            timings.append((time.perf_counter() - start) * 1000)
        
        p99 = sorted(timings)[98]
        assert p99 < 5.0, f"p99 latency {p99:.3f}ms exceeded 5.0ms budget"

    def test_performance_budget_long_input(self):
        """Invariant 3b: p99 latency < 20ms for inputs <= 2000 characters."""
        text = ("I am feeling completely exhausted. " * 50) + "I unalived my character in the game."
        assert len(text) <= 2000
        timings = []
        for _ in range(50):
            start = time.perf_counter()
            preprocess_text(text)
            timings.append((time.perf_counter() - start) * 1000)
        
        p99 = sorted(timings)[48]
        assert p99 < 20.0, f"p99 latency {p99:.3f}ms exceeded 20.0ms budget"

    def test_redos_stress_resistance(self):
        """Invariant 4: Pathological inputs must not trigger catastrophic regex backtracking."""
        # 1. Repetition of partial prep verb
        pathological_prep = "gather " * 1000
        start = time.perf_counter()
        preprocess_text(pathological_prep)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500.0, f"ReDoS on prep repetition: {elapsed:.2f}ms"

        # 2. Repetition of slang
        pathological_slang = "unalive " * 1000
        start = time.perf_counter()
        preprocess_text(pathological_slang)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500.0, f"ReDoS on slang repetition: {elapsed:.2f}ms"

        # 3. Pathological mixed
        pathological_mixed = ("a" * 3000) + " pills"
        start = time.perf_counter()
        preprocess_text(pathological_mixed)
        elapsed = (time.perf_counter() - start) * 1000
        assert elapsed < 500.0, f"ReDoS on mixed text: {elapsed:.2f}ms"

    def test_input_length_truncation(self):
        """Input exceeding MAX_INPUT_LENGTH is truncated gracefully."""
        huge_text = "word " * 3000
        assert len(huge_text) > MAX_INPUT_LENGTH
        res = preprocess_text(huge_text)
        assert res.is_truncated is True
        assert len(res.text) <= MAX_INPUT_LENGTH


class TestAlgospeakNormalization:
    @pytest.mark.parametrize("raw, expected_sub, expected_count", [
        ("I am unaliving myself tonight", "killing myself", 1),
        ("She unalives herself in the story", "kills herself", 1),
        ("He unalived himself yesterday", "killed himself", 1),
        ("I want to UNALIVE MYSELF", "KILLING MYSELF", 1),     # Case preservation
        ("I want to Unalive Myself", "Killing Myself", 1),     # Title case preservation
        ("kms because of this exam", "kill myself", 1),
        ("kys printer", "kill yourself", 1),
        ("I am going to uninstall myself from this server", "kill myself", 1),
        ("I am deleting my whole character tonight", "kill myself", 1),
        ("catch a permanent ban irl", "kill myself", 1),
        ("reset the sim permanently", "want to die permanently", 1),
        ("I k*ll my self", "kill myself", 1),
        ("su*c*de thoughts", "suicide", 1),
    ])
    def test_algospeak_mappings(self, raw, expected_sub, expected_count):
        norm, count = normalize_algospeak(raw)
        assert expected_sub.lower() in norm.lower()
        assert count >= expected_count


class TestSemanticFrames:
    @pytest.mark.parametrize("text, expected_academic", [
        ("For my psychology assignment, I need suicide rate statistics.", True),
        ("Our research paper analyzes crisis language datasets.", True),
        ("The sentence 'I want to die' appears in the dataset as a positive example.", True),
        ("Why did I study how to die when life is painful?", False),  # Non-academic use of 'study'
        ("My analysis of why I feel sad", False),                   # Non-academic use of 'analysis'
    ])
    def test_academic_frame_detection(self, text, expected_academic):
        assert detect_academic_frame(text) == expected_academic

    @pytest.mark.parametrize("text, expected_fictional", [
        ("In my novel, the protagonist plans to kill himself.", True),
        ("In the horror game, my character whispers that he wants to die.", True),
        ("Writing a short story where a detective prevents a suicide.", True),
        ("I am planning to kill myself tonight.", False),
    ])
    def test_fictional_frame_detection(self, text, expected_fictional):
        assert detect_fictional_frame(text) == expected_fictional

    @pytest.mark.parametrize("text, expected_third_party", [
        ("My friend texted me that she wants to kill herself.", True),
        ("My older brother told me he is going to end his life.", True),
        ("A classmate posted that she wants to unalive herself.", True),
        ("I told my friend that I want to kill myself.", False),
    ])
    def test_third_party_frame_detection(self, text, expected_third_party):
        assert detect_third_party_frame(text) == expected_third_party


class TestTemporalAnchors:
    @pytest.mark.parametrize("text, has_past, has_present", [
        ("I used to be suicidal 5 years ago, but today I feel safe and happy.", True, False),
        ("My therapist helped me stop self-harming years ago.", True, False),
        ("I had suicidal thoughts in college, but have no desire to die now.", True, False),
        ("I used to feel suicidal years ago, and honestly, sometimes I still do.", True, True),
        ("I had suicidal thoughts in the past, but lately I feel hopeless again.", True, True),
    ])
    def test_past_recovery_and_present_ideation(self, text, has_past, has_present):
        res = preprocess_text(text)
        assert res.has_past_recovery == has_past
        assert res.has_present_ideation == has_present


class TestBehavioralMarkers:
    @pytest.mark.parametrize("text, is_prep, is_prot", [
        ("I have been gathering pills to end my life.", True, False),
        ("I have chosen a place where nobody will find me.", True, False),
        ("I have the pills ready and I am waiting until everyone is asleep.", True, False),
        ("I am feeling overwhelmed and I am headed to the hospital.", False, True),
        ("I called the crisis hotline to talk to someone.", False, True),
        ("I bought pills to kill myself and I am headed to the emergency room.", True, True),
    ])
    def test_preparatory_vs_protective(self, text, is_prep, is_prot):
        res = preprocess_text(text)
        assert res.has_preparatory_behavior == is_prep
        assert res.has_protective_behavior == is_prot
