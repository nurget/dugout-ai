from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from app.db.base import Base
from app.models.agent_run import AgentRun, AgentToolExecution
from app.models.conversation import Conversation
from app.repositories.agent_run import (
    count_stale_runs,
    reconcile_stale_runs,
    stale_run_cutoff,
)


@pytest.mark.asyncio
async def test_only_stale_running_jobs_are_recovered():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:"
    )

    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                tables=[
                    Conversation.__table__,
                    AgentRun.__table__,
                    AgentToolExecution.__table__,
                ],
            )

        session_factory = async_sessionmaker(
            engine,
            expire_on_commit=False,
        )

        now = datetime.now(timezone.utc)

        old_run_id = str(uuid4())
        recent_run_id = str(uuid4())
        completed_run_id = str(uuid4())
        conversation_id = str(uuid4())

        async with session_factory() as db:
            db.add(Conversation(id=conversation_id))

            db.add_all([
                AgentRun(
                    run_id=old_run_id,
                    conversation_id=conversation_id,
                    status="RUNNING",
                    started_at=now - timedelta(minutes=60),
                ),
                AgentRun(
                    run_id=recent_run_id,
                    conversation_id=conversation_id,
                    status="RUNNING",
                    started_at=now - timedelta(minutes=2),
                ),
                AgentRun(
                    run_id=completed_run_id,
                    conversation_id=conversation_id,
                    status="COMPLETED",
                    started_at=now - timedelta(minutes=60),
                ),
            ])

            db.add(
                AgentToolExecution(
                    run_id=old_run_id,
                    sequence=1,
                    tool_name="get_game_state",
                    success=None,
                )
            )

            await db.commit()

        cutoff = stale_run_cutoff(
            minutes=30,
            now=now,
        )

        async with session_factory() as db:
            count = await count_stale_runs(db, cutoff)

            assert count == 1

            recovered = await reconcile_stale_runs(
                db,
                cutoff,
            )

            assert recovered == [old_run_id]

        async with session_factory() as db:
            old_run = await db.get(AgentRun, old_run_id)
            recent_run = await db.get(AgentRun, recent_run_id)
            completed_run = await db.get(AgentRun, completed_run_id)

            assert old_run is not None
            assert recent_run is not None
            assert completed_run is not None

            assert old_run.status == "INTERRUPTED"
            assert old_run.error_code == "RUN_STALE"
            assert old_run.finished_at is not None

            assert recent_run.status == "RUNNING"
            assert completed_run.status == "COMPLETED"

            from sqlalchemy import select

            result = await db.execute(
                select(AgentToolExecution).where(
                    AgentToolExecution.run_id == old_run_id
                )
            )

            tool = result.scalar_one()

            assert tool.success is None
            assert tool.error_code == "RUN_INTERRUPTED"

    finally:
        await engine.dispose()


def test_invalid_recovery_threshold():
    with pytest.raises(ValueError):
        stale_run_cutoff(minutes=0)