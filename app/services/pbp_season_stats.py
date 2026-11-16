"""PBP 완료 타석에서 계산한 시즌 타자·투수 기록.

이 집계는 단일 타자·투수·결과가 확인된 타석만 사용하며 KBO 공식 기록이 아니다.
"""
from datetime import date
from typing import Any

from sqlalchemy import and_, case, distinct, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_import_batch import DataImportBatch
from app.models.kbo_plate_appearance import KboPlateAppearance
from app.models.kbo_pitch_event import KboPitchEvent
from app.services.team_codes import normalize_official_team_code


HITS = ("single", "double", "triple", "home_run")
KNOWN_EVENTS = HITS + (
    "field_out", "strikeout", "fielders_choice", "double_play", "walk",
    "hit_by_pitch", "field_error", "sac_fly", "sac_bunt", "catcher_interference",
)
AB_EVENTS = HITS + ("field_out", "strikeout", "fielders_choice", "double_play", "field_error")


def _sum_event(event_column, *events):
    return func.coalesce(func.sum(case((event_column.in_(events), 1), else_=0)), 0)


def _percentage(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 3) if denominator else None


async def _snapshot(session: AsyncSession, season: int) -> dict[str, Any]:
    batch = await session.scalar(
        select(DataImportBatch)
        .where(
            DataImportBatch.dataset == "kbo_plate_appearances",
            DataImportBatch.season == season,
            DataImportBatch.status.in_(("SUCCESS", "PARTIAL")),
        )
        .order_by(DataImportBatch.imported_at.desc(), DataImportBatch.id.desc())
        .limit(1)
    )
    if batch is None:
        return {"snapshot_id": None, "source_name": None, "quality_summary": {}}
    return {
        "snapshot_id": batch.id,
        "source_name": batch.source_name,
        "quality_summary": batch.quality_summary or {},
    }


async def _scope_coverage(
    session: AsyncSession,
    *,
    season: int,
    team_code: str,
    date_column,
    team_column,
    as_of_date: date | None,
) -> dict[str, Any]:
    query = select(
        func.min(date_column),
        func.max(date_column),
        func.count(),
    ).where(
        KboPlateAppearance.season == season,
        team_column == team_code,
    )
    if as_of_date is not None:
        query = query.where(date_column < as_of_date)
    date_min, date_max, record_count = (await session.execute(query)).one()
    return {
        "date_min": date_min.isoformat() if date_min else None,
        "date_max": date_max.isoformat() if date_max else None,
        "accepted_plate_appearances": int(record_count or 0),
    }


