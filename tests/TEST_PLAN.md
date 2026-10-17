# MindGuard AI — QA, Safety, and Security Test Plan

**Phase:** Final Independent Verification Completed  
**Repository:** `saqi-saqi/mindguard-Ai`, branch `main`  
**Base Commit Tested:** `8ad186d2eb3e00e978d6116dfce7d9f39a250091`  
**Updated:** 2026-10-15  
**Final Release Status:** **CONDITIONAL** (Core invariants verified; production release conditioned on remote Ubuntu CI run and Roman Urdu dialect expansion)  
**Audit Artifacts:** See [TEST_REPORT.md](file:///E:/FYP/current/TEST_REPORT.md) and [BUGS.md](file:///E:/FYP/current/BUGS.md) for full execution results and reproducible findings.

## Status key

- **TESTED (PASS)** — Executed locally with 100% assertions passing.
- **PARTIAL / DIAGNOSTIC** — Executed; identified edge cases, gaps, or diagnostic failures.
- **UNVERIFIED** — Code updated but remote CI execution not yet observed.
- **UNTESTED / NOT RUN** — Surface exists but has not yet been executed in this environment.

## 1. Automation Execution Summary

| Area | Evidence found | Verified Status | Verification Evidence |
|---|---|:---:|---|
| Pytest discovery | `pytest.ini` sets `testpaths = tests/backend` | **TESTED (PASS)** | 459 passed, 179 subtests in 54.20s |
| Shared fixtures | `conftest.py` sets `USE_MONGOMOCK=true`, `FLASK_ENV=testing` | **TESTED (PASS)** | Isolated mongomock fixtures verified |
| Master runner | `tests/run_all_tests.py` orchestrates 7 CI stages | **TESTED (PASS)** | Ran all 7 stages; Exit Code 0 |
| Threat Context Matrix | `tests/test_threat_to_others_context_matrix.py` | **TESTED (PASS)** | 7 / 7 passed in 2.91s |
| Rate-Limiting Security | `tests/backend/test_rate_limiting_security.py` | **TESTED (PASS)** | 4 / 4 passed in 29.49s |
| Crisis regression fixture | `tests/fixtures/crisis_regression_cases.json` | **TESTED (PASS)** | 43 / 43 cases passed (100%) |
| Crisis release gate | `scripts/release_gate_crisis.py` | **TESTED (PASS)** | 238/238 aggressive + 100/100 locked evaluation (100% recall, 100% precision) |
| Standalone Aggressive | `tests/test_mindguard_aggressive.py` | **PARTIAL** | 309 passed, 98 failed, 23 skipped (1023.60s) |
| Frontend tests | `client/package.json` (`vitest run`) | **TESTED (PASS)** | 38 / 38 unit & a11y tests passed in 4.37s |
| Frontend type-check | `npm run type-check` (`tsc --noEmit`) | **TESTED (PASS)** | Clean compile, 0 TypeScript errors |
| Frontend build | `npm run build` (`vite build`) | **TESTED (PASS)** | Production bundle built cleanly (2.34s) |
| Python dependency audit | `pip-audit -r server/requirements.txt` | **TESTED (PASS)** | 0 vulnerabilities (flask-cors updated to >=6.0.0) |
| Frontend dependency audit | `npm audit --omit=dev` | **TESTED (PASS)** | 0 production vulnerabilities (source-map-js fixed) |
| Ubuntu CI Workflow | `.github/workflows/test.yml` | **UNVERIFIED** | Local runner made cross-platform; remote GitHub Actions run unverified |

## 2. Coverage Checklist & Component Verification

| ID | Component / feature | Required tests | Verified Status | Evidence & Reference |
|---|---|---|:---:|---|
| T1 | `server/services/crisis_rules.py` | Direct/indirect crisis language, plans/means, negation, idioms, Roman Urdu, Urdu script | **TESTED (PASS)** | Remediated contrastive negation (`BUG-CRISIS-FN-01`) & joke dampeners (`BUG-CRISIS-FN-02`); 83% line coverage |
| T1a | Multi-signal `safety_classifier.py` | Self-harm, threat to others, actor/target routing | **TESTED (PASS)** | `test_actor_target_regression.py` (8 passed), `test_threat_to_others_context_matrix.py` (7 passed); 84% line coverage |
| T1b | Session cooling-window state | Crisis persistence, cooling windows | **TESTED (PASS)** | `session_context.py` covered with 91% line coverage |
| T2 | `huggingface_service.py` | Model loading, fallback, schema boundaries | **TESTED (PASS)** | 77% line coverage; calibration monitor verified in release gate |
| T3 | `llm_service.py` & `response_kb.py` | Groq/Gemini fallback, offline response, timeouts | **TESTED (PASS)** | 15% line coverage; tested with mocks (live provider untested) |
| PIPE | Chat safety routing in `server/app.py` | High-crisis bypasses generative LLM, fail-safe | **TESTED (PASS)** | Verified in integration tests; overlong inputs with buried crisis handled safely |
| RES | `crisis_resources.py` | Pakistan helplines (1122, Umang), format validation | **TESTED (PASS)** | 72% line coverage; verified in context matrix & client tests |
| API | Flask endpoints | Auth, chat, moods, health, exercises | **TESTED (PASS)** | `/api/health`, `/api/chat`, auth routes validated |
| AUTH | `auth.py` & auth routes | Password bcrypt hashing, JWT issuance & expiry | **TESTED (PASS)** | Covered in backend auth tests |
| RATE | Rate limiter & proxy headers | 60 req/min boundary, IP spoofing | **TESTED (PASS)** | Remediated `BUG-SEC-01`: `test_rate_limiting_security.py` (4/4 passed) |
| HTTPSEC | Headers, error handlers, logging | Allowed origins, sanitization | **TESTED (PASS)** | Redaction filter and error handlers pass |
| DB | `database.py`, mongomock | CRUD, user isolation, data retention | **TESTED (PASS)** | In-memory mongomock tests pass across backend suite |
| MIG | SQLite-to-Mongo migration | Migration idempotence, dry-run | **NOT RUN** | Migration scripts preserved without live destructive execution |
| WEB | React/Vite components | `ChatInterface`, `CrisisModal`, `AnalyticsDashboard` | **TESTED (PASS)** | Vitest suite 38/38 passed |
| A11Y | Accessibility & responsive UI | axe-core, ARIA roles, 3-action clinical triage | **TESTED (PASS)** | `CrisisModal.test.tsx` 12/12 passed |
| XSS | Output encoding & sanitization | User & model input rendered safely as text | **TESTED (PASS)** | Verified in frontend component tests |
| E2E | Browser journeys | End-to-end browser journeys | **NOT CONFIGURED** | Playwright not installed in repository |
| MLTRAIN | `ml/train_*.py` | Training reproducibility, artifacts | **NOT RUN** | Retraining omitted to prevent heavy download overhead |
| GATE | Crisis CI release gate | Precision/recall thresholds, holdout isolation | **TESTED (PASS)** | 100% recall, 100% precision on held-out locked evaluation |
| PRIV | Privacy & data lifecycle | Sanitization, credential masking | **TESTED (PASS)** | Privacy redaction filter verified in tests |
| DEP | Clean install verification | Clean environment package discovery | **TESTED (PASS)** | `verify_clean_install.py` passes with exit code 0 |
| CI | GitHub Actions workflow | Ubuntu runner execution | **UNVERIFIED** | Runner made portable; awaiting live GitHub Actions run |
| PERF | Performance & latency | Crisis rule response latency | **TESTED (PASS)** | Rule engine evaluates in < 15ms |

## 3. Measured Per-Module Code Coverage

Tooling: `coverage-7.16.2`, `pytest-cov-7.1.0` (Python 3.14.6):

```
Name                                            Stmts   Miss  Cover
-------------------------------------------------------------------
server\services\__init__.py                         3      0   100%
server\services\threat_actor_detector.py          139      7    95%
server\services\generalizer.py                     93      4    96%
server\services\temporal_engine.py                 64      4    94%
server\services\discourse_evaluator.py             98      6    94%
server\services\semantic_concepts.py               48      3    94%
server\services\precedence_arbitrator.py           88      6    93%
server\services\roman_urdu_normalizer.py           76      5    93%
server\services\session_context.py                 64      6    91%
server\services\safety_classifier.py              250     39    84%
server\services\intent_rules.py                    44      7    84%
server\services\crisis_rules.py                   382     64    83%
server\services\roman_urdu_router.py               30      6    80%
server\services\huggingface_service.py            212     48    77%
server\services\text_normalizer.py                 88     22    75%
server\services\crisis_resources.py                40     11    72%
server\services\semantic_safety_classifier.py     134     92    31%
server\services\response_kb.py                     15     11    27%
server\services\llm_service.py                    352    298    15%
-------------------------------------------------------------------
TOTAL                                            2268    687    70%
```

## 4. Evaluated Safety Invariants & Release Conditions

1. **Safety Precedence Invariant:** A high-risk finding from the deterministic safety layer cannot be lowered by any downstream classifier or response generator.
2. **Generative LLM Bypass:** During crisis turns, all generative providers (Gemini, Groq, Ollama) are bypassed, returning structured deterministic guidance and Pakistan emergency resources.
3. **Resource Bound Invariant:** Messages exceeding `MAX_MESSAGE_LENGTH=2000` are scanned for crisis (delivering emergency care) or rejected with HTTP 400 `MESSAGE_TOO_LONG` if non-crisis.
4. **Conditional Release Conditions:**
   - **Condition 1:** Remote execution of GitHub Actions on `ubuntu-latest` must be confirmed.
   - **Condition 2:** Roman Urdu dialectical variants in `test_mindguard_aggressive.py` (54 cases) must be expanded.
   - **Condition 3:** Distributed Redis store must be configured for multi-worker WSGI deployments.
