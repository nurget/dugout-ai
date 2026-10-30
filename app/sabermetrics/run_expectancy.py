from typing import Literal

from pydantic import BaseModel, Field

# FanGraphs RE24 설명에 사용된 예시 행렬. (https://library.fangraphs.com/misc/re24/)

EXAMPLE_RE_MATRIX = {
    "000": (0.461, 0.243, 0.095),
    "100": (0.831, 0.489, 0.214),
    "010": (1.068, 0.644, 0.305),
    "110": (1.373, 0.908, 0.343),
    "001": (1.426, 0.865, 0.413),
    "101": (1.798, 1.140, 0.471),
    "011": (1.920, 1.352, 0.570),
    "111": (2.282, 1.520, 0.736),
}

BaseState = Literal[
    "000", "100", "010", "110",
    "001", "101", "011", "111",
]


class BaseOutState(BaseModel):
    outs: int = Field(ge=0, le=3)
    bases: BaseState


class RE24Input(BaseModel):
    before: BaseOutState
    after: BaseOutState
    runs_scored: int = Field(ge=0, le=4)


def get_run_expectancy(state: BaseOutState) -> float:
    # 3아웃이면 주자 상태와 관계없이 해당 이닝의 득점 기대값은 0이다.
    if state.outs == 3:
        return 0.0

    return EXAMPLE_RE_MATRIX[state.bases][state.outs]


def calculate_re24(data: RE24Input) -> dict:
    if data.before.outs == 3:
        raise ValueError("플레이 시작 상태는 3아웃일 수 없습니다.")

    if data.after.outs < data.before.outs:
        raise ValueError(
            "한 이닝 안에서 아웃카운트가 감소할 수 없습니다."
        )

    if data.after.outs == 3 and data.after.bases != "000":
        raise ValueError(
            "이닝 종료 상태의 주자 정보는 000으로 정규화해야 합니다."
        )

    before_re = get_run_expectancy(data.before)
    after_re = get_run_expectancy(data.after)

    re24 = round(
        after_re - before_re + data.runs_scored,
        3,
    )

    return {
        "before": data.before.model_dump(),
        "after": data.after.model_dump(),
        "runs_scored": data.runs_scored,
        "before_re": before_re,
        "after_re": after_re,
        "re24": re24,
        "interpretation": (
            "양수이면 공격팀의 득점 기대 기여가 증가했고, "
            "음수이면 감소한 것입니다."
        ),
        "source": {
            "name": "FanGraphs RE24 example matrix",
            "url": "https://library.fangraphs.com/misc/re24/",
            "league": "illustrative",
            "is_kbo_2026_data": False,
        },
    }