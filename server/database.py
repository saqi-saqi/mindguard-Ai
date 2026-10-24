"""
database.py
===========
MongoDB Database Module for MindGuard AI.
Manages persistent MongoDB connections, schemas, collections, indexes,
BSON document serialization, user models, chat history, mood logs, and data retention workflows.
Supports both real PyMongo client and isolated mongomock testing.
"""

import os
import re
import uuid
import time
import hmac
import hashlib
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple
from urllib.parse import urlparse

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.errors import PyMongoError, DuplicateKeyError

# Import config settings safely
from config import MONGO_URI, MONGO_DB_NAME, USE_MONGOMOCK

logger = logging.getLogger("MindGuard-Database")

# Module-level client cache
_mongo_client: Optional[Any] = None


def get_db_name() -> str:
    """Extracts or returns the database name from config or MONGO_URI."""
    if MONGO_DB_NAME and MONGO_DB_NAME.strip():
        return MONGO_DB_NAME.strip()
    try:
        parsed = urlparse(MONGO_URI)
        path = parsed.path.lstrip("/")
        if path:
            return path
    except Exception:
        pass
    return "mindguard_db"


def get_db_client(force_new: bool = False) -> Any:
    """
    Returns a connected MongoClient instance.
    Uses mongomock if USE_MONGOMOCK env flag is set, otherwise real PyMongo MongoClient
    with explicit server timeouts.
    """
    global _mongo_client
    if _mongo_client is not None and not force_new:
        return _mongo_client

    if USE_MONGOMOCK:
        try:
            import mongomock
            logger.info("Initializing isolated in-memory mongomock database client...")
            _mongo_client = mongomock.MongoClient()
            return _mongo_client
        except ImportError:
            logger.warning("mongomock requested but not installed. Falling back to PyMongo.")

    logger.info(f"Connecting to MongoDB instance at {MONGO_URI}...")
    _mongo_client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        socketTimeoutMS=10000
    )
    return _mongo_client


def get_db() -> Any:
    """Returns the MongoDB database handle for MindGuard."""
    client = get_db_client()
    db_name = get_db_name()
    return client[db_name]


def close_db():
    """Closes active MongoDB client connections on application shutdown."""
    global _mongo_client
    if _mongo_client is not None:
        try:
            _mongo_client.close()
            logger.info("MongoDB client connection closed cleanly.")
        except Exception as e:
            logger.error(f"Error closing MongoDB connection: {e}")
        finally:
            _mongo_client = None


def serialize_doc(doc: Optional[Dict[str, Any]], redact_password: bool = True) -> Optional[Dict[str, Any]]:
    """
    Helper function to clean BSON types (ObjectId, datetime) and remove internal `_id` 
    and sensitive fields (such as `password_hash`) to ensure pure JSON serializability.
    """
    if doc is None:
        return None

    cleaned = {}
    for k, v in doc.items():
        if k == "_id":
            continue
        elif k == "password_hash" and redact_password:
            continue
        elif isinstance(v, datetime):
            cleaned[k] = v.isoformat()
        else:
            cleaned[k] = v

    return cleaned


def init_db():
    """
    Initializes collections and compound indexes for optimal query performance.
    """
    db = get_db()
    
    # 1. Users Collection - Unique index on normalized lowercased email
    db.users.create_index([("email", ASCENDING)], unique=True, name="idx_unique_email")

    # 2. Chat Messages Collection - Compound index for fast timeline queries
    db.chat_messages.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_user_chat_timeline"
    )

    # 3. Mood Logs Collection - Compound index for mood analytics
    db.mood_logs.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_user_mood_timeline"
    )

    # 4. Chat Sessions Collection - Compound index
    db.chat_sessions.create_index(
        [("user_id", ASCENDING), ("created_at", DESCENDING)],
        name="idx_user_sessions_timeline"
    )
    db.audit_logs.create_index([("created_at", DESCENDING)], name="idx_audit_created_at")
    db.user_profiles.create_index([("user_id", ASCENDING)], name="idx_user_profiles_user_id", unique=True)

    # 5. TTL Indexes for Automatic Data Retention Expiry
    db.chat_messages.create_index("expires_at", expireAfterSeconds=0)
    db.mood_logs.create_index("expires_at", expireAfterSeconds=0)

    # 6. Safety Logs Collection - Compound and single-field indexes for clinical review
    db.safety_logs.create_index([("timestamp", DESCENDING)], name="idx_safety_timestamp")
    db.safety_logs.create_index([("tier", ASCENDING), ("timestamp", DESCENDING)], name="idx_safety_tier_timestamp")
    db.safety_logs.create_index([("category", ASCENDING), ("timestamp", DESCENDING)], name="idx_safety_category_timestamp")
    db.safety_logs.create_index([("resolved", ASCENDING), ("timestamp", DESCENDING)], name="idx_safety_resolved_timestamp")

    logger.info("MongoDB collections and compound indexes initialized successfully.")


# --- User Authentication Operations ---

