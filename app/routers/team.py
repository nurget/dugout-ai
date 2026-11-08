from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.services.team_data import (
    get_team_games,
    get_team_pitchers,
    get_team_official_pitchers,
)
from app.services.data_catalog import get_latest_dataset_statuses


router = APIRouter(
    prefix="/api/teams/me",
    tags=["my-team"],
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def serialize_model(model) -> dict:
    result = {}

    for column in model.__table__.columns:
        value = getattr(model, column.name)

        if isinstance(value, (date, datetime)):
            value = value.isoformat()

        result[column.name] = value

    return result


@router.get("")
async def get_my_team(
    current_user: CurrentUser,
):
    return {
        "username": current_user.username,
        "team_code": current_user.team_code,
        "role": current_user.role,
        "season": 2026,
    }


@router.get("/games")
async def get_my_team_games(
    current_user: CurrentUser,
    session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    season_type: str = Query(default="REGULAR", pattern="^(REGULAR|POSTSEASON)$"),
    season_phase: str | None = Query(default=None, pattern="^(WILDCARD|SEMIPLAYOFF|PLAYOFF|KOREAN_SERIES)$"),
):
    games = await get_team_games(
        session=session,
        team_code=current_user.team_code,
        season=season,
        season_type=season_type,
        season_phase=season_phase,
    )

    return {
        "team_code": current_user.team_code,
        "season": season,
        "season_type": season_type,
        "count": len(games),
        "data": [
            serialize_model(game)
            for game in games
        ],
    }


@router.get("/pitchers")
async def get_my_team_pitchers(
    current_user: CurrentUser,
    session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    season_type: str = Query(default="REGULAR", pattern="^(REGULAR|POSTSEASON|WILDCARD|SEMIPLAYOFF|PLAYOFF|KOREAN_SERIES)$"),
    as_of_date: date | None = Query(default=None),
):
    if as_of_date is not None:
        if season_type != "REGULAR":
            raise HTTPException(status_code=422, detail="기준일 누적 집계는 정규시즌만 지원합니다.")
        if as_of_date.year != season:
            raise HTTPException(status_code=422, detail="기준일과 시즌 연도가 일치해야 합니다.")
        if as_of_date > datetime.now(ZoneInfo("Asia/Seoul")).date():
            raise HTTPException(status_code=422, detail="기준일은 미래일 수 없습니다.")

        from app.services.as_of_pitcher import get_pitcher_stats_as_of

        result = await get_pitcher_stats_as_of(
            session,
            season=season,
            team_code=current_user.team_code,
            as_of_date=as_of_date,
        )
        statuses = await get_latest_dataset_statuses(session)
        snapshot = next(
            row["snapshot_id"]
            for row in statuses
            if row["dataset"] == "kbo_pitcher_appearances"
        )
        return {
            "team_code": current_user.team_code,
            "season": season,
            "season_type": "REGULAR",
            "as_of_date": as_of_date.isoformat(),
            "data_snapshot_id": snapshot,
            "stat_source": result["stat_source"],
            "coverage": result["coverage"],
            "provenance": result["provenance"],
            "data_through_date": result["data_through_date"],
            "count": len(result["pitchers"]),
            "data": result["pitchers"],
            "withheld": result["withheld"],
            "limitations": result["limitations"],
        }

    official = await get_team_official_pitchers(
        session=session,
        team_code=current_user.team_code,
        season=season,
        season_type=season_type,
    )

    if official:
        return {"team_code": current_user.team_code, "season": season, "season_type": season_type, "count": len(official), "data": [{"id": f"official-{p.id}", "pitcher_name": p.pitcher_name, "games": p.games, "batters_faced": p.batters_faced, "strikeouts": p.strikeouts, "walks": p.walks, "k_pct": p.k_pct, "bb_pct": p.bb_pct, "k_minus_bb_pct": p.k_minus_bb_pct, "stat_source": "KBO_OFFICIAL"} for p in official], "note": ""}
    if season_type != "REGULAR":
        return {"team_code": current_user.team_code, "season": season, "season_type": season_type, "count": 0, "data": [], "note": ""}
    pitchers = await get_team_pitchers(session=session, team_code=current_user.team_code, season=season)
    return {
        "team_code": current_user.team_code,
        "season": season,
        "season_type": season_type,
        "count": len(pitchers),
        "data": [
            serialize_model(pitcher)
            for pitcher in pitchers
        ],
        "note": (
            "투수 통계는 2026년 일부 경기의 "
            "Play-by-Play 데이터를 기반으로 집계했습니다. "
            "공식 시즌 전체 기록과 차이가 있을 수 있습니다."
        ),
    }


@router.get("/data-status")
async def get_my_team_data_status(
    current_user: CurrentUser,
    session: SessionDep,
):
    """인증된 사용자가 서비스가 사용하는 KBO 데이터의 출처/상태를 확인한다."""
    return {
        "team_code": current_user.team_code,
        "scope": "TEAM_ACCOUNT_DATA_OPERATIONS",
        "data": await get_latest_dataset_statuses(session),
    }
