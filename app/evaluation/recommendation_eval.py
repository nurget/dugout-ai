"""Evaluate recommendation rankings against explicitly reviewed labels."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from app.services.pitching_recommendation import recommend_bullpen


def load_recommendation_dataset(path: Path) -> list[dict[str, Any]]:
    cases = []
    case_ids: set[str] = set()
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            case = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: 잘못된 JSONL") from exc
        if not isinstance(case, dict):
            raise ValueError(f"{path}:{line_number}: 케이스는 객체여야 합니다.")
        required = {
            "dataset_version", "case_id", "record_type", "label_status",
            "fixture_ref", "candidate_ids", "acceptable_candidate_ids",
        }
        missing = required - case.keys()
        if missing:
            raise ValueError(
                f"{path}:{line_number}: 필수 필드 누락: {', '.join(sorted(missing))}"
            )
        case_id = case["case_id"]
        if not isinstance(case_id, str) or not case_id or case_id in case_ids:
            raise ValueError(f"{path}:{line_number}: case_id가 비었거나 중복")
        if case["record_type"] not in {"SYNTHETIC", "HUMAN_REVIEWED_REAL"}:
            raise ValueError(f"{path}:{line_number}: record_type이 유효하지 않습니다.")
        if case["label_status"] not in {"SYNTHETIC", "PENDING", "APPROVED"}:
            raise ValueError(f"{path}:{line_number}: label_status가 유효하지 않습니다.")
        if case["record_type"] == "SYNTHETIC" and case["label_status"] != "SYNTHETIC":
            raise ValueError(f"{path}:{line_number}: synthetic 케이스의 label_status 오류")
        if case["record_type"] == "HUMAN_REVIEWED_REAL" and case["label_status"] == "SYNTHETIC":
            raise ValueError(f"{path}:{line_number}: 실제 케이스에 synthetic label 불가")
        candidate_ids = case["candidate_ids"]
        acceptable_ids = case["acceptable_candidate_ids"]
        if (
            not isinstance(candidate_ids, list)
            or not candidate_ids
            or len(candidate_ids) != len(set(candidate_ids))
            or not isinstance(acceptable_ids, list)
            or not set(acceptable_ids).issubset(candidate_ids)
        ):
            raise ValueError(f"{path}:{line_number}: 후보 또는 허용 라벨이 유효하지 않습니다.")
        if case["record_type"] == "HUMAN_REVIEWED_REAL" and not case.get("reviewer_id"):
            raise ValueError(f"{path}:{line_number}: 실제 라벨에는 reviewer_id가 필요합니다.")
        if case["record_type"] == "HUMAN_REVIEWED_REAL":
            for field in (
                "team_code", "as_of_date", "data_snapshot_id",
                "candidate_pool_source", "label_protocol_version",
            ):
                if not isinstance(case.get(field), str) or not case[field].strip():
                    raise ValueError(f"{path}:{line_number}: 실제 라벨에는 {field}가 필요합니다.")
            try:
                date.fromisoformat(case["as_of_date"])
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: as_of_date 형식 오류") from exc
            if not acceptable_ids:
                raise ValueError(f"{path}:{line_number}: 실제 평가에는 허용 후보 라벨이 필요합니다.")
        case_ids.add(case_id)
        cases.append(case)
    if not cases:
        raise ValueError(f"{path}: 평가 케이스가 없습니다.")
    return cases


def load_recommendation_fixtures(path: Path) -> dict[str, dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"fixture를 읽을 수 없습니다: {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("fixtures"), list):
        raise ValueError(f"{path}: fixtures 배열이 필요합니다.")
    if not isinstance(payload.get("notice"), str) or not payload["notice"].strip():
        raise ValueError(f"{path}: fixture 고지가 필요합니다.")
    fixtures = {}
    for fixture in payload["fixtures"]:
        if (
            not isinstance(fixture, dict)
            or fixture.get("record_type") not in {"SYNTHETIC", "HUMAN_REVIEWED_REAL"}
        ):
            raise ValueError(f"{path}: fixture record_type이 유효하지 않습니다.")
        ref = fixture.get("fixture_ref")
        if not isinstance(ref, str) or not ref or ref in fixtures:
            raise ValueError(f"{path}: fixture_ref가 비었거나 중복입니다.")
        fixtures[ref] = fixture
    return fixtures


def evaluate_recommendation_dataset(
    cases: list[dict[str, Any]],
    fixtures: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    results = []
    for case in cases:
        fixture = fixtures.get(case["fixture_ref"])
        if fixture is None:
            results.append({"case_id": case["case_id"], "error": "fixture 누락"})
            continue
        if case["record_type"] == "SYNTHETIC" and fixture.get("record_type") != "SYNTHETIC":
            results.append({"case_id": case["case_id"], "error": "fixture 유형 불일치"})
            continue
        if (
            case["record_type"] == "HUMAN_REVIEWED_REAL"
            and fixture.get("record_type") != "HUMAN_REVIEWED_REAL"
        ):
            results.append({"case_id": case["case_id"], "error": "fixture 유형 불일치"})
            continue

        inputs = fixture["recommendation_input"]
        recommendation = recommend_bullpen(
            team_code=inputs["team_code"],
            verified_candidate_ids=case["candidate_ids"],
            season_pitchers=inputs["season_pitchers"],
            workloads=inputs["workloads"],
        )
        ranked_ids = [row["pitcher_id"] for row in recommendation["ranking"]]
        acceptable = set(case["acceptable_candidate_ids"])
        acceptable_ranks = [
            index for index, pitcher_id in enumerate(ranked_ids, 1)
            if pitcher_id in acceptable
        ]
        reciprocal_rank = 1 / min(acceptable_ranks) if acceptable_ranks else 0.0
        results.append({
            "case_id": case["case_id"],
            "record_type": case["record_type"],
            "label_status": case["label_status"],
            "ranked_candidate_ids": ranked_ids,
            "acceptable_candidate_ids": sorted(acceptable),
            "top1_acceptable": bool(ranked_ids and ranked_ids[0] in acceptable),
            "reciprocal_rank": round(reciprocal_rank, 4),
            "candidate_coverage": round(
                len(set(ranked_ids) & set(case["candidate_ids"]))
                / len(case["candidate_ids"]),
                4,
            ),
            "withheld_count": len(recommendation["withheld"]),
        })

    approved_real = [
        result for result in results
        if result.get("record_type") == "HUMAN_REVIEWED_REAL"
        and result.get("label_status") == "APPROVED"
        and "error" not in result
    ]
    if approved_real:
        real_metrics = {
            "n": len(approved_real),
            "top1_acceptable_rate": round(
                sum(result["top1_acceptable"] for result in approved_real)
                / len(approved_real),
                4,
            ),
            "mean_reciprocal_rank": round(
                sum(result["reciprocal_rank"] for result in approved_real)
                / len(approved_real),
                4,
            ),
            "mean_candidate_coverage": round(
                sum(result["candidate_coverage"] for result in approved_real)
                / len(approved_real),
                4,
            ),
        }
    else:
        real_metrics = {
            "n": 0,
            "top1_acceptable_rate": None,
            "mean_reciprocal_rank": None,
            "mean_candidate_coverage": None,
        }
    return {
        "result_count": len(results),
        "synthetic_count": sum(
            result.get("record_type") == "SYNTHETIC" for result in results
        ),
        "approved_real_metrics": real_metrics,
        "results": results,
        "interpretation": (
            "허용 후보 라벨에 대한 순위 일치도입니다. 실제 경기 성과, 승률 또는 "
            "교체 성공 확률을 의미하지 않습니다."
        ),
    }
