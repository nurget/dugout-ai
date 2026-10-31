from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_run import (
    AgentRun,
    AgentToolExecution,
)


async def create_agent_run(
    db: AsyncSession,
    run_id: str,
    conversation_id: str,
) -> None:
    db.add(
        AgentRun(
            run_id=run_id,
            conversation_id=conversation_id,
            status="RUNNING",
        )
    )
    await db.commit()


async def start_tool_execution(
    db: AsyncSession,
    run_id: str,
    sequence: int,
    tool_name: str,
) -> None:
    db.add(
        AgentToolExecution(
            run_id=run_id,
            sequence=sequence,
            tool_name=tool_name,
        )
    )
    await db.commit()


async def finish_tool_execution(
    db: AsyncSession,
    run_id: str,
    sequence: int,
    duration_ms: float | None,
    success: bool,
    error_code: str | None,
) -> None:
    result = await db.execute(
        select(AgentToolExecution).where(
            AgentToolExecution.run_id == run_id,
            AgentToolExecution.sequence == sequence,
        )
    )

    execution = result.scalar_one_or_none()

    if execution is None:
        raise ValueError("Tool 실행 기록을 찾을 수 없습니다.")

    execution.duration_ms = duration_ms
    execution.success = success
    execution.error_code = error_code

    await db.commit()


async def finish_agent_run(
    db: AsyncSession,
    run_id: str,
    status: str,
    metrics: dict | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    run = await db.get(AgentRun, run_id)

    if run is None:
        raise ValueError("Agent 실행 기록을 찾을 수 없습니다.")

    metrics = metrics or {}

    run.status = status
    run.duration_ms = metrics.get("duration_ms")
    run.llm_calls = metrics.get("llm_calls", 0)
    run.input_tokens = metrics.get("input_tokens")
    run.output_tokens = metrics.get("output_tokens")

    run.error_code = error_code
    run.error_message = error_message

    run.finished_at = datetime.now(timezone.utc)

    await db.commit()


async def get_agent_run(
    db: AsyncSession,
    run_id: str,
) -> AgentRun | None:
    return await db.get(AgentRun, run_id)


async def get_agent_run_tools(
    db: AsyncSession,
    run_id: str,
) -> list[AgentToolExecution]:
    result = await db.execute(
        select(AgentToolExecution)
        .where(AgentToolExecution.run_id == run_id)
        .order_by(AgentToolExecution.sequence.asc())
    )

    return list(result.scalars().all())