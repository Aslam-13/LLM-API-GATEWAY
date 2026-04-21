from __future__ import annotations

import redis.asyncio as redis

from app.config import get_settings
from app.providers.schemas import NormalizedResponse

_client: redis.Redis | None = None
_PREFIX = "cache:exact:"


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def get(request_hash: str) -> NormalizedResponse | None:
    raw = await get_redis().get(_PREFIX + request_hash)
    if raw is None:
        return None
    return NormalizedResponse.model_validate_json(raw)


async def set(request_hash: str, response: NormalizedResponse, ttl: int) -> None:
    await get_redis().setex(_PREFIX + request_hash, ttl, response.model_dump_json())
