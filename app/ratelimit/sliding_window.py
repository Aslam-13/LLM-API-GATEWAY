from __future__ import annotations

from app.db.models import ApiKey


async def check_and_consume(api_key: ApiKey) -> None:
    """Stub — real sliding-window Redis limiter lands in Phase 11."""
    return
