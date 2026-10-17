# MindGuard AI — Remaining Failures and Release Readiness Task

You are working in the existing MindGuard AI repository. Read `TEST_REPORT.md`, `BUGS.md`, and `TEST_PLAN.md` first. Treat the latest verification report as a starting point, not proof that the application is ready.

## Current reported status

- Backend suite: 459 passed, 179 subtests passed.
- Threat-context matrix: 7/7 passed.
- Rate-limit security suite: 4/4 passed.
- Crisis release gate: passed configured checks.
- Frontend tests: 38/38 passed; type-check and build passed.
- `tests/test_mindguard_aggressive.py`: 309 passed, 98 failed, 23 skipped.
- Reported remaining categories: 54 Roman Urdu misses, 6 Urdu-script misses, 21 response-schema assertion failures, 8 tests requiring a local HTTP server, 4 formatting-related false positives, and 5 technical/neutral idiom false positives.
- Development benchmark: 15 false negatives and 19 false positives among 530 cases; reported FNR 3.28% and FPR 26.03%.
- Remote Ubuntu CI and live-provider staging tests remain unverified.

Re-run relevant commands to confirm these numbers against the current working tree before relying on them.

## Rules

1. Do not claim release readiness while unexplained failures or known high-risk detection gaps remain.
2. Do not delete, weaken, skip, or xfail tests just to obtain a green run.
3. Do not change expected labels or schemas solely to make failures pass. Verify each expectation against the intended application contract and document any legitimate contract correction.
4. For every production fix, add or retain a regression test that fails before the fix and passes after it.
5. Minimize unrelated changes. Keep a clear diff and report all modified files.
6. Do not call live external APIs or use real user data. Keep live-provider tests explicitly opt-in and secret-free by default.
7. Treat this application as safety-critical: false negatives on credible active crisis language take priority, but reduce obvious false positives too.

## Task A — Re-establish the actual baseline

Run and record exact command, exit code, passed/failed/skipped/error counts, and duration for:

- `py -m pytest tests/test_mindguard_aggressive.py -v`
- `py -m pytest tests/backend/ -q`
- `py -m pytest tests/test_threat_to_others_context_matrix.py -v`
- `py -m pytest tests/backend/test_rate_limiting_security.py -v`
- `py scripts/release_gate_crisis.py`
- `py tests/run_all_tests.py`
- In `client/`: `npm.cmd test`, `npm.cmd run type-check`, `npm.cmd run build`

Do not infer suite results from the master runner alone. Keep each suite's output separately available.

## Task B — Resolve real language-related misses

1. Review all 54 Roman Urdu and 6 Urdu-script failures individually. Build a table of test ID, exact utterance, intended label, actual result, whether the case is a true crisis miss or a test-label issue, and the proposed change.
2. Expand Tier 1 detection carefully for valid passive/active self-harm expressions and threats in Roman Urdu and Urdu script, including common spelling variants and code-switching.
3. Add positive/negative contrast pairs. A change that catches a crisis utterance must also be tested against nearby harmless utterances, idioms, lyrics/quotes, fiction, academic discussion, negation, and third-party reporting.
4. Keep first-person user risk distinct from a threat reported about someone else. Do not map all dangerous words to the same crisis category without actor/target/context analysis.
5. Run all regression fixtures and release-gate datasets after each change. Report false negatives and false positives by language/category; do not merely report aggregate accuracy.

## Task C — Fix the 21 response-schema failures correctly

1. Inspect the actual `/api/chat` response contract and frontend consumption. Determine where Pakistan emergency resources are returned and in which field(s).
2. Correct tests to assert the documented API schema only when the existing test expectation is demonstrably wrong. Do not alter production response semantics just to satisfy a test that searches the wrong field.
3. Add tests confirming crisis responses expose the expected emergency resources in the documented JSON shape, without requiring the phone number to appear in a plain-text response field unless that is the contract.
4. Record any contract correction in documentation and tests.

## Task D — Remove hidden local-server assumptions from the 8 HTTP harness failures

1. Convert tests to Flask's `app.test_client()` where possible, including malformed JSON, content type, method, and rate-limit behavior.
2. If a real network test is genuinely needed, make it an explicit separately marked integration test that starts and stops its own server, waits for health readiness without arbitrary sleeps, and cannot accidentally target a developer's unrelated port-5000 process.
3. Ensure local test execution is deterministic and isolated. Never classify a test as passed merely because a socket-dependent case was skipped.

## Task E — Fix false positives without hiding danger

1. Triage the four formatting-related failures and five technical/neutral idiom cases using exact input/output examples.
2. Preserve escalation for genuine explicit active threats even when punctuation, casing, spacing, or casual language changes.
3. Avoid escalation for harmless phrases such as technical process termination, idioms like “kill time,” and clearly framed fictional/educational material when the surrounding context supports that interpretation.
4. Add paired tests to ensure exceptions are narrow and do not suppress genuine risk.

## Task F — Validate performance/resource bounds and fail-safe behavior

1. Verify message length validation, request-body size limits, and classification order for both benign and crisis-bearing long messages.
2. Test a crisis phrase near the beginning, middle, and end of an overlong narrative. Ensure oversized payloads cannot cause unbounded processing or bypass resource limits.
3. Verify a finalized high-crisis route calls no generative provider, including every provider available in this codebase.
4. Verify classifier/provider/database errors cannot silently become a “no risk” decision.

## Task G — Benchmark integrity and release gate

1. Verify dataset paths, counts, labels, and train/evaluation separation. Report duplicate and possible leakage findings.
2. Reconcile the reported development benchmark confusion matrix: TP=442, FP=19, TN=54, FN=15. Report FNR, FPR, precision, recall, and per-category/language misses using correct denominators.
3. Keep thresholds unchanged unless a documented, reviewed requirement authorizes a change. Never tune on the locked independent evaluation set.
4. Ensure the release gate fails closed when required data is missing, a test suite cannot be imported, or the evaluation denominator is zero.
5. Do not treat 100% on a curated 100-case set as proof of zero possible open-domain false negatives.

## Task H — Final security and delivery status

1. Re-run dependency audits for both production and development dependencies; list exact vulnerable packages and severity. Distinguish production risks from tooling/dev-only issues.
2. Confirm the rate limiter's proxy trust model and whether it works across multiple worker processes. If shared storage is not configured, document the deployment restriction clearly.
3. Check Git status and diff. Report modified and untracked files; confirm no unrelated files/secrets are included.
4. If available, inspect the actual GitHub Actions run for the current branch/commit. Otherwise leave Linux CI marked **UNVERIFIED**.
5. Update `BUGS.md`, `TEST_PLAN.md`, and `TEST_REPORT.md` with evidence, not assumptions. Include a section for every remaining failure and unresolved risk.

## Acceptance criteria

Do not declare READY FOR RELEASE unless:

- All confirmed high-risk regression cases pass.
- The 98 previously reported failures have been individually classified and either fixed with regression coverage or documented as justified test-contract/infrastructure issues with the suite corrected appropriately.
- Positive/negative paired tests show the fixes do not create broad false-positive escalation.
- Backend, frontend, release gate, and aggressive suites produce reproducible results.
- The release gate preserves thresholds and independent evaluation separation.
- Any unverified external CI/live-provider behavior remains clearly disclosed.

## Final deliverable

Update the three audit documents and provide a concise final summary with:

- exact commit and working-tree status;
- per-suite counts and exit codes;
- all remaining failures, categorized individually;
- confusion matrices and metrics by language/risk class;
- each production fix and its regression test;
- unresolved risks and why they remain;
- final status: **RELEASE BLOCKED**, **CONDITIONAL**, or **READY FOR RELEASE**.

Execute the work; do not respond with a plan alone. Do not claim a check ran if its command was not executed.
