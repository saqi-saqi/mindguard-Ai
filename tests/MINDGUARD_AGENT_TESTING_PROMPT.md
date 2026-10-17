# MindGuard AI — Comprehensive QA, Safety, and Security Audit

## Mission

Act as a senior QA/SDET engineer, application-security tester, and safety-critical ML test engineer. Audit the MindGuard AI repository that is open in the current workspace. Inspect the implementation before making assumptions. Build and run a thorough, maintainable test suite that exposes defects, especially missed crisis cases, and deliver clear reports.

The expected project is `saqi-saqi/mindguard-Ai` (also previously referenced as `saqi-saqi/mindguard_ai`). **First verify the repository and its current Git remote; do not assume these names refer to different projects.** Work on the repository already checked out in the workspace. Do not publish code, push commits, create issues, or change remote settings.

## Critical rules

1. **Do not modify production code.** Add or adjust test code, test fixtures, test configuration, and audit documentation only. If a production fix is needed, describe it in `BUGS.md` instead of applying it. If a test/config change is unavoidable, keep it isolated and explain it in the report.
2. **Never weaken, delete, skip, or loosen an existing test to get a green result.** Do not change assertions, lower thresholds, or mark a failing test as passing. If a new test reveals a real defect, preserve the failing test and document the reproducer.
3. **Never claim a test passed unless you actually ran it.** Record the exact command, exit code, relevant output, and whether the run completed. Separate `PASS`, `FAIL`, `BLOCKED`, and `NOT RUN`.
4. **No live user data, real secrets, or unapproved external calls.** Do not print environment secrets. Never call real Gemini/Hugging Face APIs during ordinary tests. Mock external services by default. Do not use a production database. Use an isolated test database or mocks.
5. **Do not expose harmful method details** in tests, fixtures, logs, reports, screenshots, or examples. Crisis inputs should be minimal and non-graphic while still testing risk detection.
6. **Safety takes priority over a green dashboard.** Keep crisis false negatives and safety-invariant failures visible and high priority. Do not hide failures behind broad `try/except`, silent fallbacks, or misleading `xfail` markers.
7. Inspect the project’s real contracts and code before writing assertions. If a requirement in this document is not supported by product docs/code, record it as a proposed requirement or specification gap rather than silently inventing behavior. If behavior is ambiguous, write a test only when the safest intended behavior is clear; otherwise document the ambiguity.
8. Keep work incremental, deterministic, and reproducible. Do not run destructive migrations or commands against any non-test database. Do not reset user changes or overwrite existing uncommitted work.
9. Start by recording `git status`. Preserve all existing user modifications. Do not use destructive Git commands such as `reset --hard`, `clean -fd`, or force-push.
10. If time, dependencies, network, or environment prevents a task, report it precisely and continue with independent tasks. Do not stop at planning if the repo can be tested locally.

## Intended architecture to verify

The documented design is a three-tier crisis pipeline; verify the real implementation and call paths:

- **Tier 1 — `crisis_rules.py`:** deterministic safety rules. For explicitly defined high-crisis cases, this tier has final authority and must not be overridden downward.
- **Tier 2 — `huggingface_service.py`:** ML classification for intent/emotion/sentiment and risk. It may raise risk but must never lower an already-raised Tier 1 crisis flag.
- **Tier 3 — `llm_service.py` and `response_kb.py`:** Gemini-based ordinary conversational response and offline fallback. It should be bypassed whenever the system has classified a high crisis, according to the repository’s actual contract.
- **Application stack:** Flask backend; MongoDB; React/Vite frontend; JWT/bcrypt authentication; Docker/deployment configuration.

This is **not a RAG/vector-database project** unless the code actually proves otherwise. Do not invent vector-store or retrieval tests.

## Deliverables to create/update in the repository

Create these files if they do not exist; otherwise update them without destroying existing useful content:

