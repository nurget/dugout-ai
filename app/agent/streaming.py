import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from openai import AsyncOpenAI, OpenAIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.service import MAX_TOOL_ROUNDS, SYSTEM_PROMPT
from app.agent.tool_definitions import AGENT_TOOLS
from app.core.config import settings
from app.tools.registry import execute_tool

logger = logging.getLogger(__name__)


async def stream_agent(
    message: str,
    session: AsyncSession,
    client: AsyncOpenAI,
) -> AsyncIterator[tuple[str, dict[str, Any]]]:
    conversation: list[Any] = [
        {"role": "user", "content": message}
    ]
    tool_history = []
    answer_started = False

    yield "started", {"message": "경기 분석을 시작합니다."}

    try:
        for round_number in range(1, MAX_TOOL_ROUNDS + 1):
            # Tool 인자는 조각으로 도착할 수 있으므로 응답이 완성된 뒤 실행한다.
            # 반면 답변 텍스트는 사용자가 기다리지 않도록 즉시 내보낸다.
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

                    yield "answer_delta", {
                        "delta": event.delta,
                    }

                elif event.type == "response.completed":
                    completed_response = event.response

                elif event.type in (
                    "response.failed",
                    "response.incomplete",
                    "error",
                ):
                    raise RuntimeError(
                        f"모델 응답이 정상 완료되지 않았습니다: {event.type}"
                    )

            if completed_response is None:
                raise RuntimeError(
                    "모델 응답 완료 이벤트를 받지 못했습니다."
                )

            # 모델이 생성한 함수 호출과 메시지를 다음 호출에도 보존한다.
            # Tool 결과만 전달하면 이전 호출의 맥락이 끊어질 수 있다.
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
                    raise RuntimeError(
                        "모델이 답변을 생성하지 않았습니다."
                    )

                yield "completed", {
                    "rounds": round_number,
                    "tool_count": len(tool_history),
                }
                return

            for tool_call in tool_calls:
                yield "tool_start", {
                    "tool": tool_call.name,
                    "round": round_number,
                }

                try:
                    arguments = json.loads(tool_call.arguments)

                    if not isinstance(arguments, dict):
                        raise ValueError(
                            "Tool 인자는 JSON 객체여야 합니다."
                        )

                    # SQL 접근은 Registry에 위임한다.
                    # Agent가 DB 구조에 직접 의존하지 않도록 유지한다.
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

                    # Timeout으로 취소된 DB 작업 후 세션을 재사용하지 않도록!
                    await session.rollback()

                tool_history.append({
                    "tool": tool_call.name,
                    "result": result,
                })

                yield "tool_result", {
                    "tool": tool_call.name,
                    "ok": result["ok"],
                    "error": result.get("error"),
                }

                conversation.append({
                    "type": "function_call_output",
                    "call_id": tool_call.call_id,
                    "output": json.dumps(
                        result,
                        ensure_ascii=False,
                    ),
                })

        raise RuntimeError(
            "Agent 최대 실행 단계를 초과했습니다."
        )

    except asyncio.CancelledError:
        logger.info("Agent 스트리밍 요청 취소")
        raise

    except (OpenAIError, RuntimeError) as error:
        logger.exception("Agent 스트리밍 실패")

        yield "error", {
            "code": "AGENT_EXECUTION_FAILED",
            "message": "분석 중 문제가 발생했습니다.",
            "partial_answer": answer_started,
        }