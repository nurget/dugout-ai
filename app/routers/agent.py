from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import AgentExecutionError, run_agent
from app.core.config import settings
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse

import asyncio
import logging

from fastapi import Request
from fastapi.responses import StreamingResponse

from app.agent.streaming import stream_agent
from app.db.session import AsyncSessionLocal
from app.utils.sse import format_sse

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

logger = logging.getLogger(__name__)


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
):
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI 서비스가 설정되지 않았습니다.",
        )

    async def generate():
        # 세션을 기존 Depends(get_db)에서 가져오지 않고
        # 스트림의 생명주기 안에서 생성하고 종료한다.
        async with AsyncSessionLocal() as session:
            async with AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=20.0,
                max_retries=0,
            ) as client:
                try:
                    async for event_name, data in stream_agent(
                        message=payload.message,
                        session=session,
                        client=client,
                    ):
                        if await request.is_disconnected():
                            break

                        yield format_sse(event_name, data)

                except asyncio.CancelledError:
                    logger.info("클라이언트 연결 종료")
                    raise

                except Exception:
                    logger.exception("SSE 응답 처리 실패")
                    yield format_sse(
                        "error",
                        {
                            "code": "STREAM_FAILED",
                            "message": "스트리밍 연결에 문제가 발생했습니다.",
                        },
                    )

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )