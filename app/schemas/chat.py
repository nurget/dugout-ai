from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=1000,
    )


class ToolExecutionResponse(BaseModel):
    tool: str
    arguments: str
    result: dict


class ChatResponse(BaseModel):
    answer: str
    tool_history: list[ToolExecutionResponse]
    rounds: int