- `TEST_PLAN.md` — inventory of application surfaces and coverage status.
- `BUGS.md` — reproducible defects and security/safety findings, ordered with crisis false negatives first.
- `TEST_REPORT.md` — actual commands/results, coverage, limitations, unresolved failures, and steps to reproduce.
- Test files and fixtures organized consistently with the existing project’s conventions.

Do not overwrite or replace existing tests/fixtures wholesale. Reuse and extend them. Before editing a file, inspect it and preserve its existing intent.

# Phase 0 — Discover and establish the baseline

**Do this before adding or changing tests.**

1. Record repository root, Git remote, branch/commit, Python and Node versions, OS, whether Docker is available, and `git status`. Redact credentials from any remote URL.
2. Inspect the README and repository tree. Read the relevant source code, not just docs:
   - `server/` including `app.py`, `auth.py`, `config.py`, `database.py`, and every service/module.
   - `client/src/` components, routes, hooks, API client, and current tests.
   - `ml/`, `scripts/`, fixtures, benchmarks, training code, and model-loading code.
   - all tests, `conftest.py`, `pytest.ini`, and frontend test configuration.
   - `docker-compose.yml`, Dockerfiles, `.github/workflows/`, dependency manifests, `.env.example`, `.gitignore`, and security/privacy/crisis-resource documentation.
3. Find all API routes, database collections, frontend screens/features, environmental configuration, external-service calls, and crisis decision paths. Follow the code to identify the actual safety decision and exact point where an LLM call could occur.
4. Inventory every current test suite and benchmark. Note duplicated tests or overlapping suites, but do not remove them.
5. Before adding tests, run existing test commands when safe and dependencies/services are available. Discover commands from package scripts and project docs first. Candidate commands include:
   - `python tests/run_all_tests.py`
   - `python -m pytest tests/backend -v`
   - the repository’s configured full Python test command (for example, `python -m pytest`)
   - the actual client test command from `client/package.json` (possibly `npm test` or `npm run test`)
   - existing benchmark and release-gate commands documented in the repo.
6. Inspect the runner before executing it. If its commands are Windows-only or unsuitable for the current OS, record that fact and run the underlying suites individually where possible. Do not present an incompatible wrapper failure as a failure of all underlying tests.
7. Inspect tests for accidental production DB/API access before running them. If tests require MongoDB or another service, use a clearly isolated test instance/database. If unavailable, record `BLOCKED` and keep running independent suites. Do not substitute a skipped test for a pass.
8. Record the baseline in `TEST_REPORT.md`: command, working directory, exit code, pass/fail/skip counts, errors, duration if available, and coverage output if actually measured. Record the environment limitations. No test should be labelled “passed” based only on static inspection.
9. Create `TEST_PLAN.md` with one row/checklist item per important API endpoint, service, DB collection, frontend component/feature, security/privacy claim, pipeline invariant, and deployment/release gate. Mark each `TESTED`, `PARTIAL`, `UNTESTED`, or `BLOCKED` based on actual evidence, and link to existing tests where possible.

After Phase 0, continue through the remaining phases in this session wherever resources permit. Do not stop merely to ask the user for permission. If a scope limit prevents completion, finish a coherent subset, preserve progress, and clearly list what remains.

# Phase 1 — Test infrastructure and conventions

- Follow established project conventions and versions rather than unnecessarily replacing tooling.
- Python: use the project’s pytest setup; use `pytest-cov` if available/compatible.
- Frontend: use the existing Vitest/React Testing Library setup. Add accessibility tooling only if compatible with current dependencies.
- E2E: use Playwright if configured or add a minimal, documented setup only if feasible. Do not claim cross-browser coverage unless each browser was actually run.
- Mock Gemini, HF model calls, and other network APIs by default. Keep explicit live tests under a marker such as `@pytest.mark.live`; never run those by default and never require a live API key for normal CI.
- Tests must be deterministic, isolated, and independent. Use factories/fixtures and parameterization. Prefer injected clocks/clients over flaky sleeps. Add realistic timeouts for potential hangs.
- Add coverage reports for the crisis rule engine and risk-decision code if compatible with the repository. Target high coverage, ideally 95%+ for safety-critical decision logic and 80%+ overall, but report actual figures and explain unreachable/excluded code. Do not game the metrics.
- If test configuration/dependencies must change, explain why and keep changes minimal. Never alter production behavior to accommodate a test.

