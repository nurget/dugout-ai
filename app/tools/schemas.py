from pydantic import BaseModel, Field

from app.sabermetrics.run_expectancy import RE24Input

class GameStateInput(BaseModel):
    game_id: int = Field(gt=0)
    state_id: int = Field(gt=0)


class PitcherStatusInput(BaseModel):
    player_id: int = Field(gt=0)


class BullpenOptionsInput(BaseModel):
    team: str = Field(min_length=1, max_length=50)
    exclude_player_id: int | None = Field(
        default=None,
        gt=0,
    )
    
class PitchingDecisionInput(BaseModel):
    inning: int = Field(ge=1, le=12)
    outs: int = Field(ge=0, le=2)
    pitch_count: int = Field(ge=0, le=200)
    runner_on_first: bool = False

class SearchSeasonPitchersInput(BaseModel):
    season: int = Field(ge=1982, le=2100)
    name: str = Field(min_length=1)
    team: str | None = None


class ComparePitchersInput(BaseModel):
    season: int = Field(ge=1982, le=2100)
    first_pitcher_id: str = Field(min_length=1)
    second_pitcher_id: str = Field(min_length=1)
    team: str | None = None