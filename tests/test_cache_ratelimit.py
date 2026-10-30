from serving.cache import Cache
from serving.ratelimit import check
from serving.store import MemoryStore


def fake_embed(text: str) -> list[float]:
    return [1.0, 0.0] if "paris" in text.lower() else [0.0, 1.0]


def payload(text: str, **kw) -> dict:
    return {"model": "m", "temperature": 0, "max_tokens": 10,
            "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": text}], **kw}


def test_exact_hit_and_miss():
    c = Cache(MemoryStore())
    c.put(payload("hi"), {"a": 1})
    assert c.get(payload("hi")) == ({"a": 1}, "hit-exact")
    assert c.get(payload("hi", max_tokens=11))[1] == "miss"


def test_semantic_hit_only_for_similar_single_turn():
    c = Cache(MemoryStore(), embed=fake_embed)
    c.put(payload("capital of France? paris"), {"a": 1})
    assert c.get(payload("paris capital please")) == ({"a": 1}, "hit-semantic")
    assert c.get(payload("boiling point of water"))[1] == "miss"
    multi = payload("paris capital please")
    multi["messages"].insert(1, {"role": "assistant", "content": "earlier"})
    assert c.get(multi)[1] == "miss"


def test_rate_limit_window():
    s = MemoryStore()
    assert [check(s, "a", 2, now=0)[0] for _ in range(3)] == [True, True, False]
    assert check(s, "b", 2, now=0)[0]  # other consumer unaffected
    assert check(s, "a", 2, now=61)[0]  # new window
