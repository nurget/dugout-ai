from datetime import date, datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.services.kbo_game_lineups import get_game_boxscore
from app.services.kbo_matchups import get_game_pitcher_matchup, get_matchup_calendar, get_matchup_pitchers


router = APIRouter(prefix="/api/kbo", tags=["kbo-matchups"])
SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/matchups/calendar")
async def matchup_calendar(current_user: CurrentUser, session: SessionDep, season: int = Query(default=2026, ge=1982, le=2100)):
    result = await get_matchup_calendar(session, team_code=current_user.team_code, season=season)
    today = datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    result["data"] = [row for row in result["data"] if row["game_date"] <= today]
    result["latest_game_date"] = result["data"][0]["game_date"] if result["data"] else None
    return result


@router.get("/matchups/pitchers")
async def matchup_pitchers(current_user: CurrentUser, session: SessionDep, game_date: date = Query(), season: int = Query(default=2026, ge=1982, le=2100)):
    if game_date.year != season:
        raise HTTPException(status_code=422, detail="조회 날짜와 시즌 연도가 일치해야 합니다.")
    if game_date > datetime.now(ZoneInfo("Asia/Seoul")).date():
        raise HTTPException(status_code=422, detail="조회 날짜는 미래일 수 없습니다.")
    return await get_matchup_pitchers(session, team_code=current_user.team_code, season=season, game_date=game_date)


@router.get("/games/{game_pk}/boxscore")
async def game_boxscore(game_pk: str, _current_user: CurrentUser, session: SessionDep):
    result = await get_game_boxscore(session, game_pk)
    if result is None:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없어요.")
    return result


@router.get("/games/{game_pk}/pitcher-matchup")
async def game_pitcher_matchup(
    game_pk: str, current_user: CurrentUser, session: SessionDep,
    pitcher_id: str | None = Query(default=None, min_length=1, max_length=32),
):
    try:
        result = await get_game_pitcher_matchup(session, team_code=current_user.team_code, game_pk=game_pk, pitcher_id=pitcher_id)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    if result is None:
        raise HTTPException(status_code=404, detail="경기를 찾을 수 없어요.")
    return result
