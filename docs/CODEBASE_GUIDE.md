# MindGuard AI — Complete Codebase Guide

*What every file does, why it exists, how it works, how errors are handled, and why the tech stack was chosen.*

> **What MindGuard is:** a full-stack mental-health support chatbot whose single most important job is **safety** — detecting crisis risk in a user's message with a layered ("3-tier") pipeline and escalating to real human help, while ordinary supportive conversation is handled by AI. It is a research prototype, not a medical device, and never claims to diagnose or treat.

**How to read this guide:** Section 1–2 explain the system as a whole (read these first). Sections 3–10 are the file-by-file reference. Section 11 lists known quirks honestly.

---

## 1. The big picture

```
User message (React client, localhost:5173)
        │  POST /api/chat
        ▼
Flask API (server/app.py)  ── auth, rate limiting, security headers
        │
        ▼
Step 0.5  Pre-LLM Safety Classifier      services/safety_classifier.py
        │   ├─ deterministic regex (harm-to-others / self-harm)
        │   ├─ semantic LLM classifier (services/semantic_safety_classifier.py)
        │   └─ cross-turn context (services/session_context.py)
        │   ► HIGH RISK here → fixed safety panel + helplines, ALL AI bypassed
        ▼
Step 1   Tier 1 — Deterministic Rules     services/crisis_rules.py
        │   ├─ text_normalizer + generalizer (evasion, algospeak, frames)
        │   ├─ pattern categories (English + Roman Urdu, severity 1–5)
        │   ├─ guards (negation, recovery, sarcasm, hyperbole, academic…)
        │   └─ precedence_arbitrator (11 numbered rules) — final authority
        │   ► crisis here → fixed emergency response + CrisisModal
        ▼
Step 2   Tier 2 — ML ensemble             services/huggingface_service.py
        │   ├─ fine-tuned distilRoBERTa (140k crisis dataset)
        │   ├─ calibrated TF-IDF crisis detector, intent, emotion, sentiment
        │   └─ can ELEVATE risk, never lower a Tier-1 flag
        ▼
Step 2.5 Gemini safety guardrail          services/llm_service.py
        │   └─ borderline confidence (0.30–0.85) → strict-JSON verifier
        ▼
Step 3   Tier 3 — Supportive response     services/llm_service.py + response_kb.py
            Gemini → Ollama (offline) → emotion-matched offline templates
```

**The one rule that governs everything:** crisis at ANY tier short-circuits all generative AI and returns a fixed, hard-coded emergency response with verified Pakistan helplines. ML and the LLM can raise a flag but can never silence Tier 1. On any internal error the system *fails closed* (treats the message as crisis) rather than silently doing nothing.

### A message's life, step by step

1. The React client posts the message (max 2,000 chars) to `POST /api/chat`.
2. `app.py` rate-limits the caller (60 req/min/IP), assigns a request ID, and validates the payload.
3. **Step 0.5** — `safety_classifier.classify_safety_risk()`: regex + a dedicated semantic LLM pass, fused by an inverted-authority rule (the more severe of the two wins). Categories: `COMBINED_HIGH_CRISIS` > `HARM_TO_OTHERS_RISK` > `SELF_HARM_RISK` > `THIRD_PARTY_REPORT` > `EMOTIONAL_DISTRESS` > `NONE`. High-risk categories return the fixed safety panel immediately — Gemini never sees the text.
4. **Step 1** — `crisis_rules.evaluate_crisis_pipeline()`: normalize (`text_normalizer` → `generalizer`) → route Roman Urdu (`roman_urdu_router` → `roman_urdu_normalizer`) → match pattern categories per sentence/segment → apply context guards (`_contextual_bypass_reason`) → combine signals (`temporal_engine`, `discourse_evaluator`, `semantic_concepts`) → decide (`precedence_arbitrator`). Crisis → fixed response; suppressed Tier-1/2 anchors → gentle `LOW_CONFIDENCE_RISK` check-in.
5. **Step 2** — `huggingface_service.analyze_user_message()`: clause-aware crisis transformer + TF-IDF detector + emotion/sentiment/intent classifiers, with an always-on regex safety floor. Confidence ≥ 0.85 → crisis; 0.30–0.85 → the Gemini guardrail verifies.
6. **Step 3** — `llm_service.generate_llm_response()`: Gemini (with circuit breakers) → local Ollama → offline emotion-matched templates. Grounding exercises (4-7-8 breathing) attach from `response_kb`.
7. The client renders the reply with risk/intent/emotion chips; any high-risk level opens `CrisisModal` with one-tap verified helplines.

