from datetime import date, datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.models.data_import_batch import DataImportBatch
from app.models.kbo_pitcher_appearance import KboPitcherAppearance
from app.models.kbo_plate_appearance import KboPlateAppearance
from app.models.kbo import KboGame, KboTeam
from app.models.kbo_game_lineup import KboGameBoxscore, KboGameLineup
from app.models.kbo_player_record import KboPlayerRecord
from app.services.kbo_game_lineups import get_game_boxscore, import_game_boxscore, normalize_game_boxscore
from app.services.kbo_matchups import analyze_lineup_matchups, get_game_pitcher_matchup, get_matchup_calendar, get_matchup_games_for_date, get_matchup_pitchers, parse_complete_plate_appearances


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tables = [DataImportBatch.__table__, KboTeam.__table__, KboGame.__table__, KboPitcherAppearance.__table__, KboPlateAppearance.__table__, KboPlayerRecord.__table__, KboGameBoxscore.__table__, KboGameLineup.__table__]
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
async def test_matchup_accepts_as_of_day_batter_but_excludes_same_day_pa(db_session):
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

    result = await analyze_lineup_matchups(
        db_session, team_code="HT", opponent_team_code="LG", pitcher_ids=["p1"],
        batter_ids=["b1"], season=2026, as_of_date=date(2026, 6, 3),
    )

    assert result["matchups"][0]["batter_name"] == "미래 타자"
    assert result["matchups"][0]["plate_appearances"] == 0


@pytest.mark.asyncio
async def test_matchup_rejects_opponent_batter_first_seen_after_as_of(db_session):
    db_session.add(KboPitcherAppearance(
        game_pk="g1", team_code="HT", appearance_order=1, pitcher_id="p1",
        pitcher_name="투수 A", pitcher_id_source="OFFICIAL_VERIFIED",
        batters_faced=10, pitches=30, strikeouts=3, walks=1,
    ))
    db_session.add(KboPlateAppearance(
        game_pk="g2", season=2026, game_date=date(2026, 6, 4), at_bat_number=1,
        inning=1, inning_topbot="top", batting_team_code="LG", fielding_team_code="HT",
        batter_id="b1", batter_name="미래 타자", batter_stand="L",
        pitcher_id="p1", pitcher_name="투수 A", event="single",
    ))
    await db_session.commit()

    with pytest.raises(ValueError, match="기준일까지 상대 구단 경기에서 확인되지 않는"):
        await analyze_lineup_matchups(
            db_session, team_code="HT", opponent_team_code="LG", pitcher_ids=["p1"],
            batter_ids=["b1"], season=2026, as_of_date=date(2026, 6, 3),
        )


def boxscore_payload():
    return {
        "season": 2026, "game_pk": "g-box", "game_date": "2026-08-03",
        "source_url": "https://www.koreabaseball.com/Schedule/GameCenter/Main.aspx?gameId=g-box",
        "teams": [
            {"team_code": "KIA", "batters": [{"player_id": "own1", "player_name": "우리 타자", "batting_order": 1, "is_starter": True, "position": "지", "raw_fields": {"AB": "4", "H": "1"}}], "pitchers": [{"player_id": "p1", "player_name": "우리 투수", "raw_fields": {"삼진": "6"}}]},
            {"team_code": "LG", "batters": [
                {"player_id": "b1", "player_name": "상대 선발", "batting_order": 1, "is_starter": True, "position": "중", "raw_fields": {"AB": "3", "H": "2"}},
                {"player_id": "box-replacement", "player_name": "상대 교체", "batting_order": 1, "is_starter": False, "position": "주", "raw_fields": {"AB": "0", "H": "0"}},
            ]},
        ],
    }


async def seed_boxscore_game(session):
    session.add_all([KboTeam(code="KIA", name="KIA"), KboTeam(code="LG", name="LG")])
    session.add(KboGame(game_pk="g-box", season=2026, season_type="REGULAR", season_phase="REGULAR", game_date=date(2026, 8, 3), home_team_code="KIA", away_team_code="LG", home_score=2, away_score=1, status="Final", source_name="kbo"))
    await session.flush()


