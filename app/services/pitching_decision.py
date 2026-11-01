
from typing import Any


def evaluate_pitching_change(
    *,
    inning: int,
    outs: int,
    runners: list[int],
    score_diff: int,
    pitch_count: int,
) -> dict[str, Any]:
    """
    현재 투수의 교체 검토 신호를 계산한다.

    score_diff:
        수비팀 득점 - 공격팀 득점
        양수: 리드 / 음수: 열세

    runners:
        점유 중인 루 번호 (1, 2, 3)
        예: [1, 2] = 1·2루

    주의:
        이 함수는 교체 확정이 아닌 검토 신호를 반환한다.
        투수의 현재 구위, 부상, 불펜 후보 정보는 포함하지 않는다.
    """

    if not 1 <= inning <= 12:
        raise ValueError("inning은 1~12여야 합니다.")

    if not 0 <= outs <= 2:
        raise ValueError("outs는 0~2여야 합니다.")

    if pitch_count < 0:
        raise ValueError("pitch_count는 0 이상이어야 합니다.")

    if (
        len(runners) != len(set(runners))
        or any(base not in (1, 2, 3) for base in runners)
    ):
        raise ValueError("runners는 중복 없는 1, 2, 3루 목록이어야 합니다.")

    signals = []
    risk_score = 0

    # 1. 투구 수에 따른 검토 신호
    # MVP용 휴리스틱이며 공식 투구 제한이 아니다.
    if pitch_count >= 100:
        risk_score += 3
        signals.append({
            "code": "HIGH_PITCH_COUNT",
            "message": f"현재 투구 수가 {pitch_count}구입니다.",
            "points": 3,
        })
    elif pitch_count >= 85:
        risk_score += 2
        signals.append({
            "code": "ELEVATED_PITCH_COUNT",
            "message": f"현재 투구 수가 {pitch_count}구입니다.",
            "points": 2,
        })

    # 2. 득점권 주자
    scoring_position = 2 in runners or 3 in runners

    if scoring_position:
        risk_score += 2
        signals.append({
            "code": "RUNNER_IN_SCORING_POSITION",
            "message": "득점권에 주자가 있습니다.",
            "points": 2,
        })
    elif 1 in runners:
        risk_score += 1
        signals.append({
            "code": "RUNNER_ON_FIRST",
            "message": "1루에 주자가 있습니다.",
            "points": 1,
        })

    # 3. 경기 후반 접전
    close_game = abs(score_diff) <= 2

    if inning >= 7 and close_game:
        risk_score += 2
        signals.append({
            "code": "LATE_CLOSE_GAME",
            "message": "7회 이후 2점 차 이내의 접전입니다.",
            "points": 2,
        })

    # 4. 2아웃인 경우 이닝 종료 가능성도 고려
    if outs == 2 and risk_score > 0:
        risk_score -= 1
        signals.append({
            "code": "TWO_OUTS",
            "message": "2아웃이므로 이닝 종료 가능성도 함께 검토합니다.",
            "points": -1,
        })

    # 점수는 의사결정을 돕는 신호일 뿐, 확률이 아니다.
    if risk_score >= 5:
        status = "CONSIDER_CHANGE"
    elif risk_score >= 3:
        status = "MONITOR"
    else:
        status = "NO_STRONG_CHANGE_SIGNAL"

    return {
        "status": status,
        "risk_score": risk_score,
        "signals": signals,
        "context": {
            "inning": inning,
            "outs": outs,
            "runners": sorted(runners),
            "score_diff": score_diff,
            "pitch_count": pitch_count,
        },
        "limitations": [
            "현재 투수의 구위와 최근 타자 상대 결과는 반영되지 않았습니다.",
            "교체 가능한 불펜 투수와 최근 투구 부담은 아직 반영되지 않았습니다.",
            "점수와 기준값은 MVP용 휴리스틱이며 교체 성공 확률이 아닙니다.",
        ],
    }