---

## 2. Tech stack and why each piece was chosen

| Technology | Where | Why this and not something else |
|---|---|---|
| **Flask** (Python) | server/app.py | Small, explicit, synchronous — ideal for a safety pipeline you must be able to read end-to-end. A big framework (Django) hides request flow; FastAPI's async adds complexity the safety review doesn't need. |
| **MongoDB + PyMongo** | server/database.py | Chat messages, mood logs and session state are document-shaped and schema-flexible; mongomock lets 220+ tests run with **zero database installed**. |
| **bcrypt + PyJWT** | server/auth.py | Industry standard: bcrypt for password hashing (slow by design), JWT for stateless sessions (24 h expiry). |
| **React 18 + Vite** | client/ | Fast dev server, instant HMR for the demo, SPA with no router needed (tab state). |
| **Tailwind CSS 4** | client/ | Utility classes keep the UI consistent without a design-system layer; dark slate theme suits a low-stimulation mental-health UI. |
| **PyTorch + HuggingFace Transformers** | ml/finetune_crisis_roberta.py | Fine-tuning distilRoBERTa is the standard low-cost transformer recipe; 6-layer model runs on CPU (~69 ms/message), which matters because the demo machine has no GPU. |
| **scikit-learn TF-IDF** | ml/train_crisis.py | Calibrated LogisticRegression on TF-IDF is transparent, fast, and gives a calibrated probability for threshold tuning (recall-first threshold selection). |
| **google-genai (Gemini)** | server/services/llm_service.py | Tier-3 conversation quality with an official SDK; wrapped in circuit breakers because the demo venue Wi-Fi can't be trusted. |
| **Ollama (local LLM)** | llm_service.py | Offline fallback so the demo works with zero internet — crisis detection never depends on this path. |
| **Docker Compose** | docker-compose.yml | One-command reproducible deployment (Mongo + backend + NGINX frontend) with health-gated startup order. |
| **pytest + Vitest** | tests/ | Standard runners for the Python and React suites; axe-core-style a11y assertions live in the Vitest tests. |

---

## 3. Error-handling philosophy (read this before the file list)

Every module follows the same direction of failure: **toward safety**.

1. **Fail closed** — `crisis_rules.evaluate_crisis_pipeline` wraps its whole body in try/except; any unexpected error returns `is_crisis=True, needs_human_review=True` with the safety template. Silence is never acceptable.
2. **Inverted authority** — `safety_classifier` fuses deterministic + semantic results with `max()`: the deterministic tier can always escalate; the semantic/LLM tier needs confidence ≥ 0.70 to override, and never overrides `active_escalation_in_progress`.
3. **Circuit breakers** — `llm_service` opens a 60 s per-model quota breaker on 429s and a global connectivity breaker on connection/auth errors, so a dead API key burns 1 attempt, not 4 model candidates × every message.
4. **Fallback chains** — Gemini → Ollama (2 s timeout) → emotion-matched offline templates; guardrail failure → confidence-threshold triage; model load failure → regex safety floor still catches crisis phrases.
5. **Structured errors** — every Flask error (400/404/405/413/429/500) returns the same JSON envelope `{success, data, error:{code,message}}`; internals never leak.
6. **Privacy under failure** — logs redact `Bearer`/`key=` tokens (`PrivacyRedactionFilter`); session context stores classification metadata only, never raw text; audit events store metadata only.
7. **Abuse resistance** — sliding-window rate limit (60/min/IP), 1 MB body cap, CSP + nosniff + frame-deny headers, JWT fail-fast on weak production secrets.
8. **Client-side mirrors** — every fetch uses a guarded JSON parse; failed sends produce an error bubble with a Retry button; the crisis modal is fully offline-capable (no fetch calls at all).

---

## 4. Server — `server/` (23 Python files, ~8,600 lines)

