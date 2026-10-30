from typing import Annotated
from uuid import UUID

from fastapi.responses import JSONResponse
from fastapi import APIRouter, Depends, HTTPException
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import AgentExecutionError, run_agent
from app.core.config import settings
from app.db.session import get_db
from app.schemas.chat import ChatRequest, ChatResponse

from app.repositories.conversation import (
    create_conversation,
    get_conversation,
    get_messages,
    get_recent_messages,
    save_exchange,
)

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

    # 스트림을 시작하기 전에 대화 존재 여부를 확인한다.
    if payload.conversation_id is not None:
        async with AsyncSessionLocal() as db:
            existing = await get_conversation(
                db,
                str(payload.conversation_id),
            )

            if existing is None:
                raise HTTPException(
                    status_code=404,
                    detail="대화를 찾을 수 없습니다.",
                )

    async def generate():
        async with AsyncSessionLocal() as session:
            async with AsyncOpenAI(
                api_key=settings.openai_api_key,
                timeout=20.0,
                max_retries=0,
            ) as client:
                completed = False
                answer_parts: list[str] = []

                try:
                    if payload.conversation_id is None:
                        conversation = await create_conversation(session)
                        history = []
                    else:
                        conversation = await get_conversation(
                            session,
                            str(payload.conversation_id),
                        )

                        if conversation is None:
                            yield format_sse(
                                "error",
                                {"message": "대화를 찾을 수 없습니다."},
                            )
                            return

                        previous_messages = await get_recent_messages(
                            session,
                            conversation.id,
                            limit=20,
                        )
                        history = [
                            {
                                "role": item.role,
                                "content": item.content,
                            }
                            for item in previous_messages
                        ]

                    yield format_sse(
                        "conversation",
                        {"conversation_id": conversation.id},
                    )

                    async for event_name, data in stream_agent(
                        message=payload.message,
                        session=session,
                        client=client,
                        history=history,
                    ):
                        if await request.is_disconnected():
                            return

                        if event_name == "answer_delta":
                            answer_parts.append(data["delta"])

                        if event_name == "error":
                            yield format_sse(event_name, data)
                            return

                        if event_name == "completed":
                            # completed 이벤트는 DB 저장까지 성공한 뒤 보낸다.
                            await save_exchange(
                                session=session,
                                conversation=conversation,
                                user_message=payload.message,
                                assistant_message="".join(answer_parts),
                            )
                            completed = True

                        yield format_sse(event_name, data)

                    if not completed:
                        yield format_sse(
                            "error",
                            {"message": "AI 분석이 완료되지 않았습니다."},
                        )

                except asyncio.CancelledError:
                    await session.rollback()
                    raise

                except Exception:
                    await session.rollback()
                    logger.exception("대화 스트리밍 및 저장 실패")

                    yield format_sse(
                        "error",
                        {
                            "message": "대화 처리 중 문제가 발생했습니다."
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

@router.get("/conversations/{conversation_id}/messages")
async def get_conversation_messages(
    conversation_id: UUID,
    session: SessionDep,
):
    conversation = await get_conversation(
        session,
        str(conversation_id),
    )

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="대화를 찾을 수 없습니다.",
        )

    messages = await get_messages(
        session,
        conversation.id,
    )

    return {
        "conversation_id": conversation.id,
        "messages": [
            {
                "id": message.id,
                "role": message.role,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
            }
            for message in messages
        ],
    }