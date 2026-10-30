import os
from pathlib import Path


def _keys(raw: str) -> dict[str, tuple[str, int]]:
    """API_KEYS='name:key:rpm,...' -> {key: (name, rpm)}"""
    out = {}
    for item in filter(None, raw.split(",")):
        name, key, rpm = item.split(":")
        out[key] = (name, int(rpm))
    return out


UPSTREAM_URL = os.getenv("UPSTREAM_URL", "https://api.groq.com/openai/v1")
UPSTREAM_KEY = os.getenv("UPSTREAM_API_KEY") or os.getenv("GROQ_API_KEY", "")
MODEL = os.getenv("MODEL", "llama-3.3-70b-versatile")
REDIS_URL = os.getenv("REDIS_URL", "")  # empty = in-process store (dev/tests)

API_KEYS = _keys(os.getenv("API_KEYS", ""))  # empty = open dev mode
DEFAULT_RPM = int(os.getenv("DEFAULT_RPM", "600"))

TIMEOUT_S = float(os.getenv("UPSTREAM_TIMEOUT_S", "30"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "32"))
QUEUE_TIMEOUT_S = float(os.getenv("QUEUE_TIMEOUT_S", "2"))

SEMANTIC_CACHE = os.getenv("SEMANTIC_CACHE", "0") == "1"
SEMANTIC_THRESHOLD = float(os.getenv("SEMANTIC_THRESHOLD", "0.92"))
CACHE_TTL_S = int(os.getenv("CACHE_TTL_S", "3600"))

# Server-side system prompt (path relative to the working dir): the prompt under regression test in CI.
SYSTEM = Path(os.getenv("SYSTEM_PROMPT_FILE", "prompts/system_v1.txt")).read_text().strip()

# USD per 1M tokens; unverified placeholders, check the provider's pricing page
PRICE_IN = float(os.getenv("PRICE_IN_PER_M", "0.59"))
PRICE_OUT = float(os.getenv("PRICE_OUT_PER_M", "0.79"))
