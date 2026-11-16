from datetime import date, datetime, timezone
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.data_import_batch import DataImportBatch
from app.models.kbo_plate_appearance import KboPlateAppearance
from app.models.kbo_pitch_event import KboPitchEvent
from app.services.pbp_season_stats import (
    get_team_batting_stats,
    get_team_pbp_pitching_stats,
    search_team_batters,
)


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [DataImportBatch.__table__, KboPlateAppearance.__table__, KboPitchEvent.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def add_pa(batch_id, game, day, number, event, *, batter="b1", pitcher="p1", batting_team="HT", fielding_team="LG"):
    return KboPlateAppearance(
        game_pk=game,
        season=2025,
        game_date=day,
        at_bat_number=number,
        inning=1,
        inning_topbot="top",
        batting_team_code=batting_team,
        fielding_team_code=fielding_team,
        batter_id=batter,
        batter_name="김타자" if batter == "b1" else "다른 타자",
        batter_stand="L",
        pitcher_id=pitcher,
        pitcher_name="이투수" if pitcher == "p1" else "다른 투수",
        event=event,
        source_batch_id=batch_id,
    )


def add_pitch(batch_id, game, day, number, *, pitch_type, speed, pitcher="p1"):
    return KboPitchEvent(
        season=2025,
        game_pk=game,
        game_date=day,
        inning=1,
        inning_topbot="top",
        at_bat_number=1,
        pitch_number=number,
        home_team_code="LG",
        away_team_code="HT",
        batter_id="b1",
        batter_name="김타자",
        pitcher_id=pitcher,
        pitcher_name="이투수",
        pitch_type=pitch_type,
        release_speed_kmh=speed,
        raw_payload={"pitch_type": pitch_type, "release_speed_kmh": speed},
        source_batch_id=batch_id,
    )


@pytest.fixture
def import_batch():
    return DataImportBatch(
        id="pbp-2025",
        dataset="kbo_plate_appearances",
        source_name="slothman3878/kbo_playbyplay@fixture",
        status="SUCCESS",
        freshness="UNKNOWN",
        season=2025,
        imported_at=datetime.now(timezone.utc),
        record_count=7,
        quality_summary={"date_min": "2025-04-01", "date_max": "2025-04-06"},
    )


@pytest.mark.asyncio
async def test_batter_line_calculates_basic_rates_and_excludes_cutoff_day(db_session, import_batch):
    db_session.add(import_batch)
    events = ["single", "double", "walk", "hit_by_pitch", "sac_fly", "strikeout"]
    for number, (day, event) in enumerate(zip(range(1, 7), events), start=1):
        db_session.add(add_pa(
            import_batch.id,
            f"game-{number}",
            date(2025, 4, day),
            number,
            event,
        ))
    # Other team's batter must not leak into the authenticated KIA team result.
    db_session.add(add_pa(
        import_batch.id, "other-team", date(2025, 4, 2), 1, "home_run",
        batter="b2", batting_team="LG", fielding_team="HT",
    ))
    await db_session.commit()

    result = await get_team_batting_stats(
        db_session,
        season=2025,
        team_code="KIA",
        as_of_date=date(2025, 4, 6),
    )

    assert result["stat_source"] == "PBP_DERIVED"
    assert result["snapshot_id"] == import_batch.id
    assert result["count"] == 1
    batter = result["data"][0]
    assert batter["plate_appearances"] == 5
    assert batter["at_bats"] == 2
    assert batter["hits"] == 2
    assert batter["total_bases"] == 3
    assert batter["batting_average"] == 1.0
    assert batter["on_base_percentage"] == 0.8
    assert batter["slugging_percentage"] == 1.5
    assert batter["ops"] == 2.3
    assert result["cutoff"] == "EXCLUSIVE"
    assert result["coverage"]["date_max"] == "2025-04-05"
    assert result["coverage"]["accepted_plate_appearances"] == 5


@pytest.mark.asyncio
async def test_full_batter_and_pitcher_lines_keep_pbp_labels(db_session, import_batch):
    db_session.add(import_batch)
    for number, event in enumerate(
        ["single", "double", "walk", "hit_by_pitch", "sac_fly", "strikeout"],
        start=1,
    ):
        db_session.add(add_pa(
            import_batch.id,
            f"game-{number}",
            date(2025, 4, number),
            number,
            event,
        ))
    db_session.add_all([
        add_pitch(import_batch.id, "game-1", date(2025, 4, 1), 1, pitch_type="FF", speed=150.0),
        add_pitch(import_batch.id, "game-1", date(2025, 4, 1), 2, pitch_type="SL", speed=151.0),
    ])
    await db_session.commit()

    batter_result = await get_team_batting_stats(
        db_session, season=2025, team_code="HT"
    )
    pitcher_result = await get_team_pbp_pitching_stats(
        db_session, season=2025, team_code="LG"
    )

    assert batter_result["data"][0]["batting_average"] == 0.667
    assert pitcher_result["stat_source"] == "PBP_DERIVED"
    pitcher = pitcher_result["data"][0]
    assert pitcher["batters_faced"] == 6
    assert pitcher["hits_allowed"] == 2
    assert pitcher["pitch_count"] == 2
    assert pitcher["avg_release_speed_kmh"] == 150.5
    assert pitcher["max_release_speed_kmh"] == 151.0
    assert pitcher["pitch_mix"] == {"FF": 1, "SL": 1}
    assert pitcher["walks"] == 1
    assert pitcher["strikeouts"] == 1
    assert pitcher["k_minus_bb_pct"] == 0.0
    assert any("ERA" in item for item in pitcher_result["limitations"])


@pytest.mark.asyncio
async def test_batter_search_requires_exclusive_same_season_cutoff(db_session, import_batch):
    db_session.add(import_batch)
    db_session.add(add_pa(
        import_batch.id, "game-1", date(2025, 4, 1), 1, "single"
    ))
    await db_session.commit()

    with pytest.raises(ValueError, match="기준일과 시즌"):
        await search_team_batters(
            db_session,
            season=2025,
            team_code="KIA",
            as_of_date=date(2024, 4, 2),
            name="김",
        )


@pytest.mark.asyncio
async def test_unknown_pbp_outcome_is_reported_and_not_counted_as_at_bat(db_session, import_batch):
    db_session.add(import_batch)
    db_session.add(add_pa(
        import_batch.id, "game-1", date(2025, 4, 1), 1, "future_event"
    ))
    await db_session.commit()

    result = await get_team_batting_stats(
        db_session,
        season=2025,
        team_code="KIA",
    )

    batter = result["data"][0]
    assert batter["plate_appearances"] == 1
    assert batter["at_bats"] == 0
    assert batter["batting_average"] is None
    assert batter["unclassified_outcomes"] == 1
