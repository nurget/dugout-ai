import pytest
from unittest.mock import AsyncMock

from app.tools.registry import execute_tool


@pytest.mark.asyncio
async def test_unknown_tool():
    result = await execute_tool(
        session=None,
        tool_name="delete_all_players",
        arguments={},
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "UNKNOWN_TOOL"


@pytest.mark.asyncio
async def test_invalid_arguments():
    result = await execute_tool(
        session=None,
        tool_name="get_pitcher_status",
        arguments={"player_id": -1},
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENTS"


@pytest.mark.asyncio
async def test_pitcher_tool_success(monkeypatch):
    mock_handler = AsyncMock(
        return_value={
            "player_id": 1,
            "name": "샘플 선발 A",
        }
    )

    monkeypatch.setitem(
        __import__(
            "app.tools.registry",
            fromlist=["TOOL_REGISTRY"],
        ).TOOL_REGISTRY,
        "get_pitcher_status",
        (
            __import__(
                "app.tools.schemas",
                fromlist=["PitcherStatusInput"],
            ).PitcherStatusInput,
            mock_handler,
        ),
    )

    result = await execute_tool(
        session=None,
        tool_name="get_pitcher_status",
        arguments={"player_id": 1},
    )

    assert result["ok"] is True
    assert result["data"]["player_id"] == 1
    mock_handler.assert_awaited_once()