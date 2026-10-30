import asyncio
import json

from app.db.session import AsyncSessionLocal, engine
from app.tools.registry import execute_tool

async def main():
    try:
        async with AsyncSessionLocal() as session:
            result = await execute_tool(
                session=session,
                tool_name="get_game_state",
                arguments={
                    "game_id": 1,
                    "state_id": 1,
                },
            )

            print(
                json.dumps(
                    result,
                    ensure_ascii=False,
                    indent=2,
                )
            )
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())