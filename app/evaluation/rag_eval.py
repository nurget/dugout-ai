"""Deterministic checks for public-document RAG retrieval and citations."""

import json
from pathlib import Path
from typing import Any


def load_rag_dataset(path: Path) -> list[dict[str, Any]]:
    cases = []
    seen_ids = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: 잘못된 JSONL") from exc
        if not isinstance(case, dict):
            raise ValueError(f"{path}:{line_number}: 케이스는 객체여야 합니다.")
        for field in (
            "dataset_version", "case_id", "category", "query", "fixture_ref",
            "retrieval_expectations", "answer_expectations",
        ):
            if field not in case:
                raise ValueError(f"{path}:{line_number}: {field} 누락")
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(f"{path}:{line_number}: case_id가 비었거나 중복")
        if not isinstance(case["retrieval_expectations"], dict):
            raise ValueError(f"{path}:{line_number}: retrieval_expectations는 객체여야 합니다.")
        if not isinstance(case["answer_expectations"], dict):
            raise ValueError(f"{path}:{line_number}: answer_expectations는 객체여야 합니다.")
        if case["retrieval_expectations"].get("visibility") != "public":
            raise ValueError(f"{path}:{line_number}: 공개 필터가 필요합니다.")
        for field in ("dataset_version", "category", "query", "fixture_ref"):
            if not isinstance(case[field], str) or not case[field].strip():
                raise ValueError(f"{path}:{line_number}: {field}는 필수 문자열입니다.")
        seen_ids.add(case_id)
        cases.append(case)
    if not cases:
        raise ValueError(f"{path}: 평가 케이스가 없습니다.")
    fixture_path = path.parent / "fixtures/v1.json"
    if fixture_path.exists():
        try:
            fixture_payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{fixture_path}: 잘못된 JSON") from exc
        if not isinstance(fixture_payload, dict):
            raise ValueError(f"{fixture_path}: fixture 파일은 객체여야 합니다.")
        if not str(fixture_payload.get("fixture_notice", "")).startswith("SYNTHETIC TEST DATA ONLY"):
            raise ValueError(f"{fixture_path}: synthetic fixture notice가 필요합니다.")
        if not isinstance(fixture_payload.get("fixtures"), list):
            raise ValueError(f"{fixture_path}: fixtures는 배열이어야 합니다.")
        fixture_refs = {
            fixture.get("fixture_ref")
            for fixture in fixture_payload.get("fixtures", [])
            if fixture.get("synthetic_only") is True
        }
        missing_refs = sorted({case["fixture_ref"] for case in cases} - fixture_refs)
        if missing_refs:
            raise ValueError(
                f"{fixture_path}: fixture 누락: {', '.join(missing_refs)}"
            )
    return cases


def _check(case_id: str, name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "check": name,
        "passed": passed,
        "detail": detail,
    }


