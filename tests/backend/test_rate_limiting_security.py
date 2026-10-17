"""
test_rate_limiting_security.py
==============================
Security and correctness regression tests for sliding-window rate limiting:
1. 60/61 boundary enforcement (60 requests return 200, 61st returns 429).
2. Direct client rate limiting via request.remote_addr.
3. Spoofed X-Forwarded-For headers from untrusted clients are NOT trusted.
4. Trusted proxy validation: only proxies configured in TRUSTED_PROXIES can forward client IPs.
5. Multiple comma-separated IPs in X-Forwarded-For parse the leftmost client IP.

Concurrency & Architectural Invariant:
MindGuard's in-memory rate limiting is per-process. In multi-worker deployments
(e.g., Gunicorn/uWSGI with multiple workers), a shared store (Redis/Memcached)
must be configured to enforce global limits across processes.
"""

from __future__ import annotations

import unittest
from unittest.mock import patch
from pathlib import Path
import sys

SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from app import app, reset_rate_limits, is_rate_limited, get_client_ip


class VirtualClock:
    def __init__(self, start=1000000.0):
        self.t = start

    def now(self):
        self.t += 0.001
        return self.t

    def advance(self, seconds):
        self.t += seconds


class TestRateLimitingSecurity(unittest.TestCase):
    """Validates rate limiting security boundaries, spoofing defenses, and proxy policies."""

    def setUp(self):
        self.app = app
        self.app.config["TESTING"] = True
        self.client = self.app.test_client()
        reset_rate_limits()

    def tearDown(self):
        reset_rate_limits()
        self.app.config["TRUSTED_PROXIES"] = []

    def test_rate_limit_60_allowed_61_blocked_boundary(self):
        """Boundary test: exactly 60 requests succeed in window; the 61st returns 429."""
        clock = VirtualClock()
        with patch("time.time", side_effect=clock.now):
            for i in range(60):
                res = self.client.post("/api/chat", json={"message": "hello"})
                self.assertEqual(res.status_code, 200, f"Request {i+1} failed unexpectedly")

            # 61st request in the same window must be blocked
            res_61 = self.client.post("/api/chat", json={"message": "hello"})
            self.assertEqual(res_61.status_code, 429)
            payload = res_61.get_json() or {}
            self.assertEqual(payload.get("error", {}).get("code"), "RATE_LIMIT_EXCEEDED")

            # After window expires (61s later), rate limit resets
            clock.advance(61.0)
            res_after_window = self.client.post("/api/chat", json={"message": "hello"})
            self.assertEqual(res_after_window.status_code, 200)

    def test_spoofed_x_forwarded_for_cannot_bypass_rate_limit(self):
        """Untrusted clients rotating X-Forwarded-For cannot bypass rate limiting."""
        self.app.config["TRUSTED_PROXIES"] = []  # Direct client, no proxies trusted
        clock = VirtualClock()

        with patch("time.time", side_effect=clock.now):
            # Attacker sends 60 requests with 60 different spoofed IPs from remote_addr 127.0.0.1
            for i in range(60):
                res = self.client.post(
                    "/api/chat",
                    json={"message": "hello"},
                    headers={"X-Forwarded-For": f"198.51.100.{i}"},
                    environ_base={"REMOTE_ADDR": "127.0.0.1"},
                )
                self.assertEqual(res.status_code, 200)

            # 61st request with yet another fake IP must be blocked based on true remote_addr (127.0.0.1)
            res_blocked = self.client.post(
                "/api/chat",
                json={"message": "hello"},
                headers={"X-Forwarded-For": "198.51.100.250"},
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
            )
            self.assertEqual(res_blocked.status_code, 429)
            self.assertEqual(res_blocked.get_json()["error"]["code"], "RATE_LIMIT_EXCEEDED")

    def test_trusted_proxy_forwarding_isolated_per_client(self):
        """When behind a trusted proxy, rate limits apply per client IP, not proxy IP."""
        self.app.config["TRUSTED_PROXIES"] = ["10.0.0.1"]
        clock = VirtualClock()

        with patch("time.time", side_effect=clock.now):
            # Client A sends 60 requests through proxy 10.0.0.1
            for i in range(60):
                res = self.client.post(
                    "/api/chat",
                    json={"message": "hello"},
                    headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.1"},
                    environ_base={"REMOTE_ADDR": "10.0.0.1"},
                )
                self.assertEqual(res.status_code, 200)

            # Client A request 61 is blocked
            res_blocked = self.client.post(
                "/api/chat",
                json={"message": "hello"},
                headers={"X-Forwarded-For": "203.0.113.10, 10.0.0.1"},
                environ_base={"REMOTE_ADDR": "10.0.0.1"},
            )
            self.assertEqual(res_blocked.status_code, 429)

            # Client B through the same proxy is NOT blocked
            res_client_b = self.client.post(
                "/api/chat",
                json={"message": "hello"},
                headers={"X-Forwarded-For": "203.0.113.20, 10.0.0.1"},
                environ_base={"REMOTE_ADDR": "10.0.0.1"},
            )
            self.assertEqual(res_client_b.status_code, 200)

    def test_multiple_forwarded_ips_extracts_leftmost(self):
        """X-Forwarded-For with multiple IPs correctly extracts the leftmost (original client)."""
        self.app.config["TRUSTED_PROXIES"] = ["10.0.0.1"]
        with self.app.test_request_context(
            "/api/chat",
            headers={"X-Forwarded-For": "198.51.100.42, 10.0.0.2, 10.0.0.1"},
            environ_base={"REMOTE_ADDR": "10.0.0.1"},
        ):
            from flask import request
            client_ip = get_client_ip(request)
            self.assertEqual(client_ip, "198.51.100.42")


if __name__ == "__main__":
    unittest.main()
