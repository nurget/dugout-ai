
from dataclasses import dataclass
from typing import Any, Literal


Availability = Literal["AVAILABLE", "UNAVAILABLE", "UNKNOWN"]
Role = Literal["RELIEVER", "STARTER", "UNKNOWN"]


@dataclass(frozen=True)
class BullpenCandidate:
    pitcher_id: str
    pitcher_name: str
    team_code: str
    role: Role
    availability: Availability
    batters_faced: int
    k_minus_bb_pct: float | None
    workload: dict[str, Any] | None = None


def evaluate_bullpen_candidates(
    candidates: list[BullpenCandidate],
    *,
    defending_team_code: str,
) -> dict[str, Any]:
    """
    확인된 불펜 후보의 시즌 지표와 최근 투구 부담을 평가한다.

    주의:
    - 시즌 성적은 경기별 기대 실점 확률이 아니다.
    - 투수 역할과 등판 가능 여부는 외부에서 확인된 값이어야 한다.
    - UNKNOWN 상태의 투수는 추천 순위에 포함하지 않는다.
    """

    evaluated = []

    for candidate in candidates:
        reasons = []
        warnings = []

        eligible = True

        if candidate.team_code != defending_team_code:
            eligible = False
            warnings.append("수비팀 소속 선수가 아닙니다.")

        if candidate.role != "RELIEVER":
            eligible = False
            warnings.append(
                "불펜 투수 역할이 확인되지 않았습니다."
                if candidate.role == "UNKNOWN"
                else "선발투수로 분류된 선수입니다."
            )

        if candidate.availability != "AVAILABLE":
            eligible = False
            warnings.append(
                "등판 불가로 확인되었습니다."
                if candidate.availability == "UNAVAILABLE"
                else "당일 등판 가능 여부가 확인되지 않았습니다."
            )

        if candidate.batters_faced < 0:
            raise ValueError("TBF는 음수일 수 없습니다.")

        if candidate.batters_faced < 50:
            sample_level = "VERY_SMALL"
            warnings.append("상대 타자 수가 50명 미만으로 표본이 작습니다.")
        elif candidate.batters_faced < 150:
            sample_level = "LIMITED"
            warnings.append("상대 타자 수가 150명 미만으로 해석에 주의해야 합니다.")
        else:
            sample_level = "LARGER"

        if candidate.k_minus_bb_pct is None:
            eligible = False
            warnings.append("K-BB% 기록이 없습니다.")

        workload = candidate.workload

        if workload is None:
            eligible = False
            warnings.append("최근 투구 부담을 확인할 수 없습니다.")
        else:
            workload_status = workload.get("workload_status")

            if workload_status == "UNKNOWN":
                eligible = False
                warnings.append("최근 등판 기록의 수집 범위가 불충분합니다.")
            elif workload_status == "REVIEW_REQUIRED":
                eligible = False
                warnings.append("최근 투구 부담에 대한 추가 확인이 필요합니다.")
            elif workload_status != "NO_HIGH_LOAD_FLAG":
                eligible = False
                warnings.append("투구 부담 상태가 유효하지 않습니다.")

            if workload.get("data_warning"):
                eligible = False
                warnings.append(str(workload["data_warning"]))

        if candidate.k_minus_bb_pct is not None:
            reasons.append(
                f"공식 시즌 K-BB% {candidate.k_minus_bb_pct:.2f}%"
            )

        reasons.append(f"시즌 상대 타자 {candidate.batters_faced}명")

        if workload is not None:
            pitches = workload.get("pitches_last_3_days")
            if isinstance(pitches, int):
                reasons.append(f"최근 3일 투구 수 {pitches}구")

        evaluated.append({
            "pitcher_id": candidate.pitcher_id,
            "pitcher_name": candidate.pitcher_name,
            "team_code": candidate.team_code,
            "eligible": eligible,
            "sample_level": sample_level,
            "k_minus_bb_pct": candidate.k_minus_bb_pct,
            "batters_faced": candidate.batters_faced,
            "reasons": reasons,
            "warnings": warnings,
        })

    eligible_candidates = [
        row for row in evaluated if row["eligible"]
    ]

    # 먼저 표본 크기 범주를 고려하고,
    # 같은 범주 내에서 K-BB%를 비교한다.
    sample_order = {
        "LARGER": 2,
        "LIMITED": 1,
        "VERY_SMALL": 0,
    }

    eligible_candidates.sort(
        key=lambda row: (
            -sample_order[row["sample_level"]],
            -row["k_minus_bb_pct"],
            -row["batters_faced"],
            row["pitcher_id"],
        )
    )

    # 순위에서 제외된 선수도 근거와 함께 반환한다.
    excluded_candidates = [
        row for row in evaluated if not row["eligible"]
    ]

    return {
        "recommended_candidates": eligible_candidates,
        "excluded_candidates": excluded_candidates,
        "evaluated_count": len(evaluated),
        "recommendation_status": (
            "CANDIDATES_FOUND"
            if eligible_candidates
            else "INSUFFICIENT_VERIFIED_CANDIDATES"
        ),
        "limitations": [
            "표본 크기 구간은 MVP용 휴리스틱이며 공식 KBO 기준이 아닙니다.",
            "현재 순위는 타자 맞대결과 구종 상성, 실제 구위 및 구속을 반영하지 않습니다.",
            "K-BB%는 교체 후 실점 확률이나 승리 확률이 아닙니다.",
            "등판 가능 여부와 투수 역할은 별도 출처로 검증해야 합니다.",
        ],
    }
