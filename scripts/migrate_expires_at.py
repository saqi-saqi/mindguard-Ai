"""
migrate_expires_at.py
=====================
One-time database migration script for MindGuard AI.
Converts legacy string-typed `expires_at` values in `chat_messages` and
`mood_logs` into native BSON Date (datetime) objects so that MongoDB's
automatic background TTL monitor (expireAfterSeconds=0) can purge expired
records as expected.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure server module is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = ROOT_DIR / "server"
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

# Do not force mongomock for real database migration
os.environ["USE_MONGOMOCK"] = "false"

from server.database import get_db, init_db


def parse_iso_to_datetime(val: str) -> datetime:
    """Parses an ISO 8601 string into a UTC datetime object."""
    dt = datetime.fromisoformat(val)
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def migrate_collection(db, collection_name: str) -> int:
    """Finds all documents with string-typed expires_at and updates them to native datetime."""
    coll = db[collection_name]
    query = {"expires_at": {"$type": "string"}}
    cursor = coll.find(query)

    converted_count = 0
    for doc in cursor:
        raw_val = doc.get("expires_at")
        if not raw_val or not isinstance(raw_val, str):
            continue
        try:
            parsed_dt = parse_iso_to_datetime(raw_val)
            coll.update_one(
                {"_id": doc["_id"]},
                {"$set": {"expires_at": parsed_dt}}
            )
            converted_count += 1
        except Exception as e:
            print(f"  [ERROR] Failed to convert doc {doc.get('id', doc.get('_id'))} in {collection_name}: {e}")

    return converted_count


def run_migration():
    print("=" * 70)
    print("   MINDGUARD: MIGRATE EXPIRES_AT STRINGS TO BSON DATE (TTL)")
    print("=" * 70)

    db = get_db()

    # Initialize collections and TTL indexes
    print("[1] Ensuring indexes (including TTL indexes on expires_at)...")
    init_db()

    # Check pre-migration string counts
    chat_str_pre = db.chat_messages.count_documents({"expires_at": {"$type": "string"}})
    mood_str_pre = db.mood_logs.count_documents({"expires_at": {"$type": "string"}})
    print(f"    Existing string-typed expires_at documents:")
    print(f"      - chat_messages: {chat_str_pre}")
    print(f"      - mood_logs:     {mood_str_pre}")

    # Migrate chat_messages
    print("\n[2] Migrating chat_messages collection...")
    chat_converted = migrate_collection(db, "chat_messages")
    print(f"    Converted {chat_converted} documents in chat_messages.")

    # Migrate mood_logs
    print("\n[3] Migrating mood_logs collection...")
    mood_converted = migrate_collection(db, "mood_logs")
    print(f"    Converted {mood_converted} documents in mood_logs.")

    # Verification
    chat_str_post = db.chat_messages.count_documents({"expires_at": {"$type": "string"}})
    mood_str_post = db.mood_logs.count_documents({"expires_at": {"$type": "string"}})
    chat_date_post = db.chat_messages.count_documents({"expires_at": {"$type": "date"}})
    mood_date_post = db.mood_logs.count_documents({"expires_at": {"$type": "date"}})

    print("\n[4] Migration Verification:")
    print(f"    chat_messages: {chat_date_post} BSON Date documents, {chat_str_post} string documents remaining.")
    print(f"    mood_logs:     {mood_date_post} BSON Date documents, {mood_str_post} string documents remaining.")

    # Check TTL indexes on collections
    chat_indexes = db.chat_messages.index_information()
    mood_indexes = db.mood_logs.index_information()

    chat_ttl = any(info.get("expireAfterSeconds") == 0 for info in chat_indexes.values())
    mood_ttl = any(info.get("expireAfterSeconds") == 0 for info in mood_indexes.values())

    print(f"    TTL index (expireAfterSeconds=0) on chat_messages: {'[OK]' if chat_ttl else '[FAIL]'}")
    print(f"    TTL index (expireAfterSeconds=0) on mood_logs:     {'[OK]' if mood_ttl else '[FAIL]'}")

    print("=" * 70)
    print("MIGRATION COMPLETED SUCCESSFULLY.")
    print("=" * 70)
    return {
        "chat_converted": chat_converted,
        "mood_converted": mood_converted,
        "chat_ttl_present": chat_ttl,
        "mood_ttl_present": mood_ttl
    }


if __name__ == "__main__":
    run_migration()
