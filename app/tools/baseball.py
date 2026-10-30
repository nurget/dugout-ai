from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.game import Game, GameState
from app.models.player import Player

from app.simulation.pitching import (
    PitchingScenario,
    evaluate_pitching_decision,
)

class ToolNotFoundError(Exception):
    pass


async def get_game_state(
    session: AsyncSession,
    game_id: int,
    state_id: int,
) -> dict:
    game = await session.get(Game, game_id)

    if game is None:
        raise ToolNotFoundError("경기를 찾을 수 없습니다.")

    state = await session.scalar(
        select(GameState).where(
            GameState.id == state_id,
            GameState.game_id == game_id,
        )
    )

    if state is None:
        raise ToolNotFoundError("경기 상태를 찾을 수 없습니다.")

    return {
        "game_id": game.id,
        "state_id": state.id,
        "home_team": game.home_team,
        "away_team": game.away_team,
        "inning": state.inning,
        "outs": state.outs,
        "pitch_count": state.pitch_count,
    }


async def get_pitcher_status(
    session: AsyncSession,
    player_id: int,
) -> dict:
    player = await session.get(Player, player_id)

    if player is None:
        raise ToolNotFoundError("선수를 찾을 수 없습니다.")

    if player.position != "P":
        raise ValueError("해당 선수는 투수가 아닙니다.")

    return {
        "player_id": player.id,
        "name": player.name,
        "team": player.team,
        "position": player.position,
        "status": "기본 정보만 확인됨",
    }


async def get_bullpen_options(
    session: AsyncSession,
    team: str,
    exclude_player_id: int | None = None,
) -> dict:
    statement = select(Player).where(
        Player.team == team,
        Player.position == "P",
    )

    if exclude_player_id is not None:
        statement = statement.where(
            Player.id != exclude_player_id
        )

    result = await session.scalars(
        statement.order_by(Player.id)
    )

    players = result.all()

    return {
        "team": team,
        "candidates": [
            {
                "player_id": player.id,
                "name": player.name,
                "availability": "unknown",
            }
            for player in players
        ],
        "note": "최근 등판 및 휴식 정보는 아직 반영되지 않았습니다.",
    }

async def simulate_pitching_decision(
    session: AsyncSession,
    inning: int,
    outs: int,
    pitch_count: int,
    runner_on_first: bool = False,
) -> dict:
    # 다른 Tool과 인터페이스를 맞추기 위해 session을 받음요
    scenario = PitchingScenario(
        inning=inning,
        outs=outs,
        pitch_count=pitch_count,
        runner_on_first=runner_on_first,
    )

    return evaluate_pitching_decision(scenario)