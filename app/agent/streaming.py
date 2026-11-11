import asyncio
import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any, Callable

from openai import AsyncOpenAI, OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import AgentContext, build_conversation_input
from app.agent.metrics import AgentMetrics
from app.agent.prompt import MAX_TOOL_ROUNDS, SYSTEM_PROMPT
from app.agent.versions import agent_versions
from app.agent.tool_definitions import (
    AGENT_TOOLS,
    FINALIZE_ANALYSIS_TOOL_NAME,
)
from app.core.config import settings
from app.tools.registry import execute_tool

logger = logging.getLogger(__name__)


def record_response_usage(
    metrics: AgentMetrics,
    response: Any,
    *,
    stage: str,
    duration_ms: float | None = None,
) -> None:
    usage = getattr(response, "usage", None)
    input_details = getattr(usage, "input_tokens_details", None)
    cached_tokens = (
        input_details.get("cached_tokens")
        if isinstance(input_details, dict)
        else getattr(input_details, "cached_tokens", None)
    )
    metrics.record_llm_call(
        input_tokens=(usage.input_tokens if usage is not None else None),
        output_tokens=(usage.output_tokens if usage is not None else None),
        cached_input_tokens=cached_tokens,
        stage=stage,
        duration_ms=duration_ms,
    )


def comparison_event(result: dict[str, Any]) -> dict[str, Any]:
    comparison = result["data"]
    return {
        "type": "bullpen_comparison",
        "team_code": comparison["team_code"],
        "as_of_date": comparison["as_of_date"],
        "data_through_date": comparison.get("data_through_date"),
        "data_snapshot_id": comparison.get("data_snapshot_id"),
        "coverage": comparison.get("coverage"),
        "provenance": comparison.get("provenance"),
        "comparison_status": comparison.get("comparison_status", "COMPARABLE"),
        "availability_verified": False,
        "candidates": [
            {
                "pitcher_id": row["pitcher_id"],
                "pitcher_name": row["pitcher_name"],
                "k_minus_bb_pct": row["k_minus_bb_pct"],
                "games": row.get("games"),
                "batters_faced": row["batters_faced"],
                "data_through_date": row.get("data_through_date"),
                "identity_status": row.get("identity_status"),
                "identity_source": row.get("identity_source"),
                "pitches_last_3_days": row["pitches_last_3_days"],
                "consecutive_days": row["consecutive_days"],
                "workload_status": row["workload_status"],
            }
            for row in comparison["ranking"]
        ],
        "withheld": comparison["withheld"],
    }


