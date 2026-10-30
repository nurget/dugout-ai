from pydantic import BaseModel, Field


class AnalysisRequest(BaseModel):
    inning: int = Field(ge=1, le=9)
    outs: int = Field(ge=0, le=2)
    pitch_count: int = Field(ge=0, le=200)
    runner_on_first: bool = False
    question: str = Field(min_length=1, max_length=500)


class AnalysisResponse(BaseModel):
    inning: int
    outs: int
    pitch_count: int
    situation: str
    message: str