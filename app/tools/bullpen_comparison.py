
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.pitching_recommendation_integration import (
    compare_verified_bullpen_candidates,
)
from app.services.team_bullpen import normalize_official_team_code


VALID_TEAMS = frozenset({
    "HT", "SS", "LG", "HH", "OB",
    "LT", "SK", "KT", "NC", "WO",
})


async def compare_bullpen_candidates_tool(
    session: AsyncSession,
    *,
    as_of_date: date,
    candidate_ids: list[str],
    authenticated_team_code: str,
) -> dict:
    """
    사용자가 지정한 같은 구단 투수들을 조건부 비교한다.

    candidate_ids는 비교 대상일 뿐이다.
    엔트리 등록이나 등판 가능 여부가 검증된 것은 아니다.
    """
    team_code = normalize_official_team_code(
        authenticated_team_code.strip().upper()
    )

    if team_code not in VALID_TEAMS:
        raise ValueError("지원하지 않는 구단입니다.")

    if not 1 <= len(candidate_ids) <= 5:
        raise ValueError("비교 대상은 1~5명이어야 합니다.")

    if len(set(candidate_ids)) != len(candidate_ids):
        raise ValueError("중복된 선수 ID가 있습니다.")

    if as_of_date.year != 2026:
        raise ValueError("2026시즌만 지원합니다.")

    result = await compare_verified_bullpen_candidates(
        session,
        season=2026,
        team_code=team_code,
        as_of_date=as_of_date,
        verified_candidate_ids=candidate_ids,
    )

    # 내부 서비스가 붙인 '확인된 후보'라는 표현이
    # 사용자 지정 대상을 실시간 검증했다고 오해시키지 않도록
    # 외부 Tool 결과에서 의미를 명확히 한다.
    result["candidate_input_type"] = "USER_SELECTED_FOR_COMPARISON"
    result["availability_source"] = "NOT_VERIFIED"
    result["availability_verified"] = False
    result["role_verified"] = False

    result["limitations"] = [
        *result.get("limitations", []),
        "후보는 비교 대상으로 지정되었을 뿐 당일 엔트리와 가용성은 검증되지 않았습니다.",
        "K-BB%는 2026년 전체 정규시즌 성적이며 과거 기준일 당시 성적이 아닙니다.",
        "TEAM_NAME_UNIQUE 선수 ID는 팀과 이름에 근거한 잠정 매핑입니다.",
    ]

    return result