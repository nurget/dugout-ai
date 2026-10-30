from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.player import Player
from app.schemas.player import PlayerResponse


router = APIRouter(
    prefix="/api/players",
    tags=["Players"],
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.get("", response_model=list[PlayerResponse])
async def get_players(session: SessionDep):
    result = await session.scalars(
        select(Player).order_by(Player.id)
    )

    return result.all()


@router.get("/{player_id}", response_model=PlayerResponse)
async def get_player(
    player_id: int,
    session: SessionDep,
):
    player = await session.get(Player, player_id)

    if player is None:
        raise HTTPException(
            status_code=404,
            detail="선수를 찾을 수 없습니다.",
        )

    return player