def test_boxscore_rejects_duplicate_starters_in_same_batting_slot():
    payload = boxscore_payload()
    payload["teams"][1]["batters"][1]["is_starter"] = True
    with pytest.raises(ValueError, match="선발 선수가 중복"):
        normalize_game_boxscore(payload)


@pytest.mark.parametrize("invalid_pitcher", [None, {"player_id": "p1", "player_name": None, "raw_fields": {"삼진": "6"}}, {"player_id": "p1", "player_name": "투수", "raw_fields": {"삼진": 6}}])
def test_boxscore_rejects_malformed_pitcher_identity_and_raw_fields(invalid_pitcher):
    payload = boxscore_payload()
    payload["teams"][0]["pitchers"] = [invalid_pitcher]
    with pytest.raises(ValueError, match="투수"):
        normalize_game_boxscore(payload)


@pytest.mark.asyncio
async def test_boxscore_lineup_is_available_outside_pbp_window_and_excludes_replacements(db_session):
    await seed_boxscore_game(db_session)
    payload = boxscore_payload()
    await import_game_boxscore(db_session, payload)
    await db_session.commit()
    result = await get_matchup_games_for_date(db_session, team_code="HT", season=2026, game_date=date(2026, 8, 3))
    game = result["data"][0]
    assert game["lineup_source"] == "KBO_GAME_BOXSCORE"
    assert [row["batter_id"] for row in game["batters"]] == ["b1"]
    assert game["batters"][0]["position"] == "중"
    stored = await get_game_boxscore(db_session, "g-box")
    assert stored["teams"][0]["pitchers"][0]["raw_fields"]["삼진"] == "6"
    assert stored["teams"][1]["batters"][1]["is_starter"] is False


@pytest.mark.asyncio
async def test_season_records_can_fill_roster_but_are_never_fabricated_as_lineup_or_matchups(db_session):
    await seed_boxscore_game(db_session)
    for category, player_id, name, team, fields in (
        ("batter", "b1", "상대 타자", "LG", {"AVG": "0.350", "HR": "30"}),
        ("pitcher", "p1", "우리 투수", "HT", {"ERA": "2.00", "SO": "100"}),
    ):
        db_session.add(KboPlayerRecord(season=2026, season_type="REGULAR", category=category, player_id=player_id, player_name=name, team_code=team, source_url="https://www.koreabaseball.com/Record/Player", raw_fields=fields))
    await db_session.commit()
    games = await get_matchup_games_for_date(db_session, team_code="KIA", season=2026, game_date=date(2026, 8, 3))
    assert games["data"][0]["batters"] == []
    assert games["data"][0]["lineup_source"] == "LINEUP_NOT_LOADED"
    assert games["data"][0]["available_batters"][0]["batter_id"] == "b1"
    result = await analyze_lineup_matchups(db_session, team_code="KIA", opponent_team_code="LG", pitcher_ids=["p1"], batter_ids=["b1"], season=2026, as_of_date=date(2026, 8, 3))
    assert result["matchups"][0]["plate_appearances"] == 0
    assert result["matchups"][0]["sample_tier"] == "NO_DIRECT_HISTORY"
    assert result["matchups"][0]["game_count"] == 0
    assert result["matchups"][0]["first_seen_date"] is None
    assert result["matchups"][0]["last_seen_date"] is None
    assert result["matchups"][0]["history_events"] == []
    assert result["season_batter_records"][0]["raw_fields"]["HR"] == "30"


