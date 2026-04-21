from __future__ import annotations

import structlog
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.keys import extract_prefix, lookup_by_prefix, verify_key
from app.db.models import ApiKey
from app.db.session import get_db

log = structlog.get_logger(__name__)


async def require_api_key(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> ApiKey:
    if not authorization:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="missing authorization header")

    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid authorization scheme")

    plaintext = parts[1].strip()
    prefix = extract_prefix(plaintext)
    if not prefix:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid api key")

    api_key = await lookup_by_prefix(db, prefix)
    if api_key is None or api_key.revoked_at is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid api key")

    if not verify_key(plaintext, api_key.key_hash):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid api key")

    request.state.api_key = api_key
    structlog.contextvars.bind_contextvars(api_key_id=str(api_key.id))
    return api_key


async def require_admin_key(api_key: ApiKey = Depends(require_api_key)) -> ApiKey:
    if not api_key.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="admin key required")
    return api_key
