import httpx
import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.auth import get_current_user
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.user import User
from app.services.kbo_player_records import (
    PlayerRecordError, get_player_record_payload, get_team_record_payload, innings_to_outs,
    canonical_team_code, import_snapshot, import_team_snapshot, normalize_team_snapshot,
    pitcher_fip_constant, record_metrics, team_code_aliases,
)


def snapshot(category, records):
    return {
        "season": 2026, "season_type": "REGULAR", "category": category,
        "source_url": "https://www.koreabaseball.com/Record/Player/HitterBasic/Basic1.aspx",
        "source_urls": ["https://www.koreabaseball.com/Record/Player/HitterBasic/Basic1.aspx",
                        "https://www.koreabaseball.com/Record/Player/HitterBasic/Basic2.aspx"],
        "fetched_at": "2026-11-16T12:00:00+00:00", "records": records,
    }


def player(player_id, name, fields, *, position=None, team="HT"):
    return {"player_id": player_id, "player_name": name, "team_code": team,
            "raw_fields": fields, "profile": {"position": position} if position else {}}


@pytest.mark.asyncio
async def test_player_records_are_identical_across_menus_and_keep_raw_profiles(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'records.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            await import_snapshot(session, snapshot("batter", [
                player("101", "가상 타자", {"AVG": "0.321", "PA": "500", "OBP": "0.400", "SLG": "0.500"}, position="내야수"),
                player("102", "가상 투수", {"AVG": "-", "PA": "0"}),
                player("103", "가상 겸업", {"AVG": "0.250", "PA": "40"}, position="투수 겸 외야수"),
            ]))
            await import_snapshot(session, snapshot("pitcher", [
                player("102", "가상 투수", {"ERA": "2.34", "G": "30", "SO": "100", "BB": "20", "TBF": "400"}),
                player("103", "가상 겸업", {"ERA": "4.00", "G": "1"}, position="투수 겸 외야수"),
            ]))
            await import_team_snapshot(session, snapshot("standings", [
                {"team_code": "KIA", "raw_fields": {"경기": "144"}},
            ]))
            await session.commit()

        async def override_db():
            async with factory() as session:
                yield session

        async def override_user():
            return User(id="test", username="records", team_code="KIA", role="COACH", is_active=True)

        app.dependency_overrides[get_db] = override_db
        app.dependency_overrides[get_current_user] = override_user
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            canonical = (await client.get("/api/kbo/records/players", params={"team_code": "KIA"})).json()
            batter_menu = (await client.get("/api/teams/me/batters")).json()
            assert canonical["data"] == batter_menu["data"]
            assert [row["player_id"] for row in canonical["data"]] == ["103", "101"]
            assert canonical["excluded_pitchers"] == 1
            complete = (await client.get("/api/kbo/records/players", params={"team_code": "HT", "include_pitchers": True})).json()
            assert complete["count"] == 3
            assert next(row for row in complete["data"] if row["player_id"] == "102")["position"] == "투수"
            record = next(row for row in canonical["data"] if row["player_id"] == "101")
            assert record["raw_fields"]["AVG"] == "0.321"
            assert record["profile"] == {"position": "내야수"}
            assert record["metrics"]["ops"] == 0.9
            assert len(record["source_urls"]) == 2
            assert record["collected_at"].startswith("2026-11-16T12:00:00")
            qualified = (await client.get("/api/kbo/records/players", params={"team_code": "HT", "qualified_only": True})).json()
            qualified_menu = (await client.get("/api/teams/me/batters", params={"qualified_only": True})).json()
            assert qualified["data"] == qualified_menu["data"]
            assert [row["player_id"] for row in qualified["data"]] == ["101"]
            assert qualified["data"][0]["qualification"]["min_plate_appearances"] == 446
            assert qualified["qualification_standards"]["rounding"] == "FLOOR"
            pitchers = (await client.get("/api/teams/me/pitchers")).json()
            kbo_pitchers = (await client.get("/api/kbo/records/players", params={"category": "pitcher", "team_code": "KIA"})).json()
            assert [(p["player_id"], p["raw_fields"]) for p in pitchers["data"]] == [(p["player_id"], p["raw_fields"]) for p in kbo_pitchers["data"]]
            assert next(row for row in pitchers["data"] if row["player_id"] == "102")["k_minus_bb_pct"] == 20.0
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)
        await engine.dispose()