@pytest.mark.asyncio
async def test_kia_and_ssg_season_aliases_link_to_boxscore_and_candidates(db_session):
    db_session.add_all([KboTeam(code="KIA", name="KIA"), KboTeam(code="SSG", name="SSG")])
    db_session.add(KboGame(game_pk="g-alias", season=2026, season_type="REGULAR", season_phase="REGULAR", game_date=date(2026, 8, 3), home_team_code="KIA", away_team_code="SSG", home_score=2, away_score=1, status="Final", source_name="kbo"))
    db_session.add_all([
        KboPlayerRecord(season=2026, season_type="REGULAR", category="pitcher", player_id="p-kia", player_name="KIA 투수", team_code="KIA", source_url="https://www.koreabaseball.com/Record/Player", raw_fields={"ERA": "2.50"}),
        KboPlayerRecord(season=2026, season_type="REGULAR", category="batter", player_id="b-ssg", player_name="SSG 타자", team_code="SSG", source_url="https://www.koreabaseball.com/Record/Player", raw_fields={"HR": "25"}),
    ])
    await db_session.flush()
    payload = boxscore_payload()
    payload["game_pk"] = "g-alias"
    payload["teams"][1]["team_code"] = "SSG"
    payload["teams"][1]["batters"][0]["player_id"] = "b-ssg"
    await import_game_boxscore(db_session, payload)
    await db_session.commit()
    games = await get_matchup_games_for_date(db_session, team_code="HT", season=2026, game_date=date(2026, 8, 3))
    assert games["data"][0]["batters"][0]["season_fields"]["HR"] == "25"
    pitchers = await get_matchup_pitchers(db_session, team_code="HT", season=2026, game_date=date(2026, 8, 3))
    assert pitchers["data"][0]["pitcher_id"] == "p-kia"
    result = await analyze_lineup_matchups(db_session, team_code="HT", opponent_team_code="SK", pitcher_ids=["p-kia"], batter_ids=["b-ssg"], season=2026, as_of_date=date(2026, 8, 3))
    assert result["matchups"][0]["pitcher_name"] == "KIA 투수"
    assert result["matchups"][0]["plate_appearances"] == 0


@pytest.mark.asyncio
async def test_fallback_roster_excludes_season_pitchers_but_confirmed_lineup_keeps_pitcher_batting(db_session):
    await seed_boxscore_game(db_session)
    for category, player_id, name, profile, fields in (
        ("batter", "b1", "상대 타자", {"position": "외야수"}, {"PA": "400"}),
        ("batter", "p-opponent", "상대 투수", {}, {"PA": "0"}),
        ("pitcher", "p-opponent", "상대 투수", {"position": "투수"}, {"G": "40"}),
    ):
        db_session.add(KboPlayerRecord(season=2026, season_type="REGULAR", category=category,
            player_id=player_id, player_name=name, team_code="LG", profile=profile,
            source_url="https://www.koreabaseball.com/Record/Player", raw_fields=fields))
    await db_session.commit()
    result = await get_matchup_games_for_date(db_session, team_code="HT", season=2026, game_date=date(2026, 8, 3))
    assert [row["batter_id"] for row in result["data"][0]["available_batters"]] == ["b1"]
    payload = boxscore_payload()
    payload["teams"][1]["batters"][0].update(player_id="p-opponent", player_name="상대 투수", position="투")
    await import_game_boxscore(db_session, payload)
    await db_session.commit()
    result = await get_matchup_games_for_date(db_session, team_code="KIA", season=2026, game_date=date(2026, 8, 3))
    assert result["data"][0]["lineup_source"] == "KBO_GAME_BOXSCORE"
    assert [row["batter_id"] for row in result["data"][0]["batters"]] == ["p-opponent"]
    assert [row["batter_id"] for row in result["data"][0]["available_batters"]] == ["b1"]


@pytest.mark.asyncio
async def test_game_pitcher_detail_only_lists_actual_appearances_and_labels_team_batting_totals(db_session):
    await seed_boxscore_game(db_session)
    payload = boxscore_payload()
    payload["teams"][0]["pitchers"][0]["raw_fields"].update({"이닝": "5", "투구수": "80"})
    await import_game_boxscore(db_session, payload)
    db_session.add(KboPlayerRecord(season=2026, season_type="REGULAR", category="pitcher", player_id="not-appeared", player_name="미등판 투수", team_code="HT", source_url="https://www.koreabaseball.com/Record/Player", raw_fields={"ERA": "2.00"}))
    await db_session.commit()
    result = await get_game_pitcher_matchup(db_session, team_code="KIA", game_pk="g-box")
    assert [row["pitcher_id"] for row in result["pitchers"]] == ["p1"]
    assert result["selected_pitcher"]["game_fields"]["투구수"] == "80"
    assert result["direct_matchup_available"] is False
    assert result["direct_totals"] is None
    assert [row["is_starter"] for row in result["batters"]] == [True, False]
    assert result["batters"][0]["game_fields"]["H"] == "2"
    with pytest.raises(ValueError, match="등판이 확인되지"):
        await get_game_pitcher_matchup(db_session, team_code="KIA", game_pk="g-box", pitcher_id="not-appeared")


