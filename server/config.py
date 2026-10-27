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
TRUSTED_PROXIES = [ip.strip() for ip in os.environ.get("TRUSTED_PROXIES", "").split(",") if ip.strip()]

# MongoDB Configuration
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://127.0.0.1:27017/mindguard_db")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "mindguard_db")
USE_MONGOMOCK = os.environ.get("USE_MONGOMOCK", "false").lower() in ("true", "1", "yes")

# Flask & Security Configuration
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev_secret_key_mindguard_2026")
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() in ("true", "1")
FLASK_USE_RELOADER = os.environ.get("FLASK_USE_RELOADER", "false").lower() in ("true", "1", "yes")
FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))
FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS", os.environ.get("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")).split(",")
RATE_LIMIT_REQUESTS = int(os.environ.get("RATE_LIMIT_REQUESTS", os.environ.get("RATE_LIMIT_PER_MINUTE", "60")))
RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get("RATE_LIMIT_WINDOW_SECONDS", "60"))
DEFAULT_RETENTION_DAYS = int(os.environ.get("DEFAULT_RETENTION_DAYS", "30"))
USE_GENERALIZER_PIPELINE = os.environ.get("USE_GENERALIZER_PIPELINE", "true").lower() in ("true", "1", "yes")
USE_UNIFIED_CRISIS_PIPELINE = os.environ.get("USE_UNIFIED_CRISIS_PIPELINE", "true").lower() in ("true", "1", "yes")
ENABLE_WELLBEING_MULTILABEL_MODEL = os.environ.get("ENABLE_WELLBEING_MULTILABEL_MODEL", "false").lower() in ("true", "1", "yes")

# Latency and Provider Configuration
DEMO_MODE = os.environ.get("DEMO_MODE", "false").lower() in ("true", "1", "yes")
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "ollama").lower()
GEMINI_PRIMARY_MODEL = os.environ.get("GEMINI_PRIMARY_MODEL", "gemini-flash-lite-latest")
GEMINI_TIMEOUT_SECONDS = max(10.0, float(os.environ.get("GEMINI_TIMEOUT_SECONDS", "10.0")))
OLLAMA_RESPONSE_TIMEOUT_SECONDS = float(os.environ.get("OLLAMA_RESPONSE_TIMEOUT_SECONDS", "20.0"))
SEMANTIC_SAFETY_TIMEOUT_SECONDS = max(10.0, float(os.environ.get("SEMANTIC_SAFETY_TIMEOUT_SECONDS", "10.0")))

# Groq Configuration
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
GROQ_TIMEOUT_SECONDS = float(os.environ.get("GROQ_TIMEOUT_SECONDS", "3.5"))
GROQ_MAX_TOKENS = int(os.environ.get("GROQ_MAX_TOKENS", "180"))

