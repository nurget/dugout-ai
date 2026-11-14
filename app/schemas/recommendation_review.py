from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RecommendationReviewRequest(BaseModel):
    outcome: Literal["ACCEPTABLE_SET", "NONE_ACCEPTABLE", "NEEDS_MORE_INFO"]
    acceptable_candidate_ids: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_outcome_candidates(self):
        ids = self.acceptable_candidate_ids
        if any(not pitcher_id.strip() for pitcher_id in ids):
            raise ValueError("선수 ID는 비어 있을 수 없습니다.")
        if len(ids) != len(set(ids)):
            raise ValueError("선수 ID가 중복되었습니다.")
        if self.outcome == "ACCEPTABLE_SET" and not ids:
            raise ValueError("적절한 후보를 한 명 이상 선택해야 합니다.")
        if self.outcome != "ACCEPTABLE_SET" and ids:
            raise ValueError("선택한 후보가 없을 때는 후보 ID를 보내지 않습니다.")
        return self