@pytest.mark.asyncio
async def test_game_direct_matchups_exclude_other_pitchers_other_games_and_wrong_fielding_team(db_session):
    await seed_boxscore_game(db_session)
    payload = boxscore_payload()
    payload["teams"][0]["pitchers"].append({"player_id": "p2", "player_name": "두 번째 투수", "raw_fields": {"이닝": "1", "피안타": "1"}})
    await import_game_boxscore(db_session, payload)
    for game_pk, ab, pitcher_id, event, batting_team, fielding_team in (
        ("g-box", 1, "p1", "single", "LG", "HT"),
        ("g-box", 2, "p2", "home_run", "LG", "HT"),
        ("other-game", 3, "p1", "home_run", "LG", "HT"),
        ("g-box", 4, "p1", "home_run", "HT", "LG"),
    ):
        db_session.add(KboPlateAppearance(game_pk=game_pk, season=2026, game_date=date(2026, 8, 3), at_bat_number=ab, batting_team_code=batting_team, fielding_team_code=fielding_team, batter_id="b1", batter_name="상대 선발", pitcher_id=pitcher_id, pitcher_name="투수", event=event))
    await db_session.commit()
    first = await get_game_pitcher_matchup(db_session, team_code="KIA", game_pk="g-box", pitcher_id="p1")
    second = await get_game_pitcher_matchup(db_session, team_code="HT", game_pk="g-box", pitcher_id="p2")
    assert first["direct_totals"]["plate_appearances"] == 1
    assert first["direct_totals"]["home_runs"] == 0
    assert second["direct_totals"]["home_runs"] == 1
    assert first["batters"][0]["direct_matchup"]["home_runs"] == 0
    assert first["batters"][0]["game_fields"]["H"] == "2"
    assert first["batters"][1]["direct_matchup"] is None


@pytest.mark.asyncio
async def test_unlinked_boxscore_pitcher_never_matches_pbp_by_name(db_session):
    await seed_boxscore_game(db_session)
    payload = boxscore_payload()
    payload["teams"][0]["pitchers"][0]["player_id"] = "box-local-unverified"
    await import_game_boxscore(db_session, payload)
    db_session.add(KboPlateAppearance(game_pk="g-box", season=2026, game_date=date(2026, 8, 3), at_bat_number=1, batting_team_code="LG", fielding_team_code="HT", batter_id="b1", batter_name="상대 선발", pitcher_id="p1", pitcher_name="우리 투수", event="home_run"))
    await db_session.commit()
    result = await get_game_pitcher_matchup(db_session, team_code="KIA", game_pk="g-box")
    assert result["selected_pitcher"]["pitcher_id"] == "box-local-unverified"
    assert result["direct_matchup_available"] is False
    assert result["direct_totals"] is None


@pytest.mark.asyncio
async def test_matchup_calendar_reuses_playable_dates_policy(db_session, monkeypatch):
    from app.services.analysis_game_dates import eligible_game_conditions
    monkeypatch.setattr("app.services.kbo_matchups.eligible_game_conditions", lambda team: eligible_game_conditions(team, today=date(2026, 11, 17)))
    await seed_boxscore_game(db_session)
    for game_pk, day, status in (("canceled", date(2026, 9, 1), "Cancelled"), ("postponed", date(2026, 9, 2), "우천취소"), ("future", date(2026, 12, 1), "Scheduled")):
        db_session.add(KboGame(game_pk=game_pk, season=2026, season_type="REGULAR", season_phase="REGULAR", game_date=day, home_team_code="KIA", away_team_code="LG", status=status, source_name="kbo"))
    await db_session.commit()
    result = await get_matchup_calendar(db_session, team_code="HT", season=2026)
    assert result["data"] == [{"game_date": "2026-08-03", "count": 1}]
    with pytest.raises(ValueError, match="취소·연기"):
        await get_game_pitcher_matchup(db_session, team_code="KIA", game_pk="canceled")


