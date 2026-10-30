from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent import streaming
from app.utils.sse import format_sse


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
    class FakeToolCall:
        type = "function_call"
        name = "get_pitcher_status"
        arguments = '{"player_id":1}'
        call_id = "call_001"

        def model_dump(self, exclude_none=True):
            return {
                "type": self.type,
                "name": self.name,
                "arguments": self.arguments,
                "call_id": self.call_id,
            }

    tool_call = FakeToolCall()

    first_response = SimpleNamespace(
        output=[tool_call],
    )

    second_response = SimpleNamespace(
        output=[
            SimpleNamespace(
                type="message",
                model_dump=lambda exclude_none=True: {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": "분석 완료"}
                    ],
                },
            )
        ],
    )

    async def fake_stream(events):
        for event in events:
            yield event

    first_events = fake_stream([
        SimpleNamespace(
            type="response.completed",
            response=first_response,
        ),
    ])

    second_events = fake_stream([
        SimpleNamespace(
            type="response.output_text.delta",
            delta="분석",
        ),
        SimpleNamespace(
            type="response.output_text.delta",
            delta=" 완료",
        ),
        SimpleNamespace(
            type="response.completed",
            response=second_response,
        ),
    ])

    mock_client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                side_effect=[first_events, second_events]
            )
        )
    )

    mock_tool = AsyncMock(
        return_value={
            "ok": True,
            "data": {"name": "샘플 선발 A"},
        }
    )

    monkeypatch.setattr(
        streaming,
        "execute_tool",
        mock_tool,
    )

    events = []

    async for event in streaming.stream_agent(
        message="선수 ID 1을 확인해줘.",
        session=None,
        client=mock_client,
    ):
        events.append(event)

    event_names = [name for name, _ in events]

    assert event_names == [
        "started",
        "tool_start",
        "tool_result",
        "answer_delta",
        "answer_delta",
        "completed",
    ]

    answer = "".join(
        data["delta"]
        for name, data in events
        if name == "answer_delta"
    )

    assert answer == "분석 완료"
    mock_tool.assert_awaited_once()

    second_call = mock_client.responses.create.call_args_list[1]
    second_input = second_call.kwargs["input"]

    # 두 번째 LLM 호출에는 첫 Tool의 실행 결과가 포함돼야 한다.
    assert any(
        item.get("type") == "function_call_output"
        and item.get("call_id") == "call_001"
        for item in second_input
    )