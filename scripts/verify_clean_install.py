"""
verify_clean_install.py
========================
Verifies clean installation of MindGuard backend dependencies.
Ensures that all runtime dependencies listed in server/requirements.txt can be imported,
and tests that the Flask application initializes cleanly and responds to /api/health.
"""

import sys
import os
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SERVER_DIR = ROOT_DIR / "server"
REQ_FILE = SERVER_DIR / "requirements.txt"

def main():
    print("=" * 80)
    print("      MINDGUARD CLEAN-INSTALL DEPENDENCY VERIFICATION")
    print("=" * 80)

    if not REQ_FILE.exists():
        print(f"[FAIL] Requirements file not found at {REQ_FILE}")
        sys.exit(1)

    print(f"[1] Inspecting requirements in {REQ_FILE}...")
    with open(REQ_FILE, 'r', encoding='utf-8') as f:
        reqs = [line.strip() for line in f if line.strip() and not line.startswith('#')]

    print(f"    Found {len(reqs)} declared requirements: {', '.join(reqs)}")

    # 2. Verify key runtime modules can be imported cleanly
    print("\n[2] Verifying module imports in Python runtime...")
    test_code = f"""
import sys
from pathlib import Path
sys.path.insert(0, r"{SERVER_DIR}")

import flask
import flask_cors
import pymongo
import mongomock
import werkzeug
import requests
import dotenv
import google.genai
import joblib

print("    All core runtime modules imported successfully!")

from app import app
client = app.test_client()
res = client.get('/api/health')
assert res.status_code == 200, f"Expected 200, got {{res.status_code}}"
data = res.get_json()
assert data.get('status') == 'ok' or data.get('success') == True, f"Unexpected health response: {{data}}"
print(f"    Flask /api/health test PASSED: {{data}}")
"""

    proc = subprocess.run([sys.executable, "-c", test_code], cwd=str(ROOT_DIR), capture_output=True, text=True)

    if proc.returncode == 0:
        print(proc.stdout)
        print("=" * 80)
        print("  CLEAN INSTALL VERIFICATION: SUCCESSFUL [PASS]")
        print("=" * 80 + "\n")
        sys.exit(0)
    else:
        print("[FAIL] Clean install verification failed:")
        print(proc.stderr or proc.stdout)
        print("=" * 80 + "\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
