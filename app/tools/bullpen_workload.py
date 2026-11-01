
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.kbo_workload import get_kbo_team_workload
from app.services.team_codes import normalize_official_team_code

VALID_TEAMS = frozenset({
    "HT", "SS", "LG", "HH", "OB",
    "LT", "SK", "KT", "NC", "WO",
})

async def get_bullpen_workload_tool(
    session: AsyncSession,
    *,
    as_of_date: date,
    authenticated_team_code: str,
) -> dict:
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
