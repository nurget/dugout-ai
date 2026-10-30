from datetime import date

from pydantic import BaseModel, ConfigDict


class GameResponse(BaseModel):
    id: int
    home_team: str
    away_team: str
    game_date: date

    model_config = ConfigDict(from_attributes=True)