### `server/app.py` (~1,230 lines) — the HTTP layer and pipeline conductor
- **Purpose:** every HTTP route, all middleware, and the `/api/chat` multi-tier pipeline.
- **Why it exists:** the single entry point the frontend talks to; without it there is no API.
- **Key pieces:** `PrivacyRedactionFilter` (masks credentials in logs); `is_rate_limited` sliding-window limiter (60 req/min/IP, lock-protected); `before_request` (request ID + rate limit on `/api/*`); `after_request` (CSP, nosniff, frame-deny, request-ID echo); uniform JSON error handlers; `chat()` (L588–1118) implementing Steps 0.5 → 3 with the crisis session state machine (`crisis_active` → `elevated_monitoring`, sticky follow-ups, cooling windows, clearance tokens).
- **Routes (complete):** `/` and `/<path>` (SPA), `/api/health`, `/api/resources`; auth: `register`, `login`, `me`, `account` (DELETE); privacy: `user/settings` (GET/PUT), `user/safety-profile`, `user/trusted-contact`, `user/export`, `user/data` (DELETE); moods: `POST/GET /api/moods`, `DELETE /api/moods/<id>`; `GET /api/analytics`; sessions: `GET/POST /api/chat/sessions`, `GET /api/chat/history`, `POST /api/chat/summarize`, `POST /api/chat/sessions/<id>/summarize`; core: `POST /api/chat` (optional JWT); crisis clear: `POST /api/chat/session/<id>/clearance-token`, `POST /api/chat/session/<id>/safety-clear` (JWT **or** HMAC token); feedback: `POST /api/feedback`, `POST /api/safety-feedback`; admin: `POST /api/admin/retention-cleanup`.
- **Error handling:** uniform error envelope; health check degrades to 503 `degraded` if DB ping fails; `init_db` failure logs but doesn't crash boot; `/api/chat` wrapped in one try/except (500 with generic message); `safety-clear` maps `KeyError/PermissionError/ValueError` → 404/403/400.
- **Startup:** import all services (compiles regexes, loads config) → logging + redaction → Flask app + 1 MB body cap → CORS → `init_db` (non-fatal) → background thread pre-warms ML models (guarded against double-load under the reloader) → `app.run()`.

### `server/auth.py` (169 lines) — authentication
- **Purpose:** bcrypt hashing, JWT issuance/validation, the `jwt_required` / `admin_required` / `optional_jwt` decorators.
- **Why:** user accounts, per-user data isolation, and the 24 h token session.
- **Error handling:** production **fails fast at import** if `JWT_SECRET_KEY` is missing, weak (<32 chars), or a known dev default; dev mode auto-generates an ephemeral key with a warning. Token verification never raises (returns `False` or typed error strings).

### `server/config.py` (41 lines) — configuration
- **Purpose:** loads `../.env` (python-dotenv) and exposes ~16 constants (Gemini key, CORS origins, Mongo URI/name, mongomock flag, Flask host/port, rate limits, `MAX_MESSAGE_LENGTH=2000`, retention default).
- **Error handling:** dotenv import swallowed if absent; safe coercions with defaults — config never crashes the app.

### `server/database.py` (659 lines) — persistence layer
- **Purpose:** the only module touching MongoDB: connection + indexes + all CRUD (users, chat messages/sessions, mood logs, audit logs, cooling windows, clearance tokens, retention cleanup, export/erasure).
- **Why it matters for safety:** it implements the **crisis session state machine** — `set_session_risk_state` (optimistic version locking, auto cooling-window), `generate/verify_clearance_token` (HMAC-SHA256, 5-min TTL, constant-time compare), `clear_session_crisis_state` (guarded transition + audit).
- **Error handling:** mongomock fallback when `USE_MONGOMOCK=true`; 5 s server-selection timeout; optimistic-lock `ValueError` on version conflict; permission errors typed for HTTP mapping; privacy export strips `_id`/`password_hash`.

### `server/services/__init__.py` (14 lines)
Re-exports the cross-turn safety API (`get_session_context`, `record_safety_event`, `canonicalize_message`, `classify_semantically`) for tests and package-path imports.

### `server/services/crisis_rules.py` (~1,790 lines) — Tier 1 brain
- **Purpose:** deterministic regex engine + pipeline orchestrator + response templates. The most important file in the system.
- **Structure:** helpers (`_normalize` with algospeak/leetspeak expansion, `_split_sentences`, `_split_contrastive_segments` — commas never split, contrastives do) → **pattern categories**: 7 English (severity 3–5) + 6 Roman Urdu (flag `ROMAN_URDU_RULES_ENABLED`, default on) → **guard chain** `_contextual_bypass_reason`: contrast clauses, Urdu span-scoped guards (hyperbole/past-recovery/sarcasm/negation, escalation-marker veto), third-party subjects, accidental context, idioms, negation-with-lethal-override, past reflection, academic, media, situational → `evaluate_crisis` (per-segment matching + bypass metadata) → templates (`SAFETY_RESPONSE_TEMPLATE`, `LOW_CONFIDENCE_CHECKIN_TEMPLATE`, `THIRD_PARTY_GUIDANCE_TEMPLATE`) → `evaluate_deterministic_crisis` (gate-facing adapter) → `evaluate_crisis_pipeline` (Steps: preprocess → Urdu routing/normalization → Urdu + English third-party routing → modular signals → `arbitrate()` → crisis | bypass (+`LOW_CONFIDENCE_RISK` when a severity-≥4 anchor was suppressed) | ML fallback | non-crisis).
- **Error handling:** whole pipeline **fails closed** (exception → `is_crisis=True, needs_human_review=True`); Urdu routing individually try/except; empty input → safe non-crisis.

