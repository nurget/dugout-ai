from app.agent.metrics import AgentMetrics


def test_multiple_llm_calls_are_aggregated():
    metrics = AgentMetrics()

    metrics.record_llm_call(
        input_tokens=150,
        output_tokens=40,
    )
    metrics.record_llm_call(
        input_tokens=230,
        output_tokens=70,
    )

    result = metrics.snapshot()

    assert result["llm_calls"] == 2
    assert result["input_tokens"] == 380
    assert result["output_tokens"] == 110


def test_tool_execution_metrics():
    metrics = AgentMetrics()

    metrics.record_tool(
        name="get_game_state",
        duration_ms=12.345,
        success=True,
    )
    metrics.record_tool(
        name="simulate_pitching_decision",
        duration_ms=1.876,
        success=False,
    )

    result = metrics.snapshot()

    assert result["tool_count"] == 2
    assert result["tools"][0] == {
        "name": "get_game_state",
        "duration_ms": 12.35,
        "success": True,
    }
    assert result["tools"][1]["success"] is False


def test_missing_usage_is_not_reported_as_zero():
    metrics = AgentMetrics()

    metrics.record_llm_call(
        input_tokens=None,
        output_tokens=None,
    )

    result = metrics.snapshot()

    assert result["llm_calls"] == 1
    assert result["input_tokens"] is None
    assert result["output_tokens"] is None


def test_each_run_has_unique_id():
    first = AgentMetrics()
    second = AgentMetrics()

    assert first.run_id != second.run_id