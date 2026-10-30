import pytest
from pydantic import ValidationError

from app.simulation.pitching import (
    PitchingScenario,
    evaluate_pitching_decision,
)
from app.tools.registry import execute_tool


def test_pitch_count_95_in_late_inning():
    scenario = PitchingScenario(
        inning=7,
        outs=1,
        pitch_count=95,
        runner_on_first=False,
    )

    result = evaluate_pitching_decision(scenario)

    assert result["workload_level"] == "caution"
    assert result["replacement_review"] is True
    assert result["recommendation"] == "교체 후보 검토"
    assert result["method"]["type"] == "rule_based"


def test_low_pitch_count():
    scenario = PitchingScenario(
        inning=4,
        outs=0,
        pitch_count=52,
        runner_on_first=False,
    )

    result = evaluate_pitching_decision(scenario)

    assert result["workload_level"] == "low"
    assert result["replacement_review"] is False


@pytest.mark.parametrize(
    "pitch_count, expected",
    [
        (84, "low"),
        (85, "caution"),
        (99, "caution"),
        (100, "high"),
    ],
)
def test_workload_boundaries(pitch_count, expected):
    result = evaluate_pitching_decision(
        PitchingScenario(
            inning=7,
            outs=1,
            pitch_count=pitch_count,
            runner_on_first=False,
        )
    )

    assert result["workload_level"] == expected


def test_invalid_outs():
    with pytest.raises(ValidationError):
        PitchingScenario(
            inning=7,
            outs=3,
            pitch_count=95,
            runner_on_first=False,
        )


@pytest.mark.asyncio
async def test_simulation_tool_registry():
    result = await execute_tool(
        session=None,
        tool_name="simulate_pitching_decision",
        arguments={
            "inning": 7,
            "outs": 1,
            "pitch_count": 95,
            "runner_on_first": False,
        },
    )

    assert result["ok"] is True
    assert result["data"]["workload_level"] == "caution"


@pytest.mark.asyncio
async def test_simulation_tool_rejects_invalid_input():
    result = await execute_tool(
        session=None,
        tool_name="simulate_pitching_decision",
        arguments={
            "inning": 7,
            "outs": 5,
            "pitch_count": 95,
            "runner_on_first": False,
        },
    )

    assert result["ok"] is False
    assert result["error"]["code"] == "INVALID_ARGUMENTS"