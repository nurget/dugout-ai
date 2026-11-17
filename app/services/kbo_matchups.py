"""명시된 상대 타순에 대해 기준일 이전 직접 맞대결 결과를 집계한다."""
from collections import Counter, defaultdict
from datetime import date
from typing import Any, Iterable

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_import_batch import DataImportBatch
from app.models.kbo_pitcher_appearance import KboPitcherAppearance
from app.models.kbo_plate_appearance import KboPlateAppearance
from app.models.kbo import KboGame
from app.models.kbo_game_lineup import KboGameBoxscore, KboGameLineup
from app.models.kbo_player_record import KboPlayerRecord
from app.services.team_codes import normalize_official_team_code
from app.services.team_codes import game_team_code_candidates
from app.services.kbo_player_records import filter_primary_batters, get_player_records
from app.services.analysis_game_dates import eligible_game_conditions
from app.services.kbo_game_identity import canonical_game_pk, game_pk_candidates


HITS = {"single", "double", "triple", "home_run"}


async def _season_records(session: AsyncSession, *, season: int, team_code: str, category: str) -> list[KboPlayerRecord]:
    rows = await get_player_records(session, season=season, category=category,
        team_code=team_code, limit=10000)
    if category == "batter":
        return await filter_primary_batters(session, rows, season=season)
    return rows


async def get_matchup_calendar(session: AsyncSession, *, team_code: str, season: int) -> dict[str, Any]:
    games = (await session.execute(select(KboGame.game_date, KboGame.game_pk).where(
        KboGame.season == season,
        *eligible_game_conditions(team_code),
    ).order_by(KboGame.game_date.desc(), KboGame.game_pk))).all()
    counts = Counter(day.isoformat() for day, _ in games)
    return {"season": season, "latest_game_date": next(iter(counts), None), "data": [{"game_date": day, "count": count} for day, count in counts.items()]}


async def get_matchup_pitchers(session: AsyncSession, *, team_code: str, season: int, game_date: date) -> dict[str, Any]:
    records = await _season_records(session, season=season, team_code=team_code, category="pitcher")
    return {
        "season": season, "game_date": game_date.isoformat(),
        "data": [{"pitcher_id": row.player_id, "pitcher_name": row.player_name,
                  "batters_faced": None, "identity_status": "KBO_PLAYER_RECORD",
                  "record_source": "KBO_SEASON_RECORD", "season_fields": row.raw_fields} for row in records],
        "note": "후보는 해당 시즌 투수 명단입니다. 시즌 기록은 선택 경기일 이전 누적 기록이나 당일 엔트리를 뜻하지 않습니다.",
    }


def _direct_counts(rows: Iterable[KboPlateAppearance]) -> dict[str, int]:
    events = Counter(row.event for row in rows)
    return {
        "plate_appearances": sum(events.values()),
        "hits": sum(events[event] for event in HITS),
        "strikeouts": sum(events[event] for event in ("strikeout", "strikeout_double_play")),
        "walks": sum(events[event] for event in ("walk", "intent_walk", "intentional_walk")),
        "home_runs": events["home_run"],
        "hit_by_pitch": events["hit_by_pitch"],
    }


def _deduplicate_game_plate_appearances(rows: Iterable[KboPlateAppearance]) -> tuple[list[KboPlateAppearance], int]:
    """Alias IDs identify one game; one at-bat can contribute at most once."""
    grouped: dict[int, list[KboPlateAppearance]] = defaultdict(list)
    for row in rows:
        grouped[row.at_bat_number].append(row)
    accepted = []
    conflicting = 0
    for candidates in grouped.values():
        identities = {(row.season, row.game_date, normalize_official_team_code(row.batting_team_code),
                       normalize_official_team_code(row.fielding_team_code), row.batter_id,
                       row.pitcher_id, row.event) for row in candidates}
        if len(identities) != 1:
            conflicting += 1
            continue
        accepted.append(min(candidates, key=lambda row: (len(row.game_pk), row.game_pk)))
    return accepted, conflicting


