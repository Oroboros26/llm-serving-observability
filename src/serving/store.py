"""Tiny key-value interface so cache and rate limiter run on Redis or in memory (tests, dev)."""
import time

from . import config as cfg


class MemoryStore:
    def __init__(self):
        self.kv: dict[str, tuple[object, float]] = {}
        self.h: dict[str, dict[str, str]] = {}

    def get(self, k):
        v = self.kv.get(k)
        return v[0] if v and v[1] > time.time() else None

    def set(self, k, v, ttl):
        self.kv[k] = (v, time.time() + ttl)

    def incr(self, k, ttl):
        v = self.kv.get(k)
        if v is None or v[1] <= time.time():
            self.kv[k] = (1, time.time() + ttl)
            return 1
        self.kv[k] = (v[0] + 1, v[1])
        return v[0] + 1

    def hset(self, name, field, value):
        self.h.setdefault(name, {})[field] = value

    def hgetall(self, name):
        return dict(self.h.get(name, {}))

    def ping(self):
        return True


class RedisStore:
    # ponytail: sync redis client blocks the event loop for ~1 ms per call; use redis.asyncio at scale
    def __init__(self, url: str):
        import redis

        self.r = redis.Redis.from_url(url, decode_responses=True)

    def get(self, k):
        return self.r.get(k)

    def set(self, k, v, ttl):
        self.r.set(k, v, ex=ttl)

    def incr(self, k, ttl):
        p = self.r.pipeline()
        p.incr(k)
        p.expire(k, ttl, nx=True)  # nx needs Redis >= 7
        return p.execute()[0]

    def hset(self, name, field, value):
        self.r.hset(name, field, value)

    def hgetall(self, name):
        return self.r.hgetall(name)

    def ping(self):
        return self.r.ping()


def make_store():
    return RedisStore(cfg.REDIS_URL) if cfg.REDIS_URL else MemoryStore()
