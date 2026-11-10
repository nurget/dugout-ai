from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.data_import_batch import DataImportBatch
from app.models.kbo_pitcher_appearance import KboPitcherAppearance
from app.models.kbo_plate_appearance import KboPlateAppearance
from app.services.kbo_matchups import analyze_lineup_matchups, parse_complete_plate_appearances


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [DataImportBatch.__table__, KboPitcherAppearance.__table__, KboPlateAppearance.__table__]
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all, tables=tables)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


def pitch(game, ab, number, *, event, pitcher="p1", batter="b1", date_value="2026-06-01"):
    return {
        "game_pk": game,
        "game_date": date_value,
        "home_team": "LG",
        "away_team": "HT",
        "inning": 1,
        "inning_topbot": "top",
        "at_bat_number": ab,
        "pitch_number": number,
        "pitcher": pitcher,
        "pitcher_name": "투수",
        "batter": batter,
        "batter_name": "타자",
        "stand": "R",
        "events": event,
    }


def test_pitch_rows_are_reduced_to_one_valid_completed_pa():
    rows = [
        pitch("g1", 1, 1, event="strikeout"),
        pitch("g1", 1, 2, event="strikeout"),
        pitch("g1", 2, 1, event="single", pitcher="p1"),
        pitch("g1", 2, 2, event="single", pitcher="p2"),
        pitch("g1", 3, 1, event=None),
    ]
    result, quality = parse_complete_plate_appearances(rows, season=2026)

    assert len(result) == 1
    assert result[0]["event"] == "strikeout"
    assert result[0]["batting_team_code"] == "HT"
    assert result[0]["fielding_team_code"] == "LG"
    assert quality["accepted"] == 1
    assert quality["mixed_pitchers"] == 1
    assert quality["incomplete"] == 1


@pytest.mark.asyncio
async def test_matchups_exclude_as_of_day_and_report_small_sample(db_session):
    batch = DataImportBatch(
        dataset="kbo_plate_appearances",
        source_name="fixture",
        status="PARTIAL",
        freshness="UNKNOWN",
        season=2026,
        season_type="REGULAR",
        imported_at=datetime.now(timezone.utc),
        record_count=3,
        quality_summary={"date_min": "2026-06-01", "date_max": "2026-06-03"},
    )
    db_session.add(batch)
    await db_session.flush()
    db_session.add(KboPitcherAppearance(
        game_pk="g1", team_code="HT", appearance_order=1, pitcher_id="p1",
        pitcher_name="투수 A", pitcher_id_source="OFFICIAL_VERIFIED",
        batters_faced=10, pitches=30, strikeouts=3, walks=1,
    ))
    for game, game_day, event in (
        ("g1", date(2026, 6, 1), "strikeout"),
        ("g2", date(2026, 6, 2), "single"),
        ("g3", date(2026, 6, 3), "home_run"),
    ):
        db_session.add(KboPlateAppearance(
            game_pk=game, season=2026, game_date=game_day, at_bat_number=1,
            inning=1, inning_topbot="top", batting_team_code="LG", fielding_team_code="HT",
            batter_id="b1", batter_name="타자 A", batter_stand="R",
            pitcher_id="p1", pitcher_name="투수 A", event=event, source_batch_id=batch.id,
        ))
    await db_session.commit()

    result = await analyze_lineup_matchups(
        db_session, team_code="KIA", opponent_team_code="LG", pitcher_ids=["p1"],
        batter_ids=["b1"], season=2026, as_of_date=date(2026, 6, 3),
    )

    matchup = result["matchups"][0]
    assert result["lineup_source"] == "OBSERVED_GAME_PBP"
    assert result["data_snapshot_id"] == batch.id
    assert matchup["plate_appearances"] == 2
    assert matchup["hits"] == 1
    assert matchup["strikeouts"] == 1
    assert matchup["home_runs"] == 0
    assert matchup["sample_tier"] == "VERY_SMALL"


@pytest.mark.asyncio
async def test_matchup_rejects_opponent_batter_only_seen_after_as_of(db_session):
    db_session.add(KboPitcherAppearance(
        game_pk="g1", team_code="HT", appearance_order=1, pitcher_id="p1",
        pitcher_name="투수 A", pitcher_id_source="OFFICIAL_VERIFIED",
        batters_faced=10, pitches=30, strikeouts=3, walks=1,
    ))
    db_session.add(KboPlateAppearance(
        game_pk="g2", season=2026, game_date=date(2026, 6, 3), at_bat_number=1,
        inning=1, inning_topbot="top", batting_team_code="LG", fielding_team_code="HT",
        batter_id="b1", batter_name="미래 타자", batter_stand="L",
        pitcher_id="p1", pitcher_name="투수 A", event="single",
    ))
    await db_session.commit()

    with pytest.raises(ValueError, match="상대 구단 기록으로 확인되지 않는"):
        await analyze_lineup_matchups(
            db_session, team_code="HT", opponent_team_code="LG", pitcher_ids=["p1"],
            batter_ids=["b1"], season=2026, as_of_date=date(2026, 6, 3),
        )
