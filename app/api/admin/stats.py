from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_admin_key
from app.db.models import ApiKey, CacheHit, UsageLog
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/stats/overview")
async def overview(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    hour_ago = now - timedelta(hours=1)

    totals = (
        await db.execute(
            select(
                func.count(UsageLog.id),
                func.coalesce(func.sum(UsageLog.cost_usd), 0.0),
                func.coalesce(func.sum(UsageLog.total_tokens), 0),
            ).where(UsageLog.created_at >= day_ago)
        )
    ).one()

    hits: dict[str, int] = {h.value: 0 for h in CacheHit}
    hit_rows = (
        await db.execute(
            select(UsageLog.cache_hit, func.count(UsageLog.id))
            .where(UsageLog.created_at >= day_ago)
            .group_by(UsageLog.cache_hit)
        )
    ).all()
    for kind, count in hit_rows:
        hits[kind.value] = count
    total_reqs = sum(hits.values())
    cache_hit_rate = (
        (hits["exact"] + hits["semantic"]) / total_reqs if total_reqs > 0 else 0.0
    )

    p95_row = (
        await db.execute(
            text(
                "SELECT percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) "
                "FROM usage_logs WHERE created_at >= :since AND status = 'success'"
            ),
            {"since": day_ago},
        )
    ).scalar_one_or_none()

    per_minute = (
        await db.execute(
            select(
                func.date_trunc("minute", UsageLog.created_at).label("minute"),
                func.count(UsageLog.id).label("count"),
            )
            .where(UsageLog.created_at >= hour_ago)
            .group_by("minute")
            .order_by("minute")
        )
    ).all()

    hourly_rows = (
        await db.execute(
            select(
                func.date_trunc("hour", UsageLog.created_at).label("hour"),
                UsageLog.cache_hit,
                func.count(UsageLog.id).label("count"),
            )
            .where(UsageLog.created_at >= day_ago)
            .group_by("hour", UsageLog.cache_hit)
            .order_by("hour")
        )
    ).all()
    hourly_map: dict[str, dict] = {}
    for hour, hit, cnt in hourly_rows:
        key = hour.isoformat()
        if key not in hourly_map:
            hourly_map[key] = {"hour": key, "none": 0, "exact": 0, "semantic": 0}
        hourly_map[key][hit.value] = cnt

    return {
        "totals_24h": {
            "requests": totals[0],
            "cost_usd": float(totals[1]),
            "tokens": int(totals[2]),
            "cache_hit_rate": float(cache_hit_rate),
            "p95_latency_ms": int(p95_row or 0),
        },
        "cache_breakdown_24h": hits,
        "requests_per_minute_1h": [
            {"minute": r.minute.isoformat(), "count": r.count} for r in per_minute
        ],
        "cache_hourly_24h": sorted(hourly_map.values(), key=lambda x: x["hour"]),
    }