async def seed_pbp_alias_game(session, *, boxscore=True):
    canonical = "20260726WOHT0"
    session.add_all([KboTeam(code="HT", name="KIA"), KboTeam(code="WO", name="키움")])
    session.add(KboGame(game_pk=canonical, season=2026, season_type="REGULAR", season_phase="REGULAR", game_date=date(2026, 7, 26), home_team_code="HT", away_team_code="WO", home_score=2, away_score=1, status="Final", source_name="kbo"))
    await session.flush()
    if boxscore:
        payload = boxscore_payload()
        payload.update(game_pk=canonical, game_date="2026-07-26")
        payload["teams"][1]["team_code"] = "WO"
        payload["teams"][1]["batters"][0].update(player_id="54319", player_name="상대 타자")
        payload["teams"][0]["pitchers"][0].update(player_id="52641", player_name="황동하")
        await import_game_boxscore(session, payload)
    return canonical


def alias_pa(game_pk, ab, *, event="single", pitcher_id="52641", game_day=date(2026, 7, 26), batting_team="WO", fielding_team="HT"):
    return KboPlateAppearance(game_pk=game_pk, season=2026, game_date=game_day, at_bat_number=ab, batting_team_code=batting_team, fielding_team_code=fielding_team, batter_id="54319", batter_name="상대 타자", pitcher_id=pitcher_id, pitcher_name="황동하", event=event)


@pytest.mark.asyncio
async def test_same_game_pbp_year_suffix_is_joined_without_cross_date_team_or_pitcher_leakage(db_session):
    canonical = await seed_pbp_alias_game(db_session)
    suffix = canonical + "2026"
    db_session.add_all([
        alias_pa(suffix, 1),
        alias_pa(suffix, 2, event="home_run", pitcher_id="other-pitcher"),
        alias_pa(suffix, 3, event="home_run", game_day=date(2026, 7, 25)),
        alias_pa(suffix, 4, event="home_run", batting_team="LG"),
        alias_pa(suffix, 5, event="home_run", fielding_team="SS"),
        alias_pa("20260726WOHT12026", 6, event="home_run"),
    ])
    await db_session.commit()
    result = await get_game_pitcher_matchup(db_session, team_code="KIA", game_pk=canonical, pitcher_id="52641")
    assert result["direct_matchup_available"] is True
    assert result["direct_totals"]["plate_appearances"] == 1
    assert result["direct_totals"]["hits"] == 1
    assert result["direct_totals"]["home_runs"] == 0
    assert result["batters"][0]["direct_matchup"]["plate_appearances"] == 1


@pytest.mark.asyncio
async def test_same_at_bat_in_both_aliases_counts_once_and_conflicting_events_are_excluded(db_session):
    canonical = await seed_pbp_alias_game(db_session)
    suffix = canonical + "2026"
    db_session.add_all([
        alias_pa(canonical, 1), alias_pa(suffix, 1),
        alias_pa(canonical, 2, event="single"), alias_pa(suffix, 2, event="home_run"),
    ])
    await db_session.commit()
    result = await get_game_pitcher_matchup(db_session, team_code="KIA", game_pk=canonical, pitcher_id="52641")
    assert result["direct_totals"]["plate_appearances"] == 1
    assert result["direct_totals"]["home_runs"] == 0
    assert "1개 타석은 집계에서 제외" in result["note"]
    assert result["data_warnings"]


