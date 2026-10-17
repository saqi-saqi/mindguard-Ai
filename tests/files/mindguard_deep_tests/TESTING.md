# MindGuard deep test suite

## Install into your repo
Copy these into the root of `mindguard-Ai`:

    tests/deep/        -> mindguard-Ai/tests/deep/
    e2e/               -> mindguard-Ai/e2e/
    requirements-test.txt

    pip install -r requirements-test.txt            # plus your existing server/requirements.txt
    npm i -D @playwright/test @axe-core/playwright && npx playwright install

## Run
    # 1) first run: see what the suite auto-discovered (routes, chat/login/register)
    python -m pytest tests/deep -k route_inventory -s

    # 2) everything backend (crisis rules, pipeline, API, auth, DB, security)
    python -m pytest tests/deep -v

    # 3) by layer
    python -m pytest tests/deep/test_01_crisis_rules.py -v          # Tier 1
    python -m pytest tests/deep/test_02_pipeline_safety.py -v       # Tier 1->2->3 via real API
    python -m pytest tests/deep/test_03_api_auth_db_security.py -v  # API/auth/DB/security

    # 4) frontend + full stack (start the app first: docker-compose up -d)
    BASE_URL=http://localhost:5173 npx playwright test e2e/mindguard.spec.ts

## How it adapts to your code
I could only read your README, not the source, so names are DISCOVERED at runtime
(Flask url_map, functions in crisis_rules.py, services). If something is mis-detected,
edit the OVERRIDES dict at the top of tests/deep/mg_adapter.py. Nothing else needs editing.

Safety: the suite uses mongomock (never your real DB), a fake Gemini key, and BLOCKS all
non-loopback network access, so it can never call Gemini or touch real data.

## Reading results
* A failure whose message starts with "FINDING" is a real defect in MindGuard (false
  negative, false positive, leak, vulnerability). Fix the code, not the test.
* "POLICY" tests encode a decision (e.g. negated intent not flagged, weak passwords
  rejected, no US hotlines). If you decide differently, edit the data in mg_cases.py.
* Skips explain why (e.g. no history route found), they are not silent passes.
* Extend coverage by adding phrases to tests/deep/mg_cases.py: every list is
  parametrized, so one line = one new test.

## What is covered
test_01  Tier-1 rules: ~190 cases. Recall per category (EN / Roman Urdu / Urdu), homicide,
         combined threats, false-positive traps, negation, 50 evasion variants, spelling
         variants, buried-in-long-text, garbage input, ReDoS timing, determinism, latency,
         "Tier 1 imports no ML/network", existing regression fixture, recall/FPR gate.
test_02  Pipeline: crisis flagged via API, bypasses Gemini (spy + network guard), Tier-2/3
         failure injection, KB fallback, 1122 present, no 988/911, no diagnosis/dosing,
         prompt-injection + secret-leak attempts, multi-turn escalation.
test_03  Validation (14 bad bodies, malformed JSON, 5MB payload, wrong methods), register/
         login, duplicate users, user enumeration, NoSQL injection (login+register), bcrypt
         at rest, hash never in responses, weak passwords, tampered / alg=none / expired
         JWT, garbage auth headers, anonymous-access audit of EVERY route, IDOR on history,
         60/min rate limit (+ per-IP, + X-Forwarded-For bypass), CORS, log redaction,
         DB persistence/indexes, concurrency + race on registration, secret scanning,
         .env hygiene, Dockerfile checks, weak-secret fallback in config.
e2e      28 Playwright tests: auth/session/logout/expired token, crisis UI in EN/Roman Urdu/
         Urdu, dialog a11y, XSS, long/empty/double sends, backend down/500/slow, RTL text,
         3 viewports, axe a11y, keyboard-only, no secrets in browser, no third-party calls.
