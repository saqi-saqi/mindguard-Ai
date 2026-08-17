"""
auth.py
=======
Authentication and Security Module for MindGuard AI.
Handles bcrypt password hashing, JWT token generation/validation, and Flask route protection middleware.
"""

import os
from datetime import datetime, timedelta
from functools import wraps
from typing import Dict, Optional, Tuple
import bcrypt
import jwt
from flask import request, jsonify, g

from database import get_user_by_id

import secrets
import logging

logger = logging.getLogger("MindGuard-Auth")

KNOWN_DEV_SECRETS = {
    "mindguard-default-dev-jwt-secret-key-change-in-prod-2026",
    "mindguard-docker-jwt-secret-key-2026",
    "change-me",
    "secret",
    "dev-secret",
    "password",
    "12345678"
}

_raw_jwt_key = os.environ.get("JWT_SECRET_KEY", "").strip()
_flask_env = os.environ.get("FLASK_ENV", "development").lower()

if _flask_env == "production":
    if not _raw_jwt_key or _raw_jwt_key in KNOWN_DEV_SECRETS or len(_raw_jwt_key) < 32:
        raise RuntimeError(
            "FATAL SECURITY ERROR: JWT_SECRET_KEY is missing, weak (<32 chars), or set to a development default in production mode. "
            "Server startup halted. Set a strong, secure JWT_SECRET_KEY environment variable."
        )
    JWT_SECRET_KEY = _raw_jwt_key
else:
    if _raw_jwt_key and _raw_jwt_key not in KNOWN_DEV_SECRETS and len(_raw_jwt_key) >= 16:
        JWT_SECRET_KEY = _raw_jwt_key
    else:
        JWT_SECRET_KEY = secrets.token_hex(32)
        logger.warning(
            "JWT_SECRET_KEY is unset or using a default. Generated a temporary 256-bit in-memory secret key for development. "
            "Note: Server restarts will invalidate active dev JWT tokens."
        )

JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = int(os.environ.get("JWT_EXPIRATION_HOURS", "24"))


def hash_password(password: str) -> str:
    """Hashes a plain-text password using bcrypt."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Verifies a plain-text password against a stored bcrypt hash."""
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False


def generate_token(user_id: str, email: str, expires_in_hours: int = JWT_EXPIRATION_HOURS) -> str:
    """Generates a signed JWT access token for a user."""
    expiration = datetime.utcnow() + timedelta(hours=expires_in_hours)
    payload = {
        "sub": user_id,
        "email": email,
        "iat": datetime.utcnow(),
        "exp": expiration
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Tuple[Optional[Dict], Optional[str]]:
    """Decodes and validates a JWT access token."""
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload, None
    except jwt.ExpiredSignatureError:
        return None, "Token has expired. Please sign in again."
    except jwt.InvalidTokenError:
        return None, "Invalid authentication token."


def jwt_required(f):
    """Flask decorator enforcing JWT authentication on protected API endpoints."""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header or not auth_header.startswith("Bearer "):
            return jsonify({
                "success": False,
                "data": None,
                "error": {
                    "code": "UNAUTHORIZED",
                    "message": "Authentication required. Please provide a valid Bearer token."
                }
            }), 401

        token = auth_header.split(" ")[1]
        payload, error_msg = decode_token(token)

        if not payload:
            return jsonify({
                "success": False,
                "data": None,
                "error": {
                    "code": "INVALID_TOKEN",
                    "message": error_msg or "Invalid authentication token."
                }
            }), 401

        user = get_user_by_id(payload.get("sub"))
        if not user:
            return jsonify({
                "success": False,
                "data": None,
                "error": {
                    "code": "USER_NOT_FOUND",
                    "message": "User account associated with token no longer exists."
                }
            }), 401

        g.current_user = user
        return f(*args, **kwargs)

    return decorated


def admin_required(f):
    """Require a valid JWT for a user explicitly assigned the admin role."""
    @wraps(f)
    @jwt_required
    def decorated(*args, **kwargs):
        if g.current_user.get("role") != "admin":
            return jsonify({
                "success": False,
                "data": None,
                "error": {"code": "FORBIDDEN", "message": "Administrator access is required."}
            }), 403
        return f(*args, **kwargs)
    return decorated


def optional_jwt(f):
    """Flask decorator that attaches g.current_user if token is valid, but allows unauthenticated access."""
    @wraps(f)
    def decorated(*args, **kwargs):
        g.current_user = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            payload, _ = decode_token(token)
            if payload:
                user = get_user_by_id(payload.get("sub"))
                if user:
                    g.current_user = user
        return f(*args, **kwargs)

    return decorated
