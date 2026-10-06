# MindGuard Crisis System Report

> **Last Updated:** September 2026  
> **Status:** Current — reflects the live codebase as of this revision.  
> Previous content below the "Stale Historical Claims" heading has been removed and replaced with verified current information.

---

## 1. Purpose

This document describes how MindGuard detects crisis and suicidal language, the models and rule engines used, the runtime workflow, recent safety fixes, test results, limitations, and how to run all tests.

---

## 2. Project Links

| Artefact | Path |
|---|---|
| Backend entry | [server/app.py](../server/app.py) |
| Deterministic rule engine | [server/services/crisis_rules.py](../server/services/crisis_rules.py) |
| Intent & regex patterns | [server/services/intent_rules.py](../server/services/intent_rules.py) |
| Precedence arbitrator | [server/services/precedence_arbitrator.py](../server/services/precedence_arbitrator.py) |
| Temporal engine | [server/services/temporal_engine.py](../server/services/temporal_engine.py) |
| Discourse evaluator | [server/services/discourse_evaluator.py](../server/services/discourse_evaluator.py) |
| Semantic concept grammars | [server/services/semantic_concepts.py](../server/services/semantic_concepts.py) |
| Text generalizer | [server/services/generalizer.py](../server/services/generalizer.py) |
| HuggingFace ML orchestration | [server/services/huggingface_service.py](../server/services/huggingface_service.py) |
| LLM service | [server/services/llm_service.py](../server/services/llm_service.py) |
| Crisis resources | [server/services/crisis_resources.py](../server/services/crisis_resources.py) |
| Backend tests | [tests/backend/](../tests/backend/) |
| Frontend tests | [client/src/\_\_tests\_\_/](../client/src/__tests__/) |
| Stress benchmark | [scripts/benchmarks/benchmark_stress_1000.py](../scripts/benchmarks/benchmark_stress_1000.py) |
| Release gate | [scripts/release_gate_crisis.py](../scripts/release_gate_crisis.py) |
| Evaluation artefacts | [artifacts/](../artifacts/) |

---

## 3. High-Level Architecture

```
User message (HTTP POST /api/chat)
         │
         ▼
  ┌─────────────────────────────┐
  │  1. Preprocessing           │  crisis_rules._normalize, generalizer.preprocess_text
  └──────────────┬──────────────┘
                 │
                 ▼
  ┌─────────────────────────────┐
  │  2. Third-party Routing     │  If message is about someone else → third_party_guidance
  └──────────────┬──────────────┘
                 │
                 ▼
  ┌─────────────────────────────┐
  │  3. Tier 1 — Deterministic  │  evaluate_crisis() per-sentence pattern matching
  │     Rule Engine             │  + Precedence Arbitrator (arbitrate())
  └──────────────┬──────────────┘
                 │
        is_crisis?  bypass_triggered?
         /                 \
        ▼                   ▼
 HIGH_CRISIS          4. Bypass Gating
 response             (suppress ML/LLM)
 (skips all                │
  generative          not bypassed
  paths)                   │
                           ▼
                  ┌─────────────────┐
                  │ 5. Tier 2 — ML  │  huggingface_service.analyze_user_message
                  │   Classifier    │
                  └────────┬────────┘
                           │
                  crisis from ML?
                   /             \
                  ▼               ▼
           HIGH_CRISIS      6. Tier 3 — LLM
           response         (Gemini → Ollama
                             → offline KB)
```

**Safety invariant**: High-risk messages are returned at Step 3 with the SAFETY_RESPONSE_TEMPLATE. They never reach Gemini, Ollama, RAG, or any generative path.

---

## 4. Crisis Rule Engine

### Pattern Categories

| Category | Severity | Description |
|---|---|---|
| `explicit_suicidal_intent` | 5 (imminent) | Direct statements of intent to die or kill oneself |
| `lethal_means_and_preparation` | 5 (imminent) | Acquiring or using means; ingestion of lethal doses |
| `active_escalation_in_progress` | 5 (imminent) | Real-time crisis in progress (blade in hand, pills swallowed) |
| `burden_and_goodbye` | 4 (high) | Farewell statements, note-writing, burden expressions |
| `subtle_slang_and_informal` | 4 (high) | KMS, unalive, self-delete, log off for good |
| `self_harm_and_cutting` | 4 (high) | NSSI and cutting behaviours |
| `indirect_implicit_distress` | 3 (moderate) | No-future, no-way-out, don't-want-to-wake-up expressions |

### Bypass / Suppression Layers (applied per sentence)

1. Contrast clause handling — genuine crisis in a leading clause prevents idiom bypass
2. Grammatical negation ("I am not suicidal", "I don't want to die")
3. Past historical reflection with confirmed resolution
4. Academic / research context
5. Media / third-person / fictional narrative context
6. Idiomatic hyperbole (standalone — "This exam is killing me")
7. Slang hyperbole dampener (KMS in humorous context with LOL/jk)
8. Protective contrast ("want to die but won't because of my dog")
9. Non-crisis situational expressions (thesis, exam stress without crisis markers)

