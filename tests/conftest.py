"""
Test fixtures.

Integration tests hit the dev Postgres + Redis. To keep the user's seeded
api_keys intact, we only TRUNCATE volatile tables (usage_logs, jobs,
cached_responses, semantic_cache_entries) between tests and only clean up
test-scoped api_keys via fixtures.
"""
from __future__ import annotations

import os

# Force semantic cache off in tests (avoids embedder calls / quota).
os.environ["SEMANTIC_CACHE_ENABLED"] = "false"

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

import app.config  # noqa: E402

app.config.get_settings.cache_clear()

from app.auth.keys import generate_key  # noqa: E402
from app.cache.exact import get_redis  # noqa: E402
from app.db.models import ApiKey  # noqa: E402
from app.db.session import AsyncSessionLocal  # noqa: E402
from app.main import app as fastapi_app  # noqa: E402


@pytest_asyncio.fixture(autouse=True)
async def reset_state():
    # Wipe Redis (exact cache + rate limit windows)
    await get_redis().flushdb()
    async with AsyncSessionLocal() as db:
        await db.execute(
            text(
                "TRUNCATE usage_logs, jobs, semantic_cache_entries, cached_responses "
                "RESTART IDENTITY CASCADE"
            )
        )
        await db.commit()
    yield


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def test_key():
    gen = generate_key()
    row = ApiKey(name="pytest", key_hash=gen.hash, key_prefix=gen.prefix, is_admin=False)
    async with AsyncSessionLocal() as db:
        db.add(row)
        await db.commit()
        await db.refresh(row)
        key_id = row.id
    yield row, gen.plaintext
    async with AsyncSessionLocal() as db:
        await db.execute(text("DELETE FROM usage_logs WHERE api_key_id = :k"), {"k": str(key_id)})
        await db.execute(text("DELETE FROM jobs WHERE api_key_id = :k"), {"k": str(key_id)})
        await db.execute(text("DELETE FROM api_keys WHERE id = :k"), {"k": str(key_id)})
        await db.commit()
