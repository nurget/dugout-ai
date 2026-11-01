import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.kbo_official_season_pitcher import KboOfficialSeasonPitcher
from app.tools.pitcher_comparison import (
    compare_pitchers_tool,
    search_season_pitchers_tool,
)


@pytest.mark.asyncio
async def test_official_pitcher_tools_apply_team_scope():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(
                Base.metadata.create_all,
                tables=[KboOfficialSeasonPitcher.__table__],
            )

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        async with session_factory() as session:
            session.add_all([
                KboOfficialSeasonPitcher(
                    season=2026,
                    season_type="REGULAR",
                    pitcher_id="HT-1",
                    pitcher_name="테스트 투수",
                    team_code="HT",
                    games=10,
                    batters_faced=100,
                    strikeouts=25,
                    walks=5,
                    k_pct=25.0,
                    bb_pct=5.0,
                    k_minus_bb_pct=20.0,
                ),
                KboOfficialSeasonPitcher(
                    season=2026,
                    season_type="REGULAR",
                    pitcher_id="HT-2",
                    pitcher_name="비교 투수",
                    team_code="HT",
                    games=10,
                    batters_faced=100,
                    strikeouts=20,
                    walks=10,
                    k_pct=20.0,
                    bb_pct=10.0,
                    k_minus_bb_pct=10.0,
                ),
                KboOfficialSeasonPitcher(
                    season=2026,
                    season_type="REGULAR",
                    pitcher_id="SS-1",
                    pitcher_name="테스트 투수",
                    team_code="SS",
                    games=10,
                    batters_faced=100,
                    strikeouts=30,
                    walks=5,
                    k_pct=30.0,
                    bb_pct=5.0,
                    k_minus_bb_pct=25.0,
                ),
            ])
            await session.commit()

            search = await search_season_pitchers_tool(
                session,
                season=2026,
                name="테스트",
                team="KIA",
            )
            assert [row["pitcher_id"] for row in search["pitchers"]] == [
                "HT-1"
            ]

            comparison = await compare_pitchers_tool(
                session,
                season=2026,
                first_pitcher_id="HT-2",
                second_pitcher_id="HT-1",
                team="KIA",
            )
            assert [
                row["pitcher_id"] for row in comparison["pitchers"]
            ] == ["HT-2", "HT-1"]
            assert comparison["k_minus_bb_pct_gap"] == -10.0
            assert comparison["higher_k_minus_bb_pitcher_id"] == "HT-1"
    finally:
        await engine.dispose()