def create_user(name: str, email: str, password_hash: str, consent_given: bool = False) -> Dict[str, Any]:
    """Creates a new user document in the users collection."""
    db = get_db()
    user_id = f"usr-{uuid.uuid4().hex[:12]}"
    normalized_email = email.strip().lower()
    created_at = datetime.utcnow().isoformat()

    doc = {
        "id": user_id,
        "name": name.strip(),
        "email": normalized_email,
        "password_hash": password_hash,
        "created_at": created_at,
        "role": "user",
        "settings": {
            "consent_given": bool(consent_given),
            "retention_enabled": True,
            "retention_days": 30,
            "locale": "pakistan"
        },
        "safety_profile": {
            "preferred_hospital_name": "",
            "preferred_hospital_phone": "",
            "city_or_district": "",
            "emergency_actions_consent": False,
        },
    }

    db.users.insert_one(doc)
    return serialize_doc(doc, redact_password=True)


def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Retrieves a user document by email (includes password_hash for authentication verification)."""
    db = get_db()
    normalized_email = email.strip().lower()
    user = db.users.find_one({"email": normalized_email})
    return serialize_doc(user, redact_password=False)


def get_user_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a user by public string ID excluding sensitive password hash."""
    db = get_db()
    user = db.users.find_one({"id": user_id})
    return serialize_doc(user, redact_password=True)


# --- User Profile (context-aware counselor) ---

def get_or_create_user_profile(user_id: str) -> Dict[str, Any]:
    """Gets or creates a lightweight chat-context profile for the user.
    Stores preferred_name, session_count, crisis_count, last_topic, and
    coping_strategies that worked — used to build a context-aware counselor."""
    db = get_db()
    profile = db.user_profiles.find_one({"user_id": user_id})
    if profile:
        return serialize_doc(profile)

    user = get_user_by_id(user_id)
    first_name = "there"
    if user and user.get("name"):
        first_name = user["name"].strip().split(" ")[0]

    profile_doc = {
        "user_id": user_id,
        "preferred_name": first_name,
        "session_count": 0,
        "crisis_count": 0,
        "harm_to_others_count": 0,
        "last_topic": None,
        "coping_tried": [],
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat(),
    }
    db.user_profiles.insert_one(profile_doc)
    return serialize_doc(profile_doc)


