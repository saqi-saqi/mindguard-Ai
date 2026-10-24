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
import re
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
    GEMINI_API_KEY, FLASK_ENV, FLASK_USE_RELOADER, FLASK_DEBUG,
    TRUSTED_PROXIES, USE_UNIFIED_CRISIS_PIPELINE
)
from database import (
    init_db, get_db, serialize_doc,
    create_user, get_user_by_email, get_user_by_id,
    save_mood_log, get_mood_logs, get_analytics_summary,
    get_user_settings, update_user_settings,
    create_chat_session, get_chat_sessions, update_chat_session,
    set_session_risk_state, get_session_risk_state, clear_session_crisis_state,
    set_user_cooling_window, is_user_in_cooling_window, clear_user_cooling_window,
    generate_clearance_token, verify_clearance_token,
    save_audit_event, delete_mood_log, delete_all_mood_logs,
    save_chat_message, get_chat_history, delete_chat_session,
    export_user_data, delete_user_data, delete_user_account,
    update_trusted_contact, update_safety_profile, cleanup_old_records,
    get_or_create_user_profile, update_user_profile, get_mood_summary_for_chat,
    log_safety_event, log_safety_event_async, get_safety_logs, get_safety_log_by_id,
    update_safety_log, get_safety_logs_stats
)
from auth import (
    hash_password, verify_password, generate_token, decode_token,
    jwt_required, admin_required, optional_jwt, JWT_SECRET_KEY, JWT_ALGORITHM
)
from services.crisis_rules import (
    evaluate_crisis, evaluate_deterministic_crisis, evaluate_crisis_pipeline,
    is_contextual_or_negated, match_crisis_regex, THIRD_PARTY_GUIDANCE_TEMPLATE,
    SAFETY_RESPONSE_TEMPLATE
)
from services.huggingface_service import (
    analyze_user_message, load_ml_pipelines
)
from services.llm_service import (
    generate_llm_response, evaluate_llm_safety_guardrail
)
from services.response_kb import INTENT_RESPONSES
from services.crisis_resources import (
    get_resources_for_region, check_resource_status, CRISIS_RESOURCES, SAFETY_DISCLAIMER
)
from services.intent_rules import match_fast_path_intent
from services.safety_classifier import (
    classify_safety_risk, SafetyRiskCategory
)
from services.unified_safety_pipeline import evaluate_unified_tier1_safety
from services.roman_urdu_router import (
    route as route_language_scope,
    ROUTE_ARABIC_SCRIPT,
    ROUTE_UNSUPPORTED_SCRIPT,
)


class PrivacyRedactionFilter(logging.Filter):
    """Redacts sensitive user prompts, credentials, and tokens from all log handlers."""
    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            # Mask API keys and bearer tokens
            record.msg = re.sub(r'(?:Bearer\s+|key=)[A-Za-z0-9_\-\.]{20,}', '[REDACTED_CREDENTIAL]', record.msg, flags=re.IGNORECASE)
        return True


# Configure Logging with Privacy Filter
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("MindGuard-API")
privacy_filter = PrivacyRedactionFilter()
logger.addFilter(privacy_filter)
for handler in logging.root.handlers:
    handler.addFilter(privacy_filter)

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

# Pre-warm ML pipelines in a background thread to avoid blocking server boot.
# Avoid duplicate pre-warming in Werkzeug reloader monitor parent process if reloader is active.
import threading
if os.environ.get("WERKZEUG_RUN_MAIN") in (None, "true"):
    threading.Thread(target=load_ml_pipelines, daemon=True).start()

# ---------------------------------------------------------------------------
# Rate Limiting & Security In-Memory Storage
# ---------------------------------------------------------------------------
# Note: In-memory rate limiting operates per-process. In a multi-worker deployment
# (e.g., Gunicorn or uWSGI with multiple workers), an out-of-process store such as
# Redis is required to share sliding-window rate counters across worker processes.
_RATE_LIMIT_STORAGE: Dict[str, list] = {}
_RATE_LIMIT_LOCK = threading.Lock()
RATE_LIMIT_WINDOW_SECONDS = 60


def get_client_ip(req) -> str:
    """
    Safely resolves the client IP address.
    Only trusts X-Forwarded-For if request.remote_addr is in TRUSTED_PROXIES.
    Otherwise uses request.remote_addr directly to prevent spoofing bypasses.
    """
    remote_addr = req.remote_addr or "127.0.0.1"
    raw_trusted = app.config.get("TRUSTED_PROXIES") if "TRUSTED_PROXIES" in app.config else (os.environ.get("TRUSTED_PROXIES") or TRUSTED_PROXIES)
    if isinstance(raw_trusted, str):
        trusted_set = {ip.strip() for ip in raw_trusted.split(",") if ip.strip()}
    elif isinstance(raw_trusted, (list, set, tuple)):
        trusted_set = {str(ip).strip() for ip in raw_trusted if str(ip).strip()}
    else:
        trusted_set = set()

    if remote_addr in trusted_set:
        forwarded_for = req.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Parse comma-separated IPs; leftmost IP is the original client
            ips = [ip.strip() for ip in forwarded_for.split(",") if ip.strip()]
            if ips:
                return ips[0]
    return remote_addr


