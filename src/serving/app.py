"""OpenAI-compatible /v1/chat/completions in front of any OpenAI-compatible upstream (Groq, vLLM)."""
import asyncio
import json
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from pydantic import BaseModel

from . import config as cfg
from . import metrics as m
from .cache import Cache, fastembed_embed
from .ratelimit import check
from .store import make_store


class Chat(BaseModel):
    messages: list[dict]
    temperature: float = 0  # default 0 so responses are cacheable
    max_tokens: int = 512
    stream: bool = False


def auth(authorization: str | None = Header(None)) -> tuple[str, int]:
    if not cfg.API_KEYS:  # dev mode: no keys configured
        return "anon", cfg.DEFAULT_RPM
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token not in cfg.API_KEYS:
        raise HTTPException(401, "invalid api key")
    return cfg.API_KEYS[token]


def err(status: int, code: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code}}, status, headers=headers)


async def _relay(client, payload, consumer, t0, sem):
    usage, status = None, "200"
    try:
        body = {**payload, "stream": True, "stream_options": {"include_usage": True}}
        async with client.stream("POST", "/chat/completions", json=body) as r:
            r.raise_for_status()
            async for line in r.aiter_lines():
                if line.startswith("data: {"):
                    try:
                        usage = json.loads(line[6:]).get("usage") or usage
                    except ValueError:
                        pass
                yield line + "\n"
    except httpx.TimeoutException:
        status = "504"
        yield 'data: {"error": "upstream_timeout"}\n\n'
    except httpx.HTTPError:
        status = "502"
        yield 'data: {"error": "upstream_error"}\n\n'
    finally:
        sem.release()
        m.record(consumer, status, "miss", t0, usage)


def create_app(store=None, client=None, embed=None) -> FastAPI:
    store = store or make_store()
    if embed is None and cfg.SEMANTIC_CACHE:
        embed = fastembed_embed()
    cache = Cache(store, embed, cfg.SEMANTIC_THRESHOLD, cfg.CACHE_TTL_S)
    sem = asyncio.Semaphore(cfg.MAX_CONCURRENCY)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.client = client or httpx.AsyncClient(
            base_url=cfg.UPSTREAM_URL, timeout=cfg.TIMEOUT_S,
            headers={"Authorization": f"Bearer {cfg.UPSTREAM_KEY}"})
        yield
        if client is None:
            await app.state.client.aclose()

    app = FastAPI(title="llm-serving-observability", lifespan=lifespan)

    @app.post("/v1/chat/completions")
    async def chat(body: Chat, request: Request, who: tuple[str, int] = Depends(auth)):
        consumer, rpm = who
        t0 = time.perf_counter()
        ok, _ = check(store, consumer, rpm)
        if not ok:
            m.record(consumer, "429", "none", t0)
            return err(429, "rate_limit_exceeded", {"Retry-After": "60"})
        system = [{"role": "system", "content": cfg.SYSTEM}] if cfg.SYSTEM else []
        payload = {"model": cfg.MODEL, "messages": system + body.messages,
                   "temperature": body.temperature, "max_tokens": body.max_tokens}
        if not body.stream:
            hit, kind = cache.get(payload)
            if hit:
                m.record(consumer, "200", kind, t0)
                return JSONResponse(hit, headers={"X-Cache": kind})
        try:  # bounded wait for an upstream slot; shed load instead of queueing forever
            await asyncio.wait_for(sem.acquire(), cfg.QUEUE_TIMEOUT_S)
        except TimeoutError:
            m.record(consumer, "503", "none", t0)
            return err(503, "overloaded", {"Retry-After": "5"})
        up = request.app.state.client
        if body.stream:  # streaming bypasses the cache
            return StreamingResponse(_relay(up, payload, consumer, t0, sem),
                                     media_type="text/event-stream")
        try:
            r = await up.post("/chat/completions", json=payload)
            r.raise_for_status()
            data = r.json()
        except httpx.TimeoutException:
            m.record(consumer, "504", "none", t0)
            return err(504, "upstream_timeout")
        except httpx.HTTPError:
            m.record(consumer, "502", "none", t0)
            return err(502, "upstream_error")
        finally:
            sem.release()
        m.record(consumer, "200", "miss", t0, data.get("usage"))
        if body.temperature == 0:
            cache.put(payload, data)
        return JSONResponse(data, headers={"X-Cache": "miss"})

    @app.get("/health")
    def health():
        return {"ok": True}

    @app.get("/ready")
    def ready():
        try:
            store.ping()
        except Exception:  # noqa: BLE001 - readiness probe: any store failure means not ready
            return err(503, "store_unavailable")
        if not cfg.UPSTREAM_KEY:
            return err(503, "upstream_not_configured")
        return {"ready": True}

    @app.get("/metrics")
    def metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    return app
