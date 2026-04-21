from __future__ import annotations

import argparse
import asyncio

from app.auth.keys import generate_key
from app.db.models import ApiKey
from app.db.session import AsyncSessionLocal


async def create(name: str, email: str | None, is_admin: bool) -> None:
    gen = generate_key()
    async with AsyncSessionLocal() as db:
        row = ApiKey(
            name=name,
            key_hash=gen.hash,
            key_prefix=gen.prefix,
            user_email=email,
            is_admin=is_admin,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)

    print("API key created.")
    print(f"  id:       {row.id}")
    print(f"  name:     {row.name}")
    print(f"  admin:    {row.is_admin}")
    print(f"  prefix:   {row.key_prefix}")
    print(f"  key:      {gen.plaintext}")
    print("Save the key now — it cannot be recovered.")


def main() -> None:
    p = argparse.ArgumentParser(description="Create an API key.")
    p.add_argument("--name", required=True)
    p.add_argument("--email", default=None)
    p.add_argument("--admin", action="store_true")
    args = p.parse_args()
    asyncio.run(create(args.name, args.email, args.admin))


if __name__ == "__main__":
    main()