@pytest.mark.asyncio
async def test_team_snapshot_preserves_standings_and_failed_replacement_keeps_data(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'teams.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            payload = snapshot("standings", [{"team_code": "HT", "raw_fields": {"순위": "1", "승": "90", "패": "50", "무": "4", "승률": "0.643"}}])
            assert await import_team_snapshot(session, payload) == 1
            await session.commit()
            result = await get_team_record_payload(session, season=2026, category="standings", team_code="KIA")
            assert result["data"][0]["team_code"] == "KIA"
            assert result["data"][0]["raw_fields"]["승률"] == "0.643"
            invalid = {**payload, "records": [payload["records"][0], {**payload["records"][0], "team_code": "KIA"}]}
            with pytest.raises(PlayerRecordError, match="중복"):
                await import_team_snapshot(session, invalid)
            assert (await get_team_record_payload(session, season=2026, category="standings"))["count"] == 1
    finally:
        await engine.dispose()


def test_rates_require_known_denominators_and_reject_invalid_team_record_rows():
    assert record_metrics({"SO": "80", "BB": "20", "IP": "60 1/3"}, "pitcher")["k_pct"] is None
    assert record_metrics({"AVG": "-", "OBP": "-", "SLG": "-"}, "batter")["ops"] is None
    assert record_metrics({"TBF": "0", "SO": "0", "BB": "0"}, "pitcher")["bb_pct"] is None
    with pytest.raises(PlayerRecordError):
        normalize_team_snapshot(snapshot("standings", [None]))


def test_sabermetrics_use_complete_denominators_and_season_fip_constant():
    batter = record_metrics({
        "AVG": "0.250", "OBP": "0.330", "SLG": "0.420", "PA": "460", "AB": "400",
        "H": "100", "HR": "20", "BB": "50", "SO": "80", "SF": "5",
    }, "batter")
    assert batter["iso"] == 0.17
    assert batter["k_pct"] == 17.39
    assert batter["bb_pct"] == 10.87
    assert batter["babip"] == 0.262
    assert batter["fip"] is None

    constant = pitcher_fip_constant([{
        "IP": "100", "ER": "40", "HR": "10", "BB": "30", "HBP": "5", "SO": "100",
    }])
    assert constant == 3.25
    pitcher = record_metrics({
        "IP": "100", "TBF": "400", "H": "90", "HR": "10", "BB": "30", "HBP": "5",
        "SO": "100", "SAC": "3", "SF": "4", "ERA": "3.60", "WHIP": "1.20",
    }, "pitcher", fip_constant=constant)
    assert pitcher["k_per_9"] == 9.0
    assert pitcher["bb_per_9"] == 2.7
    assert pitcher["hr_per_9"] == 0.9
    assert pitcher["babip"] == 0.317
    assert pitcher["fip"] == 3.6
    assert pitcher["fip_constant"] == 3.25

    incomplete_batter = record_metrics({"H": "10", "HR": "1", "AB": "50", "SO": "10"}, "batter")
    assert incomplete_batter["babip"] is None
    assert pitcher_fip_constant([{"IP": "10", "ER": "3"}]) is None


@pytest.mark.parametrize(("innings", "outs"), [
    ("143 2/3", 431), ("144", 432), ("143.2", 431), ("143⅔", 431),
    ("2/3", 2), ("0", 0), ("-", None), ("143.66", None), ("143 3/3", None),
])
def test_innings_qualification_uses_exact_baseball_thirds(innings, outs):
    assert innings_to_outs(innings) == outs


@pytest.mark.asyncio
async def test_qualification_floors_team_game_multiplier_and_compares_innings_in_outs(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'qualification.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            await import_team_snapshot(session, snapshot("standings", [{"team_code": "KIA", "raw_fields": {"경기": "139"}}]))
            await import_team_snapshot(session, snapshot("batting", [{"team_code": "HT", "raw_fields": {"G": "1"}}]))
            await import_snapshot(session, snapshot("batter", [
                player("b429", "규정 미달", {"PA": "429", "G": "999"}, position="내야수"),
                player("b430", "규정 충족", {"PA": "430", "G": "2"}, position="내야수"),
                player("b446", "시즌 규정 충족", {"PA": "446", "G": "2"}, position="내야수"),
                player("b0", "영타석", {"PA": "0", "G": "999"}, position="내야수"),
                player("b-missing", "타석 누락", {"AVG": "0.500"}, position="내야수"),
                player("b-unknown", "팀 기준 없음", {"PA": "999", "G": "999"}, position="외야수", team="HH"),
            ]))
            result = await get_player_record_payload(session, season=2026, category="batter")
            records = {row["player_id"]: row["qualification"] for row in result["data"]}
            assert records["b430"]["min_plate_appearances"] == 430  # 139 × 3.1 = 430.9, 소수점 버림.
            assert records["b430"]["team_games"] == 139
            assert records["b430"]["basis"] == "TEAM_RECORD"
            assert records["b430"]["is_qualified"] is True
            assert records["b429"]["is_qualified"] is False
            assert records["b0"]["is_qualified"] is False
            assert records["b-missing"]["is_qualified"] is None
            assert records["b-unknown"]["is_qualified"] is None
            await import_team_snapshot(session, snapshot("standings", [{"team_code": "HT", "raw_fields": {"경기": "144"}}]))
            await import_snapshot(session, snapshot("pitcher", [
                player("p143", "삼분의 이 미달", {"IP": "143 2/3", "ERA": "0.00"}),
                player("p144", "규정 이닝 충족", {"IP": "144", "ERA": "2.00"}),
                player("p0", "영이닝", {"IP": "0", "ERA": "0.00"}),
            ]))
            pitchers = await get_player_record_payload(session, season=2026, category="pitcher")
            pitcher_records = {row["player_id"]: row["qualification"] for row in pitchers["data"]}
            assert pitcher_records["p143"]["actual_outs"] == 431
            assert pitcher_records["p143"]["min_innings"] == 144
            assert pitcher_records["p143"]["is_qualified"] is False
            assert pitcher_records["p144"]["is_qualified"] is True
            assert pitcher_records["p0"]["is_qualified"] is False
            filtered = await get_player_record_payload(session, season=2026, category="pitcher", qualified_only=True)
            assert [row["player_id"] for row in filtered["data"]] == ["p144"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_qualification_fallback_counts_completed_team_games_and_excludes_nonresults(tmp_path):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    from app.models.kbo import KboGame, KboTeam

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'qualification-games.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    today = datetime.now(ZoneInfo("Asia/Seoul")).date()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            session.add_all([KboTeam(code=code, name=code) for code in ("KIA", "HT", "LG")])
            await session.flush()
            for index, status, days, season_type in (
                (1, "Final", -5, "REGULAR"), (2, "종료", -4, "REGULAR"),
                (3, "Cancelled", -3, "REGULAR"), (4, "Postponed", -2, "REGULAR"),
                (5, "Scheduled", -1, "REGULAR"), (6, "Final", 1, "REGULAR"),
                (7, "Final", -1, "POSTSEASON"),
            ):
                day = today + timedelta(days=days)
                session.add(KboGame(game_pk=f"qualification-{index}", season=today.year, season_type=season_type,
                    season_phase=season_type, game_date=day, home_team_code="HT" if index % 2 else "KIA",
                    away_team_code="LG", status=status, source_name="test"))
            payload = snapshot("batter", [player("fallback", "규정타석", {"PA": "6", "G": "999"}, position="내야수")])
            payload["season"] = today.year
            await import_snapshot(session, payload)
            result = await get_player_record_payload(session, season=today.year, category="batter", qualified_only=True)
            qualification = result["data"][0]["qualification"]
            assert qualification["team_games"] == 2
            assert qualification["min_plate_appearances"] == 6
            assert qualification["basis"] == "COMPLETED_GAMES"
            assert qualification["is_qualified"] is True
    finally:
        await engine.dispose()


@pytest.mark.parametrize(("source", "canonical", "stored"), [
    ("KIA", "KIA", "HT"), ("HT", "KIA", "KIA"), ("SSG", "SSG", "SK"),
    ("DOOSAN", "OB", "DOO"), ("SAMSUNG", "SS", "SAM"), ("HANWHA", "HH", "HAN"),
    ("LOTTE", "LT", "LOT"), ("KIWOOM", "WO", "KIW"),
])
def test_records_share_team_aliases_with_schedule_and_matchup_services(source, canonical, stored):
    assert canonical_team_code(source) == canonical
    assert stored in team_code_aliases(source)


@pytest.mark.asyncio
async def test_game_boxscore_import_registers_its_source_batch(tmp_path):
    from datetime import date
    from sqlalchemy import select
    from app.models.data_import_batch import DataImportBatch
    from app.models.kbo import KboGame, KboTeam
    from app.services.kbo_game_lineups import import_game_boxscore

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'boxscore.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        async with factory() as session:
            session.add_all([KboTeam(code="KIA", name="테스트 홈"), KboTeam(code="LG", name="테스트 원정")])
            await session.flush()
            session.add(KboGame(game_pk="test-game", season=2026, season_type="REGULAR", season_phase="REGULAR",
                game_date=date(2026, 9, 1), home_team_code="KIA", away_team_code="LG", status="Final", source_name="test"))
            await session.flush()
            rows = [{"team_code": code, "batters": [
                {"player_id": f"{code}-{order}", "player_name": f"가상 타자 {order}", "batting_order": order,
                 "is_starter": True, "position": "내야수", "raw_fields": {"AB": "4", "H": "1"}}
                for order in range(1, 10)
            ]} for code in ("HT", "LG")]
            count = await import_game_boxscore(session, {"season": 2026, "game_pk": "test-game", "game_date": "2026-09-01",
                "source_url": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx", "teams": rows})
            assert count == 18
            batch = await session.scalar(select(DataImportBatch).where(DataImportBatch.dataset == "kbo_game_lineups"))
            assert batch is not None and batch.record_count == 18
            assert batch.quality_summary["validation"] == "PASSED"
    finally:
        await engine.dispose()
