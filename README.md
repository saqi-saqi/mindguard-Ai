# MindGuard AI — Intelligent Mental Health Support Companion

> **NON-CLINICAL DISCLAIMER**: MindGuard is an automated AI self-help support tool designed for early intervention, self-monitoring, and crisis resource guidance. MindGuard is **not** a licensed medical provider, hospital, or clinical emergency service. It does **not** provide clinical diagnosis, therapy, or guaranteed crisis prevention. If you or someone you know is in immediate physical danger, please call your local emergency services (1122 or 15 in Pakistan) or go to the nearest emergency room.

---

## 1. System Architecture

MindGuard utilizes a **3-tier hybrid safety and conversational pipeline** engineered to deliver rapid, deterministic triage for acute crisis inputs while maintaining empathetic conversational engagement for non-crisis mental health support:

```
                         +-----------------------------------+
                         |         Incoming User Text        |
                         +-----------------------------------+
                                           |
                                           v
                         +-----------------------------------+
                         |   Tier 1: Deterministic Engine    |
                         |        (crisis_rules.py)          |
                         +-----------------------------------+
                                           |
                    +----------------------+----------------------+
                    |                                             |
            [Crisis Detected]                             [No Crisis Detected]
                    |                                             |
                    v                                             v
+---------------------------------------+     +---------------------------------------+
|        BYPASS ALL DOWNSTREAM          |     | Tier 2: Machine Learning Classifier   |
|         GENERATIVE MODULES            |     |        (huggingface_service.py)       |
+---------------------------------------+     +---------------------------------------+
                    |                                             |
                    v                                             v
+---------------------------------------+     +---------------------------------------+
|  Return Hardcoded Emergency Response  |     |  Classify Intent & Sentiment State    |
|   & Targeted Helpline Resources UI    |     +---------------------------------------+
+---------------------------------------+                                 |
                                                                          v
                                              +---------------------------------------+
                                              | Tier 3: Generative LLM & KB Fallback  |
                                              |  (llm_service.py / response_kb.py)    |
                                              +---------------------------------------+
                                                                          |
                                                                          v
                                              +---------------------------------------+
                                              | Return Dynamic Supportive Response    |
                                              +---------------------------------------+
```

### Safety Hierarchy & Architectural Invariants
1. **Tier 1 (Deterministic Rules — Final Authority)**:
   - Evaluates regex patterns, semantic concepts, actor/target dependencies, contrastive conjunctions, and temporal transitions.
   - **Absolute Authority Invariant**: A Tier 1 acute-crisis determination can **never** be suppressed, downgraded, or recategorized by context-bypass filters (academic/fictional frames, jokes), actor/target parsing, Tier 2 (ML), or Tier 3 (LLM/KB).
   - **Target-Specific Triage**:
     - **Interpersonal Harm / Threats to Others (`HARM_TO_OTHERS_RISK`)**: Routes strictly to law enforcement and rescue services (**Police 15**, **Rescue 1122**). Self-harm/suicide helplines are completely omitted to prevent inappropriate crisis routing.
     - **Self-Harm / Suicidal Ideation (`CRISIS_SUICIDE_ATTEMPT`, `CRISIS_EXPLICIT_SUICIDE_INTENT`)**: Routes immediately to mental health crisis hotlines (**Umang 0311-7786264**, **Talk2Me 0333-1441444**, **Rescue 1122**).
   - **Ultra-Low Latency Fast-Path**: Crisis inputs short-circuit within **5–25ms**, immediately returning static guidance and locking the composer without making external LLM calls.

2. **Tier 2 (Machine Learning Classification — Safety Floor)**:
   - Scikit-learn models (`crisis_detector.joblib`, `intent_classifier.joblib`, `sentiment_classifier.joblib`) backed by HuggingFace transformer pipelines (`huggingface_crisis_roberta`, `j-hartmann/emotion-english-distilroberta-base`, `cardiffnlp/twitter-roberta-base-sentiment-latest`).
   - Functions as an additive safety net: can elevate risk if Tier 1 did not fire, but **can never lower or dismiss a Tier 1 crisis flag**.

3. **Tier 3 (Generative LLM & Knowledge Base Fallback)**:
   - Powered by Google Gemini API / Groq API with robust fallback to structured offline knowledge base (`response_kb.py`).
   - **Hard Fail-Safe**: If Tier 1 or Tier 2 flags high crisis risk, **Tier 3 is completely bypassed** to prevent hallucination, delay, or inappropriate conversational response.

---

## 2. Safety Benchmarks & Empirical Verification

MindGuard is continuously verified against adversarial test suites, held-out benchmarks, and cross-browser end-to-end testing:

