from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_api_key
from app.db.models import ApiKey, Job
from app.db.session import get_db

router = APIRouter(prefix="/v1", tags=["jobs"])


def _serialize_job(job: Job, include_result: bool = True) -> dict:
    return {
        "id": str(job.id),
        "kind": job.kind.value,
        "status": job.status.value,
        "input": job.input,
        "result": job.result if include_result else None,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
    }


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: UUID,
    include_result: bool = Query(default=True),
    api_key: ApiKey = Depends(require_api_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    job = (
        await db.execute(select(Job).where(Job.id == job_id))
    ).scalar_one_or_none()
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    if job.api_key_id != api_key.id and not api_key.is_admin:
        raise HTTPException(status_code=403, detail="not your job")
    return _serialize_job(job, include_result=include_result)
