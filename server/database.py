"""
database.py
===========
MongoDB Database Module for MindGuard AI.
Manages persistent MongoDB connections, schemas, collections, indexes,
BSON document serialization, user models, chat history, mood logs, and data retention workflows.
Supports both real PyMongo client and isolated mongomock testing.
"""

import os
import uuid
import logging
from datetime import datetime, timedelta
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


# --- Mood Logs Operations ---

def save_mood_log(user_id: str, score: int, tags: List[str], notes: str, expires_at: Optional[str] = None) -> Dict[str, Any]:
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


def set_session_risk_state(
    session_id: str,
    user_id: Optional[str],
    new_state: str,
    risk_level: Optional[str] = None
) -> Dict[str, Any]:
    """Updates session risk state ('normal', 'crisis_active', 'elevated_monitoring', 'resolved_by_safety_flow')."""
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
        
    query: Dict[str, Any] = {"id": session_id}
    set_dict = dict(updates)
    if user_id:
        set_dict["user_id"] = user_id

    update_op: Dict[str, Any] = {
        "$set": set_dict,
        "$setOnInsert": {
            "title": "Chat Session",
            "created_at": datetime.utcnow().isoformat()
        }
    }
    if state == "crisis_active":
        update_op["$inc"] = {"crisis_count": 1}
    else:
        update_op["$setOnInsert"]["crisis_count"] = 0

    get_db().chat_sessions.update_one(query, update_op, upsert=True)
    return get_session_risk_state(session_id, user_id)


def get_session_risk_state(session_id: Optional[str], user_id: Optional[str] = None) -> Dict[str, Any]:
    """Returns the risk state dictionary for a session."""
    if not session_id:
        return {"risk_state": "normal", "last_risk_level": "LOW", "crisis_count": 0}
    session = get_chat_session_by_id(session_id, user_id)
    if not session:
        return {"risk_state": "normal", "last_risk_level": "LOW", "crisis_count": 0}
    return {
        "risk_state": session.get("risk_state", "normal"),
        "last_risk_level": session.get("last_risk_level", "LOW"),
        "crisis_triggered_at": session.get("crisis_triggered_at"),
        "crisis_count": session.get("crisis_count", 0)
    }


def clear_session_crisis_state(
    session_id: str,
    user_id: Optional[str] = None,
    resolution_type: str = "grounding_completed"
) -> Dict[str, Any]:
    """Guarded de-escalation of a crisis session via explicit safety workflow."""
    save_audit_event("crisis_session_resolved", user_id, {
        "session_id": session_id,
        "resolution_type": resolution_type,
        "timestamp": datetime.utcnow().isoformat()
    })
    return set_session_risk_state(session_id, user_id, "resolved_by_safety_flow", risk_level="LOW")


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
    expires_at: Optional[str] = None
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


def get_chat_history(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Retrieves most recent chat history for an authenticated user, returned in chronological order (ASC)."""
    db = get_db()
    cursor = db.chat_messages.find({"user_id": user_id}).sort("created_at", DESCENDING).limit(limit)
    messages = [serialize_doc(doc) for doc in cursor]
    messages.reverse()
    return messages


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


def cleanup_old_records(retention_days: int = 30) -> Dict[str, int]:
    """Deletes documents older than retention_days from chat_messages and mood_logs."""
    db = get_db()
    cutoff_date = (datetime.utcnow() - timedelta(days=retention_days)).isoformat()

    res_msg = db.chat_messages.delete_many({"$or": [{"created_at": {"$lt": cutoff_date}}, {"expires_at": {"$lte": datetime.utcnow().isoformat()}}]})
    res_mood = db.mood_logs.delete_many({"$or": [{"created_at": {"$lt": cutoff_date}}, {"expires_at": {"$lte": datetime.utcnow().isoformat()}}]})

    return {
        "cutoff_date": cutoff_date,
        "deleted_messages": res_msg.deleted_count,
        "deleted_mood_logs": res_mood.deleted_count
    }
