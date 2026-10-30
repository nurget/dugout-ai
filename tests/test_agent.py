import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.agent import service


class FakeOutput:
    def __init__(self, item_type, **kwargs):
        self.type = item_type

        for key, value in kwargs.items():
            setattr(self, key, value)

    def model_dump(self, exclude_none=True):
        data = vars(self).copy()
        data.pop("type", None)

        return {
            "type": self.type,
            **data,
        }


@pytest.mark.asyncio
async def test_agent_calls_tool_and_generates_answer(monkeypatch):
    # 첫 번째 응답은 Tool 호출, 두 번째 응답은 최종 답변으로 고정한다.
    tool_call = FakeOutput(
        "function_call",
        name="get_pitcher_status",
        arguments=json.dumps({"player_id": 1}),
        call_id="call_test_001",
    )

    first_response = SimpleNamespace(
        output=[tool_call],
        output_text="",
    )

    second_response = SimpleNamespace(
        output=[],
        output_text="샘플 선발 A의 정보를 확인했습니다.",
    )

    mock_client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                side_effect=[first_response, second_response]
            )
        )
    )

    mock_tool = AsyncMock(
        return_value={
            "ok": True,
            "data": {
                "player_id": 1,
                "name": "샘플 선발 A",
            },
        }
    )

    # 테스트에서는 PostgreSQL에 접근하지 않고 Tool 결과를 대체한다.
    monkeypatch.setattr(service, "execute_tool", mock_tool)

    result = await service.run_agent(
        message="선수 ID 1의 투수 정보를 알려줘.",
        session=None,
        client=mock_client,
    )

    assert result["rounds"] == 2
    assert len(result["tool_history"]) == 1
    assert result["tool_history"][0]["tool"] == "get_pitcher_status"
    assert "샘플 선발 A" in result["answer"]

    mock_tool.assert_awaited_once()

    # Tool 결과가 두 번째 모델 호출에 포함되었는지 확인한다.
    second_call = mock_client.responses.create.call_args_list[1]
    second_input = second_call.kwargs["input"]

    tool_results = [
        item for item in second_input
        if item.get("type") == "function_call_output"
    ]

    assert len(tool_results) == 1
    assert tool_results[0]["call_id"] == "call_test_001"
    assert json.loads(tool_results[0]["output"])["ok"] is True

@pytest.mark.asyncio
async def test_agent_rejects_invalid_tool_arguments(monkeypatch):
    invalid_call = FakeOutput(
        "function_call",
        name="get_pitcher_status",
        arguments="{잘못된 JSON",
        call_id="call_invalid",
    )

    mock_client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                side_effect=[
                    SimpleNamespace(
                        output=[invalid_call],
                        output_text="",
                    ),
                    SimpleNamespace(
                        output=[],
                        output_text="Tool 인자가 잘못되었습니다.",
                    ),
                ]
            )
        )
    )

    mock_tool = AsyncMock()
    monkeypatch.setattr(service, "execute_tool", mock_tool)

    result = await service.run_agent(
        message="투수 정보를 조회해줘.",
        session=None,
        client=mock_client,
    )

    assert result["tool_history"][0]["result"]["ok"] is False
    assert (
        result["tool_history"][0]["result"]["error"]["code"]
        == "INVALID_ARGUMENTS"
    )

    # JSON 파싱 자체가 실패했으므로 DB Tool은 실행하지 않는다.
    mock_tool.assert_not_awaited()


@pytest.mark.asyncio
async def test_agent_stops_after_max_rounds(monkeypatch):
    repeated_call = FakeOutput(
        "function_call",
        name="get_pitcher_status",
        arguments='{"player_id":1}',
        call_id="repeated_call",
    )

    mock_client = SimpleNamespace(
        responses=SimpleNamespace(
            create=AsyncMock(
                return_value=SimpleNamespace(
                    output=[repeated_call],
                    output_text="",
                )
            )
        )
    )

    monkeypatch.setattr(
        service,
        "execute_tool",
        AsyncMock(return_value={"ok": True, "data": {}}),
    )

    with pytest.raises(
        service.AgentExecutionError,
        match="최대 Tool 호출",
    ):
        await service.run_agent(
            message="계속 조회해줘.",
            session=None,
            client=mock_client,
        )

    assert (
        mock_client.responses.create.await_count
        == service.MAX_TOOL_ROUNDS
    )