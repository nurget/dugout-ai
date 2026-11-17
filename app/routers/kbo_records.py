from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.models.kbo import KboGame
from app.services.kbo_player_records import (
    get_player_record_payload, get_team_record_payload, team_code_aliases,
)
from app.services.kbo_data_coverage import get_data_coverage


router = APIRouter(prefix="/api/kbo", tags=["kbo-records"])
SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/games")
async def get_kbo_games(
    _current_user: CurrentUser,
    session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    season_type: str = Query(default="REGULAR", pattern="^(REGULAR|POSTSEASON)$"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    team_code: str | None = Query(default=None, min_length=2, max_length=12),
    limit: int = Query(default=500, ge=1, le=1000),
):
    if start_date and start_date.year != season or end_date and end_date.year != season:
        raise HTTPException(status_code=422, detail="조회 날짜와 시즌 연도가 일치해야 합니다.")
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="시작 날짜는 종료 날짜보다 늦을 수 없습니다.")

    query = select(KboGame).where(
        KboGame.season == season,
        KboGame.season_type == season_type,
    )
    if start_date:
        query = query.where(KboGame.game_date >= start_date)
    if end_date:
        query = query.where(KboGame.game_date <= end_date)
    if team_code:
        codes = team_code_aliases(team_code)
        query = query.where(KboGame.home_team_code.in_(codes) | KboGame.away_team_code.in_(codes))
    query = query.order_by(KboGame.game_date, KboGame.game_pk).limit(limit)
    games = list((await session.scalars(query)).all())
    return {
        "season": season,
        "season_type": season_type,
        "count": len(games),
        "limit": limit,
        "data": [
            {
                "game_pk": row.game_pk,
                "game_date": row.game_date.isoformat(),
                "home_team_code": row.home_team_code,
                "away_team_code": row.away_team_code,
                "home_score": row.home_score,
                "away_score": row.away_score,
                "status": row.status,
                "source_name": row.source_name,
                "source_batch_id": row.source_batch_id,
            }
            for row in games
        ],
        "note": "수집된 경기 일정과 결과예요. 순위와 승률은 구단 기록에서 확인할 수 있어요.",
    }


@router.get("/records/players")
async def get_kbo_player_records(
    _current_user: CurrentUser,
    session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    season_type: str = Query(default="REGULAR", pattern="^(REGULAR|POSTSEASON)$"),
    category: str = Query(default="batter", pattern="^(batter|pitcher)$"),
    team_code: str | None = Query(default=None, min_length=2, max_length=12),
    name: str | None = Query(default=None, min_length=1, max_length=80),
    include_pitchers: bool = Query(default=False),
    qualified_only: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=1000),
):
    return await get_player_record_payload(
        session,
        season=season,
        season_type=season_type,
        category=category,
        team_code=team_code,
        name=name,
        include_pitchers=include_pitchers,
        qualified_only=qualified_only,
        limit=limit,
    )


@router.get("/records/teams")
async def get_kbo_team_records(
    _current_user: CurrentUser, session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    season_type: str = Query(default="REGULAR", pattern="^(REGULAR|POSTSEASON)$"),
    category: str = Query(default="standings", pattern="^(standings|batting|pitching|defense|running)$"),
    team_code: str | None = Query(default=None, min_length=2, max_length=12),
):
    return await get_team_record_payload(session, season=season, season_type=season_type,
        category=category, team_code=team_code)


@router.get("/records/coverage")
async def get_kbo_record_coverage(
    _current_user: CurrentUser, session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
    team_code: str | None = Query(default=None, min_length=2, max_length=12),
):
    return await get_data_coverage(session, season=season, team_code=team_code)
