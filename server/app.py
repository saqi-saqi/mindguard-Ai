"""
MindGuard - Backend API Server
================================
Enterprise-grade Flask application powering MindGuard:
- Multi-tier Crisis Detection Pipeline (Deterministic Regex -> TF-IDF/ML -> Gemini LLM Guardrail)
- User Authentication (JWT, bcrypt, rate limiting)
- Mood Tracking and Emotional Trend Analytics
- Chat Persistence with Configurable Privacy & Data Retention
- Crisis Resources and Grounding Exercise Delivery
- Full Security Headers, Audit Logging, and Privacy-Compliant Data Erasure
"""

import os
import sys
import time
import json
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

from flask import Flask, request, jsonify, g, send_from_directory
from flask_cors import CORS

# Add current directory and server directory to path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from config import (
    CORS_ORIGINS, RATE_LIMIT_PER_MINUTE, MAX_MESSAGE_LENGTH,
    GEMINI_API_KEY, FLASK_ENV
)
from database import (
    init_db, get_db, serialize_doc,
    create_user, get_user_by_email, get_user_by_id,
    save_mood_log, get_mood_logs, get_analytics_summary,
    get_user_settings, update_user_settings,
    create_chat_session, get_chat_sessions, update_chat_session,
    save_audit_event, delete_mood_log,
    save_chat_message, get_chat_history,
    export_user_data, delete_user_data, delete_user_account,
    update_trusted_contact, cleanup_old_records
)
from auth import (
    hash_password, verify_password, generate_token, decode_token,
    jwt_required, admin_required, optional_jwt, JWT_SECRET_KEY, JWT_ALGORITHM
)
from services.crisis_rules import (
    evaluate_crisis, evaluate_deterministic_crisis, is_contextual_or_negated,
    match_crisis_regex
)
from services.huggingface_service import (
    analyze_user_message, load_ml_pipelines
)
from services.llm_service import (
    generate_llm_response, evaluate_llm_safety_guardrail
)
from services.crisis_resources import (
    get_resources_for_region, check_resource_status, CRISIS_RESOURCES
)
from services.intent_rules import match_fast_path_intent

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MindGuard-API")

# Initialize Flask App
app = Flask(__name__, static_folder=os.path.join(os.path.dirname(BASE_DIR), "client"), static_url_path="")
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "dev_secret_key_mindguard_2026")
app.config["MAX_CONTENT_LENGTH"] = 1 * 1024 * 1024  # 1MB payload limit

# Configure CORS
CORS(
    app,
    resources={r"/api/*": {"origins": CORS_ORIGINS}},
    supports_credentials=True,
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
    methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"]
)

# Initialize Database and Start Pre-warming ML Pipelines
try:
    init_db()
except Exception as e:
    logger.error(f"Database initialization error on startup: {e}")

# Pre-warm ML pipelines in a background thread to avoid blocking server boot
import threading
threading.Thread(target=load_ml_pipelines, daemon=True).start()

# ---------------------------------------------------------------------------
# Rate Limiting & Security In-Memory Storage
# ---------------------------------------------------------------------------
_RATE_LIMIT_STORAGE: Dict[str, list] = {}
_RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_WINDOW_SECONDS = 60


def is_rate_limited(client_ip: str) -> bool:
    """Sliding-window IP rate limiter."""
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    with _RATE_LIMIT_LOCK:
        timestamps = _RATE_LIMIT_STORAGE.get(client_ip, [])
        valid_timestamps = [t for t in timestamps if t > cutoff]
        if len(valid_timestamps) >= RATE_LIMIT_PER_MINUTE:
            _RATE_LIMIT_STORAGE[client_ip] = valid_timestamps
            return True
        valid_timestamps.append(now)
        _RATE_LIMIT_STORAGE[client_ip] = valid_timestamps
        return False


def reset_rate_limits():
    """Testing helper to reset in-memory rate limit store."""
    with _RATE_LIMIT_LOCK:
        _RATE_LIMIT_STORAGE.clear()


