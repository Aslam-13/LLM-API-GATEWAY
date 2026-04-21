from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache.keys import last_user_message
from app.db.models import CachedResponse, SemanticCacheEntry
from app.providers.schemas import NormalizedRequest, NormalizedResponse


async def lookup(
    db: AsyncSession,
    model: str,
    embedding: list[float],
    threshold: float,
) -> tuple[NormalizedResponse, str, float] | None:
    # cosine distance = 1 - cosine similarity; hit when similarity > threshold → distance < (1 - threshold)
    max_dist = 1.0 - threshold
    dist = SemanticCacheEntry.embedding.cosine_distance(embedding).label("dist")
    stmt = (
        select(SemanticCacheEntry.request_hash, dist)
        .where(SemanticCacheEntry.model == model)
        .order_by(dist)
        .limit(1)
    )
    row = (await db.execute(stmt)).first()
    if row is None or row.dist > max_dist:
        return None

    cr = (
        await db.execute(
            select(CachedResponse).where(CachedResponse.request_hash == row.request_hash)
        )
    ).scalar_one_or_none()
    if cr is None:
        return None
    return NormalizedResponse.model_validate(cr.response), row.request_hash, float(row.dist)


async def store(
    db: AsyncSession,
    request_hash: str,
    req: NormalizedRequest,
    response: NormalizedResponse,
    embedding: list[float],
    ttl_seconds: int,
) -> None:
    expires = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    exists = (
        await db.execute(
            select(CachedResponse).where(CachedResponse.request_hash == request_hash)
        )
    ).scalar_one_or_none()
    if exists is None:
        db.add(
            CachedResponse(
                request_hash=request_hash,
                model=req.model,
                messages=[m.model_dump() for m in req.messages],
                response=response.model_dump(),
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
                expires_at=expires,
            )
        )
    db.add(
        SemanticCacheEntry(
            request_hash=request_hash,
            embedding=embedding,
            prompt_text=last_user_message(req) or "",
            model=req.model,
        )
    )
    await db.commit()
