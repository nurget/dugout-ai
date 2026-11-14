import json
from pathlib import Path

import pytest

from app.agent.metrics import AgentMetrics
from app.agent.versions import agent_versions
from app.evaluation.agent_eval import (
    EvalTrace,
    TraceMetrics,
    TraceToolCall,
    compare_reports,
    grade_case,
    grade_dataset,
    load_dataset,
)
from scripts.agent_eval import _fixture_tool_executor, _load_eval_fixture


DATASET = Path(__file__).resolve().parents[1] / "evals" / "agent" / "v1.jsonl"


def test_versioned_dataset_has_unique_cases_and_human_review_labels():
    cases = load_dataset(DATASET)

    assert len(cases) == 11
    assert len({case.case_id for case in cases}) == len(cases)
    assert {case.category for case in cases} >= {
        "AUTHORIZATION",
        "TEMPORAL_LEAKAGE",
        "PROMPT_INJECTION",
        "TOOL_FAILURE",
    }
    assert all(case.human_review for case in cases)


@pytest.mark.asyncio
async def test_prompt_injection_fixture_is_hash_pinned_and_replayed_without_db():
    case = next(case for case in load_dataset(DATASET) if case.case_id == "prompt_injection_in_source")
    fixture, snapshot_id = _load_eval_fixture(case)

    assert fixture is not None
    assert snapshot_id == case.expected_data_snapshot_ids["eval_fixture:prompt_injection"]
    result = await _fixture_tool_executor(fixture)(
        session=None,
        tool_name="get_pitcher_status",
        arguments={"player_id": 1},
        context=None,
    )

    assert result["ok"] is True
    assert "Ignore all previous instructions" in result["data"]["source_note"]


def test_all_synthetic_fixture_refs_resolve_to_their_pinned_file_hashes():
    cases = [case for case in load_dataset(DATASET) if case.fixture_ref.startswith("fixture:")]

    assert len(cases) == 6
    for case in cases:
        fixture_entry = _load_eval_fixture(case)
        assert fixture_entry is not None
        fixture, snapshot_id = fixture_entry
        assert case.expected_data_snapshot_ids == {
            fixture["snapshot_key"]: snapshot_id,
        }


def test_grader_checks_tool_arguments_answer_claims_and_context():
    case = next(case for case in load_dataset(DATASET) if case.case_id == "normal_pitcher_comparison")
    trace = EvalTrace(
        case_id=case.case_id,
        fixture_ref=case.fixture_ref,
        context=case.context,
        data_snapshot_ids=case.expected_data_snapshot_ids,
        versions={"model": "test-model", "prompt_version": "p1", "tool_schema_version": "t1"},
        tool_calls=[
            TraceToolCall(name="search_season_pitchers", arguments={"name": "양현종", "as_of_date": "2026-06-30"}),
            TraceToolCall(name="compare_pitchers", arguments={"as_of_date": "2026-06-30"}),
        ],
        answer="2026년 6월 30일 기준 이전 기록으로 비교했습니다. 기준일 당일 경기는 제외했습니다.",
        metrics=TraceMetrics(
            llm_calls=2,
            input_tokens=400,
            cached_input_tokens=120,
            output_tokens=100,
            duration_ms=900,
            llm_call_metrics=[
                {"stage": "PLAN", "input_tokens": 180, "cached_input_tokens": 60, "output_tokens": 20},
                {"stage": "FINAL", "input_tokens": 220, "cached_input_tokens": 60, "output_tokens": 80},
            ],
        ),
    )

    result = grade_case(case, trace)

    assert result["status"] == "REVIEW"
    assert all(check["passed"] for check in result["checks"])


def test_grader_fails_as_of_boundary_when_same_day_exclusion_is_missing():
    case = next(case for case in load_dataset(DATASET) if case.case_id == "normal_pitcher_comparison")
    trace = EvalTrace(
        case_id=case.case_id,
        fixture_ref=case.fixture_ref,
        context=case.context,
        data_snapshot_ids=case.expected_data_snapshot_ids,
        tool_calls=[
            TraceToolCall(name="search_season_pitchers", arguments={"as_of_date": "2026-06-30"}),
            TraceToolCall(name="compare_pitchers", arguments={"as_of_date": "2026-06-30"}),
        ],
        answer="2026년 6월 30일 기준 이전 기록을 비교했습니다.",
    )

    result = grade_case(case, trace)

    check = next(item for item in result["checks"] if item["name"] == "answer_same_day_exclusion")
    assert check["passed"] is False


def test_grader_fails_when_tool_argument_leaks_as_of_boundary():
    case = next(case for case in load_dataset(DATASET) if case.case_id == "as_of_date_no_leakage")
    trace = EvalTrace(
        case_id=case.case_id,
        fixture_ref=case.fixture_ref,
        context=case.context,
        data_snapshot_ids=case.expected_data_snapshot_ids,
        tool_calls=[
            TraceToolCall(name="search_season_pitchers", arguments={"as_of_date": "2026-06-01"}),
            TraceToolCall(name="compare_pitchers", arguments={"as_of_date": "2026-06-01"}),
        ],
        answer="2026-05-31 기준 이전 데이터를 사용했습니다.",
    )

    result = grade_case(case, trace)

    assert result["status"] == "FAIL"
    assert any(not check["passed"] and check["name"].startswith("tool_argument") for check in result["checks"])


