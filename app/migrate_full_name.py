"""Rename the existing users.first_name column without losing its contents."""
import asyncio

from sqlalchemy import text

from db.database import engine


async def migrate():
    try:
        async with engine.begin() as conn:
            await conn.execute(text("LOCK TABLE users IN ACCESS EXCLUSIVE MODE"))
            result = await conn.execute(text("""
                SELECT column_name FROM information_schema.columns
                WHERE table_schema = current_schema() AND table_name = 'users'
                  AND column_name IN ('first_name', 'full_name')
            """))
            columns = set(result.scalars())
            if columns == {'first_name'}:
                await conn.execute(text("ALTER TABLE users RENAME COLUMN first_name TO full_name"))
                print("Renamed users.first_name to users.full_name.")
            elif columns == {'full_name'}:
                print("users.full_name already exists; no changes made.")
            else:
                raise RuntimeError(
                    "Expected exactly one of users.first_name or users.full_name; "
                    "inspect the database before migrating. No changes were made."
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
