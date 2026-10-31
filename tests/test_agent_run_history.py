from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from app.repositories.agent_run import finish_agent_run


@pytest.mark.asyncio
async def test_finish_agent_run_records_metrics():
    run = type("FakeAgentRun", (), {})()
    run.run_id = "test-run"
    run.status = "RUNNING"

    db = AsyncMock()
    db.get.return_value = run

    await finish_agent_run(
        db=db,
        run_id="test-run",
        status="COMPLETED",
        metrics={
            "duration_ms": 3200.5,
            "llm_calls": 3,
            "input_tokens": 1500,
            "output_tokens": 400,
        },
    )

    assert run.status == "COMPLETED"
    assert run.duration_ms == 3200.5
    assert run.llm_calls == 3
    assert run.input_tokens == 1500
    assert run.output_tokens == 400
    assert run.finished_at is not None

    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_run_preserves_error():
    run = type("FakeAgentRun", (), {})()
    run.run_id = "failed-run"

    db = AsyncMock()
    db.get.return_value = run

    await finish_agent_run(
        db=db,
        run_id="failed-run",
        status="FAILED",
        error_code="STREAM_FAILED",
    )

    assert run.status == "FAILED"
    assert run.error_code == "STREAM_FAILED"
    assert run.input_tokens is None
    assert run.output_tokens is None

    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_missing_run_raises_error():
    db = AsyncMock()
    db.get.return_value = None

    with pytest.raises(
        ValueError,
        match="Agent 실행 기록을 찾을 수 없습니다",
    ):
        await finish_agent_run(
            db=db,
            run_id="missing-run",
            status="FAILED",
        )

    db.commit.assert_not_awaited()