import asyncio

import app.models
from app.db.base import Base
from app.db.session import engine


async def init_db():
    async with engine.begin() as connection:
        await connection.run_sync(
            Base.metadata.create_all
        )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(init_db())