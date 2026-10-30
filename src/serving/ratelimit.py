import time


def check(store, consumer: str, rpm: int, now: float | None = None) -> tuple[bool, int]:
    """Fixed-window limiter. Returns (allowed, remaining)."""
    # ponytail: fixed window allows a 2x burst at window edges; use a sliding window if that matters
    window = int((now or time.time()) // 60)
    n = store.incr(f"rl:{consumer}:{window}", 60)
    return n <= rpm, max(0, rpm - n)
