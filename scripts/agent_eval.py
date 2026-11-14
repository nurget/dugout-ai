"""Validate, run, and grade the versioned DUGOUT AI Agent evaluation set."""

import argparse
import asyncio
import hashlib
import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from app.evaluation.agent_eval import (
    EvalCase,
    EvalTrace,
    TraceMetrics,
    TraceToolCall,
    compare_reports,
    database_fixture_snapshot_id,
    grade_dataset,
    load_dataset,
    load_price_card,
    load_traces,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "evals" / "agent" / "v1.jsonl"
FIXTURE_DIR = ROOT / "evals" / "agent" / "fixtures"
PRIVATE_DIR = (ROOT / "data" / "private").resolve()
NO_DATA_FIXTURES = {"no-data-required", "no-live-game-required"}


def _jsonl_write(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.fchmod(descriptor, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as output:
        for row in rows:
            output.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    os.chmod(path, 0o600)


def _load_eval_fixture(case: EvalCase) -> tuple[dict[str, Any], str] | None:
    for path in sorted(FIXTURE_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("fixture_ref") == case.fixture_ref:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            return payload, f"sha256:{digest}"
    return None


def _fixture_tool_executor(fixture: dict[str, Any]):
    async def execute_fixture_tool(*, session, tool_name, arguments, context):
        tool_fixture = fixture.get("tools", {}).get(tool_name)
        if tool_fixture is None:
            return {
                "ok": False,
                "error": {
                    "code": "FIXTURE_TOOL_NOT_CONFIGURED",
                    "message": "이 평가 fixture에 정의되지 않은 Tool입니다.",
                },
            }
        if tool_fixture.get("ok") is False:
            return tool_fixture
        return {"ok": True, "data": tool_fixture["data"]}

    return execute_fixture_tool


async def _run_case(case: EvalCase) -> EvalTrace:
    from openai import AsyncOpenAI

    from app.agent.context import AgentContext
    from app.agent.streaming import stream_agent
    from app.core.config import settings
    from app.db.session import AsyncSessionLocal
    from app.services.data_catalog import get_latest_dataset_statuses

    if not settings.openai_api_key:
        raise RuntimeError("실제 평가 실행에는 OPENAI_API_KEY 설정이 필요합니다.")
    calls: list[TraceToolCall] = []
    answer_parts: list[str] = []
    versions: dict[str, str] = {}
    snapshots: dict[str, str | None] = {}
    metrics = TraceMetrics()
    cached_counts: list[int] = []
    run_status = "FAILED"
    fixture_entry = _load_eval_fixture(case)
    fixture = fixture_entry[0] if fixture_entry else None
    fixture_snapshot = fixture_entry[1] if fixture_entry else None

    def capture_tool_call(name: str, arguments: dict[str, Any]) -> None:
        calls.append(TraceToolCall(name=name, arguments=arguments))

    async with AsyncSessionLocal() as session:
        if fixture:
            snapshots[fixture["snapshot_key"]] = fixture_snapshot
        elif case.fixture_ref in NO_DATA_FIXTURES:
            snapshots = {}
        else:
            statuses = await get_latest_dataset_statuses(session)
            snapshots = {row["dataset"]: row["snapshot_id"] for row in statuses}
            snapshots["eval_fixture:database"] = await database_fixture_snapshot_id(session)
        if not case.expected_data_snapshot_ids and not fixture and case.fixture_ref not in NO_DATA_FIXTURES:
            raise RuntimeError(
                f"{case.case_id}: 실제 실행 전에 expected_data_snapshot_ids를 pin해야 합니다."
            )
        mismatches = {
            key: {"expected": expected, "actual": snapshots.get(key)}
            for key, expected in case.expected_data_snapshot_ids.items()
            if snapshots.get(key) != expected
        }
        if mismatches:
            raise RuntimeError(
                f"{case.case_id}: pin한 fixture snapshot과 현재 DB가 다릅니다: {mismatches}"
            )
        context = AgentContext(
            user_id="local-agent-eval",
            team_code=case.context.team_code or "",
            role=case.context.role or "FAN",
            as_of_date=(
                date.fromisoformat(case.context.as_of_date)
                if case.context.as_of_date else None
            ),
            data_snapshot_ids=snapshots,
        )
        async with AsyncOpenAI(
            api_key=settings.openai_api_key,
            timeout=20.0,
            max_retries=0,
        ) as client:
            async for event_name, data in stream_agent(
                message=case.user_message,
                session=session,
                client=client,
                context=context,
                on_tool_call=capture_tool_call,
                tool_executor=_fixture_tool_executor(fixture) if fixture else None,
            ):
                if event_name == "started":
                    versions = {
                        key: data[key]
                        for key in ("model", "prompt_version", "tool_schema_version")
                        if data.get(key) is not None
                    }
                elif event_name == "tool_result":
                    for call in reversed(calls):
                        if call.name == data["tool"] and call.success is None:
                            call.success = bool(data["ok"])
                            break
                elif event_name == "answer_delta":
                    answer_parts.append(data["delta"])
                elif event_name == "completed":
                    run_status = "COMPLETED"
                    cached_counts = [
                        int(call["cached_input_tokens"])
                        for call in data.get("llm_call_metrics", [])
                        if call.get("cached_input_tokens") is not None
                    ]
                    metrics = TraceMetrics(
                        llm_calls=data.get("llm_calls"),
                        input_tokens=data.get("input_tokens"),
                        cached_input_tokens=sum(cached_counts) if cached_counts else None,
                        output_tokens=data.get("output_tokens"),
                        duration_ms=data.get("duration_ms"),
                        llm_call_metrics=data.get("llm_call_metrics", []),
                    )
                elif event_name == "error":
                    run_status = "FAILED"
                    cached_counts = [
                        int(call["cached_input_tokens"])
                        for call in data.get("llm_call_metrics", [])
                        if call.get("cached_input_tokens") is not None
                    ]
                    metrics = TraceMetrics(
                        llm_calls=data.get("llm_calls"),
                        input_tokens=data.get("input_tokens"),
                        cached_input_tokens=sum(cached_counts) if cached_counts else None,
                        output_tokens=data.get("output_tokens"),
                        duration_ms=data.get("duration_ms"),
                        llm_call_metrics=data.get("llm_call_metrics", []),
                    )

    return EvalTrace(
        case_id=case.case_id,
        fixture_ref=case.fixture_ref,
        run_status=run_status,
        context=case.context,
        data_snapshot_ids=snapshots,
        versions=versions,
        tool_calls=calls,
        answer="".join(answer_parts),
        metrics=metrics,
    )


async def _run_live(cases: list[EvalCase], output: Path) -> None:
    traces = []
    _jsonl_write(output, traces)
    for index, case in enumerate(cases, 1):
        print(f"[{index}/{len(cases)}] {case.case_id}: 실행 중")
        trace = await _run_case(case)
        traces.append(trace.model_dump(mode="json"))
        _jsonl_write(output, traces)
        print(f"[{index}/{len(cases)}] {case.case_id}: {trace.run_status}")
    print(f"민감한 실행 trace 저장: {output}")


async def _print_fixture_snapshot() -> None:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as session:
        fixture_id = await database_fixture_snapshot_id(session)
    print(json.dumps({"eval_fixture:database": fixture_id}, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "snapshot", "run", "grade", "compare"))
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--traces", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--price-card", type=Path)
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--candidate-report", type=Path)
    parser.add_argument("--case-id", action="append", dest="case_ids")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    try:
        cases = load_dataset(args.dataset)
        if args.command == "validate":
            categories = sorted({case.category for case in cases})
            versions = sorted({case.dataset_version for case in cases})
            print(f"유효한 평가 데이터: {len(cases)}건; version={','.join(versions)}")
            print(f"범주: {', '.join(categories)}")
            return

        if args.command == "snapshot":
            asyncio.run(_print_fixture_snapshot())
            return

        if args.command == "run":
            output = args.traces or PRIVATE_DIR / "agent_eval_traces.jsonl"
            resolved = output.resolve()
            if not resolved.is_relative_to(PRIVATE_DIR):
                raise ValueError("실제 실행 trace는 민감할 수 있으므로 data/private/ 아래에만 저장합니다.")
            if resolved.exists() and not args.overwrite:
                raise ValueError(f"기존 trace 파일이 있습니다. 덮어쓰려면 --overwrite를 지정하세요: {resolved}")
            if args.case_ids:
                unknown = sorted(set(args.case_ids) - {case.case_id for case in cases})
                if unknown:
                    raise ValueError(f"데이터셋에 없는 case_id: {', '.join(unknown)}")
                cases = [case for case in cases if case.case_id in set(args.case_ids)]
            if not cases:
                raise ValueError("실행할 평가 케이스가 없습니다.")
            asyncio.run(_run_live(cases, resolved))
            return

        if args.command == "compare":
            if args.baseline is None or args.candidate_report is None:
                raise ValueError("compare 명령에는 --baseline과 --candidate-report가 필요합니다.")
            baseline = json.loads(args.baseline.read_text(encoding="utf-8"))
            candidate = json.loads(args.candidate_report.read_text(encoding="utf-8"))
            comparison = compare_reports(baseline, candidate)
            rendered = json.dumps(comparison, ensure_ascii=False, indent=2)
            if args.report:
                report_path = args.report.resolve()
                if not report_path.is_relative_to(PRIVATE_DIR):
                    raise ValueError("비교 결과는 data/private/ 아래에만 저장합니다.")
                report_path.parent.mkdir(parents=True, exist_ok=True)
                report_path.write_text(rendered + "\n", encoding="utf-8")
                os.chmod(report_path, 0o600)
            print(rendered)
            return

        if args.traces is None:
            raise ValueError("grade 명령에는 --traces가 필요합니다.")
        price_card = load_price_card(args.price_card) if args.price_card else None
        report = grade_dataset(cases, load_traces(args.traces), price_card=price_card)
        rendered = json.dumps(report, ensure_ascii=False, indent=2)
        if args.report:
            report_path = args.report.resolve()
            if not report_path.is_relative_to(PRIVATE_DIR):
                raise ValueError("실행 결과 보고서는 data/private/ 아래에만 저장합니다.")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(rendered + "\n", encoding="utf-8")
            os.chmod(report_path, 0o600)
        print(rendered)
    except (OSError, ValueError, RuntimeError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
