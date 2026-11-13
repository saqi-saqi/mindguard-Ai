# MindGuard Data Lifecycle & Retention Policy

**Status:** Implemented (see `server/database.py`, `server/config.py`).
**Principle:** Every record that can be linked to a person has a bounded lifetime, and
exercising the right to erasure leaves nothing behind that points back to that person.

---

## Collections

| Collection | Content | Retention | Erasure behaviour |
|---|---|---|---|
| `chat_messages` | Chat turns | TTL on `expires_at` (user setting, default 30 days, can be disabled by the user) | Deleted |
| `mood_logs` | Mood check-ins | TTL on `expires_at` (same setting as chat) | Deleted |
| `chat_sessions` | Session metadata (title, risk state) | Lifetime of the account | Deleted |
| `audit_logs` | Security/safety metadata only — **no raw chat text** | TTL `AUDIT_LOG_RETENTION_DAYS` (default 90 days) | Deleted |
| `safety_logs` | Crisis detection events: tier, category, action, confidence, redacted message excerpt + hash | TTL `SAFETY_LOG_RETENTION_DAYS` (default 365 days) | **Anonymized** (see below) |
| `users`, `user_profiles` | Account + counselling profile | Lifetime of the account | Deleted / reset |
| `refresh_tokens` | Rotating refresh-token **hashes** for opt-in "Keep me signed in" sessions | TTL `REFRESH_TOKEN_TTL_DAYS` (default 7 days) | Deleted |

## Safety logs: why anonymized, not deleted

Crisis events carry a clinical-audit value that outlives the account: they are the only
record that the safety pipeline fired, and they are used to measure recall and review
triage decisions. On erasure (`delete_user_data` / `delete_user_account`):

- `user_id` → `None`, `session_id` → `None`, `is_guest` → `True`
- `message_excerpt` is removed entirely; the content hash is kept only for de-duplication
- `redacted: true` and `anonymized_at` are stamped on the document
- Aggregate fields (tier, category, action taken, confidence) are retained until the
  collection TTL expires the document automatically

No field that remains can be linked back to the person who erased their data.

## Redaction at write time

`log_safety_event` never stores a raw crisis message. It stores
`redact_trigger_message(message)`: a truncated excerpt plus a short SHA-256 prefix
(`message_hash`) used to correlate repeated triggers without exposing content.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `SAFETY_LOG_RETENTION_DAYS` | `365` | TTL for crisis event records |
| `AUDIT_LOG_RETENTION_DAYS` | `90` | TTL for audit metadata |
| `DEFAULT_RETENTION_DAYS` | `30` | Per-user chat/mood retention default |

TTL indexes are created in `init_db()` (`idx_safety_expires_at`, `idx_audit_expires_at`).
MongoDB enforces TTL deletion in a background pass (roughly once per minute); records may
persist up to that interval past their expiry timestamp.

## Cookies

| Cookie | Purpose | Lifetime |
|---|---|---|
| `mg_refresh` (HttpOnly, `Path=/api/auth`) | Rotating refresh token for opt-in "Keep me signed in" | 7 days; revoked on logout or theft detection |
| `mg_guest` (HttpOnly, `Path=/`) | Random continuity reference so an anonymous visitor's crisis-state monitoring survives a page reload | 24 hours |

Neither cookie stores identity data: `mg_refresh` holds an opaque rotating token whose
SHA-256 hash lives server-side (raw token never persisted), and `mg_guest` is a random
string with no PII that only links an anonymous visitor to their own session risk state.

## What this does not claim

- Backups taken before an erasure request are out of scope until they roll off.
- MongoDB TTL deletion is eventually consistent; the counts returned by
  `delete_user_data` reflect the synchronous deletions only.
