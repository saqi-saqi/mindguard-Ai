"""Temporary test runner: injects .test-deps into sys.path for the vendor Python.

The bundled interpreter is an embeddable distribution (python._pth), which ignores
PYTHONPATH. This shim adds the local dependency folder before importing pytest.
Delete this file once a proper venv exists.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
DEPS = os.path.join(ROOT, ".test-deps")
if os.path.isdir(DEPS) and DEPS not in sys.path:
    sys.path.insert(0, DEPS)

# Keep server imports working exactly as the repo's conftest.py expects.
sys.path.insert(0, os.path.join(ROOT, "server"))
sys.path.insert(0, os.path.join(ROOT, "tests", "backend"))

import pytest  # noqa: E402

raise SystemExit(pytest.main(sys.argv[1:]))
