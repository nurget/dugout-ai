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
from app.services.team_codes import normalize_official_team_code
from app.services.team_codes import game_team_code_candidates


HITS = {"single", "double", "triple", "home_run"}


async def get_matchup_games_for_date(
    session: AsyncSession,
    *,
    team_code: str,
    season: int,
    game_date: date,
) -> dict[str, Any]:
    """해당 날짜 소속 구단 경기와 PBP에서 관측된 상대 타자를 반환한다."""
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
        rows = (await session.execute(
            select(
                KboPlateAppearance.batter_id,
                KboPlateAppearance.batter_name,
                KboPlateAppearance.batter_stand,
                KboPlateAppearance.at_bat_number,
            ).where(
                KboPlateAppearance.game_pk == game.game_pk,
                KboPlateAppearance.season == season,
                KboPlateAppearance.batting_team_code == opponent_pbp_code,
            ).order_by(KboPlateAppearance.at_bat_number)
        )).all()
        batters_by_id: dict[str, dict[str, Any]] = {}
        for batter_id, name, stand, _ in rows:
            batter = batters_by_id.setdefault(batter_id, {
                "batter_id": batter_id,
                "batter_name": name,
                "batter_stand": stand,
                "last_seen_date": game.game_date.isoformat(),
            })
            if batter["batter_stand"] is None and stand:
                batter["batter_stand"] = stand
        output.append({
            "game_pk": game.game_pk,
            "game_date": game.game_date.isoformat(),
            "home_team_code": game.home_team_code,
            "away_team_code": game.away_team_code,
            "opponent_team_code": opponent,
            "home_score": game.home_score,
            "away_score": game.away_score,
            "status": game.status,
            "lineup_source": "OBSERVED_BATTERS_FROM_GAME_PBP",
            "batters": list(batters_by_id.values()),
            "batters_count": len(batters_by_id),
        })
    return {
        "team_code": own_team,
        "season": season,
        "game_date": game_date.isoformat(),
        "count": len(output),
        "data": output,
        "note": "타순은 해당 경기 PBP에서 첫 타석이 나온 순서로 구성했으며 공식 선발 라인업과 다를 수 있습니다.",
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
            KboPitcherAppearance.team_code == own_team,
            KboPitcherAppearance.pitcher_id.in_(pitcher_ids),
            KboPitcherAppearance.pitcher_id_source.in_(["OFFICIAL_VERIFIED", "TEAM_NAME_UNIQUE"]),
        ).distinct()
    )).all())
    if valid_pitchers != set(pitcher_ids):
        raise ValueError("후보 투수 중 로그인 구단에서 확인할 수 없는 ID가 있습니다.")

    pitcher_names = dict((await session.execute(
        select(KboPitcherAppearance.pitcher_id, KboPitcherAppearance.pitcher_name)
        .where(
            KboPitcherAppearance.team_code == own_team,
            KboPitcherAppearance.pitcher_id.in_(pitcher_ids),
        )
        .order_by(KboPitcherAppearance.pitcher_id)
    )).all())

    statement = select(KboPlateAppearance).where(
        KboPlateAppearance.season == season,
        KboPlateAppearance.game_date < as_of_date,
        KboPlateAppearance.batting_team_code == opponent,
        KboPlateAppearance.batter_id.in_(batter_ids),
        KboPlateAppearance.pitcher_id.in_(pitcher_ids),
    ).order_by(KboPlateAppearance.game_date, KboPlateAppearance.game_pk, KboPlateAppearance.at_bat_number)
    rows = (await session.scalars(statement)).all()

    batter_names: dict[str, str] = {}
    grouped: dict[tuple[str, str], list[KboPlateAppearance]] = defaultdict(list)
    for row in rows:
        batter_names[row.batter_id] = row.batter_name
        if row.fielding_team_code == own_team:
            grouped[(row.pitcher_id, row.batter_id)].append(row)

    # The target game's lineup can include a player with no earlier season record.
    # Validate identities through the selected date while keeping matchup stats
    # strictly before that date.
    known_batters = set((await session.scalars(
        select(KboPlateAppearance.batter_id).where(
            KboPlateAppearance.season == season,
            KboPlateAppearance.game_date <= as_of_date,
            KboPlateAppearance.batting_team_code == opponent,
            KboPlateAppearance.batter_id.in_(batter_ids),
        ).distinct()
    )).all())
    if known_batters != set(batter_ids):
        raise ValueError("상대 타순에 기준일까지 상대 구단 경기에서 확인되지 않는 타자 ID가 있습니다.")
    # Names can use the selected game's identity record; matchup statistics above
    # remain restricted to prior dates.
    all_names = (await session.execute(
        select(KboPlateAppearance.batter_id, KboPlateAppearance.batter_name)
        .where(
            KboPlateAppearance.season == season,
            KboPlateAppearance.game_date <= as_of_date,
            KboPlateAppearance.batting_team_code == opponent,
            KboPlateAppearance.batter_id.in_(batter_ids),
        )
        .order_by(KboPlateAppearance.game_date.desc())
    )).all()
    for batter_id, name in all_names:
        batter_names.setdefault(batter_id, name)

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
            event_counts = Counter(row.event for row in matchups)
            pa = len(matchups)
            hits = sum(event_counts[event] for event in HITS)
            strikeouts = event_counts["strikeout"]
            walks = event_counts["walk"]
            home_runs = event_counts["home_run"]
            hbp = event_counts["hit_by_pitch"]
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
        "lineup_source": "OBSERVED_GAME_PBP",
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
        "limitations": [
            "타순은 해당 날짜 경기 PBP에서 첫 타석이 나온 순서이며 공식 선발 라인업 피드로 검증하지 않았습니다.",
            "데이터에 투수 투구 손이 없어 좌우 스플릿을 계산하지 않았습니다.",
            "직접 맞대결 표본은 예측 점수나 교체 성공 확률이 아닙니다.",
            "원천 데이터는 2026년 7월 26일까지이며, 그 이후 경기와 현재 라인업을 포함하지 않습니다.",
        ],
    }
