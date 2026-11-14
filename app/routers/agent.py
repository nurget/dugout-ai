import asyncio
import logging
from datetime import date, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from zoneinfo import ZoneInfo

from app.agent.context import AgentContext
from app.agent.streaming import stream_agent
from app.core.auth import CurrentUser
from app.core.config import settings
from app.db.session import get_db, get_session_factory
from app.schemas.chat import ChatRequest
from app.schemas.recommendation_review import RecommendationReviewRequest
from app.utils.sse import format_sse

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
from app.repositories.recommendation_review import (
    get_recommendation_review,
    upsert_recommendation_review,
)

from app.repositories.conversation_owner import (
    assign_conversation_owner,
    require_conversation_access,
)
from app.services.data_catalog import get_latest_dataset_statuses
from app.services.team_codes import normalize_official_team_code
from app.models.agent_run import AgentRun


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/agent",
    tags=["Agent"],
)

SessionDep = Annotated[AsyncSession, Depends(get_db)]
SessionFactoryDep = Annotated[
    async_sessionmaker[AsyncSession],
    Depends(get_session_factory),
]


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatRequest,
    request: Request,
    current_user: CurrentUser,
    session_factory: SessionFactoryDep,
):
    if not settings.openai_api_key:
        raise HTTPException(
            status_code=503,
            detail="AI 서비스가 설정되지 않았습니다.",
        )

    requested_as_of = payload.as_of_date or datetime.now(
        ZoneInfo("Asia/Seoul")
    ).date()
    if requested_as_of > datetime.now(ZoneInfo("Asia/Seoul")).date():
        raise HTTPException(status_code=422, detail="분석 기준일은 미래일 수 없습니다.")

    # 권한 검사는 SSE 응답이 시작되기 전에 수행한다.
    if payload.conversation_id is not None:
        async with session_factory() as db:
            conversation_id = str(payload.conversation_id)

            await require_conversation_access(
                session=db,
                conversation_id=conversation_id,
                user_id=str(current_user.id),
                team_code=current_user.team_code,
            )

            existing = await get_conversation(
                db,
                conversation_id,
            )

            if existing is None:
                raise HTTPException(
                    status_code=404,
                    detail="대화를 찾을 수 없습니다.",
                )

    async def generate():
        # Tool 실행 세션과 감사 기록 세션을 분리한다.
        async with session_factory() as session:
            async with session_factory() as audit_db:
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
                    analysis_results: list[dict] = []

                    try:
                        statuses = await get_latest_dataset_statuses(session)
                        data_snapshot_ids = {
                            row["dataset"]: row["snapshot_id"]
                            for row in statuses
                        }
                        context = AgentContext(
                            user_id=str(current_user.id),
                            team_code=current_user.team_code,
                            role=current_user.role,
                            as_of_date=requested_as_of,
                            data_snapshot_ids=data_snapshot_ids,
                        )
                        if payload.conversation_id is None:
                            conversation = (
                                await create_conversation(session)
                            )

                            await assign_conversation_owner(
                                session=session,
                                conversation_id=conversation.id,
                                user_id=context.user_id,
                                team_code=context.team_code,
                            )

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
                                    {
                                        "message": (
                                            "대화를 찾을 수 없습니다."
                                        )
                                    },
                                )
                                return

                            previous = await get_recent_messages(
                                session,
                                conversation.id,
                                limit=20,
                            )

                            history = [
                                {
                                    "role": item.role,
                                    "content": item.content,
                                }
                                for item in previous
                            ]

                        yield format_sse(
                            "conversation",
                            {
                                "conversation_id": conversation.id,
                            },
                        )

                        async for event_name, data in stream_agent(
                            message=payload.message,
                            session=session,
                            client=client,
                            history=history,
                            context=context,
                        ):
                            if await request.is_disconnected():
                                break

                            if event_name == "started":
                                run_id = data["run_id"]

                                await create_agent_run(
                                    db=audit_db,
                                    run_id=run_id,
                                    conversation_id=conversation.id,
                                    as_of_date=requested_as_of,
                                    data_snapshot_ids=data_snapshot_ids,
                                    model_name=data.get("model"),
                                    prompt_version=data.get("prompt_version"),
                                    tool_schema_version=data.get("tool_schema_version"),
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
                                    duration_ms=data.get(
                                        "duration_ms"
                                    ),
                                    success=data["ok"],
                                    error_code=(
                                        (data.get("error") or {}).get(
                                            "code"
                                        )
                                    ),
                                )

                                current_tool_sequence = None

                            elif event_name == "answer_delta":
                                answer_parts.append(
                                    data["delta"]
                                )

                            elif event_name == "analysis_result":
                                data = {**data, "run_id": run_id}
                                analysis_results.append(data)

                            elif event_name == "completed":
                                await save_exchange(
                                    session=session,
                                    conversation=conversation,
                                    user_message=payload.message,
                                    assistant_message="".join(
                                        answer_parts
                                    ),
                                    analysis_results=analysis_results,
                                )

                                await finish_agent_run(
                                    db=audit_db,
                                    run_id=run_id,
                                    status="COMPLETED",
                                    metrics=data,
                                )

                                run_finished = True

                            elif event_name == "error":
                                if run_id:
                                    await finish_agent_run(
                                        db=audit_db,
                                        run_id=run_id,
                                        status="FAILED",
                                        metrics=data,
                                        error_code=data.get(
                                            "code",
                                            "AGENT_EXECUTION_FAILED",
                                        ),
                                    )

                                    run_finished = True

                            yield format_sse(
                                event_name,
                                data,
                            )

                            if event_name in (
                                "completed",
                                "error",
                            ):
                                return

                    except asyncio.CancelledError:
                        await session.rollback()
                        await audit_db.rollback()
                        raise

                    except Exception:
                        logger.exception(
                            "Agent 실행 또는 이력 저장 실패"
                        )

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
                                logger.exception(
                                    "Agent 실패 이력 저장 실패"
                                )

                        yield format_sse(
                            "error",
                            {
                                "code": "STREAM_FAILED",
                                "message": (
                                    "대화 처리 중 문제가 발생했습니다."
                                ),
                            },
                        )

                    finally:
                        if run_id and not run_finished:
                            # 연결 중단은 정상 완료로 기록하지 않는다.
                            try:
                                await audit_db.rollback()

                                await finish_agent_run(
                                    db=audit_db,
                                    run_id=run_id,
                                    status="CANCELLED",
                                    error_code="STREAM_INTERRUPTED",
                                )

                            except Exception:
                                logger.exception(
                                    "Agent 취소 이력 저장 실패"
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
    current_user: CurrentUser,
):
    await require_conversation_access(
        session=session,
        conversation_id=str(conversation_id),
        user_id=str(current_user.id),
        team_code=current_user.team_code,
    )

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
                "analysis_results": message.analysis_results or [],
                "created_at": message.created_at.isoformat(),
            }
            for message in messages
        ],
    }


