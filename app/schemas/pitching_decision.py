from enum import Enum

from pydantic import BaseModel, Field, model_validator


class InningHalf(str, Enum):
    TOP = "TOP"
    BOTTOM = "BOTTOM"


class BatterHand(str, Enum):
    LEFT = "L"
    RIGHT = "R"
    SWITCH = "S"


class BaseRunners(BaseModel):
    first: bool = False
    second: bool = False
    third: bool = False


class PitchingDecisionContext(BaseModel):
    season: int = Field(default=2026, ge=1982, le=2100)

    # 수비 중인 구단을 기준으로 경기 상황을 표현한다.
    defending_team_code: str = Field(min_length=1)

    inning: int = Field(ge=1)
    inning_half: InningHalf
    outs: int = Field(ge=0, le=2)
    runners: BaseRunners

    # 양수는 수비 팀이 앞서는 상황, 음수는 뒤지는 상황이다.
    score_diff: int

    current_pitcher_id: str | None = None
    current_pitch_count: int = Field(ge=0)

    next_batter_id: str | None = None
    next_batter_hand: BatterHand | None = None

    # 사용자 입력 상황인지, 수집한 실제 기록인지 구분한다.
    source: str = Field(default="USER_INPUT")

    @model_validator(mode="after")
    def validate_source(self):
        if self.source not in {"USER_INPUT", "RECORDED_GAME"}:
            raise ValueError(
                "source는 USER_INPUT 또는 RECORDED_GAME이어야 합니다."
            )

        return self