# ---------------------------------------------------------------------------
# Request Hooks & Security Headers
# ---------------------------------------------------------------------------
@app.before_request
def before_request_hook():
    """Executes pre-request validation, security tagging, and rate limiting."""
    g.start_time = time.time()
    raw_req_id = request.headers.get("X-Request-ID")
    g.request_id = raw_req_id if raw_req_id else f"req-{uuid.uuid4().hex[:12]}"

    if request.method == "OPTIONS":
        return "", 200

    if request.path.startswith("/api/"):
        client_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "127.0.0.1").split(",")[0].strip()
        if is_rate_limited(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip} on {request.path}")
            return jsonify({
                "success": False,
                "data": None,
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit of {RATE_LIMIT_PER_MINUTE} requests per minute exceeded. Please slow down."
                }
            }), 429


@app.after_request
def after_request_hook(response):
    """Appends strict enterprise security headers to every HTTP response."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' https://fonts.gstatic.com; "
        "img-src 'self' data: https:; "
        "connect-src 'self' https://generativelanguage.googleapis.com;"
    )
    if hasattr(g, "request_id"):
        response.headers["X-Request-ID"] = g.request_id
    return response


# ---------------------------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------------------------
@app.errorhandler(400)
def bad_request_error(e):
    return jsonify({"success": False, "data": None, "error": {"code": "BAD_REQUEST", "message": str(e)}}), 400

@app.errorhandler(404)
def not_found_error(e):
    return jsonify({"success": False, "data": None, "error": {"code": "NOT_FOUND", "message": "The requested resource was not found."}}), 404

@app.errorhandler(405)
def method_not_allowed_error(e):
    return jsonify({"success": False, "data": None, "error": {"code": "METHOD_NOT_ALLOWED", "message": "HTTP method not allowed on this endpoint."}}), 405

@app.errorhandler(413)
def request_entity_too_large(e):
    return jsonify({"success": False, "data": None, "error": {"code": "PAYLOAD_TOO_LARGE", "message": "Payload exceeds 1MB limit."}}), 413

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({"success": False, "data": None, "error": {"code": "RATE_LIMIT_EXCEEDED", "message": "Rate limit exceeded."}}), 429

@app.errorhandler(500)
def internal_server_error(e):
    logger.error(f"Internal server error: {e}", exc_info=True)
    return jsonify({"success": False, "data": None, "error": {"code": "INTERNAL_SERVER_ERROR", "message": "An unexpected server error occurred."}}), 500


# ---------------------------------------------------------------------------
# Core Static & UI Routing
# ---------------------------------------------------------------------------
@app.route("/")
def serve_index():
    client_dir = os.path.join(os.path.dirname(BASE_DIR), "client")
    if os.path.exists(os.path.join(client_dir, "index.html")):
        return send_from_directory(client_dir, "index.html")
    return jsonify({"name": "MindGuard AI API", "version": "2.0.0", "status": "online"})


@app.route("/<path:path>")
def serve_static(path):
    client_dir = os.path.join(os.path.dirname(BASE_DIR), "client")
    file_path = os.path.join(client_dir, path)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(client_dir, path)
    if os.path.exists(os.path.join(client_dir, "index.html")):
        return send_from_directory(client_dir, "index.html")
    return jsonify({"success": False, "error": {"code": "NOT_FOUND", "message": "Not Found"}}), 404


# ---------------------------------------------------------------------------
# System & Health Routes
# ---------------------------------------------------------------------------
@app.route("/api/health", methods=["GET"])
def system_health():
    db_ok = False
    try:
        db = get_db()
        db.command("ping")
        db_ok = True
    except Exception as e:
        logger.warning(f"Database health check failed: {e}")

    uptime_sec = round(time.time() - getattr(app, "_start_time", time.time()), 1)

    return jsonify({
        "success": db_ok,
        "data": {
            "status": "healthy" if db_ok else "degraded",
            "service": "MindGuard AI Backend",
            "version": "2.0.0",
            "database": "connected" if db_ok else "disconnected",
            "uptime_seconds": uptime_sec
        },
        "error": None
    }), 200 if db_ok else 503


@app.route("/api/resources", methods=["GET"])
def get_crisis_resources():
    region = request.args.get("region", "pakistan").strip().lower()
    reg_res = get_resources_for_region(region)
    intl_res = get_resources_for_region("international")
    return jsonify({
        "success": True,
        "data": {
            "region": region,
            "resources": {
                region: reg_res,
                "international": intl_res
            }
        },
        "error": None
    }), 200


# ---------------------------------------------------------------------------
# Authentication Routes
# ---------------------------------------------------------------------------
@app.route("/api/auth/register", methods=["POST"])
def register():
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_JSON", "message": "Invalid JSON body."}}), 400

    name = body.get("name")
    email = body.get("email")
    password = body.get("password")
    consent_given = bool(body.get("consent_given", False))

    if not isinstance(name, str) or not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_FIELD", "message": "All fields must be strings."}}), 400

    name = name.strip()
    email = email.strip().lower()
    password = password.strip()

    if not name or len(name) < 2:
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_NAME", "message": "Name must be at least 2 characters."}}), 400

    if not email or "@" not in email or "." not in email:
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_EMAIL", "message": "A valid email address is required."}}), 400

    if not password or len(password) < 8:
        return jsonify({"success": False, "data": None, "error": {"code": "WEAK_PASSWORD", "message": "Password must be at least 8 characters."}}), 400

    existing = get_user_by_email(email)
    if existing:
        return jsonify({"success": False, "data": None, "error": {"code": "DUPLICATE_EMAIL", "message": "An account with this email address already exists."}}), 409

    password_hash = hash_password(password)
    user_doc = create_user(name=name, email=email, password_hash=password_hash, consent_given=consent_given)

    token = generate_token(user_id=user_doc["id"], email=user_doc["email"])

    return jsonify({
        "success": True,
        "token": token,
        "data": {
            "token": token,
            "user": user_doc
        },
        "user": user_doc,
        "error": None
    }), 201


@app.route("/api/auth/login", methods=["POST"])
def login():
    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_JSON", "message": "Invalid JSON body."}}), 400

    raw_email = body.get("email")
    raw_pass = body.get("password")

    if not isinstance(raw_email, str) or not isinstance(raw_pass, str):
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_FIELD", "message": "Email and password must be strings."}}), 400

    email = raw_email.strip().lower()
    password = raw_pass.strip()

    if not email or not password:
        return jsonify({"success": False, "data": None, "error": {"code": "MISSING_CREDENTIALS", "message": "Email and password are required."}}), 400

    user = get_user_by_email(email)
    if not user or not verify_password(password, user.get("password_hash", "")):
        save_audit_event("login_failed", email, {"reason": "invalid_credentials"})
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_CREDENTIALS", "message": "Invalid email or password."}}), 401

    token = generate_token(user_id=user["id"], email=user["email"])
    save_audit_event("login_success", user["id"])

    sanitized_user = {k: v for k, v in user.items() if k != "password_hash"}
    return jsonify({
        "success": True,
        "data": {
            "token": token,
            "user": sanitized_user
        },
        "error": None
    }), 200


@app.route("/api/auth/me", methods=["GET"])
@jwt_required
def get_me():
    user = get_user_by_id(g.current_user["id"])
    if not user:
        return jsonify({"success": False, "data": None, "error": {"code": "USER_NOT_FOUND", "message": "User profile not found."}}), 404

    return jsonify({
        "success": True,
        "data": {
            "user": user
        },
        "error": None
    }), 200


@app.route("/api/auth/account", methods=["DELETE"])
@jwt_required
def delete_account():
    user_id = g.current_user["id"]
    res = delete_user_account(user_id)
    return jsonify({
        "success": True,
        "data": res,
        "error": None
    }), 200


# ---------------------------------------------------------------------------
# User Settings, Trusted Contact & Privacy Routes
# ---------------------------------------------------------------------------
@app.route("/api/user/settings", methods=["GET", "PUT"])
@jwt_required
def user_settings_endpoint():
    user_id = g.current_user["id"]
    if request.method == "GET":
        settings = get_user_settings(user_id)
        return jsonify({"success": True, "data": {"settings": settings}, "error": None}), 200

    body = request.get_json(silent=True) or {}
    updated = update_user_settings(user_id, body)
    return jsonify({"success": True, "data": {"user": updated}, "error": None}), 200


@app.route("/api/user/trusted-contact", methods=["POST", "GET"])
@jwt_required
def trusted_contact_endpoint():
    user_id = g.current_user["id"]
    if request.method == "GET":
        user = get_user_by_id(user_id) or {}
        contact = user.get("trusted_contact", {})
        return jsonify({"success": True, "data": {"trusted_contact": contact}, "error": None}), 200

    body = request.get_json(silent=True) or {}
    updated = update_trusted_contact(user_id, body)
    save_audit_event("trusted_contact_updated", user_id)
    return jsonify({"success": True, "data": {"user": updated}, "error": None}), 200


@app.route("/api/user/export", methods=["GET"])
@jwt_required
def export_endpoint():
    user_id = g.current_user["id"]
    data = export_user_data(user_id)
    save_audit_event("data_exported", user_id)
    return jsonify({"success": True, "data": data, "error": None}), 200


@app.route("/api/user/data", methods=["DELETE"])
@jwt_required
def wipe_user_data_endpoint():
    user_id = g.current_user["id"]
    counts = delete_user_data(user_id)
    return jsonify({"success": True, "data": {"stats": counts}, "error": None}), 200


# ---------------------------------------------------------------------------
# Mood Tracking & Analytics Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/moods", methods=["POST", "GET"])
@jwt_required
def moods_endpoint():
    user_id = g.current_user["id"]

    if request.method == "GET":
        limit = min(int(request.args.get("limit", 100)), 500)
        logs = get_mood_logs(user_id, limit=limit)
        return jsonify({"success": True, "data": {"mood_logs": logs}, "error": None}), 200

    body = request.get_json(silent=True) or {}
    score = body.get("score")
    tags = body.get("tags", [])
    notes = str(body.get("notes", ""))[:500]

    if not isinstance(score, int) or score < 1 or score > 10:
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_SCORE", "message": "Mood score must be an integer between 1 and 10."}}), 400

    user = get_user_by_id(user_id) or {}
    settings = user.get("settings", {})
    if not settings.get("retention_enabled", True):
        return jsonify({"success": False, "data": None, "error": {"code": "RETENTION_DISABLED", "message": "Mood logging is disabled when retention is turned off."}}), 409

    retention_days = int(settings.get("retention_days", 30))
    expires_at = (datetime.utcnow() + timedelta(days=retention_days)).isoformat()

    doc = save_mood_log(user_id, score, tags, notes, expires_at=expires_at)
    save_audit_event("mood_logged", user_id, {"score": score})

    return jsonify({"success": True, "data": {"mood_log": doc}, "error": None}), 201


@app.route("/api/moods/<log_id>", methods=["DELETE"])
@jwt_required
def delete_mood_endpoint(log_id):
    user_id = g.current_user["id"]
    deleted = delete_mood_log(log_id, user_id)
    if not deleted:
        return jsonify({"success": False, "data": None, "error": {"code": "NOT_FOUND", "message": "Mood log not found or permission denied."}}), 404

    return jsonify({"success": True, "data": {"deleted": True}, "error": None}), 200


@app.route("/api/analytics", methods=["GET"])
@jwt_required
def analytics_endpoint():
    user_id = g.current_user["id"]
    period = request.args.get("period", "monthly").lower()
    days = 365 if period == "yearly" else (90 if period == "quarterly" else (7 if period == "weekly" else 30))

    summary = get_analytics_summary(user_id, days=days)
    return jsonify({"success": True, "data": summary, "error": None}), 200


# ---------------------------------------------------------------------------
# Chat Sessions & Summaries
# ---------------------------------------------------------------------------
@app.route("/api/chat/sessions", methods=["GET", "POST"])
@jwt_required
def chat_sessions_endpoint():
    user_id = g.current_user["id"]
    if request.method == "GET":
        sessions = get_chat_sessions(user_id)
        return jsonify({"success": True, "data": {"sessions": sessions}, "error": None}), 200

    body = request.get_json(silent=True) or {}
    title = str(body.get("title", "New reflection"))[:100]
    session = create_chat_session(user_id, title)
    return jsonify({"success": True, "data": {"session": session}, "error": None}), 201


@app.route("/api/chat/history", methods=["GET"])
@jwt_required
def get_chat_history_endpoint():
    user_id = g.current_user["id"]
    limit = min(int(request.args.get("limit", 100)), 500)
    messages = get_chat_history(user_id, limit=limit)
    return jsonify({"success": True, "data": {"messages": messages, "chat_messages": messages}, "error": None}), 200


@app.route("/api/chat/summarize", methods=["POST"])
@jwt_required
def summarize_chat_endpoint():
    summary = "A supportive self-reflection session focused on identifying stressors and gentle coping strategies."
    return jsonify({"success": True, "data": {"summary": summary}, "error": None}), 200


@app.route("/api/chat/sessions/<session_id>/summarize", methods=["POST"])
@jwt_required
def summarize_session_endpoint(session_id):
    user_id = g.current_user["id"]
    summary = "A supportive self-reflection session focused on identifying stressors and gentle coping strategies."
    update_chat_session(session_id, user_id, {"summary": summary})
    return jsonify({"success": True, "data": {"summary": summary}, "error": None}), 200


@app.route("/api/admin/retention-cleanup", methods=["POST"])
@admin_required
def admin_cleanup():
    body = request.get_json(silent=True) or {}
    days = int(body.get("retention_days", 30))
    res = cleanup_old_records(retention_days=days)
    return jsonify({"success": True, "data": res, "error": None}), 200


# ---------------------------------------------------------------------------
# Core Chat & Multi-Tier Crisis Triage Endpoint
# ---------------------------------------------------------------------------
SAFETY_DISCLAIMER = (
    "MindGuard is an AI-powered conversational support companion, not a licensed therapist or medical diagnostic tool. "
    "If you or someone you know is in immediate danger or experiencing a life-threatening mental health emergency, "
    "please call emergency services (911 in the US) or contact the 988 Suicide & Crisis Lifeline immediately."
)


@app.route("/api/chat", methods=["POST"])
@optional_jwt
def chat():
    start_req_time = time.time()
    req_id = getattr(g, "request_id", None) or f"req-{uuid.uuid4().hex[:12]}"
    g.request_id = req_id

    body = request.get_json(silent=True)
    if not body or not isinstance(body, dict):
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_JSON", "message": "Invalid JSON body."}}), 400

    user_message = body.get("message")
    if not isinstance(user_message, str) or not user_message.strip():
        return jsonify({"success": False, "data": None, "error": {"code": "EMPTY_MESSAGE", "message": "Message text cannot be empty."}}), 400

    user_message = user_message.strip()

    if len(user_message) > MAX_MESSAGE_LENGTH:
        return jsonify({"success": False, "data": None, "error": {"code": "MESSAGE_TOO_LONG", "message": f"Message exceeds maximum allowed length ({MAX_MESSAGE_LENGTH} characters)."}}), 400

    session_id = body.get("session_id")
    user_api_key = body.get("api_key")

    user_id = g.current_user["id"] if hasattr(g, "current_user") and g.current_user else None

    # Retention settings
    retention_enabled = True
    retention_days = 30
    expires_at = None

    if user_id:
        user = get_user_by_id(user_id)
        if user:
            settings = user.get("settings", {})
            retention_enabled = bool(settings.get("retention_enabled", True))
            retention_days = int(settings.get("retention_days", 30))
            if retention_enabled:
                expires_at = (datetime.utcnow() + timedelta(days=retention_days)).isoformat()

    try:
        if user_id and not session_id:
            session_id = create_chat_session(user_id, user_message[:60])["id"]

        logger.info(f"[{req_id}] Processing message length={len(user_message)} chars (user_id={user_id})")

        # Capture prior user-only context BEFORE persisting current turn
        recent_context = []
        if user_id and retention_enabled:
            history_before_current = get_chat_history(user_id, limit=10)
            recent_context = [
                msg.get("text", "")
                for msg in history_before_current
                if isinstance(msg.get("text"), str)
                and msg.get("text")
                and msg.get("sender") == "user"
            ][-3:]

        # Save user message
        if user_id and retention_enabled:
            save_chat_message(user_id=user_id, sender="user", text=user_message, session_id=session_id, expires_at=expires_at)
            if session_id:
                update_chat_session(session_id, user_id, {"last_message_at": time.strftime("%Y-%m-%dT%H:%M:%S")})

        # -------------------------------------------------------------------
        # Step 1: Tier 1 - Deterministic Crisis Rules
        # -------------------------------------------------------------------
        crisis_eval = evaluate_deterministic_crisis(user_message)

        if crisis_eval["is_crisis"]:
            duration_ms = round((time.time() - start_req_time) * 1000, 2)
            logger.warning(f"[{req_id}] CRISIS DETECTED via Tier 1 Deterministic Rules. Duration={duration_ms}ms")

            if user_id and retention_enabled:
                save_chat_message(
                    user_id=user_id,
                    sender="assistant",
                    text=crisis_eval["safety_message"],
                    risk_level="HIGH_CRISIS",
                    intent="SUICIDE CRISIS OR SELF HARM RISK",
                    emotion="DISTRESS",
                    sentiment="NEGATIVE",
                    session_id=session_id,
                    expires_at=expires_at
                )
            save_audit_event("crisis_detected", user_id, {"source": "deterministic", "request_id": req_id})

            return jsonify({
                "success": True,
                "status": "success",
                "risk_level": "HIGH_CRISIS",
                "requires_immediate_action": True,
                "data": {
                    "status": "success",
                    "risk_level": "HIGH_CRISIS",
                    "reply": crisis_eval["safety_message"],
                    "disclaimer": SAFETY_DISCLAIMER,
                    "intent": "SUICIDE CRISIS OR SELF HARM RISK",
                    "emotion": "DISTRESS",
                    "sentiment": "NEGATIVE",
                    "emergency_resources": crisis_eval.get("resources", CRISIS_RESOURCES),
                    "requires_immediate_action": True,
                    "session_id": session_id,
                    "latency_ms": duration_ms,
                    "inference_latency_ms": duration_ms
                },
                "error": None
            }), 200

        # -------------------------------------------------------------------
        # Step 2: Tier 2 & Tier 2.5 - ML Classification & LLM Crisis Verifier
        # -------------------------------------------------------------------
        ml_results = analyze_user_message(user_message, context_turns=recent_context)

        is_crisis_signal = (
            ml_results["intent"] == "SUICIDE CRISIS OR SELF HARM RISK"
            and not is_contextual_or_negated(user_message)
        )

        triage_level = "LOW"

        if is_crisis_signal:
            conf = float(ml_results.get("intent_confidence", 0.5))

            if conf >= 0.85:
                triage_level = "HIGH_CRISIS"
            elif conf >= 0.30:
                verifier_res = evaluate_llm_safety_guardrail(
                    user_text=user_message,
                    api_key=user_api_key
                )
                if verifier_res is not None:
                    if verifier_res.get("is_crisis", False):
                        logger.info(f"[{req_id}] LLM Verifier CONFIRMED crisis risk ({verifier_res.get('category')})")
                        triage_level = "HIGH_CRISIS"
                    else:
                        cat = verifier_res.get("category", "")
                        if cat == "indirect_distress" and not verifier_res.get("is_crisis", False):
                            logger.info(f"[{req_id}] LLM Verifier flagged elevated distress ({cat}) - routing to ELEVATED_DISTRESS")
                            triage_level = "ELEVATED_DISTRESS"
                        else:
                            logger.info(f"[{req_id}] LLM Verifier de-escalated non-crisis message ({cat}) - routing to supportive flow")
                            triage_level = "LOW"
                else:
                    if conf >= 0.85:
                        triage_level = "HIGH_CRISIS"
                    elif conf >= 0.30:
                        triage_level = "ELEVATED_DISTRESS"
                    else:
                        triage_level = "LOW"

        if triage_level == "HIGH_CRISIS":
            duration_ms = round((time.time() - start_req_time) * 1000, 2)
            logger.warning(f"[{req_id}] CRISIS DETECTED via Tier 2/2.5 Pipeline. Duration={duration_ms}ms")

            if user_id and retention_enabled:
                save_chat_message(
                    user_id=user_id,
                    sender="assistant",
                    text=crisis_eval["safety_message"],
                    risk_level="HIGH_CRISIS",
                    intent=ml_results["intent"],
                    intent_confidence=ml_results["intent_confidence"],
                    emotion=ml_results["emotion"],
                    sentiment=ml_results["sentiment"],
                    session_id=session_id,
                    expires_at=expires_at
                )
            save_audit_event("crisis_detected", user_id, {"source": "ml_pipeline", "request_id": req_id})

            return jsonify({
                "success": True,
                "status": "success",
                "risk_level": "HIGH_CRISIS",
                "requires_immediate_action": True,
                "data": {
                    "status": "success",
                    "risk_level": "HIGH_CRISIS",
                    "reply": crisis_eval["safety_message"],
                    "disclaimer": SAFETY_DISCLAIMER,
                    "intent": ml_results["intent"],
                    "intent_confidence": ml_results["intent_confidence"],
                    "emotion": ml_results["emotion"],
                    "sentiment": ml_results["sentiment"],
                    "emergency_resources": crisis_eval.get("resources", CRISIS_RESOURCES),
                    "requires_immediate_action": True,
                    "session_id": session_id,
                    "latency_ms": duration_ms,
                    "inference_latency_ms": duration_ms
                },
                "error": None
            }), 200

        if triage_level == "ELEVATED_DISTRESS":
            bot_reply = (
                "I hear how overwhelming things feel right now, and I want you to know that you are not alone. "
                "Please consider reaching out to a supportive friend, counselor, or helpline. "
                "\n\n*(Note: If you feel overwhelmed or need someone to talk to, support is always free and confidential. "
                "You can call or text 988 anytime.)*"
            )
            duration_ms = round((time.time() - start_req_time) * 1000, 2)

            if user_id and retention_enabled:
                save_chat_message(
                    user_id=user_id,
                    sender="assistant",
                    text=bot_reply,
                    risk_level="ELEVATED_DISTRESS",
                    intent=ml_results["intent"],
                    intent_confidence=ml_results["intent_confidence"],
                    emotion=ml_results["emotion"],
                    sentiment=ml_results["sentiment"],
                    session_id=session_id,
                    expires_at=expires_at
                )

            return jsonify({
                "success": True,
                "status": "success",
                "risk_level": "ELEVATED_DISTRESS",
                "requires_immediate_action": False,
                "data": {
                    "status": "success",
                    "risk_level": "ELEVATED_DISTRESS",
                    "reply": bot_reply,
                    "disclaimer": SAFETY_DISCLAIMER,
                    "intent": ml_results["intent"],
                    "intent_confidence": ml_results["intent_confidence"],
                    "emotion": ml_results["emotion"],
                    "sentiment": ml_results["sentiment"],
                    "emergency_resources": crisis_eval.get("resources", CRISIS_RESOURCES),
                    "requires_immediate_action": False,
                    "session_id": session_id,
                    "latency_ms": duration_ms,
                    "inference_latency_ms": duration_ms
                },
                "error": None
            }), 200

        # -------------------------------------------------------------------
        # Step 3: Tier 3 - Supportive Flow Response Generation
        # -------------------------------------------------------------------
        bot_reply = generate_llm_response(
            user_text=user_message,
            intent=ml_results["intent"],
            emotion=ml_results["emotion"],
            sentiment=ml_results["sentiment"],
            api_key=user_api_key
        )

        duration_ms = round((time.time() - start_req_time) * 1000, 2)
        logger.info(f"[{req_id}] Processed non-crisis chat successfully. Duration={duration_ms}ms")

        if user_id and retention_enabled:
            save_chat_message(
                user_id=user_id,
                sender="assistant",
                text=bot_reply,
                risk_level="LOW",
                intent=ml_results["intent"],
                intent_confidence=ml_results["intent_confidence"],
                emotion=ml_results["emotion"],
                sentiment=ml_results["sentiment"],
                session_id=session_id,
                expires_at=expires_at
            )

        return jsonify({
            "success": True,
            "status": "success",
            "risk_level": "LOW",
            "requires_immediate_action": False,
            "data": {
                "status": "success",
                "risk_level": "LOW",
                "reply": bot_reply,
                "disclaimer": SAFETY_DISCLAIMER,
                "intent": ml_results["intent"],
                "intent_confidence": ml_results["intent_confidence"],
                "emotion": ml_results["emotion"],
                "sentiment": ml_results["sentiment"],
                "emergency_resources": None,
                "requires_immediate_action": False,
                "session_id": session_id,
                "latency_ms": duration_ms,
                "inference_latency_ms": duration_ms
            },
            "error": None
        }), 200

    except Exception as e:
        logger.error(f"[{req_id}] Unexpected error in /api/chat pipeline: {e}", exc_info=True)
        return jsonify({
            "success": False,
            "data": None,
            "error": {"code": "INTERNAL_SERVER_ERROR", "message": "An error occurred while processing your message. Please try again."}
        }), 500


# ---------------------------------------------------------------------------
# Feedback & Safety Audit Telemetry
# ---------------------------------------------------------------------------
@app.route("/api/feedback", methods=["POST"])
@optional_jwt
def submit_feedback():
    body = request.get_json(silent=True) or {}
    rating = body.get("rating")
    feedback_type = body.get("type", "general")
    notes = str(body.get("notes", ""))[:300]

    user_id = g.current_user["id"] if hasattr(g, "current_user") and g.current_user else None

    save_audit_event("safety_feedback", user_id, {
        "rating": rating,
        "type": feedback_type,
        "notes": notes
    })

    return jsonify({"success": True, "data": {"recorded": True}, "error": None}), 200


@app.route("/api/safety-feedback", methods=["POST"])
@optional_jwt
def safety_feedback():
    body = request.get_json(silent=True) or {}
    outcome = body.get("outcome")
    source = body.get("source")

    ALLOWED_SOURCES = {"crisis_modal", "crisis_card", "grounding_tool"}
    if source not in ALLOWED_SOURCES or not outcome:
        return jsonify({"success": False, "data": None, "error": {"code": "INVALID_FEEDBACK", "message": "Invalid feedback parameters."}}), 400

    user_id = g.current_user["id"] if hasattr(g, "current_user") and g.current_user else None
    save_audit_event("safety_support_selected", user_id, {
        "outcome": outcome,
        "source": source
    })

    return jsonify({"success": True, "data": {"recorded": True}, "error": None}), 201


# ---------------------------------------------------------------------------
# Application Initialization Entry Point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    app._start_time = time.time()
    port = int(os.environ.get("FLASK_PORT", 5000))
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    logger.info(f"MindGuard Backend Server starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=FLASK_ENV == "development")
