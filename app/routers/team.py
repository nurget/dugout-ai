from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends
from typing import Annotated

from app.core.auth import CurrentUser
from app.db.session import get_db
from app.models.kbo_season_pitcher import KboSeasonPitcher


router = APIRouter(
    prefix="/api/teams/me",
    tags=["my-team"],
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]


def serialize_pitcher(pitcher: KboSeasonPitcher) -> dict:
    # SQLAlchemy 모델에서 실제 DB 컬럼만 추출한다.
    # 사용자 모델이나 비밀번호 등은 이 API에 포함되지 않는다.
    result = {}

    for column in pitcher.__table__.columns:
        value = getattr(pitcher, column.name)

        if isinstance(value, (date, datetime)):
            value = value.isoformat()

        result[column.name] = value

    return result


@router.get("")
async def get_my_team(
    current_user: CurrentUser,
):
    return {
        "team_code": current_user.team_code,
        "role": current_user.role,
        "username": current_user.username,
        "season": 2026,
    }


@router.get("/pitchers")
async def get_my_team_pitchers(
    current_user: CurrentUser,
    session: SessionDep,
    season: int = Query(default=2026, ge=1982, le=2100),
):
    # 소속 팀은 요청 파라미터가 아닌 인증된 사용자 정보에서 가져온다.
    statement = (
        select(KboSeasonPitcher)
        .where(
            KboSeasonPitcher.season == season,
            KboSeasonPitcher.team_code == current_user.team_code,
        )
    )

    result = await session.execute(statement)
    pitchers = result.scalars().all()

    return {
        "team_code": current_user.team_code,
        "season": season,
        "count": len(pitchers),
        "data": [
            serialize_pitcher(pitcher)
            for pitcher in pitchers
        ],
    }