# Phase 2A — Tier 1 deterministic crisis rules (highest priority)

Inspect every public function and branch in `crisis_rules.py` and all related normalization/context helpers. Create tests that verify both positive detections and carefully chosen negative/ambiguous cases. Test only categories and behaviors that the repository defines or explicitly document gaps.

Cover, where supported by the actual product contract:

- Passive and active suicidal ideation; plan/means/timing indicators; self-harm; harm to others; combined self-harm plus harm-to-others, including the specified `HIGH_CRISIS` invariant if the code/docs require it.
- Abuse/domestic violence, substance-related crisis, eating-related risk, panic/anxiety, general distress, neutral and positive messages.
- Direct and indirect language; euphemisms; ambiguous statements; idioms/hyperbole; sarcasm/joking; past events; third-party reports; fictional/quoted/academic contexts; hypotheticals; help-seeking questions; direct negation and double negation.
- Contextual invariants: a direct negation or academic/third-party context must not suppress clear active first-person risk elsewhere in the same message. Contrastive clauses must be evaluated without allowing a benign clause to erase a crisis clause. Historical risk with a clear current acute relapse must not be treated as resolved. A third-party report should get the documented guidance path rather than incorrectly escalating the reporting user.
- English, Urdu script, Roman Urdu, mixed/code-switched text, common misspellings/transliterations, slang, punctuation/spacing variation, ALL CAPS, emojis alongside text, and RTL/Unicode edge cases where supported.
- Robustness: empty/whitespace/`None`/unexpected types according to the function contract; long inputs; phrases buried later in a message; zero-width characters and unusual Unicode. Avoid tests that intentionally consume excessive CPU or memory. For regex ReDoS, use a bounded, isolated test with a conservative timeout and do not risk hanging the suite.
- False positives: common idioms such as “this exam is killing me,” “dying of laughter,” coding language such as “kill the process,” games, cooking, news, and medical/educational contexts, provided no genuine active-risk clause exists.
- Each important contextual bypass/negation rule should be tested both ways: the benign/negated case and a close variant with real unnegated risk that still triggers.
- Input normalization and order of operations. Specifically verify that a raw substring regex hit cannot bypass contextual negation logic if the documented design says otherwise.

Use parameterized cases with fields such as `id`, `category`, `text`, `expected_crisis`, expected risk level/intent where defined, `rationale`, and source/requirement. Keep test inputs non-graphic. Use existing regression fixtures and test datasets as the starting point; check for duplicates and conflicting labels.

# Phase 2B — Tier 2 ML classifier (`huggingface_service.py`)

Test with injected/mocked model components and deterministic outputs:

- Model loading success/failure, lazy initialization, absent/corrupt artifacts, missing dependencies, cached initialization, thread-safety where relevant, and failure recovery.
- Intent, emotion and sentiment output schema, invalid/empty output handling, confidence boundaries including exactly-at-threshold cases, and batch/individual consistency where supported.
- Empty, long, Unicode, Urdu/Roman Urdu and mixed-language inputs according to stated model scope. Do not claim non-English support merely because the function accepts Unicode.
- Failures/timeouts must follow the documented safe behavior; they must not silently turn a possible crisis into an assured “no risk.” If safe behavior is undefined, record the specification gap.
- Invariant tests: Tier 2 may elevate a message when Tier 1 did not fire; contradictory Tier 2 output can never downgrade or erase a Tier 1 crisis flag.
- Latency tests only with an appropriate mocked/local path and robust measurement; keep hardware-dependent live model latency in a separate optional report.

# Phase 2C — Tier 3 LLM and offline fallback (`llm_service.py`, `response_kb.py`)

