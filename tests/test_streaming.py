from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent import streaming
from app.agent.context import AgentContext
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


def test_standalone_workload_tool_is_only_available_for_workload_requests():
    ordinary_tools = streaming.tools_for_message(
        "양현종과 정해영의 누적 성적을 비교해줘."
    )
    workload_tools = streaming.tools_for_message(
        "최근 투구 부담과 휴식일을 확인해줘."
    )

    assert "get_bullpen_workload" not in {
        tool["name"] for tool in ordinary_tools
    }
    assert "get_bullpen_workload" in {
        tool["name"] for tool in workload_tools
    }
    bullpen_candidate_tools = streaming.tools_for_message(
        "오늘 기준으로 두 명을 불펜 후보로 비교해줘."
    )
    assert "compare_pitchers" not in {
        tool["name"] for tool in bullpen_candidate_tools
    }


@pytest.mark.asyncio
async def test_authenticated_team_scope_is_provided_to_planning_model():
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=[
            response(finalize_call()),
            final_stream("KIA 데이터만 조회할 수 있습니다."),
        ]))
    )

    [event async for event in streaming.stream_agent(
        message="LG 구단 투수 데이터를 조회해줘.",
        session=None,
        client=client,
        context=AgentContext(
            user_id="eval",
            team_code="KIA",
            role="COACH",
        ),
    )]

    plan_input = client.responses.create.call_args_list[0].kwargs["input"]
    trusted_context = [
        item["content"] for item in plan_input
        if item.get("role") == "developer"
    ]
    assert len(trusted_context) == 1
    assert "KIA" in trusted_context[0]
    assert "다른 구단" in trusted_context[0]


@pytest.mark.asyncio
async def test_as_of_comparison_adds_date_boundary_to_final_context(monkeypatch):
    compare = FakeToolCall(
        "compare_pitchers",
        '{"first_pitcher_id":"p1","second_pitcher_id":"p2"}',
        "call_compare",
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=[
            response(compare),
            response(finalize_call()),
            final_stream("비교 결과"),
        ]))
    )
    monkeypatch.setattr(
        streaming, "execute_tool",
        AsyncMock(return_value={
            "ok": True,
            "data": {
                "as_of_date": "2026-06-30",
                "date_boundary": "game_date < as_of_date; same-day games excluded",
                "data_through_date": "2026-06-29",
            },
        }),
    )

    events = [event async for event in streaming.stream_agent(
        message="양현종과 정해영을 2026-06-30 기준으로 비교해줘.",
        session=None,
        client=client,
        context=AgentContext(
            user_id="eval",
            team_code="KIA",
            role="COACH",
            as_of_date=date(2026, 6, 30),
        ),
    )]

    first_tools = client.responses.create.call_args_list[0].kwargs["tools"]
    assert "get_bullpen_workload" not in {
        tool["name"] for tool in first_tools
    }
    final_input = client.responses.create.call_args_list[2].kwargs["input"]
    developer_notes = [
        item["content"] for item in final_input
        if item.get("role") == "developer"
    ]
    assert developer_notes
    assert "2026-06-30" in developer_notes[-1]
    assert "data_through_date" in developer_notes[-1]
    assert any(name == "completed" for name, _ in events)


@pytest.mark.asyncio
async def test_simulation_final_context_marks_scenario_as_hypothetical(monkeypatch):
    simulation = FakeToolCall(
        "simulate_pitching_decision",
        '{"inning":7,"outs":1,"pitch_count":85,"runner_on_first":true}',
        "call_simulation",
    )
    client = SimpleNamespace(
        responses=SimpleNamespace(create=AsyncMock(side_effect=[
            response(simulation),
            response(finalize_call()),
            final_stream("가상 입력 상황에 대한 결과입니다."),
        ]))
    )
    monkeypatch.setattr(
        streaming, "execute_tool",
        AsyncMock(return_value={"ok": True, "data": {"risk": "review"}}),
    )

    [event async for event in streaming.stream_agent(
        message="7회 1아웃, 85구, 1루 주자 상황을 시뮬레이션해줘.",
        session=None,
        client=client,
    )]

    final_input = client.responses.create.call_args_list[2].kwargs["input"]
    developer_notes = [
        item["content"] for item in final_input
        if item.get("role") == "developer"
    ]
    assert len(developer_notes) == 1
    assert "가상 상황" in developer_notes[0]
    assert "실제 경기" in developer_notes[0]


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
