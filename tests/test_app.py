import httpx
import pytest
from fastapi.testclient import TestClient

from serving import config as cfg
from serving.app import create_app
from serving.store import MemoryStore

OK = {"choices": [{"message": {"role": "assistant", "content": "Paris."}}],
      "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
BODY = {"messages": [{"role": "user", "content": "capital of France?"}]}
STREAM = (b'data: {"choices": [{"delta": {"content": "hi"}}]}\n\n'
          b'data: {"usage": {"prompt_tokens": 3, "completion_tokens": 1}}\n\ndata: [DONE]\n\n')


def make(handler, **kw):
    calls = []

    def wrapped(req):
        calls.append(req)
        return handler(req)

    client = httpx.AsyncClient(base_url="http://up", transport=httpx.MockTransport(wrapped))
    return TestClient(create_app(store=MemoryStore(), client=client, **kw)), calls


@pytest.fixture(autouse=True)
def _cfg(monkeypatch):
    monkeypatch.setattr(cfg, "API_KEYS", {"k1": ("team-a", 2)})
    monkeypatch.setattr(cfg, "UPSTREAM_KEY", "x")


def post(c, body=BODY, key="k1"):
    return c.post("/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"})


def test_bad_key_401():
    with make(lambda r: httpx.Response(200, json=OK))[0] as c:
        assert post(c, key="nope").status_code == 401


def test_second_identical_request_served_from_cache():
    c, calls = make(lambda r: httpx.Response(200, json=OK))
    with c:
        assert post(c).headers["X-Cache"] == "miss"
        assert post(c).headers["X-Cache"] == "hit-exact"
    assert len(calls) == 1


def test_rate_limit_429_with_retry_after():
    c, _ = make(lambda r: httpx.Response(200, json=OK))
    with c:
        post(c), post(c)
        r = post(c)
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"


def test_upstream_errors_map_to_clean_statuses():
    def boom(r):
        raise httpx.ReadTimeout("slow")

    with make(boom)[0] as c:
        assert post(c).status_code == 504
    with make(lambda r: httpx.Response(500))[0] as c:
        assert post(c).status_code == 502


def test_stream_passthrough():
    c, _ = make(lambda r: httpx.Response(200, content=STREAM))
    with c:
        r = post(c, {**BODY, "stream": True})
    assert r.status_code == 200 and "data: [DONE]" in r.text


def test_health_ready_metrics():
    with make(lambda r: httpx.Response(200, json=OK))[0] as c:
        assert c.get("/health").status_code == 200
        assert c.get("/ready").status_code == 200
        post(c)
        assert "llm_requests_total" in c.get("/metrics").text


def test_not_ready_without_upstream_key(monkeypatch):
    monkeypatch.setattr(cfg, "UPSTREAM_KEY", "")
    with make(lambda r: httpx.Response(200, json=OK))[0] as c:
        assert c.get("/ready").status_code == 503