def is_rate_limited(client_ip: str) -> bool:
    """Sliding-window IP rate limiter."""
    if app.config.get("RATE_LIMIT_DISABLED") or os.environ.get("RATE_LIMIT_DISABLED") == "true":
        return False
    effective_limit = int(app.config.get("RATE_LIMIT_PER_MINUTE") if "RATE_LIMIT_PER_MINUTE" in app.config else (os.environ.get("RATE_LIMIT_PER_MINUTE") or RATE_LIMIT_PER_MINUTE))
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW_SECONDS
    with _RATE_LIMIT_LOCK:
        timestamps = _RATE_LIMIT_STORAGE.get(client_ip, [])
        valid_timestamps = [t for t in timestamps if t > cutoff]
        if len(valid_timestamps) >= effective_limit:
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
        client_ip = get_client_ip(request)
        if is_rate_limited(client_ip):
            logger.warning(f"Rate limit exceeded for IP: {client_ip} on {request.path}")
            return jsonify({
                "success": False,
                "data": None,
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit of {RATE_LIMIT_PER_MINUTE} requests per minute exceeded. If you are in immediate danger or need crisis support, please contact emergency services at 1122 (Pakistan) or Umang helpline at 0311-7786264."
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
    region = "pakistan"
    reg_res = get_resources_for_region(region)
    return jsonify({
        "success": True,
        "data": {
            "region": region,
            "resources": {
                region: reg_res,
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
    return jsonify({"success": True, "data": {"user": updated, "settings": (updated or {}).get("settings", {})}, "error": None}), 200


@app.route("/api/user/safety-profile", methods=["POST", "GET"])
@jwt_required
def safety_profile_endpoint():
    user_id = g.current_user["id"]
    if request.method == "GET":
        user = get_user_by_id(user_id) or {}
        return jsonify({"success": True, "data": {"safety_profile": user.get("safety_profile", {})}, "error": None}), 200

    body = request.get_json(silent=True) or {}
    updated = update_safety_profile(user_id, body)
    save_audit_event("safety_profile_updated", user_id)
    return jsonify({"success": True, "data": {"user": updated, "safety_profile": (updated or {}).get("safety_profile", {})}, "error": None}), 200


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


@app.route("/api/user/profile-summary", methods=["GET"])
@jwt_required
def profile_summary_endpoint():
    """Returns the user's counseling profile: name, mood trend, crisis count,
    session count. Used by the client for a personalized welcome."""
    user_id = g.current_user["id"]
    profile = get_or_create_user_profile(user_id)
    mood_summary = get_mood_summary_for_chat(user_id)
    actual_sessions = get_db().chat_sessions.count_documents({"user_id": user_id})
    if profile.get("session_count") != actual_sessions:
        get_db().user_profiles.update_one({"user_id": user_id}, {"$set": {"session_count": actual_sessions}})
        profile["session_count"] = actual_sessions

    return jsonify({
        "success": True,
        "data": {
            "name": profile.get("preferred_name", "there"),
            "session_count": actual_sessions,
            "crisis_count": profile.get("crisis_count", 0),
            "last_topic": profile.get("last_topic"),
            "mood_summary": mood_summary,
            "coping_tried": profile.get("coping_tried", []),
        },
        "error": None
    }), 200


# ---------------------------------------------------------------------------
# Mood Tracking & Analytics Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/moods", methods=["POST", "GET", "DELETE"])
@jwt_required
def moods_endpoint():
    user_id = g.current_user["id"]

    if request.method == "DELETE":
        deleted_count = delete_all_mood_logs(user_id)
        save_audit_event("mood_logs_cleared", user_id, {"deleted_count": deleted_count})
        return jsonify({"success": True, "data": {"deleted_count": deleted_count}, "error": None}), 200

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
    expires_at = datetime.utcnow() + timedelta(days=retention_days)

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
    days = 1 if period == "daily" else (7 if period == "weekly" else (365 if period == "yearly" else (90 if period == "quarterly" else 30)))

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
    session_id = request.args.get("session_id")
    limit = min(int(request.args.get("limit", 100)), 500)
    messages = get_chat_history(user_id, session_id=session_id, limit=limit)
    return jsonify({"success": True, "data": {"messages": messages, "chat_messages": messages}, "error": None}), 200


@app.route("/api/chat/sessions/<session_id>", methods=["DELETE"])
@jwt_required
def delete_session_endpoint(session_id):
    user_id = g.current_user["id"]
    deleted = delete_chat_session(session_id, user_id)
    if deleted:
        return jsonify({"success": True, "data": {"deleted": True}, "error": None}), 200
    return jsonify({"success": False, "data": None, "error": {"code": "NOT_FOUND", "message": "Session not found."}}), 404


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
# Admin Crisis Safety Logs Review Endpoints
# ---------------------------------------------------------------------------

@app.route("/api/admin/safety-logs", methods=["GET"])
@admin_required
def get_admin_safety_logs():
    """
    Paginated, filterable clinical review endpoint for crisis detection logs.
    Supports filtering by tier, category, resolved status, and date range.
    Includes aggregated summary stats for dashboard header metrics.
    """
    tier = request.args.get("tier")
    category = request.args.get("category")
    resolved = request.args.get("resolved")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    try:
        page = int(request.args.get("page", 1))
    except (ValueError, TypeError):
        page = 1

    try:
        limit = int(request.args.get("limit", 20))
    except (ValueError, TypeError):
        limit = 20

    logs_result = get_safety_logs(
        tier=tier,
        category=category,
        resolved=resolved,
        start_date=start_date,
        end_date=end_date,
        page=page,
        limit=limit,
    )
    stats = get_safety_logs_stats()
    logs_result["stats"] = stats

    return jsonify({"success": True, "data": logs_result, "error": None}), 200


@app.route("/api/admin/safety-logs/stats", methods=["GET"])
@admin_required
def get_admin_safety_logs_stats():
    """Returns crisis flag counts per tier and category for the last 7 and 30 days."""
    stats = get_safety_logs_stats()
    return jsonify({"success": True, "data": stats, "error": None}), 200


@app.route("/api/admin/safety-logs/<log_id>", methods=["PATCH"])
@admin_required
def patch_admin_safety_log(log_id):
    """
    Updates a safety log entry: marks it as reviewed/resolved and adds clinician/admin notes.
    """
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({
            "success": False,
            "data": None,
            "error": {"code": "INVALID_JSON", "message": "Expected JSON object body."}
        }), 400

    actor_id = g.current_user.get("id") if hasattr(g, "current_user") and g.current_user else None
    updated = update_safety_log(log_id, body, actor_id=actor_id)
    if not updated:
        return jsonify({
            "success": False,
            "data": None,
            "error": {"code": "NOT_FOUND", "message": "Safety log entry not found."}
        }), 404

    save_audit_event("safety_log_reviewed", actor_id, {
        "log_id": log_id,
        "resolved": updated.get("resolved"),
        "timestamp": datetime.utcnow().isoformat()
    })

    return jsonify({"success": True, "data": updated, "error": None}), 200


# ---------------------------------------------------------------------------
# Core Chat & Multi-Tier Crisis Triage Endpoint
# ---------------------------------------------------------------------------
SAFETY_DISCLAIMER = (
    "MindGuard is an AI-powered conversational support companion, not a licensed therapist or medical diagnostic tool. "
    "If you or someone you know is in immediate danger or experiencing a life-threatening mental health emergency, "
    "please call Rescue 1122, Police 15 when another person is at immediate risk, or go to the nearest hospital emergency department."
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

    session_id = body.get("session_id")
    user_api_key = body.get("api_key")
    user_id = g.current_user["id"] if hasattr(g, "current_user") and g.current_user else None

    if len(user_message) > MAX_MESSAGE_LENGTH:
        if USE_UNIFIED_CRISIS_PIPELINE:
            long_safety = evaluate_unified_tier1_safety(user_message, session_id=session_id)
        else:
            long_safety = classify_safety_risk(user_message, session_id=session_id)
        if long_safety.is_crisis or long_safety.category in (
            SafetyRiskCategory.REPORTED_THREAT_TO_OTHERS,
            SafetyRiskCategory.THIRD_PARTY_REPORT,
        ):
            risk_label = "HIGH_CRISIS" if long_safety.category == SafetyRiskCategory.SELF_HARM_RISK else long_safety.category.value
            if session_id and long_safety.is_crisis:
                set_session_risk_state(session_id, user_id, "crisis_active", risk_label)
            if user_id and long_safety.is_crisis:
                try:
                    update_user_profile(user_id, {"inc_crisis": True})
                except Exception:
                    pass
            log_safety_event_async(
                tier=1,
                rule_or_model="safety_classifier:max_length_gate",
                category=long_safety.category.value if hasattr(long_safety.category, "value") else str(long_safety.category),
                action_taken="hotline_shown_LLM_bypassed" if long_safety.is_crisis else "guidance_shown",
                message=user_message,
                session_id=session_id,
                user_id=user_id,
                confidence=long_safety.confidence,
                sync=bool(app.config.get("TESTING")),
            )
            return jsonify({
                "success": True,
                "status": "success",
                "risk_level": risk_label,
                "requires_immediate_action": long_safety.is_crisis,
                "data": {
                    "reply": long_safety.safety_message,
                    "is_crisis": long_safety.is_crisis,
                    "risk_level": risk_label,
                    "classification": risk_label,
                    "category": long_safety.category.value if hasattr(long_safety.category, "value") else str(long_safety.category),
                    "safety_message": long_safety.safety_message,
                    "status": "success",
                    "disclaimer": SAFETY_DISCLAIMER,
                    "emergency_resources": get_resources_for_region("pakistan"),
                    "requires_immediate_action": long_safety.is_crisis,
                    "session_id": session_id,
                },
                "error": None
            }), 200
        return jsonify({"success": False, "data": None, "error": {"code": "MESSAGE_TOO_LONG", "message": f"Message exceeds maximum allowed length ({MAX_MESSAGE_LENGTH} characters)."}}), 400

    # Retention and Regional Settings
    retention_enabled = True
    retention_days = 30
    expires_at = None
    user_locale = "pakistan"

    if user_id:
        user = get_user_by_id(user_id)
        if user:
            settings = user.get("settings", {})
            retention_enabled = bool(settings.get("retention_enabled", True))
            retention_days = int(settings.get("retention_days", 30))
            user_locale = "pakistan"
            if retention_enabled:
                expires_at = datetime.utcnow() + timedelta(days=retention_days)

    # --- Context-aware counselor context (built AFTER session creation) ---
    user_context = ""
    is_new_session = False

    regional_resources = get_resources_for_region(user_locale)

    try:
        is_new_session = not session_id
        if not session_id:
            if user_id:
                session_id = create_chat_session(user_id, user_message[:60])["id"]
            else:
                session_id = f"ses-{uuid.uuid4().hex[:12]}"

        # Build user_context only now that we know if this is a new session
        if user_id:
            try:
                profile = get_or_create_user_profile(user_id)
                mood_summary = get_mood_summary_for_chat(user_id)
                context_parts = []
                if profile.get("preferred_name"):
                    context_parts.append(f"The person's name is {profile['preferred_name']}.")
                actual_sessions = get_db().chat_sessions.count_documents({"user_id": user_id})
                if is_new_session and actual_sessions > 1:
                    context_parts.append("They are a returning user. Welcome them back warmly without mentioning any session numbers or counts.")
                if profile.get("crisis_count", 0) > 0 and is_new_session:
                    context_parts.append(
                        f"They have reached out during {profile['crisis_count']} previous crisis moment(s) "
                        "and came back — acknowledge their courage if natural."
                    )
                if is_new_session and profile.get("last_topic"):
                    context_parts.append(f"Last session they talked about: {profile['last_topic']}.")
                if mood_summary:
                    context_parts.append(f"Mood context: {mood_summary}.")
                user_context = " ".join(context_parts)
            except Exception:
                user_context = ""

        logger.info(f"[{req_id}] Processing message length={len(user_message)} chars (user_id={user_id})")

        # Capture prior user-only context BEFORE persisting current turn
        recent_context = []
        if user_id and retention_enabled:
            history_before_current = get_chat_history(user_id, session_id=session_id, limit=10)
            recent_context = [
                msg.get("text", "")
                for msg in history_before_current
                if isinstance(msg.get("text"), str)
                and msg.get("text")
                and msg.get("sender") == "user"
            ][-3:]

        # This release classifies English and Roman Urdu only. Do this scope
        # check before any safety, ML, or generative model call so native Urdu
        # and other unsupported scripts receive a transparent local check-in
        # instead of an unreliable classification result.
        language_route, _ = route_language_scope(user_message)
        if language_route in (ROUTE_ARABIC_SCRIPT, ROUTE_UNSUPPORTED_SCRIPT):
            duration_ms = round((time.time() - start_req_time) * 1000, 2)
            scope_reply = (
                "We may not fully understand this language yet, but we're glad you reached out. "
                "If you are struggling or feel unsafe, please contact someone you trust or local emergency support right now."
            )
            logger.info(f"[{req_id}] Unsupported-script check-in returned without model inference. Duration={duration_ms}ms")
            save_audit_event(
                "unsupported_script_checkin",
                user_id,
                {"request_id": req_id, "route": language_route},
            )
            return jsonify({
                "success": True,
                "status": "success",
                "risk_level": "script_checkin",
                "requires_immediate_action": False,
                "data": {
                    "status": "success",
                    "risk_level": "script_checkin",
                    "reply": scope_reply,
                    "disclaimer": SAFETY_DISCLAIMER,
                    "intent": "UNSUPPORTED_LANGUAGE_CHECKIN",
                    "emotion": "UNKNOWN",
                    "sentiment": "NEUTRAL",
                    "emergency_resources": regional_resources,
                    "requires_immediate_action": False,
                    "session_id": session_id,
                    "latency_ms": duration_ms,
                    "inference_latency_ms": duration_ms,
                },
                "error": None,
            }), 200

        # Save user message
        if user_id and retention_enabled:
            save_chat_message(user_id=user_id, sender="user", text=user_message, session_id=session_id, expires_at=expires_at)
            if session_id:
                update_chat_session(session_id, user_id, {"last_message_at": time.strftime("%Y-%m-%dT%H:%M:%S")})

        # -------------------------------------------------------------------
        # Step 0: Check Active Session Crisis State Machine
        # -------------------------------------------------------------------
        session_risk = get_session_risk_state(session_id, user_id)
        is_session_crisis_active = session_risk.get("risk_state") == "crisis_active"

        # -------------------------------------------------------------------
        # Step 1: Tier 1 - Unified Deterministic Safety, Threat & Rules Pipeline
        # -------------------------------------------------------------------
        if USE_UNIFIED_CRISIS_PIPELINE:
            unified_eval = evaluate_unified_tier1_safety(
                user_message,
                session_id=session_id,
                context_turns=recent_context,
                user_api_key=user_api_key,
            )
            safety_eval = unified_eval
            crisis_eval = unified_eval
        else:
            safety_eval = classify_safety_risk(
                user_message,
                context_turns=recent_context,
                api_key=user_api_key,
                session_id=session_id,
            )
            crisis_eval = evaluate_crisis_pipeline(
                user_message,
                allow_ml_fallback=False,
                context_turns=recent_context,
            )

        # 1A. Deterministic Acute Crisis (Self-Harm, Harm-to-Others, Combined, Threat-Against-User)
        is_tier1_crisis = False
        tier1_risk_label = "HIGH_CRISIS"
        tier1_safety_msg = ""
        tier1_signals = []
        tier1_source = "safety_classifier"
        tier1_conf = 0.98

        if safety_eval.category in (
            SafetyRiskCategory.COMBINED_HIGH_CRISIS,
            SafetyRiskCategory.THREAT_AGAINST_USER,
            SafetyRiskCategory.HARM_TO_OTHERS_RISK,
            SafetyRiskCategory.SELF_HARM_RISK,
        ):
            is_tier1_crisis = True
            tier1_risk_label = "HIGH_CRISIS" if safety_eval.category == SafetyRiskCategory.SELF_HARM_RISK else safety_eval.category.value
            tier1_safety_msg = safety_eval.safety_message
            tier1_signals = safety_eval.matched_signals
            tier1_source = "safety_classifier"
            tier1_conf = safety_eval.confidence
        elif crisis_eval.get("is_crisis"):
            is_tier1_crisis = True
            eval_risk = crisis_eval.get("risk_level")
            tier1_risk_label = eval_risk if eval_risk in ("THREAT_AGAINST_USER", "HARM_TO_OTHERS_RISK", "COMBINED_HIGH_CRISIS") else ("HIGH_CRISIS" if crisis_eval.get("high_risk", True) else "ELEVATED_DISTRESS")
            tier1_safety_msg = crisis_eval.get("safety_message") or SAFETY_RESPONSE_TEMPLATE.strip()
            tier1_signals = crisis_eval.get("matched_categories", [])
            tier1_source = "crisis_rules"
            tier1_conf = crisis_eval.get("confidence", 0.98)

        if is_tier1_crisis:
            duration_ms = round((time.time() - start_req_time) * 1000, 2)
            logger.warning(
                f"[{req_id}] CRITICAL SAFETY RISK DETECTED via Tier 1: {tier1_risk_label}. "
                f"Bypassing all LLM and generative paths. Duration={duration_ms}ms"
            )

            if session_id:
                set_session_risk_state(session_id, user_id, "crisis_active", tier1_risk_label)

            if user_id:
                try:
                    update_user_profile(user_id, {
                        "inc_crisis": True,
                        "inc_harm_others": tier1_risk_label == "HARM_TO_OTHERS_RISK"
                    })
                except Exception:
                    pass

            if user_id and retention_enabled:
                save_chat_message(
                    user_id=user_id,
                    sender="assistant",
                    text=tier1_safety_msg,
                    risk_level=tier1_risk_label,
                    intent=f"SAFETY PROTOCOL - {tier1_risk_label}",
                    emotion="ACUTE_RISK",
                    sentiment="NEGATIVE",
                    session_id=session_id,
                    expires_at=expires_at
                )

            save_audit_event(
                "critical_safety_escalation",
                user_id,
                {"source": tier1_source, "request_id": req_id, "risk_category": tier1_risk_label}
            )

            norm_cat = "self-harm" if tier1_risk_label == "HIGH_CRISIS" else tier1_risk_label
            log_safety_event_async(
                tier=3 if any("semantic" in s for s in tier1_signals) else 1,
                rule_or_model=", ".join(tier1_signals) if tier1_signals else tier1_source,
                category=norm_cat,
                action_taken="hotline_shown_LLM_bypassed",
                message=user_message,
                session_id=session_id,
                user_id=user_id,
                confidence=tier1_conf,
                sync=bool(app.config.get("TESTING")),
            )

            return jsonify({
                "success": True,
                "status": "success",
                "risk_level": tier1_risk_label,
                "requires_immediate_action": True,
                "data": {
                    "status": "success",
                    "risk_level": tier1_risk_label,
                    "classification": tier1_risk_label,
                    "reply": tier1_safety_msg,
                    "disclaimer": SAFETY_DISCLAIMER,
                    "intent": f"SAFETY PROTOCOL - {tier1_risk_label}",
                    "emotion": "ACUTE_RISK",
                    "sentiment": "NEGATIVE",
                    "emergency_resources": regional_resources,
                    "requires_immediate_action": True,
                    "session_id": session_id,
                    "latency_ms": duration_ms,
                    "inference_latency_ms": duration_ms
                },
                "error": None
            }), 200

        # 1B. Third-Party Reporting Guidance
        is_third_party = False
        tp_risk_label = "THIRD_PARTY_REPORT"
        tp_safety_msg = ""
        tp_signals = []
        tp_source = "safety_classifier:third_party"
        tp_conf = 0.95

        if safety_eval.category in (
            SafetyRiskCategory.REPORTED_THREAT_TO_OTHERS,
            SafetyRiskCategory.THIRD_PARTY_REPORT,
        ):
            is_third_party = True
            tp_risk_label = safety_eval.category.value
            tp_safety_msg = safety_eval.safety_message
            tp_signals = safety_eval.matched_signals
            tp_source = "safety_classifier:third_party"
            tp_conf = safety_eval.confidence
        elif crisis_eval.get("is_third_party") or crisis_eval.get("risk_level") == "REPORTED_THREAT_TO_OTHERS":
            is_third_party = True
            tp_risk_label = crisis_eval.get("risk_level", "THIRD_PARTY_REPORT")
            tp_safety_msg = crisis_eval.get("safety_message") or THIRD_PARTY_GUIDANCE_TEMPLATE.strip()
            tp_signals = [str(crisis_eval.get("source") or "deterministic_pipeline:third_party")]
            tp_source = "crisis_rules:third_party"
            tp_conf = crisis_eval.get("confidence", 0.95)

        if is_third_party:
            duration_ms = round((time.time() - start_req_time) * 1000, 2)
            logger.info(f"[{req_id}] {tp_risk_label} DETECTED. Returning guidance panel. Duration={duration_ms}ms")

            if user_id and retention_enabled:
                save_chat_message(
                    user_id=user_id,
                    sender="assistant",
                    text=tp_safety_msg,
                    risk_level=tp_risk_label,
                    intent=f"SAFETY PROTOCOL - {tp_risk_label}",
                    emotion="CONCERN",
                    sentiment="NEUTRAL",
                    session_id=session_id,
                    expires_at=expires_at
                )

            save_audit_event(
                "third_party_report_guidance",
                user_id,
                {"source": tp_source, "request_id": req_id, "risk_category": tp_risk_label}
            )

            log_safety_event_async(
                tier=1,
                rule_or_model=", ".join(tp_signals) if tp_signals else tp_source,
                category=tp_risk_label,
                action_taken="guidance_shown",
                message=user_message,
                session_id=session_id,
                user_id=user_id,
                confidence=tp_conf,
                sync=bool(app.config.get("TESTING")),
            )

            return jsonify({
                "success": True,
                "status": "success",
                "risk_level": tp_risk_label,
                "requires_immediate_action": False,
                "data": {
                    "status": "success",
                    "risk_level": tp_risk_label,
                    "classification": tp_risk_label,
                    "reply": tp_safety_msg,
                    "disclaimer": SAFETY_DISCLAIMER,
                    "intent": f"SAFETY PROTOCOL - {tp_risk_label}",
                    "emotion": "CONCERN",
                    "sentiment": "NEUTRAL",
                    "emergency_resources": regional_resources,
                    "requires_immediate_action": False,
                    "session_id": session_id,
                    "latency_ms": duration_ms,
                    "inference_latency_ms": duration_ms
                },
                "error": None
            }), 200

        # -------------------------------------------------------------------
        # Step 2: Tier 2 & Tier 2.5 - ML Classification & LLM Crisis Verifier
        # -------------------------------------------------------------------
        pp_res = crisis_eval.get("preprocess_result")
        clean_user_message = pp_res.text if pp_res else user_message
        ml_results = analyze_user_message(clean_user_message, context_turns=recent_context)

        is_crisis_signal = (
            ml_results["intent"] == "SUICIDE CRISIS OR SELF HARM RISK"
            and not (crisis_eval.get("bypass_triggered") or (is_contextual_or_negated(clean_user_message) if not USE_UNIFIED_CRISIS_PIPELINE else False))
        )

        triage_level = "ELEVATED_DISTRESS" if safety_eval.category == SafetyRiskCategory.EMOTIONAL_DISTRESS else "LOW"

        verifier_res = None
        if is_crisis_signal:
            conf = float(ml_results.get("intent_confidence", 0.5))

            if conf >= 0.85:
                triage_level = "HIGH_CRISIS"
            elif conf >= 0.30:
                verifier_res = evaluate_llm_safety_guardrail(
                    user_text=clean_user_message,
                    context_turns=recent_context,
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
                    # Conservative fallback when verifier is offline/unreachable:
                    # Confirmed ML confidence >= 0.65 fails closed to HIGH_CRISIS
                    if conf >= 0.65:
                        logger.warning(f"[{req_id}] LLM verifier offline; failing closed on ML conf {conf:.2f} to HIGH_CRISIS")
                        triage_level = "HIGH_CRISIS"
                    else:
                        triage_level = "ELEVATED_DISTRESS"

        if triage_level == "HIGH_CRISIS":
            duration_ms = round((time.time() - start_req_time) * 1000, 2)
            logger.warning(f"[{req_id}] CRISIS DETECTED via Tier 2/2.5 Pipeline. Duration={duration_ms}ms")

            crisis_reply = crisis_eval.get("safety_message") or SAFETY_RESPONSE_TEMPLATE.strip()

            if session_id:
                set_session_risk_state(session_id, user_id, "crisis_active", "HIGH_CRISIS")

            if user_id and retention_enabled:
                save_chat_message(
                    user_id=user_id,
                    sender="assistant",
                    text=crisis_reply,
                    risk_level="HIGH_CRISIS",
                    intent=ml_results["intent"],
                    intent_confidence=ml_results["intent_confidence"],
                    emotion=ml_results["emotion"],
                    sentiment=ml_results["sentiment"],
                    session_id=session_id,
                    expires_at=expires_at
                )
            save_audit_event("crisis_detected", user_id, {"source": "ml_pipeline", "request_id": req_id, "risk_category": "HIGH_CRISIS"})
            is_verifier_crisis = bool(verifier_res and verifier_res.get("is_crisis", False))
            if is_verifier_crisis:
                t_val = 3
                m_val = "gemini_llm_guardrail"
                c_val = verifier_res.get("category") or "self-harm"
                conf_val = float(verifier_res.get("confidence") or ml_results.get("intent_confidence") or 0.90)
            else:
                t_val = 2
                m_val = "crisis_detector.joblib"
                c_val = "self-harm"
                conf_val = float(ml_results.get("intent_confidence", 0.85))

            log_safety_event_async(
                tier=t_val,
                rule_or_model=m_val,
                category=c_val,
                action_taken="hotline_shown_LLM_bypassed",
                message=user_message,
                session_id=session_id,
                user_id=user_id,
                confidence=conf_val,
                sync=bool(app.config.get("TESTING")),
            )

            return jsonify({
                "success": True,
                "status": "success",
                "risk_level": "HIGH_CRISIS",
                "requires_immediate_action": True,
                "data": {
                    "status": "success",
                    "risk_level": "HIGH_CRISIS",
                    "reply": crisis_reply,
                    "disclaimer": SAFETY_DISCLAIMER,
                    "intent": ml_results["intent"],
                    "intent_confidence": ml_results["intent_confidence"],
                    "emotion": ml_results["emotion"],
                    "sentiment": ml_results["sentiment"],
                    "emergency_resources": regional_resources,
                    "requires_immediate_action": True,
                    "session_id": session_id,
                    "latency_ms": duration_ms,
                    "inference_latency_ms": duration_ms
                },
                "error": None
            }), 200

        # -------------------------------------------------------------------
        # Step 3: Guarded Sticky Follow-up (Post-Triage)
        # Reached ONLY after both Tier 1 and Tier 2/2.5 have verified this turn is non-crisis.
        # If session is in crisis_active or user in cooling window, transition to elevated_monitoring.
        # -------------------------------------------------------------------
        user_cooling = bool(user_id and is_user_in_cooling_window(user_id))
        if is_session_crisis_active or user_cooling:
            duration_ms = round((time.time() - start_req_time) * 1000, 2)
            logger.info(f"[{req_id}] Guarded crisis follow-up turn (session_crisis={is_session_crisis_active}, user_cooling={user_cooling}). Transitioning to elevated_monitoring.")
            
            if session_id:
                set_session_risk_state(session_id, user_id, "elevated_monitoring", "ELEVATED_DISTRESS")

            guarded_reply = (
                "I hear you, and I want to make sure you are safe first. "
                "Even if you feel like stepping back or changing the topic from what you shared, please know that support is available 24/7. "
                "I am here with you — would you like to talk through how you are feeling, or try a calming grounding exercise together?"
            )

            if user_id and retention_enabled:
                save_chat_message(
                    user_id=user_id,
                    sender="assistant",
                    text=guarded_reply,
                    risk_level="ELEVATED_DISTRESS",
                    intent="CRISIS MONITORING FOLLOWUP",
                    intent_confidence=0.90,
                    emotion="DISTRESS",
                    sentiment="NEGATIVE",
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
                    "reply": guarded_reply,
                    "disclaimer": SAFETY_DISCLAIMER,
                    "intent": "CRISIS MONITORING FOLLOWUP",
                    "emotion": "DISTRESS",
                    "sentiment": "NEGATIVE",
                    "emergency_resources": regional_resources,
                    "requires_immediate_action": False,
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
                "If you feel at risk of acting on these thoughts, call Rescue 1122, go to the nearest hospital emergency department, or contact someone you trust.)*"
            )
            duration_ms = round((time.time() - start_req_time) * 1000, 2)

            if session_id:
                set_session_risk_state(session_id, user_id, "elevated_monitoring", "ELEVATED_DISTRESS")

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
                    "emergency_resources": regional_resources,
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
            api_key=user_api_key,
            user_context=user_context
        )

        duration_ms = round((time.time() - start_req_time) * 1000, 2)
        logger.info(f"[{req_id}] Processed non-crisis chat successfully. Duration={duration_ms}ms")

        # Update user profile: session count only on NEW sessions, topic always
        if user_id:
            try:
                profile_updates = {}
                if is_new_session:
                    profile_updates["inc_session"] = True
                if ml_results.get("intent") and ml_results["intent"] not in ("GREETING OR CASUAL CHAT", "BOT INFORMATION REQUEST"):
                    profile_updates["last_topic"] = ml_results["intent"].replace(" OR ", " / ").title()
                if profile_updates:
                    update_user_profile(user_id, profile_updates)
            except Exception:
                pass

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

        kb_match = INTENT_RESPONSES.get(ml_results.get("intent", ""), {})
        grounding_exercise = kb_match.get("grounding_exercise")

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
                "grounding_exercise": grounding_exercise,
                "emergency_resources": regional_resources if session_risk.get("risk_state") == "elevated_monitoring" else None,
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
# Session Safety Clear & Clearance Token Endpoints
# ---------------------------------------------------------------------------
@app.route("/api/chat/session/<session_id>/clearance-token", methods=["POST"])
@optional_jwt
def get_session_clearance_token(session_id):
    current_user = getattr(g, "current_user", None)
    caller_user_id = current_user["id"] if current_user else None
    session = get_db().chat_sessions.find_one({"id": session_id})
    if not session:
        return jsonify({"success": False, "error": "not_found", "message": "Session not found"}), 404
    if session.get("user_id"):
        if not caller_user_id or session["user_id"] != caller_user_id:
            return jsonify({"success": False, "error": "forbidden", "message": "Session ownership verification failed"}), 403
    effective_user_id = caller_user_id or "anonymous"
    token = generate_clearance_token(session_id, effective_user_id, JWT_SECRET_KEY)
    return jsonify({"success": True, "data": {"clearance_token": token}, "error": None}), 200


@app.route("/api/chat/session/<session_id>/safety-clear", methods=["POST"])
def clear_crisis_session(session_id):
    auth_header = request.headers.get("Authorization", "")
    token_str = auth_header.replace("Bearer ", "").strip() if auth_header.startswith("Bearer ") else ""
    body = request.get_json(silent=True) or {}
    clearance_token = body.get("clearance_token") or request.headers.get("X-Clearance-Token", "")
    resolution_type = body.get("resolution_type", "grounding_completed")

    user_id = None
    if token_str:
        try:
            payload, err = decode_token(token_str)
            if err or not payload:
                return jsonify({"success": False, "error": "unauthorized", "message": err or "Invalid token"}), 401
            user_id = payload.get("sub")
        except Exception as e:
            return jsonify({"success": False, "error": "unauthorized", "message": f"Invalid token: {e}"}), 401
    elif clearance_token:
        valid = verify_clearance_token(clearance_token, session_id, JWT_SECRET_KEY)
        if not valid:
            return jsonify({"success": False, "error": "unauthorized", "message": "Invalid or expired clearance token"}), 401
        parts = clearance_token.split(":")
        user_id = parts[1] if len(parts) >= 2 else None
    else:
        return jsonify({"success": False, "error": "unauthorized", "message": "Authentication required: provide Bearer JWT or X-Clearance-Token"}), 401

    try:
        res = clear_session_crisis_state(session_id, user_id, resolution_type=resolution_type)
        return jsonify({"success": True, "data": res, "error": None}), 200
    except KeyError:
        return jsonify({"success": False, "error": "not_found", "message": "Session not found"}), 404
    except PermissionError as pe:
        return jsonify({"success": False, "error": "forbidden", "message": str(pe)}), 403
    except ValueError as ve:
        return jsonify({"success": False, "error": "bad_request", "message": str(ve)}), 400


# ---------------------------------------------------------------------------
# Feedback & Safety Audit Telemetry
# ---------------------------------------------------------------------------
@app.route("/api/feedback", methods=["POST"])
@optional_jwt
def submit_feedback():
    body = request.get_json(silent=True) or {}
    rating = body.get("rating")
    feedback_type = body.get("type", "general")
    notes = str(body.get("notes", "")).strip()

    user_id = g.current_user["id"] if hasattr(g, "current_user") and g.current_user else None

    save_audit_event("safety_feedback", user_id, {
        "rating": rating,
        "type": feedback_type,
        "has_notes": bool(notes),
        "notes_length": len(notes)
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
    port = int(os.environ.get("FLASK_PORT", os.environ.get("PORT", 5000)))
    host = os.environ.get("FLASK_HOST", "127.0.0.1")
    debug_mode = FLASK_DEBUG or (FLASK_ENV == "development")
    use_reloader = FLASK_USE_RELOADER
    logger.info(f"MindGuard Backend Server starting on http://{host}:{port} (debug={debug_mode}, reloader={use_reloader})")
    app.run(host=host, port=port, debug=debug_mode, use_reloader=use_reloader)
