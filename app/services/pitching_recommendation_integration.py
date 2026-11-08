
from datetime import date, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.as_of_pitcher import get_pitcher_stats_as_of
from app.services.kbo_workload import get_kbo_team_workload
from app.services.pitching_recommendation import recommend_bullpen
from app.services.team_codes import normalize_official_team_code


VALID_TEAMS = frozenset({
    "HT", "SS", "LG", "HH", "OB",
    "LT", "SK", "KT", "NC", "WO",
})


async def compare_verified_bullpen_candidates(
    db: AsyncSession,
    *,
    season: int,
    team_code: str,
    as_of_date: date,
    verified_candidate_ids: list[str],
) -> dict:
    """
    코치가 별도로 확인한 후보들을 기준일 이전 등판 기록으로 비교한다.

    이 함수는 후보의 실시간 엔트리나 가용성을 검증하지 않는다.
    verified_candidate_ids는 신뢰된 서버 계층에서 전달해야 한다.
    """
    team = normalize_official_team_code(
        team_code.strip().upper()
    )

    if team not in VALID_TEAMS:
        raise ValueError("지원하지 않는 KBO 구단입니다.")

    if as_of_date.year != season:
        raise ValueError("기준일과 시즌 연도가 일치해야 합니다.")

    if not verified_candidate_ids:
        raise ValueError("확인된 불펜 후보 ID가 필요합니다.")

    season_stats = await get_pitcher_stats_as_of(
        db,
        season=season,
        team_code=team,
        as_of_date=as_of_date,
    )
    season_pitchers = season_stats["pitchers"]

    workload_result = await get_kbo_team_workload(
        db,
        season=season,
        team_code=team,
        as_of_date=as_of_date,
        lookback_days=3,
    )

    workloads = list(workload_result["pitchers"])

    # 최근 등판 기록이 없는 선수도 기준일 이전 누적 기록과
    # 신원이 확인된 경우에만 0구로 표현한다.
    workloads_by_id = {
        str(row["pitcher_id"]): row
        for row in workloads
        if row.get("pitcher_id") is not None
    }

    for pitcher in season_pitchers:
        pid = pitcher["pitcher_id"]

        if pid in workloads_by_id:
            continue

        workloads.append({
            "pitcher_id": pid,
            "pitcher_name": pitcher["pitcher_name"],
            "workload_status": "NO_HIGH_LOAD_FLAG",
            "pitches_last_3_days": 0,
            "appearances_last_3_days": 0,
            "appearance_days_last_3_days": 0,
            "consecutive_days": 0,
            "days_rest": None,
            "pitcher_id_source": pitcher["identity_source"],
            "reason": (
                "최근 3일 공식 정규시즌 등판 기록 없음. "
                "실제 등판 가능 여부는 별도 확인 필요."
            ),
        })

    safe_ids = {row["pitcher_id"] for row in season_pitchers}
    trusted_ids = [
        pid for pid in verified_candidate_ids
        if pid in safe_ids
    ]

    unverified_ids = [
        pid for pid in verified_candidate_ids
        if pid not in safe_ids
    ]

    if trusted_ids:
        result = recommend_bullpen(
            team_code=team,
            verified_candidate_ids=trusted_ids,
            season_pitchers=season_pitchers,
            workloads=workloads,
        )
    else:
        result = {
            "team_code": team,
            "ranking": [],
            "withheld": [],
            "verified_candidate_count": 0,
        }

    result["withheld"].extend(
        {
            "pitcher_id": pid,
            "reason": (
                "기준일 이전 기록에서 선수 ID와 누적 성적을 확정하지 못했습니다."
            ),
        }
        for pid in unverified_ids
    )

    if season_stats["coverage"]["status"] != "COMPLETE":
        result["ranking"] = []
        result["withheld"].extend(
            {
                "pitcher_id": pid,
                "reason": "기준일 이전 종료 경기의 등판 기록이 불완전하여 후보 비교를 보류합니다.",
            }
            for pid in trusted_ids
        )
        result["comparison_status"] = "WITHHELD"
    else:
        result["comparison_status"] = "COMPARABLE"

    result["verified_candidate_count"] = len(
        verified_candidate_ids
    )
    result["as_of_date"] = as_of_date.isoformat()
    result["coverage"] = season_stats["coverage"]
    result["provenance"] = season_stats["provenance"]
    result["data_through_date"] = season_stats["data_through_date"]
    result["stat_source"] = "KBO_PITCHER_APPEARANCES_AS_OF"
    result["season"] = season
    result["availability_source"] = (
        "코치가 별도로 확인한 후보 명단"
    )
    result["identity_note"] = (
        "TEAM_NAME_UNIQUE는 잠정 선수 식별이며 "
        "공식 고유 ID 직접 검증은 아닙니다."
    )
    result["limitations"] = [
        *result.get("limitations", []),
        "시즌 누적 K%, BB%, K-BB%는 기준일 이전 등판 기록으로 재계산했습니다.",
        "당일 경기는 더블헤더를 포함해 모두 제외했습니다.",
    ]

    return result
