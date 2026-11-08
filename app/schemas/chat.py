from pydantic import BaseModel, Field
from uuid import UUID
from datetime import date

class ChatRequest(BaseModel):
    message: str = Field(
        min_length=1,
        max_length=1000,
    )
    conversation_id: UUID | None = None
    as_of_date: date | None = Field(
        default=None,
        description="분석 기준일. 생략하면 Asia/Seoul 기준 오늘 날짜를 사용합니다.",
    )
