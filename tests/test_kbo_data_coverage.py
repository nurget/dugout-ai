from datetime import date

import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.kbo import KboGame, KboTeam
from app.models.kbo_pitch_event import KboPitchEvent
from app.models.kbo_plate_appearance import KboPlateAppearance
from app.models.user import User
from app.services.kbo_data_coverage import get_data_coverage
from app.services.kbo_game_lineups import import_game_boxscore
from app.services.kbo_player_records import import_snapshot, import_team_snapshot


def player_snapshot(category: str, player_id: str) -> dict:
    fields = {"PA": "500", "AVG": "0.300"} if category == "batter" else {"IP": "150", "ERA": "3.00"}
    return {
        "season": 2026,
        "season_type": "REGULAR",
        "category": category,
        "source_url": "https://www.koreabaseball.com/Record/Player/HitterBasic/Basic1.aspx",
        "fetched_at": "2026-11-16T12:00:00+00:00",
        "records": [{
            "player_id": player_id,
            "player_name": f"가상 {category}",
            "team_code": "HT",
            "raw_fields": fields,
        }],
    }


def team_snapshot(category: str) -> dict:
    return {
        "season": 2026,
        "season_type": "REGULAR",
        "category": category,
        "source_url": "https://www.koreabaseball.com/Record/TeamRank/TeamRank.aspx",
        "fetched_at": "2026-11-16T12:00:00+00:00",
        "records": [{"team_code": "KIA", "raw_fields": {"G": "2", "경기": "2"}}],
    }


@pytest.mark.asyncio
async def test_coverage_keeps_complete_records_separate_from_partial_pbp(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'coverage.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            session.add_all([KboTeam(code=code, name=code) for code in ("KIA", "LG", "HH")])
            await session.flush()
            session.add_all([
                KboGame(game_pk="20260401LGHT0", season=2026, season_type="REGULAR", season_phase="REGULAR",
                        game_date=date(2026, 4, 1), home_team_code="KIA", away_team_code="LG", status="Final", source_name="test"),
                KboGame(game_pk="20260402HHHT0", season=2026, season_type="REGULAR", season_phase="REGULAR",
                        game_date=date(2026, 4, 2), home_team_code="KIA", away_team_code="HH", status="Final", source_name="test"),
                KboGame(game_pk="20260403LGHT0", season=2026, season_type="REGULAR", season_phase="REGULAR",
                        game_date=date(2026, 4, 3), home_team_code="KIA", away_team_code="LG", status="Cancelled", source_name="test"),
            ])
            await session.flush()
            await import_snapshot(session, player_snapshot("batter", "b1"))
            await import_snapshot(session, player_snapshot("pitcher", "p1"))
            for category in ("standings", "batting", "pitching", "defense", "running"):
                await import_team_snapshot(session, team_snapshot(category))
            await import_game_boxscore(session, {
                "season": 2026,
                "game_pk": "20260401LGHT0",
                "game_date": "2026-04-01",
                "source_url": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx",
                "teams": [{
                    "team_code": "LG",
                    "batters": [{"player_id": "b-lg", "player_name": "상대 타자", "batting_order": 1,
                                 "is_starter": True, "position": "중견수", "raw_fields": {"AB": "4"}}],
                }, {
                    "team_code": "HT",
                    "batters": [{"player_id": "b-ht", "player_name": "우리 타자", "batting_order": 1,
                                 "is_starter": True, "position": "중견수", "raw_fields": {"AB": "4"}}],
                }],
            })
            session.add_all([
                KboPlateAppearance(game_pk="20260401LGHT0", season=2026, game_date=date(2026, 4, 1),
                                   at_bat_number=1, inning=1, inning_topbot="TOP", batting_team_code="LG",
                                   fielding_team_code="HT", batter_id="b-lg", batter_name="상대 타자",
                                   batter_stand="R", pitcher_id="p1", pitcher_name="가상 pitcher", event="single"),
                KboPlateAppearance(game_pk="20260401LGHT02026", season=2026, game_date=date(2026, 4, 1),
                                   at_bat_number=2, inning=3, inning_topbot="TOP", batting_team_code="LG",
                                   fielding_team_code="HT", batter_id="b-lg", batter_name="상대 타자",
                                   batter_stand="R", pitcher_id="p1", pitcher_name="가상 pitcher", event="strikeout"),
                KboPitchEvent(game_pk="20260401LGHT02026", season=2026, game_date=date(2026, 4, 1),
                              inning=1, inning_topbot="TOP", at_bat_number=1, pitch_number=1,
                              home_team_code="HT", away_team_code="LG", batter_id="b-lg",
                              batter_name="상대 타자", pitcher_id="p1", pitcher_name="가상 pitcher",
                              raw_payload={}),
            ])
            await session.commit()

            result = await get_data_coverage(session, season=2026, team_code="KIA")
            assert result["overall_status"] == "PARTIAL"
            assert result["team_code"] == "KIA"
            assert result["sections"]["records"]["status"] == "COMPLETE"
            assert result["sections"]["records"]["team_record_count"] == 5
            assert result["sections"]["schedule"]["game_count"] == 3
            assert result["sections"]["schedule"]["completed_game_count"] == 2
            assert result["sections"]["boxscores"]["loaded_completed_games"] == 1
            assert result["sections"]["boxscores"]["coverage_rate"] == 50.0
            assert result["sections"]["matchups"]["covered_completed_games"] == 1
            assert result["sections"]["matchups"]["coverage_rate"] == 50.0
            assert result["sections"]["matchups"]["plate_appearances"] == 2
            assert result["sections"]["matchups"]["pitch_events"] == 1
            assert result["sections"]["matchups"]["date_through"] == "2026-04-01"

            empty = await get_data_coverage(session, season=2025, team_code="KIA")
            assert empty["overall_status"] == "EMPTY"
            assert all(section["status"] == "EMPTY" for section in empty["sections"].values())

        async def override_db():
            async with factory() as session:
                yield session

        async def override_user():
            return User(id="coverage-user", username="coverage", team_code="KIA", role="COACH", is_active=True)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
                response = await client.get("/api/kbo/records/coverage", params={"season": 2026, "team_code": "KIA"})
                assert response.status_code == 200
                assert response.json()["sections"]["matchups"]["coverage_rate"] == 50.0
        finally:
            app.dependency_overrides.pop(get_db, None)
            app.dependency_overrides.pop(get_current_user, None)
    finally:
        await engine.dispose()
