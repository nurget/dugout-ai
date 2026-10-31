from datetime import datetime, timezone, timedelta

from sqlalchemy import select, func, update
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

def stale_run_cutoff(
    minutes: int,
    now: datetime | None = None,
) -> datetime:
    if minutes < 1:
        raise ValueError("복구 기준은 1분 이상이어야 합니다.")

    current_time = now or datetime.now(timezone.utc)
    return current_time - timedelta(minutes=minutes)


async def count_stale_runs(
    db: AsyncSession,
    cutoff: datetime,
) -> int:
    result = await db.scalar(
        select(func.count())
        .select_from(AgentRun)
        .where(
            AgentRun.status == "RUNNING",
            AgentRun.started_at < cutoff,
        )
    )

    return result or 0


async def reconcile_stale_runs(
    db: AsyncSession,
    cutoff: datetime,
) -> list[str]:
    now = datetime.now(timezone.utc)

    # 실행 중인 요청을 잘못 종료하지 않도록 상태와 시작 시각을 UPDATE 조건에서 다시 확인한다.
    result = await db.execute(
        update(AgentRun)
        .where(
            AgentRun.status == "RUNNING",
            AgentRun.started_at < cutoff,
        )
        .values(
            status="INTERRUPTED",
            finished_at=now,
            error_code="RUN_STALE",
            error_message=(
                "복구 기준 시간을 초과한 미완료 실행입니다. "
                "실제 종료 원인은 서버 로그 확인이 필요합니다."
            ),
        )
        .returning(AgentRun.run_id)
    )

    recovered_ids = list(result.scalars().all())

    if recovered_ids:
        # 실행 결과를 받지 못한 Tool에는 성공이나 실패를 임의로 기록하지 않는다.
        await db.execute(
            update(AgentToolExecution)
            .where(
                AgentToolExecution.run_id.in_(recovered_ids),
                AgentToolExecution.success.is_(None),
            )
            .values(error_code="RUN_INTERRUPTED")
        )

    await db.commit()
    return recovered_ids