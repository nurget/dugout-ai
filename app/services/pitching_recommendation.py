
from typing import Any


def recommend_bullpen(
    *,
    team_code: str,
    verified_candidate_ids: list[str],
    season_pitchers: list[dict[str, Any]],
    workloads: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    코치가 확인한 후보만 시즌 기록과 최근 부담으로 비교한다.

    verified_candidate_ids:
        오늘 경기에서 등판 후보라고 코치가 직접 확인한
        공식 pitcher_id 목록

    이 목록은 LLM이 생성한 값이나 선수 이름 검색 결과를
    그대로 전달해서는 안 된다.
    """
    verified_ids = set(verified_candidate_ids)

    if not team_code.strip():
        raise ValueError("team_code가 필요합니다.")

    if not verified_ids or any(
        not isinstance(pid, str) or not pid.strip()
        for pid in verified_ids
    ):
        raise ValueError("확인된 후보 선수 ID가 필요합니다.")

    if len(verified_ids) != len(verified_candidate_ids):
        raise ValueError("후보 선수 ID가 중복되었습니다.")

    # 공식 ID가 확인된 부담 기록만 연결한다.
    workload_by_id = {
        str(row["pitcher_id"]): row
        for row in workloads
        if row.get("pitcher_id") is not None
        and row.get("workload_status") != "AMBIGUOUS_IDENTITY"
    }

    season_by_id = {
        str(row["pitcher_id"]): row
        for row in season_pitchers
        if row.get("pitcher_id") is not None
        and row.get("team_code") == team_code
    }

    eligible = []
    withheld = []

    for pitcher_id in sorted(verified_ids):
        season = season_by_id.get(pitcher_id)

        if season is None:
            withheld.append({
                "pitcher_id": pitcher_id,
                "reason": "해당 팀의 공식 시즌 성적을 확인할 수 없습니다.",
            })
            continue

        workload = workload_by_id.get(pitcher_id)

        # 동명이인과 미매핑된 투수는 최근 부담을
        # 다른 사람의 기록과 합산할 위험이 있으므로 제외한다.
        if workload is None:
            withheld.append({
                "pitcher_id": pitcher_id,
                "pitcher_name": season.get("pitcher_name"),
                "reason": "선수 ID로 연결된 최근 투구 부담 기록이 없습니다.",
            })
            continue

        if workload.get("workload_status") not in {
            "NO_HIGH_LOAD_FLAG",
            "REVIEW_REQUIRED",
        }:
            withheld.append({
                "pitcher_id": pitcher_id,
                "pitcher_name": season.get("pitcher_name"),
                "reason": "최근 투구 부담을 확정할 수 없습니다.",
            })
            continue

        # 데이터 표본이 작은 선수는 높은 K-BB%라도
        # 표본 신뢰도가 낮을 수 있으므로 별도 분류한다.
        batters_faced = season.get("batters_faced")
        k_minus_bb_pct = season.get("k_minus_bb_pct")

        if (
            batters_faced is None
            or k_minus_bb_pct is None
            or batters_faced <= 0
        ):
            withheld.append({
                "pitcher_id": pitcher_id,
                "pitcher_name": season.get("pitcher_name"),
                "reason": "시즌 비교 지표가 부족합니다.",
            })
            continue

        sample_tier = (
            "LARGER" if batters_faced >= 150
            else "LIMITED" if batters_faced >= 50
            else "VERY_SMALL"
        )

        eligible.append({
            "pitcher_id": pitcher_id,
            "pitcher_name": season["pitcher_name"],
            "team_code": team_code,
            "batters_faced": batters_faced,
            "k_minus_bb_pct": float(k_minus_bb_pct),
            "sample_tier": sample_tier,
            "identity_status": season.get("identity_status"),
            "identity_source": season.get("identity_source"),
            "workload_status": workload["workload_status"],
            "pitches_last_3_days": workload.get(
                "pitches_last_3_days"
            ),
            "consecutive_days": workload.get(
                "consecutive_days"
            ),
            "days_rest": workload.get("days_rest"),
        })

    # 최근 부담 검토가 필요한 투수를 뒤로 배치한다.
    # 그다음 시즌 표본 규모와 K-BB%를 비교한다.
    tier_rank = {
        "LARGER": 0,
        "LIMITED": 1,
        "VERY_SMALL": 2,
    }

    eligible.sort(
        key=lambda row: (
            row["workload_status"] != "NO_HIGH_LOAD_FLAG",
            tier_rank[row["sample_tier"]],
            -row["k_minus_bb_pct"],
            row["pitcher_id"],
        )
    )

    return {
        "team_code": team_code,
        "ranking": eligible,
        "withheld": withheld,
        "verified_candidate_count": len(verified_ids),
        "recommendation_basis": (
            "코치 확인 후보, 최근 투구 부담, "
            "시즌 표본 규모, K-BB%에 따른 규칙 기반 비교"
        ),
        "limitations": [
            "등판 가능 여부는 코치가 입력한 정보에 의존합니다.",
            "구종·상대 타자 상성·실시간 컨디션은 반영하지 않았습니다.",
            "순위는 승률 예측이나 최적 교체 확률이 아닙니다.",
        ],
    }