| Metric / Benchmark Suite | Dataset / Scope | Empirical Result | Target Invariant |
| :--- | :--- | :---: | :---: |
| **Clean English 296 Benchmark** | Held-out 296 non-leaked crisis/benign cases | **93.28% Recall** (111/119 TP, 8 FN)<br>92.50% Precision, 92.89% F1 | $\ge 93.0\%$ recall |
| **Context Bypass Abuse Suite** | 1,800 adversarial permutations (30 triggers $\times$ 20 statements $\times$ 3 positions) | **1,800 / 1,800 Passed (100.0%)** | 0 suppressions |
| **Tier 1 Authority Invariant** | `test_08_pipeline_never_below_tier1.py` | **100% Passed (0 failed, 0 xfailed)** | Absolute Tier-1 precedence |
| **Backend & Deep Test Suite** | Master unit, integration, ML, and deep safety tests | **3,030 Passed (0 failed, 0 xfailed)** | 100% pass rate |
| **Sealed Roman Urdu Benchmark** | `roman_urdu_crisis_benchmark_sealed_100.json` (unseen held-out) | **20.00% Recall** (10/50 TP, 100% Prec)<br>*Dev-100: 100% recall* | Cryptographically sealed (SHA-256) |
| **E2E Browser Matrix** | Playwright WebKit, Chromium, Firefox, Mobile Chrome | **112 / 112 Passed** (28/28 per engine) | Cross-browser parity |

> [!NOTE]
> **Roman Urdu Benchmark Reporting Policy**: To ensure scientific integrity and prevent data contamination, Roman Urdu evaluation is strictly divided between `dev_100` (tuning set) and `sealed_100` (unseen evaluation set). The **20.00% recall** on `sealed_100` represents the true offline baseline on novel unseen dialectical inputs. Tier 1 deterministic rules carry 100% of the Roman Urdu workload in production; offline TF-IDF and English RoBERTa models do not process Roman Urdu morphology.

---

## 3. Project Directory Structure

```text
├── .github/                # GitHub Actions CI workflows (test.yml)
├── artifacts/              # Exported model files (.joblib) and metric JSON reports
├── client/                 # React.js (Vite) frontend application
│   ├── src/
│   │   ├── components/     # ChatInterface, CrisisModal, AnalyticsDashboard, SettingsPanel, AuthScreen
│   │   ├── __tests__/      # Vitest unit & accessibility tests (vitest-axe)
│   │   └── App.jsx         # Root app layout and tab state
│   └── Dockerfile          # NGINX container build for client
├── docs/                   # Documentation (PRIVACY_AND_SECURITY.md, CRISIS_RESOURCES_MAINTENANCE.md)
├── ml/                     # Machine learning training scripts and datasets
├── scripts/                # Verification & CI Release Gate scripts
│   ├── release_gate_crisis.py          # Pre-merge CI release gate for crisis precision/recall
│   └── benchmarks/                     # Benchmark execution scripts (stress, matrix, edge cases)
├── server/                 # Flask backend REST API
│   ├── app.py              # Flask endpoints, validation, CORS, rate-limiting, error handlers
│   ├── auth.py             # Bcrypt hashing & JWT authentication middleware
│   ├── config.py           # Environment configuration loader
│   ├── database.py         # MongoDB data access layer & compound indexes
│   ├── services/           # Crisis detection, ML pipelines, and LLM safety services
│   │   ├── crisis_rules.py             # Deterministic Tier 1 rule engine & bypass arbiter
│   │   ├── safety_classifier.py       # High-level crisis categorization (self-harm vs harm-to-others)
│   │   ├── threat_actor_detector.py   # Subject/target parsing and grammatical clause analyzer
│   │   ├── precedence_arbitrator.py   # Multi-tier conflict resolution & authority arbiter
│   │   ├── huggingface_service.py     # Tier 2 ML & transformer pipeline loader
│   │   ├── llm_service.py             # Tier 3 generative service (Gemini / Groq)
│   │   └── response_kb.py             # Offline fallback knowledge base
│   └── Dockerfile          # Backend Python API container
├── tests/                  # Automated test suite, benchmark datasets & regression fixtures
│   ├── backend/            # Backend unit, integration, and security tests
│   ├── deep/               # Deep integration, Tier-1 invariants, and adversarial bypass suites
│   │   ├── test_07_bypass_abuse.py             # 1,800-permutation adversarial jailbreak suite
│   │   └── test_08_pipeline_never_below_tier1.py # Tier 1 absolute authority invariant
│   ├── data/               # English 296, Roman Urdu Dev-100, and Sealed-100 benchmarks
│   ├── fixtures/           # Regression fixtures (crisis_regression_cases.json)
│   └── run_all_tests.py    # Master test & security audit pipeline
├── e2e/                    # Playwright end-to-end multi-browser test suite
├── docker-compose.yml      # Multi-container orchestration (MongoDB + Flask + React)
├── BUGS.md                 # Authoritative defect remediation & root cause log
├── TEST_REPORT.md          # Comprehensive QA and verification audit report
└── README.md
```

