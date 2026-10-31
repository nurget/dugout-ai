from typing import Any

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import AgentContext
from app.sabermetrics.run_expectancy import RE24Input

from app.tools.baseball import (
    ToolNotFoundError,
    get_game_state,
    get_pitcher_status,
    get_bullpen_options,
    simulate_pitching_decision,
    calculate_re24_tool,
)

from app.tools.pitcher_comparison import (
    search_season_pitchers_tool,
    compare_pitchers_tool,
)

from app.tools.schemas import (
    GameStateInput,
    PitcherStatusInput,
    BullpenOptionsInput,
    PitchingDecisionInput,
    SearchSeasonPitchersInput,
    ComparePitchersInput,
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
    "calculate_re24": (
        RE24Input,
        calculate_re24_tool,
    ),
    "search_season_pitchers": (
        SearchSeasonPitchersInput,
        search_season_pitchers_tool,
    ),
    "compare_pitchers": (
        ComparePitchersInput,
        compare_pitchers_tool,
    ),
}


# 현재 등록된 Tool은 공개 경기 정보 또는 규칙 기반 계산만 수행한다.
# 새로운 Tool은 접근 정책을 명시하기 전까지 실행하지 않는다.
PUBLIC_TOOLS = frozenset({
    "get_game_state",
    "get_pitcher_status",
    "get_bullpen_options",
    "simulate_pitching_decision",
    "calculate_re24",
    "search_season_pitchers",
    "compare_pitchers",
})


def tool_error(code: str, message: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }


async def execute_tool(
    session: AsyncSession,
    tool_name: str,
    arguments: dict[str, Any],
    context: AgentContext | None = None,
) -> dict[str, Any]:
    tool = TOOL_REGISTRY.get(tool_name)

    if tool is None:
        return tool_error(
            "UNKNOWN_TOOL",
            "허용되지 않은 도구입니다.",
        )

    # 공개 Tool만 실행을 허용한다.
    # 비공개 Tool은 별도의 사용자·구단 인가 구현 후 등록해야 한다.
    if tool_name not in PUBLIC_TOOLS:
        return tool_error(
            "FORBIDDEN",
            "이 도구를 실행할 권한이 없습니다.",
        )

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
        return tool_error(
            "INVALID_ARGUMENTS",
            "도구 입력값이 올바르지 않습니다.",
        )

    except ToolNotFoundError as error:
        return tool_error(
            "NOT_FOUND",
            str(error),
        )

    except ValueError as error:
        return tool_error(
            "INVALID_STATE",
            str(error),
        )