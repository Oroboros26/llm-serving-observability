"""Exact + semantic response cache. Only deterministic (temperature 0), non-streaming requests."""
import hashlib
import json


def _h(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode()).hexdigest()


def _text(payload: dict) -> str:
    return next((m["content"] for m in reversed(payload["messages"]) if m["role"] == "user"), "")


def _ctx(payload: dict) -> str:
    """Semantic hits are only allowed between requests with identical settings and system prompt."""
    system = [m for m in payload["messages"] if m["role"] == "system"]
    return _h({k: v for k, v in payload.items() if k != "messages"} | {"system": system})


def _single_turn(payload: dict) -> bool:
    return sum(m["role"] != "system" for m in payload["messages"]) == 1


def fastembed_embed():
    from fastembed import TextEmbedding

    model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(text: str) -> list[float]:
        v = next(iter(model.embed([text])))
        norm = sum(x * x for x in v) ** 0.5
        return [float(x) / norm for x in v]

    return embed


class Cache:
    def __init__(self, store, embed=None, threshold: float = 0.92, ttl: int = 3600):
        self.store, self.embed, self.threshold, self.ttl = store, embed, threshold, ttl

    def get(self, payload: dict) -> tuple[dict | None, str]:
        hit = self.store.get("ex:" + _h(payload))
        if hit:
            return json.loads(hit), "hit-exact"
        if self.embed and _single_turn(payload):
            q = self.embed(_text(payload))
            best, resp = 0.0, None
            # ponytail: linear scan over all entries of this context; use a vector index past ~10k entries
            for raw in self.store.hgetall("sem:" + _ctx(payload)).values():
                e = json.loads(raw)
                score = sum(a * b for a, b in zip(q, e["v"]))
                if score > best:
                    best, resp = score, e["r"]
            if best >= self.threshold:
                return resp, "hit-semantic"
        return None, "miss"

    def put(self, payload: dict, resp: dict) -> None:
        self.store.set("ex:" + _h(payload), json.dumps(resp), self.ttl)
        if self.embed and _single_turn(payload):
            text = _text(payload)
            # ponytail: semantic entries never expire; add a TTL or max size before long-running use
            self.store.hset("sem:" + _ctx(payload), _h(text),
                            json.dumps({"v": self.embed(text), "r": resp}))
