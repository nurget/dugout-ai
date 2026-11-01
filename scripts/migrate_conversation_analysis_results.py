"""Add persisted structured analysis results to existing conversation tables."""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import inspect, text

# `python scripts/...`로 실행해도 프로젝트 패키지를 찾도록 한다.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.session import engine


async def migrate() -> None:
    async with engine.begin() as connection:
        columns = await connection.run_sync(
            lambda sync_connection: {
                column["name"]
                for column in inspect(sync_connection).get_columns(
                    "conversation_messages"
                )
            }
        )

        if "analysis_results" not in columns:
            await connection.execute(
                text(
                    "ALTER TABLE conversation_messages "
                    "ADD COLUMN analysis_results JSON"
                )
            )

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(migrate())
