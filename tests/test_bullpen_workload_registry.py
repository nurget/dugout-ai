
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