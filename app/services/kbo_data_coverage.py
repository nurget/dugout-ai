"""User-facing coverage summary for the separately sourced KBO datasets."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.kbo import KboGame
from app.models.kbo_game_lineup import KboGameBoxscore, KboGameLineup
from app.models.kbo_pitch_event import KboPitchEvent
from app.models.kbo_plate_appearance import KboPlateAppearance
from app.models.kbo_player_record import KboPlayerRecord
from app.models.kbo_team_record import KboTeamRecord
from app.services.kbo_game_identity import canonical_game_pk
from app.services.kbo_player_records import canonical_team_code, team_code_aliases


COMPLETE_GAME_STATUSES = {"final", "completed", "종료", "경기종료", "경기 종료"}
TEAM_RECORD_CATEGORIES = {"standings", "batting", "pitching", "defense", "running"}


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None else None


def _rate(loaded: int, expected: int) -> float | None:
    return round(loaded / expected * 100, 1) if expected else None


def _coverage_status(loaded: int, expected: int) -> str:
    if loaded <= 0:
        return "EMPTY"
    if expected > 0 and loaded >= expected:
        return "COMPLETE"
    return "PARTIAL"


def _canonical_ids(values: Iterable[str]) -> set[str]:
    return {canonical_game_pk(value) or value for value in values}


async def get_data_coverage(
    session: AsyncSession,
    *,
    season: int,
    team_code: str | None = None,
) -> dict[str, Any]:
    aliases = team_code_aliases(team_code) if team_code else None

    game_query = select(KboGame).where(
        KboGame.season == season,
        KboGame.season_type == "REGULAR",
    )
    if aliases:
        game_query = game_query.where(
            or_(KboGame.home_team_code.in_(aliases), KboGame.away_team_code.in_(aliases))
        )
    games = list((await session.scalars(game_query.order_by(KboGame.game_date, KboGame.game_pk))).all())
    completed_games = [
        game for game in games if game.status.strip().casefold() in COMPLETE_GAME_STATUSES
    ]
    completed_ids = _canonical_ids(game.game_pk for game in completed_games)
    game_ids = [game.game_pk for game in games]

    player_query = select(
        KboPlayerRecord.category,
        func.count(KboPlayerRecord.id),
        func.max(KboPlayerRecord.collected_at),
        func.max(KboPlayerRecord.imported_at),
    ).where(
        KboPlayerRecord.season == season,
        KboPlayerRecord.season_type == "REGULAR",
    )
    if aliases:
        player_query = player_query.where(KboPlayerRecord.team_code.in_(aliases))
    player_rows = (await session.execute(player_query.group_by(KboPlayerRecord.category))).all()
    player_counts = {category: count for category, count, _, _ in player_rows}
    player_collected_at = max((value for _, _, value, _ in player_rows if value), default=None)
    player_imported_at = max((value for _, _, _, value in player_rows if value), default=None)

    team_query = select(
        KboTeamRecord.category,
        func.count(KboTeamRecord.id),
        func.max(KboTeamRecord.collected_at),
        func.max(KboTeamRecord.imported_at),
    ).where(
        KboTeamRecord.season == season,
        KboTeamRecord.season_type == "REGULAR",
    )
    if aliases:
        team_query = team_query.where(KboTeamRecord.team_code.in_(aliases))
    team_rows = (await session.execute(team_query.group_by(KboTeamRecord.category))).all()
    team_counts = {category: count for category, count, _, _ in team_rows}
    team_collected_at = max((value for _, _, value, _ in team_rows if value), default=None)
    team_imported_at = max((value for _, _, _, value in team_rows if value), default=None)
    loaded_team_categories = sorted(category for category, count in team_counts.items() if count)
    records_complete = (
        player_counts.get("batter", 0) > 0
        and player_counts.get("pitcher", 0) > 0
        and TEAM_RECORD_CATEGORIES.issubset(loaded_team_categories)
    )

    boxscore_rows: list[tuple[str, datetime]] = []
    lineup_count = 0
    if game_ids:
        boxscore_rows = list((await session.execute(select(
            KboGameBoxscore.game_pk, KboGameBoxscore.imported_at,
        ).where(KboGameBoxscore.game_pk.in_(game_ids)))).all())
        lineup_count = int(await session.scalar(select(func.count(KboGameLineup.id)).where(
            KboGameLineup.game_pk.in_(game_ids)
        )) or 0)
    loaded_boxscore_ids = _canonical_ids(game_pk for game_pk, _ in boxscore_rows)
    completed_boxscores = len(completed_ids & loaded_boxscore_ids)
    latest_boxscore_import = max((value for _, value in boxscore_rows if value), default=None)

    pa_conditions = [KboPlateAppearance.season == season]
    pitch_conditions = [KboPitchEvent.season == season]
    if aliases:
        pa_conditions.append(or_(
            KboPlateAppearance.batting_team_code.in_(aliases),
            KboPlateAppearance.fielding_team_code.in_(aliases),
        ))
        pitch_conditions.append(or_(
            KboPitchEvent.home_team_code.in_(aliases),
            KboPitchEvent.away_team_code.in_(aliases),
        ))
    pa_summary = (await session.execute(select(
        func.count(KboPlateAppearance.id),
        func.min(KboPlateAppearance.game_date),
        func.max(KboPlateAppearance.game_date),
    ).where(*pa_conditions))).one()
    pa_game_rows = (await session.execute(select(
        KboPlateAppearance.game_pk, KboPlateAppearance.game_date,
    ).where(*pa_conditions).distinct())).all()
    pitch_count = int(await session.scalar(select(func.count(KboPitchEvent.id)).where(*pitch_conditions)) or 0)
    pbp_ids = _canonical_ids(game_pk for game_pk, _ in pa_game_rows)
    covered_completed_ids = completed_ids & pbp_ids

    schedule_status = "COMPLETE" if games else "EMPTY"
    boxscore_status = _coverage_status(completed_boxscores, len(completed_ids))
    matchup_status = _coverage_status(len(covered_completed_ids), len(completed_ids))
    record_status = "COMPLETE" if records_complete else (
        "PARTIAL" if player_counts or team_counts else "EMPTY"
    )
    statuses = (record_status, schedule_status, boxscore_status, matchup_status)
    overall_status = "EMPTY" if all(status == "EMPTY" for status in statuses) else (
        "COMPLETE" if all(status == "COMPLETE" for status in statuses) else "PARTIAL"
    )

    matchup_note = (
        "선택한 범위의 종료 경기와 직접 맞대결 PBP 경기 수가 같아요."
        if matchup_status == "COMPLETE"
        else "직접 맞대결은 PBP가 있는 경기만 보여줘요. 시즌 기록이나 경기 기록지로 빈 표본을 채우지 않아요."
    )
    return {
        "season": season,
        "team_code": canonical_team_code(team_code) if team_code else None,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "sections": {
            "records": {
                "status": record_status,
                "batter_count": int(player_counts.get("batter", 0)),
                "pitcher_count": int(player_counts.get("pitcher", 0)),
                "team_record_categories_loaded": loaded_team_categories,
                "team_record_categories_expected": sorted(TEAM_RECORD_CATEGORIES),
                "team_record_count": int(sum(team_counts.values())),
                "collected_at": _iso(max(
                    (value for value in (player_collected_at, team_collected_at) if value),
                    default=None,
                )),
                "imported_at": _iso(max(
                    (value for value in (player_imported_at, team_imported_at) if value),
                    default=None,
                )),
            },
            "schedule": {
                "status": schedule_status,
                "game_count": len(games),
                "completed_game_count": len(completed_games),
                "date_from": _iso(games[0].game_date) if games else None,
                "date_through": _iso(games[-1].game_date) if games else None,
                "imported_at": _iso(max((game.imported_at for game in games), default=None)),
            },
            "boxscores": {
                "status": boxscore_status,
                "expected_completed_games": len(completed_ids),
                "loaded_completed_games": completed_boxscores,
                "coverage_rate": _rate(completed_boxscores, len(completed_ids)),
                "lineup_rows": lineup_count,
                "imported_at": _iso(latest_boxscore_import),
            },
            "matchups": {
                "status": matchup_status,
                "expected_completed_games": len(completed_ids),
                "covered_completed_games": len(covered_completed_ids),
                "coverage_rate": _rate(len(covered_completed_ids), len(completed_ids)),
                "plate_appearances": int(pa_summary[0] or 0),
                "pitch_events": pitch_count,
                "date_from": _iso(pa_summary[1]),
                "date_through": _iso(pa_summary[2]),
                "note": matchup_note,
            },
        },
        "limitations": [
            "시즌 누적 기록, 경기 기록지와 직접 맞대결 PBP는 서로 다른 데이터 범위예요.",
            "커버리지는 데이터가 있는 경기 비율이며 기록의 정확도나 추천 적중률을 뜻하지 않아요.",
        ],
    }
