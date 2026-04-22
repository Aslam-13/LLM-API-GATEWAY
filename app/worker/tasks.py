from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import select

from app.db.models import Job, JobStatus
from app.db.session import AsyncSessionLocal, engine
from app.providers.gemini_provider import GeminiProvider
from app.providers.openai_provider import OpenAIProvider
from app.worker.celery_app import celery_app

log = structlog.get_logger(__name__)

# OpenAI allows up to 2048 inputs per embeddings call; Gemini embedding API is
# effectively per-item. We batch conservatively for both.
OPENAI_BATCH = 512
GEMINI_BATCH = 32


async def _run_batch_embeddings(
    job_id_str: str, provider_name: str, model: str, texts: list[str]
) -> None:
    async with AsyncSessionLocal() as db:
        job = (
            await db.execute(select(Job).where(Job.id == UUID(job_id_str)))
        ).scalar_one()
        job.status = JobStatus.running
        job.started_at = datetime.now(timezone.utc)
        await db.commit()

        try:
            if provider_name == "openai":
                provider = OpenAIProvider()
                batch_size = OPENAI_BATCH
            else:
                provider = GeminiProvider()
                batch_size = GEMINI_BATCH

            vectors: list[list[float]] = []
            total = len(texts)
            for i in range(0, total, batch_size):
                batch = texts[i : i + batch_size]
                log.info(
                    "batch_embeddings.progress",
                    job_id=job_id_str,
                    done=i,
                    total=total,
                )
                vectors.extend(await provider.embed(batch, model))

            job.result = {
                "model": model,
                "provider": provider_name,
                "count": len(vectors),
                "dimensions": len(vectors[0]) if vectors else 0,
                "vectors": vectors,
            }
            job.status = JobStatus.succeeded
            log.info("batch_embeddings.succeeded", job_id=job_id_str, count=len(vectors))
        except Exception as e:
            job.status = JobStatus.failed
            job.error = str(e)
            log.exception("batch_embeddings.failed", job_id=job_id_str)
        finally:
            job.finished_at = datetime.now(timezone.utc)
            await db.commit()


@celery_app.task(name="batch_embeddings", bind=True)
def batch_embeddings_task(
    self, job_id: str, provider: str, model: str, texts: list[str]
) -> dict:
    try:
        asyncio.run(_run_batch_embeddings(job_id, provider, model, texts))
    finally:
        # ensure asyncpg pool is released before the task worker exits / rotates
        try:
            asyncio.run(engine.dispose())
        except Exception:
            pass
    return {"job_id": job_id}
