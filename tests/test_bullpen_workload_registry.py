
from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.tools import registry


@pytest.mark.asyncio
async def test_requires_authenticated_context():
    result = await registry.execute_tool(
        session=None,
        tool_name="get_bullpen_workload",
        arguments={"as_of_date": "2026-03-30"},
        context=None,
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_rejects_invalid_date():
    result = await registry.execute_tool(
        session=None,
        tool_name="get_bullpen_workload",
        arguments={"as_of_date": "invalid-date"},
        context=SimpleNamespace(team_code="KT"),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENTS"


@pytest.mark.asyncio
async def test_injects_authenticated_team(monkeypatch):
    handler = AsyncMock(
        return_value={"team_code": "KT", "pitchers": []}
    )
    schema_class, _ = registry.TOOL_REGISTRY[
        "get_bullpen_workload"
    ]

    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "get_bullpen_workload",
        (schema_class, handler),
    )

    result = await registry.execute_tool(
        session=None,
        tool_name="get_bullpen_workload",
        arguments={"as_of_date": "2026-03-30"},
        context=SimpleNamespace(team_code="KT"),
    )

    assert result["ok"] is True

    handler.assert_awaited_once_with(
        None,
        as_of_date=date(2026, 3, 30),
        authenticated_team_code="KT",
    )


@pytest.mark.asyncio
async def test_injects_server_as_of_date_over_model_argument(monkeypatch):
    handler = AsyncMock(return_value={"team_code": "KT", "pitchers": []})
    schema_class, _ = registry.TOOL_REGISTRY["get_bullpen_workload"]
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "get_bullpen_workload",
        (schema_class, handler),
    )

    result = await registry.execute_tool(
        session=None,
        tool_name="get_bullpen_workload",
        arguments={"as_of_date": "2026-03-30"},
        context=SimpleNamespace(
            team_code="KT",
            as_of_date=date(2026, 4, 1),
        ),
    )

    assert result["ok"] is True
    assert handler.await_args.kwargs["as_of_date"] == date(2026, 4, 1)


@pytest.mark.asyncio
async def test_historical_pitcher_comparison_uses_server_as_of(monkeypatch):
    handler = AsyncMock(return_value={"comparison_status": "COMPARABLE"})
    schema_class, _ = registry.TOOL_REGISTRY["compare_pitchers"]
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        "compare_pitchers",
        (schema_class, handler),
    )
    result = await registry.execute_tool(
        session=None,
        tool_name="compare_pitchers",
        arguments={
            "season": 2026,
            "first_pitcher_id": "1",
            "second_pitcher_id": "2",
            "as_of_date": "2026-03-30",
        },
        context=SimpleNamespace(
            team_code="KT",
            as_of_date=date(2026, 3, 29),
        ),
    )

    assert result["ok"] is True
    assert handler.await_args.kwargs["as_of_date"] == date(2026, 3, 29)
    assert handler.await_args.kwargs["season"] == 2026


@pytest.mark.asyncio
async def test_rejects_model_supplied_team_code():
    result = await registry.execute_tool(
        session=None,
        tool_name="get_bullpen_workload",
        arguments={
            "as_of_date": "2026-03-30",
            "team_code": "HT",
        },
        context=SimpleNamespace(team_code="KT"),
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENTS"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "arguments", "team_argument"),
    [
        (
            "get_bullpen_options",
            {"exclude_player_id": None},
            "team",
        ),
        (
            "search_season_pitchers",
            {"season": 2026, "name": "김", "as_of_date": "2026-03-30"},
            "team",
        ),
        (
            "compare_pitchers",
            {
                "season": 2026,
                "first_pitcher_id": "1",
                "second_pitcher_id": "2",
                "as_of_date": "2026-03-30",
            },
            "team",
        ),
    ],
)
async def test_player_tools_use_authenticated_team(
    monkeypatch,
    tool_name,
    arguments,
    team_argument,
):
    handler = AsyncMock(return_value={})
    schema_class, _ = registry.TOOL_REGISTRY[tool_name]
    monkeypatch.setitem(
        registry.TOOL_REGISTRY,
        tool_name,
        (schema_class, handler),
    )

    result = await registry.execute_tool(
        session=None,
        tool_name=tool_name,
        arguments=arguments,
        context=SimpleNamespace(team_code="KIA"),
    )

    assert result["ok"] is True
    called_kwargs = handler.await_args.kwargs
    assert called_kwargs[team_argument] == "KIA"
