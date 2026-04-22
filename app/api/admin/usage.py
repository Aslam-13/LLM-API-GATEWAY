from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_admin_key
from app.db.models import ApiKey, UsageLog
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/usage")
async def usage(
    api_key_id: UUID | None = None,
    from_: datetime | None = Query(default=None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if to is None:
        to = datetime.now(timezone.utc)
    if from_ is None:
        from_ = to - timedelta(days=7)

    filters = [UsageLog.created_at >= from_, UsageLog.created_at <= to]
    if api_key_id:
        filters.append(UsageLog.api_key_id == api_key_id)

    total = (
        await db.execute(select(func.count(UsageLog.id)).where(*filters))
    ).scalar_one()

    rows = (
        (
            await db.execute(
                select(UsageLog)
                .where(*filters)
                .order_by(UsageLog.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    agg = (
        await db.execute(
            select(
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.total_tokens), 0),
                func.coalesce(func.sum(UsageLog.cost_usd), 0.0),
                func.coalesce(func.avg(UsageLog.latency_ms), 0),
            ).where(*filters)
        )
    ).one()

    daily = (
        await db.execute(
            select(
                cast(UsageLog.created_at, Date).label("day"),
                func.count(UsageLog.id).label("requests"),
                func.coalesce(func.sum(UsageLog.total_tokens), 0).label("tokens"),
                func.coalesce(func.sum(UsageLog.cost_usd), 0.0).label("cost"),
            )
            .where(*filters)
            .group_by(cast(UsageLog.created_at, Date))
            .order_by("day")
        )
    ).all()

    return {
        "total": total,
        "aggregate": {
            "requests": agg[0],
            "tokens": int(agg[1]),
            "cost_usd": float(agg[2]),
            "avg_latency_ms": int(agg[3] or 0),
        },
        "daily": [
            {
                "day": r.day.isoformat(),
                "requests": r.requests,
                "tokens": int(r.tokens),
                "cost": float(r.cost),
            }
            for r in daily
        ],
        "rows": [
            {
                "id": r.id,
                "request_id": r.request_id,
                "api_key_id": str(r.api_key_id),
                "model": r.model,
                "provider": r.provider,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "total_tokens": r.total_tokens,
                "cost_usd": r.cost_usd,
                "latency_ms": r.latency_ms,
                "cache_hit": r.cache_hit.value,
                "status": r.status,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