- Test service success; invalid/missing API configuration; timeouts; rate limits/429; 5xx; malformed, empty, refused or blocked responses; and fallback selection.
- Verify every documented intent has a useful, non-empty offline fallback. Identify missing, conflicting, stale, or misleading knowledge-base responses. Do not invent medical advice.
- Prompt-injection tests such as requests to ignore the rules, act as a different role, reveal hidden instructions, or provide harmful instructions. Verify user content cannot override system safeguards and that the application does not reveal secrets or hidden prompt text.
- Output validation/filtering must block or replace outputs that violate product rules, including diagnosis/treatment claims, medication recommendations, or harmful method detail, if those are prohibited by the docs.
- **Crisis bypass invariant:** spy/mock the provider client and assert the provider makes zero calls whenever the application has reached a high-crisis decision at Tier 1 or Tier 2, according to the documented pipeline contract. Test normal non-crisis calls separately.
- Logs and HTTP responses must not reveal API keys, private prompts, stack traces, or unredacted sensitive text contrary to documented privacy claims.

# Phase 2D — Crisis response and localized resources

- Check deterministic crisis responses and UI resources for each documented crisis path.
- Read the crisis resource maintenance documentation and validate consistency with the resources actually configured in the repo. Flag possibly outdated or unverifiable resources for human review; do not silently change phone numbers.
- Verify Pakistan-oriented resources, including 1122 and Umang Pakistan where the product documentation specifies them. US/UK numbers such as 988 or 111 should only appear where the product intentionally configures them for the relevant context.
- Test harm-to-others handling separately from self-harm and general distress; it should follow the documented response and escalation rules.
- Ensure crisis responses do not contain method/means instructions and that resource links are validly formatted and usable by the UI.
- Simulate Gemini down, HF down, and database unavailable. The deterministic crisis engine and crisis response path must still behave according to documented fail-safe guarantees.

# Phase 2E — Flask API and authentication

Enumerate and test every actual route found in the app. For each relevant route, cover success, invalid input, missing/extra fields, wrong types, malformed JSON, wrong content type, method mismatch, unauthenticated access, permission errors, and consistent error formatting/status codes.

Authentication and authorization (`auth.py` and related modules):

- Register/login/logout flows, duplicate accounts, input validation, password policy, bcrypt hashing, and proof that plaintext passwords are never stored or logged.
- JWT creation, claims, expiry, missing/tampered tokens, wrong signature, and algorithm-confusion/`alg=none` rejection if the library/config exposes that risk.
- Authorization of user-owned resources: user A must not read/write/delete user B’s data (IDOR tests).
- Session/token clearing behavior on logout and expired-session handling in the frontend.

Security controls:

- Validate configured rate-limit semantics. If the documented policy is 60 requests/minute, test the boundary (60th accepted and 61st limited), window reset, and isolation by client identity without adding flaky sleeps; use injectable clocks or a test limiter if available.
- Check `X-Forwarded-For` trust assumptions against the deployment/proxy configuration. A client-supplied header must not enable rate-limit bypass unless a trusted proxy explicitly sanitizes it.
- CORS tests should assert allowed origins get the correct access-control headers and disallowed origins do not get permissive headers; do not incorrectly assume CORS always blocks the HTTP request itself.
- Security headers, payload-size limits, request validation, secret/config handling, and stack-trace suppression.
- Capture logs and assert secrets/prompts/user text are redacted wherever documented. Avoid logging actual sensitive test values in test failure output.
- NoSQL/operator injection against login, filters and query parameters, including `$ne`, `$where` and other operators as appropriate to actual query construction.
- Parallel requests and relevant race conditions, using deterministic coordination rather than arbitrary sleep-based assertions.

# Phase 2F — Database and persistence

- Test CRUD operations for each actual collection, validation, indexes/unique constraints, ordering/pagination, and per-user isolation.
- Verify account deletion and documented data export/delete functionality remove or return all appropriate user-owned data without affecting other users.
- Connection loss/reconnect and partial write errors should be handled predictably; crisis behavior should not rely on MongoDB if the stated design promises otherwise.
- Use mocks for unit-level DB tests and a clearly named isolated test DB for integration tests. Never point tests at production or the user’s real database.
- Review and test any SQLite-to-Mongo migration script, if present: dry run, idempotency, malformed source rows, partial failure, and duplicate handling. Do not execute a real destructive migration as part of this audit.