### `server/services/intent_rules.py` (195 lines)
- **Purpose:** the canonical first-person crisis regexes (single source of truth — imported by the engine, the ML service, and the LLM service), the distress-signal gate, and fast-path non-crisis intents (anxiety, sleep, coping, physical need, grief, bot info, greetings).
- **Error handling:** pure functions; None/empty → `False`/`None`. Distress-carrying messages bypass fast-path routing so "I can't sleep" vs "I can't sleep and want to die" diverge correctly.

### `server/services/crisis_resources.py` (215 lines)
- **Purpose:** the curated Pakistan helpline directory (Police 15, Rescue 1122, Edhi 115, Umang, Rozan, CPWB 1121, Madadgaar 1098, Taskeen) with per-resource verification metadata and a 180-day re-audit workflow, plus `SAFETY_DISCLAIMER`.
- **Error handling:** a bad date → status `PENDING_REVIEW` + `is_outdated=True` (**fail-visible**, not fail-silent); unknown region falls back to Pakistan.

### `server/services/llm_service.py` (491 lines) — Tier 2.5 + Tier 3
- **Purpose:** Gemini generation with the Tier-2.5 strict-JSON safety guardrail, four-level fallback, two circuit breakers.
- **Key pieces:** `SAFETY_GUARDRAIL_PROMPT` + `strict_parse_guardrail_json` (rejects JSON injection / multi-object payloads); `_MODEL_QUOTA_EXCEEDED_UNTIL` (per-model 60 s breaker on 429); `_GEMINI_CONNECTIVITY_BROKEN_UNTIL` (global 60 s breaker); `query_local_ollama` (localhost:11434, 2 s timeout, no-proxy); `generate_llm_response` chain: keyword KB → Gemini loop → Ollama → emotion fallback; `sanitize_prompt_content` (XML-escape, anti-injection).
- **Error handling:** guardrail failures return `None` → caller falls back to confidence-threshold triage; the fallback chain always ends in a response (offline templates).

### `server/services/huggingface_service.py` (345 lines) — Tier 2
- **Purpose:** loads six artifacts (crisis RoBERTa, emotion, sentiment, TF-IDF crisis, TF-IDF intent) in offline mode and runs `analyze_user_message`: multi-turn window → clause-aware crisis scoring → combined probability → negation check → emotion/sentiment → intent with abstention → **always-on regex safety floor**.
- **Error handling:** each model load/inference independently try/except; `_ML_LOAD_FAILED` flag stops retry storms; catch-all returns neutral defaults; the regex floor guarantees detection even if every model is dead.

### `server/services/generalizer.py` (361 lines)
- **Purpose:** upstream preprocessing producing `PreprocessResult` — algospeak normalization (~40 rules: "unalive"→"kill myself"), academic/fictional/third-party frame detection, past-recovery vs present-ideation, preparatory vs protective behavior, coping-query detection.
- **Why:** the difference between "I wrote an essay about suicide" (benign) and "I plan to end it" (crisis) is *context*, not keywords.
- **Error handling:** None-safe, 10,000-char cap with `is_truncated` flag, documented ReDoS-safe patterns, negation guard inside preparatory-behavior detection.

### `server/services/temporal_engine.py` (328 lines)
- **Purpose:** past-anchor / confirmed-resolution / acute-relapse extraction with a decision matrix ("used to be suicidal" + "it's happening again" = imminent relapse). Feeds arbitration rules 3, 7, 9.
- **Error handling:** layered fallbacks so a missed layer degrades gracefully; resolution requires **positive evidence** (absence of distress is not resolution).

