from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent import streaming
from app.agent.tool_definitions import FINALIZE_ANALYSIS_TOOL_NAME
from app.utils.sse import format_sse


class FakeToolCall:
    type = "function_call"

    def __init__(
        self,
        name: str,
        arguments: str,
        call_id: str,
    ) -> None:
        self.name = name
        self.arguments = arguments
        self.call_id = call_id

    def model_dump(self, exclude_none=True):
        return {
            "type": self.type,
            "name": self.name,
            "arguments": self.arguments,
            "call_id": self.call_id,
        }


def response(*items):
    return SimpleNamespace(output=list(items), usage=None)


async def fake_stream(events):
    for event in events:
        yield event


def final_stream(*deltas: str):
    completed = SimpleNamespace(output=[], usage=None)
    return fake_stream([
        *[
            SimpleNamespace(
                type="response.output_text.delta",
                delta=delta,
            )
            for delta in deltas
        ],
        SimpleNamespace(
            type="response.completed",
            response=completed,
        ),
    ])


def finalize_call() -> FakeToolCall:
    return FakeToolCall(
        FINALIZE_ANALYSIS_TOOL_NAME,
        "{}",
        "call_finalize",
    )


def test_sse_format():
    event = format_sse(
        "answer_delta",
        {"delta": "KIA 투수"},
    )
    assert event.startswith("event: answer_delta\n")
    assert "KIA 투수" in event
    assert event.endswith("\n\n")


@pytest.mark.asyncio
async def test_stream_agent_with_tool_call(monkeypatch):
    tool_call = FakeToolCall(
        "get_pitcher_status",
        '{"player_id":1}',
        "call_001",
    )
    mock_client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(side_effect=[
                response(tool_call),
                response(finalize_call()),
                final_stream("분석", " 완료"),
            ])
        )
    )
    mock_tool = AsyncMock(return_value={
        "ok": True,
        "data": {"name": "샘플 선발 A"},
    })
    monkeypatch.setattr(streaming, "execute_tool", mock_tool)

    events = [
        event async for event in streaming.stream_agent(
            message="선수 ID 1을 확인해줘.",
            session=None,
            client=mock_client,
        )
    ]
    assert [name for name, _ in events] == [
        "started",
        "tool_start",
        "tool_result",
        "answer_delta",
        "answer_delta",
        "completed",
    ]
    assert "".join(
        data["delta"]
        for name, data in events
        if name == "answer_delta"
    ) == "분석 완료"
    mock_tool.assert_awaited_once()

    second_input = (
        mock_client.responses.create.call_args_list[1].kwargs["input"]
    )
    assert any(
        item.get("type") == "function_call_output"
        and item.get("call_id") == "call_001"
        for item in second_input
    )
    assert (
        mock_client.responses.create.call_args_list[0]
        .kwargs["tool_choice"]
        == "required"
    )
    assert (
        mock_client.responses.create.call_args_list[2]
        .kwargs["tool_choice"]
        == "none"
    )


@pytest.mark.asyncio
async def test_planning_text_is_not_emitted_or_forwarded(monkeypatch):
    planning_message = SimpleNamespace(
        type="message",
        model_dump=lambda exclude_none=True: {
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "중간 설명"}],
        },
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(side_effect=[
                response(planning_message, finalize_call()),
                final_stream("최종 답변"),
            ])
        )
    )

    events = [
        event async for event in streaming.stream_agent(
            message="간단히 답해줘.",
            session=None,
            client=client,
        )
    ]
    answer = "".join(
        data["delta"]
        for name, data in events
        if name == "answer_delta"
    )
    assert answer == "최종 답변"
    assert "중간 설명" not in str(
        client.responses.create.call_args_list[1].kwargs["input"]
    )


@pytest.mark.asyncio
async def test_stream_agent_emits_structured_bullpen_comparison(
    monkeypatch,
):
    tool_call = FakeToolCall(
        "compare_bullpen_candidates",
        '{"as_of_date":"2026-08-15","candidate_ids":["1"]}',
        "call_bullpen",
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(side_effect=[
                response(tool_call),
                response(finalize_call()),
                final_stream("완료"),
            ])
        )
    )
    monkeypatch.setattr(
        streaming,
        "execute_tool",
        AsyncMock(return_value={
            "ok": True,
            "data": {
                "team_code": "KT",
                "as_of_date": "2026-08-15",
                "ranking": [{
                    "pitcher_id": "52060",
                    "pitcher_name": "박영현",
                    "k_minus_bb_pct": 14.83,
                    "batters_faced": 100,
                    "pitches_last_3_days": 0,
                    "consecutive_days": 0,
                    "workload_status": "NO_HIGH_LOAD_FLAG",
                }],
                "withheld": [],
            },
        }),
    )

    events = [
        event async for event in streaming.stream_agent(
            message="후보 비교",
            session=None,
            client=client,
        )
    ]
    analysis = next(
        data for name, data in events if name == "analysis_result"
    )
    assert analysis == {
        "type": "bullpen_comparison",
        "team_code": "KT",
        "as_of_date": "2026-08-15",
        "data_through_date": None,
        "data_snapshot_id": None,
        "coverage": None,
        "provenance": None,
        "comparison_status": "COMPARABLE",
        "availability_verified": False,
        "candidates": [{
            "pitcher_id": "52060",
            "pitcher_name": "박영현",
            "k_minus_bb_pct": 14.83,
            "games": None,
            "batters_faced": 100,
            "data_through_date": None,
            "identity_status": None,
            "identity_source": None,
            "pitches_last_3_days": 0,
            "consecutive_days": 0,
            "workload_status": "NO_HIGH_LOAD_FLAG",
        }],
        "withheld": [],
    }
