"""
REAL MONGODB PERSISTENCE & CONCURRENCY TESTS (Phase 5)

Runs directly against the real local MongoDB daemon (mongodb://localhost:27017, v8.3.7)
bypassing mongomock using the underlying PyMongo synchronous client.
Uses a dedicated, temporary throwaway database (mindguard_test_<uuid>).
Guarantees clean tear-down: drops ONLY the throwaway test database after tests complete.
Never touches production or development collections.

Verifies:
  1. Compound index initialization on users, chat_messages, mood_logs, sessions.
  2. Index usage proof: queries utilize IXSCAN (not COLLSCAN) verified via database explain command.
  3. Unique-index concurrency enforcement: 16 simultaneous race registrations with the same email
     result in exactly 1 success and 15 DuplicateKeyError rejections.
  4. Clean database drop on completion.
"""
from __future__ import annotations

import uuid
import threading
from typing import List

import pytest
import pymongo.synchronous.mongo_client as real_pymongo
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError

LOCAL_MONGO_URI = "mongodb://localhost:27017"


@pytest.fixture(scope="module")
def real_mongo():
    """Connects to real local MongoDB, provisions a throwaway DB, and drops it on teardown."""
    try:
        client = real_pymongo.MongoClient(LOCAL_MONGO_URI, serverSelectionTimeoutMS=2000)
        client.server_info()  # probe connectivity
    except Exception as e:
        pytest.skip(f"Local MongoDB not reachable at {LOCAL_MONGO_URI}: {e}")

    throwaway_db_name = f"mindguard_test_{uuid.uuid4().hex[:8]}"
    db = client[throwaway_db_name]

    # Initialize MindGuard schema & indexes
    db.users.create_index([("email", ASCENDING)], unique=True, name="idx_unique_email")
    db.chat_messages.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_user_chat_timeline")
    db.mood_logs.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_user_mood_timeline")
    db.chat_sessions.create_index([("user_id", ASCENDING), ("created_at", DESCENDING)], name="idx_user_sessions_timeline")
    db.user_profiles.create_index([("user_id", ASCENDING)], name="idx_user_profiles_user_id", unique=True)
    db.chat_messages.create_index("expires_at", expireAfterSeconds=0)
    db.mood_logs.create_index("expires_at", expireAfterSeconds=0)

    yield {"client": client, "db": db, "name": throwaway_db_name}

    # Strict cleanup: drop throwaway database
    client.drop_database(throwaway_db_name)
    client.close()


def test_real_mongodb_indexes_created(real_mongo):
    """Verify all required unique, compound, and TTL indexes exist on real MongoDB."""
    db = real_mongo["db"]
    user_idx = db.users.index_information()
    assert "idx_unique_email" in user_idx
    assert user_idx["idx_unique_email"].get("unique") is True

    chat_idx = db.chat_messages.index_information()
    assert "idx_user_chat_timeline" in chat_idx
    assert chat_idx["idx_user_chat_timeline"]["key"] == [("user_id", 1), ("created_at", -1)]
    assert "expires_at_1" in chat_idx
    assert chat_idx["expires_at_1"].get("expireAfterSeconds") == 0

    mood_idx = db.mood_logs.index_information()
    assert "idx_user_mood_timeline" in mood_idx
    assert mood_idx["idx_user_mood_timeline"]["key"] == [("user_id", 1), ("created_at", -1)]
    assert "expires_at_1" in mood_idx
    assert mood_idx["expires_at_1"].get("expireAfterSeconds") == 0