# Phase 2G — Frontend

Inspect the real component tree and test all meaningful screens and states, including the equivalents of `ChatInterface`, `CrisisModal`, `AnalyticsDashboard`, `SettingsPanel`, `AuthScreen`, navigation/tab state, and API helpers if present.

- Rendering; required props; loading, empty, success and error states; long text; malformed API responses; network timeout/failure; retry behavior; history load/persistence; rapid double-submit; and send/receive flow.
- Crisis modal/resource display for each supported crisis class; correct phone/link formats; keyboard focus handling, accessible labels, and dismissal behavior consistent with the safety design. Verify that dismissal does not misrepresent the crisis as resolved.
- Registration/login validation and errors; tokens are not left behind after logout; expired sessions are handled safely.
- Analytics empty/large/malformed datasets, date ranges and non-diagnostic disclaimers. Settings should persist and apply according to actual implementation.
- Accessibility checks with axe or equivalent if installed/compatible; keyboard-only navigation; responsive mobile/tablet/desktop layouts; Urdu/RTL rendering where supported.
- XSS: render user and model content as text, not executable HTML. Test HTML/script-like input through the real rendering path; do not execute payloads in a real external browser or environment.

# Phase 2H — End-to-end tests

Use Playwright only if the project can be started safely with a test DB and mocked external services. Add focused journeys for:

- Sign up, log in, normal chat, history, analytics, settings, and logout.
- English, Urdu-script and Roman Urdu crisis cases, plus the combined self-harm/harm-to-others invariant if specified.
- Crisis UI and localized resources appearing without making a Gemini request.
- Gemini unavailable and correct offline fallback; backend unavailable; slow network; expired token; unauthorized access.

Run Chromium/Firefox/WebKit and a mobile viewport only when the browser binaries and environment are available. Record each browser as `PASS`, `FAIL`, `BLOCKED`, or `NOT RUN`; never imply every browser was tested when only one was run.

# Phase 2I — Training, benchmarks, and release gate

- Inspect and smoke-test each actual training entry point on a tiny, local, non-sensitive sample if the script supports it. Fix random seeds where configured. Do not download large models or datasets without need. Verify documented output files/metric JSON only when actually produced.
- Test the release gate with controlled fixtures/mocks that simulate unacceptable high-risk recall or deliberately bad predictions. Verify the gate exits non-zero and blocks release. Avoid modifying or corrupting real artifacts to simulate failure.
- Test clean-install verification in a disposable/isolated environment if feasible.
- Audit benchmark datasets for contradictory labels, duplicates, class imbalance, train/test leakage, and overlap between regression fixtures and evaluation data.
- Extend existing datasets rather than duplicating them. A goal of 300+ well-labelled cases may be used if the repository and available evidence support it, but **do not fabricate ground-truth labels solely to reach a number**. Synthetic cases must be clearly marked, rationale-tagged, reviewed against an explicit policy, and kept separate from real-world evaluation claims.
- Report per-class precision, recall and F1 where the labels and execution permit. High-risk recall must have an explicit acceptance threshold grounded in the repo/docs; if none exists, recommend one rather than silently inventing a release policy. Ensure the gate fails on unacceptable high-risk recall.

# Phase 2J — Security, privacy, dependencies, and deployment

