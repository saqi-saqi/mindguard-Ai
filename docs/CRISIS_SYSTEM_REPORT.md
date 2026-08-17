# MindGuard Crisis System Report

Purpose
- This report documents how MindGuard detects crisis/suicidal language, the models and rule engines used, the runtime workflow, test results, limitations, and recommended next steps for hardening and evaluation. Use this for review with external evaluators (e.g., Clue Sonnet model) or for audit.

**Project Links**
- Backend entry: [server/app.py](server/app.py)
- Rule engine: [server/services/crisis_rules.py](server/services/crisis_rules.py)
- Intent & regex patterns: [server/services/intent_rules.py](server/services/intent_rules.py)
- Hugging Face / local model orchestration: [server/services/huggingface_service.py](server/services/huggingface_service.py)
- LLM orchestration: [server/services/llm_service.py](server/services/llm_service.py)
- Crisis resources: [server/services/crisis_resources.py](server/services/crisis_resources.py)
- Test harnesses: [tests/](tests/), [server/tests/](server/tests/), [tests/backend/](tests/backend/)
- SRS and policy docs: [extras/docs/PRIVACY_AND_SECURITY.md](extras/docs/PRIVACY_AND_SECURITY.md), [extras/docs/CRISIS_RESOURCES_MAINTENANCE.md](extras/docs/CRISIS_RESOURCES_MAINTENANCE.md)
- ML artifacts & evaluation: [artifacts/](artifacts/)

**High-level System Architecture**
- **Frontend**: React app (client/src) collects messages and posts to `/api/chat`.
- **Backend API**: Flask app ([server/app.py](server/app.py)) manages auth, persistence, analytics and chat pipeline.
- **Processing pipeline (per message)**:
  1. Receive message (HTTP POST).
  2. Basic normalization & intent quick-check via `intent_rules`.
  3. Deterministic rule evaluation with `crisis_rules` (per-sentence splitting, negation/context bypass, category matching).
  4. If deterministic rules escalate -> trigger crisis protocol (safety response template + resource list) and bypass LLM transmission.
  5. If not escalated, optionally call Hugging Face models (sentiment/intent classifiers) and/or LLMs (Gemini → Ollama → local fallback) via `huggingface_service` and `llm_service`.
  6. Record events (redaction applied per privacy policy) and return response to user.

**Crisis Rule Engine (deterministic)**
- Location: [server/services/crisis_rules.py](server/services/crisis_rules.py)
- Design
  - Rule categories (PatternCategory): `explicit_suicidal_intent`, `indirect_implicit_distress`, `burden_and_goodbye`, `lethal_means_and_preparation`, `subtle_slang_and_informal`, `self_harm_and_cutting`, `active_escalation_in_progress`.
  - Per-sentence evaluation with `_split_sentences` and `_normalize`.
  - Contextual bypasses: negation, past-historical reflection, academic/media context, idiomatic hyperbole, non-crisis situational expressions.
  - First-person-present overrides ensure unambiguous present intent is not bypassed by contextual patterns.
- Output: `evaluate_crisis`/`evaluate_deterministic_crisis` returns structured payload including `is_crisis`, `risk_level`, `matched_categories`, `bypass_reason`, and a `safety_message` template.

**ML & LLM Components**
- `huggingface_service.py` orchestrates local or HF-hosted classifiers (sentiment, intent). A joblib artifact `artifacts/crisis_detector.joblib` is included for an ML-based crisis detector.
- `llm_service.py` preferentially calls Google Gemini (when API key available), falls back to local Ollama, then to offline rule/ML fallbacks. Guardrails and a safety floor are enforced to avoid risky generations.
- Artifacts and metrics: check `artifacts/` for classifier metrics (intent_classifier.metrics.json, sentiment_classifier.metrics.json, crisis_detector.metrics.json).

