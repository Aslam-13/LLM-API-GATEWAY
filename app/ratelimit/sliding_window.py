from __future__ import annotations

import time
import uuid

import redis.asyncio as redis
from fastapi import HTTPException, status

from app.config import get_settings
from app.db.models import ApiKey
from app.metrics.prometheus import rate_limit_rejections_total

_client: redis.Redis | None = None
_KEY_PREFIX = "ratelimit"


def _get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def _count_in_window(r: redis.Redis, key: str, window_seconds: int) -> int:
    now_ms = int(time.time() * 1000)
    cutoff = now_ms - window_seconds * 1000
    pipe = r.pipeline(transaction=False)
    pipe.zremrangebyscore(key, 0, cutoff)
    pipe.zcard(key)
    results = await pipe.execute()
    return int(results[1])


async def _consume(r: redis.Redis, keys_with_ttl: list[tuple[str, int]], now_ms: int) -> None:
    member = f"{now_ms}-{uuid.uuid4().hex}"
    pipe = r.pipeline(transaction=False)
    for key, ttl in keys_with_ttl:
        pipe.zadd(key, {member: now_ms})
        pipe.expire(key, ttl)
    await pipe.execute()


async def check_and_consume(api_key: ApiKey) -> None:
    settings = get_settings()
    overrides = api_key.rate_limit_overrides or {}
    per_minute = int(overrides.get("per_minute", settings.rate_limit_requests_per_minute))
    per_day = int(overrides.get("per_day", settings.rate_limit_requests_per_day))

    r = _get_redis()
    key_id = str(api_key.id)
    minute_key = f"{_KEY_PREFIX}:{key_id}:minute"
    day_key = f"{_KEY_PREFIX}:{key_id}:day"

    # Gate both windows BEFORE consuming so one request equals one slot.
    if per_minute > 0:
        count = await _count_in_window(r, minute_key, 60)
        if count >= per_minute:
            rate_limit_rejections_total.labels(api_key_prefix=api_key.key_prefix).inc()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"rate limit exceeded: {per_minute}/minute",
                headers={"Retry-After": "60"},
            )
    if per_day > 0:
        count = await _count_in_window(r, day_key, 86400)
        if count >= per_day:
            rate_limit_rejections_total.labels(api_key_prefix=api_key.key_prefix).inc()
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"rate limit exceeded: {per_day}/day",
                headers={"Retry-After": "86400"},
            )

    now_ms = int(time.time() * 1000)
    await _consume(
        r,
        [(minute_key, 61), (day_key, 86401)],
        now_ms,
    )
