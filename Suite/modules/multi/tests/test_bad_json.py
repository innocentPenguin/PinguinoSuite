"""Write routes answer 400 (never 500) to bodies that are not JSON, not an object, or carry wrong-typed fields.
The exhaustive sweep over every route is tests/fuzz_post.py (slow, run by hand)."""
import re

import pytest
from fastapi.testclient import TestClient

import server

H = {"origin": "http://127.0.0.1:8766", "content-type": "application/json"}
ROUTES = ["/api/alerts/test", "/api/dev/inject", "/api/stream/schedule", "/api/stream/info", "/api/ding/reset",
          "/api/mod/ban", "/api/pins", "/api/assist/suggest", "/api/assist/translate", "/api/cards/manual", "/api/ding/settings"]
BODIES = [b"", b"{", b"null", b"[]", b'"x"', b"123", b"\xff\xfe", b"[1,2,3]", b"{}",
          b'{"amount": Infinity}', b'{"amount": "x"}', b'{"text": []}', b'{"type": []}', b'{"platforms": true}', b'{"card_id": 5}',
          b'{"message_id": 1000000000000000000000000000000}', b'{"message_id": []}', b'{"message_id": {}}', b'{"volume": Infinity}', b'{"master_volume": Infinity}']


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("MULTI_NO_SEND", "1")
    return TestClient(server.app, base_url="http://127.0.0.1:8766", raise_server_exceptions=False)


@pytest.mark.parametrize("body", BODIES, ids=lambda b: re.sub(r"\W+", "_", b.decode("latin1"))[:20] or "empty")
@pytest.mark.parametrize("route", ROUTES)
def test_bad_body_is_never_a_500(client, route, body):
    r = client.post(route, content=body, headers=H)
    assert r.status_code < 500, (route, body, r.status_code, r.text[:100])
