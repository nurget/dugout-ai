from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.tools.schemas import PitchingDecisionInput
from app.tools.baseball import simulate_pitching_decision

from app.tools.baseball import (
    ToolNotFoundError,
    get_game_state,
    get_pitcher_status,
    get_bullpen_options,
)

from app.tools.schemas import (
    GameStateInput,
    PitcherStatusInput,
    BullpenOptionsInput,
)

TOOL_REGISTRY = {
    "get_game_state": (
        GameStateInput,
        get_game_state,
    ),
    "get_pitcher_status": (
        PitcherStatusInput,
        get_pitcher_status,
    ),
    "get_bullpen_options": (
        BullpenOptionsInput,
        get_bullpen_options,
    ),
    "simulate_pitching_decision": (
        PitchingDecisionInput,
        simulate_pitching_decision,
    ),
}


async def execute_tool(
    session: AsyncSession,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict:
    tool = TOOL_REGISTRY.get(tool_name)

    if tool is None:
        return {
            "ok": False,
            "error": {
                "code": "UNKNOWN_TOOL",
                "message": "허용되지 않은 도구입니다.",
            },
        }

    schema_class, handler = tool

    try:
        validated = schema_class.model_validate(arguments)

        result = await handler(
            session,
            **validated.model_dump(),
        )

        return {
            "ok": True,
            "data": result,
        }

    except ValidationError:
        return {
            "ok": False,
            "error": {
                "code": "INVALID_ARGUMENTS",
                "message": "도구 입력값이 올바르지 않습니다.",
            },
        }

    except ToolNotFoundError as error:
        return {
            "ok": False,
            "error": {
                "code": "NOT_FOUND",
                "message": str(error),
            },
        }

    except ValueError as error:
        return {
            "ok": False,
            "error": {
                "code": "INVALID_STATE",
                "message": str(error),
            },
        }