async def get_game_pitcher_matchup(
    session: AsyncSession, *, team_code: str, game_pk: str, pitcher_id: str | None = None,
) -> dict[str, Any] | None:
    """Show actual game appearances without attributing a team batting sheet to one pitcher."""
    game = await session.get(KboGame, game_pk)
    if game is None:
        return None
    own_codes = game_team_code_candidates(team_code)
    if game.home_team_code not in own_codes and game.away_team_code not in own_codes:
        raise ValueError("선택한 경기는 로그인 구단의 경기가 아니에요.")
    eligible = await session.scalar(select(KboGame.game_pk).where(KboGame.game_pk == game_pk, *eligible_game_conditions(team_code)))
    if eligible is None:
        raise ValueError("미래 일정이나 취소·연기된 경기는 분석할 수 없어요.")
    opponent = game.away_team_code if game.home_team_code in own_codes else game.home_team_code
    opponent_codes = game_team_code_candidates(opponent)
    game_ids = game_pk_candidates(game.game_pk, season=game.season, game_date=game.game_date,
                                  home_team_code=game.home_team_code, away_team_code=game.away_team_code)
    season_pitchers = await _season_records(session, season=game.season, team_code=team_code, category="pitcher")
    season_batters = await _season_records(session, season=game.season, team_code=opponent, category="batter")
    season_pitcher_by_id = {row.player_id: row for row in season_pitchers}
    season_batter_by_id = {row.player_id: row for row in season_batters}
    boxscore = await session.get(KboGameBoxscore, game_pk)
    own_sheet = next((team for team in (boxscore.raw_payload.get("teams", []) if boxscore else []) if normalize_official_team_code(team.get("team_code", "")) == normalize_official_team_code(team_code)), {})
    candidates = []
    for order, row in enumerate(own_sheet.get("pitchers", []), start=1):
        fields = row.get("raw_fields", {})
        record = season_pitcher_by_id.get(row["player_id"])
        candidates.append({
            "pitcher_id": row["player_id"], "pitcher_name": row["player_name"],
            "appearance_order": order, "identity_status": fields.get("identity_status", "KBO_GAME_RECORD"),
            "game_fields": fields, "season_fields": record.raw_fields if record else {},
        })
    if not candidates:
        appearances = list((await session.scalars(select(KboPitcherAppearance).where(
            KboPitcherAppearance.game_pk.in_(game_ids), KboPitcherAppearance.team_code.in_(own_codes),
        ).order_by(KboPitcherAppearance.appearance_order))).all())
        for row in appearances:
            if not row.pitcher_id:
                continue
            record = season_pitcher_by_id.get(row.pitcher_id)
            candidates.append({"pitcher_id": row.pitcher_id, "pitcher_name": row.pitcher_name,
                               "appearance_order": row.appearance_order, "identity_status": row.pitcher_id_source or "UNVERIFIED",
                               "game_fields": {key: str(value) for key, value in (("타자", row.batters_faced), ("투구수", row.pitches), ("삼진", row.strikeouts), ("볼넷", row.walks)) if value is not None},
                               "season_fields": record.raw_fields if record else {}})
    game_pa = list((await session.scalars(select(KboPlateAppearance).where(
        KboPlateAppearance.game_pk.in_(game_ids),
        KboPlateAppearance.season == game.season,
        KboPlateAppearance.game_date == game.game_date,
        KboPlateAppearance.fielding_team_code.in_(own_codes),
        KboPlateAppearance.batting_team_code.in_(opponent_codes),
    ).order_by(KboPlateAppearance.at_bat_number))).all())
    game_pa, conflicting_pa = _deduplicate_game_plate_appearances(game_pa)
    if not candidates:
        observed_ids = dict.fromkeys(row.pitcher_id for row in game_pa)
        for order, observed_id in enumerate(observed_ids, start=1):
            first = next(row for row in game_pa if row.pitcher_id == observed_id)
            record = season_pitcher_by_id.get(observed_id)
            candidates.append({"pitcher_id": observed_id, "pitcher_name": first.pitcher_name, "appearance_order": order,
                               "identity_status": "PBP_OBSERVED", "game_fields": {},
                               "season_fields": record.raw_fields if record else {}})
    selected = next((row for row in candidates if row["pitcher_id"] == pitcher_id), None) if pitcher_id else next(iter(candidates), None)
    if pitcher_id and selected is None:
        raise ValueError("선택한 투수는 이 경기에서 등판이 확인되지 않아요.")
    selected_pa = [row for row in game_pa if selected and row.pitcher_id == selected["pitcher_id"]]
    by_batter: dict[str, list[KboPlateAppearance]] = defaultdict(list)
    for row in selected_pa:
        by_batter[row.batter_id].append(row)
    lineup = list((await session.scalars(select(KboGameLineup).where(
        KboGameLineup.game_pk == game_pk, KboGameLineup.team_code.in_(opponent_codes),
    ).order_by(KboGameLineup.batting_order, KboGameLineup.is_starter.desc(), KboGameLineup.id))).all())
    batters = []
    for row in lineup:
        record = season_batter_by_id.get(row.player_id)
        batters.append({
            "batter_id": row.player_id, "batter_name": row.player_name, "batting_order": row.batting_order,
            "is_starter": row.is_starter, "position": row.position, "game_fields": row.raw_fields,
            "season_fields": record.raw_fields if record else {},
            "direct_matchup": _direct_counts(by_batter[row.player_id]) if row.player_id in by_batter else None,
        })
    # Unlinked IDs are kept separate; a matching name never substitutes for a verified ID.
    known_batter_ids = {row["batter_id"] for row in batters}
    for row in game_pa:
        if row.batter_id in known_batter_ids:
            continue
        known_batter_ids.add(row.batter_id)
        record = season_batter_by_id.get(row.batter_id)
        batters.append({"batter_id": row.batter_id, "batter_name": row.batter_name, "batting_order": None,
                        "is_starter": None, "position": None, "game_fields": {},
                        "season_fields": record.raw_fields if record else {},
                        "direct_matchup": _direct_counts(by_batter[row.batter_id]) if row.batter_id in by_batter else None})
    return {
        "game": {"game_pk": game.game_pk, "season": game.season, "game_date": game.game_date.isoformat(),
                 "home_team_code": game.home_team_code, "away_team_code": game.away_team_code,
                 "home_score": game.home_score, "away_score": game.away_score, "status": game.status},
        "team_code": normalize_official_team_code(team_code), "opponent_team_code": normalize_official_team_code(opponent),
        "pitchers": candidates, "selected_pitcher": selected, "batters": batters,
        "direct_matchup_available": bool(selected_pa),
        "direct_totals": _direct_counts(selected_pa) if selected_pa else None,
        "note": "경기 타격 성적은 상대팀 전체 투수를 상대로 기록한 성적이에요. 선택한 투수 상대 기록은 같은 경기의 투수·타자 ID가 확인된 타석만 별도로 표시해요." + (f" 중복 경기 식별자에서 결과가 다른 {conflicting_pa}개 타석은 집계에서 제외했어요." if conflicting_pa else ""),
        "data_warnings": [f"중복 경기 식별자에서 결과가 다른 {conflicting_pa}개 타석은 집계에서 제외했어요."] if conflicting_pa else [],
    }


