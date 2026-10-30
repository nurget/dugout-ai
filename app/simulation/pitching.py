from typing import Any

from pydantic import BaseModel, Field


class PitchingScenario(BaseModel):
    inning: int = Field(ge=1, le=12)
    outs: int = Field(ge=0, le=2)
    pitch_count: int = Field(ge=0, le=200)
    runner_on_first: bool = False


def evaluate_pitching_decision(
    scenario: PitchingScenario,
) -> dict[str, Any]:
    pitch_count = scenario.pitch_count

    if pitch_count >= 100:
        workload_level = "high"
    elif pitch_count >= 85:
        workload_level = "caution"
    else:
        workload_level = "low"

    is_late_inning = scenario.inning >= 7

    risk_factors: list[str] = []

    if workload_level == "high":
        risk_factors.append(
            "투구 수가 100구 이상으로, 투구 부담을 확인할 필요가 있음"
        )
    elif workload_level == "caution":
        risk_factors.append(
            "투구 수가 85구 이상으로, 교체 시점 검토가 필요함"
        )

    if is_late_inning:
        risk_factors.append(
            "경기 후반으로, 남은 아웃카운트와 불펜 운영을 함께 고려해야 함"
        )

    if scenario.runner_on_first:
        risk_factors.append(
            "1루 주자가 있어 실점 위험과 투수의 주자 견제 능력 등을 확인해야 함"
        )

    # 임계값은 실제 KBO 데이터로 학습한 수치가 아니라 데모 가정이다.
    # 이를 승률이나 선수별 부상 위험 예측으로 해석하지 않도록 결과에 명시한다.
    replacement_review = (
        workload_level == "high"
        or (workload_level == "caution" and is_late_inning)
    )

    if replacement_review:
        recommendation = "교체 후보 검토"
    else:
        recommendation = "현 투수 유지와 교체 모두 검토"

    return {
        "scenario": scenario.model_dump(),
        "workload_level": workload_level,
        "replacement_review": replacement_review,
        "recommendation": recommendation,
        "risk_factors": risk_factors,
        "required_information": [
            "현재 투수의 최근 등판 기록과 휴식 상태",
            "불펜 후보의 실제 등판 가능 여부",
            "상대 타순과 타자별 대응 데이터",
            "점수 차이 및 남은 경기 운영 계획",
        ],
        "method": {
            "type": "rule_based",
            "version": "1.0",
            "assumptions": [
                "85구 이상을 주의 구간으로 설정",
                "100구 이상을 높은 투구 부담 구간으로 설정",
                "7회 이후를 경기 후반으로 설정",
            ],
            "limitation": (
                "이 결과는 교육용 규칙 기반 시나리오 평가이며, "
                "실제 승률·부상 확률·교체 효과를 예측하지 않습니다."
            ),
        },
    }