### `server/services/discourse_evaluator.py` (308 lines)
- **Purpose:** multi-sentence sarcasm/hyperbole evaluation — "this exam is killing me lol" downgrades; "I'm fine lol. I have the pills ready." never downgrades. 7-branch decision, method/planning/escalation markers block any downgrade.
- **Error handling:** fail-safe default is **no downgrade** on ambiguity.

### `server/services/semantic_concepts.py` (199 lines)
- **Purpose:** positive/negative grammar pairs for three figurative concepts — fatal sleep ("I just want to sleep and not wake up"), concealment ("no one would find me"), irreversible exit — with negative blockers ("slept until noon", "surprise party").
- **Error handling:** pure functions; blocked matches return a `blocked_by` audit trail.

### `server/services/precedence_arbitrator.py` (324 lines)
- **Purpose:** the single decision point — 11 numbered precedence rules combining all signals into one verdict with a full reasoning audit. Escalation rules (relapse, preparatory behavior, semantic concepts) all precede bypass rules (past narrative, academic, ambiguity).
- **Error handling:** conservative ordering; ambiguity defaults to human review, never silence.

### `server/services/text_normalizer.py` (273 lines)
- **Purpose:** anti-evasion canonicalization: confusable folding (Cyrillic/Greek lookalikes), zero-width stripping, punctuation normalization, intra-word emoji stripping, spaced-token compaction (only for crisis keywords), leet expansion ("k!ll", "catch the bus").
- **Error handling:** pure functions; **Urdu/Arabic script explicitly preserved** (scope exclusion — the Roman Urdu subsystem handles that path).

### `server/services/safety_classifier.py` (515 lines) — Step 0.5
- **Purpose:** the pre-LLM gate with 6 risk categories; fuses deterministic regex with the semantic LLM classifier via **inverted authority** (`max()` of the two; semantic override needs confidence ≥ 0.70); cross-turn combination via `session_context` (120 s window).
- **Error handling:** every cross-module call individually try/except; semantic failure → deterministic-only; deterministic can always escalate.

