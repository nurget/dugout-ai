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

from app.repositories.agent_run import (
    create_agent_run,
    start_tool_execution,
    finish_tool_execution,
    finish_agent_run,
    get_agent_run,
    get_agent_run_tools,
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
        # Agent의 Tool 실행 세션과 감사 이력 저장 세션을 분리한다.
        # Tool 쿼리가 실패하거나 rollback되어도 실행 기록은 유지되어야 한다.
        async with AsyncSessionLocal() as session:
            async with AsyncSessionLocal() as audit_db:
                async with AsyncOpenAI(
                    api_key=settings.openai_api_key,
                    timeout=20.0,
                    max_retries=0,
                ) as client:
                    run_id = None
                    run_finished = False
                    tool_sequence = 0
                    current_tool_sequence = None
                    answer_parts: list[str] = []

                    try:
                        if payload.conversation_id is None:
                            conversation = await create_conversation(session)
                            # 실행 이력이 대화 ID를 참조하므로 부모 대화를
                            # 먼저 확정한다. 실패 시 빈 대화는 남을 수 있다.
                            await session.commit()
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

                            previous = await get_recent_messages(
                                session,
                                conversation.id,
                                limit=20,
                            )
                            history = [
                                {"role": item.role, "content": item.content}
                                for item in previous
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
                                break

                            if event_name == "started":
                                run_id = data["run_id"]
                                await create_agent_run(
                                    db=audit_db,
                                    run_id=run_id,
                                    conversation_id=conversation.id,
                                )

                            elif event_name == "tool_start":
                                tool_sequence += 1
                                current_tool_sequence = tool_sequence
                                await start_tool_execution(
                                    db=audit_db,
                                    run_id=run_id,
                                    sequence=tool_sequence,
                                    tool_name=data["tool"],
                                )

                            elif event_name == "tool_result":
                                await finish_tool_execution(
                                    db=audit_db,
                                    run_id=run_id,
                                    sequence=current_tool_sequence,
                                    duration_ms=data.get("duration_ms"),
                                    success=data["ok"],
                                    error_code=(
                                        (data.get("error") or {}).get("code")
                                    ),
                                )
                                current_tool_sequence = None

                            elif event_name == "answer_delta":
                                answer_parts.append(data["delta"])

                            elif event_name == "completed":
                                await save_exchange(
                                    session=session,
                                    conversation=conversation,
                                    user_message=payload.message,
                                    assistant_message="".join(answer_parts),
                                )
                                await finish_agent_run(
                                    db=audit_db,
                                    run_id=run_id,
                                    status="COMPLETED",
                                    metrics=data,
                                )
                                run_finished = True

                            elif event_name == "error" and run_id:
                                await finish_agent_run(
                                    db=audit_db,
                                    run_id=run_id,
                                    status="FAILED",
                                    error_code=data.get(
                                        "code", "AGENT_EXECUTION_FAILED"
                                    ),
                                )
                                run_finished = True

                            yield format_sse(event_name, data)

                            if event_name in ("completed", "error"):
                                return

                    except asyncio.CancelledError:
                        await session.rollback()
                        await audit_db.rollback()
                        raise

                    except Exception:
                        logger.exception("Agent 실행 또는 이력 저장 실패")
                        await session.rollback()
                        await audit_db.rollback()

                        if run_id and not run_finished:
                            try:
                                await finish_agent_run(
                                    db=audit_db,
                                    run_id=run_id,
                                    status="FAILED",
                                    error_code="STREAM_FAILED",
                                )
                                run_finished = True
                            except Exception:
                                logger.exception("Agent 실패 이력 저장 실패")

                        yield format_sse(
                            "error",
                            {
                                "code": "STREAM_FAILED",
                                "message": "대화 처리 중 문제가 발생했습니다.",
                            },
                        )

                    finally:
                        if run_id and not run_finished:
                            # 연결 종료와 요청 취소는 정상 완료로 기록하지 않는다.
                            try:
                                await audit_db.rollback()
                                await finish_agent_run(
                                    db=audit_db,
                                    run_id=run_id,
                                    status="CANCELLED",
                                    error_code="STREAM_INTERRUPTED",
                                )
                            except Exception:
                                logger.exception("Agent 취소 이력 저장 실패")

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

@router.get("/runs/{run_id}")
async def get_agent_run_detail(
    run_id: UUID,
    session: SessionDep,
):
    run = await get_agent_run(
        session,
        str(run_id),
    )

    if run is None:
        raise HTTPException(
            status_code=404,
            detail="Agent 실행 기록을 찾을 수 없습니다.",
        )

    tools = await get_agent_run_tools(
        session,
        run.run_id,
    )

    return {
        "run_id": run.run_id,
        "conversation_id": run.conversation_id,
        "status": run.status,
        "duration_ms": run.duration_ms,
        "llm_calls": run.llm_calls,
        "input_tokens": run.input_tokens,
        "output_tokens": run.output_tokens,
        "error_code": run.error_code,
        "started_at": run.started_at.isoformat(),
        "finished_at": (
            run.finished_at.isoformat()
            if run.finished_at else None
        ),
        "tools": [
            {
                "sequence": item.sequence,
                "name": item.tool_name,
                "duration_ms": item.duration_ms,
                "success": item.success,
                "error_code": item.error_code,
            }
            for item in tools
        ],
    }