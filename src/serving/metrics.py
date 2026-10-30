import time

from prometheus_client import Counter, Histogram

from . import config as cfg

REQS = Counter("llm_requests_total", "Requests", ["consumer", "status", "cache"])
LAT = Histogram("llm_request_seconds", "End-to-end latency", ["consumer"],
                buckets=(.005, .01, .05, .1, .25, .5, 1, 2, 5, 10, 30))
TOK = Counter("llm_tokens_total", "Upstream tokens", ["consumer", "kind"])
COST = Counter("llm_cost_usd_total", "Estimated upstream spend", ["consumer"])


def record(consumer: str, status: str, cache: str, t0: float, usage: dict | None = None) -> None:
    REQS.labels(consumer, status, cache).inc()
    LAT.labels(consumer).observe(time.perf_counter() - t0)
    if usage:
        tin, tout = usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)
        TOK.labels(consumer, "in").inc(tin)
        TOK.labels(consumer, "out").inc(tout)
        COST.labels(consumer).inc((tin * cfg.PRICE_IN + tout * cfg.PRICE_OUT) / 1e6)
