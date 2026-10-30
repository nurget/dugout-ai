from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.game import Game
from app.schemas.game import GameResponse


router = APIRouter(
    prefix="/api/games",
    tags=["Games"],
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[GameResponse])
async def get_games(session: SessionDep):
    result = await session.scalars(
        select(Game).order_by(Game.id)
    )

    return result.all()


@router.get("/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: int,
    session: SessionDep,
):
    game = await session.get(Game, game_id)

    if game is None:
        raise HTTPException(
            status_code=404,
            detail="경기를 찾을 수 없습니다.",
        )

    return game