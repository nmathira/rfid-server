"""Add reference_tag without guessing which existing names are tags."""
import asyncio

from sqlalchemy import text
from db.database import engine


async def migrate():
    try:
        async with engine.begin() as conn:
            await conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS reference_tag VARCHAR(4)"
            ))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
