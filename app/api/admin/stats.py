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


@router.get("/stats/latency")
async def latency(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT date_trunc('hour', created_at) AS t, "
                "percentile_cont(0.5) WITHIN GROUP (ORDER BY latency_ms) AS p50, "
                "percentile_cont(0.95) WITHIN GROUP (ORDER BY latency_ms) AS p95, "
                "percentile_cont(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99 "
                "FROM usage_logs "
                "WHERE created_at >= now() - interval '24 hours' "
                "AND status = 'success' "
                "GROUP BY t ORDER BY t"
            )
        )
    ).all()
    return {
        "series": [
            {
                "t": r[0].isoformat(),
                "p50": int(r[1] or 0),
                "p95": int(r[2] or 0),
                "p99": int(r[3] or 0),
            }
            for r in rows
        ]
    }


@router.get("/stats/errors")
async def errors(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT date_trunc('hour', created_at) AS t, "
                "count(*) FILTER (WHERE status='error') AS errors, "
                "count(*) FILTER (WHERE status='rate_limited') AS rate_limited, "
                "count(*) AS total "
                "FROM usage_logs "
                "WHERE created_at >= now() - interval '24 hours' "
                "GROUP BY t ORDER BY t"
            )
        )
    ).all()
    return {
        "series": [
            {
                "t": r[0].isoformat(),
                "errors": int(r[1] or 0),
                "rate_limited": int(r[2] or 0),
                "total": int(r[3] or 0),
                "error_rate": (float(r[1] or 0) / r[3]) if r[3] else 0.0,
            }
            for r in rows
        ]
    }


@router.get("/stats/tokens")
async def tokens_by_provider(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT date_trunc('day', created_at) AS d, provider, "
                "sum(total_tokens) AS tokens "
                "FROM usage_logs "
                "WHERE created_at >= now() - interval '7 days' "
                "AND provider NOT IN ('ratelimit') "
                "GROUP BY d, provider ORDER BY d, provider"
            )
        )
    ).all()
    by_day: dict[str, dict] = {}
    providers: set[str] = set()
    for day, provider, tokens in rows:
        key = day.isoformat()
        providers.add(provider)
        by_day.setdefault(key, {"d": key})[provider] = int(tokens or 0)
    # fill missing providers with 0 for nice stacked chart
    for day_bucket in by_day.values():
        for p in providers:
            day_bucket.setdefault(p, 0)
    return {
        "providers": sorted(providers),
        "series": sorted(by_day.values(), key=lambda x: x["d"]),
    }


@router.get("/stats/cost-by-key")
async def cost_by_key(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT k.name, k.key_prefix, "
                "coalesce(sum(u.cost_usd), 0) AS cost, "
                "coalesce(sum(u.total_tokens), 0) AS tokens, "
                "count(u.id) AS requests "
                "FROM api_keys k "
                "LEFT JOIN usage_logs u "
                "  ON u.api_key_id = k.id "
                "  AND u.created_at >= now() - interval '7 days' "
                "GROUP BY k.id, k.name, k.key_prefix "
                "ORDER BY cost DESC "
                "LIMIT 10"
            )
        )
    ).all()
    return {
        "rows": [
            {
                "name": r[0],
                "prefix": r[1],
                "cost_usd": float(r[2] or 0),
                "tokens": int(r[3] or 0),
                "requests": int(r[4] or 0),
            }
            for r in rows
        ]
    }


@router.get("/stats/rate-limits")
async def rate_limits(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    rows = (
        await db.execute(
            text(
                "SELECT date_trunc('hour', created_at) AS t, count(*) AS rejections "
                "FROM usage_logs "
                "WHERE status = 'rate_limited' "
                "AND created_at >= now() - interval '24 hours' "
                "GROUP BY t ORDER BY t"
            )
        )
    ).all()
    return {
        "series": [{"t": r[0].isoformat(), "rejections": int(r[1])} for r in rows]
    }
