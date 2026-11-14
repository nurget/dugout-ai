"""Validate versioned Agent cases and grade privacy-safe execution traces."""

import json
import hashlib
import math
import re
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import inspect as sqlalchemy_inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_import_batch import DataImportBatch
from app.models.kbo import KboGame, KboTeam
from app.models.kbo_official_season_pitcher import KboOfficialSeasonPitcher
from app.models.kbo_pitcher_appearance import KboPitcherAppearance
from app.models.kbo_pitching import KboPitchingAppearance
from app.models.kbo_plate_appearance import KboPlateAppearance
from app.models.kbo_season_pitcher import KboSeasonPitcher
from app.models.player import Player


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ArgumentConstraint(StrictModel):
    tool: str
    path: str
    equals_context: str | None = None
    equals_literal: Any = None

    @model_validator(mode="after")
    def require_one_expected_value(self):
        if (self.equals_context is None) == (self.equals_literal is None):
            raise ValueError("정확히 하나의 equals_context/equals_literal 값이 필요합니다.")
        return self


class ToolExpectations(StrictModel):
    required_tools: list[str] = Field(default_factory=list)
    required_order: list[str] = Field(default_factory=list)
    forbidden_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] | None = None
    argument_constraints: list[ArgumentConstraint] = Field(default_factory=list)


class AnswerExpectations(StrictModel):
    required_contains: list[str] = Field(default_factory=list)
    forbidden_contains: list[str] = Field(default_factory=list)
    uncertainty_groups: list[list[str]] = Field(default_factory=list)
    require_as_of_boundary: bool = False


class EvalContext(StrictModel):
    team_code: str | None = None
    role: str | None = None
    as_of_date: str | None = None


class EvalCase(StrictModel):
    dataset_version: str = Field(min_length=1, max_length=32)
    case_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$")
    category: str = Field(min_length=1, max_length=80)
    severity: str = Field(pattern=r"^(LOW|MEDIUM|HIGH|CRITICAL)$")
    title: str = Field(min_length=1, max_length=160)
    user_message: str = Field(min_length=1, max_length=2000)
    context: EvalContext
    fixture_ref: str = Field(min_length=1, max_length=120)
    expected_data_snapshot_ids: dict[str, str] = Field(default_factory=dict)
    tool_expectations: ToolExpectations
    answer_expectations: AnswerExpectations
    human_review: list[str] = Field(default_factory=list)


class TraceToolCall(StrictModel):
    name: str = Field(min_length=1, max_length=100)
    arguments: dict[str, Any] = Field(default_factory=dict)
    success: bool | None = None


class TraceMetrics(StrictModel):
    llm_calls: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    duration_ms: float | None = Field(default=None, ge=0)
    llm_call_metrics: list[dict[str, Any]] = Field(default_factory=list)


class EvalTrace(StrictModel):
    case_id: str
    fixture_ref: str
    run_status: str = "COMPLETED"
    context: EvalContext
    data_snapshot_ids: dict[str, str | None] = Field(default_factory=dict)
    versions: dict[str, str] = Field(default_factory=dict)
    tool_calls: list[TraceToolCall] = Field(default_factory=list)
    answer: str = ""
    metrics: TraceMetrics = Field(default_factory=TraceMetrics)


FIXTURE_MODELS = (
    DataImportBatch,
    KboGame,
    KboOfficialSeasonPitcher,
    KboPitcherAppearance,
    KboPitchingAppearance,
    KboPlateAppearance,
    KboSeasonPitcher,
    KboTeam,
    Player,
)


def _stable_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _stable_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    if isinstance(value, bytes):
        return value.hex()
    return value