async def get_team_batting_stats(
    session: AsyncSession,
    *,
    season: int,
    team_code: str,
    as_of_date: date | None = None,
    name: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    team = normalize_official_team_code(team_code)
    event = KboPlateAppearance.event
    ab_case = case((event.in_(AB_EVENTS), 1), else_=0)
    unknown_case = case((event.not_in(KNOWN_EVENTS), 1), else_=0)
    query = (
        select(
            KboPlateAppearance.batter_id.label("player_id"),
            KboPlateAppearance.batter_name.label("player_name"),
            KboPlateAppearance.batting_team_code.label("team_code"),
            func.count().label("plate_appearances"),
            func.count(distinct(KboPlateAppearance.game_pk)).label("games"),
            func.coalesce(func.sum(ab_case), 0).label("at_bats"),
            _sum_event(event, *HITS).label("hits"),
            _sum_event(event, "single").label("singles"),
            _sum_event(event, "double").label("doubles"),
            _sum_event(event, "triple").label("triples"),
            _sum_event(event, "home_run").label("home_runs"),
            _sum_event(event, "walk").label("walks"),
            _sum_event(event, "strikeout").label("strikeouts"),
            _sum_event(event, "hit_by_pitch").label("hit_by_pitch"),
            _sum_event(event, "sac_fly").label("sacrifice_flies"),
            _sum_event(event, "sac_bunt").label("sacrifice_bunts"),
            func.coalesce(func.sum(unknown_case), 0).label("unclassified_outcomes"),
        )
        .where(
            KboPlateAppearance.season == season,
            KboPlateAppearance.batting_team_code == team,
        )
    )
    if as_of_date is not None:
        if as_of_date.year != season:
            raise ValueError("기준일과 시즌 연도가 일치해야 합니다.")
        query = query.where(KboPlateAppearance.game_date < as_of_date)
    if name and name.strip():
        query = query.where(KboPlateAppearance.batter_name.ilike(f"%{name.strip()}%"))
    query = (
        query.group_by(
            KboPlateAppearance.batter_id,
            KboPlateAppearance.batter_name,
            KboPlateAppearance.batting_team_code,
        )
        .order_by(func.count().desc(), KboPlateAppearance.batter_name)
        .limit(limit)
    )
    rows = (await session.execute(query)).all()
    data = []
    for row in rows:
        pa = int(row.plate_appearances or 0)
        ab = int(row.at_bats or 0)
        hits = int(row.hits or 0)
        walks = int(row.walks or 0)
        hbp = int(row.hit_by_pitch or 0)
        sf = int(row.sacrifice_flies or 0)
        total_bases = (
            int(row.singles or 0)
            + 2 * int(row.doubles or 0)
            + 3 * int(row.triples or 0)
            + 4 * int(row.home_runs or 0)
        )
        obp_denominator = ab + walks + hbp + sf
        obp = _percentage(hits + walks + hbp, obp_denominator)
        slg = _percentage(total_bases, ab)
        data.append({
            "player_id": row.player_id,
            "player_name": row.player_name,
            "team_code": row.team_code,
            "games": int(row.games or 0),
            "plate_appearances": pa,
            "at_bats": ab,
            "hits": hits,
            "singles": int(row.singles or 0),
            "doubles": int(row.doubles or 0),
            "triples": int(row.triples or 0),
            "home_runs": int(row.home_runs or 0),
            "walks": walks,
            "strikeouts": int(row.strikeouts or 0),
            "hit_by_pitch": hbp,
            "sacrifice_flies": sf,
            "sacrifice_bunts": int(row.sacrifice_bunts or 0),
            "unclassified_outcomes": int(row.unclassified_outcomes or 0),
            "total_bases": total_bases,
            "batting_average": _percentage(hits, ab),
            "on_base_percentage": obp,
            "slugging_percentage": slg,
            "ops": round(obp + slg, 3) if obp is not None and slg is not None else None,
        })

    snapshot = await _snapshot(session, season)
    coverage = await _scope_coverage(
        session,
        season=season,
        team_code=team,
        date_column=KboPlateAppearance.game_date,
        team_column=KboPlateAppearance.batting_team_code,
        as_of_date=as_of_date,
    )
    return {
        "season": season,
        "team_code": team,
        "as_of_date": as_of_date.isoformat() if as_of_date else None,
        "cutoff": "EXCLUSIVE" if as_of_date else None,
        "stat_source": "PBP_DERIVED",
        "stat_definition": "완료 타석 PBP 기준. 타율=안타/타수, 출루율=(안타+볼넷+사구)/(타수+볼넷+사구+희생플라이), 장타율=루타/타수.",
        "snapshot_id": snapshot["snapshot_id"],
        "source_name": snapshot["source_name"],
        "coverage": coverage,
        "count": len(data),
        "data": data,
        "limitations": [
            "KBO 공식 시즌 기록이 아닌 PBP 파생 집계입니다.",
            "단일 타자·투수·타석 결과가 확인된 완료 타석만 포함합니다.",
            "타점, 득점, 도루와 수비 기록은 이 집계에 포함하지 않습니다.",
        ],
    }


async def search_team_batters(
    session: AsyncSession,
    *,
    season: int,
    team_code: str,
    as_of_date: date,
    name: str,
    limit: int = 20,
) -> dict[str, Any]:
    if as_of_date.year != season:
        raise ValueError("기준일과 시즌 연도가 일치해야 합니다.")
    result = await get_team_batting_stats(
        session,
        season=season,
        team_code=team_code,
        as_of_date=as_of_date,
        name=name,
        limit=limit,
    )
    return {
        **result,
        "note": "선수 이름과 지표는 PBP 파생 기록입니다. 표본 수와 기준일을 함께 해석하세요.",
    }


async def get_team_pbp_pitching_stats(
    session: AsyncSession,
    *,
    season: int,
    team_code: str,
    as_of_date: date | None = None,
    name: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    team = normalize_official_team_code(team_code)
    event = KboPlateAppearance.event
    query = (
        select(
            KboPlateAppearance.pitcher_id.label("player_id"),
            KboPlateAppearance.pitcher_name.label("player_name"),
            KboPlateAppearance.fielding_team_code.label("team_code"),
            func.count().label("batters_faced"),
            func.count(distinct(KboPlateAppearance.game_pk)).label("games"),
            _sum_event(event, *HITS).label("hits_allowed"),
            _sum_event(event, "home_run").label("home_runs_allowed"),
            _sum_event(event, "walk").label("walks"),
            _sum_event(event, "strikeout").label("strikeouts"),
            _sum_event(event, "hit_by_pitch").label("hit_batters"),
        )
        .where(
            KboPlateAppearance.season == season,
            KboPlateAppearance.fielding_team_code == team,
        )
    )
    if as_of_date is not None:
        if as_of_date.year != season:
            raise ValueError("기준일과 시즌 연도가 일치해야 합니다.")
        query = query.where(KboPlateAppearance.game_date < as_of_date)
    if name and name.strip():
        query = query.where(KboPlateAppearance.pitcher_name.ilike(f"%{name.strip()}%"))
    query = (
        query.group_by(
            KboPlateAppearance.pitcher_id,
            KboPlateAppearance.pitcher_name,
            KboPlateAppearance.fielding_team_code,
        )
        .order_by(func.count().desc(), KboPlateAppearance.pitcher_name)
        .limit(limit)
    )
    rows = (await session.execute(query)).all()
    data_by_pitcher: dict[tuple[str, str], dict[str, Any]] = {}
    for row in rows:
        bf = int(row.batters_faced or 0)
        strikeouts = int(row.strikeouts or 0)
        walks = int(row.walks or 0)
        data_by_pitcher[(row.player_id, row.team_code)] = {
            "player_id": row.player_id,
            "player_name": row.player_name,
            "team_code": row.team_code,
            "games": int(row.games or 0),
            "batters_faced": bf,
            "pitch_count": 0,
            "avg_release_speed_kmh": None,
            "max_release_speed_kmh": None,
            "pitch_mix": {},
            "hits_allowed": int(row.hits_allowed or 0),
            "home_runs_allowed": int(row.home_runs_allowed or 0),
            "walks": walks,
            "strikeouts": strikeouts,
            "hit_batters": int(row.hit_batters or 0),
            "k_pct": round(100 * strikeouts / bf, 2) if bf else None,
            "bb_pct": round(100 * walks / bf, 2) if bf else None,
            "k_minus_bb_pct": round(100 * (strikeouts - walks) / bf, 2) if bf else None,
        }

    fielding_team = case(
        (KboPitchEvent.inning_topbot == "top", KboPitchEvent.home_team_code),
        (KboPitchEvent.inning_topbot == "bot", KboPitchEvent.away_team_code),
        else_=None,
    )
    pitch_query = select(
        KboPitchEvent.pitcher_id,
        KboPitchEvent.pitcher_name,
        fielding_team.label("team_code"),
        KboPitchEvent.pitch_type,
        func.count().label("pitch_count"),
        func.count(KboPitchEvent.release_speed_kmh).label("speed_sample_count"),
        func.avg(KboPitchEvent.release_speed_kmh).label("avg_speed"),
        func.max(KboPitchEvent.release_speed_kmh).label("max_speed"),
    ).where(
        KboPitchEvent.season == season,
        or_(
            and_(
                KboPitchEvent.inning_topbot == "top",
                KboPitchEvent.home_team_code == team,
            ),
            and_(
                KboPitchEvent.inning_topbot == "bot",
                KboPitchEvent.away_team_code == team,
            ),
        ),
    )
    if as_of_date is not None:
        if as_of_date.year != season:
            raise ValueError("기준일과 시즌 연도가 일치해야 합니다.")
        pitch_query = pitch_query.where(KboPitchEvent.game_date < as_of_date)
    if name and name.strip():
        pitch_query = pitch_query.where(KboPitchEvent.pitcher_name.ilike(f"%{name.strip()}%"))
    pitch_query = pitch_query.group_by(
        KboPitchEvent.pitcher_id,
        KboPitchEvent.pitcher_name,
        fielding_team,
        KboPitchEvent.pitch_type,
    )
    pitch_rows = (await session.execute(pitch_query)).all()
    speed_totals: dict[tuple[str, str], list[float]] = {}
    for row in pitch_rows:
        key = (row.pitcher_id, row.team_code)
        pitcher = data_by_pitcher.get(key)
        if pitcher is None:
            continue
        pitcher["pitch_count"] += int(row.pitch_count or 0)
        pitch_type = row.pitch_type or "UNKNOWN"
        pitcher["pitch_mix"][pitch_type] = (
            pitcher["pitch_mix"].get(pitch_type, 0) + int(row.pitch_count or 0)
        )
        if row.speed_sample_count:
            totals = speed_totals.setdefault(key, [0.0, 0.0])
            totals[0] += float(row.avg_speed) * int(row.speed_sample_count)
            totals[1] += int(row.speed_sample_count)
            current_max = pitcher["max_release_speed_kmh"]
            pitcher["max_release_speed_kmh"] = max(
                current_max if current_max is not None else float(row.max_speed),
                float(row.max_speed),
            )
    for key, (weighted_speed_sum, speed_count) in speed_totals.items():
        data_by_pitcher[key]["avg_release_speed_kmh"] = round(
            weighted_speed_sum / speed_count, 1
        )
    data = sorted(
        data_by_pitcher.values(),
        key=lambda row: (-row["batters_faced"], row["player_name"]),
    )[:limit]
    snapshot = await _snapshot(session, season)
    coverage = await _scope_coverage(
        session,
        season=season,
        team_code=team,
        date_column=KboPlateAppearance.game_date,
        team_column=KboPlateAppearance.fielding_team_code,
        as_of_date=as_of_date,
    )
    return {
        "season": season,
        "team_code": team,
        "as_of_date": as_of_date.isoformat() if as_of_date else None,
        "cutoff": "EXCLUSIVE" if as_of_date else None,
        "stat_source": "PBP_DERIVED",
        "stat_definition": "BF·K·BB 등 결과 지표는 완료 타석 PBP, 투구 수·구종 분포·구속은 투구 원본 PBP에서 계산합니다. K%, BB%, K-BB%의 분모는 확인된 완료 타석 수입니다.",
        "snapshot_id": snapshot["snapshot_id"],
        "source_name": snapshot["source_name"],
        "coverage": coverage,
        "count": len(data),
        "data": data,
        "limitations": [
            "KBO 공식 투수 기록이 아닌 PBP 파생 집계입니다.",
            "투수 교체가 포함된 타석은 제외되므로 공식 타자 상대 수와 다를 수 있습니다.",
            "구속 평균은 구속 값이 제공된 투구만 포함합니다.",
            "이닝, 자책점, ERA, WHIP, 세이브와 홀드는 계산하지 않습니다.",
        ],
    }
