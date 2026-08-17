import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    import server.app as app_module
except ImportError:
    import app as app_module



def test_bypass_before_llm(monkeypatch):
    """Ensure deterministic crisis messages do not call the LLM generation step."""
    called = {"flag": False}

    def fake_generate(*args, **kwargs):
        called["flag"] = True
        return "SHOULD NOT BE_CALLED"

    # Patch the symbol actually used by the route module, not just the
    # originating service module.
    monkeypatch.setattr(app_module, "generate_llm_response", fake_generate)

    client = app_module.app.test_client()
    # This message is known to trigger the deterministic 'burden_and_goodbye' rule
    resp = client.post('/api/chat', json={'message': 'I wrote a goodbye note and deleted my accounts.'})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data.get('requires_immediate_action') is True
    assert called["flag"] is False
