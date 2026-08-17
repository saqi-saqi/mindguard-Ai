"""
conftest.py
===========
Pytest configuration for MindGuard test suite.
Dynamically sets up sys.path and mongomock environment flags before test collection.
"""

import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent
SERVER_DIR = ROOT_DIR / "server"
TESTS_BACKEND_DIR = ROOT_DIR / "tests" / "backend"

# Ensure server and tests/backend directories are on Python module search path
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))
if str(TESTS_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_BACKEND_DIR))
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Enforce in-memory mongomock for all tests so no live MongoDB server is required
os.environ["USE_MONGOMOCK"] = "true"
os.environ["FLASK_ENV"] = "testing"