- Check applicable OWASP risks: injection (including NoSQL and prompt injection), broken authentication/access control, sensitive data exposure, XSS, CSRF where applicable, SSRF only where user-controlled network fetching exists, security misconfiguration, and dependency risks.
- Review secret hygiene in the current working tree and tracked files; inspect `.env.example` and `.gitignore`. Do not print secret contents. Do not run a destructive Git-history rewrite. If history scanning is available, report the command/tool and its scope.
- Run `pip-audit`, `npm audit`, or equivalent only if the tools and dependencies are available and the command is safe. Separate network/tool failures from confirmed vulnerabilities. Do not treat a failed audit command as a passed audit.
- Check Docker configuration for root/non-root behavior, secrets baked into images, exposed ports, health checks, and dependency readiness. Do not claim a Docker deployment passed unless actually built and run.
- Convert material claims in `PRIVACY_AND_SECURITY.md` into tests where possible, especially: crisis inputs bypass external APIs, logging redacts user text, CORS is restricted, and the rate-limit policy is enforced. If a claim is contradicted by the code/tests, report it.
- Check CI workflow coverage and ensure it runs the relevant suites and fails on genuine failure. Test the release workflow locally where possible.

# Phase 2K — Reliability and performance

- Measure deterministic crisis-rule latency with a bounded local benchmark and realistic test inputs. Report machine/environment and percentile/sample methodology; do not claim universal latency based on one laptop.
- Exercise long conversations, oversized payloads and parallel requests without intentionally exhausting system resources.
- Verify service startup/health checks and restart behavior if Docker/services are available. Track external model/API latency separately from deterministic crisis-engine latency.

# Test quality requirements

- Use descriptive behavior-style test names and Arrange/Act/Assert structure.
- Prefer `pytest.mark.parametrize`/data-driven cases for language, context and risk matrices.
- Keep tests deterministic, independently runnable, and fast by default. Mark integrations, slow tests and live-model tests distinctly.
- Never depend on real API credentials, external internet, wall-clock sleeps, real personal data, or non-test DBs in the standard suite.
- Avoid assertions that only verify implementation details without an observable contract. Avoid over-mocking the exact behavior the test is meant to verify.
- When a requirement is ambiguous, record a spec gap and add a test only if safe expected behavior is defensible.
- Do not “fix” failed tests by broadening exception handlers, relaxing assertions, hiding output, lowering thresholds, or changing the production code.

# Final report format (`TEST_REPORT.md`)

Include the following sections and keep them current as you work:

1. **Executive summary:** most important safety/security issues first.
2. **Environment:** commit/branch, OS, Python/Node versions, available services and dependencies.
3. **Baseline:** commands run before new tests, exact outcomes, coverage if actually measured.
4. **Work performed:** added/changed test files and fixtures; purpose of each.
5. **Results:** suite-by-suite and requirement-by-requirement `PASS` / `FAIL` / `BLOCKED` / `NOT RUN`, counts and evidence.
6. **Coverage:** module/line/branch coverage if available; separately call out `crisis_rules.py` and risk-decision logic.
7. **Defects:** link to `BUGS.md`; prioritize crisis false negatives, then safety-invariant violations, false positives, privacy/security, functional bugs, and UX issues.
8. **Reproduction:** exact command and minimal safe input/setup for each defect; expected versus actual behavior; file/function/line references when available; likely cause and suggested fix. Do not include secrets.
9. **Limitations and untested gaps:** explain precisely why each item could not be tested.
10. **How to run:** copy-paste commands for unit, integration, frontend, E2E, security, benchmark, and release-gate suites.
11. **Release recommendation:** state whether the tested evidence supports release, blocks release, or is insufficient. Any unresolved high-risk false negative or critical safety invariant failure must be prominent; do not label the app safe solely because the suite is green.

## Final execution checklist

Before finishing:

- Run the full test command(s) that are safe and available after adding tests, plus all relevant targeted suites.
- Compare against the baseline and explain any new failures versus pre-existing failures.
- Confirm no production source files were changed. Show `git status --short` and a list of changed files.
- Confirm any test failure is retained and documented, not hidden or weakened.
- Ensure `TEST_PLAN.md`, `BUGS.md`, and `TEST_REPORT.md` exist and agree with the actual evidence.
- Summarize the most important findings and remaining blocked work in your final response. Be precise about what was and was not executed.

**Start now with Phase 0 in the current repository. Inspect first, establish the baseline, then continue through the phases and deliver the reports and tests.**
