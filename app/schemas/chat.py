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
        description="소속 구단 경기가 있었던 날짜. 취소·연기·미래 경기는 제외하며, 생략하면 가장 최근의 유효 경기 날짜를 사용합니다. 해당 날짜 경기는 누적 집계에서 제외합니다.",
    )
