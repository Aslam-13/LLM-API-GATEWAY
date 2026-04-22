from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_api_key
from app.config import get_settings
from app.db.models import ApiKey, Job, JobKind, JobStatus
from app.db.session import get_db
from app.deps import get_embedder
from app.providers.base import ProviderError
from app.ratelimit.sliding_window import check_and_consume
from app.worker.tasks import batch_embeddings_task

router = APIRouter(prefix="/v1", tags=["embeddings"])

MAX_SYNC_INPUTS = 100


class EmbeddingRequest(BaseModel):
    model: str | None = None
    input: list[str] | str


class BatchEmbeddingRequest(BaseModel):
    model: str | None = None
    input: list[str] = Field(min_length=1)
    provider: str = "gemini"


@router.post("/embeddings")
async def embeddings(
    body: EmbeddingRequest,
    api_key: ApiKey = Depends(require_api_key),
) -> dict:
    await check_and_consume(api_key)
    texts = [body.input] if isinstance(body.input, str) else body.input
    if not texts:
        raise HTTPException(status_code=400, detail="input empty")
    if len(texts) > MAX_SYNC_INPUTS:
        raise HTTPException(
            status_code=400,
            detail=f"use /v1/embeddings/batch for >{MAX_SYNC_INPUTS} inputs",
        )
    model = body.model or get_settings().embedding_model
    try:
        vectors = await get_embedder().embed(texts, model)
    except ProviderError as e:
        raise HTTPException(status_code=502, detail=f"embedder error: {e}") from e
    return {
        "object": "list",
        "model": model,
        "data": [
            {"object": "embedding", "index": i, "embedding": v}
            for i, v in enumerate(vectors)
        ],
    }


@router.post("/embeddings/batch", status_code=status.HTTP_202_ACCEPTED)
async def embeddings_batch(
    body: BatchEmbeddingRequest,
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await check_and_consume(api_key)
    if body.provider not in {"openai", "gemini"}:
        raise HTTPException(status_code=400, detail="provider must be openai or gemini")
    model = body.model or get_settings().embedding_model

    job = Job(
        api_key_id=api_key.id,
        kind=JobKind.batch_embeddings,
        status=JobStatus.pending,
        input={
            "model": model,
            "provider": body.provider,
            "count": len(body.input),
        },
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    batch_embeddings_task.delay(str(job.id), body.provider, model, body.input)

    return {"job_id": str(job.id), "status": job.status.value}
