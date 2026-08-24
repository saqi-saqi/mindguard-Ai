"""
precedence_arbitrator.py
========================

Central precedence arbitrator for MindGuard multi-tier crisis detection.

Combines signals from:
- Pattern matching (crisis_rules.py)
- Temporal state extraction (temporal_engine.py)
- Windowed discourse evaluation (discourse_evaluator.py)
- Semantic concept grammars (semantic_concepts.py)
- Generalizer frame detection (generalizer.py PreprocessResult)

Replaces sequential ad-hoc if/elif chains with explicit, documented,
numbered precedence rules and a full reasoning audit trail.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from .temporal_engine import TemporalState
from .discourse_evaluator import DiscourseContext
from .semantic_concepts import ConceptMatch


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class ArbitrationInput:
    """Consolidated input payload for precedence arbitration."""
    # Deterministic pattern matching results
    base_severity: int = 0                  # 1-5 (from PatternCategory)
    base_risk_level: str = "none"           # "imminent" | "high" | "moderate" | "none"
    is_base_crisis: bool = False
    matched_categories: List[str] = field(default_factory=list)
    matched_phrases: List[str] = field(default_factory=list)
    bypass_reason: Optional[str] = None
    
    # Modular extractor results
    temporal: Optional[TemporalState] = None
    discourse: Optional[DiscourseContext] = None
    semantic_concepts: List[ConceptMatch] = field(default_factory=list)
    
    # Generalizer semantic frame flags
    is_academic: bool = False
    is_fictional: bool = False
    is_third_party: bool = False
    has_preparatory_behavior: bool = False
    has_protective_behavior: bool = False
    has_first_person_override: bool = False


@dataclass
class ArbitrationResult:
    """Final decision output from precedence arbitration."""
    is_crisis: bool
    risk_level: str                          # "imminent" | "high" | "elevated" | "moderate" | "none"
    high_risk: bool = False
    imminent_risk: bool = False
    protective_factor: bool = False
    bypass_triggered: bool = False
    bypass_reason: Optional[str] = None
    source: str = "deterministic_rules"      # "deterministic_rules" | "contextual_bypass" | "third_party_guidance"
    confidence: float = 0.95
    rule_triggered: Optional[str] = None
    reasoning: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Arbitration Engine
# ---------------------------------------------------------------------------

def arbitrate(inp: ArbitrationInput) -> ArbitrationResult:
    """
    Arbitrate across all module signals using explicit numbered precedence.

    Precedence order (highest to lowest):
    1. THIRD-PARTY ROUTING: Third-party reports -> third_party_guidance (non-crisis)
    2. FAIL-SAFE FLOOR: Active escalation in progress -> imminent ALWAYS
    3. RELAPSE ESCALATION: Past anchor + acute relapse -> imminent
    4. PREPARATORY BEHAVIOR TRIAGE:
       - Prep + protective -> elevated (attenuated)
       - Prep alone -> imminent
    5. SEMANTIC CONCEPT MATCH:
       - Fatal sleep / Concealment / Irreversible exit -> escalate to imminent/high
       - Suppressed if safe past narrative or academic frame applies
    6. DISCOURSE MODULATION:
       - Sarcasm/hyperbole downgrade -> safe bypass (low/none)
       - Blocked if safety blocker present (means/planning/escalation)
    7. SAFE PAST NARRATIVE:
       - Past anchor + confirmed resolution and not relapse -> contextual_bypass
    8. ACADEMIC / FICTIONAL BYPASS:
       - Academic/fictional frame without first-person override -> contextual_bypass
    9. AMBIGUOUS PAST:
       - Past anchor without resolution and without relapse -> moderate / review
    10. PASSTHROUGH:
       - Return base pattern matching decision
    """
    reasoning: List[str] = []

    # 1. THIRD-PARTY ROUTING
    if inp.is_third_party:
        reasoning.append("Rule 1 (Third-party routing): Statement describes someone else in crisis.")
        return ArbitrationResult(
            is_crisis=False,
            risk_level="none",
            high_risk=False,
            imminent_risk=False,
            protective_factor=False,
            bypass_triggered=False,
            source="third_party_guidance",
            confidence=0.95,
            rule_triggered="third_party_crisis_reported",
            reasoning=reasoning,
        )

    # 2. FAIL-SAFE FLOOR: Active escalation in progress
    if "active_escalation_in_progress" in inp.matched_categories:
        reasoning.append("Rule 2 (Fail-safe floor): Active escalation in progress matched. Immediate crisis.")
        return ArbitrationResult(
            is_crisis=True,
            risk_level="imminent",
            high_risk=True,
            imminent_risk=True,
            protective_factor=inp.has_protective_behavior,
            bypass_triggered=False,
            source="deterministic_rules",
            confidence=0.98,
            rule_triggered="active_escalation_in_progress",
            reasoning=reasoning,
        )

    # 3. RELAPSE ESCALATION: Past recovery + acute relapse
    has_relapse = False
    if inp.temporal:
        has_relapse = inp.temporal.past_anchor.detected and inp.temporal.acute_relapse.detected

    if has_relapse:
        reasoning.append("Rule 3 (Relapse escalation): Acute relapse detected after past anchor. Elevating to imminent.")
        return ArbitrationResult(
            is_crisis=True,
            risk_level="imminent",
            high_risk=True,
            imminent_risk=True,
            protective_factor=False,
            bypass_triggered=False,
            source="deterministic_rules",
            confidence=0.95,
            rule_triggered="acute_relapse_after_recovery",
            reasoning=reasoning,
        )

    # 4. PREPARATORY BEHAVIOR TRIAGE
    if inp.has_preparatory_behavior:
        if inp.has_protective_behavior:
            reasoning.append("Rule 4a (Preparatory + protective): Preparatory means mitigated by protective help-seeking.")
            return ArbitrationResult(
                is_crisis=True,
                risk_level="elevated",
                high_risk=False,
                imminent_risk=False,
                protective_factor=True,
                bypass_triggered=False,
                source="deterministic_rules",
                confidence=0.95,
                rule_triggered="preparatory_behavior",
                reasoning=reasoning,
            )
        else:
            reasoning.append("Rule 4b (Preparatory alone): Preparatory behavior without protective factor. Imminent risk.")
            return ArbitrationResult(
                is_crisis=True,
                risk_level="imminent",
                high_risk=True,
                imminent_risk=True,
                protective_factor=False,
                bypass_triggered=False,
                source="deterministic_rules",
                confidence=0.95,
                rule_triggered="preparatory_behavior",
                reasoning=reasoning,
            )

    # 5. SEMANTIC CONCEPT MATCH
    active_concepts = [c for c in inp.semantic_concepts if c.detected]
    if active_concepts:
        # Check if academic/fictional frame overrides without first-person intent
        if (inp.is_academic or inp.is_fictional) and not inp.has_first_person_override:
            pass  # Let academic/fictional bypass handle it
        else:
            concept_names = [c.concept for c in active_concepts]
            reasoning.append(f"Rule 5 (Semantic concept match): Detected bounded concepts: {', '.join(concept_names)}.")
            return ArbitrationResult(
                is_crisis=True,
                risk_level="imminent" if "fatal_sleep" in concept_names or "concealment" in concept_names else "high",
                high_risk=True,
                imminent_risk=("fatal_sleep" in concept_names or "concealment" in concept_names),
                protective_factor=inp.has_protective_behavior,
                bypass_triggered=False,
                source="deterministic_rules",
                confidence=0.92,
                rule_triggered=concept_names[0],
                reasoning=reasoning,
            )

    # 6. DISCOURSE MODULATION: Sarcasm / Casual Hyperbole Downgrade
    if inp.discourse and inp.discourse.should_downgrade:
        reasoning.append(f"Rule 6 (Discourse modulation): Downgrade approved for {inp.discourse.humor_type}.")
        return ArbitrationResult(
            is_crisis=False,
            risk_level="none",
            high_risk=False,
            imminent_risk=False,
            protective_factor=inp.has_protective_behavior,
            bypass_triggered=True,
            bypass_reason="slang_hyperbole_dampener",
            source="contextual_bypass",
            confidence=0.85,
            reasoning=reasoning,
        )

    # 7. SAFE PAST NARRATIVE (Resolved)
    if inp.temporal and inp.temporal.past_anchor.detected:
        if inp.temporal.confirmed_resolution.detected and not inp.temporal.acute_relapse.detected:
            reasoning.append("Rule 7 (Safe past narrative): Past anchor with confirmed resolution and no relapse.")
            return ArbitrationResult(
                is_crisis=False,
                risk_level="none",
                high_risk=False,
                imminent_risk=False,
                protective_factor=inp.has_protective_behavior,
                bypass_triggered=True,
                bypass_reason="past_historical_reflection_with_confirmed_resolution",
                source="contextual_bypass",
                confidence=0.90,
                reasoning=reasoning,
            )

    # 8. ACADEMIC / FICTIONAL BYPASS
    if (inp.is_academic or inp.is_fictional) and not inp.has_first_person_override:
        bypass_tag = "academic_or_research_context" if inp.is_academic else "fictional_narrative_context"
        reasoning.append(f"Rule 8 (Contextual frame bypass): Safe {bypass_tag} without personal crisis intent.")
        return ArbitrationResult(
            is_crisis=False,
            risk_level="none",
            high_risk=False,
            imminent_risk=False,
            protective_factor=inp.has_protective_behavior,
            bypass_triggered=True,
            bypass_reason=bypass_tag,
            source="contextual_bypass",
            confidence=0.90,
            reasoning=reasoning,
        )

    # 9. AMBIGUOUS PAST (Past history without explicit resolution, but no current relapse)
    if inp.temporal and inp.temporal.past_anchor.detected and not inp.temporal.acute_relapse.detected and not inp.is_base_crisis:
        reasoning.append("Rule 9 (Ambiguous past reflection): Historical mention without active crisis markers.")
        return ArbitrationResult(
            is_crisis=False,
            risk_level="none",
            high_risk=False,
            imminent_risk=False,
            protective_factor=inp.has_protective_behavior,
            bypass_triggered=True,
            bypass_reason="past_historical_reflection",
            source="contextual_bypass",
            confidence=0.85,
            reasoning=reasoning,
        )

    # 10. PASSTHROUGH: Deterministic Pattern Match Result
    if inp.is_base_crisis:
        risk_level = inp.base_risk_level
        reasoning.append(f"Rule 10 (Deterministic passthrough): Matched crisis categories with severity {inp.base_severity}.")
        return ArbitrationResult(
            is_crisis=True,
            risk_level=risk_level,
            high_risk=(risk_level in ("imminent", "high")),
            imminent_risk=(risk_level == "imminent"),
            protective_factor=inp.has_protective_behavior,
            bypass_triggered=False,
            source="deterministic_rules",
            confidence=0.95 if risk_level in ("imminent", "high") else 0.85,
            rule_triggered=inp.matched_categories[0] if inp.matched_categories else None,
            reasoning=reasoning,
        )

    # 11. DEFAULT: Non-crisis / Bypass from sentence findings
    if inp.bypass_reason:
        reasoning.append(f"Rule 11 (Sentence bypass): Bypassed by reason: {inp.bypass_reason}.")
        return ArbitrationResult(
            is_crisis=False,
            risk_level="none",
            high_risk=False,
            imminent_risk=False,
            protective_factor=inp.has_protective_behavior,
            bypass_triggered=True,
            bypass_reason=inp.bypass_reason,
            source="contextual_bypass",
            confidence=0.90,
            reasoning=reasoning,
        )

    reasoning.append("Default fallback: No deterministic rules triggered.")
    return ArbitrationResult(
        is_crisis=False,
        risk_level="none",
        high_risk=False,
        imminent_risk=False,
        protective_factor=inp.has_protective_behavior,
        bypass_triggered=False,
        source="deterministic_rules",
        confidence=0.80,
        reasoning=reasoning,
    )