### Precedence Arbitrator

`precedence_arbitrator.arbitrate()` combines deterministic pattern results with signals from:
- **Temporal engine** — past anchor, confirmed resolution, acute relapse
- **Discourse evaluator** — sarcasm/hyperbole detection across turns
- **Semantic concept grammars** — fatal sleep, concealment, irreversible exit

Numbered rules (highest priority first): Third-party routing → Fail-safe floor (active escalation) → Relapse escalation → Preparatory behaviour → Semantic concept → Discourse modulation → Safe past narrative → Academic/fictional bypass → Ambiguous past → Passthrough → Default.

---

## 5. Recent Safety Fixes

### Fix 1 — High-Risk Medication-Ingestion Detection (Task 1)

**Problem:** Phrases such as _"I took a whole bottle of pills"_, _"I swallowed a whole bottle of tablets"_, and _"I took all my medication"_ were not detected as crisis. The existing `_LETHAL_MEANS_AND_PREPARATION` pattern (line 338) required a numeric quantifier or a specific keyword between the verb and substance noun, missing the `a whole bottle of …` and `all my …` forms.

**Fix:** Added two conservative, first-person–anchored patterns to `_LETHAL_MEANS_AND_PREPARATION`:
1. First-person verb (`took|ingested|consumed|swallowed|downed|popped`) + explicit quantity (`a whole bottle of …`, `the entire bottle of …`, `all my/the …`) + substance noun.
2. First-person verb (`took|ingested|consumed`) + `all my/of my/the` + substance noun.

**False-positive protection:** Both patterns require the first-person subject and an explicit quantity marker. Ordinary statements ("I forgot to take my pills", "I take two pills every morning") do not match.

**Regression tests:** `test_whole_bottle_medication_ingestion_crisis` and `test_benign_medication_statements_no_false_positive` in `tests/backend/test_safety_and_crisis_engine.py`.

---

### Fix 2 — Unsafe Hyperbole Precedence (Task 2)

**Problem:** The message _"I want to die, but this exam is killing me"_ was incorrectly bypassed as an idiomatic expression. `_contextual_bypass_reason()` split on `but/however/though/yet`, detected genuine crisis in the **first** clause (setting `allow_idiom_bypass = False`), but then step (3) still ran the full-text idiom search and returned `"idiomatic_or_hyperbolic_expression"`.

**Fix:** When `idx == 0` and `part_has_crisis` is True, the function now returns `None` immediately — the genuine crisis in the leading clause prevents any idiom bypass from firing for the whole message.

**Safe cases preserved:**
- `"This exam is killing me"` — no contrast split, idiom bypass fires correctly ✓
- `"This exam is killing me, but I do not want to die"` — first clause is idiom (no crisis), second clause is negation → safe ✓
- `"I want to die, but this exam is killing me"` → `None` returned → HIGH_CRISIS ✓

**Regression tests:** `test_crisis_in_lead_clause_not_downgraded_by_idiom`, `test_standalone_idiom_remains_safe`, `test_negation_in_followup_clause_remains_safe`, `test_mixed_risk_sentences_correct_precedence` in `tests/backend/test_safety_and_crisis_engine.py`.

**Safety precedence policy (canonical):** A direct, un-negated, first-person expression of suicidal desire or intent is never downgraded by an idiom, metaphor, or hyperbole appearing anywhere else in the same message.

---

## 6. Stress Benchmark Schema

### File: `tests/data/crisis_test_utterances.csv`

**Columns:** `id, text, category, severity`

> [!IMPORTANT]  
> The benchmark script `scripts/benchmarks/benchmark_stress_1000.py` previously used a non-existent `label` column (`df["label"] == "suicide"`), which caused a `KeyError` at runtime. This has been corrected.

**Severity scale (1–5):**

| severity | meaning |
|---|---|
| 1 | Idiom / non-crisis expression |
| 2 | Low-ambiguity non-crisis |
| 3 | Moderate risk (indirect distress, subtle slang) |
| 4 | High risk (explicit intent, burden/goodbye) |
| 5 | Imminent risk (lethal preparation, active escalation) |

**`expected_crisis` derivation rule (conservative — favours recall):**

```python
expected_crisis = (severity >= 3) AND (category != "idiom_non_crisis")
```

This is consistent with the `PatternCategory` severity thresholds in `crisis_rules.py`. No rows are silently excluded.

---

## 7. LLM Service — Connectivity Circuit Breaker

### Problem (Task 4)
When Gemini is unreachable due to a network outage, invalid API key, or SSL error, the original code tried all 4 candidate models sequentially, each hitting the full `~1.5 s` timeout. Worst case: **6 seconds** of blocked latency before falling back to Ollama or the offline knowledge base.

The existing per-model quota circuit breaker (60 s per model on 429/resource_exhausted) did not cover connection/config errors.

### Fix
Added a **module-level connectivity circuit breaker** (`_GEMINI_CONNECTIVITY_BROKEN_UNTIL: float`) in `server/services/llm_service.py`:

