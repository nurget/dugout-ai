from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.kbo import KboGame

router = APIRouter(prefix="/api/kbo", tags=["kbo"])
SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("/games")
async def list_games(
    db: SessionDep,
    season: int = Query(ge=1982, le=2100),
    team: str | None = Query(default=None, min_length=2, max_length=8),
    limit: int = Query(default=30, ge=1, le=100),
):
    query = select(KboGame).where(KboGame.season == season)
    if team:
        code = team.upper()
        query = query.where(or_(KboGame.home_team_code == code,
                                KboGame.away_team_code == code))
    query = query.order_by(KboGame.game_date.desc(), KboGame.game_pk.desc()).limit(limit)
    rows = (await db.execute(query)).scalars().all()
    return [{
        "game_pk": game.game_pk,
        "date": game.game_date.isoformat(),
        "home_team": game.home_team_code,
        "away_team": game.away_team_code,
        "home_score": game.home_score,
        "away_score": game.away_score,
        "status": game.status,
        "source": game.source_name,
    } for game in rows]
