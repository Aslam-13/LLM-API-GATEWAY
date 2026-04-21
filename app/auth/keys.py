from __future__ import annotations

import secrets
from dataclasses import dataclass

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ApiKey

_pwd = CryptContext(schemes=["argon2"], deprecated="auto")

KEY_PREFIX = "sk-gw-live-"
_RANDOM_LEN = 32


@dataclass
class GeneratedKey:
    plaintext: str
    prefix: str
    hash: str


def generate_key() -> GeneratedKey:
    random = secrets.token_urlsafe(_RANDOM_LEN)[:_RANDOM_LEN]
    plaintext = f"{KEY_PREFIX}{random}"
    prefix = plaintext[: len(KEY_PREFIX) + 6]
    return GeneratedKey(plaintext=plaintext, prefix=prefix, hash=_pwd.hash(plaintext))


def verify_key(plaintext: str, key_hash: str) -> bool:
    try:
        return _pwd.verify(plaintext, key_hash)
    except Exception:
        return False


def extract_prefix(plaintext: str) -> str | None:
    if not plaintext.startswith(KEY_PREFIX):
        return None
    return plaintext[: len(KEY_PREFIX) + 6]


async def lookup_by_prefix(db: AsyncSession, prefix: str) -> ApiKey | None:
    result = await db.execute(select(ApiKey).where(ApiKey.key_prefix == prefix))
    return result.scalar_one_or_none()