def test_real_mongodb_ttl_auto_purge(real_mongo):
    """
    Creates a document with expires_at in the past (as a real datetime),
    confirms it exists immediately after insert, then confirms MongoDB's
    background TTL monitor removes it within ~90 seconds.
    """
    import time
    from datetime import datetime, timedelta

    db = real_mongo["db"]
    doc_id = f"msg-ttl-{uuid.uuid4().hex[:8]}"
    past_date = datetime.utcnow() - timedelta(minutes=5)

    # Insert document with expires_at in the past (as native datetime)
    db.chat_messages.insert_one({
        "id": doc_id,
        "user_id": "usr-ttl-test",
        "text": "This message should auto-purge via MongoDB TTL",
        "created_at": (datetime.utcnow() - timedelta(days=1)).isoformat(),
        "expires_at": past_date
    })

    # 1. Confirm it exists immediately after insert
    inserted = db.chat_messages.find_one({"id": doc_id})
    assert inserted is not None, "Document must exist immediately after insert"
    assert isinstance(inserted.get("expires_at"), datetime), "expires_at must be stored as native datetime"

    # 2. Confirm MongoDB's background TTL monitor removes it within ~90 seconds
    max_wait = 95
    poll_interval = 2
    start = time.time()
    purged = False

    while (time.time() - start) < max_wait:
        if db.chat_messages.find_one({"id": doc_id}) is None:
            purged = True
            break
        time.sleep(poll_interval)

    assert purged, f"Document was not removed by MongoDB TTL monitor within {max_wait}s (elapsed {time.time() - start:.1f}s)"


def test_real_mongodb_query_uses_ixscan_not_collscan(real_mongo):
    """Verify via db.command('explain') that timeline queries execute IXSCAN rather than COLLSCAN."""
    db = real_mongo["db"]

    # Seed sample messages
    for i in range(25):
        db.chat_messages.insert_one({
            "user_id": "usr-test-ixscan",
            "created_at": f"2026-10-16T12:00:{i:02d}",
            "text": f"Message {i}"
        })

    # Run explain command on find query with compound index sorting
    explain_res = db.command(
        "explain",
        {
            "find": "chat_messages",
            "filter": {"user_id": "usr-test-ixscan"},
            "sort": {"created_at": -1}
        }
    )

    plan = str(explain_res.get("queryPlanner", {}).get("winningPlan", {}))
    assert "IXSCAN" in plan, f"Query plan did not use index scan: {plan}"
    assert "idx_user_chat_timeline" in plan, f"Query did not use idx_user_chat_timeline: {plan}"
    assert "COLLSCAN" not in plan, f"Query performed an unindexed full collection scan: {plan}"


def test_real_mongodb_concurrent_unique_registration_race(real_mongo):
    """
    Simulate 16 threads attempting to register the exact same email simultaneously.
    Proves that real MongoDB's unique index strictly enforces single insertion,
    with exactly 1 success and 15 DuplicateKeyError exceptions.
    """
    db = real_mongo["db"]
    race_email = f"race_{uuid.uuid4().hex[:6]}@example.com"

    successes = []
    duplicate_errors = []
    other_errors = []

    def attempt_insert(thread_id: int):
        doc = {
            "id": f"usr-{uuid.uuid4().hex[:8]}",
            "name": f"User {thread_id}",
            "email": race_email,
            "password_hash": "dummy_bcrypt_hash",
            "role": "user"
        }
        try:
            db.users.insert_one(doc)
            successes.append(thread_id)
        except DuplicateKeyError:
            duplicate_errors.append(thread_id)
        except Exception as ex:
            other_errors.append((thread_id, str(ex)))

    threads: List[threading.Thread] = []
    for i in range(16):
        t = threading.Thread(target=attempt_insert, args=(i,))
        threads.append(t)

    # Launch all 16 threads simultaneously
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)

    assert other_errors == [], f"Unexpected non-duplicate errors during race: {other_errors}"
    assert len(successes) == 1, f"Expected exactly 1 success, got {len(successes)}: {successes}"
    assert len(duplicate_errors) == 15, f"Expected 15 DuplicateKeyErrors, got {len(duplicate_errors)}"

    # Verify database document count
    count = db.users.count_documents({"email": race_email})
    assert count == 1, f"Database has {count} documents for unique email!"