---

## 4. Environment Setup & Installation

### Prerequisites
- Python 3.10+ (Python 3.11 or 3.12 recommended)
- Node.js 18+ & npm
- Local MongoDB instance (or MongoDB Atlas connection URI)

### Backend Setup
```bash
# Navigate to project root
cd e:/FYP/current

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Copy environment template
cp .env.example .env

# Install server runtime dependencies
pip install -r server/requirements.txt

# Install test dependencies (pytest, pytest-cov, transformers, torch)
pip install -r requirements-test.txt

# (Optional) Verify SQLite to MongoDB data migration
python server/migrate_sqlite_to_mongodb.py --dry-run

# Start Flask Backend Server (http://127.0.0.1:5000)
python server/app.py
```

### Frontend Setup
```bash
# Navigate to client directory
cd client

# Install frontend dependencies
npm install

# Start Vite dev server (http://localhost:5173)
npm run dev
```

---

## 5. Running Automated Tests & Quality Gates

### Master Test Runner
Run the complete automated test suite (backend tests, release gate, frontend unit tests, and accessibility audit):
```bash
python tests/run_all_tests.py
```

### Specialized Safety & Invariant Suites
```bash
# 1. Run all backend and deep integration tests (3,030 tests)
pytest tests/backend tests/deep -v

# 2. Run the 1,800-permutation adversarial context bypass suite
pytest tests/deep/test_07_bypass_abuse.py -v

# 3. Verify the Tier 1 authority invariant across all benchmark cases
pytest tests/deep/test_08_pipeline_never_below_tier1.py -v

# 4. Verify cryptographically sealed Roman Urdu benchmark integrity (SHA-256)
pytest tests/backend/test_roman_urdu_sealed_integrity.py -v

# 5. Run the pre-merge CI crisis release gate
python scripts/release_gate_crisis.py
```

### Frontend & Accessibility Tests
```bash
cd client
npm test -- --run
```

### End-to-End (E2E) Browser Tests
```bash
# Run Playwright cross-browser tests across Chromium, Firefox, WebKit, and Mobile
npx playwright test
```

---

## 6. Model Training Commands

To retrain the offline scikit-learn classifiers on updated datasets:

```bash
# Train Crisis Risk Detector (TF-IDF + Logistic Regression)
python ml/train_crisis.py

# Train Sentiment Classifier
python ml/train_sentiment.py

# Train Intent Classifier
python ml/train_intent.py
```

---

## 7. Security, Privacy & Abuse Protections

* **Unauthenticated Access with Rate Limiting**: The `/api/chat` endpoint allows public anonymous access so users in distress never encounter a login wall.
* **IP Sliding-Window Rate Limiting**: Enforces a strict 60 requests/minute ceiling per client IP in `server/app.py`.
* **Crisis Safety Fail-Safe**: In the event of an HTTP 429 (Rate Limit Exceeded), the JSON response payload still renders emergency contact numbers (Rescue 1122 and Umang 0311-7786264).
* **Anti-Spoofing IP Verification**: `get_client_ip` only trusts `X-Forwarded-For` headers from addresses defined in `TRUSTED_PROXIES`.
* **PII & Text Redaction**: Flask logging middleware redacts user message content, authorization tokens, and API credentials.
* **Zero Resource Exhaustion on Crisis**: Tier 1 crisis detection halts downstream LLM generation in 5–25ms, preventing resource consumption from malicious bot traffic.

---

## 8. Docker Deployment

```bash
# Build and run backend and frontend containers
docker-compose up --build -d
```
* **Frontend**: `http://localhost:5173`
* **Backend API**: `http://localhost:5000`

---

## 9. Emergency Helplines & Crisis Resources

MindGuard directs individuals in distress to verified emergency contacts:

| Service / Organization | Scope | Contact Information |
| :--- | :--- | :--- |
| **Police Emergency** | Pakistan (Interpersonal violence, imminent danger) | **15** |
| **Rescue / Ambulance** | Pakistan (Medical emergencies & trauma) | **1122** |
| **Umang Mental Health** | Pakistan (24/7 Mental health & suicide prevention) | **0311-7786264** / [umang.com.pk](https://www.umang.com.pk) |
| **Talk2Me Pakistan** | Pakistan (Emotional & psychological counseling) | **0333-1441444** |
| **988 Suicide & Crisis Lifeline** | USA & Canada (Call / Text) | **988** |
| **Befrienders Worldwide** | Global Helpline Directory | [befrienders.org](https://www.befrienders.org) |

---

## 10. Development Readiness Statement

MindGuard is currently functional as an **academic development prototype** and **integration-testing candidate**. Full clinical validation, formal regulatory approval, and healthcare compliance certification are pending prior to production healthcare deployment.

