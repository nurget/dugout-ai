import asyncio
from datetime import date

from sqlalchemy import select

from app.db.session import AsyncSessionLocal, engine
from app.models import Game, GameState, Player


async def seed():
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(
            select(Game.id).limit(1)
        )

        if existing is not None:
            print("경기 데이터가 이미 존재합니다.")
            return

        async with session.begin_nested():
            session.add_all([
                Player(
                    name="양현종",
                    team="KIA",
                    position="P",
                ),
                Player(
                    name="전상현",
                    team="KIA",
                    position="P",
                ),
            ])

            game = Game(
                home_team="KIA",
                away_team="삼성",
                game_date=date(2026, 10, 30),
            )

            session.add(game)
            await session.flush()

            session.add(
                GameState(
                    game_id=game.id,
                    inning=7,
                    outs=1,
                    pitch_count=95,
                )
            )

        await session.commit()

    print("샘플 데이터 생성 완료")


async def main():
    try:
        await seed()
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())