async def get_matchup_games_for_date(
    session: AsyncSession,
    *,
    team_code: str,
    season: int,
    game_date: date,
) -> dict[str, Any]:
    """경기 기록지의 선발 타순을 우선 제공하고 확인되지 않은 타순을 만들지 않는다."""
    if game_date.year != season:
        raise ValueError("기준일과 시즌 연도가 일치해야 합니다.")
    own_team = team_code.strip().upper()
    own_codes = game_team_code_candidates(own_team)
    games = (await session.scalars(
        select(KboGame).where(
            KboGame.season == season,
            KboGame.game_date == game_date,
            or_(KboGame.home_team_code.in_(own_codes), KboGame.away_team_code.in_(own_codes)),
        ).order_by(KboGame.game_pk)
    )).all()
    output = []
    for game in games:
        is_home = game.home_team_code in own_codes
        opponent = game.away_team_code if is_home else game.home_team_code
        opponent_pbp_code = normalize_official_team_code(opponent)
        game_ids = game_pk_candidates(game.game_pk, season=game.season, game_date=game.game_date,
                                      home_team_code=game.home_team_code, away_team_code=game.away_team_code)
        season_batters = await _season_records(session, season=season, team_code=opponent, category="batter")
        season_by_id = {row.player_id: row for row in season_batters}
        lineup_rows = list((await session.scalars(select(KboGameLineup).where(
            KboGameLineup.game_pk == game.game_pk,
            KboGameLineup.team_code.in_(game_team_code_candidates(opponent)),
            KboGameLineup.is_starter.is_(True),
        ).order_by(KboGameLineup.batting_order))).all())
        rows = list((await session.scalars(
            select(KboPlateAppearance).where(
                KboPlateAppearance.game_pk.in_(game_ids),
                KboPlateAppearance.season == season,
                KboPlateAppearance.game_date == game.game_date,
                KboPlateAppearance.batting_team_code.in_(game_team_code_candidates(opponent_pbp_code)),
                KboPlateAppearance.fielding_team_code.in_(own_codes),
            ).order_by(KboPlateAppearance.at_bat_number)
        )).all())
        rows, _ = _deduplicate_game_plate_appearances(rows)
        batters_by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            batter_id, name, stand = row.batter_id, row.batter_name, row.batter_stand
            batter = batters_by_id.setdefault(batter_id, {
                "batter_id": batter_id,
                "batter_name": name,
                "batter_stand": stand,
                "last_seen_date": game.game_date.isoformat(),
            })
            if batter["batter_stand"] is None and stand:
                batter["batter_stand"] = stand
        if lineup_rows:
            batters = [{
                "batter_id": row.player_id, "batter_name": row.player_name, "batter_stand": None,
                "last_seen_date": game.game_date.isoformat(), "batting_order": row.batting_order,
                "position": row.position, "game_fields": row.raw_fields,
                "season_fields": season_by_id[row.player_id].raw_fields if row.player_id in season_by_id else {},
            } for row in lineup_rows]
            lineup_source = "KBO_GAME_BOXSCORE"
        elif batters_by_id:
            batters = [{**row, "batting_order": index, "season_fields": season_by_id[row["batter_id"]].raw_fields if row["batter_id"] in season_by_id else {}} for index, row in enumerate(list(batters_by_id.values())[:9], start=1)]
            lineup_source = "OBSERVED_BATTERS_FROM_GAME_PBP"
        else:
            batters = []
            lineup_source = "LINEUP_NOT_LOADED"
        roster = [{"batter_id": row.player_id, "batter_name": row.player_name, "batter_stand": None,
                   "last_seen_date": None, "season_fields": row.raw_fields} for row in season_batters]
        output.append({
            "game_pk": game.game_pk,
            "game_date": game.game_date.isoformat(),
            "home_team_code": game.home_team_code,
            "away_team_code": game.away_team_code,
            "opponent_team_code": opponent,
            "home_score": game.home_score,
            "away_score": game.away_score,
            "status": game.status,
            "lineup_source": lineup_source,
            "batters": batters,
            "batters_count": len(batters),
            "available_batters": roster,
        })
    return {
        "team_code": own_team,
        "season": season,
        "game_date": game_date.isoformat(),
        "count": len(output),
        "data": output,
        "note": "경기 기록지가 적재되면 선발 타순을 표시합니다. 대체 명단은 시즌 선수 명단이며 확인된 선발 타순과 구분합니다.",
    }


