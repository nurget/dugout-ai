from datetime import date

from pydantic import BaseModel, Field, field_validator


class LineupMatchupRequest(BaseModel):
    season: int = Field(ge=1982, le=2100)
    as_of_date: date
    opponent_team_code: str = Field(min_length=2, max_length=12)
    pitcher_ids: list[str] = Field(min_length=1, max_length=5)
    batter_ids: list[str] = Field(min_length=1, max_length=9)

    @field_validator("pitcher_ids", "batter_ids")
    @classmethod
    def require_unique_ids(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value or len(value) > 32 for value in cleaned):
            raise ValueError("선수 ID가 비어 있거나 너무 깁니다.")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("같은 선수 ID를 두 번 입력할 수 없습니다.")
        return cleaned
