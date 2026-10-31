import asyncio
import json
import logging
from collections.abc import AsyncIterator
from time import perf_counter
from typing import Any

from openai import AsyncOpenAI, OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.context import build_conversation_input
from app.agent.metrics import AgentMetrics
from app.agent.service import MAX_TOOL_ROUNDS, SYSTEM_PROMPT
from app.agent.tool_definitions import AGENT_TOOLS
from app.core.config import settings
from app.tools.registry import execute_tool

logger = logging.getLogger(__name__)


async def stream_agent(
    message: str,
    session: AsyncSession,
    client: AsyncOpenAI,
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    # 과거 대화는 DB에서 읽은 메시지만 사용한다.
    conversation: list[Any] = build_conversation_input(
        message=message,
        history=history,
    )
    metrics = AgentMetrics()
    answer_started = False
    tool_count = 0

    yield "started", {
        "run_id": metrics.run_id,
        "message": "경기 분석을 시작합니다.",
    }

    try:
        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            # Tool 인자는 응답 완료 후 실행하지만, 일반 텍스트는 즉시 전송한다.
            stream = await client.responses.create(
                model=settings.openai_model,
                instructions=SYSTEM_PROMPT,
                input=conversation,
                tools=AGENT_TOOLS,
                parallel_tool_calls=False,
                max_output_tokens=1024,
                store=False,
                stream=True,
            )

            completed_response = None
            round_answer = False

            async for event in stream:
                if event.type == "response.output_text.delta":
                    round_answer = True
                    answer_started = True
                    yield "answer_delta", {"delta": event.delta}

                elif event.type == "response.completed":
                    completed_response = event.response
                    usage = getattr(event.response, "usage", None)
                    metrics.record_llm_call(
                        input_tokens=(
                            usage.input_tokens if usage is not None else None
                        ),
                        output_tokens=(
                            usage.output_tokens if usage is not None else None
                        ),
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
                raise RuntimeError("모델 응답 완료 이벤트를 받지 못했습니다.")

            # 모델의 function_call을 포함한 응답 전체를 다음 round에 보존한다.
            conversation.extend(
                item.model_dump(exclude_none=True)
                for item in completed_response.output
            )
            tool_calls = [
                item
                for item in completed_response.output
                if item.type == "function_call"
            ]

            if not tool_calls:
                if not round_answer:
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
                    "rounds": round_number,
                }
                return

            for tool_call in tool_calls:
                tool_count += 1
                yield "tool_start", {
                    "tool": tool_call.name,
                    "round": round_number,
                }

                tool_started_at = perf_counter()

                try:
                    arguments = json.loads(tool_call.arguments)

                    if not isinstance(arguments, dict):
                        raise ValueError("Tool 인자는 JSON 객체여야 합니다.")

                    result = await asyncio.wait_for(
                        execute_tool(
                            session=session,
                            tool_name=tool_call.name,
                            arguments=arguments,
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

                conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": tool_call.call_id,
                        "output": json.dumps(result, ensure_ascii=False),
                    }
                )

        raise RuntimeError("Agent 최대 실행 단계를 초과했습니다.")

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
