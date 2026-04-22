from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.middleware import require_admin_key
from app.db.models import ApiKey, Job, JobStatus
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/jobs")
async def list_jobs(
    status_filter: JobStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, le=500),
    offset: int = 0,
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    filters = []
    if status_filter:
        filters.append(Job.status == status_filter)

    total = (
        await db.execute(select(func.count(Job.id)).where(*filters))
    ).scalar_one()

    rows = (
        (
            await db.execute(
                select(Job)
                .where(*filters)
                .order_by(Job.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )

    return {
        "total": total,
        "rows": [
            {
                "id": str(j.id),
                "api_key_id": str(j.api_key_id),
                "kind": j.kind.value,
                "status": j.status.value,
                "input": j.input,
                "error": j.error,
                "created_at": j.created_at.isoformat() if j.created_at else None,
                "started_at": j.started_at.isoformat() if j.started_at else None,
                "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            }
            for j in rows
        ],
    }
