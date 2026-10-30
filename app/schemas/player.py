from pydantic import BaseModel, ConfigDict


class PlayerResponse(BaseModel):
    id: int
    name: str
    team: str
    position: str

    model_config = ConfigDict(from_attributes=True)