import sys, os, re
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
try:
    from server.app import app
except ImportError:
    from app import app



def test_logs_do_not_contain_raw_message(caplog):
    """Verify that raw user message text is not present in application logs (redaction/privacy)."""
    client = app.test_client()
    test_msg = "I wrote a goodbye note and deleted my accounts."

    with caplog.at_level("INFO"):
        resp = client.post('/api/chat', json={'message': test_msg})
        assert resp.status_code == 200

    # The app logs metadata about message length but should not contain the full raw message
    logs = "\n".join(r.getMessage() for r in caplog.records)
    assert test_msg not in logs

    # Basic sanity: request_id should be present in logs
    assert re.search(r"req-[0-9a-f]{12}", logs) is not None