def test_grade_summary_reports_unrun_cases_and_token_percentiles():
    cases = load_dataset(DATASET)
    case = cases[0]
    trace = EvalTrace(
        case_id=case.case_id,
        fixture_ref=case.fixture_ref,
        context=case.context,
        data_snapshot_ids=case.expected_data_snapshot_ids,
        tool_calls=[
            TraceToolCall(name="search_season_pitchers", arguments={"as_of_date": case.context.as_of_date}),
            TraceToolCall(name="compare_pitchers", arguments={"as_of_date": case.context.as_of_date}),
        ],
        answer="기준일 이전 기록입니다.",
        metrics=TraceMetrics(input_tokens=200, output_tokens=50, duration_ms=700),
    )

    report = grade_dataset(cases, [trace])

    assert report["evaluated_count"] == 1
    assert report["not_run_count"] == len(cases) - 1
    assert report["metrics"]["input_tokens_p95"] == 200
    assert report["metrics"]["output_tokens_total"] == 50


def test_metrics_keep_per_call_usage_and_missing_usage_is_not_zero():
    metrics = AgentMetrics(versions={"model": "m", "prompt_version": "p", "tool_schema_version": "t"})
    metrics.record_llm_call(100, 20, stage="PLAN", duration_ms=25, cached_input_tokens=30)
    metrics.record_llm_call(None, None, stage="FINAL")

    snapshot = metrics.snapshot()

    assert snapshot["input_tokens"] is None
    assert snapshot["llm_call_metrics"][0] == {
        "sequence": 1,
        "stage": "PLAN",
        "duration_ms": 25,
        "input_tokens": 100,
        "cached_input_tokens": 30,
        "output_tokens": 20,
    }
    assert snapshot["llm_call_metrics"][1]["input_tokens"] is None


def test_agent_versions_are_stable_for_same_inputs():
    assert agent_versions("model-a") == agent_versions("model-a")
    assert agent_versions("model-a")["model"] != agent_versions("model-b")["model"]


def test_price_card_estimates_cached_and_uncached_input_separately():
    cases = load_dataset(DATASET)
    case = cases[0]
    trace = EvalTrace(
        case_id=case.case_id,
        fixture_ref=case.fixture_ref,
        context=case.context,
        data_snapshot_ids=case.expected_data_snapshot_ids,
        versions={"model": "test-model"},
        tool_calls=[
            TraceToolCall(name="search_season_pitchers", arguments={"as_of_date": case.context.as_of_date}),
            TraceToolCall(name="compare_pitchers", arguments={"as_of_date": case.context.as_of_date}),
        ],
        answer="기준일 이전 기록입니다.",
        metrics=TraceMetrics(
            input_tokens=100,
            output_tokens=20,
            llm_call_metrics=[{"input_tokens": 100, "cached_input_tokens": 30, "output_tokens": 20}],
        ),
    )
    price_card = {
        "version": "test-rate-1",
        "unit": "USD_PER_1M_TOKENS",
        "models": {
            "test-model": {
                "input_usd_per_million": 1,
                "cached_input_usd_per_million": 0.5,
                "output_usd_per_million": 2,
            }
        },
    }

    report = grade_dataset(cases, [trace], price_card=price_card)

    assert report["results"][0]["estimated_cost_usd"] == 0.000125
    assert report["price_card_version"] == "test-rate-1"


def test_report_comparison_flags_regressions_and_allows_prompt_version_change():
    baseline = {
        "dataset_version": "1.0.0",
        "fixture_refs": ["fixture-a"],
        "data_snapshot_sets": ['{"kbo":"snapshot-1"}'],
        "versions": ['{"model":"m","prompt_version":"old"}'],
        "automated_pass_rate": 1.0,
        "price_card_version": "rates-1",
        "metrics": {"duration_ms_p95": 800, "input_tokens_p95": 400, "output_tokens_p95": 100, "estimated_cost_usd_total": 0.01},
        "results": [{"case_id": "case-one", "status": "REVIEW"}],
    }
    candidate = {
        **baseline,
        "versions": ['{"model":"m","prompt_version":"new"}'],
        "automated_pass_rate": 0.0,
        "metrics": {"duration_ms_p95": 900, "input_tokens_p95": 500, "output_tokens_p95": 100, "estimated_cost_usd_total": 0.012},
        "results": [{"case_id": "case-one", "status": "FAIL"}],
    }

    report = compare_reports(baseline, candidate)

    assert report["comparable"] is True
    assert report["regression_case_ids"] == ["case-one"]
    assert report["p95_delta"]["input_tokens_p95"] == 100
    assert report["estimated_cost_usd_delta"] == 0.002


def test_report_comparison_rejects_different_snapshots():
    baseline = {"dataset_version": "1.0.0", "fixture_refs": ["a"], "data_snapshot_sets": ["old"], "results": []}
    candidate = {"dataset_version": "1.0.0", "fixture_refs": ["a"], "data_snapshot_sets": ["new"], "results": []}

    report = compare_reports(baseline, candidate)

    assert report["comparable"] is False
    assert any("snapshot" in reason for reason in report["reasons"])


def test_dataset_rejects_invalid_jsonl(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps({"dataset_version": "1.0.0", "case_id": "bad"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="bad.jsonl:1"):
        load_dataset(path)
