"""
seed_demo_analytics.py
Seeds realistic mood logs and contact profiles for demo accounts in MongoDB.
"""

import sys
import uuid
from datetime import datetime, timezone, timedelta

sys.path.insert(0, "server")
from database import get_db
from auth import hash_password

def seed():
    db = get_db()
    now = datetime.now(timezone.utc)

    sample_moods = [
        (9, 5, ["Study", "Sleep"], "Feeling tired after long university lectures."),
        (8, 6, ["Exercise", "Relaxation"], "Went for an evening walk, feeling calmer."),
        (6, 4, ["Exam", "Study"], "Stressed about upcoming project presentation and deadlines."),
        (5, 5, ["Exam", "Work"], "Made solid progress on project slides, feeling slightly better."),
        (4, 7, ["Social", "Relaxation"], "Met up with university friends, had lunch and good laughs."),
        (3, 6, ["Study", "Sleep"], "Sleep routine is stabilizing nicely."),
        (1, 8, ["Exercise", "Relaxation"], "Went for a morning run, feeling energized and optimistic."),
        (0, 7, ["Study", "Social"], "Final presentation preparation complete, feeling confident!")
    ]

    target_users = ["usr-9c667b679dbd", "usr-bdd06ffdce77"]

    # Also check or create demo@mindguard.ai
    demo_user = db.users.find_one({"email": "demo@mindguard.ai"})
    if not demo_user:
        demo_id = "usr-demo12345678"
        db.users.insert_one({
            "id": demo_id,
            "name": "Saqib Tariq",
            "email": "demo@mindguard.ai",
            "password_hash": hash_password("MindGuard@2026"),
            "created_at": now.isoformat(),
            "role": "user",
            "settings": {"consent_given": True, "retention_enabled": True, "retention_days": 30, "locale": "pakistan"},
            "trusted_contact": {"name": "Ali Khan", "phone": "03001234567", "relationship": "Close Friend"},
            "safety_profile": {"preferred_hospital_name": "PIMS Hospital Islamabad", "preferred_hospital_phone": "051-9261170", "city_or_district": "Islamabad", "emergency_actions_consent": True}
        })
        target_users.append(demo_id)
    else:
        target_users.append(demo_user["id"])

    for uid in target_users:
        db.users.update_one(
            {"id": uid},
            {"$set": {
                "trusted_contact": {"name": "Ali Khan", "phone": "03001234567", "relationship": "Close Friend"},
                "safety_profile": {"preferred_hospital_name": "PIMS Hospital Islamabad", "preferred_hospital_phone": "051-9261170", "city_or_district": "Islamabad", "emergency_actions_consent": True}
            }}
        )

        # Clear old mood logs for fresh realistic trend
        db.mood_logs.delete_many({"user_id": uid})

        for days_ago, score, tags, notes in sample_moods:
            t = (now - timedelta(days=days_ago)).isoformat()
            db.mood_logs.insert_one({
                "id": f"mood-{uuid.uuid4().hex[:12]}",
                "user_id": uid,
                "score": score,
                "tags": tags,
                "notes": notes,
                "created_at": t,
                "expires_at": (now + timedelta(days=30)).isoformat()
            })

        # Seed a sample previous chat session if user has none
        if db.chat_sessions.count_documents({"user_id": uid}) == 0:
            ses_id = f"ses-{uuid.uuid4().hex[:12]}"
            created_time = (now - timedelta(days=2)).isoformat()
            db.chat_sessions.insert_one({
                "id": ses_id,
                "user_id": uid,
                "title": "Managing Presentation Stress",
                "summary": None,
                "risk_state": "normal",
                "crisis_triggered_at": None,
                "last_risk_level": "LOW",
                "crisis_count": 0,
                "created_at": created_time,
                "last_message_at": created_time
            })
            db.chat_messages.insert_one({
                "id": f"msg-{uuid.uuid4().hex[:12]}",
                "user_id": uid,
                "session_id": ses_id,
                "sender": "user",
                "text": "I have my final year project presentation coming up and I feel pretty anxious about it.",
                "risk_level": "LOW",
                "intent": "EXAM_OR_ACADEMIC_STRESS",
                "intent_confidence": 0.94,
                "emotion": "FEAR",
                "sentiment": "NEGATIVE",
                "created_at": created_time
            })
            db.chat_messages.insert_one({
                "id": f"msg-{uuid.uuid4().hex[:12]}",
                "user_id": uid,
                "session_id": ses_id,
                "sender": "assistant",
                "text": "It is completely normal to feel nervous before such a major milestone. You have put in months of effort, and your preparation will speak for itself. Let's break down your rehearsal into small, manageable parts so you feel fully in control.",
                "risk_level": "LOW",
                "intent": "EXAM_OR_ACADEMIC_STRESS",
                "intent_confidence": 0.94,
                "emotion": "NEUTRAL",
                "sentiment": "POSITIVE",
                "created_at": created_time
            })
            db.user_profiles.update_one(
                {"user_id": uid},
                {"$set": {"last_topic": "Exam / Academic Stress", "session_count": 1}},
                upsert=True
            )

    print(f"Successfully seeded mood logs and profile for user IDs: {target_users}")
    print(f"Total mood logs now in DB: {db.mood_logs.count_documents({})}")

if __name__ == "__main__":
    seed()