async def database_fixture_snapshot_id(session: AsyncSession) -> str:
    """Hash all baseball source tables used by Agent Tools, without exporting rows."""
    digest = hashlib.sha256()
    for model in FIXTURE_MODELS:
        digest.update(model.__tablename__.encode("utf-8"))
        digest.update(b"\0")
        exists = await session.run_sync(
            lambda sync_session, table=model.__tablename__: sqlalchemy_inspect(sync_session.connection()).has_table(table)
        )
        if not exists:
            digest.update(b"MISSING\n")
            continue
        primary_key = tuple(model.__table__.primary_key.columns)
        rows = (await session.scalars(select(model).order_by(*primary_key))).all()
        for row in rows:
            record = {
                column.name: _stable_value(getattr(row, column.name))
                for column in model.__table__.columns
            }
            digest.update(json.dumps(
                record,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8"))
            digest.update(b"\n")
    return f"sha256:{digest.hexdigest()}"


def _read_jsonl(path: Path, model: type[BaseModel]) -> list[BaseModel]:
    rows = []
    with path.open(encoding="utf-8") as source:
        for line_number, raw in enumerate(source, 1):
            if not raw.strip() or raw.lstrip().startswith("#"):
                continue
            try:
                rows.append(model.model_validate_json(raw))
            except Exception as error:
                raise ValueError(f"{path}:{line_number}: {error}") from error
    return rows


def load_dataset(path: str | Path) -> list[EvalCase]:
    cases = _read_jsonl(Path(path), EvalCase)
    typed_cases = [case for case in cases if isinstance(case, EvalCase)]
    ids = [case.case_id for case in typed_cases]
    if not typed_cases:
        raise ValueError(f"평가 데이터가 비어 있습니다: {path}")
    if len(ids) != len(set(ids)):
        raise ValueError("평가 데이터에 중복 case_id가 있습니다.")
    versions = {case.dataset_version for case in typed_cases}
    if len(versions) != 1:
        raise ValueError("하나의 JSONL 파일에는 dataset_version 하나만 사용할 수 있습니다.")
    return typed_cases


def load_traces(path: str | Path) -> list[EvalTrace]:
    traces = _read_jsonl(Path(path), EvalTrace)
    typed_traces = [trace for trace in traces if isinstance(trace, EvalTrace)]
    ids = [trace.case_id for trace in typed_traces]
    if len(ids) != len(set(ids)):
        raise ValueError("trace 파일에 중복 case_id가 있습니다.")
    return typed_traces


def load_price_card(path: str | Path) -> dict[str, Any]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"가격표를 읽을 수 없습니다: {error}") from error
    if (
        not isinstance(payload, dict)
        or not payload.get("version")
        or payload.get("unit") != "USD_PER_1M_TOKENS"
        or not isinstance(payload.get("models"), dict)
    ):
        raise ValueError("가격표에는 version, unit=USD_PER_1M_TOKENS, models 객체가 필요합니다.")
    for model, rates in payload["models"].items():
        required = ("input_usd_per_million", "output_usd_per_million")
        if not isinstance(rates, dict) or any(key not in rates for key in required):
            raise ValueError(f"{model}: 입력/출력 token 단가가 필요합니다.")
        for key, value in rates.items():
            if key not in (*required, "cached_input_usd_per_million"):
                raise ValueError(f"{model}: 알 수 없는 단가 필드 {key}")
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{model}.{key}: 0 이상의 숫자여야 합니다.")
    return payload


def _normalized(value: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()


def _argument_at_path(arguments: dict[str, Any], path: str) -> Any:
    current: Any = arguments
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _subsequence(expected: list[str], actual: list[str]) -> bool:
    position = 0
    for item in actual:
        if position < len(expected) and item == expected[position]:
            position += 1
    return position == len(expected)


def grade_case(case: EvalCase, trace: EvalTrace) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    add("fixture_ref", trace.fixture_ref == case.fixture_ref,
        "평가 케이스와 동일한 fixture 사용" if trace.fixture_ref == case.fixture_ref
        else f"기대 {case.fixture_ref}, 실제 {trace.fixture_ref}")
    snapshot_mismatches = {
        dataset: {"expected": expected, "actual": trace.data_snapshot_ids.get(dataset)}
        for dataset, expected in case.expected_data_snapshot_ids.items()
        if trace.data_snapshot_ids.get(dataset) != expected
    }
    if case.expected_data_snapshot_ids:
        add("data_snapshot_ids", not snapshot_mismatches,
            "고정한 데이터 snapshot 일치" if not snapshot_mismatches
            else f"snapshot 불일치: {snapshot_mismatches}")
    add("run_status", trace.run_status == "COMPLETED",
        "Agent 실행 완료" if trace.run_status == "COMPLETED" else f"실행 상태: {trace.run_status}")
    for field_name in ("team_code", "role", "as_of_date"):
        expected_value = getattr(case.context, field_name)
        if expected_value is not None:
            actual_value = getattr(trace.context, field_name)
            add(f"context_{field_name}", actual_value == expected_value,
                f"인증/기준 context의 {field_name} 확인" if actual_value == expected_value
                else f"{field_name}: 기대 {expected_value!r}, 실제 {actual_value!r}")

    names = [call.name for call in trace.tool_calls]
    expectations = case.tool_expectations
    missing = [name for name in expectations.required_tools if name not in names]
    add("required_tools", not missing, "필수 Tool 호출 확인" if not missing else f"누락: {', '.join(missing)}")
    forbidden = [name for name in expectations.forbidden_tools if name in names]
    add("forbidden_tools", not forbidden, "금지 Tool 호출 없음" if not forbidden else f"호출됨: {', '.join(forbidden)}")
    if expectations.required_order:
        ordered = _subsequence(expectations.required_order, names)
        add("tool_order", ordered, "필수 호출 순서 확인" if ordered else f"필요 순서: {' → '.join(expectations.required_order)}")
    if expectations.allowed_tools is not None:
        unexpected = [name for name in names if name not in expectations.allowed_tools]
        add("allowed_tools", not unexpected, "허용 목록 안의 Tool만 호출" if not unexpected else f"예상 밖 호출: {', '.join(unexpected)}")

    for index, constraint in enumerate(expectations.argument_constraints, 1):
        matching = [call for call in trace.tool_calls if call.name == constraint.tool]
        if constraint.equals_context is not None:
            expected_value = getattr(case.context, constraint.equals_context, None)
        else:
            expected_value = constraint.equals_literal
        actual_values = [_argument_at_path(call.arguments, constraint.path) for call in matching]
        passed = bool(matching) and all(value == expected_value for value in actual_values)
        add(f"tool_argument_{index}", passed,
            f"{constraint.tool}.{constraint.path}가 기준값과 일치" if passed
            else f"{constraint.tool}.{constraint.path}: 기대 {expected_value!r}, 실제 {actual_values!r}")

    answer = _normalized(trace.answer)
    for index, phrase in enumerate(case.answer_expectations.required_contains, 1):
        found = _normalized(phrase) in answer
        add(f"required_answer_{index}", found,
            f"필수 표현 확인: {phrase}" if found else f"필수 표현 누락: {phrase}")
    for index, phrase in enumerate(case.answer_expectations.forbidden_contains, 1):
        found = _normalized(phrase) in answer
        add(f"forbidden_answer_{index}", not found,
            f"금지 표현 없음: {phrase}" if not found else f"금지 표현 포함: {phrase}")
    for index, group in enumerate(case.answer_expectations.uncertainty_groups, 1):
        found = [phrase for phrase in group if _normalized(phrase) in answer]
        add(f"uncertainty_{index}", bool(found),
            f"불확실성 표현 확인: {', '.join(found)}" if found
            else f"필요한 불확실성 표현 중 하나가 필요: {' / '.join(group)}")

    if case.answer_expectations.require_as_of_boundary:
        as_of_date = case.context.as_of_date
        date_found = False
        if as_of_date:
            year, month, day = as_of_date.split("-")
            date_variants = (
                as_of_date,
                f"{year}년 {int(month)}월 {int(day)}일",
                f"{int(month)}월 {int(day)}일",
            )
            date_found = any(_normalized(value) in answer for value in date_variants)
        add("answer_as_of_date", date_found,
            "답변에 분석 기준일 표시" if date_found
            else f"답변에 분석 기준일({as_of_date})이 없음")

        same_day_exclusion = bool(re.search(
            r"(?:당일|그날|해당일).{0,24}(?:제외|빼|반영하지|포함하지)|"
            r"(?:제외|빼|반영하지|포함하지).{0,24}(?:당일|그날|해당일)",
            answer,
        ))
        add("answer_same_day_exclusion", same_day_exclusion,
            "기준일 당일 경기 제외를 답변에서 설명" if same_day_exclusion
            else "기준일 당일 경기 제외 설명이 없음")

    return {
        "case_id": case.case_id,
        "category": case.category,
        "severity": case.severity,
        "status": (
            "FAIL" if not all(item["passed"] for item in checks)
            else "REVIEW" if case.human_review
            else "PASS"
        ),
        "human_review": case.human_review,
        "checks": checks,
        "versions": trace.versions,
        "metrics": trace.metrics.model_dump(),
    }


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * quantile) - 1))
    return round(ordered[index], 2)


