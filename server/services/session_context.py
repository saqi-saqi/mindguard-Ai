"""
session_context.py
==================
Anonymous, server-side, in-memory cross-turn safety context.

Strict design constraints:
- No database persistence (ephemeral, in-memory only)
- No raw-text logging (stores only classification metadata, not user text)
- Strict TTL of 15 minutes; auto-evicted on expiry
- Thread-safe via a per-session lock pattern
- Supports combined-risk detection (turn-N + turn-N+1)
"""

from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field
from typing import Dict, List, Optional

__all__ = [
    "SessionContext",
    "SessionSafetyEntry",
    "get_session_context",
    "record_safety_event",
    "get_recent_safety_events",
    "clear_session_context",
]

SESSION_TTL_SECONDS = 900  # 15 minutes
MAX_EVENTS_PER_SESSION = 10


@dataclass
class SessionSafetyEntry:
    """A single turn's safety classification result (NO raw user text)."""
    timestamp: float
    risk_level: str          # e.g. "HIGH_CRISIS", "HARM_TO_OTHERS_RISK", "NONE"
    category: str            # SafetyRiskCategory value
    confidence: float
    has_harm_to_others: bool = False
    has_self_harm: bool = False
    has_weapon_mention: bool = False
    source: str = "unknown"  # "deterministic", "ml", "semantic"


@dataclass
class SessionContext:
    """Per-session safety state."""
    session_id: str
    created_at: float = field(default_factory=time.monotonic)
    last_updated: float = field(default_factory=time.monotonic)
    events: List[SessionSafetyEntry] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def is_expired(self) -> bool:
        return (time.monotonic() - self.last_updated) > SESSION_TTL_SECONDS

    def add_event(self, entry: SessionSafetyEntry) -> None:
        with self._lock:
            self.events.append(entry)
            if len(self.events) > MAX_EVENTS_PER_SESSION:
                self.events = self.events[-MAX_EVENTS_PER_SESSION:]
            self.last_updated = time.monotonic()

    def recent_events(self, max_age_seconds: float = 600.0) -> List[SessionSafetyEntry]:
        """Return events within max_age_seconds, newest first."""
        cutoff = time.monotonic() - max_age_seconds
        with self._lock:
            return [
                e for e in reversed(self.events)
                if e.timestamp >= cutoff
            ]

    def had_harm_to_others_recently(self, window_seconds: float = 120.0) -> bool:
        """True if a recent turn contained harm-to-others signal."""
        return any(
            e.has_harm_to_others
            for e in self.recent_events(window_seconds)
        )

    def had_self_harm_recently(self, window_seconds: float = 120.0) -> bool:
        """True if a recent turn contained self-harm signal."""
        return any(
            e.has_self_harm
            for e in self.recent_events(window_seconds)
        )


# ---------------------------------------------------------------------------
# In-memory session store
# ---------------------------------------------------------------------------

_STORE: Dict[str, SessionContext] = {}
_STORE_LOCK = threading.Lock()


def _evict_expired() -> None:
    """Remove expired sessions. Called opportunistically."""
    with _STORE_LOCK:
        expired = [sid for sid, ctx in _STORE.items() if ctx.is_expired()]
        for sid in expired:
            del _STORE[sid]


def get_session_context(session_id: str) -> SessionContext:
    """Get or create an in-memory session context."""
    _evict_expired()
    with _STORE_LOCK:
        if session_id not in _STORE:
            _STORE[session_id] = SessionContext(session_id=session_id)
        return _STORE[session_id]


def record_safety_event(
    session_id: str,
    risk_level: str,
    category: str,
    confidence: float,
    has_harm_to_others: bool = False,
    has_self_harm: bool = False,
    has_weapon_mention: bool = False,
    source: str = "unknown",
) -> None:
    """
    Record a safety classification event for a session.
    Does NOT store raw user text — only classification metadata.
    """
    ctx = get_session_context(session_id)
    entry = SessionSafetyEntry(
        timestamp=time.monotonic(),
        risk_level=risk_level,
        category=category,
        confidence=confidence,
        has_harm_to_others=has_harm_to_others,
        has_self_harm=has_self_harm,
        has_weapon_mention=has_weapon_mention,
        source=source,
    )
    ctx.add_event(entry)


def get_recent_safety_events(
    session_id: str,
    max_age_seconds: float = 600.0,
) -> List[SessionSafetyEntry]:
    """Retrieve recent safety events for cross-turn risk detection."""
    ctx = get_session_context(session_id)
    return ctx.recent_events(max_age_seconds)


def clear_session_context(session_id: str) -> None:
    """Remove session context (e.g. after crisis clearance)."""
    with _STORE_LOCK:
        _STORE.pop(session_id, None)
