# MindGuard AI Privacy and Security Policy

**Effective Date:** August 2026  
**Status:** Academic Research / Development Prototype

---

## 1. Overview and Non-Clinical Disclaimer
MindGuard is an automated AI conversational platform designed for self-help guidance and risk identification. MindGuard is **not** a licensed medical provider, hospital, or emergency response center. 

---

## 2. Conversation Data Storage and Memory
* **Conversation storage choice**: Users choose whether authenticated chats and self-reported mood entries are retained. When retention is disabled, new authenticated chat messages are not persisted.
* **Persistent Database**: The prototype uses MongoDB for authenticated user profiles, retained chat messages, sessions, mood entries, and metadata-only safety audit events.
* **Retention and deletion**: Users can configure a retention period, export their data as JSON, delete stored data, or permanently delete their account from Privacy & Settings.

---

## 3. Gemini API Transmission
* **Data Flow**: Non-crisis user text, intent labels, and emotion tags are transmitted over encrypted HTTPS to Google Gemini API endpoints (`generativelanguage.googleapis.com`) to synthesize supportive responses.
* **Crisis Bypass**: If a message triggers Tier 1 or Tier 2 crisis detection rules, **no data is sent to the Gemini API**.

---

## 4. Logging & Privacy Controls
* **Log Redaction**: Server logging (`server/app.py`) is configured with a privacy filter that redacts raw user messages, prompt payloads, API keys, and personal identifiers.
* **Recorded Log Fields**: Logs store only operational metadata (`request_id`, `timestamp`, `endpoint`, `status_code`, `processing_duration_ms`, `risk_level`).

---

## 5. Security Measures & Limitations
* **Environment Variables**: API keys and configuration secrets are loaded exclusively via environment variables (`.env`) and are excluded from version control (`.gitignore`).
* **CORS Restrictions**: Cross-Origin Resource Sharing is restricted to authorized frontend origins configured through `CORS_ORIGINS`.
* **Rate Limiting**: IP-based rate limiting (60 requests/minute per client) protects endpoints against abuse.
* **HTTPS**: The local Docker configuration is not a TLS termination point. Deployments must place the application behind a TLS-enabled reverse proxy and use HTTPS before handling real user data.

---

## 6. Limitations and Pending Controls
- [ ] Database encryption at rest must be configured by the production database operator.
- [ ] Formal Terms of Service and legal/privacy review are required before production use.
- [ ] An automated regulatory compliance audit has not been completed.
