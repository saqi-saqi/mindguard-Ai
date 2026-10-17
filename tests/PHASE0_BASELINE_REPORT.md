# MindGuard AI — Phase 0 Baseline Report

**Date:** 2026-10-15  
**Repository:** https://github.com/saqi-saqi/mindguard-Ai (`main`)  
**Scope:** Public-source discovery only; no production files changed and no tests added.

## Executive summary

Phase 0 is **partially complete**. The public README and several high-value source files were read. This workspace could not clone the repository: `git clone --depth 1 https://github.com/saqi-saqi/mindguard-Ai.git /mnt/data/mindguard-Ai` failed with `Could not resolve host: github.com`. Direct raw-file views are available for selected paths, but they do not provide a complete checkout or a runnable environment.

Therefore, the actual test baseline is **BLOCKED / NOT RUN**. No pass count, failure count, or coverage percentage is reported. The full source tree and all existing test files have not yet been read, and no test result should be inferred from README claims.

## Repository and automation evidence

- README documents a three-stage safety/conversation design: deterministic crisis rules, an ML classifier, then Gemini/offline response fallback. It also documents Flask, MongoDB, React/Vite, Docker, backend tests, frontend tests, fixtures, and benchmark scripts.
- `pytest.ini` sets `tests/backend` as the pytest test path.
- `conftest.py` sets `USE_MONGOMOCK=true` and `FLASK_ENV=testing` and inserts project directories into `sys.path`.
- `tests/run_all_tests.py` attempts backend pytest, clean-install verification, release gate, frontend type-check, Vitest tests, Vite build, and Python/Node dependency audits.
- `client/package.json` defines `npm test` as `vitest run`, `npm run type-check` as `tsc --noEmit`, and `npm run build` as `vite build`.
- `.github/workflows/test.yml` runs on `ubuntu-latest` and calls `python tests/run_all_tests.py`; it also runs `npm ci` and `npm run build` in a separate frontend job.
- `tests/fixtures/crisis_regression_cases.json` is present and contains labelled crisis regression cases. The contents of every test module and the full dataset inventory could not be established.

## Preliminary source-review findings (not runtime-reproduced)

### F-01 — Master runner uses Windows shell commands in a Linux workflow
**Evidence:** `tests/run_all_tests.py` builds commands starting with `cmd.exe /c` for frontend type-checking, frontend tests, and production build. `.github/workflows/test.yml` calls the master runner on `ubuntu-latest`.
**Impact:** These three subprocesses are expected to fail under the Linux runner unless a Windows `cmd.exe` compatibility layer is unexpectedly installed. This can cause the CI backend job to fail even if the frontend's separate build job passes.
**Recommended follow-up:** Replace Windows-specific shell invocation with platform-independent argument-list subprocess calls (or run the commands in their own CI steps); verify on Ubuntu and Windows.
**Confidence:** High for the incompatibility; actual CI run status not retrieved.

### F-02 — Dependency-audit failures are converted to success flags
**Evidence:** `run_security_audits()` sets `pip_ok = True` after a failed `pip-audit` command and `npm_ok = True` after a failed `npm audit` command, following warning output.
**Impact:** The master summary can report dependency audits as passing even though an audit command failed. A network failure and a vulnerability finding should be distinguishable, but neither should be represented as an unconditional pass.
**Recommended follow-up:** Preserve non-zero audit status; optionally classify network/tooling errors separately, while keeping the release decision fail-closed or explicitly “inconclusive.” Add tests for a vulnerable dependency, audit-tool failure, and network failure.
**Confidence:** High; visible directly in the runner; not executed.

### F-03 — Rate limiter trusts `X-Forwarded-For`
**Evidence:** `server/app.py` chooses the first IP in the client-provided `X-Forwarded-For` header as the rate-limit key, falling back to `request.remote_addr` only when the header is absent.
**Impact:** If Flask is directly reachable or the reverse proxy does not overwrite/validate that header, a client can send changing IP values and potentially evade the per-IP rate limit.
**Recommended follow-up:** Add a test sending repeated requests with changing `X-Forwarded-For`; define and test a trusted-proxy policy. Use the connection address unless requests arrive through a known proxy that sanitizes forwarding headers.
**Confidence:** Conditional on deployment/proxy configuration; no deployment config was executed.

### F-04 — Release gate may crash when the aggressive suite cannot be imported
**Evidence:** `run_aggressive_suite()` catches import/execution exceptions and returns `(0, 0)`. The caller then calculates `agg_passed / agg_total` for its result message without guarding against zero.
**Impact:** If the expected test module is missing or import fails, the release gate can crash with `ZeroDivisionError` rather than producing a controlled FAIL report.
**Recommended follow-up:** Verify the imported module exists in the checkout; guard the denominator and make a missing/empty suite fail explicitly. Add a test for import failure.
**Confidence:** High for the zero-denominator path; whether the current module import succeeds is not established.

### F-05 — Privacy claims need behavior-level proof
**Evidence:** `docs/PRIVACY_AND_SECURITY.md` claims sensitive message/prompt redaction. The visible `PrivacyRedactionFilter` in `server/app.py` specifically regex-masks credential-like strings in `record.msg`; the chat route logs message length rather than the message body in one inspected statement.
**Impact:** The filter alone does not prove all logging paths are free of user content, prompts, tokens, and personal data. Exception strings and third-party library loggers also need inspection.
**Recommended follow-up:** Capture logs from normal, crisis, provider-error, database-error, and malformed-input paths and assert that sentinels representing message bodies and secrets never occur.
**Confidence:** Documentation/test gap, not a confirmed user-text leak.

### F-06 — Crisis resource documentation has a path inconsistency
**Evidence:** `docs/CRISIS_RESOURCES_MAINTENANCE.md` names `server/crisis_resources.py`, while the inspected backend imports `services.crisis_resources` and the source file is located at `server/services/crisis_resources.py`.
**Impact:** Maintainers may follow a stale path when updating emergency resources.
**Recommended follow-up:** Confirm the documented path against the full tracked-file tree and correct documentation if stale.
**Confidence:** High for the mismatch in the inspected documents/source.

## Baseline command status

| Command | Result in this workspace | Reason |
|---|---|---|
| `python tests/run_all_tests.py` | Not run | Repository could not be cloned; no local checkout exists |
| `python -m pytest tests/backend -v` | Not run | Repository could not be cloned; no local checkout exists |
| `cd client && npm test` | Not run | Repository could not be cloned; dependencies not installed |
| `cd client && npm run type-check` | Not run | Repository could not be cloned; dependencies not installed |
| `cd client && npm run build` | Not run | Repository could not be cloned; dependencies not installed |
| Crisis release gate and benchmarks | Not run | Repository/data files not available locally |
| Coverage | Not measured | No tests executed in a checkout |

## Exact next steps to complete Phase 0

1. Provide a local checkout to this environment by uploading a ZIP of the repository (exclude `.env`, live credentials, personal data, and unnecessary model binaries), or connect the GitHub integration and provide repository access if offered.
2. Inventory every tracked source/test/fixture file and read the tests before adding new ones.
3. Run baseline commands in the project's intended environment and capture logs/exit codes. The Windows-specific calls in the master runner may prevent a clean Ubuntu baseline; run individual frontend commands separately so their outcomes are visible.
4. Measure coverage only after the baseline is runnable; report exact tool/command, module coverage, and any exclusions.
5. Update `TEST_PLAN.md` and present the verified Phase 0 results before Phase 1.
