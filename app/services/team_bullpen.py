
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.official_pitcher import (
    get_team_official_pitchers,
)
from app.services.bullpen_candidates import (
    BullpenCandidate,
    evaluate_bullpen_candidates,
)


# 인증 시스템과 KBO 기록실의 팀 코드 차이를 보정한다.
OFFICIAL_TEAM_CODES = {
    "KIA": "HT",
    "DOOSAN": "OB",
    "SSG": "SK",
    "SAMSUNG": "SS",
    "HANWHA": "HH",
    "LOTTE": "LT",
    "KIWOOM": "WO",
}


def normalize_official_team_code(team_code: str) -> str:
    code = team_code.strip().upper()
    return OFFICIAL_TEAM_CODES.get(code, code)


async def get_team_bullpen_candidates(
    db: AsyncSession,
    *,
    season: int,
    team_code: str,
    verified_roles: dict[str, str] | None = None,
    verified_availability: dict[str, str] | None = None,
    workloads: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """
    공식 시즌 기록을 기반으로 팀 투수 후보를 평가한다.

    검증된 역할·가용성·최근 부담 자료가 없으면 UNKNOWN으로 유지한다.
    이 값들은 공식 시즌 집계 기록만으로 추론하지 않는다.
    """

    official_code = normalize_official_team_code(team_code)

    records = await get_team_official_pitchers(
        db,
        season=season,
        team_code=official_code,
    )

    verified_roles = verified_roles or {}
    verified_availability = verified_availability or {}
    workloads = workloads or {}

    candidates = []

    for record in records:
        role = verified_roles.get(
            record.pitcher_id,
            "UNKNOWN",
        )
        availability = verified_availability.get(
            record.pitcher_id,
            "UNKNOWN",
        )

        if role not in ("RELIEVER", "STARTER", "UNKNOWN"):
            raise ValueError(
                f"잘못된 투수 역할: {record.pitcher_id}, {role}"
            )

        if availability not in (
            "AVAILABLE",
            "UNAVAILABLE",
            "UNKNOWN",
        ):
            raise ValueError(
                f"잘못된 등판 가능 상태: "
                f"{record.pitcher_id}, {availability}"
            )

        candidates.append(
            BullpenCandidate(
                pitcher_id=record.pitcher_id,
                pitcher_name=record.pitcher_name,
                team_code=record.team_code,
                role=role,
                availability=availability,
                batters_faced=record.batters_faced or 0,
                k_minus_bb_pct=record.k_minus_bb_pct,
                workload=workloads.get(record.pitcher_id),
            )
        )

    evaluation = evaluate_bullpen_candidates(
        candidates,
        defending_team_code=official_code,
    )

    return {
        "season": season,
        "season_type": "REGULAR",
        "team_code": official_code,
        "source": "KBO_OFFICIAL_SEASON_PITCHERS",
        "official_pitcher_count": len(records),
        **evaluation,
    }