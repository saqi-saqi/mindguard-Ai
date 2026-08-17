import sys, os, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from server.app import app
except ImportError:
    from app import app



sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from server.app import app
except ImportError:
    from app import app



def test_rule_only_latency_under_threshold():
    """Send a simple non-crisis message and assert inference latency reported (smoke test)."""
    client = app.test_client()
    # Warm-up request to initialize in-memory singletons and avoid counting one-time cold-start latency
    client.post('/api/chat', json={'message': 'hello'})
    start = time.time()
    resp = client.post('/api/chat', json={'message': "I'm feeling anxious about exams."})
    duration = (time.time() - start) * 1000.0
    assert resp.status_code == 200
    data = resp.get_json()
    payload = data.get('data', {}) if isinstance(data.get('data'), dict) else data

    # Expect a latency field (inference or overall) to be present
    assert 'inference_latency_ms' in data or 'latency_ms' in data or 'latency_ms' in payload

    # Basic smoke assertion: end-to-end duration should be reasonably small (developer machine dependent)
    assert duration < 3500  # 3-second SRS target, with a small local-test allowance