@pytest.mark.asyncio
async def test_pbp_lineup_fallback_accepts_year_suffix_and_filters_same_date_and_clubs(db_session):
    canonical = await seed_pbp_alias_game(db_session, boxscore=False)
    db_session.add_all([
        alias_pa(canonical + "2026", 1),
        alias_pa(canonical + "2026", 2, game_day=date(2026, 7, 25)),
        alias_pa(canonical + "2026", 3, fielding_team="LG"),
    ])
    await db_session.commit()
    result = await get_matchup_games_for_date(db_session, team_code="KIA", season=2026, game_date=date(2026, 7, 26))
    game = result["data"][0]
    assert game["lineup_source"] == "OBSERVED_BATTERS_FROM_GAME_PBP"
    assert game["batters_count"] == 1
    assert game["batters"][0]["batter_id"] == "54319"


@pytest.mark.asyncio
async def test_one_selected_pair_returns_only_prior_season_samples_and_exact_history_dates(db_session):
    for pitcher_id, name in (("p1", "양현종"), ("p2", "다른 투수")):
        db_session.add(KboPitcherAppearance(game_pk="old", team_code="HT", appearance_order=1 if pitcher_id == "p1" else 2, pitcher_id=pitcher_id, pitcher_name=name, pitcher_id_source="OFFICIAL_VERIFIED"))
    for game_pk, game_day, season, pitcher_id, batter_id, event in (
        ("old-first", date(2026, 6, 1), 2026, "p1", "b1", "strikeout"),
        ("old-last", date(2026, 6, 2), 2026, "p1", "b1", "double"),
        ("same-day-1", date(2026, 6, 3), 2026, "p1", "b1", "home_run"),
        ("same-day-2", date(2026, 6, 3), 2026, "p1", "b1", "home_run"),
        ("other-pitcher", date(2026, 6, 2), 2026, "p2", "b1", "home_run"),
        ("other-batter", date(2026, 6, 2), 2026, "p1", "b2", "walk"),
        ("previous-season", date(2025, 6, 1), 2025, "p1", "b1", "home_run"),
    ):
        db_session.add(KboPlateAppearance(game_pk=game_pk, game_date=game_day, season=season, at_bat_number=1, inning=3, batting_team_code="SS", fielding_team_code="KIA", pitcher_id=pitcher_id, pitcher_name="양현종", batter_id=batter_id, batter_name="구자욱", event=event))
    await db_session.commit()
    result = await analyze_lineup_matchups(db_session, team_code="KIA", opponent_team_code="SS", pitcher_ids=["p1"], batter_ids=["b1"], season=2026, as_of_date=date(2026, 6, 3))
    assert len(result["matchups"]) == 1
    row = result["matchups"][0]
    assert row["pitcher_name"] == "양현종"
    assert row["batter_name"] == "구자욱"
    assert row["plate_appearances"] == 2
    assert row["hits"] == 1
    assert row["strikeouts"] == 1
    assert row["home_runs"] == 0
    assert row["game_count"] == 2
    assert row["first_seen_date"] == "2026-06-01"
    assert row["last_seen_date"] == "2026-06-02"
    assert [event["game_date"] for event in row["history_events"]] == ["2026-06-02", "2026-06-01"]
    assert [event["event"] for event in row["history_events"]] == ["double", "strikeout"]


@pytest.mark.asyncio
async def test_prior_pair_history_deduplicates_same_game_aliases(db_session):
    canonical = await seed_pbp_alias_game(db_session)
    db_session.add(KboPitcherAppearance(game_pk=canonical, team_code="HT", appearance_order=1, pitcher_id="52641", pitcher_name="황동하", pitcher_id_source="OFFICIAL_VERIFIED"))
    db_session.add_all([alias_pa(canonical, 1), alias_pa(canonical + "2026", 1)])
    await db_session.commit()
    result = await analyze_lineup_matchups(db_session, team_code="KIA", opponent_team_code="WO", pitcher_ids=["52641"], batter_ids=["54319"], season=2026, as_of_date=date(2026, 7, 27))
    row = result["matchups"][0]
    assert row["plate_appearances"] == 1
    assert row["game_count"] == 1
    assert len(row["history_events"]) == 1
    assert row["history_events"][0]["game_pk"] == canonical
