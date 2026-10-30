import pytest
from pydantic import ValidationError

from app.sabermetrics.run_expectancy import (
    BaseOutState,
    RE24Input,
    calculate_re24,
    get_run_expectancy,
)
from app.tools.registry import execute_tool


def test_run_expectancy_for_runner_on_first():
    state = BaseOutState(outs=1, bases="100")

    assert get_run_expectancy(state) == 0.489


def test_double_play_re24():
    result = calculate_re24(
        RE24Input(
            before=BaseOutState(
                outs=1,
                bases="100",
            ),
            after=BaseOutState(
                outs=3,
                bases="000",
            ),
            runs_scored=0,
        )
    )

    assert result["before_re"] == 0.489
    assert result["after_re"] == 0.0
    assert result["re24"] == -0.489


def test_run_scored_changes_re24():
    result = calculate_re24(
        RE24Input(
            before=BaseOutState(
                outs=1,
                bases="001",
            ),
            after=BaseOutState(
                outs=1,
                bases="100",
            ),
            runs_scored=1,
        )
    )

    assert result["re24"] == 0.624


def test_invalid_base_state():
    with pytest.raises(ValidationError):
        BaseOutState(outs=1, bases="999")


def test_cannot_start_with_three_outs():
    with pytest.raises(ValueError):
        calculate_re24(
            RE24Input(
                before=BaseOutState(outs=3, bases="000"),
                after=BaseOutState(outs=3, bases="000"),
                runs_scored=0,
            )
        )


@pytest.mark.asyncio
async def test_re24_tool_through_registry():
    result = await execute_tool(
        session=None,
        tool_name="calculate_re24",
        arguments={
            "before": {"outs": 1, "bases": "100"},
            "after": {"outs": 3, "bases": "000"},
            "runs_scored": 0,
        },
    )

    assert result["ok"] is True
    assert result["data"]["re24"] == -0.489