from pydantic import BaseModel, Field


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