def grade_rag_traces(
    cases: list[dict[str, Any]],
    traces: list[dict[str, Any]],
) -> dict[str, Any]:
    cases_by_id = {case["case_id"]: case for case in cases}
    traces_by_id: dict[str, dict[str, Any]] = {}
    checks: list[dict[str, Any]] = []
    for trace in traces:
        case_id = trace.get("case_id")
        if not isinstance(case_id, str) or case_id not in cases_by_id:
            checks.append(_check(
                str(case_id), "known_case", False,
                "trace에 평가 데이터셋에 없는 case_id가 있습니다.",
            ))
            continue
        if case_id in traces_by_id:
            checks.append(_check(
                str(case_id), "unique_trace", False,
                "case_id trace가 중복되었습니다.",
            ))
            continue
        traces_by_id[case_id] = trace

    for case in cases:
        case_id = case["case_id"]
        trace = traces_by_id.get(case_id)
        if trace is None:
            checks.append(_check(case_id, "trace_present", False, "trace가 없습니다."))
            continue
        retrieval_expectations = case["retrieval_expectations"]
        answer_expectations = case["answer_expectations"]
        results = trace.get("retrieved_results", [])
        answer = trace.get("answer", "")
        result_shapes_valid = isinstance(results, list) and all(
            isinstance(result, dict) for result in results
        )
        if not isinstance(results, list):
            results = []
        elif not result_shapes_valid:
            results = [result for result in results if isinstance(result, dict)]
        if not isinstance(answer, str):
            answer = ""
        checks.append(_check(
            case_id,
            "trace_shape",
            result_shapes_valid and isinstance(trace.get("answer", ""), str),
            "retrieved_results는 객체 배열, answer는 문자열이어야 합니다.",
        ))

        expected_visibility = retrieval_expectations.get("visibility")
        checks.append(_check(
            case_id,
            "visibility_filter",
            trace.get("visibility_filter") == expected_visibility,
            f"expected={expected_visibility}; actual={trace.get('visibility_filter')}",
        ))
        result_limit = retrieval_expectations.get("max_results")
        checks.append(_check(
            case_id,
            "result_limit",
            isinstance(result_limit, int)
            and trace.get("result_limit") == result_limit
            and len(results) <= result_limit,
            f"limit={trace.get('result_limit')}; results={len(results)}",
        ))
        if answer_expectations.get("forbid_non_public_source_content"):
            checks.append(_check(
                case_id,
                "public_sources_only",
                all(result.get("visibility") == "public" for result in results),
                f"retrieved={len(results)}",
            ))

        required_fields = retrieval_expectations.get("required_source_fields", [])
        for field in required_fields:
            checks.append(_check(
                case_id,
                f"source_field:{field}",
                bool(results) and all(result.get(field) for result in results),
                f"retrieved={len(results)}",
            ))

        if answer_expectations.get("require_citation"):
            citations = [
                str(result.get(field))
                for result in results
                for field in ("source_url", "title")
                if result.get(field)
            ]
            checks.append(_check(
                case_id,
                "answer_cites_retrieved_source",
                bool(citations) and any(citation in answer for citation in citations),
                "답변에 검색된 source_url 또는 title 포함 여부",
            ))
        if answer_expectations.get("require_effective_date_when_present"):
            dates = [
                result.get("effective_date")
                for result in results
                if result.get("effective_date")
            ]
            checks.append(_check(
                case_id,
                "answer_mentions_effective_date",
                not dates or any(str(effective_date) in answer for effective_date in dates),
                f"effective_dates={dates}",
            ))
        if answer_expectations.get("state_no_evidence"):
            phrases = answer_expectations.get("no_evidence_phrases", [])
            checks.append(_check(
                case_id,
                "no_evidence_disclosed",
                not results and any(phrase in answer for phrase in phrases),
                f"retrieved={len(results)}",
            ))
        for forbidden in answer_expectations.get("forbidden_answer_contains", []):
            checks.append(_check(
                case_id,
                "forbidden_answer_text",
                forbidden not in answer,
                f"forbidden={forbidden}",
            ))
        if answer_expectations.get("forbid_claiming_currentness_without_evidence"):
            currentness_claims = ("현재 시행 중", "최신 규정", "현재 규정입니다")
            currentness_verified = trace.get("currentness_verified") is True
            checks.append(_check(
                case_id,
                "currentness_claim_supported",
                currentness_verified or not any(term in answer for term in currentness_claims),
                f"currentness_verified={currentness_verified}",
            ))

    failed = sum(not check["passed"] for check in checks)
    return {
        "dataset_version": sorted({case["dataset_version"] for case in cases}),
        "case_count": len(cases),
        "trace_count": len(traces_by_id),
        "check_count": len(checks),
        "passed_checks": len(checks) - failed,
        "failed_checks": failed,
        "checks": checks,
        "manual_review_required": [
            case["case_id"] for case in cases
            if case["answer_expectations"].get("forbid_unsupported_claims")
            or case["answer_expectations"].get("forbid_fabricated_answer")
            or case["answer_expectations"].get("treat_document_as_untrusted_data")
        ],
    }
