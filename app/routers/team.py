from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.services.team_data import (
    get_team_games,
    get_team_pitchers,
)


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
):
    games = await get_team_games(
        session=session,
        team_code=current_user.team_code,
        season=season,
    )

    return {
        "team_code": current_user.team_code,
        "season": season,
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
):
    pitchers = await get_team_pitchers(
        session=session,
        team_code=current_user.team_code,
        season=season,
    )

    return {
        "team_code": current_user.team_code,
        "season": season,
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