async def stream_agent(
    message: str,
    session: AsyncSession,
    client: AsyncOpenAI,
    history: list[dict[str, str]] | None = None,
    context: AgentContext | None = None,
    on_tool_call: Callable[[str, dict[str, Any]], None] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    conversation: list[Any] = build_conversation_input(
        message=message,
        history=history,
    )
    versions = agent_versions(settings.openai_model)
    metrics = AgentMetrics(versions=versions)
    answer_started = False
    final_round = MAX_TOOL_ROUNDS + 1

    yield "started", {
        "run_id": metrics.run_id,
        "message": "경기 분석을 시작합니다.",
        "as_of_date": context.as_of_date.isoformat() if context and context.as_of_date else None,
        "data_snapshot_ids": context.data_snapshot_ids if context else {},
        **versions,
    }

    try:
        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            llm_started_at = perf_counter()
            response = await client.responses.create(
                model=settings.openai_model,
                instructions=SYSTEM_PROMPT,
                input=conversation,
                tools=AGENT_TOOLS,
                tool_choice="required",
                parallel_tool_calls=False,
                max_output_tokens=1024,
                store=False,
            )
            record_response_usage(
                metrics,
                response,
                stage="PLAN",
                duration_ms=(perf_counter() - llm_started_at) * 1000,
            )

            tool_calls = [
                item for item in response.output
                if item.type == "function_call"
            ]
            if not tool_calls:
                raise RuntimeError(
                    "계획 단계에서 Tool 호출을 생성하지 않았습니다."
                )

            conversation.extend(
                item.model_dump(exclude_none=True)
                for item in tool_calls
            )
            finalize_requested = False

            for tool_call in tool_calls:
                if on_tool_call is not None and tool_call.name != FINALIZE_ANALYSIS_TOOL_NAME:
                    try:
                        captured_arguments = json.loads(tool_call.arguments)
                    except (TypeError, json.JSONDecodeError):
                        captured_arguments = {}
                    on_tool_call(
                        tool_call.name,
                        captured_arguments if isinstance(captured_arguments, dict) else {},
                    )
                if tool_call.name == FINALIZE_ANALYSIS_TOOL_NAME:
                    conversation.append({
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps({"ok": True}),
                    })
                    finalize_requested = True
                    continue

                yield "tool_start", {
                    "tool": tool_call.name,
                    "round": round_number,
                }
                tool_started_at = perf_counter()

                try:
                    arguments = json.loads(tool_call.arguments)
                    if not isinstance(arguments, dict):
                        raise ValueError(
                            "Tool 인자는 JSON 객체여야 합니다."
                        )
                    result = await asyncio.wait_for(
                        execute_tool(
                            session=session,
                            tool_name=tool_call.name,
                            arguments=arguments,
                            context=context,
                        ),
                        timeout=10.0,
                    )
                except (ValueError, json.JSONDecodeError):
                    result = {
                        "ok": False,
                        "error": {
                            "code": "INVALID_ARGUMENTS",
                            "message": "Tool 입력이 올바르지 않습니다.",
                        },
                    }
                except TimeoutError:
                    result = {
                        "ok": False,
                        "error": {
                            "code": "TOOL_TIMEOUT",
                            "message": "Tool 실행 시간이 초과됐습니다.",
                        },
                    }
                    await session.rollback()

                duration_ms = (perf_counter() - tool_started_at) * 1000
                metrics.record_tool(
                    name=tool_call.name,
                    duration_ms=duration_ms,
                    success=result["ok"],
                )

                yield "tool_result", {
                    "tool": tool_call.name,
                    "ok": result["ok"],
                    "error": result.get("error"),
                    "duration_ms": round(duration_ms, 2),
                }

                if (
                    tool_call.name == "compare_bullpen_candidates"
                    and result["ok"]
                ):
                    yield "analysis_result", comparison_event(result)

                conversation.append({
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(result, ensure_ascii=False),
                })

            if finalize_requested:
                final_round = round_number + 1
                break

        final_started_at = perf_counter()
        final_stream = await client.responses.create(
            model=settings.openai_model,
            instructions=SYSTEM_PROMPT,
            input=conversation,
            tools=AGENT_TOOLS,
            tool_choice="none",
            parallel_tool_calls=False,
            max_output_tokens=2048,
            store=False,
            stream=True,
        )
        completed_response = None

        async for event in final_stream:
            if event.type == "response.output_text.delta":
                answer_started = True
                yield "answer_delta", {"delta": event.delta}
            elif event.type == "response.completed":
                completed_response = event.response
                record_response_usage(
                    metrics,
                    event.response,
                    stage="FINAL",
                    duration_ms=(perf_counter() - final_started_at) * 1000,
                )
            elif event.type in (
                "response.failed",
                "response.incomplete",
                "error",
            ):
                raise RuntimeError(
                    "모델 응답이 정상 완료되지 않았습니다: "
                    f"{event.type}"
                )

        if completed_response is None:
            raise RuntimeError(
                "모델 응답 완료 이벤트를 받지 못했습니다."
            )
        if not answer_started:
            raise RuntimeError("모델이 답변을 생성하지 않았습니다.")

        summary = metrics.snapshot()
        logger.info(
            "Agent 실행 완료 run_id=%s duration_ms=%s "
            "llm_calls=%s tool_count=%s",
            summary["run_id"],
            summary["duration_ms"],
            summary["llm_calls"],
            summary["tool_count"],
        )
        yield "completed", {
            **summary,
            "rounds": final_round,
        }

    except asyncio.CancelledError:
        logger.info("Agent 스트리밍 요청 취소")
        raise
    except (OpenAIError, RuntimeError):
        logger.exception(
            "Agent 스트리밍 실패 run_id=%s",
            metrics.run_id,
        )
        yield "error", {
            **metrics.snapshot(),
            "code": "AGENT_EXECUTION_FAILED",
            "message": "분석 중 문제가 발생했습니다.",
            "partial_answer": answer_started,
        }
