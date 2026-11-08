from datetime import date

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.kbo import KboGame, KboTeam
from app.models.data_import_batch import DataImportBatch
from app.models.kbo_pitcher_appearance import KboPitcherAppearance
from app.services.as_of_pitcher import (
    compare_pitcher_stats_as_of,
    get_pitcher_stats_as_of,
)
from app.services.pitching_recommendation_integration import (
    compare_verified_bullpen_candidates,
)
from app.tools.pitcher_comparison import (
    compare_pitchers_tool,
    search_season_pitchers_tool,
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [
        KboTeam.__table__,
        DataImportBatch.__table__,
        KboGame.__table__,
        KboPitcherAppearance.__table__,
    ]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        session.add_all([
            KboTeam(code="HT", name="KIA"),
            KboTeam(code="SS", name="Samsung"),
        ])
        await session.commit()
        yield session
    await engine.dispose()


def add_game(session, game_pk, game_date, status="Final"):
    session.add(KboGame(
        game_pk=game_pk,
        season=2026,
        season_type="REGULAR",
        season_phase="REGULAR",
        game_date=date.fromisoformat(game_date),
        home_team_code="SS",
        away_team_code="HT",
        home_score=1,
        away_score=2,
        status=status,
        source_name="fixture",
    ))


def add_appearance(
    session,
    game_pk,
    *,
    pitcher_id="101",
    pitcher_name="투수 A",
    source="OFFICIAL_VERIFIED",
    order=1,
    bf=10,
    strikeouts=3,
    walks=1,
):
    session.add(KboPitcherAppearance(
        game_pk=game_pk,
        team_code="HT",
        appearance_order=order,
        pitcher_id=pitcher_id,
        pitcher_name=pitcher_name,
        pitcher_id_source=source,
        batters_faced=bf,
        strikeouts=strikeouts,
        walks=walks,
        pitches=30,
    ))


@pytest.mark.asyncio
async def test_as_of_stats_exclude_boundary_day_and_recompute_rates(db_session):
    add_game(db_session, "g1", "2026-06-01")
    add_game(db_session, "g2", "2026-06-02")
    add_game(db_session, "g3-dh1", "2026-06-03")
    add_game(db_session, "g3-dh2", "2026-06-03")
    add_appearance(db_session, "g1", bf=20, strikeouts=6, walks=2)
    add_appearance(db_session, "g2", bf=10, strikeouts=3, walks=1)
    # 당일 더블헤더 성적은 기준 시점에 포함하지 않는다.
    add_appearance(db_session, "g3-dh1", bf=100, strikeouts=90, walks=0)
    add_appearance(db_session, "g3-dh2", bf=100, strikeouts=90, walks=0)
    await db_session.commit()

    result = await get_pitcher_stats_as_of(
        db_session,
        season=2026,
        team_code="KIA",
        as_of_date=date(2026, 6, 3),
    )

    pitcher = result["pitchers"][0]
    assert result["coverage"] == {
        "status": "COMPLETE",
        "expected_final_games": 2,
        "games_with_appearance_data": 2,
        "missing_games": 0,
    }
    assert pitcher["games"] == 2
    assert pitcher["batters_faced"] == 30
    assert pitcher["strikeouts"] == 9
    assert pitcher["walks"] == 3
    assert pitcher["k_pct"] == 30.0
    assert pitcher["bb_pct"] == 10.0
    assert pitcher["k_minus_bb_pct"] == 20.0
    assert pitcher["data_through_date"] == "2026-06-02"
    assert result["provenance"]["status"] == "UNTRACKED"


@pytest.mark.asyncio
async def test_missing_game_appearance_marks_coverage_partial(db_session):
    add_game(db_session, "g1", "2026-06-01")
    add_game(db_session, "g2", "2026-06-02")
    add_appearance(db_session, "g1", pitcher_id="101")
    add_appearance(db_session, "g1", pitcher_id="102", pitcher_name="투수 B", order=2)
    await db_session.commit()

    result = await compare_pitcher_stats_as_of(
        db_session,
        season=2026,
        team_code="HT",
        as_of_date=date(2026, 6, 3),
        first_pitcher_id="101",
        second_pitcher_id="102",
    )

    assert result["coverage"]["status"] == "PARTIAL"
    assert result["comparison_status"] == "WITHHELD"
    assert result["coverage"]["missing_games"] == 1


@pytest.mark.asyncio
async def test_same_game_duplicate_name_is_withheld(db_session):
    add_game(db_session, "g1", "2026-06-01")
    add_appearance(db_session, "g1", pitcher_id="101", pitcher_name="동명이인", order=1)
    add_appearance(db_session, "g1", pitcher_id="202", pitcher_name="동명이인", order=2)
    await db_session.commit()

    result = await get_pitcher_stats_as_of(
        db_session,
        season=2026,
        team_code="HT",
        as_of_date=date(2026, 6, 2),
    )

    assert result["pitchers"] == []
    assert {row["pitcher_id"] for row in result["withheld"]} == {"101", "202"}


@pytest.mark.asyncio
async def test_invalid_box_score_values_are_withheld(db_session):
    add_game(db_session, "g1", "2026-06-01")
    add_appearance(db_session, "g1", source="TEAM_NAME_UNIQUE", bf=10, strikeouts=12)
    await db_session.commit()

    result = await get_pitcher_stats_as_of(
        db_session,
        season=2026,
        team_code="HT",
        as_of_date=date(2026, 6, 2),
    )

    assert result["pitchers"] == []
    assert result["withheld"][0]["pitcher_id"] == "101"
    assert "유효하지 않은" in result["withheld"][0]["reason"]


@pytest.mark.asyncio
async def test_zero_batter_appearance_does_not_distort_cumulative_rate(db_session):
    add_game(db_session, "g1", "2026-06-01")
    add_game(db_session, "g2", "2026-06-02")
    add_appearance(db_session, "g1", bf=0, strikeouts=0, walks=0)
    add_appearance(db_session, "g2", bf=10, strikeouts=3, walks=1)
    await db_session.commit()

    result = await get_pitcher_stats_as_of(
        db_session,
        season=2026,
        team_code="HT",
        as_of_date=date(2026, 6, 3),
    )

    assert result["pitchers"][0]["games"] == 2
    assert result["pitchers"][0]["batters_faced"] == 10
    assert result["pitchers"][0]["k_minus_bb_pct"] == 20.0


@pytest.mark.asyncio
async def test_unfinished_and_same_day_games_are_excluded(db_session):
    add_game(db_session, "g1", "2026-06-01")
    add_game(db_session, "g2", "2026-06-02")
    add_game(db_session, "g3", "2026-06-01", status="In Progress")
    add_appearance(db_session, "g1", pitcher_id="101")
    add_appearance(db_session, "g2", pitcher_id="202", pitcher_name="당일 투수")
    add_appearance(db_session, "g3", pitcher_id="303", pitcher_name="미종료 투수")
    await db_session.commit()

    result = await get_pitcher_stats_as_of(
        db_session,
        season=2026,
        team_code="HT",
        as_of_date=date(2026, 6, 2),
    )

    assert [row["pitcher_id"] for row in result["pitchers"]] == ["101"]
    assert result["coverage"]["expected_final_games"] == 1


@pytest.mark.asyncio
async def test_bullpen_candidate_comparison_uses_as_of_season_stats(db_session):
    add_game(db_session, "g1", "2026-06-01")
    add_game(db_session, "g2", "2026-06-02")
    add_appearance(
        db_session,
        "g1",
        pitcher_id="101",
        pitcher_name="투수 A",
        bf=100,
        strikeouts=30,
        walks=10,
    )
    add_appearance(
        db_session,
        "g2",
        pitcher_id="102",
        pitcher_name="투수 B",
        bf=100,
        strikeouts=20,
        walks=10,
    )
    await db_session.commit()

    result = await compare_verified_bullpen_candidates(
        db_session,
        season=2026,
        team_code="HT",
        as_of_date=date(2026, 6, 5),
        verified_candidate_ids=["101", "102"],
    )

    assert result["comparison_status"] == "COMPARABLE"
    assert result["coverage"]["status"] == "COMPLETE"
    assert [row["pitcher_id"] for row in result["ranking"]] == ["101", "102"]
    assert [row["k_minus_bb_pct"] for row in result["ranking"]] == [20.0, 10.0]


@pytest.mark.asyncio
async def test_search_and_pairwise_compare_use_only_as_of_appearances(db_session):
    add_game(db_session, "g1", "2026-06-01")
    add_game(db_session, "g2", "2026-06-02")
    add_appearance(
        db_session,
        "g1",
        pitcher_id="101",
        pitcher_name="기준일 투수 A",
        bf=100,
        strikeouts=30,
        walks=10,
    )
    add_appearance(
        db_session,
        "g2",
        pitcher_id="102",
        pitcher_name="기준일 투수 B",
        bf=100,
        strikeouts=20,
        walks=10,
    )
    # 기준일 당일의 성적은 시즌 전체 테이블과 유사한 미래 누수로 쓰면 안 된다.
    add_game(db_session, "g3", "2026-06-03")
    add_appearance(
        db_session,
        "g3",
        pitcher_id="101",
        pitcher_name="기준일 투수 A",
        bf=100,
        strikeouts=100,
        walks=0,
    )
    await db_session.commit()

    search = await search_season_pitchers_tool(
        db_session,
        season=2026,
        name="투수 A",
        team="KIA",
        as_of_date=date(2026, 6, 3),
    )
    comparison = await compare_pitchers_tool(
        db_session,
        season=2026,
        first_pitcher_id="101",
        second_pitcher_id="102",
        team="KIA",
        as_of_date=date(2026, 6, 3),
    )

    assert len(search["pitchers"]) == 1
    assert search["pitchers"][0]["k_minus_bb_pct"] == 20.0
    assert comparison["pitchers"][0]["k_minus_bb_pct"] == 20.0
    assert comparison["k_minus_bb_pct_gap"] == 10.0
