from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import AgentExecutionError, run_agent
from app.core.config import settings
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter(
    prefix="/api/agent",
    tags=["Agent"],
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    session: SessionDep,
):
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI 서비스가 설정되지 않았습니다.",
        )

    try:
        async with AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=20.0,
            max_retries=1,
        ) as client:
            result = await run_agent(
                message=request.message,
                session=session,
                client=client,
            )

        return ChatResponse(**result)

    except AgentExecutionError as error:
        raise HTTPException(
            status_code=503,
            detail=str(error),
        ) from error