async def search_opponent_batters(
    session: AsyncSession,
    *,
    opponent_team_code: str,
    season: int,
    as_of_date: date,
    query: str | None = None,
) -> dict[str, Any]:
    if as_of_date.year != season:
        raise ValueError("기준일과 시즌 연도가 일치해야 합니다.")
    opponent = normalize_official_team_code(opponent_team_code)
    statement = select(
        KboPlateAppearance.batter_id,
        KboPlateAppearance.batter_name,
        KboPlateAppearance.batter_stand,
        KboPlateAppearance.game_date,
    ).where(
        KboPlateAppearance.season == season,
        KboPlateAppearance.game_date < as_of_date,
        KboPlateAppearance.batting_team_code == opponent,
    ).order_by(KboPlateAppearance.game_date.desc())
    rows = (await session.execute(statement)).all()
    by_id: dict[str, dict[str, Any]] = {}
    for batter_id, name, stand, game_date in rows:
        if query and query.casefold() not in name.casefold():
            continue
        current = by_id.setdefault(batter_id, {
            "batter_id": batter_id,
            "batter_name": name,
            "batter_stand": stand,
            "last_seen_date": game_date.isoformat(),
        })
        if current["batter_stand"] is None and stand:
            current["batter_stand"] = stand
    return {
        "opponent_team_code": opponent,
        "season": season,
        "as_of_date": as_of_date.isoformat(),
        "lineup_source": "HISTORICAL_BATTING_RECORDS_NOT_OFFICIAL_LINEUP",
        "count": len(by_id),
        "data": sorted(by_id.values(), key=lambda row: row["batter_name"]),
        "note": "선수 목록은 기준일 이전 기록에 등장한 타자이며, 당일 출전/예정 타순을 뜻하지 않습니다.",
    }