def update_user_profile(user_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Updates the user profile after a chat session.
    Call with {"inc_session": True} to increment session_count,
    {"inc_crisis": True} to increment crisis_count,
    {"inc_harm_others": True} to increment harm_to_others_count,
    {"last_topic": "..."} to set the last conversation theme,
    {"coping_tried": ["breathing", "walking"]} to record strategies used."""
    db = get_db()
    update_ops: Dict[str, Any] = {
        "$set": {"updated_at": datetime.utcnow().isoformat()},
        "$setOnInsert": {"created_at": datetime.utcnow().isoformat()},
    }
    set_fields = {}
    inc_fields = {}
    if updates.get("last_topic"):
        set_fields["last_topic"] = updates["last_topic"]
    if updates.get("coping_tried"):
        set_fields["coping_tried"] = updates["coping_tried"][:10]
    if updates.get("preferred_name"):
        set_fields["preferred_name"] = updates["preferred_name"]
    if updates.get("inc_session"):
        inc_fields["session_count"] = 1
    if updates.get("inc_crisis"):
        inc_fields["crisis_count"] = 1
    if updates.get("inc_harm_others"):
        inc_fields["harm_to_others_count"] = 1
    if set_fields:
        update_ops["$set"] = {**update_ops["$set"], **set_fields}
    if inc_fields:
        update_ops["$inc"] = inc_fields

    db.user_profiles.update_one({"user_id": user_id}, update_ops, upsert=True)
    profile = db.user_profiles.find_one({"user_id": user_id})
    return serialize_doc(profile)


def get_mood_summary_for_chat(user_id: str) -> str:
    """Builds a compact mood-context string for the LLM prompt.
    Returns '' if no mood data exists (never sends irrelevant context)."""
    try:
        logs = get_mood_logs(user_id, limit=7)
        if not logs:
            return ""
        scores = [log.get("score", 5) for log in logs if isinstance(log.get("score"), (int, float))]
        if not scores:
            return ""
        avg = sum(scores) / len(scores)
        all_tags = []
        for log in logs:
            for tag in (log.get("tags") or []):
                if tag and tag not in all_tags:
                    all_tags.append(tag)
        parts = [f"{len(logs)} recent mood check-ins averaging {avg:.1f} out of 10"]
        if all_tags:
            parts.append(f"topics they tagged: {', '.join(all_tags[:5])}")
        if avg < 4.0:
            parts.append("they have been struggling recently — be extra warm and gentle")
        elif avg >= 7.0:
            parts.append("they have been doing relatively well lately")
        return "; ".join(parts)
    except Exception:
        return ""


# --- Mood Logs Operations ---

def save_mood_log(user_id: str, score: int, tags: List[str], notes: str, expires_at: Optional[Any] = None) -> Dict[str, Any]:
    """Saves a mood log record for a user."""
    db = get_db()
    log_id = f"mood-{uuid.uuid4().hex[:12]}"
    created_at = datetime.utcnow().isoformat()

    doc = {
        "id": log_id,
        "user_id": user_id,
        "score": score,
        "tags": tags,
        "notes": notes,
        "expires_at": expires_at,
        "created_at": created_at
    }

    db.mood_logs.insert_one(doc)
    return serialize_doc(doc)


def get_mood_logs(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves recent mood logs for an authenticated user, ordered chronologically (ASC)."""
    db = get_db()
    # Query using compound index (user_id, created_at)
    cursor = db.mood_logs.find({"user_id": user_id}).sort("created_at", ASCENDING).limit(limit)
    return [serialize_doc(doc) for doc in cursor]


def get_analytics_summary(user_id: str, days: int) -> Dict[str, Any]:
    """Return user-scoped, non-diagnostic activity and mood data for a selected time range."""
    cutoff = (datetime.utcnow() - timedelta(days=days)).isoformat()
    db = get_db()
    mood_logs = [serialize_doc(doc) for doc in db.mood_logs.find({"user_id": user_id, "created_at": {"$gte": cutoff}}).sort("created_at", ASCENDING)]
    return {
        "range_days": days,
        "mood_logs": mood_logs,
        "message_count": db.chat_messages.count_documents({"user_id": user_id, "created_at": {"$gte": cutoff}}),
        "session_count": db.chat_sessions.count_documents({"user_id": user_id, "created_at": {"$gte": cutoff}})
    }


def get_user_settings(user_id: str) -> Dict[str, Any]:
    user = get_user_by_id(user_id) or {}
    return user.get("settings", {})


def update_user_settings(user_id: str, settings: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    allowed = {"consent_given", "retention_enabled", "retention_days", "locale"}
    clean = {key: value for key, value in settings.items() if key in allowed}
    if "retention_days" in clean:
        clean["retention_days"] = max(1, min(365, int(clean["retention_days"])))
    if "locale" in clean:
        clean["locale"] = "pakistan"
    if clean:
        get_db().users.update_one({"id": user_id}, {"$set": {f"settings.{key}": value for key, value in clean.items()}})
    return get_user_by_id(user_id)


def update_safety_profile(user_id: str, profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Persist optional, user-controlled emergency preferences without any dispatch capability."""
    allowed = {
        "preferred_hospital_name",
        "preferred_hospital_phone",
        "city_or_district",
        "emergency_actions_consent",
    }
    clean = {key: profile.get(key) for key in allowed if key in profile}
    for key in {"preferred_hospital_name", "preferred_hospital_phone", "city_or_district"} & clean.keys():
        clean[key] = str(clean[key]).strip()[:160]
    if "emergency_actions_consent" in clean:
        clean["emergency_actions_consent"] = bool(clean["emergency_actions_consent"])
    if clean:
        get_db().users.update_one(
            {"id": user_id},
            {"$set": {f"safety_profile.{key}": value for key, value in clean.items()}},
        )
    return get_user_by_id(user_id)


def create_chat_session(user_id: str, title: str = "New reflection") -> Dict[str, Any]:
    doc = {
        "id": f"ses-{uuid.uuid4().hex[:12]}",
        "user_id": user_id,
        "title": title[:100] or "New reflection",
        "summary": None,
        "risk_state": "normal",
        "crisis_triggered_at": None,
        "last_risk_level": None,
        "crisis_count": 0,
        "created_at": datetime.utcnow().isoformat(),
        "last_message_at": datetime.utcnow().isoformat()
    }
    get_db().chat_sessions.insert_one(doc)
    return serialize_doc(doc)


def get_chat_sessions(user_id: str) -> List[Dict[str, Any]]:
    cursor = get_db().chat_sessions.find({"user_id": user_id}).sort("last_message_at", DESCENDING)
    return [serialize_doc(doc) for doc in cursor]


def get_chat_session_by_id(session_id: str, user_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    query: Dict[str, Any] = {"id": session_id}
    if user_id:
        query["user_id"] = user_id
    doc = get_db().chat_sessions.find_one(query)
    return serialize_doc(doc)


def update_chat_session(session_id: str, user_id: Optional[str], updates: Dict[str, Any]) -> None:
    allowed = {
        key: value for key, value in updates.items()
        if key in {"title", "summary", "last_message_at", "risk_state", "crisis_triggered_at", "last_risk_level", "crisis_count"}
    }
    if allowed:
        query: Dict[str, Any] = {"id": session_id}
        if user_id:
            query["user_id"] = user_id
        get_db().chat_sessions.update_one(query, {"$set": allowed})


# User cooling window cache (user_id -> ISO timestamp)
_USER_COOLING_WINDOWS: Dict[str, str] = {}


def set_user_cooling_window(user_id: str, duration_minutes: int = 15) -> str:
    """Sets a cooling window for user across all sessions to prevent crisis-state escape."""
    if not user_id:
        return ""
    expiry = (datetime.utcnow() + timedelta(minutes=duration_minutes)).isoformat()
    _USER_COOLING_WINDOWS[user_id] = expiry
    try:
        get_db().users.update_one(
            {"id": user_id},
            {"$set": {"crisis_cooling_until": expiry, "last_crisis_at": datetime.utcnow().isoformat()}}
        )
    except Exception:
        pass
    return expiry


def is_user_in_cooling_window(user_id: Optional[str]) -> bool:
    """Checks whether the user is currently inside an active cooling window."""
    if not user_id:
        return False
    expiry_str = _USER_COOLING_WINDOWS.get(user_id)
    if not expiry_str:
        try:
            user = get_db().users.find_one({"id": user_id})
            if user:
                expiry_str = user.get("crisis_cooling_until")
        except Exception:
            pass
    if not expiry_str:
        return False
    try:
        expiry = datetime.fromisoformat(expiry_str)
        if datetime.utcnow() < expiry:
            return True
        else:
            _USER_COOLING_WINDOWS.pop(user_id, None)
            return False
    except Exception:
        return False


def clear_user_cooling_window(user_id: str) -> None:
    """Clears user cooling window upon verified safety workflow completion."""
    if not user_id:
        return
    _USER_COOLING_WINDOWS.pop(user_id, None)
    try:
        get_db().users.update_one(
            {"id": user_id},
            {"$unset": {"crisis_cooling_until": ""}}
        )
    except Exception:
        pass


def generate_clearance_token(session_id: str, user_id: str, secret_key: str) -> str:
    """Generates an HMAC-signed one-time clearance token with 5-minute TTL."""
    now = int(time.time())
    payload = f"{session_id}:{user_id}:{now}"
    signature = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def verify_clearance_token(token: str, session_id: str, secret_key: str, max_age_seconds: int = 300) -> bool:
    """Verifies HMAC signature and 5-minute TTL for a clearance token."""
    try:
        parts = token.split(":")
        if len(parts) != 4:
            return False
        tok_session, tok_user, tok_time_str, tok_sig = parts
        if tok_session != session_id:
            return False
        tok_time = int(tok_time_str)
        if time.time() - tok_time > max_age_seconds:
            return False
        payload = f"{tok_session}:{tok_user}:{tok_time_str}"
        expected = hmac.new(secret_key.encode(), payload.encode(), hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, tok_sig)
    except Exception:
        return False


def set_session_risk_state(
    session_id: str,
    user_id: Optional[str],
    new_state: str,
    risk_level: Optional[str] = None,
    expected_version: Optional[int] = None
) -> Dict[str, Any]:
    """Updates session risk state ('normal', 'crisis_active', 'elevated_monitoring', 'resolved_by_safety_flow') with versioning."""
    valid_states = {"normal", "crisis_active", "elevated_monitoring", "resolved_by_safety_flow"}
    state = new_state if new_state in valid_states else "normal"
    
    updates: Dict[str, Any] = {
        "risk_state": state,
        "last_message_at": datetime.utcnow().isoformat()
    }
    if risk_level:
        updates["last_risk_level"] = risk_level
    if state == "crisis_active":
        updates["crisis_triggered_at"] = datetime.utcnow().isoformat()
        if user_id:
            set_user_cooling_window(user_id)
        
    query: Dict[str, Any] = {"id": session_id}
    if expected_version is not None:
        query["version"] = expected_version

    set_dict = dict(updates)
    if user_id:
        set_dict["user_id"] = user_id

    update_op: Dict[str, Any] = {
        "$set": set_dict,
        "$inc": {"version": 1},
        "$setOnInsert": {
            "title": "Chat Session",
            "created_at": datetime.utcnow().isoformat()
        }
    }
    if state == "crisis_active":
        update_op["$inc"]["crisis_count"] = 1
    else:
        update_op["$setOnInsert"]["crisis_count"] = 0

    res = get_db().chat_sessions.update_one(query, update_op, upsert=(expected_version is None))
    if expected_version is not None and res.matched_count == 0:
        raise ValueError(f"Concurrent update conflict on session {session_id} (expected version {expected_version})")

    return get_session_risk_state(session_id, user_id)


def get_session_risk_state(session_id: Optional[str], user_id: Optional[str] = None) -> Dict[str, Any]:
    """Returns the risk state dictionary for a session, including concurrency version."""
    if not session_id:
        return {"risk_state": "normal", "last_risk_level": "LOW", "crisis_count": 0, "version": 1}
    session = get_chat_session_by_id(session_id, user_id)
    if not session:
        return {"risk_state": "normal", "last_risk_level": "LOW", "crisis_count": 0, "version": 1}
    return {
        "risk_state": session.get("risk_state", "normal"),
        "last_risk_level": session.get("last_risk_level", "LOW"),
        "crisis_triggered_at": session.get("crisis_triggered_at"),
        "crisis_count": session.get("crisis_count", 0),
        "version": session.get("version", 1),
    }


def clear_session_crisis_state(
    session_id: str,
    user_id: Optional[str] = None,
    resolution_type: str = "grounding_completed"
) -> Dict[str, Any]:
    """Guarded de-escalation of a crisis session via explicit safety workflow."""
    session = get_db().chat_sessions.find_one({"id": session_id})
    if not session:
        raise KeyError(f"Session {session_id} not found")

    # Ownership check: if session has user_id, caller must match
    if session.get("user_id") and user_id and session["user_id"] != user_id:
        raise PermissionError(f"User {user_id} does not own session {session_id}")

    # Transition guard: only crisis_active or elevated_monitoring can be resolved
    current_state = session.get("risk_state", "normal")
    if current_state not in ("crisis_active", "elevated_monitoring"):
        raise ValueError(f"Cannot clear crisis state from non-crisis state: {current_state}")

    # Resolution type validation
    valid_resolutions = {
        "grounding_completed",
        "crisis_helpline_contacted",
        "support_network_contacted",
        "safety_flow_completed",
        "user_confirmed_safe"
    }
    res_type = resolution_type if resolution_type in valid_resolutions else "grounding_completed"

    save_audit_event("crisis_session_resolved", user_id or session.get("user_id"), {
        "session_id": session_id,
        "resolution_type": res_type,
        "timestamp": datetime.utcnow().isoformat()
    })

    owner_id = user_id or session.get("user_id")
    if owner_id:
        clear_user_cooling_window(owner_id)

    return set_session_risk_state(session_id, owner_id, "resolved_by_safety_flow", risk_level="LOW")


def save_audit_event(event_type: str, actor_id: Optional[str] = None, metadata: Optional[Dict[str, Any]] = None) -> None:
    """Store security/safety metadata only; never save raw chat text or credentials."""
    get_db().audit_logs.insert_one({
        "id": f"audit-{uuid.uuid4().hex[:12]}", "event_type": event_type,
        "actor_id": actor_id, "metadata": metadata or {}, "created_at": datetime.utcnow().isoformat()
    })


def delete_mood_log(log_id: str, user_id: str) -> bool:
    """Deletes a specific mood log belonging to a user."""
    db = get_db()
    result = db.mood_logs.delete_one({"id": log_id, "user_id": user_id})
    return result.deleted_count > 0


def delete_all_mood_logs(user_id: str) -> int:
    """Deletes all mood logs belonging to a user without affecting chats or sessions."""
    db = get_db()
    result = db.mood_logs.delete_many({"user_id": user_id})
    return result.deleted_count


# --- Chat Message Operations ---

def save_chat_message(
    user_id: Optional[str],
    sender: str,
    text: str,
    risk_level: Optional[str] = None,
    intent: Optional[str] = None,
    intent_confidence: Optional[float] = None,
    emotion: Optional[str] = None,
    sentiment: Optional[str] = None,
    grounding_exercise: Optional[str] = None,
    session_id: Optional[str] = None,
    expires_at: Optional[Any] = None
) -> Dict[str, Any]:
    """Saves a chat message to MongoDB chat_messages collection."""
    db = get_db()
    msg_id = f"msg-{uuid.uuid4().hex[:12]}"
    created_at = datetime.utcnow().isoformat()

    doc = {
        "id": msg_id,
        "user_id": user_id,
        "session_id": session_id,
        "sender": sender,
        "text": text,
        "risk_level": risk_level,
        "intent": intent,
        "intent_confidence": intent_confidence,
        "emotion": emotion,
        "sentiment": sentiment,
        "grounding_exercise": grounding_exercise,
        "expires_at": expires_at,
        "created_at": created_at
    }

    db.chat_messages.insert_one(doc)
    return serialize_doc(doc)


def get_chat_history(user_id: str, session_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves most recent chat history for an authenticated user, optionally scoped to a session, returned in chronological order (ASC)."""
    db = get_db()
    query: Dict[str, Any] = {"user_id": user_id}
    if session_id:
        query["session_id"] = session_id
    cursor = db.chat_messages.find(query).sort("created_at", DESCENDING).limit(limit)
    messages = [serialize_doc(doc) for doc in cursor]
    messages.reverse()
    return messages


def delete_chat_session(session_id: str, user_id: str) -> bool:
    """Deletes a chat session and all messages within that session for a user."""
    db = get_db()
    db.chat_messages.delete_many({"user_id": user_id, "session_id": session_id})
    res = db.chat_sessions.delete_one({"id": session_id, "user_id": user_id})
    # Synchronize session count in user_profiles
    remaining = db.chat_sessions.count_documents({"user_id": user_id})
    db.user_profiles.update_one({"user_id": user_id}, {"$set": {"session_count": remaining}})
    return res.deleted_count > 0


# --- Data Retention, Privacy & Export Operations ---

def export_user_data(user_id: str) -> Dict[str, Any]:
    """Exports all personal account profile data, chat messages, and mood logs in clean JSON format."""
    user_info = get_user_by_id(user_id)
    chat_history = get_chat_history(user_id, limit=1000)
    mood_history = get_mood_logs(user_id, limit=1000)

    return {
        "export_metadata": {
            "exported_at": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "format_version": "2.0-mongodb"
        },
        "user_profile": user_info,
        "chat_messages": chat_history,
        "mood_logs": mood_history
    }


def delete_user_data(user_id: str) -> Dict[str, int]:
    """
    Idempotent multi-collection data wipe for personal chat messages, mood logs, sessions,
    and audit events that reference the user. Returns exact counts of documents deleted.
    """
    db = get_db()

    res_msg = db.chat_messages.delete_many({"user_id": user_id})
    res_mood = db.mood_logs.delete_many({"user_id": user_id})
    res_session = db.chat_sessions.delete_many({"user_id": user_id})
    res_audit = db.audit_logs.delete_many({"actor_id": user_id})
    db.user_profiles.update_one(
        {"user_id": user_id},
        {"$set": {"session_count": 0, "crisis_count": 0, "last_topic": None, "coping_tried": []}}
    )

    return {
        "deleted_messages": res_msg.deleted_count,
        "deleted_mood_logs": res_mood.deleted_count,
        "deleted_sessions": res_session.deleted_count,
        "deleted_audit_events": res_audit.deleted_count
    }


def delete_user_account(user_id: str) -> Dict[str, Any]:
    """
    Permanently purges the user account document from the users collection
    alongside wiping all associated chat messages, mood logs, and sessions.
    """
    db = get_db()
    data_counts = delete_user_data(user_id)
    res_user = db.users.delete_one({"id": user_id})

    return {
        "user_account_deleted": res_user.deleted_count > 0,
        "data_wiped": data_counts
    }


def update_trusted_contact(user_id: str, contact_data: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """
    Persists personal trusted contact details ({name, phone, relationship}) in the user document.
    """
    db = get_db()
    trusted = {
        "name": contact_data.get("name", "").strip(),
        "phone": contact_data.get("phone", "").strip(),
        "relationship": contact_data.get("relationship", "Friend/Family").strip()
    }
    db.users.update_one({"id": user_id}, {"$set": {"trusted_contact": trusted}})
    return get_user_by_id(user_id)


# NOTE: cleanup_old_records() is now a manual/audit purge tool, not the primary deletion mechanism (the TTL index is).
def cleanup_old_records(retention_days: int = 30) -> Dict[str, int]:
    """Deletes documents older than retention_days from chat_messages and mood_logs."""
    db = get_db()
    now_dt = datetime.utcnow()
    now_iso = now_dt.isoformat()
    cutoff_date = (now_dt - timedelta(days=retention_days)).isoformat()

    res_msg = db.chat_messages.delete_many({
        "$or": [
            {"created_at": {"$lt": cutoff_date}},
            {"expires_at": {"$lte": now_dt}},
            {"expires_at": {"$lte": now_iso}}
        ]
    })
    res_mood = db.mood_logs.delete_many({
        "$or": [
            {"created_at": {"$lt": cutoff_date}},
            {"expires_at": {"$lte": now_dt}},
            {"expires_at": {"$lte": now_iso}}
        ]
    })

    return {
        "cutoff_date": cutoff_date,
        "deleted_messages": res_msg.deleted_count,
        "deleted_mood_logs": res_mood.deleted_count
    }


# ===========================================================================
# Clinical Crisis Safety Logs & Review Operations (safety_logs collection)
# ===========================================================================

# Circuit breaker state for safety logging persistence
_SAFETY_LOG_CIRCUIT_BROKEN_UNTIL: float = 0.0
_SAFETY_LOG_CONSECUTIVE_FAILURES: int = 0
_CIRCUIT_BREAKER_COOLDOWN_SEC: float = 30.0
_MAX_CONSECUTIVE_FAILURES: int = 3
_safety_log_lock = threading.Lock()


def is_safety_log_circuit_open() -> bool:
    """Returns True if the safety logging circuit breaker is currently open."""
    global _SAFETY_LOG_CIRCUIT_BROKEN_UNTIL
    return time.time() < _SAFETY_LOG_CIRCUIT_BROKEN_UNTIL


def reset_safety_log_circuit() -> None:
    """Resets the safety log circuit breaker state (useful for tests and manual resets)."""
    global _SAFETY_LOG_CIRCUIT_BROKEN_UNTIL, _SAFETY_LOG_CONSECUTIVE_FAILURES
    with _safety_log_lock:
        _SAFETY_LOG_CIRCUIT_BROKEN_UNTIL = 0.0
        _SAFETY_LOG_CONSECUTIVE_FAILURES = 0


def _record_safety_log_failure(err: Exception) -> None:
    global _SAFETY_LOG_CIRCUIT_BROKEN_UNTIL, _SAFETY_LOG_CONSECUTIVE_FAILURES
    with _safety_log_lock:
        _SAFETY_LOG_CONSECUTIVE_FAILURES += 1
        if _SAFETY_LOG_CONSECUTIVE_FAILURES >= _MAX_CONSECUTIVE_FAILURES:
            _SAFETY_LOG_CIRCUIT_BROKEN_UNTIL = time.time() + _CIRCUIT_BREAKER_COOLDOWN_SEC
            logger.error(
                f"Safety logging circuit breaker ACTIVATED for {_CIRCUIT_BREAKER_COOLDOWN_SEC}s "
                f"after {_SAFETY_LOG_CONSECUTIVE_FAILURES} consecutive errors. Last error: {err}"
            )


def _record_safety_log_success() -> None:
    global _SAFETY_LOG_CONSECUTIVE_FAILURES
    with _safety_log_lock:
        _SAFETY_LOG_CONSECUTIVE_FAILURES = 0


def redact_trigger_message(text: str, max_chars: int = 60) -> str:
    """
    Produces a privacy-preserving redacted excerpt and cryptographic hash of the triggering message.
    The full raw message is never persisted in safety_logs to minimize sensitive data retention.
    """
    if not text or not isinstance(text, str):
        return "[EMPTY]"

    msg_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    sensitive_tokens = {
        "kill", "killing", "suicide", "suicidal", "murder", "die", "dying", "death",
        "stab", "shoot", "hang", "cut", "cutting", "overdose", "slit", "gun",
        "knife", "blade", "poison", "marne", "khatam", "jaan", "khudkushi", "marna"
    }

    words = text.strip().split()
    redacted = []
    for w in words[:12]:
        cleaned_w = re.sub(r"[^\w]", "", w.lower())
        if cleaned_w in sensitive_tokens or any(t in cleaned_w for t in ("suicid", "overdos")):
            redacted.append("[REDACTED]")
        else:
            redacted.append(w)

    excerpt = " ".join(redacted)
    if len(excerpt) > max_chars:
        excerpt = excerpt[:max_chars].rsplit(" ", 1)[0] + "..."

    return f"{excerpt} [hash:{msg_hash}]"


def normalize_safety_category(cat: Any) -> str:
    """Normalizes internal enum values and classification labels into clean, standard categories."""
    if hasattr(cat, "value"):
        c = str(cat.value)
    else:
        c = str(cat or "")

    c_upper = c.upper()
    if "SELF_HARM" in c_upper or "SUICIDE" in c_upper:
        return "self-harm"
    if "HARM_TO_OTHERS" in c_upper or "HOMICIDE" in c_upper:
        return "homicide/threat-to-others"
    if "THREAT_AGAINST_USER" in c_upper:
        return "reported-threat-to-user"
    if "REPORTED_THREAT_TO_OTHERS" in c_upper:
        return "reported-threat-to-others"
    if "COMBINED" in c_upper:
        return "combined-high-crisis"
    if "THIRD_PARTY" in c_upper:
        return "third-party-report"
    return c.lower().replace("_", "-")


def log_safety_event(
    tier: int,
    rule_or_model: str,
    category: str,
    action_taken: str,
    message: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    confidence: Optional[float] = None,
) -> Optional[Dict[str, Any]]:
    """
    Persists a crisis detection event to the safety_logs collection.
    
    Guaranteed graceful failure: catches all exceptions, increments failure counters,
    and returns None instead of raising so safety triage is never interrupted.
    """
    if is_safety_log_circuit_open():
        logger.warning("Safety log write skipped: circuit breaker is open.")
        return None

    try:
        db = get_db()

        if user_id:
            user_ref = user_id
            is_guest = False
        else:
            seed = session_id or str(uuid.uuid4())
            user_ref = f"guest-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:12]}"
            is_guest = True

        log_id = f"safe-{uuid.uuid4().hex[:12]}"
        now_dt = datetime.now(timezone.utc)  # Real BSON Date!

        doc = {
            "id": log_id,
            "timestamp": now_dt,  # Stored as native BSON Date (datetime object)
            "session_id": session_id,
            "user_id": user_ref,
            "is_guest": is_guest,
            "tier": int(tier),
            "rule_or_model": str(rule_or_model),
            "category": normalize_safety_category(category),
            "confidence": float(confidence) if confidence is not None else None,
            "action_taken": str(action_taken),
            "message_excerpt": redact_trigger_message(message),
            "message_hash": hashlib.sha256(message.encode("utf-8")).hexdigest()[:12] if message else "",
            "resolved": False,
            "reviewed": False,
            "admin_note": "",
            "reviewed_at": None,
            "reviewed_by": None,
        }

        db.safety_logs.insert_one(doc)
        _record_safety_log_success()
        return serialize_doc(doc)
    except Exception as e:
        logger.error(f"Failed to record safety log: {e}", exc_info=True)
        _record_safety_log_failure(e)
        return None


def log_safety_event_async(
    tier: int,
    rule_or_model: str,
    category: str,
    action_taken: str,
    message: str,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    confidence: Optional[float] = None,
    sync: bool = False,
) -> None:
    """
    Fire-and-forget logging hook.
    Dispatches to a daemon thread so it never blocks or slows the critical crisis response path.
    When sync=True (e.g. in test suites), executes synchronously.
    """
    if is_safety_log_circuit_open():
        return

    if sync:
        log_safety_event(
            tier=tier,
            rule_or_model=rule_or_model,
            category=category,
            action_taken=action_taken,
            message=message,
            session_id=session_id,
            user_id=user_id,
            confidence=confidence,
        )
        return

    def _worker():
        try:
            log_safety_event(
                tier=tier,
                rule_or_model=rule_or_model,
                category=category,
                action_taken=action_taken,
                message=message,
                session_id=session_id,
                user_id=user_id,
                confidence=confidence,
            )
        except Exception as e:
            logger.error(f"Async safety logging worker error: {e}")

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()


def _parse_filter_date(val: Any) -> Optional[datetime]:
    if not val:
        return None
    if isinstance(val, datetime):
        return val
    if isinstance(val, (int, float)):
        return datetime.fromtimestamp(val, tz=timezone.utc).replace(tzinfo=None)
    if isinstance(val, str) and val.strip():
        s = val.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
            if dt.tzinfo:
                dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
            return dt
        except Exception:
            pass
        try:
            return datetime.strptime(val.strip(), "%Y-%m-%d")
        except Exception:
            pass
    return None


def get_safety_logs(
    tier: Optional[Any] = None,
    category: Optional[str] = None,
    resolved: Optional[Any] = None,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
    page: int = 1,
    limit: int = 20,
) -> Dict[str, Any]:
    """
    Retrieves a paginated list of crisis safety logs with optional filters for
    tier, category, resolved status, and date range.
    """
    db = get_db()
    query: Dict[str, Any] = {}

    if tier is not None and str(tier).strip() != "" and str(tier).strip().lower() != "all":
        try:
            query["tier"] = int(tier)
        except (ValueError, TypeError):
            query["tier"] = tier

    if category and str(category).strip() != "" and str(category).strip().lower() != "all":
        query["category"] = normalize_safety_category(str(category).strip())

    if resolved is not None and str(resolved).strip() != "" and str(resolved).strip().lower() != "all":
        if isinstance(resolved, str):
            query["resolved"] = resolved.lower() in ("true", "1", "yes")
        else:
            query["resolved"] = bool(resolved)

    start_dt = _parse_filter_date(start_date)
    end_dt = _parse_filter_date(end_date)
    if end_dt and isinstance(end_date, str) and len(end_date.strip()) == 10:
        end_dt = end_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

    if start_dt or end_dt:
        date_q: Dict[str, Any] = {}
        if start_dt:
            date_q["$gte"] = start_dt
        if end_dt:
            date_q["$lte"] = end_dt
        query["timestamp"] = date_q

    total = db.safety_logs.count_documents(query)

    page = max(1, int(page))
    limit = max(1, min(100, int(limit)))
    skip = (page - 1) * limit

    cursor = db.safety_logs.find(query).sort("timestamp", DESCENDING).skip(skip).limit(limit)
    logs = [serialize_doc(doc) for doc in cursor]

    total_pages = (total + limit - 1) // limit if limit > 0 else 1

    return {
        "logs": logs,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages,
    }


def get_safety_log_by_id(log_id: str) -> Optional[Dict[str, Any]]:
    """Retrieves a single safety log by public ID."""
    db = get_db()
    doc = db.safety_logs.find_one({"id": log_id})
    return serialize_doc(doc)


def update_safety_log(log_id: str, updates: Dict[str, Any], actor_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Updates the review status and clinical notes of a safety log entry.
    """
    db = get_db()
    set_fields: Dict[str, Any] = {}

    if "resolved" in updates:
        is_res = bool(updates["resolved"])
        set_fields["resolved"] = is_res
        set_fields["reviewed"] = is_res
        if is_res:
            set_fields["reviewed_at"] = datetime.now(timezone.utc)
            if actor_id:
                set_fields["reviewed_by"] = actor_id

    if "reviewed" in updates and "resolved" not in updates:
        is_rev = bool(updates["reviewed"])
        set_fields["resolved"] = is_rev
        set_fields["reviewed"] = is_rev
        if is_rev:
            set_fields["reviewed_at"] = datetime.now(timezone.utc)
            if actor_id:
                set_fields["reviewed_by"] = actor_id

    if "admin_note" in updates:
        set_fields["admin_note"] = str(updates["admin_note"]).strip()

    if not set_fields:
        return get_safety_log_by_id(log_id)

    res = db.safety_logs.update_one({"id": log_id}, {"$set": set_fields})
    if res.matched_count == 0:
        return None

    return get_safety_log_by_id(log_id)


def get_safety_logs_stats() -> Dict[str, Any]:
    """
    Returns summary crisis flag metrics and counts for the admin dashboard header:
    overall total, unresolved count, flags per tier and category in the last 7 and 30 days.
    """
    db = get_db()
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    total_flags = db.safety_logs.count_documents({})
    unresolved_count = db.safety_logs.count_documents({"resolved": False})

    logs_7d = list(db.safety_logs.find({"timestamp": {"$gte": seven_days_ago}}))
    tier_7d = {1: 0, 2: 0, 3: 0}
    cat_7d: Dict[str, int] = {}
    for item in logs_7d:
        t = item.get("tier")
        if t in tier_7d:
            tier_7d[t] += 1
        c = item.get("category", "unknown")
        cat_7d[c] = cat_7d.get(c, 0) + 1

    logs_30d = list(db.safety_logs.find({"timestamp": {"$gte": thirty_days_ago}}))
    tier_30d = {1: 0, 2: 0, 3: 0}
    cat_30d: Dict[str, int] = {}
    for item in logs_30d:
        t = item.get("tier")
        if t in tier_30d:
            tier_30d[t] += 1
        c = item.get("category", "unknown")
        cat_30d[c] = cat_30d.get(c, 0) + 1

    return {
        "total_flags": total_flags,
        "unresolved_count": unresolved_count,
        "resolved_count": max(0, total_flags - unresolved_count),
        "last_7_days": {
            "total": len(logs_7d),
            "tier_1": tier_7d[1],
            "tier_2": tier_7d[2],
            "tier_3": tier_7d[3],
            "by_tier": tier_7d,
            "by_category": cat_7d,
        },
        "last_30_days": {
            "total": len(logs_30d),
            "tier_1": tier_30d[1],
            "tier_2": tier_30d[2],
            "tier_3": tier_30d[3],
            "by_tier": tier_30d,
            "by_category": cat_30d,
        },
    }

