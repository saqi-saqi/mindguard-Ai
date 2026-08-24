"""
config.py
---------
MindGuard Configuration Loader
Loads environment variables safely without hardcoded secrets.
"""

import os
from pathlib import Path

# Load from .env file if python-dotenv is installed
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)
except ImportError:
    pass

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
FLASK_ENV = os.environ.get("FLASK_ENV", "development")
MAX_MESSAGE_LENGTH = int(os.environ.get("MAX_MESSAGE_LENGTH", "2000"))
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "60"))

# MongoDB Configuration
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017/mindguard_db")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "mindguard_db")
USE_MONGOMOCK = os.environ.get("USE_MONGOMOCK", "false").lower() in ("true", "1", "yes")

# Flask & Security Configuration
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev_secret_key_mindguard_2026")
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")).split(",")
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", os.environ.get("RATE_LIMIT_PER_MINUTE", "60")))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
DEFAULT_RETENTION_DAYS = int(os.environ.get("DEFAULT_RETENTION_DAYS", "30"))
USE_GENERALIZER_PIPELINE = os.environ.get("USE_GENERALIZER_PIPELINE", "true").lower() in ("true", "1", "yes")