@router.get("/runs/{run_id}")
async def get_agent_run_detail(
    run_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
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

    await require_conversation_access(
        session=session,
        conversation_id=run.conversation_id,
        user_id=str(current_user.id),
        team_code=current_user.team_code,
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
        "llm_call_metrics": run.llm_call_metrics or [],
        "model_name": run.model_name,
        "prompt_version": run.prompt_version,
        "tool_schema_version": run.tool_schema_version,
        "as_of_date": run.as_of_date.isoformat() if run.as_of_date else None,
        "data_snapshot_ids": run.data_snapshot_ids or {},
        "error_code": run.error_code,
        "started_at": run.started_at.isoformat(),
        "finished_at": (
            run.finished_at.isoformat()
            if run.finished_at
            else None
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


async def _get_reviewable_recommendation(
    *,
    session: AsyncSession,
    run_id: str,
    current_user,
) -> tuple[AgentRun, dict]:
    if current_user.role not in {"COACH", "MANAGER"}:
        raise HTTPException(status_code=403, detail="코치 또는 관리자만 평가할 수 있습니다.")
    run = await session.get(AgentRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Agent 실행 기록을 찾을 수 없습니다.")
    await require_conversation_access(
        session=session,
        conversation_id=run.conversation_id,
        user_id=str(current_user.id),
        team_code=current_user.team_code,
    )
    if run.status != "COMPLETED":
        raise HTTPException(status_code=409, detail="완료된 추천만 평가할 수 있습니다.")

    messages = await get_messages(session, run.conversation_id)
    for message in messages:
        if message.role != "assistant":
            continue
        for result in message.analysis_results or []:
            if (
                result.get("type") == "bullpen_comparison"
                and result.get("run_id") == run_id
            ):
                if normalize_official_team_code(
                    result.get("team_code", "")
                ) != normalize_official_team_code(current_user.team_code):
                    raise HTTPException(status_code=404, detail="평가할 추천을 찾을 수 없습니다.")
                if not result.get("candidates"):
                    raise HTTPException(status_code=409, detail="평가 가능한 후보 비교 결과가 없습니다.")
                return run, result
    raise HTTPException(status_code=404, detail="평가할 추천 결과를 찾을 수 없습니다.")


def _serialize_recommendation_review(review) -> dict:
    return {
        "run_id": review.run_id,
        "outcome": review.outcome,
        "acceptable_candidate_ids": review.acceptable_candidate_ids,
        "reviewed_at": review.updated_at.isoformat(),
    }


@router.get("/runs/{run_id}/recommendation-review")
async def get_run_recommendation_review(
    run_id: UUID,
    session: SessionDep,
    current_user: CurrentUser,
):
    await _get_reviewable_recommendation(
        session=session,
        run_id=str(run_id),
        current_user=current_user,
    )
    review = await get_recommendation_review(
        session,
        run_id=str(run_id),
        reviewer_user_id=str(current_user.id),
    )
    return {"review": _serialize_recommendation_review(review) if review else None}


@router.put("/runs/{run_id}/recommendation-review")
async def save_run_recommendation_review(
    run_id: UUID,
    payload: RecommendationReviewRequest,
    session: SessionDep,
    current_user: CurrentUser,
):
    run, result = await _get_reviewable_recommendation(
        session=session,
        run_id=str(run_id),
        current_user=current_user,
    )
    candidate_ids = {
        str(candidate["pitcher_id"])
        for candidate in result["candidates"]
    }
    requested_ids = set(payload.acceptable_candidate_ids)
    if not requested_ids.issubset(candidate_ids):
        raise HTTPException(
            status_code=422,
            detail="평가 대상에는 비교 결과에 포함된 후보만 선택할 수 있습니다.",
        )
    review = await upsert_recommendation_review(
        session,
        run_id=str(run_id),
        reviewer_user_id=str(current_user.id),
        team_code=result["team_code"],
        as_of_date=date.fromisoformat(result["as_of_date"]),
        outcome=payload.outcome,
        acceptable_candidate_ids=payload.acceptable_candidate_ids,
        recommendation_snapshot={
            "team_code": result["team_code"],
            "as_of_date": result["as_of_date"],
            "comparison_status": result.get("comparison_status"),
            "coverage": result.get("coverage"),
            "candidates": result["candidates"],
            "withheld": result.get("withheld", []),
        },
        data_snapshot_ids=run.data_snapshot_ids,
    )
    return {"review": _serialize_recommendation_review(review)}
