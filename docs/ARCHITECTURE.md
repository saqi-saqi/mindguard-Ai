# MindGuard Runtime Architecture Notes

Companion to the README architecture diagram. This file records the **runtime
constraints** that are easy to violate accidentally.

## Single-worker requirement

The backend currently keeps operational state in the API process:

| Store | Location | Purpose | Breaks with >1 worker because… |
|---|---|---|---|
| Rate limiter | `_RATE_LIMIT_STORAGE` in `app.py` | 60 req/min sliding window per IP | counters are per-process; limits multiply |
| Session safety context | `services/session_context.py` | 15-minute cross-turn crisis memory | turn N+1 may land on a worker that never saw turn N |
| Cooling windows | `_USER_COOLING_WINDOWS` in `database.py` | sticky elevated monitoring after crisis | ditto |
| Safety-log circuit breaker | module globals in `database.py` | stop hammering a failing DB | per-worker, harmless but weaker |

**Deployment rule:** run exactly one worker (`gunicorn --workers 1 --threads 8`, as the
Dockerfile does) until these stores move to Redis. Scaling horizontally before that
silently degrades cross-turn crisis detection — the worst possible failure mode for this
product.

## Session authentication

Access tokens are JWTs carrying a `ver` claim bound to the user's `token_version`.
Logout — or detected reuse of an already-rotated refresh token — bumps the version,
which instantly invalidates every outstanding access token for that account. Refresh
tokens rotate within a family and are stored only as SHA-256 hashes; the raw token
lives exclusively in an HttpOnly cookie scoped to `/api/auth`. The client keeps the
access token in sessionStorage — never localStorage — so a shared device holds
nothing after the browser closes.

## Static file serving

The API serves the built SPA from `client/dist` only. The repository's `client/` source
directory is never served; in development the Vite dev server owns the frontend and the
API root falls back to a JSON banner.

## Session ownership

A client-supplied `session_id` is untrusted. Every session write path
(`set_session_risk_state`, `update_chat_session`, `clear_session_crisis_state`) verifies
ownership via `assert_session_ownership` and raises `PermissionError` on mismatch; the
chat endpoint silently drops foreign ids (and audits the rejection) rather than
confirming that another user's session exists.
