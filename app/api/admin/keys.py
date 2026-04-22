from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.keys import generate_key
from app.auth.middleware import require_admin_key
from app.db.models import ApiKey, UsageLog
from app.db.session import get_db

router = APIRouter(prefix="/admin", tags=["admin"])


class KeyCreate(BaseModel):
    name: str
    email: str | None = None
    admin: bool = False


@router.get("/me")
async def me(admin: ApiKey = Depends(require_admin_key)) -> dict:
    return {
        "id": str(admin.id),
        "name": admin.name,
        "admin": admin.is_admin,
        "email": admin.user_email,
    }


@router.get("/keys")
async def list_keys(
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    rows = (
        (await db.execute(select(ApiKey).order_by(ApiKey.created_at.desc())))
        .scalars()
        .all()
    )
    last_used = (
        await db.execute(
            select(UsageLog.api_key_id, func.max(UsageLog.created_at)).group_by(
                UsageLog.api_key_id
            )
        )
    ).all()
    last_used_map = {row[0]: row[1] for row in last_used}
    return [
        {
            "id": str(k.id),
            "name": k.name,
            "prefix": k.key_prefix,
            "email": k.user_email,
            "admin": k.is_admin,
            "rate_limit_overrides": k.rate_limit_overrides,
            "created_at": k.created_at.isoformat() if k.created_at else None,
            "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
            "last_used_at": last_used_map[k.id].isoformat()
            if last_used_map.get(k.id)
            else None,
        }
        for k in rows
    ]


@router.post("/keys", status_code=201)
async def create_key(
    body: KeyCreate,
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    gen = generate_key()
    row = ApiKey(
        name=body.name,
        key_hash=gen.hash,
        key_prefix=gen.prefix,
        user_email=body.email,
        is_admin=body.admin,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return {
        "id": str(row.id),
        "name": row.name,
        "prefix": row.key_prefix,
        "email": row.user_email,
        "admin": row.is_admin,
        "plaintext": gen.plaintext,
        "created_at": row.created_at.isoformat(),
    }


@router.delete("/keys/{key_id}")
async def revoke_key(
    key_id: UUID,
    _admin: ApiKey = Depends(require_admin_key),
    db: AsyncSession = Depends(get_db),
) -> dict:
    row = (
        await db.execute(select(ApiKey).where(ApiKey.id == key_id))
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="key not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(timezone.utc)
        await db.commit()
    return {"id": str(row.id), "revoked_at": row.revoked_at.isoformat()}
