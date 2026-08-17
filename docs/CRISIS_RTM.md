# MindGuard Crisis Detection — Requirements Traceability Matrix (RTM)

Derived from `extras/docs/CRISIS_SYSTEM_REPORT.md`. This maps each suggested
SRS acceptance criterion to the implementing code, its tests, and the
artifact/metric that verifies it. File paths are taken from the report as
written — verify against the actual repo before treating this as final.

| Req ID | Requirement | Implementing File(s) | Test(s) | Acceptance Criteria | Verifying Artifact |
|---|---|---|---|---|---|
| REQ-01 | Deterministic rule engine flags explicit first-person suicidal intent | `server/services/crisis_rules.py` (`explicit_suicidal_intent`) | `tests/backend/test_crisis_rules.py` | Recall ≥ 0.95 on explicit-intent subset | `artifacts/crisis_detector.metrics.json` |
| REQ-02 | Rule engine flags lethal-means/preparation language (incl. overdose phrasing) | `server/services/crisis_rules.py` (`lethal_means_and_preparation`) | `tests/backend/test_crisis_rules.py` (add: overdose regression cases) | Recall ≥ 0.95 on lethal-means subset | `artifacts/crisis_detector.metrics.json` |
| REQ-03 | Rule engine handles negation / historical / academic context bypass without suppressing unambiguous present intent | `server/services/crisis_rules.py` (bypass logic) | `tests/backend/test_crisis_rules.py` (bypass cases) | Zero suppressed true positives on first-person-present test set | `artifacts/crisis_detector.metrics.json` |
| REQ-04 | Multilingual / romanized-script coverage | `server/services/crisis_rules.py`, `server/services/intent_rules.py` | `tests/backend/test_crisis_rules.py` (per-language cohort) | Recall ≥ 0.95 per language cohort | `artifacts/crisis_detector.metrics.json` (by-cohort breakdown) |
| REQ-05 | Deterministic escalation bypasses LLM transmission for crisis-positive messages | `server/app.py` (pipeline step 4) | `server/tests/` (pipeline integration test) | 100% of `is_crisis=True` messages bypass `llm_service` | Pipeline integration test log |
| REQ-06 | ML classifier ensemble catches paraphrases missed by regex | `server/services/huggingface_service.py`, `artifacts/crisis_detector.joblib` | (not yet implemented — see Medium-term) | Recall ≥ 0.95 combined (rules ∪ ML) | `artifacts/crisis_detector.metrics.json` |
| REQ-07 | Precision bound to limit reviewer/alert overload | `server/services/crisis_rules.py` + ML ensemble | Held-out precision eval (not yet implemented) | Precision ≥ 0.6 | `artifacts/crisis_detector.metrics.json` |
| REQ-08 | End-to-end latency | `server/app.py` pipeline | Load/latency test (not yet implemented) | Median < 500ms rule-only; < 2s with ML | Latency test report |
| REQ-09 | Escalation logging with redaction | `server/app.py`, logging layer | `server/tests/` (log redaction test) | Every escalation logs `request_id`, `timestamp`, `matched_categories`; no raw message content | Audit log sample review |
| REQ-10 | Privacy: no crisis-positive message content sent to external LLM (Gemini) | `server/services/llm_service.py` | `server/tests/` (bypass-before-send test) | 0 crisis-positive messages reach external API call | `extras/docs/PRIVACY_AND_SECURITY.md` conformance check |

## Gaps identified in this pass
- REQ-06, REQ-07, REQ-08 have no test coverage yet per the report — these are the ML/latency work items, not quick wins.
- REQ-04 needs the specific romanized-language regression cases added (see `false_negatives.csv` and `regex_additions_draft.py`).
- No test file currently referenced for REQ-05/REQ-09/REQ-10 (pipeline-level, not rule-level) — confirm whether these exist under `server/tests/` or need to be written.

## Next step to make this authoritative
Upload `server/services/crisis_rules.py`, `server/services/intent_rules.py`, and the contents of `tests/backend/` and `server/tests/` so file paths, function names, and test IDs in this RTM can be verified against the real code rather than inferred from the report.