def parse_complete_plate_appearances(
    rows: Iterable[dict[str, Any]],
    *,
    season: int,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """투구 행을 단일 타자·투수·결과가 확인된 완료 타석으로 축약한다."""
    grouped: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    quality = {
        "pitch_rows": 0,
        "plate_appearances_seen": 0,
        "duplicate_pitches": 0,
        "conflicting_pitches": 0,
        "incomplete": 0,
        "mixed_pitchers": 0,
        "invalid_identity": 0,
        "invalid_team_side": 0,
        "accepted": 0,
    }
    seen_pitches: dict[tuple[str, int, int], dict[str, Any]] = {}
    conflicted: set[tuple[str, int, int]] = set()
    for row in rows:
        quality["pitch_rows"] += 1
        game_date = str(row.get("game_date") or "")
        if not game_date.startswith(f"{season}-"):
            continue
        try:
            game_pk = str(row["game_pk"])
            ab = int(row["at_bat_number"])
            pitch_no = int(row["pitch_number"])
        except (KeyError, TypeError, ValueError):
            quality["invalid_identity"] += 1
            continue
        if not game_pk or ab < 1 or pitch_no < 0:
            quality["invalid_identity"] += 1
            continue
        pitch_key = (game_pk, ab, pitch_no)
        previous = seen_pitches.get(pitch_key)
        if previous is not None:
            if previous == row:
                quality["duplicate_pitches"] += 1
            else:
                conflicted.add(pitch_key)
                quality["conflicting_pitches"] += 1
            continue
        seen_pitches[pitch_key] = row
        grouped[(game_pk, ab)].append(row)

    quality["plate_appearances_seen"] = len(grouped)
    accepted: list[dict[str, Any]] = []
    for (game_pk, ab), pitches in grouped.items():
        if any((game_pk, ab, int(p["pitch_number"])) in conflicted for p in pitches):
            quality["conflicting_pitches"] += 0
            quality["incomplete"] += 1
            continue
        event_values = {str(p["events"]) for p in pitches if p.get("events") not in (None, "")}
        pitchers = {str(p.get("pitcher") or "") for p in pitches}
        batters = {str(p.get("batter") or "") for p in pitches}
        if not event_values:
            quality["incomplete"] += 1
            continue
        if len(pitchers) != 1 or "" in pitchers:
            quality["mixed_pitchers"] += 1
            continue
        if len(batters) != 1 or "" in batters or len(event_values) != 1:
            quality["invalid_identity"] += 1
            continue

        ordered = sorted(pitches, key=lambda p: int(p["pitch_number"]))
        last = ordered[-1]
        side = last.get("inning_topbot")
        home = last.get("home_team")
        away = last.get("away_team")
        batting_team = away if side == "top" else home if side == "bot" else None
        fielding_team = home if side == "top" else away if side == "bot" else None
        if not batting_team or not fielding_team:
            quality["invalid_team_side"] += 1
            continue
        try:
            game_day = date.fromisoformat(str(last["game_date"])[:10])
            inning = int(last["inning"]) if last.get("inning") is not None else None
        except (KeyError, TypeError, ValueError):
            quality["invalid_identity"] += 1
            continue

        batter_id = next(iter(batters))
        pitcher_id = next(iter(pitchers))
        accepted.append({
            "game_pk": game_pk,
            "season": season,
            "game_date": game_day,
            "at_bat_number": ab,
            "inning": inning,
            "inning_topbot": side,
            "batting_team_code": normalize_official_team_code(str(batting_team)),
            "fielding_team_code": normalize_official_team_code(str(fielding_team)),
            "batter_id": batter_id,
            "batter_name": str(last.get("batter_name") or batter_id),
            "batter_stand": next((p.get("stand") for p in ordered if p.get("stand") in {"L", "R", "S"}), None),
            "pitcher_id": pitcher_id,
            "pitcher_name": str(last.get("pitcher_name") or pitcher_id),
            "event": next(iter(event_values)),
        })
        quality["accepted"] += 1
    accepted.sort(key=lambda row: (row["game_date"], row["game_pk"], row["at_bat_number"]))
    return accepted, quality


def _sample_tier(pa: int) -> str:
    if pa == 0:
        return "NO_DIRECT_HISTORY"
    if pa < 10:
        return "VERY_SMALL"
    if pa < 30:
        return "LIMITED"
    return "OBSERVATIONAL"


async def analyze_lineup_matchups(
    session: AsyncSession,
    *,
    team_code: str,
    opponent_team_code: str,
    pitcher_ids: list[str],
    batter_ids: list[str],
    season: int,
    as_of_date: date,
) -> dict[str, Any]:
    if as_of_date.year != season:
        raise ValueError("기준일과 시즌 연도가 일치해야 합니다.")
    own_team = normalize_official_team_code(team_code)
    opponent = normalize_official_team_code(opponent_team_code)
    if own_team == opponent:
        raise ValueError("상대 구단은 로그인한 구단과 달라야 합니다.")

    valid_pitchers = set((await session.scalars(
        select(KboPitcherAppearance.pitcher_id).where(
            KboPitcherAppearance.team_code.in_(game_team_code_candidates(own_team)),
            KboPitcherAppearance.pitcher_id.in_(pitcher_ids),
            KboPitcherAppearance.pitcher_id_source.in_(["OFFICIAL_VERIFIED", "TEAM_NAME_UNIQUE"]),
        ).distinct()
    )).all())
    season_pitchers = await _season_records(session, season=season, team_code=own_team, category="pitcher")
    valid_pitchers.update(row.player_id for row in season_pitchers if row.player_id in pitcher_ids)
    if valid_pitchers != set(pitcher_ids):
        raise ValueError("후보 투수 중 로그인 구단에서 확인할 수 없는 ID가 있습니다.")

    pitcher_names = dict((await session.execute(
        select(KboPitcherAppearance.pitcher_id, KboPitcherAppearance.pitcher_name)
        .where(
            KboPitcherAppearance.team_code.in_(game_team_code_candidates(own_team)),
            KboPitcherAppearance.pitcher_id.in_(pitcher_ids),
        )
        .order_by(KboPitcherAppearance.pitcher_id)
    )).all())
    pitcher_names.update({row.player_id: row.player_name for row in season_pitchers if row.player_id in pitcher_ids})

    statement = select(KboPlateAppearance).where(
        KboPlateAppearance.season == season,
        KboPlateAppearance.game_date < as_of_date,
        KboPlateAppearance.batting_team_code.in_(game_team_code_candidates(opponent)),
        KboPlateAppearance.fielding_team_code.in_(game_team_code_candidates(own_team)),
        KboPlateAppearance.batter_id.in_(batter_ids),
        KboPlateAppearance.pitcher_id.in_(pitcher_ids),
    ).order_by(KboPlateAppearance.game_date, KboPlateAppearance.game_pk, KboPlateAppearance.at_bat_number)
    rows = (await session.scalars(statement)).all()
    by_game: dict[tuple[date, str], list[KboPlateAppearance]] = defaultdict(list)
    for row in rows:
        by_game[(row.game_date, canonical_game_pk(row.game_pk) or row.game_pk)].append(row)
    rows = []
    historical_conflicts = 0
    for game_rows in by_game.values():
        accepted, conflicts = _deduplicate_game_plate_appearances(game_rows)
        rows.extend(accepted)
        historical_conflicts += conflicts

    batter_names: dict[str, str] = {}
    grouped: dict[tuple[str, str], list[KboPlateAppearance]] = defaultdict(list)
    for row in rows:
        batter_names[row.batter_id] = row.batter_name
        if row.fielding_team_code in game_team_code_candidates(own_team):
            grouped[(row.pitcher_id, row.batter_id)].append(row)

    # The target game's lineup can include a player with no earlier season record.
    # Validate identities through the selected date while keeping matchup stats
    # strictly before that date.
    known_batters = set((await session.scalars(
        select(KboPlateAppearance.batter_id).where(
            KboPlateAppearance.season == season,
            KboPlateAppearance.game_date <= as_of_date,
            KboPlateAppearance.batting_team_code.in_(game_team_code_candidates(opponent)),
            KboPlateAppearance.batter_id.in_(batter_ids),
        ).distinct()
    )).all())
    boxscore_batters = list((await session.scalars(select(KboGameLineup).where(
        KboGameLineup.season == season,
        KboGameLineup.game_date <= as_of_date,
        KboGameLineup.team_code.in_(game_team_code_candidates(opponent)),
        KboGameLineup.player_id.in_(batter_ids),
    ))).all())
    known_batters.update(row.player_id for row in boxscore_batters)
    season_batters = await _season_records(session, season=season, team_code=opponent, category="batter")
    known_batters.update(row.player_id for row in season_batters if row.player_id in batter_ids)
    if known_batters != set(batter_ids):
        raise ValueError("상대 타순에 기준일까지 상대 구단 경기에서 확인되지 않는 타자 ID가 있습니다.")
    # Names can use the selected game's identity record; matchup statistics above
    # remain restricted to prior dates.
    all_names = (await session.execute(
        select(KboPlateAppearance.batter_id, KboPlateAppearance.batter_name)
        .where(
            KboPlateAppearance.season == season,
            KboPlateAppearance.game_date <= as_of_date,
            KboPlateAppearance.batting_team_code.in_(game_team_code_candidates(opponent)),
            KboPlateAppearance.batter_id.in_(batter_ids),
        )
        .order_by(KboPlateAppearance.game_date.desc())
    )).all()
    for batter_id, name in all_names:
        batter_names.setdefault(batter_id, name)
    for row in boxscore_batters:
        batter_names.setdefault(row.player_id, row.player_name)
    for row in season_batters:
        batter_names.setdefault(row.player_id, row.player_name)

    batch = (await session.scalars(
        select(DataImportBatch)
        .where(
            DataImportBatch.dataset == "kbo_plate_appearances",
            DataImportBatch.season == season,
            DataImportBatch.status.in_(["SUCCESS", "PARTIAL"]),
        )
        .order_by(DataImportBatch.imported_at.desc(), DataImportBatch.id.desc())
        .limit(1)
    )).first()

    comparisons = []
    totals: dict[str, dict[str, int]] = {
        pitcher_id: {"pa": 0, "hits": 0, "strikeouts": 0, "walks": 0, "home_runs": 0, "hit_by_pitch": 0}
        for pitcher_id in pitcher_ids
    }
    for pitcher_id in pitcher_ids:
        for order, batter_id in enumerate(batter_ids, start=1):
            matchups = grouped.get((pitcher_id, batter_id), [])
            counts = _direct_counts(matchups)
            pa = counts["plate_appearances"]
            hits = counts["hits"]
            strikeouts = counts["strikeouts"]
            walks = counts["walks"]
            home_runs = counts["home_runs"]
            hbp = counts["hit_by_pitch"]
            comparisons.append({
                "lineup_order": order,
                "batter_id": batter_id,
                "batter_name": batter_names.get(batter_id, batter_id),
                "batter_stand": next((row.batter_stand for row in matchups if row.batter_stand), None),
                "pitcher_id": pitcher_id,
                "pitcher_name": pitcher_names.get(pitcher_id, pitcher_id),
                "plate_appearances": pa,
                "hits": hits,
                "strikeouts": strikeouts,
                "walks": walks,
                "home_runs": home_runs,
                "hit_by_pitch": hbp,
                "game_count": len({(row.game_date, canonical_game_pk(row.game_pk) or row.game_pk) for row in matchups}),
                "first_seen_date": min((row.game_date for row in matchups), default=None).isoformat() if matchups else None,
                "last_seen_date": max((row.game_date for row in matchups), default=None).isoformat() if matchups else None,
                "history_events": [{"game_pk": canonical_game_pk(row.game_pk) or row.game_pk,
                                    "game_date": row.game_date.isoformat(), "inning": row.inning,
                                    "at_bat_number": row.at_bat_number, "event": row.event}
                                   for row in sorted(matchups, key=lambda row: (row.game_date, row.game_pk, row.at_bat_number), reverse=True)],
                "sample_tier": _sample_tier(pa),
                "interpretation": "직접 맞대결 표본이 없습니다." if pa == 0 else "직접 맞대결 기록이며 투수 우열/미래 결과를 뜻하지 않습니다." if pa < 10 else "직접 맞대결 기록입니다. 소표본은 참고 수준입니다." if pa < 30 else "관측된 직접 맞대결 기록입니다. 인과적 효과를 뜻하지 않습니다.",
            })
            for key, value in (("pa", pa), ("hits", hits), ("strikeouts", strikeouts), ("walks", walks), ("home_runs", home_runs), ("hit_by_pitch", hbp)):
                totals[pitcher_id][key] += value

    return {
        "team_code": own_team,
        "opponent_team_code": opponent,
        "season": season,
        "as_of_date": as_of_date.isoformat(),
        "date_boundary": "game_date < as_of_date; all games on as_of_date are excluded",
        "lineup_source": "KBO_GAME_BOXSCORE" if boxscore_batters else "KBO_SEASON_ROSTER" if not all_names else "OBSERVED_GAME_PBP",
        "pitcher_hand": "UNAVAILABLE",
        "coverage": "PARTIAL_SOURCE_WINDOW",
        "data_snapshot_id": batch.id if batch else None,
        "source_name": batch.source_name if batch else None,
        "source_date_range": {
            "from": (batch.quality_summary or {}).get("date_min"),
            "through": (batch.quality_summary or {}).get("date_max"),
        } if batch else None,
        "data_through_date": max((row.game_date for row in rows), default=None).isoformat() if rows else None,
        "totals_by_pitcher": [
            {"pitcher_id": pitcher_id, "pitcher_name": pitcher_names.get(pitcher_id, pitcher_id), **totals[pitcher_id]}
            for pitcher_id in pitcher_ids
        ],
        "matchups": comparisons,
        "season_batter_records": [{"player_id": row.player_id, "player_name": row.player_name, "raw_fields": row.raw_fields} for row in season_batters if row.player_id in batter_ids],
        "season_reference_note": "시즌 기록은 최근 적재된 정규시즌 누적 성적이며 선택 경기일 이전 누적 성적과 다릅니다. 직접 맞대결 통계에는 사용하지 않습니다.",
        "data_warnings": [f"중복 경기 식별자에서 결과가 다른 {historical_conflicts}개 타석은 이전 맞대결 집계에서 제외했어요."] if historical_conflicts else [],
        "limitations": [
            "경기 기록지의 타순과 직접 선택한 타순을 구분해 확인해 주세요.",
            "데이터에 투수 투구 손이 없어 좌우 스플릿을 계산하지 않았습니다.",
            "직접 맞대결 표본은 예측 점수나 교체 성공 확률이 아닙니다.",
            "직접 맞대결은 적재된 타석 기록 범위에 한합니다. 시즌 기록이나 경기 기록지를 직접 맞대결 표본으로 합산하지 않습니다.",
        ],
    }