**Testing & Observed Results (executed tests / example runs)**
- I ran the project's test suite in this environment (pytest) and executed a small representative rule-based script (`run_crisis_cases.py`).
- Representative rule-run results (sample): many explicit English goodbye/will/possession patterns are detected (e.g., "I wrote a goodbye note and deleted my accounts." → `high`). Several other high-risk utterances were not detected by pure regex engine, including overdose phrases and romanized-Urdu phrases. See failing examples below.
- Example false negatives observed in deterministic run:
  - "I am not safe with myself tonight." → not flagged
  - "I took too many pills." → not flagged
  - "I swallowed a bottle of tablets." → not flagged
  - Romanized examples such as "Mujhe mar jana hai." → not flagged
- Tests: the repo contains unit/regression tests under `tests/backend/` and `server/tests/`. The exhaustive test run reported a mix of passes and failures; several `test_crisis_rules` cases failed on the phrases above.

**Limitations & Risk Analysis**
- Deterministic regex limitations:
  - High chance of false negatives for paraphrases, misspellings, transliterations, and code-switching.
  - Multilingual coverage is limited unless normalized/translated first.
  - Negation and contrast handling is fragile for complex sentences.
- ML/LLM limitations:
  - ML models can generalize, but require labeled data representing the target distribution and must be tuned for high recall.
  - External LLM calls raise privacy and availability concerns; SRS specifies crisis bypass before sending data to Gemini.

**Recommended Improvements (prioritized)**
1. Short term (quick wins)
   - Add targeted regexes for overdose/self-harm verbs and common romanized phrases identified in failing tests.
   - Add language detection + fallback translation (e.g., `langdetect` + translation API or offline Moses/OPUS models) before rule evaluation.
   - Expand unit tests to include every failing phrase observed; add to `tests/backend/test_crisis_rules.py` as regression cases.
2. Medium term
   - Build an ensemble: combine the deterministic rules with a fine-tuned binary classifier (RoBERTa/DistilBERT) trained to prioritize recall.
   - Use the `artifacts/crisis_detector.joblib` as a starting point and evaluate on a held-out crisis corpus; tune thresholds.
   - Implement human-in-the-loop review for borderline predictions and use active learning to update training data.
3. Long term
   - Continuous evaluation pipeline: automated dataset + metrics tracking, drift detection, and periodic re-training.
   - Monitoring & alerting for model degradation, false-negative clusters, and language coverage gaps.

**Acceptance Criteria (suggested additions to SRS)**
- Minimum Recall: 0.95 on held-out crisis-positive test set (measure by language cohort).
- Precision: ≥ 0.6 (balanced to limit human reviewer overload); tune thresholds by cohort.
- Response latency: median end-to-end < 500 ms for rule-only flow; < 2s with ML inference depending on deployment.
- Logging policy: all escalations must store a redacted snapshot with `request_id`, `timestamp`, `matched_categories`, and audit trail.

**Traceability Recommendations**
- Add a Requirements Traceability Matrix (RTM) mapping SRS items to code modules and test files. Example columns: Requirement ID → Implementing File(s) → Test(s) → Acceptance Criteria → Artifact (metrics file).
- Link the existing metrics files in `artifacts/` into the SRS and RTM.

**Suggested Next Steps I Can Do (no code changes unless you approve)**
- Produce an RTM markdown file mapping SRS → code → tests.
- Generate a CSV/JSON of false negatives from batch runs to guide rule or training improvements.
- Prepare a patch with conservative regex additions (if you allow edits) and re-run the representative cases.

Repro commands (run from repo root)

```
# optional: create venv
python -m venv .venv
.venv\Scripts\Activate.ps1

# install minimal test deps (avoid heavy ML packages if you only want rule tests)
pip install pytest pytest-mock mongomock requests

# run unit tests
python -m pytest -q

# run the representative deterministic cases
python run_crisis_cases.py
```


**File created:** [extras/docs/CRISIS_SYSTEM_REPORT.md](extras/docs/CRISIS_SYSTEM_REPORT.md)

If you'd like, I can now either (A) produce the RTM, (B) draft conservative regex additions and run the unit cases, or (C) prepare a training plan and data schema for the ML classifier. Which do you want next?