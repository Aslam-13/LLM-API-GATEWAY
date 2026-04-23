from __future__ import annotations

import time
import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_api_key
from app.cache import exact as exact_cache
from app.cache import semantic as semantic_cache
from app.cache.keys import build_request_hash, last_user_message
from app.config import get_settings
from app.db.models import ApiKey, CacheHit, UsageLog
from app.db.session import get_db
from app.deps import get_embedder, get_router
from app.metrics import prometheus as m
from app.providers.base import ProviderError
from app.providers.pricing import estimate_cost
from app.providers.schemas import NormalizedRequest, NormalizedResponse
from app.ratelimit.sliding_window import check_and_consume

router = APIRouter(prefix="/v1", tags=["chat"])
log = structlog.get_logger(__name__)
ENDPOINT = "/v1/chat/completions"


@router.post("/chat/completions")
async def chat_completions(
    req: NormalizedRequest,
    request: Request,
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    request_id = uuid.uuid4().hex
    structlog.contextvars.bind_contextvars(request_id=request_id)
    start = time.perf_counter()
    settings = get_settings()

    try:
        await check_and_consume(api_key)
    except HTTPException as e:
        if e.status_code == 429:
            await _log_usage(
                db, api_key, request_id, req.model, "ratelimit",
                0, 0, 0.0, int((time.perf_counter() - start) * 1000),
                CacheHit.none, "rate_limited", str(e.detail),
            )
        raise

    request_hash = build_request_hash(req)
    response: NormalizedResponse | None = None
    cache_hit_kind: CacheHit = CacheHit.none
    embedding: list[float] | None = None
    user_text: str | None = None

    # 1) exact cache
    cached = await exact_cache.get(request_hash)
    if cached is not None:
        response = cached
        cache_hit_kind = CacheHit.exact
        m.cache_exact_hits_total.inc()
    else:
        m.cache_exact_misses_total.inc()

    # 2) semantic cache
    if response is None and settings.semantic_cache_enabled:
        user_text = last_user_message(req)
        if user_text:
            embedder = get_embedder()
            try:
                vectors = await embedder.embed([user_text], settings.embedding_model)
                embedding = vectors[0] if vectors else None
            except Exception as e:
                log.warning("semantic.embed_failed", error=str(e), error_type=type(e).__name__)
                embedding = None
            if embedding is not None:
                hit = await semantic_cache.lookup(
                    db, req.model, embedding, settings.semantic_cache_threshold
                )
                if hit is not None:
                    response, _, dist = hit
                    cache_hit_kind = CacheHit.semantic
                    m.cache_semantic_hits_total.inc()
                    log.info("cache.semantic_hit", distance=dist, model=req.model)
                else:
                    m.cache_semantic_misses_total.inc()

    # 3) provider
    if response is None:
        router_ = get_router()
        try:
            response = await router_.complete(req)
        except ProviderError as e:
            latency_ms = int((time.perf_counter() - start) * 1000)
            provider_name = getattr(e, "provider", "unknown")
            m.provider_errors_total.labels(
                provider=provider_name, error_type=type(e).__name__
            ).inc()
            m.requests_total.labels(
                endpoint=ENDPOINT, status="error", provider=provider_name, cache_hit="none"
            ).inc()
            await _log_usage(
                db, api_key, request_id, req.model, provider_name,
                0, 0, 0.0, latency_ms, CacheHit.none, "error", str(e),
            )
            raise HTTPException(status_code=502, detail=f"provider error: {e}") from e

        # populate caches
        try:
            await exact_cache.set(request_hash, response, settings.cache_ttl_seconds)
        except Exception as e:
            log.warning("cache.exact_set_failed", error=str(e))
        if settings.semantic_cache_enabled and user_text and embedding is not None:
            try:
                await semantic_cache.store(
                    db, request_hash, req, response, embedding, settings.cache_ttl_seconds
                )
            except Exception as e:
                log.warning("cache.semantic_store_failed", error=str(e))

    # 4) usage log + metrics
    latency_ms = int((time.perf_counter() - start) * 1000)
    if cache_hit_kind == CacheHit.none:
        pt, ct = response.usage.prompt_tokens, response.usage.completion_tokens
        cost = estimate_cost(response.provider, response.model, pt, ct)
    else:
        pt = ct = 0
        cost = 0.0

    await _log_usage(
        db, api_key, request_id, response.model, response.provider,
        pt, ct, cost, latency_ms, cache_hit_kind, "success", None,
    )

    m.tokens_total.labels(provider=response.provider, kind="prompt").inc(pt)
    m.tokens_total.labels(provider=response.provider, kind="completion").inc(ct)
    m.cost_usd_total.labels(provider=response.provider, api_key_prefix=api_key.key_prefix).inc(cost)
    m.requests_total.labels(
        endpoint=ENDPOINT, status="success",
        provider=response.provider, cache_hit=cache_hit_kind.value,
    ).inc()
    m.request_duration_seconds.labels(endpoint=ENDPOINT).observe(time.perf_counter() - start)

    return _to_openai_shape(response, request_id, cache_hit_kind)


async def _log_usage(
    db: AsyncSession, api_key: ApiKey, request_id: str, model: str, provider: str,
    pt: int, ct: int, cost: float, latency_ms: int, hit: CacheHit, status: str, err: str | None,
) -> None:
    db.add(
        UsageLog(
            api_key_id=api_key.id,
            request_id=request_id,
            model=model,
            provider=provider,
            prompt_tokens=pt,
            completion_tokens=ct,
            total_tokens=pt + ct,
            cost_usd=cost,
            latency_ms=latency_ms,
            cache_hit=hit,
            status=status,
            error=err,
        )
    )
    await db.commit()


def _to_openai_shape(resp: NormalizedResponse, request_id: str, hit: CacheHit) -> dict:
    return {
        "id": resp.id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": resp.model,
        "provider": resp.provider,
        "x_request_id": request_id,
        "x_cache_hit": hit.value,
        "choices": [
            {
                "index": c.index,
                "message": c.message.model_dump(),
                "finish_reason": c.finish_reason,
            }
            for c in resp.choices
        ],
        "usage": resp.usage.model_dump(),
    }