### `server/services/semantic_safety_classifier.py` (384 lines)
- **Purpose:** an *isolated* Gemini classification call (separate from the chat generator so a jailbreak of one can't compromise the other) with a strict-JSON parser and a **9-stage regex fallback** for tests/no-key/offline.
- **Error handling:** testing env or missing key → fallback immediately; unparseable output → fallback; the fallback always returns a well-formed result dict.

### `server/services/session_context.py` (155 lines)
- **Purpose:** anonymous in-memory cross-turn store (15-min TTL, max 10 events, thread-safe) holding classification metadata only — never raw text. Enables "turn N: I want to hurt them" + "turn N+1: and then myself" = COMBINED_HIGH_CRISIS.

### `server/services/calibration_monitor.py` (136 lines)
- **Purpose:** 22 benchmark fixtures run through the full pipeline; verifies sensitivity ≥ 95% and **zero Tier-1 bypasses**. The release gate's invariant checker.

### `server/services/roman_urdu_router.py` (86 lines)
- **Purpose:** routes each message to English / Roman-Urdu / both (more severe wins) / Arabic-script fallback. Arabic-script input returns a gentle check-in with resources — never "nothing to see".

### `server/services/roman_urdu_normalizer.py` (201 lines)
- **Purpose:** Urdu-texting normalization — 31 justified word folds ("mjhe"→"mujhe"), phrase folds ("khud kushi"→"khudkushi"), repeat collapse ("marrrr"→"mar"), and edit-distance-1 fuzzy correction **restricted to crisis vocabulary only**. `FORBIDDEN_FOLDS` documents meaning-changing pairs that must never fold ("mein"=in vs "main"=I). English passes through byte-identical (property-tested).

### `server/services/response_kb.py` (192 lines)
- **Purpose:** instant (<1 ms) canned psychoeducational responses for 17 intents + grounding exercises + default fallback. Powers the fast-path intents and the offline tier.

---

## 5. Client — `client/`

### Config files
- **`package.json`** — scripts (`dev`, `build`, `type-check`, `test`); deps: React 18.3, lucide-react icons, recharts, Vitest/Testing Library. (Known quirk: `recharts`, `canvas-confetti`, `axe-core`, `jest-dom` are declared but unused — analytics charts are hand-rolled CSS bars.)
- **`vite.config.js`** — React + Tailwind plugins; dev server :5173; **proxy `/api` → `http://127.0.0.1:5000`** (kills CORS in dev).
- **`vitest.config.ts`** — jsdom environment for component tests.
- **`tsconfig.json`** — loose TS (`strict:false`) for the `.tsx` components.
- **`index.html`** — mount point, shield favicon.
- **`Dockerfile` + `nginx.conf`** — build → NGINX; `location /api/` proxies to the compose service; SPA fallback for refresh-safe routing.
- **`package-lock.json`, `.dockerignore`** — reproducible installs, small build context.

### Source files
- **`src/main.jsx`** — mounts `<App/>` (or `<DocScreenshots/>` when `?screen=` is in the URL — the documentation-screenshot harness with mock data and zero fetches).
- **`src/App.jsx` (247 lines)** — root orchestrator: restores JWT session from `localStorage`, fetches settings/moods/history with `AbortController`, owns the crisis-modal open state, wires all callbacks down. **Error idiom:** every fetch is `res.ok ? res.json().catch(()=>null) : null`; telemetry failures are `console.warn` only ("optional telemetry must never prevent access").
- **`src/components/types.ts`** — shared TypeScript interfaces (MindUser, MoodLog, ChatMessage with `risk_level`/`grounding_exercise`, CrisisResources…).
- **`src/components/ChatInterface.tsx` (787 lines)** — the chat: composer (2,000-char guard, Enter/Shift+Enter), message bubbles with risk ribbons (crisis rose, third-party amber with `tel:` links), grounding-exercise card with 4-7-8 breathing timer, error bubble + Retry, `aria-live` announcements, auto-resizing textarea. On high-risk replies calls `onOpenCrisisModal(resources, "detected")`; "I'm safe now" POSTs the safety-clear endpoint.
- **`src/components/CrisisModal.tsx` (726 lines)** — full-screen modal, deliberately ≤3 primary actions (emergency dispatch → personal trusted contact → 24/7 Umang line), progressive-disclosure directory, breathing tool, sticky "I'm safe for now". A11y: `role="dialog"`, focus trap + restoration, Escape-to-close, ≥38 px touch targets. **Makes zero network calls** — works fully offline; close/Escape/backdrop never record a safety outcome (only the explicit button does).
- **`src/components/AnalyticsDashboard.tsx` (566 lines)** — mood check-ins (1–10 slider with ARIA value text, context tags, notes), POST `/api/moods` with a 1.5 s double-submit debounce, client-computed reflection copy ("recent check-in story"), low-score support prompt linking to chat. Non-diagnostic language enforced.
- **`src/components/SettingsPanel.tsx` (487 lines)** — data sovereignty: consent + retention (1–365 days), trusted contact (masked phone, mandatory "never contacts automatically" notice), safety profile, JSON export (Blob download), two-step account deletion gated on typing "DELETE".
- **`src/components/AuthScreen.tsx` (240 lines)** — login/register with a **required consent checkbox** before any sensitive text is processed; supports both response-envelope shapes.
- **`src/components/Navigation.tsx` (230 lines)** — desktop sidebar + mobile drawer, `aria-current` tabs, emergency-helpline button, body-scroll lock while the drawer is open.
- **`src/index.css`** — Tailwind import, dark slate theme, `fade-in` animations, focus-visible outlines, and a full `prefers-reduced-motion` block that disables animation globally.
- **`src/__tests__/`** — 33 tests across 4 files: ChatInterface (10 — crisis-modal triggers, banner persistence, safety-clear), CrisisModal (11 — ARIA, focus trap, "only the safe button records", no US/UK numbers), AnalyticsDashboard (7 — slider ARIA, POST body), SettingsPanel (5 — masking, typed-DELETE).

---

## 6. ML — `ml/`

- **`training_utils.py`** — shared TF-IDF pipeline (word 1–2 gram + char 3–5 gram, 50k features each) and **leakage guard**: `load_splits()` hashes files and fails hard if any normalized text appears in two splits. Saves `.joblib` + sibling `.metrics.json`.
- **`train_crisis.py`** — binary crisis classifier: TF-IDF → calibrated LogisticRegression; **5-fold CV threshold selection targeting recall ≥ 0.95 then max precision**; outputs `artifacts/crisis_detector.joblib` with an embedded safety note ("never the sole crisis control").
- **`train_intent.py`** — multiclass intent with **confidence abstention** (below threshold → "fallback" label; measured accepted-accuracy vs coverage); out-of-scope rejection diagnostics.
- **`train_sentiment.py`** — 3-class SGDClassifier; the simplest trainer.
- **`finetune_crisis_roberta.py`** — fine-tunes distilroberta-base on the 140k crisis corpus (3 epochs, best-by-F1, batch 32 GPU / 8 CPU, max_length 128) → `artifacts/huggingface_crisis_roberta/`.
- **`finetune_crisis_roberta_urdu.py`** — continue-trains on 21.7k augmented Roman Urdu + 15k English replay (anti-forgetting), writes to a **candidate dir only**, temperature-scales (T=2.0), selects the threshold for recall ≥ 98% first, and prints manual promotion gates. Fixed seed 42.
- **`augment_roman_urdu.py`** — synthesizes 21.7k balanced samples from 107 template grammars × 3 noise levels (spelling variants, character typos, code-switching); **template-diversity gate** (fails if any template > 2%); excludes all benchmark texts (disjointness).
- **`download_232k_dataset.py`** — builds the crisis corpus from Hugging Face (3 fallback repos), 10× oversamples the 300 edge cases (dedupe-before-oversample — the fixed bug), stratified 80/10/10 split.
- **`generate_multiturn_data.py` / `generate_multiturn_intent_data.py`** — prefix 50% of rows with 1–2 turns of context so classifiers survive multi-turn conversations.
- **`refine_datasets.py`** — the original cleaner: de-identification (URLs/emails/handles), duplicate-label conflict removal, intent taxonomy consolidation (80→refined), deterministic stratified splits, validation + provenance manifest.
- **`predict_crisis.py`** — CLI smoke test for the TF-IDF artifact (prints JSON verdict).
- **`test_huggingface_models.py`** — manual exploration of pretrained emotion/sentiment/zero-shot pipelines on 11 tricky samples; every section try/except so a missing model only warns.

---

## 7. Scripts — `scripts/`

**Safety gates**
- **`release_gate_crisis.py`** — the CI pass/fail bar: v1 fixture 43/43 must pass, v2 paraphrase fixture (162 tuning / 50 held-out) with an overfitting-gap check (>15 pp flags), 238-case aggressive suite at 100%, dev benchmark (~530), locked 100-case holdout with recall ≥ 95 / FPR ≤ 5 gates, and the calibration invariant audit (zero Tier-1 bypasses). Exit 1 on any failure.
- **`run_aggressive_gate.py`** — fast re-run of the 238-case suite with per-category breakdown for rule-tuning loops.
- **`verify_clean_install.py`** — imports every runtime dependency, boots Flask, asserts `/api/health` = 200.

**Roman Urdu harness**
- **`build_roman_urdu_benchmark.py`** — 216 skeletons → 522 cases (4 style variants), dedupe, balance gate (≥8 TEST skeletons per T1/T2 category).
- **`split_roman_urdu_benchmark.py`** — skeleton-grouped 60/40 DEV/TEST; freezes TEST read-only with a SHA-256 logged in `artifacts/test_runs.json`.
- **`eval_roman_urdu_dev.py`** — DEV-only metrics harness (tier/category/style metrics, Wilson CIs, conservative skeleton-cluster recall, error file with root causes). Defines the route semantics: crisis route vs guidance route vs any-escalation.
- **`eval_roman_urdu_holdout.py`** — **the only code allowed to read the frozen TEST**: verifies the hash, enforces the ≤3-runs contamination flag, prints aggregates + failing IDs only, never case text.
- **`make_reviewer_sheets.py`** / **`compute_kappa.py`** — blind reviewer sheets (guide-example exclusion via Jaccard ≥ 0.7) and Cohen's kappa with adjudication routing.
- **`build_roman_urdu_adversarial.py`** — 127 hand-authored hard cases (negation placement, hedged negation, temporal mixes, sarcasm, religious framings, third-party, harm-to-others).
- **`check_ml_disjoint.py`** — fails if ML training data overlaps any benchmark text (leakage guard).

**Evaluation & reporting**
- **`evaluate_crisis_roberta.py`** — stratified n=2000 test-subsample eval (+latency, threshold sweep) + four 300-case English benchmarks.
- **`build_report_numbers.py`** — aggregates every artifact into `report_numbers.json`; the deck/poster read **only** this file (single source of truth for claims).
- **`benchmarks/`** — stress test (1,000+ samples → latency + accuracy), matrix sets A–J (thesis tables), multiturn API check, guardrail-on-failures experiments (Gemini + offline Ollama), pitch latency measurement.

---

## 8. Tests — `tests/`

- **`run_all_tests.py`** — 7-stage master pipeline: pytest → clean-install verify → release gate → frontend type-check → Vitest → production build → security audits (`pip-audit`, `npm audit`; warn-only). Exits 1 if any hard stage fails.
- **Backend suites (221 pytest functions):**
  - `test_safety_and_crisis_engine.py` (73) — Tier-1 engine + the 238-case aggressive suite.
  - `test_crisis_authority_model.py` (34) — proves Tier 1 cannot be overridden by ML/LLM.
  - `test_api_and_security.py` (23) — auth, CORS, rate limiting, privacy endpoints.
  - `test_ml_and_nlp_guardrails.py` (23) — ML can elevate, never downgrade.
  - `test_adversarial_evasion.py` (20) — obfuscation/evasion regression.
  - `test_roman_urdu_engine.py` (15) + `test_roman_urdu_splitter.py` (14) — router/normalizer/fuzz/flag/latency + trap sentences.
  - `test_homicide_and_safety_classifier.py` (11), `test_llm_circuit_breaker.py` (8).
- **Fixtures:** `crisis_regression_cases.json` (43, must be 100%), `crisis_regression_cases_v2.json` (162 tuning + 50 held-out — measures tuning-vs-holdout gap), `adversarial_safety_cases.json` (14).
- **`conftest.py` + `pytest.ini`** — force mongomock/testing env and scope discovery to `tests/backend`.

---

## 9. Data & artifacts (roles)

- **`dataset/processed/crisis/`** — train (112,222) / validation (14,028) / test (14,028), ~50/50 balanced — output of `download_232k_dataset.py`; trains both the TF-IDF detector and distilRoBERTa.
- **`artifacts/`** — the models (`crisis_detector.joblib`, `intent_classifier.joblib`, `sentiment_classifier.joblib`, `huggingface_crisis_roberta/`) and **every evaluation report** (aggressive gate, edge cases, stress test, RoBERTa eval, Roman Urdu DEV/TEST metrics, final report, split report, kappa report, `test_runs.json` contamination ledger, `report_numbers.json`).
- **`tests/data/`** — all benchmark corpora (English 300-case sets, Roman Urdu DEV/TEST/adversarial, edge-case suites) and the frozen holdout.
- **`ml/data/roman_urdu_augmented.csv`** — 21,748 ML training samples, disjoint from every benchmark (verified).

---

## 10. Security & privacy model (cross-cutting)

- **Auth:** bcrypt (rounds 12) + JWT HS256 (24 h); weak/missing production secret halts startup.
- **Per-user isolation:** every user-scoped query filters by `user_id` from the JWT, never from the request body.
- **Privacy rights implemented in code:** consent gating (client blocks submit without it), retention with a real cleanup job, full JSON export, account + data erasure, audit events that store metadata only.
- **What leaves the system:** crisis-flagged text **never** goes to Gemini (Step 0.5/Tier 1 bypass first); non-crisis text goes to Gemini with sanitized (XML-escaped) content.
- **Logging:** credentials redacted at the filter level; no raw crisis text in audit logs.

---

## 11. Known quirks & honest notes

1. `LOW_CONFIDENCE_CHECKIN_TEMPLATE` is defined twice in `crisis_rules.py` (the second, gentler definition wins) — harmless but should be deduplicated.
2. `app.py` has a duplicated retention-settings block (~L614–621, dead first assignment).
3. `app.py` defines its own `SAFETY_DISCLAIMER` that differs slightly in wording from `crisis_resources.SAFETY_DISCLAIMER`.
4. Client declares unused dependencies: `recharts`, `canvas-confetti`, `axe-core`, `@testing-library/jest-dom`.
5. `.env.example` is referenced by the README but doesn't exist (the real `.env` is gitignored — recreate the example file before sharing).
6. `DocScreenshots.jsx` mock resource shape differs slightly from the runtime `CrisisResources` type.
7. `semantic_safety_classifier.py` has no circuit breaker (it uses a per-request model loop + regex fallback) — acceptable because its fallback is always available.
8. `SettingsPanel.save()` has one silent-failure path (`profileResult` parse) while the other two calls throw — worth aligning.

---

*Generated 2026-10-06 from a full repository inventory (all 23 server files, all client sources, all ML/scripts/tests). Numbers trace to `artifacts/report_numbers.json`; Roman Urdu claims carry the caveats in `docs/ROMAN_URDU_LIMITATIONS.md`.*