def _estimate_trace_cost(trace: EvalTrace, price_card: dict[str, Any] | None) -> float | None:
    if price_card is None:
        return None
    model_name = trace.versions.get("model")
    rates = price_card.get("models", {}).get(model_name)
    calls = trace.metrics.llm_call_metrics
    if not rates or not calls:
        return None
    total = 0.0
    for call in calls:
        input_tokens = call.get("input_tokens")
        output_tokens = call.get("output_tokens")
        cached_tokens = call.get("cached_input_tokens")
        if input_tokens is None or output_tokens is None:
            return None
        cached_rate = rates.get("cached_input_usd_per_million")
        if cached_rate is not None and cached_tokens is None:
            return None
        cached = int(cached_tokens or 0)
        if cached < 0 or cached > input_tokens:
            return None
        noncached = input_tokens - cached
        total += (
            noncached * rates["input_usd_per_million"]
            + cached * (cached_rate if cached_rate is not None else rates["input_usd_per_million"])
            + output_tokens * rates["output_usd_per_million"]
        ) / 1_000_000
    return round(total, 10)


def grade_dataset(
    cases: list[EvalCase],
    traces: list[EvalTrace],
    price_card: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cases_by_id = {case.case_id: case for case in cases}
    traces_by_id = {trace.case_id: trace for trace in traces}
    unknown = sorted(set(traces_by_id) - set(cases_by_id))
    if unknown:
        raise ValueError(f"데이터셋에 없는 case_id trace: {', '.join(unknown)}")
    results = [grade_case(cases_by_id[case_id], trace) for case_id, trace in traces_by_id.items()]
    costs = {
        trace.case_id: _estimate_trace_cost(trace, price_card)
        for trace in traces if trace.case_id in cases_by_id
    }
    for result in results:
        result["estimated_cost_usd"] = costs.get(result["case_id"])
    summaries = [trace.metrics for trace in traces if trace.case_id in cases_by_id]
    latency = [float(item.duration_ms) for item in summaries if item.duration_ms is not None]
    input_tokens = [float(item.input_tokens) for item in summaries if item.input_tokens is not None]
    output_tokens = [float(item.output_tokens) for item in summaries if item.output_tokens is not None]
    total_cases = len(cases)
    passed = sum(result["status"] == "PASS" for result in results)
    failed = sum(result["status"] == "FAIL" for result in results)
    review = sum(result["status"] == "REVIEW" for result in results)
    llm_calls = [call for trace in traces for call in trace.metrics.llm_call_metrics]
    call_inputs = [float(call["input_tokens"]) for call in llm_calls if call.get("input_tokens") is not None]
    call_outputs = [float(call["output_tokens"]) for call in llm_calls if call.get("output_tokens") is not None]
    call_cached = [float(call["cached_input_tokens"]) for call in llm_calls if call.get("cached_input_tokens") is not None]
    known_costs = [cost for cost in costs.values() if cost is not None]
    return {
        "dataset_version": cases[0].dataset_version if cases else None,
        "fixture_refs": sorted({case.fixture_ref for case in cases}),
        "case_count": total_cases,
        "evaluated_count": len(results),
        "not_run_count": total_cases - len(results),
        "passed_count": passed,
        "failed_count": failed,
        "human_review_count": review,
        "automated_pass_rate": round((passed + review) / len(results), 4) if results else None,
        "severity_failures": {
            severity: sum(result["severity"] == severity and result["status"] == "FAIL" for result in results)
            for severity in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        },
        "metrics": {
            "duration_ms_p50": _percentile(latency, 0.50),
            "duration_ms_p95": _percentile(latency, 0.95),
            "input_tokens_p50": _percentile(input_tokens, 0.50),
            "input_tokens_p95": _percentile(input_tokens, 0.95),
            "output_tokens_p50": _percentile(output_tokens, 0.50),
            "output_tokens_p95": _percentile(output_tokens, 0.95),
            "input_tokens_total": sum(input_tokens) if input_tokens else None,
            "output_tokens_total": sum(output_tokens) if output_tokens else None,
            "llm_call_count": len(llm_calls),
            "llm_call_input_tokens_p50": _percentile(call_inputs, 0.50),
            "llm_call_input_tokens_p95": _percentile(call_inputs, 0.95),
            "llm_call_output_tokens_p50": _percentile(call_outputs, 0.50),
            "llm_call_output_tokens_p95": _percentile(call_outputs, 0.95),
            "cached_input_tokens_total": sum(call_cached) if call_cached else None,
            "estimated_cost_usd_total": round(sum(known_costs), 10) if known_costs else None,
            "estimated_cost_usd_p50": _percentile(known_costs, 0.50),
            "estimated_cost_usd_p95": _percentile(known_costs, 0.95),
            "estimated_cost_coverage_count": len(known_costs),
        },
        "price_card_version": price_card.get("version") if price_card else None,
        "versions": sorted({json.dumps(trace.versions, sort_keys=True) for trace in traces}),
        "data_snapshot_sets": sorted({json.dumps(trace.data_snapshot_ids, sort_keys=True) for trace in traces}),
        "results": results,
    }


def compare_reports(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    if baseline.get("dataset_version") != candidate.get("dataset_version"):
        reasons.append("평가 데이터셋 버전이 다릅니다.")
    if baseline.get("fixture_refs") != candidate.get("fixture_refs"):
        reasons.append("fixture 참조 집합이 다릅니다.")
    if baseline.get("data_snapshot_sets") != candidate.get("data_snapshot_sets"):
        reasons.append("실행 trace의 data snapshot 집합이 다릅니다.")

    before = {row["case_id"]: row for row in baseline.get("results", [])}
    after = {row["case_id"]: row for row in candidate.get("results", [])}
    if before.keys() != after.keys():
        reasons.append("실행된 case_id 집합이 다릅니다.")
    regressions = [
        case_id for case_id in sorted(before.keys() & after.keys())
        if after[case_id]["status"] == "FAIL" and before[case_id]["status"] != "FAIL"
    ]
    improvements = [
        case_id for case_id in sorted(before.keys() & after.keys())
        if before[case_id]["status"] == "FAIL" and after[case_id]["status"] != "FAIL"
    ]
    baseline_prices = baseline.get("price_card_version")
    candidate_prices = candidate.get("price_card_version")
    if baseline_prices != candidate_prices:
        reasons.append("가격표 버전이 달라 비용 비교는 직접 비교할 수 없습니다.")
    before_cost = baseline.get("metrics", {}).get("estimated_cost_usd_total")
    after_cost = candidate.get("metrics", {}).get("estimated_cost_usd_total")
    cost_delta = (
        round(after_cost - before_cost, 10)
        if baseline_prices == candidate_prices and before_cost is not None and after_cost is not None
        else None
    )
    before_metrics = baseline.get("metrics", {})
    after_metrics = candidate.get("metrics", {})
    return {
        "comparable": not any("버전이 다릅니다" in reason or "집합이 다릅니다" in reason for reason in reasons),
        "reasons": reasons,
        "dataset_version": candidate.get("dataset_version"),
        "baseline_versions": baseline.get("versions", []),
        "candidate_versions": candidate.get("versions", []),
        "regression_case_ids": regressions,
        "improved_case_ids": improvements,
        "baseline_pass_rate": baseline.get("automated_pass_rate"),
        "candidate_pass_rate": candidate.get("automated_pass_rate"),
        "p95_delta": {
            metric: (
                round(after_metrics[metric] - before_metrics[metric], 2)
                if after_metrics.get(metric) is not None and before_metrics.get(metric) is not None
                else None
            )
            for metric in ("duration_ms_p95", "input_tokens_p95", "output_tokens_p95")
        },
        "estimated_cost_usd_delta": cost_delta,
        "price_card_version": candidate_prices if baseline_prices == candidate_prices else None,
    }