- `_call_gemini()` catches `ConnectionError`, `OSError`, `ssl`, `api_key`, `permission_denied`, `unauthenticated`, and `transport` errors and raises the internal `_GeminiConnectivityError` sentinel + sets the module flag for 60 s.
- `generate_llm_response()` checks the flag **before the model loop** and skips Gemini entirely if active.
- The inner model loop catches `_GeminiConnectivityError` and `break`s immediately (instead of continuing to the next model).
- After 60 s the flag expires and Gemini is retried normally.
- Quota errors (429/resource_exhausted) continue to use the existing per-model breaker — behaviour unchanged.

**Tests:** `tests/backend/test_llm_circuit_breaker.py`.

---

## 8. Crisis Modal Safety Telemetry

### Problem (Task 5)
`CrisisModal.tsx` recorded `safe_for_now` telemetry (`onSafetyStatus?.("safe_for_now")`) on three passive dismissal events:
- The **X close button** `onClick`
- The **backdrop click** `onClick` (clicking outside the modal panel)

This inflated `safe_for_now` counts with non-intentional confirmations. The dedicated **"I'm safe for now — return to chat"** button was the only intended source.

### Fix
Removed `onSafetyStatus?.("safe_for_now")` from:
- Close button `onClick` (now calls only `onClose()`)
- Backdrop `onClick` (now calls only `onClose()`)

The Escape key handler already called only `onClose()` — no change needed.  
The explicit "I'm safe for now" button (line ~696) remains the sole place `onSafetyStatus("safe_for_now")` fires.

**Tests:** Four new tests in `client/src/__tests__/CrisisModal.test.tsx` covering close button, backdrop click, Escape key, and the explicit confirmation button.

---

## 9. Limitations & Risk Analysis

| Limitation | Detail |
|---|---|
| Paraphrase coverage | Regex patterns do not generalise to all reformulations. ML Tier 2 provides partial coverage for unseen phrasing. |
| Multilingual | Roman Urdu/Hindi patterns are included; other languages are not covered without normalization/translation. |
| Negation & contrast | Complex multi-clause sentences with unusual syntax may misroute. Regression test suite covers known edge cases. |
| Adversarial evasion | Deliberate character substitutions are handled by `text_normalizer`; novel obfuscation may be missed. |
| ML model drift | HuggingFace classifier performance depends on training distribution; periodic re-evaluation is recommended. |
| LLM dependency | Gemini API availability affects Tier 3 response quality. The circuit breaker and offline KB ensure safe fallback. |

---

## 10. How to Run All Tests

Run from the **repository root** (`e:\FYP\current` or equivalent):

```bash
# 1. Backend unit & integration tests
python -m pytest tests/backend -v

# 2. TypeScript type check
npm run type-check --prefix client

# 3. Frontend component tests
npm test --prefix client -- --run

# 4. Frontend production build
npm run build --prefix client

# 5. Crisis release gate (deterministic safety contract)
python scripts/release_gate_crisis.py

# 6. 1,000-prompt stress benchmark
python scripts/benchmarks/benchmark_stress_1000.py
```

### Expected Outcomes

| Command | Expected |
|---|---|
| `pytest tests/backend -v` | All tests pass; 0 errors |
| `npm run type-check` | No TypeScript errors |
| `npm test -- --run` | All tests pass |
| `npm run build` | Build succeeds; dist/ populated |
| `release_gate_crisis.py` | Gate PASSED |
| `benchmark_stress_1000.py` | Runs to completion; metrics JSON written to `artifacts/` |

---

## 11. Acceptance Criteria

| Criterion | Target |
|---|---|
| Crisis recall on held-out positive set | ≥ 0.95 |
| Precision | ≥ 0.60 |
| End-to-end latency (rule-only path) | < 500 ms (median) |
| End-to-end latency (with ML inference) | < 2 s |
| Gemini fallback latency on connectivity failure | < 200 ms (circuit breaker active) |
| `safe_for_now` telemetry accuracy | Fires only on explicit button click |

---

## 12. Traceability

| Requirement | Implementing file(s) | Test(s) |
|---|---|---|
| Medication ingestion detection | `crisis_rules.py _LETHAL_MEANS_AND_PREPARATION` | `test_whole_bottle_medication_ingestion_crisis` |
| Hyperbole precedence | `crisis_rules._contextual_bypass_reason` | `test_crisis_in_lead_clause_not_downgraded_by_idiom` |
| Connectivity circuit breaker | `llm_service._call_gemini`, `generate_llm_response` | `test_llm_circuit_breaker.py` |
| Safe telemetry | `CrisisModal.tsx` close/backdrop/Escape | `CrisisModal.test.tsx` Task 5 tests |
| Benchmark schema | `benchmark_stress_1000.py` | Manual run |
| Deterministic bypass contract | `crisis_rules`, `precedence_arbitrator` | `release_gate_crisis.py`, `test_safety_and_crisis_engine.py` |