
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.kbo_workload import get_kbo_team_workload
from app.services.team_bullpen import normalize_official_team_code

VALID_TEAMS = frozenset({
    "HT", "SS", "LG", "HH", "OB",
    "LT", "SK", "KT", "NC", "WO",
})

class BullpenWorkloadToolError(ValueError):
    pass


async def get_bullpen_workload_tool(
    session: AsyncSession,
    *,
    as_of_date: date,
    authenticated_team_code: str,
) -> dict:
    """
    인증된 사용자의 구단만 조회한다.

    구단 코드는 LLM 인자가 아닌 서버 인증 컨텍스트에서 전달받는다.
    """

    team_code = normalize_official_team_code(
        authenticated_team_code.strip().upper()
    )

    if team_code not in VALID_TEAMS:
        raise ValueError("지원하지 않는 구단 코드입니다.")

    if as_of_date.year != 2026:
        raise ValueError(
            "현재 제공 가능한 공식 기록은 2026시즌입니다."
        )

    result = await get_kbo_team_workload(
        session,
        season=2026,
        team_code=team_code,
        as_of_date=as_of_date,
        lookback_days=3,
    )

    return result

async def execute_bullpen_workload(
    db: AsyncSession,
    *,
    authenticated_team_code: str,
    requested_team_code: str,
    as_of_date: str,
    season: int = 2026,
) -> dict:
    """
    로그인한 구단의 투구 부담만 조회한다.

    LLM이 전달한 team_code를 신뢰하지 않고,
    서버 인증 컨텍스트의 팀 코드와 비교한다.
    """

    auth_team = normalize_official_team_code(
        authenticated_team_code.upper()
    )

    requested_team = normalize_official_team_code(
        requested_team_code.upper()
    )

    if auth_team != requested_team:
        raise BullpenWorkloadToolError(
            "현재 로그인한 구단의 기록만 조회할 수 있습니다."
        )

    try:
        target_date = date.fromisoformat(as_of_date)
    except (TypeError, ValueError) as error:
        raise BullpenWorkloadToolError(
            "as_of_date는 YYYY-MM-DD 형식이어야 합니다."
        ) from error

    if target_date.year != season:
        raise BullpenWorkloadToolError(
            "요청 날짜와 시즌이 일치하지 않습니다."
        )

    result = await get_kbo_team_workload(
        db,
        season=season,
        team_code=auth_team,
        as_of_date=target_date,
        lookback_days=3,
    )

    # 특정 선수만 요청하더라도 같은 기준일의 구단 기록을
    # 일관된 구조로 반환한다.
    return result