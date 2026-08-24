# MindGuard AI — Intelligent Mental Health Support Companion

> **NON-CLINICAL DISCLAIMER**: MindGuard is an automated AI self-help support tool designed for early intervention, self-monitoring, and crisis resource guidance. MindGuard is **not** a licensed medical provider, hospital, or clinical emergency service. It does **not** provide clinical diagnosis, therapy, or guaranteed crisis prevention. If you or someone you know is in immediate physical danger, please call your local emergency services (1122 in Pakistan, 911 in US/Canada, 999 in UK) or go to the nearest emergency room.

---

## 1. System Architecture

MindGuard utilizes a **3-tier hybrid safety and conversational pipeline**:

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
|   & Regional Helpline Resources UI    |     +---------------------------------------+
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

### Safety Hierarchy
1. **Tier 1 (Deterministic Rules)**: Evaluates regex patterns, keyphrases, and contextual negations. Tier 1 has **final authority** on crisis detection.
2. **Tier 2 (ML Classification)**: Zero-shot transformer classifier for intent, emotion, and sentiment. Can elevate risk if Tier 1 did not fire, but **cannot override or reduce a Tier 1 crisis flag**.
3. **Tier 3 (Generative LLM)**: Powered by Google Gemini API with fallback to structured offline knowledge base (`response_kb.py`). If Tier 1 or Tier 2 flags high crisis risk, **Tier 3 is completely bypassed**.

---

## 2. Project Directory Structure

```text
├── .github/                # GitHub Actions CI workflows (test.yml)
├── artifacts/              # Exported model files (.joblib) and metric JSON reports
├── client/                 # React.js (Vite) frontend application
│   ├── src/
│   │   ├── components/     # UI components (ChatInterface, CrisisModal, AnalyticsDashboard, SettingsPanel, AuthScreen)
│   │   ├── __tests__/      # Vitest unit & accessibility tests
│   │   └── App.jsx         # Root app layout and tab state
│   └── Dockerfile          # NGINX container build for client
├── docs/                   # Documentation (PRIVACY_AND_SECURITY.md, CRISIS_RESOURCES_MAINTENANCE.md, figures/)
├── ml/                     # Machine learning training scripts (train_crisis.py, train_sentiment.py, train_intent.py)
├── scripts/                # Verification & CI Release Gate scripts (release_gate_crisis.py, verify_clean_install.py)
├── server/                 # Flask backend REST API
│   ├── app.py              # Flask REST endpoints, validation, CORS, rate-limiting
│   ├── auth.py             # Bcrypt hashing & JWT authentication middleware
│   ├── config.py           # Environment configuration loader
│   ├── database.py         # MongoDB data access layer & compound indexes
│   ├── services/           # Crisis detection, ML pipelines, and LLM safety services
│   └── Dockerfile          # Backend Python API container
├── tests/                  # Automated test suite, benchmark datasets & regression fixtures
│   ├── backend/            # Backend unit, integration & safety test suites
│   ├── fixtures/           # Regression fixtures (crisis_regression_cases.json)
│   ├── data/               # Benchmark test cases
│   └── run_all_tests.py    # Master test & security audit pipeline
├── docker-compose.yml      # Multi-container orchestration (MongoDB + Flask + React)
└── README.md
```

---

## 3. Environment Setup & Installation

### Backend Setup (Python 3.10+ & MongoDB)
```bash
# Navigate to project root
cd e:/FYP/current

# Copy environment template
cp .env.example .env

# Install Python dependencies (includes PyMongo & mongomock)
pip install -r server/requirements.txt

# (Optional) Migrate legacy SQLite data to MongoDB
python server/migrate_sqlite_to_mongodb.py --dry-run
python server/migrate_sqlite_to_mongodb.py

# Start Flask Backend Server (http://127.0.0.1:5000)
python server/app.py
```

### Frontend Setup (Node.js 18+)
```bash
# Navigate to client directory
cd client

# Install packages
npm install

# Start Vite dev server (http://localhost:5173)
npm run dev
```

---

## 4. Running Automated Tests & Benchmarks

```bash
# Run complete automated master test runner (Backend, CI Gate, Frontend, A11y, Security Audits)
python tests/run_all_tests.py

# Run standalone backend test suite with pytest
python -m pytest tests/backend -v

# Run 120 custom edge-case benchmark suite
python scripts/benchmarks/benchmark_custom_edge_cases.py tests/data/my_edge_cases.json

# Run 1,000-sample stress test against processed crisis dataset
python scripts/benchmarks/benchmark_stress_1000.py

# Run controlled matrix sets evaluation (Sets A-J)
python scripts/benchmarks/benchmark_matrix_sets.py
```

---

## 5. Model Training Commands

```bash
# Train Crisis Risk Detector
python ml/train_crisis.py

# Train Sentiment Classifier
python ml/train_sentiment.py

# Train Intent Classifier
python ml/train_intent.py
```

---

## 6. Privacy & Security Checklist

* **Secrets**: API keys loaded via environment variables (`.env`). Secrets excluded from `.gitignore`.
* **Logging**: Flask logger redacts user text, API keys, and sensitive prompts from logs.
* **CORS**: Restricted to configured origins (`http://localhost:5173`).
* **Rate Limiting**: IP-based rate limiting (60 requests/minute) configured in `app.py`.
* **Data Transmission**: Gemini API calls occur over encrypted HTTPS; crisis inputs bypass external APIs completely.

---

## 7. Docker Deployment

```bash
# Build and run backend and frontend containers
docker-compose up --build -d
```
* **Frontend**: `http://localhost:5173`
* **Backend API**: `http://localhost:5000`

---

## 8. Development Readiness Statement
MindGuard is currently functional as an **academic development prototype** and **integration-testing candidate**. Full clinical validation, formal regulatory approval, and database deployment are pending prior to production healthcare release.
