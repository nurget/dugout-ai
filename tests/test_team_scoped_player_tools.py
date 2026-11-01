import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.player import Player
from app.tools.baseball import ToolNotFoundError, get_pitcher_status


@pytest.mark.asyncio
async def test_pitcher_status_is_limited_to_authenticated_team():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Player.__table__.create)

        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            kia_pitcher = Player(name="KIA 투수", team="KIA", position="P")
            other_pitcher = Player(name="타 구단 투수", team="SS", position="P")
            session.add_all([kia_pitcher, other_pitcher])
            await session.commit()

            result = await get_pitcher_status(
                session,
                player_id=kia_pitcher.id,
                authenticated_team_code="KIA",
            )
            assert result["player_id"] == kia_pitcher.id

            with pytest.raises(ToolNotFoundError):
                await get_pitcher_status(
                    session,
                    player_id=other_pitcher.id,
                    authenticated_team_code="KIA",
                )
    finally:
        await engine.dispose()
