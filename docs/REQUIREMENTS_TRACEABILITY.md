# MindGuard Requirements Traceability Matrix (RTM) & Operations Manual

This document maps high-level SRS requirements and safety mandates to actual implementation files, automated test suites, CI release gates, and exact execution commands.

---

## 1. Functional Requirements Traceability

| ID | Requirement Description | Implementation Files | Automated Test Suite | Status |
| :--- | :--- | :--- | :--- | :--- |
| **FR1** | User Registration & Auth (bcrypt, JWT) | [auth.py](file:///E:/FYP/current/server/auth.py), [app.py](file:///E:/FYP/current/server/app.py#L240-L340) | [test_auth_input_validation.py](file:///E:/FYP/current/tests/backend/test_auth_input_validation.py), [test_complete_backend.py](file:///E:/FYP/current/tests/backend/test_complete_backend.py) | **VERIFIED** |
| **FR2** | Multi-Tier Crisis Detection & LLM Bypass | [crisis_rules.py](file:///E:/FYP/current/server/services/crisis_rules.py), [intent_rules.py](file:///E:/FYP/current/server/services/intent_rules.py), [app.py](file:///E:/FYP/current/server/app.py#L614-L650) | [test_crisis_rules.py](file:///E:/FYP/current/tests/backend/test_crisis_rules.py), [test_crisis_rules_aggressive.py](file:///E:/FYP/current/tests/backend/test_crisis_rules_aggressive.py) | **VERIFIED** |
| **FR3** | Crisis Emergency Helpline & Modal UI | [CrisisModal.tsx](file:///E:/FYP/current/client/src/components/CrisisModal.tsx), [crisis_resources.py](file:///E:/FYP/current/server/services/crisis_resources.py) | [CrisisModal.test.tsx](file:///E:/FYP/current/client/src/__tests__/CrisisModal.test.tsx) | **VERIFIED** |
| **FR4** | Persistent Mood Logs & Aggregation | [database.py](file:///E:/FYP/current/server/database.py#L140-L240), [AnalyticsDashboard.tsx](file:///E:/FYP/current/client/src/components/AnalyticsDashboard.tsx) | [test_complete_backend.py](file:///E:/FYP/current/tests/backend/test_complete_backend.py#L120-L170) | **VERIFIED** |
| **FR5** | Data Wipe & Permanent Account Deletion | [app.py](file:///E:/FYP/current/server/app.py#L770-L850), [App.jsx](file:///E:/FYP/current/client/src/App.jsx#L120-L158) | [test_complete_backend.py](file:///E:/FYP/current/tests/backend/test_complete_backend.py#L170-L190) | **VERIFIED** |
| **FR6** | User-controlled urgent-help access and non-punitive safety check-in | [ChatInterface.tsx](file:///E:/FYP/current/client/src/components/ChatInterface.tsx), [CrisisModal.tsx](file:///E:/FYP/current/client/src/components/CrisisModal.tsx), [app.py](file:///E:/FYP/current/server/app.py) | [test_complete_backend.py](file:///E:/FYP/current/tests/backend/test_complete_backend.py), [CrisisModal.test.tsx](file:///E:/FYP/current/client/src/__tests__/CrisisModal.test.tsx) | **IMPLEMENTED — verification pending** |

---

## 2. Non-Functional Requirements & Security Safeguards

| ID | Requirement Description | Target Threshold / Constraint | Verification Tool / Script | Status |
| :--- | :--- | :--- | :--- | :--- |
| **NFR1** | Locked Holdout Crisis Sensitivity | Recall ≥ 95.0% (FNR ≤ 5.0%) | [release_gate_crisis.py](file:///E:/FYP/current/extras/scripts/release_gate_crisis.py) | **PASS (98.11%)** |
| **NFR2** | Locked Holdout Crisis Precision | Precision ≥ 90.0% (FPR ≤ 5.0%) | [release_gate_crisis.py](file:///E:/FYP/current/extras/scripts/release_gate_crisis.py) | **PASS (98.11%)** |
| **NFR3** | Rate Limiting & 429 Protection | Max 60 req/min per IP | [test_complete_backend.py](file:///E:/FYP/current/tests/backend/test_complete_backend.py#L200-L215) | **PASS** |
| **NFR4** | Request Payload Boundary | HTTP 413 for requests > 1 MB | [test_complete_backend.py](file:///E:/FYP/current/tests/backend/test_complete_backend.py#L195-L205) | **PASS** |
| **NFR5** | JWT Secret Key Enforcer | Production startup fail if weak/default | [auth.py](file:///E:/FYP/current/server/auth.py#L32-L50), `test_prod_config` | **PASS** |
| **NFR6** | Clean Cold-Install Verification | Fresh virtualenv import and health check | [verify_clean_install.py](file:///E:/FYP/current/extras/scripts/verify_clean_install.py) | **IMPLEMENTED — fresh-environment execution required** |
| **NFR7** | Frontend Accessibility & Focus | Automated keyboard checks; manual WCAG 2.1 AA audit | [CrisisModal.tsx](file:///E:/FYP/current/client/src/components/CrisisModal.tsx), [Navigation.tsx](file:///E:/FYP/current/client/src/components/Navigation.tsx) | **PARTIALLY VERIFIED — automated modal checks pass; manual audit required** |
| **NFR8** | Safety incident handling | Urgent help is independent of classifier output; predictions never automatically contact third parties | [SAFETY_INCIDENT_RESPONSE.md](file:///E:/FYP/current/extras/docs/SAFETY_INCIDENT_RESPONSE.md) | Manual safety review required | **IMPLEMENTED — verification pending** |

---

## 3. Operations & Execution Manual (PowerShell Commands)

Execute all commands from project root directory (`E:\FYP\current`).

### A. Environment Setup & Dependency Installation
```powershell
# Set Python path for current session
$env:PYTHONPATH = "$PWD/server;$PWD/tests/backend;$PWD"
$env:USE_MONGOMOCK = "true"
$env:FLASK_ENV = "testing"

# Install backend dependencies
pip install -r server/requirements.txt

# Install frontend dependencies
cd client
npm install
cd ..
```

### B. Master Test Suite & Health Verification
```powershell
# Run Master Test Suite (Runs all backend tests, CI release gate, TypeScript check & Vite build)
python tests/run_all_tests.py
```

### C. Tier-1 Crisis Detection Benchmark & CI Release Gate
```powershell
# Evaluate 530-case development regression benchmark
python extras/scripts/eval_crisis.py

# Evaluate Locked Independent Holdout Evaluation Dataset & Enforce Release Gate
python extras/scripts/release_gate_crisis.py
```

### D. Clean Cold-Install Verification Script
```powershell
# Creates an isolated temporary virtual environment, installs server/requirements.txt, imports app & calls /api/health
python extras/scripts/verify_clean_install.py
```

### E. Frontend Type-Checking, Testing & Production Build
```powershell
# Run TypeScript type-checking
cd client
npx tsc --noEmit

# Run Vitest unit & accessibility tests
npm test

# Build production bundle
npm run build
cd ..
```

### F. Production Configuration Launch Example
```powershell
# Set strong production secrets before launching in production mode
$env:FLASK_ENV = "production"
$env:JWT_SECRET_KEY = "super-secure-production-jwt-secret-key-32chars-minimum-length-2026!"
$env:MONGO_URI = "mongodb://localhost:27017/mindguard_db"

python server/app.py
```
